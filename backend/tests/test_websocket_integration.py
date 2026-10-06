"""
Integration tests using FastAPI's TestClient (in-process, real WebSocket
protocol, no real network needed).

NOTE: This file requires `fastapi`, `starlette`, and `httpx` to be
installed. This sandbox environment had no internet access and could not
install them, so this specific file was written carefully but NOT executed
here - unlike tests/test_protocol.py, test_storage.py, test_session_manager.py,
and test_flow_control.py, which WERE run (see PROJECT_STATUS.md).

Run it yourself after `pip install -r requirements.txt`:
    pytest tests/test_websocket_integration.py -v
"""
import hashlib
import json
import os
import shutil
import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app import config


@pytest.fixture(autouse=True)
def isolated_storage(tmp_path, monkeypatch):
    """Redirect storage/session dirs to a temp dir for each test."""
    download_dir = tmp_path / "downloads"
    session_dir = tmp_path / "sessions"
    download_dir.mkdir()
    session_dir.mkdir()
    monkeypatch.setattr(config, "DOWNLOAD_DIRECTORY", str(download_dir))
    monkeypatch.setattr(config, "SESSION_DIRECTORY", str(session_dir))
    yield


def test_health_endpoint():
    client = TestClient(app)
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_info_endpoint_returns_config():
    client = TestClient(app)
    resp = client.get("/api/info")
    body = resp.json()
    assert "local_ip" in body
    assert body["chunk_size"] == config.CHUNK_SIZE


def test_full_transfer_over_websocket():
    client = TestClient(app)
    payload = b"HyperLocal integration test payload!" * 10000  # ~370KB
    chunk_size = 1 * 1024 * 1024  # bigger than payload -> 1 chunk

    with client.websocket_connect("/ws") as ws:
        ws.send_text(json.dumps({
            "type": "INIT",
            "file_name": "integration_test.bin",
            "file_size": len(payload),
            "chunk_size": chunk_size,
        }))
        ready = json.loads(ws.receive_text())
        assert ready["type"] == "SESSION_READY"
        assert ready["total_chunks"] == 1

        file_id = uuid.UUID(ready["file_id"])
        digest = hashlib.sha256(payload).digest()

        import struct
        header = struct.pack(">16sII32s", file_id.bytes, 0, len(payload), digest)
        ws.send_bytes(header + payload)

        ack = json.loads(ws.receive_text())
        assert ack["type"] == "CHUNK_ACK"
        assert ack["chunk_index"] == 0

        complete = json.loads(ws.receive_text())
        assert complete["type"] == "TRANSFER_COMPLETE"
        assert complete["integrity_verified"] is True


def test_hash_mismatch_triggers_retry():
    client = TestClient(app)
    payload = b"data" * 100
    chunk_size = 1 * 1024 * 1024

    with client.websocket_connect("/ws") as ws:
        ws.send_text(json.dumps({
            "type": "INIT", "file_name": "bad.bin", "file_size": len(payload), "chunk_size": chunk_size,
        }))
        ready = json.loads(ws.receive_text())
        file_id = uuid.UUID(ready["file_id"])

        import struct
        wrong_digest = b"\x00" * 32
        header = struct.pack(">16sII32s", file_id.bytes, 0, len(payload), wrong_digest)
        ws.send_bytes(header + payload)

        resp = json.loads(ws.receive_text())
        assert resp["type"] == "CHUNK_RETRY"
        assert resp["reason"] == "hash_mismatch"


def test_malformed_frame_returns_error_not_crash():
    client = TestClient(app)
    with client.websocket_connect("/ws") as ws:
        ws.send_text(json.dumps({
            "type": "INIT", "file_name": "x.bin", "file_size": 100, "chunk_size": 1024 * 1024,
        }))
        json.loads(ws.receive_text())  # SESSION_READY
        ws.send_bytes(b"too short to be a valid header")
        resp = json.loads(ws.receive_text())
        assert resp["type"] == "ERROR"
        assert resp["code"] == "MALFORMED_FRAME"


def test_resume_after_simulated_disconnect():
    client = TestClient(app)
    chunk_size = 1 * 1024 * 1024
    payload = b"A" * chunk_size + b"B" * chunk_size + b"C" * chunk_size  # 3 chunks of 1MB

    session_id = None
    file_id = None
    with client.websocket_connect("/ws") as ws:
        ws.send_text(json.dumps({
            "type": "INIT", "file_name": "resume.bin", "file_size": len(payload), "chunk_size": chunk_size,
        }))
        ready = json.loads(ws.receive_text())
        session_id = ready["session_id"]
        file_id = uuid.UUID(ready["file_id"])

        import struct
        chunk0 = payload[0:chunk_size]
        digest0 = hashlib.sha256(chunk0).digest()
        header0 = struct.pack(">16sII32s", file_id.bytes, 0, len(chunk0), digest0)
        ws.send_bytes(header0 + chunk0)
        ack = json.loads(ws.receive_text())
        assert ack["type"] == "CHUNK_ACK"
        # connection closes here (simulating a drop) without sending remaining chunks

    with client.websocket_connect("/ws") as ws2:
        ws2.send_text(json.dumps({"type": "RESUME_REQUEST", "session_id": session_id}))
        resumed = json.loads(ws2.receive_text())
        assert resumed["type"] == "SESSION_READY"
        assert resumed["resumed"] is True
        assert resumed["missing_chunks"] == [1, 2]
