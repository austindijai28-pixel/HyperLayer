"""
Standalone benchmark client (MILESTONE 15 - optional, run after the core
app works end-to-end on your machine).

Generates a deterministic test file, sends it over a real WebSocket
connection to a running HyperLocal server, and records throughput. Varies
ONE variable per experiment as required by the design doc.

Usage (server must already be running, e.g. `uvicorn app.main:app`):

    python benchmark_client.py --host 127.0.0.1 --port 8000 \
        --experiment chunk_size --file-size-mb 200

    python benchmark_client.py --host 127.0.0.1 --port 8000 \
        --experiment window_size --file-size-mb 200

Results are appended as CSV rows to benchmark_results.csv.

Requires: pip install websockets  (already in requirements.txt)
This script was NOT executed in the development sandbox (no network / no
FastAPI server could run there) - run it yourself once the server is up.
"""
import argparse
import asyncio
import csv
import hashlib
import os
import struct
import time
import uuid

import websockets

CHUNK_SIZE_EXPERIMENTS = [1, 5, 10, 25]  # MB
WINDOW_SIZE_EXPERIMENTS = [1, 2, 4, 8, 16, 32]


def make_test_file(path: str, size_mb: int) -> None:
    if os.path.exists(path) and os.path.getsize(path) == size_mb * 1024 * 1024:
        return
    with open(path, "wb") as f:
        remaining = size_mb * 1024 * 1024
        block = os.urandom(4 * 1024 * 1024)
        while remaining > 0:
            n = min(len(block), remaining)
            f.write(block[:n])
            remaining -= n


async def run_transfer(uri: str, file_path: str, chunk_size: int) -> dict:
    file_size = os.path.getsize(file_path)
    start = time.time()

    async with websockets.connect(uri, max_size=None) as ws:
        await ws.send(f'{{"type":"INIT","file_name":"bench_{uuid.uuid4().hex}.bin",'
                       f'"file_size":{file_size},"chunk_size":{chunk_size}}}')
        import json
        ready = json.loads(await ws.recv())
        file_id = uuid.UUID(ready["file_id"])
        total_chunks = ready["total_chunks"]

        with open(file_path, "rb") as f:
            for idx in range(total_chunks):
                f.seek(idx * chunk_size)
                payload = f.read(chunk_size)
                digest = hashlib.sha256(payload).digest()
                header = struct.pack(">16sII32s", file_id.bytes, idx, len(payload), digest)
                await ws.send(header + payload)
                await ws.recv()  # wait for ACK - simple stop-and-wait baseline;
                # a full sliding-window benchmark client can pipeline sends here.

        complete = json.loads(await ws.recv())

    duration = time.time() - start
    throughput_mbps = (file_size / (1024 * 1024)) / duration if duration > 0 else 0
    return {
        "file_size_mb": file_size / (1024 * 1024),
        "chunk_size_mb": chunk_size / (1024 * 1024),
        "duration_s": duration,
        "throughput_mbps": throughput_mbps,
        "integrity_verified": complete.get("integrity_verified"),
    }


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--experiment", choices=["chunk_size"], default="chunk_size",
                         help="Only chunk_size is implemented in this stop-and-wait baseline client; "
                              "window_size and multi-socket experiments need a pipelined client extension.")
    parser.add_argument("--file-size-mb", type=int, default=100)
    args = parser.parse_args()

    test_file = f"/tmp/hyperlocal_bench_{args.file_size_mb}mb.bin"
    make_test_file(test_file, args.file_size_mb)

    uri = f"ws://{args.host}:{args.port}/ws"
    results = []
    for mb in CHUNK_SIZE_EXPERIMENTS:
        chunk_size = mb * 1024 * 1024
        print(f"Running chunk_size={mb}MB ...")
        result = await run_transfer(uri, test_file, chunk_size)
        result["chunk_size_mb_label"] = mb
        results.append(result)
        print(result)

    out_path = "benchmark_results.csv"
    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(results[0].keys()))
        writer.writeheader()
        writer.writerows(results)
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
