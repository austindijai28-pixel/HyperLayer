"""
HyperLocal FastAPI application entrypoint.

Run directly for local dev:
    python -m app.main

Or with uvicorn (recommended, supports --reload):
    uvicorn app.main:app --host 0.0.0.0 --port 8000
"""
from __future__ import annotations

import logging
import os

from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import config
from .utils import get_local_ip
from .ws_handler import websocket_endpoint

logging.basicConfig(
    level=os.environ.get("HYPERLOCAL_LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("hyperlocal")

app = FastAPI(title="HyperLocal", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.get("/api/info")
async def info():
    """Lets the frontend display the host's device name, LAN IP, and port."""
    return {
        "device_name": config.DEVICE_NAME,
        "local_ip": get_local_ip(),
        "port": config.PORT,
        "chunk_size": config.CHUNK_SIZE,
        "allowed_chunk_sizes": config.ALLOWED_CHUNK_SIZES,
        "initial_window_size": config.INITIAL_WINDOW_SIZE,
        "max_window_size": config.MAX_WINDOW_SIZE,
    }


@app.post("/api/device_name")
async def set_device_name(data: dict):
    new_name = data.get("device_name", "").strip()
    if new_name:
        config.DEVICE_NAME = new_name
    return {"device_name": config.DEVICE_NAME}


@app.get("/api/downloads")
async def list_downloads():
    """List files in the downloads directory for the Receiver Mode UI."""
    import datetime
    downloads = []
    try:
        for entry in os.scandir(config.DOWNLOAD_DIRECTORY):
            if entry.is_file():
                stat = entry.stat()
                downloads.append({
                    "name": entry.name,
                    "size": stat.st_size,
                    "modified_at": datetime.datetime.fromtimestamp(
                        stat.st_mtime, tz=datetime.timezone.utc
                    ).isoformat(),
                })
        downloads.sort(key=lambda f: f["modified_at"], reverse=True)
    except OSError:
        pass
    return {"files": downloads}


@app.get("/api/downloads/{filename}")
async def download_file(filename: str):
    """Serve a single received file for download."""
    from .utils import safe_join_download_path
    try:
        path = safe_join_download_path(config.DOWNLOAD_DIRECTORY, filename)
    except Exception:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="invalid filename")
    if not os.path.isfile(path):
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="file not found")
    return FileResponse(
        path,
        filename=filename,
        media_type="application/octet-stream",
    )


@app.websocket("/ws")
async def ws_route(websocket: WebSocket):
    await websocket_endpoint(websocket)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request, exc):
    # Defense in depth: any HTTP-side exception that slips through gets a
    # generic JSON error instead of a raw traceback.
    logger.exception("Unhandled HTTP exception")
    return JSONResponse(status_code=500, content={"error": "internal_server_error"})


# Serve the built React frontend (frontend/dist) as static files so the
# final demo only needs one server/port, per MILESTONE 2.
_frontend_dist = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "frontend", "dist",
)
if os.path.isdir(_frontend_dist):
    app.mount("/", StaticFiles(directory=_frontend_dist, html=True), name="frontend")
    logger.info("Serving built frontend from %s", _frontend_dist)
else:
    logger.warning(
        "frontend/dist not found - run `npm run build` in frontend/ to serve the UI from FastAPI. "
        "Until then, run the Vite dev server separately (see README)."
    )


if __name__ == "__main__":
    import uvicorn

    local_ip = get_local_ip()
    print(f"HyperLocal starting...")
    print(f"  Local:   http://127.0.0.1:{config.PORT}")
    print(f"  Network: http://{local_ip}:{config.PORT}   <-- use this on Laptop B")
    uvicorn.run("app.main:app", host=config.HOST, port=config.PORT, reload=False)
