"""Unit tests for app/flow_control.py (sliding window)."""
from app.flow_control import WindowState
from app import config


def test_initial_window_matches_config():
    w = WindowState()
    assert w.window_size == config.INITIAL_WINDOW_SIZE


def test_available_slots_shrinks_as_chunks_sent():
    w = WindowState()
    start = w.available_slots()
    w.mark_sent(0)
    w.mark_sent(1)
    assert w.available_slots() == start - 2


def test_ack_frees_a_slot_and_grows_window():
    w = WindowState()
    initial_size = w.window_size
    w.mark_sent(0)
    w.mark_ack(0)
    assert 0 not in w.in_flight
    assert 0 in w.acknowledged
    assert w.window_size >= initial_size  # additive growth, capped at MAX


def test_window_never_exceeds_max():
    w = WindowState()
    for i in range(1000):
        w.mark_sent(i)
        w.mark_ack(i)
    assert w.window_size <= config.MAX_WINDOW_SIZE


def test_failed_chunk_counts_retries_and_shrink_window_halves_it():
    w = WindowState()
    w.mark_sent(0)
    count1 = w.mark_failed(0)
    assert count1 == 1
    # mark_failed() only does in-flight/retry bookkeeping; shrinking the
    # window on failure is a deliberate, separate call (see ws_handler.py),
    # so growth/shrink policy stays decoupled from ack/fail bookkeeping.
    before = w.window_size
    w.shrink_window()
    assert w.window_size == max(1, before // 2)
    count2 = w.mark_failed(0)
    assert count2 == 2


def test_retry_exhausted_after_max_retries():
    w = WindowState()
    for _ in range(config.MAX_RETRIES):
        w.mark_failed(5)
    assert w.retry_exhausted(5)


def test_window_never_below_minimum():
    w = WindowState()
    for i in range(50):
        w.mark_failed(i)
    assert w.window_size >= 1
