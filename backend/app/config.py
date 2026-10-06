"""
HyperLocal configuration.

These are starting values, not guaranteed-optimal values. The benchmark
system (see app/benchmark.py) can be used to find better values for a
specific machine/network combination.
"""
import os
import socket

# --- Device Identity ---
DEVICE_NAME = os.environ.get("HYPERLOCAL_DEVICE_NAME", socket.gethostname())

# --- Chunking ---
CHUNK_SIZE = int(os.environ.get("HYPERLOCAL_CHUNK_SIZE", 5 * 1024 * 1024))  # 5 MB default
ALLOWED_CHUNK_SIZES = [1 * 1024 * 1024, 5 * 1024 * 1024, 10 * 1024 * 1024, 25 * 1024 * 1024]

# --- Flow control ---
INITIAL_WINDOW_SIZE = int(os.environ.get("HYPERLOCAL_INITIAL_WINDOW", 8))
MAX_WINDOW_SIZE = int(os.environ.get("HYPERLOCAL_MAX_WINDOW", 32))
MIN_WINDOW_SIZE = 1

# --- Retries ---
MAX_RETRIES = int(os.environ.get("HYPERLOCAL_MAX_RETRIES", 5))

# --- Binary protocol header layout (56 bytes total) ---
# FILE_ID(16) + CHUNK_INDEX(4) + PAYLOAD_LENGTH(4) + SHA256(32) = 56
HEADER_FILE_ID_LEN = 16
HEADER_CHUNK_INDEX_LEN = 4
HEADER_PAYLOAD_LEN_LEN = 4
HEADER_SHA256_LEN = 32
HEADER_SIZE = (
    HEADER_FILE_ID_LEN
    + HEADER_CHUNK_INDEX_LEN
    + HEADER_PAYLOAD_LEN_LEN
    + HEADER_SHA256_LEN
)  # == 56

# Hard safety bound so a malformed/malicious payload-length field can never
# make the server try to read gigabytes into memory for one frame.
MAX_PAYLOAD_LENGTH = 32 * 1024 * 1024  # 32 MB, comfortably above ALLOWED_CHUNK_SIZES max

# --- Storage ---
DOWNLOAD_DIRECTORY = os.environ.get(
    "HYPERLOCAL_DOWNLOAD_DIR",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "storage", "downloads"),
)
SESSION_DIRECTORY = os.environ.get(
    "HYPERLOCAL_SESSION_DIR",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "storage", "sessions"),
)

# --- Networking ---
HOST = os.environ.get("HYPERLOCAL_HOST", "0.0.0.0")
PORT = int(os.environ.get("HYPERLOCAL_PORT", 8000))

# CORS / allowed origins - configurable rather than "*" for anything beyond local dev.
_raw_origins = os.environ.get("HYPERLOCAL_ALLOWED_ORIGINS", "*")
ALLOWED_ORIGINS = ["*"] if _raw_origins.strip() == "*" else [o.strip() for o in _raw_origins.split(",")]

os.makedirs(DOWNLOAD_DIRECTORY, exist_ok=True)
os.makedirs(SESSION_DIRECTORY, exist_ok=True)
