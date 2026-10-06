"""
Sliding-window flow control.

The sender is allowed only a bounded number of unacknowledged ("in-flight")
chunks at once. This keeps the amount of unvalidated data that can pile up
on the receiver bounded, regardless of file size.

This module implements the *server-side bookkeeping* used to tell the
client how many more chunks it may send, and to track ACKs/failures for
telemetry. The client (React) mirrors the same windowing logic - see
frontend/src/lib/transferEngine.js.

A larger window is not automatically faster: it trades a bit more
in-flight memory/buffering for the ability to keep the pipe fuller despite
round-trip latency. The optimum depends on measured RTT and disk-write
speed, which is exactly what the benchmark mode (app/benchmark.py) is for.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from . import config


@dataclass
class WindowState:
    window_size: int = config.INITIAL_WINDOW_SIZE
    in_flight: set = field(default_factory=set)      # chunk indices sent, awaiting ACK
    acknowledged: set = field(default_factory=set)    # chunk indices confirmed good
    failed_counts: dict = field(default_factory=dict)  # chunk index -> retry count

    def available_slots(self) -> int:
        return max(0, self.window_size - len(self.in_flight))

    def mark_sent(self, chunk_index: int) -> None:
        self.in_flight.add(chunk_index)

    def mark_ack(self, chunk_index: int) -> None:
        self.in_flight.discard(chunk_index)
        self.acknowledged.add(chunk_index)
        self.failed_counts.pop(chunk_index, None)

    def mark_failed(self, chunk_index: int) -> int:
        """Returns the new retry count for this chunk."""
        self.in_flight.discard(chunk_index)
        count = self.failed_counts.get(chunk_index, 0) + 1
        self.failed_counts[chunk_index] = count
        return count

    def retry_exhausted(self, chunk_index: int) -> bool:
        return self.failed_counts.get(chunk_index, 0) >= config.MAX_RETRIES

    def grow_window(self) -> None:
        """Additive increase, capped at MAX_WINDOW_SIZE."""
        self.window_size = min(config.MAX_WINDOW_SIZE, self.window_size + 1)

    def shrink_window(self) -> None:
        """Multiplicative decrease on failure, floored at MIN_WINDOW_SIZE."""
        self.window_size = max(config.MIN_WINDOW_SIZE, self.window_size // 2)

    def snapshot(self) -> dict:
        return {
            "window_size": self.window_size,
            "in_flight": len(self.in_flight),
            "acknowledged": len(self.acknowledged),
            "failed_chunks": len(self.failed_counts),
        }
