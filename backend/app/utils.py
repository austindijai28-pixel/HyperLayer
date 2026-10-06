"""Small stateless helpers: filename sanitization, local IP discovery."""
from __future__ import annotations

import re
import socket
import os

_UNSAFE_CHARS = re.compile(r"[^A-Za-z0-9._-]+")


def sanitize_filename(name: str) -> str:
    """
    Turn an arbitrary user-supplied filename into a safe basename.

    - Strips any directory component (path traversal protection).
    - Removes characters outside a conservative safe set.
    - Collapses leading dots (so ".." / hidden-file tricks can't escape).
    - Falls back to a generic name if nothing safe remains.
    """
    if not name:
        return "unnamed_file"

    # Only ever keep the basename - discards any directory traversal attempt
    # such as "../../etc/passwd" or "..\\..\\Windows\\System32\\x".
    name = name.replace("\\", "/")
    name = os.path.basename(name)

    # Strip leading dots so files can't become hidden or resolve to "..".
    name = name.lstrip(".")

    name = _UNSAFE_CHARS.sub("_", name)

    if not name:
        return "unnamed_file"

    return name[:255]  # keep well under typical filesystem limits


def safe_join_download_path(download_dir: str, filename: str) -> str:
    """
    Join a sanitized filename onto download_dir and verify the resulting
    absolute path is still inside download_dir. Raises ValueError if not.
    """
    safe_name = sanitize_filename(filename)
    download_dir_abs = os.path.abspath(download_dir)
    candidate = os.path.abspath(os.path.join(download_dir_abs, safe_name))

    if os.path.commonpath([download_dir_abs, candidate]) != download_dir_abs:
        raise ValueError("resolved path escapes the configured download directory")

    return candidate


def get_local_ip() -> str:
    """
    Best-effort discovery of this machine's LAN IP address.

    Uses the "connect to a public IP over UDP without actually sending
    traffic" trick to ask the OS which local interface/IP would be used to
    reach the outside world - this works even with no real internet
    connectivity because UDP connect() doesn't perform a handshake.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except OSError:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip
