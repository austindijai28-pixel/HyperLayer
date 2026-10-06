# HyperLocal

High-speed, resumable, browser-based file transfer between two computers over local Wi-Fi. No cloud, no internet required once both devices are on the same network.

Client-server architecture: a FastAPI backend (host/receiver) serves a React frontend and a WebSocket transfer endpoint; a browser (sender) streams a file to it in chunks over a single persistent binary WebSocket connection.

## Architecture

```
React UI  --File.slice()-->  Web Worker (SHA-256)  --binary frame-->  WebSocket
                                                                          |
                                                                          v
                                                       FastAPI: frame parser,
                                                       hash validator, sliding
                                                       window, session manager
                                                                          |
                                                                          v
                                                    Offset-based storage engine
                                                    (os.pwrite via threadpool)
```

Binary wire protocol (56-byte header, big-endian), sent as WebSocket **binary** frames (no Base64):

```
FILE_ID (16B) | CHUNK_INDEX (4B) | PAYLOAD_LENGTH (4B) | SHA-256 (32B) | PAYLOAD
```

See `backend/app/protocol.py` for the authoritative implementation and `frontend/src/lib/protocol.js` for the matching client-side packer.

## Technology stack

- **Frontend**: React 18, Vite, Tailwind CSS, lucide-react
- **Backend**: Python 3.10+, FastAPI, Uvicorn, Pydantic-based config

## Folder structure

```
HyperLocal/
  backend/
    app/
      main.py              FastAPI app, static frontend serving, /api/info
      config.py            All tunables (chunk size, window size, retries...)
      protocol.py           56-byte binary header pack/parse/validate
      ws_protocol_messages.py  JSON control-message schema
      ws_handler.py         WebSocket connection state machine
      session_manager.py    Manifest + resume + transfer state machine
      storage.py             Offset-based writes (os.pwrite in a threadpool)
      flow_control.py        Sliding-window bookkeeping
      utils.py               Filename sanitization, local-IP discovery
    tests/                  pytest unit + integration tests
    benchmark_client.py      Optional benchmark harness (Milestone 15)
    requirements.txt
    storage/downloads/       Received files land here
    storage/sessions/        Session manifests (JSON) for resume
  frontend/
    src/
      App.jsx                Top-level view router (Home/Transfer/Recovery/Complete)
      components/             HomeView, TransferView, RecoveryView, CompleteView, StatusBadge
      lib/
        protocol.js           Client-side binary frame packer
        hasher.worker.js       Web Worker: SHA-256 via Web Crypto API
        transferEngine.js      WebSocket lifecycle, chunking, sliding window, telemetry, resume
    package.json, vite.config.js, tailwind.config.js
  README.md, PROJECT_STATUS.md
```

## ⚠️ Important: this codebase was written in a network-isolated sandbox

Every file in this repository was written and, where possible, verified in an environment with **no internet access** - `pip install` and `npm install` both failed there. That means:

- The pure Python logic (binary protocol, offset math, filename sanitization, session/resume state machine, sliding window) was **actually executed** with the standard library and passed 31/31 unit tests, plus a full simulated end-to-end transfer (chunking → hash-verify → offset write → simulated disconnect → resume → final SHA-256 match). See `PROJECT_STATUS.md` for the exact commands/output.
- The FastAPI/WebSocket integration tests (`tests/test_websocket_integration.py`) were **written but not executed**, because `fastapi`/`httpx` couldn't be installed in that sandbox.
- The React frontend was **not run through Vite/npm**, because `npm install` couldn't reach the registry there. Every `.jsx`/`.js` file *was* syntax-checked and the whole app *was* bundled successfully with `esbuild` (catching real import/path errors along the way), but it has not been rendered in an actual browser.

**You need to run the install/build/test commands below yourself, on a machine with internet access, before the two-laptop demo.** Budget time for this - don't wait until the day of the demo.

## Installation

### Backend

```bash
cd backend
python -m venv venv

# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

pip install -r requirements.txt
```

### Frontend

```bash
cd frontend
npm install
```

## Running

### Backend (development)

