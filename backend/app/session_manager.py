"""
Session manifest + resumable-transfer manager.

Each transfer gets a manifest persisted as JSON to SESSION_DIRECTORY, so
that if the server process restarts or the connection drops, the manifest
(and the partially-written destination file) survive and the transfer can
resume instead of restarting from zero.

State machine:

    INITIALIZED -> TRANSFERRING -> PAUSED/INTERRUPTED -> RESUMING
                -> TRANSFERRING -> VERIFYING -> COMPLETED
                                              -> FAILED
"""
from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass, field, asdict
from typing import Optional

from . import config

VALID_TRANSITIONS = {
    "INITIALIZED": {"TRANSFERRING", "FAILED"},
    "TRANSFERRING": {"PAUSED", "INTERRUPTED", "VERIFYING", "FAILED"},
    "PAUSED": {"RESUMING", "FAILED"},
    "INTERRUPTED": {"RESUMING", "FAILED"},
    "RESUMING": {"TRANSFERRING", "FAILED"},
    "VERIFYING": {"COMPLETED", "FAILED"},
    "COMPLETED": set(),
    "FAILED": {"RESUMING"},
}


class InvalidTransitionError(Exception):
    pass


@dataclass
class SessionManifest:
    session_id: str
    file_id: str
    file_name: str
    file_size: int
    chunk_size: int
    total_chunks: int
    received_chunks: list = field(default_factory=list)  # sorted list of chunk indices
    file_hash: Optional[str] = None  # expected source hash, if client sent one
    status: str = "INITIALIZED"
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def missing_chunks(self) -> list:
        received = set(self.received_chunks)
        return [i for i in range(self.total_chunks) if i not in received]

    def mark_chunk_received(self, chunk_index: int) -> None:
        if chunk_index not in self.received_chunks:
            self.received_chunks.append(chunk_index)
            self.received_chunks.sort()
        self.updated_at = time.time()

    def is_complete(self) -> bool:
        return len(self.received_chunks) == self.total_chunks

    def transition(self, new_status: str) -> None:
        allowed = VALID_TRANSITIONS.get(self.status, set())
        if new_status != self.status and new_status not in allowed:
            raise InvalidTransitionError(f"cannot move from {self.status} to {new_status}")
        self.status = new_status
        self.updated_at = time.time()

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "SessionManifest":
        return cls(**d)

    @classmethod
    def new(cls, file_name: str, file_size: int, chunk_size: int, file_hash: Optional[str] = None) -> "SessionManifest":
        total_chunks = (file_size + chunk_size - 1) // chunk_size if file_size > 0 else 0
        return cls(
            session_id=str(uuid.uuid4()),
            file_id=str(uuid.uuid4()),
            file_name=file_name,
            file_size=file_size,
            chunk_size=chunk_size,
            total_chunks=total_chunks,
            file_hash=file_hash,
        )


class SessionStore:
    """Persists SessionManifest objects as JSON files, keyed by session_id."""

    def __init__(self, session_dir: str = None):
        self.session_dir = session_dir or config.SESSION_DIRECTORY
        os.makedirs(self.session_dir, exist_ok=True)
        self._cache: dict[str, SessionManifest] = {}

    def _path(self, session_id: str) -> str:
        # session_id is always a uuid4 string we generated ourselves, but
        # validate defensively before touching the filesystem.
        if not _is_safe_session_id(session_id):
            raise ValueError("invalid session_id")
        return os.path.join(self.session_dir, f"{session_id}.json")

    def save(self, manifest: SessionManifest) -> None:
        self._cache[manifest.session_id] = manifest
        path = self._path(manifest.session_id)
        tmp_path = path + ".tmp"
        with open(tmp_path, "w") as f:
            json.dump(manifest.to_dict(), f)
        os.replace(tmp_path, path)  # atomic on POSIX and Windows

    def load(self, session_id: str) -> Optional[SessionManifest]:
        if session_id in self._cache:
            return self._cache[session_id]
        path = self._path(session_id)
        if not os.path.exists(path):
            return None
        with open(path, "r") as f:
            data = json.load(f)
        manifest = SessionManifest.from_dict(data)
        self._cache[session_id] = manifest
        return manifest

    def delete(self, session_id: str) -> None:
        self._cache.pop(session_id, None)
        path = self._path(session_id)
        if os.path.exists(path):
            os.remove(path)


def _is_safe_session_id(session_id: str) -> bool:
    try:
        uuid.UUID(session_id)
        return True
    except (ValueError, AttributeError, TypeError):
        return False
