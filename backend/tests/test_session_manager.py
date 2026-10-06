"""Unit tests for app/session_manager.py (manifest, resume, state machine)."""
import os
import shutil
import pytest

from app.session_manager import SessionManifest, SessionStore, InvalidTransitionError


def test_new_manifest_computes_total_chunks():
    m = SessionManifest.new("file.bin", file_size=25 * 1024 * 1024, chunk_size=5 * 1024 * 1024)
    assert m.total_chunks == 5
    assert m.status == "INITIALIZED"


def test_total_chunks_rounds_up_for_partial_last_chunk():
    m = SessionManifest.new("file.bin", file_size=12 * 1024 * 1024, chunk_size=5 * 1024 * 1024)
    assert m.total_chunks == 3  # 5 + 5 + 2


def test_missing_chunks_and_mark_received():
    m = SessionManifest.new("file.bin", file_size=15, chunk_size=5)
    assert m.missing_chunks() == [0, 1, 2]
    m.mark_chunk_received(1)
    assert m.missing_chunks() == [0, 2]
    assert not m.is_complete()
    m.mark_chunk_received(0)
    m.mark_chunk_received(2)
    assert m.is_complete()


def test_mark_received_is_idempotent():
    m = SessionManifest.new("file.bin", file_size=10, chunk_size=5)
    m.mark_chunk_received(0)
    m.mark_chunk_received(0)
    assert m.received_chunks == [0]


def test_valid_state_transitions():
    m = SessionManifest.new("f.bin", 10, 5)
    m.transition("TRANSFERRING")
    m.transition("INTERRUPTED")
    m.transition("RESUMING")
    m.transition("TRANSFERRING")
    m.transition("VERIFYING")
    m.transition("COMPLETED")
    assert m.status == "COMPLETED"


def test_invalid_state_transition_rejected():
    m = SessionManifest.new("f.bin", 10, 5)
    with pytest.raises(InvalidTransitionError):
        m.transition("COMPLETED")  # can't jump straight from INITIALIZED


def test_session_store_persists_and_reloads(tmp_path=None):
    d = "/tmp/hyperlocal_test_sessions"
    if os.path.exists(d):
        shutil.rmtree(d)
    store = SessionStore(session_dir=d)
    m = SessionManifest.new("f.bin", 20, 5)
    m.mark_chunk_received(0)
    store.save(m)

    store2 = SessionStore(session_dir=d)  # fresh instance, no in-memory cache
    reloaded = store2.load(m.session_id)
    assert reloaded is not None
    assert reloaded.received_chunks == [0]
    assert reloaded.file_name == "f.bin"
    shutil.rmtree(d)


def test_session_store_unknown_id_returns_none():
    store = SessionStore(session_dir="/tmp/hyperlocal_test_sessions_2")
    assert store.load("00000000-0000-0000-0000-000000000000") is None
