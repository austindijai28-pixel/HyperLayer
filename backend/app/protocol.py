"""
HyperLocal binary transfer protocol.

Every WebSocket binary frame sent by the client for file data is:

    +----------------+----------------+------------------+----------------+------------------+
    | FILE_ID (16B)  | CHUNK_IDX (4B) | PAYLOAD_LEN (4B) | SHA-256 (32B)  | PAYLOAD (N bytes)|
    +----------------+----------------+------------------+----------------+------------------+
      offset 0          offset 16        offset 20          offset 24        offset 56

Total header size = 16 + 4 + 4 + 32 = 56 bytes. Payload follows immediately.

Byte ordering: big-endian ("network order", struct format ">") is used
explicitly for the integer fields so the wire format is unambiguous
regardless of host CPU endianness.

FILE_ID is the raw 16 bytes of a UUID (uuid.UUID.bytes).
CHUNK_INDEX is an unsigned 32-bit integer (chunk number, 0-based).
PAYLOAD_LENGTH is an unsigned 32-bit integer, the exact byte length of PAYLOAD.
SHA-256 is the 32-byte digest of PAYLOAD, computed by the sender.

This module only does struct packing/parsing and validation - no I/O.
"""
from __future__ import annotations

import struct
import uuid
from dataclasses import dataclass

from . import config

# ">16s I I 32s" = big-endian: 16-byte string, uint32, uint32, 32-byte string
_HEADER_FORMAT = ">16sII32s"
HEADER_SIZE = struct.calcsize(_HEADER_FORMAT)
assert HEADER_SIZE == config.HEADER_SIZE == 56, f"header size drifted: {HEADER_SIZE}"


class ProtocolError(ValueError):
    """Raised when a frame is malformed or fails validation."""


@dataclass(frozen=True)
class ChunkFrame:
    file_id: uuid.UUID
    chunk_index: int
    payload_length: int
    sha256: bytes
    payload: bytes


def pack_chunk_frame(file_id: uuid.UUID, chunk_index: int, payload: bytes, sha256_digest: bytes) -> bytes:
    """Build a full 56-byte-header + payload binary frame."""
    if len(sha256_digest) != config.HEADER_SHA256_LEN:
        raise ProtocolError(f"sha256 digest must be {config.HEADER_SHA256_LEN} bytes")
    if chunk_index < 0 or chunk_index > 0xFFFFFFFF:
        raise ProtocolError("chunk_index out of range for uint32")
    if len(payload) > 0xFFFFFFFF:
        raise ProtocolError("payload too large for uint32 length field")
    header = struct.pack(_HEADER_FORMAT, file_id.bytes, chunk_index, len(payload), sha256_digest)
    return header + payload


def unpack_chunk_frame(raw: bytes) -> ChunkFrame:
    """
    Parse and validate a raw binary WebSocket frame into a ChunkFrame.

    Raises ProtocolError on any structural problem. Callers MUST catch this
    and respond with a safe error / CHUNK_RETRY rather than crashing the
    connection or exposing a stack trace to the client.
    """
    if not isinstance(raw, (bytes, bytearray)):
        raise ProtocolError("frame must be binary (bytes)")

    if len(raw) < HEADER_SIZE:
        raise ProtocolError(f"frame too short: {len(raw)} bytes, need at least {HEADER_SIZE}")

    file_id_bytes, chunk_index, payload_length, sha256_digest = struct.unpack(
        _HEADER_FORMAT, raw[:HEADER_SIZE]
    )

    if payload_length < 0 or payload_length > config.MAX_PAYLOAD_LENGTH:
        raise ProtocolError(f"payload_length {payload_length} outside safe bounds")

    actual_payload = raw[HEADER_SIZE:]
    if len(actual_payload) != payload_length:
        raise ProtocolError(
            f"payload_length header ({payload_length}) does not match actual payload bytes "
            f"({len(actual_payload)})"
        )

    try:
        file_id = uuid.UUID(bytes=file_id_bytes)
    except ValueError as exc:
        raise ProtocolError(f"invalid file_id bytes: {exc}") from exc

    return ChunkFrame(
        file_id=file_id,
        chunk_index=chunk_index,
        payload_length=payload_length,
        sha256=sha256_digest,
        payload=bytes(actual_payload),
    )


def validate_chunk_bounds(chunk_index: int, total_chunks: int) -> None:
    """Raise ProtocolError if chunk_index is outside the file's known chunk range."""
    if chunk_index < 0 or chunk_index >= total_chunks:
        raise ProtocolError(
            f"chunk_index {chunk_index} out of bounds for total_chunks {total_chunks}"
        )


def offset_for_chunk(chunk_index: int, chunk_size: int) -> int:
    """offset = chunkIndex * chunkSize"""
    if chunk_index < 0:
        raise ProtocolError("chunk_index cannot be negative")
    return chunk_index * chunk_size
