# HyperLocal — Project Status

Last updated: this build session. Read this before claiming any feature works in a demo or report — it's meant to be accurate, not aspirational.

## Build environment constraint (read this first)

This codebase was written in a sandbox with **no internet access**: `pip install fastapi` and `npm install` both failed (registry access denied). This shaped what could be *verified by actually running it* vs what was carefully written but is untested by me. The two categories are kept separate below.

## Completed and verified (actually executed in this session)

- **Binary protocol** (`app/protocol.py`): pack/unpack of the 56-byte header, big-endian field layout, bounds/length validation, offset math. 7/7 unit tests passed.
- **Filename sanitization / path-traversal protection** (`app/utils.py`): 5/5 unit tests passed, including `../../etc/passwd` style attacks.
- **Session manifest + resumable-transfer state machine** (`app/session_manager.py`): total-chunk calculation, missing-chunk tracking, idempotent chunk marking, valid/invalid state transitions, JSON persistence and reload from a fresh process. 8/8 unit tests passed.
- **Sliding-window flow control** (`app/flow_control.py`): window growth/shrink, retry counting, retry exhaustion, min/max bounds. 7/7 unit tests passed (found and fixed one real bug: `mark_failed` doesn't auto-shrink the window — that's a deliberate separate call — the first version of this test was wrong, not the code, but it's worth knowing the API shape).
- **Offset-based storage engine** (`app/storage.py`): out-of-order chunk writes landing at correct byte offsets, final-file SHA-256 hashing, over-length write rejection, auto-creating a missing download directory. 4/4 unit tests passed (found and fixed one real bug: `open()` didn't create the download directory if it didn't exist yet — fixed and covered by a new regression test).
- **Full simulated end-to-end transfer**: a 23 MB in-memory "file" was chunked, framed, hash-verified, and offset-written; the transfer was interrupted at 40% completion; a fresh `SessionStore` instance (simulating a server restart) correctly reported the missing chunks; the remaining chunks were sent **out of order**; the final reconstructed file matched the source byte-for-byte and by SHA-256. This exercises the core promise of the whole project (chunking → binary framing → integrity → offset writes → resume → verification) without needing FastAPI or a browser.
- **Frontend structural correctness**: every `.jsx`/`.js` file passed `esbuild` syntax checking, and the full app (`App.jsx` → `transferEngine.js` → `protocol.js` → all components) was bundled successfully with `esbuild`, which would have caught broken imports, typos in exports, or JSX syntax errors. (Two real typos were caught and fixed this way in `tailwind.config.js`.)

Total: **31/31 pure-logic unit tests + 1 full e2e simulation passed**, run for real, output included in the build transcript.

## Written but NOT executed (needs fastapi/httpx/npm/browser, unavailable in this sandbox)

- `app/main.py`, `app/ws_handler.py` — the actual FastAPI app and WebSocket route. Logic was carefully hand-reviewed against `protocol.py`/`session_manager.py`/`storage.py`/`flow_control.py` (which *were* tested), but the FastAPI wiring itself has not been run.
- `tests/test_websocket_integration.py` — written using `TestClient`, covers full transfer, hash-mismatch retry, malformed-frame handling, and resume-after-disconnect. **Run this yourself first**: `pytest tests/test_websocket_integration.py -v`.
- The entire React frontend (`npm run dev` / `npm run build`) — never rendered in a real browser. Structurally verified via esbuild (see above), but you should open it in a browser and watch the console before trusting it in a demo.
- `benchmark_client.py` — written, not run.

## Blocked / needs your machine

- Two-laptop LAN demo (Milestone 17) — needs two physical laptops.
- Large-file testing beyond what a sandbox disk allows — 1GB/10GB/100GB soak tests (Milestone 16).
- Wi-Fi-disconnect fault test (Milestone 9's "unplug Wi-Fi mid-transfer") — needs a real network to unplug.
- Full benchmark suite (Milestone 15): the provided `benchmark_client.py` only implements the chunk-size experiment with a **stop-and-wait** client (send chunk, wait for ACK, repeat) — it does NOT yet pipeline sends the way the real sliding-window frontend does, so its throughput numbers will understate what the actual UI can do. The window-size and multi-WebSocket experiments are not implemented; treat the benchmark script as a starting point, not a finished deliverable.

## Known issues / things to check when you first run it

1. `benchmark_client.py`'s stop-and-wait approach means its numbers are NOT comparable to real sliding-window transfer speed — don't put its throughput numbers in a report as "the" HyperLocal speed without noting this.
2. Windows path handling in `utils.sanitize_filename`/`safe_join_download_path` was tested with POSIX-style traversal strings (`../../`) — Windows-style backslash paths are also handled (converted to `/` first), but this hasn't been tested with real Windows-originated filenames from a browser's file picker; watch for this during your first real transfer.
3. `os.statvfs` (used for the pre-transfer free-space check in `storage.py`) doesn't exist on Windows — the code catches this and skips the pre-check rather than crashing, but that means on Windows you get no "insufficient storage" warning up front, only a write failure if disk actually fills up mid-transfer.
4. The resume flow persists `session_id` in the browser's `localStorage`, keyed by file name + size. If you transfer two different files that happen to share both name and size, resume state could collide. Low risk for a typical demo, worth knowing.
5. `_pumpWindow()` in `transferEngine.js` has a no-op guard for a "stalled, nothing queued/in-flight, not complete" state — this scenario shouldn't occur given the current ACK/retry flow, but if you see a transfer freeze partway through, this is the first place to add a diagnostic log.

## Next steps (in order)

1. `pip install -r backend/requirements.txt` and `npm install` in `frontend/`.
2. Run all pytest tests, fix anything that surfaces (there's a real chance something in `ws_handler.py` needs a small correction now that it can actually execute — treat items above as "high confidence, not proven").
3. `npm run dev` + `uvicorn ... --reload`, test single-machine transfer via `localhost`.
4. `npm run build`, run `uvicorn` alone, confirm it serves the built UI at `http://127.0.0.1:8000`.
5. Two-laptop LAN test with a small file, then progressively larger files.
6. Wi-Fi-disconnect resume test.
7. Benchmarks, if time allows.

## Not implemented (explicitly out of scope for this build)

- WebRTC DataChannel path, automatic device discovery, QR pairing, encryption, folder/batch transfer, multi-device fan-out, adaptive chunk/window auto-tuning — all listed as Future Scope in the project doc and left that way.
- Pipelined (non-stop-and-wait) benchmark client for the window-size/multi-socket experiments.