```bash
cd backend
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Frontend (development, separate port with hot reload)

```bash
cd frontend
npm run dev
```
Open `http://localhost:5173`. In dev mode, Vite proxies `/ws` and `/api` to `127.0.0.1:8000` (see `vite.config.js`) - this is single-machine dev convenience, not the LAN demo path.

### Final single-server LAN deployment (what you use for the actual demo)

```bash
cd frontend
npm run build          # produces frontend/dist

cd ../backend
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

FastAPI detects `frontend/dist` and serves the built UI itself, so Laptop B only ever needs one URL and one port.

## Two-laptop LAN setup

**Laptop A (host / receiver):**
1. Turn on its Wi-Fi hotspot, or connect both laptops to the same router/AP.
2. `cd backend && uvicorn app.main:app --host 0.0.0.0 --port 8000`
3. Find its LAN IP if it's not already printed on startup:
   - Windows (Command Prompt): `ipconfig` → look for "IPv4 Address" under the active adapter.
   - macOS/Linux: `ifconfig` or `ip addr show`
   - Or just open `http://127.0.0.1:8000/api/info` in a browser on Laptop A - it returns `local_ip`.

**Laptop B (sender):**
1. Connect to Laptop A's Wi-Fi / the shared network.
2. Open a browser to `http://<Laptop A's IP>:8000`.
3. Select or drag a file, pick a chunk size, click Start Transfer.

### Windows firewall

If Laptop B can't reach Laptop A, Windows Defender Firewall is almost always why:

```powershell
# Run as Administrator on Laptop A
New-NetFirewallRule -DisplayName "HyperLocal" -Direction Inbound -Protocol TCP -LocalPort 8000 -Action Allow
```
Or: Control Panel → Windows Defender Firewall → Allow an app through firewall → add `python.exe` for both Private and Public networks (or just Private, if the hotspot registers as Private).

If Laptop A is *hosting* the Wi-Fi hotspot, make sure "Mobile hotspot" or your router isn't isolating client devices from each other (AP/client isolation) - some routers block device-to-device traffic by default.

## Testing

### Unit tests (fast, no server needed)

```bash
cd backend
pytest tests/test_protocol.py tests/test_utils.py tests/test_session_manager.py tests/test_flow_control.py tests/test_storage.py -v
```

### Integration tests (spins up the FastAPI app in-process)

```bash
cd backend
pytest tests/test_websocket_integration.py -v
```

### Everything

```bash
cd backend
pytest -v
```

## Benchmarking (optional, Milestone 15)

A stop-and-wait baseline benchmark client is provided for the chunk-size experiment:

```bash
cd backend
# with the server already running in another terminal:
python benchmark_client.py --host 127.0.0.1 --port 8000 --experiment chunk_size --file-size-mb 100
```

Writes `benchmark_results.csv`. The window-size and multi-WebSocket experiments described in the project docs need a pipelined (not stop-and-wait) benchmark client - see "Limitations" below.

## Large-file testing

Progress incrementally rather than starting with a 100 GB file:

```bash
# macOS/Linux - create a deterministic test file
head -c 1073741824 /dev/urandom > test_1gb.bin   # 1 GB
# Windows PowerShell
fsutil file createnew test_1gb.bin 1073741824
```
Transfer it through the UI, then check the received file's SHA-256 against the source:
```bash
# macOS/Linux
sha256sum test_1gb.bin
# Windows PowerShell
Get-FileHash test_1gb.bin -Algorithm SHA256
```
and compare to the "Integrity: VERIFIED" hash shown on the Complete screen.

## Limitations / what's not done

See `PROJECT_STATUS.md` for the authoritative, up-to-date list. In short: the core protocol, backend, and UI are implemented for all 18 milestones' *code*, but end-to-end execution (real two-laptop run, multi-GB/100GB soak test, full window-size/multi-socket benchmarks, browser rendering of the UI) has not happened yet because this sandbox had no way to run FastAPI, npm, or a browser. You are the first one who can actually run this.

## Future scope

WebRTC DataChannel for true peer-to-peer (no server hop), automatic device discovery, QR pairing, end-to-end encryption, folder/batch transfer, mobile browser support, multi-device fan-out, adaptive chunk/window sizing based on measured RTT and disk speed.
