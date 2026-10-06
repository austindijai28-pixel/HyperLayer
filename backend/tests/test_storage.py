"""Unit tests for app/storage.py (offset-based positional writes)."""
import asyncio
import os
import shutil

import pytest

from app.storage import ChunkFileWriter


@pytest.mark.asyncio
async def test_out_of_order_chunk_writes_land_at_correct_offsets():
    d = "/tmp/hyperlocal_test_storage"
    if os.path.exists(d):
        shutil.rmtree(d)
    os.makedirs(d)

    chunk_size = 4
    total_size = chunk_size * 3
    writer = ChunkFileWriter("sess1", "out_of_order.bin", total_size, download_dir=d)
    writer.open()

    chunks = {0: b"AAAA", 1: b"BBBB", 2: b"CCCC"}
    # Write in reverse order to prove offset math is correct regardless of arrival order.
    for idx in [2, 0, 1]:
        offset = idx * chunk_size
        await writer.write_chunk(chunks[idx], offset)

    writer.close()

    with open(writer.path, "rb") as f:
        data = f.read()
    assert data == b"AAAABBBBCCCC"
    shutil.rmtree(d)


@pytest.mark.asyncio
async def test_final_file_hash_matches_expected():
    import hashlib

    d = "/tmp/hyperlocal_test_storage_hash"
    if os.path.exists(d):
        shutil.rmtree(d)
    os.makedirs(d)

    payload = b"the quick brown fox jumps over the lazy dog"
    writer = ChunkFileWriter("sess2", "hash_test.bin", len(payload), download_dir=d)
    writer.open()
    await writer.write_chunk(payload, 0)
    writer.close()

    # re-open just to compute hash (compute_sha256 opens its own file handle)
    writer2 = ChunkFileWriter("sess2", "hash_test.bin", len(payload), download_dir=d)
    writer2.path = writer.path
    got = await writer2.compute_sha256()
    assert got == hashlib.sha256(payload).hexdigest()
    shutil.rmtree(d)


@pytest.mark.asyncio
async def test_open_creates_missing_download_dir():
    d = "/tmp/hyperlocal_test_storage_missing_dir/nested/dir"
    if os.path.exists("/tmp/hyperlocal_test_storage_missing_dir"):
        shutil.rmtree("/tmp/hyperlocal_test_storage_missing_dir")
    # Note: directory does NOT exist yet - open() must create it.
    writer = ChunkFileWriter("sess4", "f.bin", 4, download_dir=d)
    writer.open()
    assert os.path.isdir(d)
    writer.close()
    shutil.rmtree("/tmp/hyperlocal_test_storage_missing_dir")


def test_write_beyond_file_size_rejected():
    import asyncio as _asyncio

    d = "/tmp/hyperlocal_test_storage_bounds"
    if os.path.exists(d):
        shutil.rmtree(d)
    os.makedirs(d)

    writer = ChunkFileWriter("sess3", "small.bin", 4, download_dir=d)
    writer.open()

    async def _run():
        from app.storage import StorageError
        with pytest.raises(StorageError):
            await writer.write_chunk(b"TOO_LONG_PAYLOAD", 0)

    _asyncio.run(_run())
    writer.close()
    shutil.rmtree(d)
