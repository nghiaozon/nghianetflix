"""Secure updater for the packaged Windows application."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

import requests

from app_version import APP_VERSION, DEFAULT_UPDATE_MANIFEST_URL
from runtime_paths import app_dir


SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


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


def _safe_filename(value: object, field: str) -> str:
    name = str(value or "").strip()
    if not name or Path(name).name != name or name in (".", ".."):
        raise UpdateError(f"Trường {field} phải là tên file, không được chứa đường dẫn.")
    return name


def validate_manifest(info: object, *, require_hash: bool = False) -> dict:
    if not isinstance(info, dict):
        raise UpdateError("update.json phải là một đối tượng JSON.")
    required = ("version", "download_url")
    if any(not info.get(key) for key in required):
        raise UpdateError("update.json thiếu version hoặc download_url.")

    parsed_url = urlparse(str(info["download_url"]))
    if parsed_url.scheme.lower() != "https" or not parsed_url.netloc:
        raise UpdateError("download_url phải là URL HTTPS công khai.")

    package_name = _safe_filename(
        info.get("package_name") or info.get("file_name"), "package_name"
    )
    package_type = str(info.get("package_type") or Path(package_name).suffix.lstrip(".")).lower()
    if package_type not in ("exe", "zip"):
        raise UpdateError("package_type chỉ hỗ trợ exe hoặc zip.")
    if Path(package_name).suffix.lower() != f".{package_type}":
        raise UpdateError("package_name không khớp với package_type.")

    executable_name = _safe_filename(
        info.get("executable_name") or (package_name if package_type == "exe" else ""),
        "executable_name",
    )
    if Path(executable_name).suffix.lower() != ".exe":
        raise UpdateError("executable_name phải là file .exe.")

    sha256 = str(info.get("sha256", "")).strip().lower()
    if sha256 and not SHA256_RE.fullmatch(sha256):
        raise UpdateError("sha256 phải gồm đúng 64 ký tự hexadecimal.")
    if require_hash and not sha256:
        raise UpdateError("Bản cập nhật thiếu SHA-256; ứng dụng từ chối tải để bảo vệ an toàn.")

    normalized = dict(info)
    normalized.update(
        package_name=package_name,
        package_type=package_type,
        executable_name=executable_name,
        sha256=sha256,
    )
    _version_tuple(str(normalized["version"]))
    return normalized


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
    except (json.JSONDecodeError, requests.exceptions.JSONDecodeError) as exc:
        raise UpdateError("File update.json trên máy chủ không hợp lệ.") from exc

    normalized = validate_manifest(info)
    normalized["update_available"] = (
        _version_tuple(normalized["version"]) > _version_tuple(APP_VERSION)
    )
    if normalized["update_available"] and not normalized["sha256"]:
        raise UpdateError("Bản cập nhật mới thiếu SHA-256 và không thể được cài đặt an toàn.")
    return normalized


def ensure_installation_writable(directory: Path | None = None) -> None:
    target = (directory or app_dir()).resolve()
    if not target.is_dir():
        raise UpdateError(f"Thư mục cài đặt không tồn tại: {target}")
    probe = target / f".update-write-test-{os.getpid()}"
    try:
        probe.write_bytes(b"")
        probe.unlink()
    except OSError as exc:
        raise UpdateError(
            "Ứng dụng không có quyền ghi vào thư mục cài đặt. "
            "Hãy di chuyển ứng dụng sang thư mục thuộc người dùng hoặc chạy với quyền phù hợp."
        ) from exc


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_authenticode(executable: Path, required_publisher: str = "") -> None:
    if os.name != "nt":
        raise UpdateError("Chỉ có thể xác minh chữ ký Authenticode trên Windows.")
    script = (
        "$s=Get-AuthenticodeSignature -LiteralPath $args[0];"
        "[Console]::OutputEncoding=[Text.Encoding]::UTF8;"
        "Write-Output ($s.Status.ToString()+'|'+$s.SignerCertificate.Subject)"
    )
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script, str(executable)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        timeout=30,
        check=False,
    )
    status, _, publisher = result.stdout.strip().partition("|")
    if result.returncode or status != "Valid":
        raise UpdateError("Chữ ký số Authenticode của bản cập nhật không hợp lệ.")
    if required_publisher and required_publisher.casefold() not in publisher.casefold():
        raise UpdateError("Nhà phát hành trong chữ ký số không đúng cấu hình.")


def download_update(info: dict, progress: Callable[[int], None] | None = None) -> Path:
    info = validate_manifest(info, require_hash=True)
    ensure_installation_writable()
    staging = Path(tempfile.mkdtemp(prefix="NetflixManager-update-"))
    package = staging / info["package_name"]
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

    if _sha256(package) != info["sha256"]:
        shutil.rmtree(staging, ignore_errors=True)
        raise UpdateError("File tải về không đúng mã SHA-256; bản hiện tại được giữ nguyên.")

    if info["package_type"] == "exe":
        prepared = package
    else:
        try:
            with zipfile.ZipFile(package) as archive:
                candidates = [
                    item for item in archive.infolist()
                    if not item.is_dir() and Path(item.filename).name == info["executable_name"]
                ]
                if len(candidates) != 1:
                    raise UpdateError("Gói ZIP không chứa đúng một executable_name đã khai báo.")
                prepared = staging / info["executable_name"]
                with archive.open(candidates[0]) as source, prepared.open("wb") as target:
                    shutil.copyfileobj(source, target)
        except (zipfile.BadZipFile, OSError) as exc:
            shutil.rmtree(staging, ignore_errors=True)
            raise UpdateError(f"Không thể giải nén bản cập nhật: {exc}") from exc

    if info.get("require_authenticode", False):
        verify_authenticode(prepared, str(info.get("publisher", "")).strip())
    return prepared


def install_and_restart(prepared_exe: Path) -> None:
    if not getattr(sys, "frozen", False):
        raise UpdateError("Chỉ có thể tự cài đặt trên bản .exe đã đóng gói.")
    ensure_installation_writable()
    current_exe = Path(sys.executable).resolve()
    helper = prepared_exe.parent / "apply_update.cmd"
    helper.write_text(
        "@echo off\nsetlocal\n"
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
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        close_fds=True,
        cwd=str(app_dir()),
    )


def frozen_runtime_self_test() -> bool:
    """Small smoke test invoked against the PyInstaller executable in CI."""
    return bool(getattr(sys, "frozen", False) and Path(sys.executable).is_file() and manifest_url())
