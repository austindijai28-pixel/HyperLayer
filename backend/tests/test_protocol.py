"""Unit tests for app/protocol.py (binary header pack/parse/validate)."""
import hashlib
import uuid

import pytest

from app import protocol


def test_pack_unpack_roundtrip():
    file_id = uuid.uuid4()
    payload = b"hello world" * 1000
    digest = hashlib.sha256(payload).digest()
    frame = protocol.pack_chunk_frame(file_id, 5, payload, digest)

    assert len(frame) == protocol.HEADER_SIZE + len(payload)

    parsed = protocol.unpack_chunk_frame(frame)
    assert parsed.file_id == file_id
    assert parsed.chunk_index == 5
    assert parsed.payload_length == len(payload)
    assert parsed.sha256 == digest
    assert parsed.payload == payload


def test_header_size_is_56_bytes():
    assert protocol.HEADER_SIZE == 56


def test_rejects_frame_shorter_than_header():
    with pytest.raises(protocol.ProtocolError):
        protocol.unpack_chunk_frame(b"too short")


def test_rejects_payload_length_mismatch():
    file_id = uuid.uuid4()
    payload = b"x" * 100
    digest = hashlib.sha256(payload).digest()
    frame = bytearray(protocol.pack_chunk_frame(file_id, 0, payload, digest))
    # Truncate the payload after the header without updating the length field.
    truncated = bytes(frame[:-10])
    with pytest.raises(protocol.ProtocolError):
        protocol.unpack_chunk_frame(truncated)


def test_rejects_payload_length_over_safe_bound():
    file_id = uuid.uuid4()
    small_payload = b"x" * 10
    digest = hashlib.sha256(small_payload).digest()
    # Manually craft a frame whose header claims a huge payload_length but
    # doesn't actually carry that many bytes.
    import struct
    header = struct.pack(">16sII32s", file_id.bytes, 0, 999_999_999, digest)
    with pytest.raises(protocol.ProtocolError):
        protocol.unpack_chunk_frame(header + small_payload)


def test_validate_chunk_bounds():
    protocol.validate_chunk_bounds(0, 10)
    protocol.validate_chunk_bounds(9, 10)
    with pytest.raises(protocol.ProtocolError):
        protocol.validate_chunk_bounds(10, 10)
    with pytest.raises(protocol.ProtocolError):
        protocol.validate_chunk_bounds(-1, 10)


def test_offset_calculation():
    assert protocol.offset_for_chunk(0, 5 * 1024 * 1024) == 0
    assert protocol.offset_for_chunk(1, 5 * 1024 * 1024) == 5 * 1024 * 1024
    assert protocol.offset_for_chunk(3, 5 * 1024 * 1024) == 15 * 1024 * 1024
    with pytest.raises(protocol.ProtocolError):
        protocol.offset_for_chunk(-1, 5)
