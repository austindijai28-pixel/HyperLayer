"""
WebSocket connection handler: ties together protocol parsing, session
manifest, offset-based storage, sliding-window flow control, and hashing
into the actual per-connection transfer state machine.

One WebSocket connection == one active transfer session at a time (the
UI only opens one persistent socket per the "ONE PERSISTENT WEBSOCKET"
architecture in the design doc).
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
import uuid

from fastapi import WebSocket, WebSocketDisconnect

from . import config
from . import protocol
from .storage import ChunkFileWriter, StorageError, InsufficientStorageError
from .session_manager import SessionStore, SessionManifest, InvalidTransitionError
from .flow_control import WindowState
from .utils import sanitize_filename
from . import ws_protocol_messages as M

logger = logging.getLogger("hyperlocal")

_session_store = SessionStore()


class ConnectionState:
    """Per-WebSocket-connection mutable state for the active transfer."""

    def __init__(self):
        self.manifest: SessionManifest | None = None
        self.writer: ChunkFileWriter | None = None
        self.window = WindowState()
        self.start_time: float | None = None

    def cleanup(self):
        if self.writer is not None:
            self.writer.close()


async def _send_json(ws: WebSocket, payload: dict) -> None:
    await ws.send_text(json.dumps(payload))


async def _send_error(ws: WebSocket, code: str, message: str) -> None:
    # Never leak raw exception text/stack traces to the client.
    await _send_json(ws, {"type": M.MSG_ERROR, "code": code, "message": message})


async def handle_init(ws: WebSocket, state: ConnectionState, msg: dict) -> None:
    file_name = sanitize_filename(str(msg.get("file_name", "")))
    file_size = int(msg.get("file_size", 0))
    chunk_size = int(msg.get("chunk_size", config.CHUNK_SIZE))
    file_hash = msg.get("file_hash")

    if chunk_size not in config.ALLOWED_CHUNK_SIZES:
        await _send_error(ws, M.ERR_INVALID_CHUNK, "chunk_size not in allowed set")
        return
    if file_size <= 0:
        await _send_error(ws, M.ERR_INVALID_CHUNK, "file_size must be positive")
        return

    manifest = SessionManifest.new(file_name, file_size, chunk_size, file_hash)
    manifest.transition("TRANSFERRING")
    _session_store.save(manifest)

    writer = ChunkFileWriter(manifest.session_id, manifest.file_name, manifest.file_size)
    try:
        writer.open()
    except InsufficientStorageError as exc:
        await _send_error(ws, M.ERR_INSUFFICIENT_STORAGE, str(exc))
        return
    except StorageError as exc:
        await _send_error(ws, M.ERR_DISK_WRITE_FAILED, str(exc))
        return

    state.manifest = manifest
    state.writer = writer
    state.window = WindowState()
    state.start_time = time.time()

    logger.info("Transfer initialized: %s (%d bytes, %d chunks)",
                manifest.file_name, manifest.file_size, manifest.total_chunks)

    await _send_json(ws, {
        "type": M.MSG_SESSION_READY,
        "session_id": manifest.session_id,
        "file_id": manifest.file_id,
        "total_chunks": manifest.total_chunks,
        "chunk_size": manifest.chunk_size,
        "window_size": state.window.window_size,
        "missing_chunks": manifest.missing_chunks(),
        "resumed": False,
    })


async def handle_resume_request(ws: WebSocket, state: ConnectionState, msg: dict) -> None:
    session_id = str(msg.get("session_id", ""))
    manifest = _session_store.load(session_id)
    if manifest is None:
        await _send_error(ws, M.ERR_INVALID_SESSION, "unknown or expired session_id")
        return

    try:
        if manifest.status in ("PAUSED", "INTERRUPTED", "FAILED"):
            manifest.transition("RESUMING")
            manifest.transition("TRANSFERRING")
        _session_store.save(manifest)
    except InvalidTransitionError as exc:
        await _send_error(ws, M.ERR_INVALID_SESSION, str(exc))
        return

    writer = ChunkFileWriter(manifest.session_id, manifest.file_name, manifest.file_size)
    try:
        writer.open()  # re-opens/truncates-to-same-size; existing bytes on disk are preserved
    except StorageError as exc:
        await _send_error(ws, M.ERR_DISK_WRITE_FAILED, str(exc))
        return

    state.manifest = manifest
    state.writer = writer
    state.window = WindowState()
    state.start_time = time.time()

    missing = manifest.missing_chunks()
    logger.info("Transfer resumed: %s (%d/%d chunks missing)",
                manifest.file_name, len(missing), manifest.total_chunks)

    await _send_json(ws, {
        "type": M.MSG_SESSION_READY,
        "session_id": manifest.session_id,
        "file_id": manifest.file_id,
        "total_chunks": manifest.total_chunks,
        "chunk_size": manifest.chunk_size,
        "window_size": state.window.window_size,
        "missing_chunks": missing,
        "resumed": True,
    })


async def handle_binary_frame(ws: WebSocket, state: ConnectionState, raw: bytes) -> None:
    if state.manifest is None or state.writer is None:
        await _send_error(ws, M.ERR_INVALID_SESSION, "no active session - send INIT first")
        return

    try:
        frame = protocol.unpack_chunk_frame(raw)
        protocol.validate_chunk_bounds(frame.chunk_index, state.manifest.total_chunks)
    except protocol.ProtocolError as exc:
        await _send_error(ws, M.ERR_MALFORMED_FRAME, str(exc))
        return

    if str(frame.file_id) != state.manifest.file_id:
        await _send_error(ws, M.ERR_INVALID_SESSION, "file_id does not match active session")
        return

    if frame.chunk_index in state.manifest.received_chunks:
        # Duplicate chunk (e.g. a retransmit that arrived after the original
        # ACK was delayed). Not an error - just re-ACK and move on.
        await _send_json(ws, {
            "type": M.MSG_CHUNK_ACK,
            "chunk_index": frame.chunk_index,
            "window_size": state.window.window_size,
            "in_flight": len(state.window.in_flight),
            "received_count": len(state.manifest.received_chunks),
            "total_chunks": state.manifest.total_chunks,
        })
        return

    # Independently verify SHA-256 of the payload server-side.
    computed = hashlib.sha256(frame.payload).digest()
    if computed != frame.sha256:
        retry_count = state.window.mark_failed(frame.chunk_index)
        state.window.shrink_window()
        if retry_count >= config.MAX_RETRIES:
            await _send_error(ws, M.ERR_RETRY_EXHAUSTED,
                               f"chunk {frame.chunk_index} exceeded max retries ({config.MAX_RETRIES})")
            return
        logger.warning("Chunk %d hash mismatch (attempt %d)", frame.chunk_index, retry_count)
        await _send_json(ws, {
            "type": M.MSG_CHUNK_RETRY,
            "chunk_index": frame.chunk_index,
            "reason": "hash_mismatch",
            "retry_count": retry_count,
        })
        return

    offset = protocol.offset_for_chunk(frame.chunk_index, state.manifest.chunk_size)
    try:
        await state.writer.write_chunk(frame.payload, offset)
    except StorageError as exc:
        await _send_error(ws, M.ERR_DISK_WRITE_FAILED, str(exc))
        return

    state.manifest.mark_chunk_received(frame.chunk_index)
    _session_store.save(state.manifest)
    state.window.mark_ack(frame.chunk_index)
    state.window.grow_window()

    await _send_json(ws, {
        "type": M.MSG_CHUNK_ACK,
        "chunk_index": frame.chunk_index,
        "window_size": state.window.window_size,
        "in_flight": len(state.window.in_flight),
        "received_count": len(state.manifest.received_chunks),
        "total_chunks": state.manifest.total_chunks,
    })

    if state.manifest.is_complete():
        await finalize_transfer(ws, state)


async def finalize_transfer(ws: WebSocket, state: ConnectionState) -> None:
    state.manifest.transition("VERIFYING")
    _session_store.save(state.manifest)

    integrity_verified = True
    computed_hash = await state.writer.compute_sha256()
    if state.manifest.file_hash:
        integrity_verified = (computed_hash == state.manifest.file_hash)

    state.manifest.transition("COMPLETED" if integrity_verified else "FAILED")
    _session_store.save(state.manifest)
    state.writer.close()

    duration = time.time() - (state.start_time or time.time())
    logger.info("Transfer complete: %s in %.2fs, integrity_verified=%s",
                state.manifest.file_name, duration, integrity_verified)

    await _send_json(ws, {
        "type": M.MSG_TRANSFER_COMPLETE,
        "integrity_verified": integrity_verified,
        "file_hash": computed_hash,
        "duration_seconds": duration,
    })


async def websocket_endpoint(ws: WebSocket) -> None:
    await ws.accept()
    state = ConnectionState()
    logger.info("WebSocket connected")
    try:
        while True:
            message = await ws.receive()
            if message.get("type") == "websocket.disconnect":
                break

            if "bytes" in message and message["bytes"] is not None:
                await handle_binary_frame(ws, state, message["bytes"])
            elif "text" in message and message["text"] is not None:
                try:
                    msg = json.loads(message["text"])
                except json.JSONDecodeError:
                    await _send_error(ws, M.ERR_MALFORMED_FRAME, "invalid JSON control message")
                    continue

                msg_type = msg.get("type")
                if msg_type == M.MSG_INIT:
                    await handle_init(ws, state, msg)
                elif msg_type == M.MSG_RESUME_REQUEST:
                    await handle_resume_request(ws, state, msg)
                else:
                    await _send_error(ws, M.ERR_MALFORMED_FRAME, f"unknown message type: {msg_type}")
    except WebSocketDisconnect:
        logger.info("WebSocket disconnected")
        if state.manifest is not None and state.manifest.status == "TRANSFERRING":
            try:
                state.manifest.transition("INTERRUPTED")
                _session_store.save(state.manifest)
            except InvalidTransitionError:
                pass
    except Exception:
        # Never propagate a raw stack trace to the client / crash the server
        # process over one bad connection.
        logger.exception("Unhandled error in websocket_endpoint")
    finally:
        state.cleanup()
