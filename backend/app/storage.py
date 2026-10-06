"""
Offset-based storage engine.

Chunks can arrive out of order over the WebSocket (retries, sliding-window
overlap, etc). Each chunk is written directly to its correct byte offset
in the destination file using a positional write, so ordering of arrival
does not matter.

The positional write operation is blocking, so every call is dispatched
to a thread-pool executor via `loop.run_in_executor(...)` to avoid blocking
the asyncio event loop.
"""
from __future__ import annotations

import asyncio
import os
import threading
from functools import partial

from . import config
from .utils import safe_join_download_path


class StorageError(Exception):
    pass


class InsufficientStorageError(StorageError):
    pass


class ChunkFileWriter:
    """
    Manages the on-disk destination file for a single transfer session.

    One writer per session_id. Pre-allocates the file to its final size
    (sparse where the filesystem supports it) so positional writes never
    need to extend the file, and so free-space can be checked up front.
    """

    def __init__(
        self,
        session_id: str,
        filename: str,
        file_size: int,
        download_dir: str = None,
    ):
        self.session_id = session_id
        self.download_dir = download_dir or config.DOWNLOAD_DIRECTORY
        self.path = safe_join_download_path(self.download_dir, filename)
        self.file_size = file_size
        self._fd = None

        # Windows does not provide os.pwrite(), so positional writes use
        # lseek() + write(). This lock prevents concurrent writes from
        # interfering with each other's file offsets.
        self._write_lock = threading.Lock()

    def open(self) -> None:
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        self._check_free_space()

        # Open (or reuse) the file in binary mode, then truncate/pre-allocate to file_size.
        flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_BINARY", 0)
        self._fd = os.open(self.path, flags, 0o644)

        try:
            os.ftruncate(self._fd, self.file_size)
        except OSError as exc:
            os.close(self._fd)
            self._fd = None
            raise StorageError(
                f"failed to allocate destination file: {exc}"
            ) from exc

    def _check_free_space(self) -> None:
        target_dir = os.path.dirname(self.path) or "."

        try:
            usage = os.statvfs(target_dir)
            free_bytes = usage.f_bavail * usage.f_frsize
        except (OSError, AttributeError):
            # statvfs unavailable (e.g. Windows) - skip the pre-check rather
            # than fail; the write itself will raise OSError if disk is full.
            return

        if free_bytes < self.file_size:
            raise InsufficientStorageError(
                f"only {free_bytes} bytes free, need "
                f"{self.file_size} bytes for this transfer"
            )

    def close(self) -> None:
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None

    def _pwrite_blocking(self, data: bytes, offset: int) -> int:
        if self._fd is None:
            raise StorageError("writer is not open")

        if offset < 0 or offset + len(data) > self.file_size:
            raise StorageError(
                f"write of {len(data)} bytes at offset {offset} "
                f"would exceed file size {self.file_size}"
            )

        try:
            # Windows does not provide os.pwrite().
            # Use lseek() + write() while holding a lock so concurrent
            # chunk writes cannot interfere with each other's file position.
            with self._write_lock:
                os.lseek(self._fd, offset, os.SEEK_SET)
                return os.write(self._fd, data)

        except OSError as exc:
            raise StorageError(f"disk write failed: {exc}") from exc

    async def write_chunk(
        self,
        data: bytes,
        offset: int,
        loop: asyncio.AbstractEventLoop = None,
    ) -> int:
        """Write `data` at `offset` without blocking the event loop."""
        loop = loop or asyncio.get_running_loop()
        func = partial(self._pwrite_blocking, data, offset)
        return await loop.run_in_executor(None, func)

    async def compute_sha256(
        self,
        loop: asyncio.AbstractEventLoop = None,
    ) -> str:
        """Hash the completed file on disk (blocking work off-loaded to a thread)."""
        import hashlib

        loop = loop or asyncio.get_running_loop()

        def _hash():
            h = hashlib.sha256()

            with open(self.path, "rb") as f:
                while True:
                    block = f.read(4 * 1024 * 1024)

                    if not block:
                        break

                    h.update(block)

            return h.hexdigest()

        return await loop.run_in_executor(None, _hash)