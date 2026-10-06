"""Unit tests for app/utils.py (filename sanitization / path safety)."""
import os
import pytest

from app.utils import sanitize_filename, safe_join_download_path


def test_sanitize_strips_path_traversal():
    assert sanitize_filename("../../etc/passwd") == "passwd"
    assert sanitize_filename("..\\..\\Windows\\System32\\evil.exe") == "evil.exe"


def test_sanitize_normal_name_preserved():
    assert sanitize_filename("my_video-2024.mp4") == "my_video-2024.mp4"


def test_sanitize_removes_unsafe_chars():
    result = sanitize_filename('weird<>:"|?*name.txt')
    assert "<" not in result and ">" not in result and "|" not in result


def test_sanitize_empty_falls_back():
    assert sanitize_filename("") == "unnamed_file"
    assert sanitize_filename("...") == "unnamed_file"


def test_safe_join_stays_inside_download_dir(tmp_path=None):
    download_dir = "/tmp/hyperlocal_test_downloads"
    os.makedirs(download_dir, exist_ok=True)
    path = safe_join_download_path(download_dir, "../../../etc/passwd")
    assert path.startswith(os.path.abspath(download_dir))
    assert "etc" not in os.path.basename(path)
