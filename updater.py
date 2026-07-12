"""Safe, user-initiated updater for the packaged Windows application."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Callable

import requests

from app_version import APP_VERSION, DEFAULT_UPDATE_MANIFEST_URL
from runtime_paths import app_dir


class UpdateError(RuntimeError):
    pass


def _version_tuple(value: str) -> tuple[int, ...]:
    try:
        parts = value.strip().lstrip("vV").split(".")
        if not parts or any(not part.isdigit() for part in parts):
            raise ValueError
        return tuple(int(part) for part in parts)
    except (AttributeError, ValueError):
        raise UpdateError(f"Version không hợp lệ: {value!r}") from None


def manifest_url() -> str:
    return os.getenv("NETFLIX_MANAGER_UPDATE_URL", DEFAULT_UPDATE_MANIFEST_URL).strip()


def check_for_update(timeout: int = 15) -> dict:
    url = manifest_url()
    if "OWNER/REPOSITORY" in url:
        raise UpdateError("Chưa cấu hình đường dẫn update.json trong app_version.py.")
    try:
        response = requests.get(url, timeout=timeout)
        response.raise_for_status()
        info = response.json()
    except requests.RequestException as exc:
        raise UpdateError(f"Không thể kết nối máy chủ cập nhật: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise UpdateError("File update.json trên máy chủ không hợp lệ.") from exc

    required = ("version", "download_url", "file_name")
    if not isinstance(info, dict) or any(not info.get(key) for key in required):
        raise UpdateError("update.json thiếu version, download_url hoặc file_name.")
    info["update_available"] = _version_tuple(info["version"]) > _version_tuple(APP_VERSION)
    return info


def download_update(info: dict, progress: Callable[[int], None] | None = None) -> Path:
    suffix = Path(info["file_name"]).suffix.lower()
    if suffix not in (".exe", ".zip"):
        raise UpdateError("Bản cập nhật phải là file .exe hoặc .zip.")
    staging = Path(tempfile.mkdtemp(prefix="NetflixManager-update-"))
    package = staging / ("package" + suffix)
    try:
        with requests.get(info["download_url"], stream=True, timeout=(15, 120)) as response:
            response.raise_for_status()
            total = int(response.headers.get("content-length", 0))
            received = 0
            with package.open("wb") as output:
                for chunk in response.iter_content(1024 * 256):
                    if chunk:
                        output.write(chunk)
                        received += len(chunk)
                        if progress and total:
                            progress(min(100, int(received * 100 / total)))
    except (requests.RequestException, OSError) as exc:
        shutil.rmtree(staging, ignore_errors=True)
        raise UpdateError(f"Tải bản cập nhật thất bại: {exc}") from exc

    expected_hash = str(info.get("sha256", "")).strip().lower()
    if expected_hash:
        actual_hash = hashlib.sha256(package.read_bytes()).hexdigest()
        if actual_hash != expected_hash:
            shutil.rmtree(staging, ignore_errors=True)
            raise UpdateError("File tải về không đúng mã SHA-256; bản hiện tại được giữ nguyên.")

    if suffix == ".exe":
        prepared = staging / info["file_name"]
        package.replace(prepared)
        return prepared

    try:
        with zipfile.ZipFile(package) as archive:
            candidates = [item for item in archive.infolist()
                          if not item.is_dir() and Path(item.filename).name == info["file_name"]]
            if len(candidates) != 1 or Path(info["file_name"]).suffix.lower() != ".exe":
                raise UpdateError("Không tìm thấy đúng file .exe được khai báo trong gói ZIP.")
            prepared = staging / Path(info["file_name"]).name
            with archive.open(candidates[0]) as source, prepared.open("wb") as target:
                shutil.copyfileobj(source, target)
            return prepared
    except (zipfile.BadZipFile, OSError) as exc:
        shutil.rmtree(staging, ignore_errors=True)
        raise UpdateError(f"Không thể giải nén bản cập nhật: {exc}") from exc


def install_and_restart(prepared_exe: Path) -> None:
    if not getattr(sys, "frozen", False):
        raise UpdateError("Chỉ có thể tự cài đặt trên bản .exe đã đóng gói.")
    current_exe = Path(sys.executable).resolve()
    helper = prepared_exe.parent / "apply_update.cmd"
    helper.write_text(
        "@echo off\n"
        "setlocal\n"
        f':wait\ntasklist /FI "PID eq {os.getpid()}" | find "{os.getpid()}" >nul\n'
        "if not errorlevel 1 (timeout /t 1 /nobreak >nul & goto wait)\n"
        f'move /Y "{current_exe}" "{current_exe}.old" >nul\n'
        f'if errorlevel 1 goto failed\nmove /Y "{prepared_exe}" "{current_exe}" >nul\n'
        f'if errorlevel 1 (move /Y "{current_exe}.old" "{current_exe}" >nul & goto failed)\n'
        f'del /Q "{current_exe}.old" >nul 2>&1\nstart "" "{current_exe}"\n'
        'rmdir /S /Q "%~dp0" >nul 2>&1\nexit /b 0\n'
        f':failed\nstart "" "{current_exe}"\n'
        'msg * "Cap nhat that bai. Phien ban cu da duoc giu nguyen." >nul 2>&1\nexit /b 1\n',
        encoding="utf-8",
    )
    subprocess.Popen(
        ["cmd.exe", "/c", str(helper)],
        creationflags=subprocess.CREATE_NO_WINDOW,
        close_fds=True,
        cwd=str(app_dir()),
    )
