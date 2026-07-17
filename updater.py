"""Transactional, location-independent updater for the Windows application."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import traceback
import uuid
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Callable
from urllib.parse import urlparse

import requests

from app_version import (
    APP_VERSION,
    GITHUB_RELEASE_API_URL,
    UPDATE_ASSET_NAMES,
)
from runtime_paths import app_dir


SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
VERSION_RE = re.compile(r"(?<!\d)[vV]?(\d+(?:\.\d+){1,3})(?!\d)")
PROTECTED_ROOTS = {
    "data",
    "config",
    "excel",
    "database",
    "credentials",
    "backup",
    "backups",
    "log",
    "logs",
}
PROTECTED_SUFFIXES = {
    ".db",
    ".db3",
    ".sqlite",
    ".sqlite3",
    ".xls",
    ".xlsx",
    ".xlsm",
    ".xlsb",
    ".csv",
    ".json",
}
PROTECTED_NAMES = {".env", "credentials.json", "update.log"}


class UpdateError(RuntimeError):
    pass


@dataclass(frozen=True)
class PreparedUpdate:
    """A verified package extracted outside the installation directory."""

    staging_dir: Path
    payload_dir: Path
    executable: Path
    install_mode: str = "portable"


def current_executable() -> Path:
    """Resolve the running executable every time; never read it from config."""
    return Path(sys.executable).resolve()


def update_log_path() -> Path:
    return app_dir().resolve() / "update.log"


def _log(event: str, detail: object = "") -> None:
    line = f"{datetime.now().isoformat(timespec='seconds')} | {event}"
    if detail != "":
        line += f": {detail}"
    try:
        with update_log_path().open("a", encoding="utf-8") as output:
            output.write(line + "\n")
    except OSError:
        try:
            fallback = Path(tempfile.gettempdir()) / "NetflixManager-update.log"
            with fallback.open("a", encoding="utf-8") as output:
                output.write(line + "\n")
        except OSError:
            pass


def log_exception(event: str, exc: BaseException) -> None:
    _log(event, f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}")


def _independent_subprocess_environment() -> dict[str, str]:
    """Return an environment safe for processes that outlive a one-file app.

    PyInstaller 6.9+ assumes another invocation of the same executable is a
    worker and may reuse the parent's _MEI directory.  An updater/restart must
    be an independent instance because the old _MEI directory is deleted when
    the old app exits.
    """
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.upper().startswith("_PYI_")
    }
    environment["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    return environment


def _log_runtime_paths() -> None:
    _log("Current EXE", current_executable())
    _log("Current Folder", app_dir().resolve())


def normalize_version(value: object) -> str:
    """Return a numeric release version from tags such as v1.0.7."""
    match = VERSION_RE.search(str(value or "").strip())
    if not match:
        raise UpdateError(f"Version không hợp lệ: {value!r}")
    return ".".join(str(int(part)) for part in match.group(1).split("."))


def _version_tuple(value: object) -> tuple[int, ...]:
    return tuple(int(part) for part in normalize_version(value).split("."))


def release_api_url() -> str:
    return os.getenv(
        "NETFLIX_MANAGER_RELEASE_API_URL", GITHUB_RELEASE_API_URL
    ).strip()


def _github_headers() -> dict[str, str]:
    return {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": f"NetflixManager/{APP_VERSION}",
    }


def _asset_hash(asset: dict) -> str:
    digest = str(asset.get("digest") or "").strip().lower()
    if digest.startswith("sha256:"):
        digest = digest.partition(":")[2]
    return digest if SHA256_RE.fullmatch(digest) else ""


def _select_release_asset(release: dict, version: str) -> dict:
    assets = release.get("assets")
    if not isinstance(assets, list):
        raise UpdateError("GitHub Release không có danh sách asset hợp lệ.")

    by_name = {
        str(asset.get("name") or "").casefold(): asset
        for asset in assets
        if isinstance(asset, dict)
    }
    selected = None
    for template in UPDATE_ASSET_NAMES:
        candidate = template.format(version=version)
        if candidate.casefold() in by_name:
            selected = by_name[candidate.casefold()]
            break
    if selected is None:
        expected = ", ".join(
            name.format(version=version) for name in UPDATE_ASSET_NAMES
        )
        raise UpdateError(
            "Không tìm thấy asset cập nhật phù hợp trong GitHub Release. "
            f"Tên được hỗ trợ: {expected}."
        )

    name = _safe_filename(selected.get("name"), "asset.name")
    url = str(selected.get("browser_download_url") or "").strip()
    parsed_url = urlparse(url)
    if parsed_url.scheme.lower() != "https" or not parsed_url.netloc:
        raise UpdateError("Asset GitHub Release không có URL tải HTTPS hợp lệ.")
    try:
        size = int(selected.get("size") or 0)
    except (TypeError, ValueError):
        size = 0
    if size <= 0:
        raise UpdateError(f"Asset {name} trên GitHub Release có dung lượng bằng 0.")

    lower_name = name.casefold()
    is_installer = lower_name.endswith(("-setup.exe", "-installer.exe"))
    package_type = "zip" if lower_name.endswith(".zip") else "exe"
    return {
        "version": version,
        "download_url": url,
        "package_type": package_type,
        "package_name": name,
        "file_name": name,
        "executable_name": "NetflixManager.exe" if package_type == "zip" else name,
        "sha256": _asset_hash(selected),
        "asset_size": size,
        "install_mode": "installer" if is_installer else "portable",
        "require_authenticode": False,
    }


def _load_sidecar_hash(info: dict, release: dict, timeout: int) -> str:
    sidecar_name = f"{info['package_name']}.sha256".casefold()
    sidecar = next(
        (
            asset
            for asset in release.get("assets", [])
            if isinstance(asset, dict)
            and str(asset.get("name") or "").casefold() == sidecar_name
        ),
        None,
    )
    if sidecar is None:
        return ""
    url = str(sidecar.get("browser_download_url") or "").strip()
    try:
        response = requests.get(url, headers=_github_headers(), timeout=timeout)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise UpdateError(f"Không thể tải file SHA-256 của bản cập nhật: {exc}") from exc
    match = re.search(r"\b([0-9a-fA-F]{64})\b", response.text)
    return match.group(1).lower() if match else ""


def _safe_filename(value: object, field: str) -> str:
    name = str(value or "").strip()
    if not name or Path(name).name != name or name in (".", ".."):
        raise UpdateError(
            f"Trường {field} phải là tên file, không được chứa đường dẫn."
        )
    return name


def validate_manifest(info: object, *, require_hash: bool = False) -> dict:
    if not isinstance(info, dict):
        raise UpdateError("update.json phải là một đối tượng JSON.")
    if any(not info.get(key) for key in ("version", "download_url")):
        raise UpdateError("update.json thiếu version hoặc download_url.")

    parsed_url = urlparse(str(info["download_url"]))
    if parsed_url.scheme.lower() != "https" or not parsed_url.netloc:
        raise UpdateError("download_url phải là URL HTTPS công khai.")

    package_name = _safe_filename(
        info.get("package_name") or info.get("file_name"), "package_name"
    )
    package_type = str(
        info.get("package_type") or Path(package_name).suffix.lstrip(".")
    ).lower()
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
        raise UpdateError(
            "Bản cập nhật thiếu SHA-256; ứng dụng từ chối tải để bảo vệ an toàn."
        )

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
    _log_runtime_paths()
    url = release_api_url()
    _log("release_api_url", url)
    _log("current_version", APP_VERSION)
    try:
        response = requests.get(url, headers=_github_headers(), timeout=timeout)
        response.raise_for_status()
        release = response.json()
    except requests.RequestException as exc:
        _log("Check FAILED", exc)
        status = getattr(getattr(exc, "response", None), "status_code", None)
        if status == 404:
            raise UpdateError(
                "Không tìm thấy GitHub Release công khai cho ứng dụng."
            ) from exc
        raise UpdateError(
            f"Không thể kết nối GitHub để kiểm tra cập nhật: {exc}"
        ) from exc
    except (json.JSONDecodeError, requests.exceptions.JSONDecodeError) as exc:
        _log("Check FAILED", "invalid GitHub JSON")
        raise UpdateError("Phản hồi GitHub Release không phải JSON hợp lệ.") from exc

    if not isinstance(release, dict):
        raise UpdateError("Phản hồi GitHub Release không hợp lệ.")
    latest_version = ""
    for release_version_source in (release.get("tag_name"), release.get("name")):
        try:
            latest_version = normalize_version(release_version_source)
            break
        except UpdateError:
            continue
    if not latest_version:
        raise UpdateError("GitHub Release không có tag_name hoặc name chứa version hợp lệ.")
    current_version = normalize_version(APP_VERSION)
    _log("latest_version", latest_version)

    update_available = _version_tuple(latest_version) > _version_tuple(current_version)
    if not update_available:
        return {
            "version": latest_version,
            "current_version": current_version,
            "update_available": False,
            "changelog": str(release.get("body") or "").strip(),
        }

    info = _select_release_asset(release, latest_version)
    if not info["sha256"]:
        info["sha256"] = _load_sidecar_hash(info, release, timeout)
    if not info["sha256"]:
        raise UpdateError(
            "Asset cập nhật thiếu SHA-256 (digest hoặc file <asset>.sha256); "
            "ứng dụng từ chối tải để bảo vệ an toàn."
        )
    info["changelog"] = str(release.get("body") or "").strip()
    info["current_version"] = current_version
    info["update_available"] = True
    normalized = validate_manifest(info, require_hash=True)
    _log("selected_asset", normalized["package_name"])
    _log("download_url", normalized["download_url"])
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
        _log("Permission FAILED", f"{target}: {exc}")
        raise UpdateError(
            "Ứng dụng không có quyền ghi vào thư mục cài đặt hiện tại. "
            "Hãy cấp quyền ghi phù hợp rồi thử lại."
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


def _safe_extract(archive: zipfile.ZipFile, destination: Path) -> None:
    """Extract a ZIP without traversal, absolute paths, or symlink entries."""
    root = destination.resolve()
    for item in archive.infolist():
        relative = PurePosixPath(item.filename.replace("\\", "/"))
        if relative.is_absolute() or ".." in relative.parts:
            raise UpdateError("Gói ZIP chứa đường dẫn không an toàn.")
        unix_mode = item.external_attr >> 16
        if stat.S_ISLNK(unix_mode):
            raise UpdateError("Gói ZIP không được chứa symbolic link.")
        target = destination.joinpath(*relative.parts)
        if target.resolve() != root and root not in target.resolve().parents:
            raise UpdateError("Gói ZIP chứa đường dẫn vượt khỏi thư mục tạm.")
        if item.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(item) as source, target.open("wb") as output:
                shutil.copyfileobj(source, output)


def download_update(
    info: dict, progress: Callable[[int], None] | None = None
) -> PreparedUpdate:
    info = validate_manifest(info, require_hash=True)
    install_mode = str(info.get("install_mode") or "portable").lower()
    if install_mode not in ("portable", "installer"):
        raise UpdateError("Kiểu cài đặt của asset không được hỗ trợ.")
    if install_mode == "portable":
        ensure_installation_writable()
    _log_runtime_paths()
    staging = Path(tempfile.mkdtemp(prefix="NetflixManager-update-"))
    package = staging / info["package_name"]
    _log("download_path", package)
    try:
        with requests.get(
            info["download_url"],
            headers=_github_headers(),
            stream=True,
            timeout=(15, 120),
        ) as response:
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
        _log("Download FAILED", exc)
        raise UpdateError(f"Tải bản cập nhật thất bại: {exc}") from exc

    try:
        downloaded_size = package.stat().st_size
    except OSError as exc:
        shutil.rmtree(staging, ignore_errors=True)
        _log("Download FAILED", exc)
        raise UpdateError(f"Không thể kiểm tra file cập nhật đã tải: {exc}") from exc
    if downloaded_size <= 0:
        shutil.rmtree(staging, ignore_errors=True)
        _log("Download FAILED", "empty file")
        raise UpdateError("File cập nhật tải về rỗng.")
    expected_size = int(info.get("asset_size") or 0)
    if expected_size and downloaded_size != expected_size:
        shutil.rmtree(staging, ignore_errors=True)
        _log("Download FAILED", f"size {downloaded_size} != {expected_size}")
        raise UpdateError("Dung lượng file tải về không khớp với GitHub Release.")

    if _sha256(package) != info["sha256"]:
        shutil.rmtree(staging, ignore_errors=True)
        _log("Download FAILED", "SHA-256 mismatch")
        raise UpdateError(
            "File tải về không đúng mã SHA-256; bản hiện tại được giữ nguyên."
        )
    _log("Download OK", package.name)

    payload = staging / "payload"
    payload.mkdir()
    try:
        if info["package_type"] == "exe":
            executable = payload / info["executable_name"]
            shutil.move(str(package), executable)
        else:
            extracted = staging / "extracted"
            extracted.mkdir()
            with zipfile.ZipFile(package) as archive:
                _safe_extract(archive, extracted)
            candidates = [
                path for path in extracted.rglob(info["executable_name"]) if path.is_file()
            ]
            if len(candidates) != 1:
                raise UpdateError(
                    "Gói ZIP phải chứa đúng một executable_name đã khai báo."
                )
            source_root = candidates[0].parent
            shutil.rmtree(payload)
            shutil.move(str(source_root), str(payload))
            executable = payload / info["executable_name"]
    except (zipfile.BadZipFile, OSError) as exc:
        shutil.rmtree(staging, ignore_errors=True)
        _log("Extract FAILED", exc)
        raise UpdateError(f"Không thể giải nén bản cập nhật: {exc}") from exc
    except UpdateError:
        shutil.rmtree(staging, ignore_errors=True)
        _log("Extract FAILED", "invalid ZIP layout")
        raise

    if info.get("require_authenticode", False):
        verify_authenticode(executable, str(info.get("publisher", "")).strip())
    if progress:
        progress(100)
    _log("Extract OK", payload)
    return PreparedUpdate(staging, payload, executable, install_mode)


def _is_protected(relative: Path) -> bool:
    parts = tuple(part.casefold() for part in relative.parts)
    return bool(
        not parts
        or parts[0] in PROTECTED_ROOTS
        or relative.name.casefold() in PROTECTED_NAMES
        or relative.suffix.casefold() in PROTECTED_SUFFIXES
    )


def _install_operations(prepared: PreparedUpdate, running_exe: Path) -> list[dict[str, str]]:
    operations: list[dict[str, str]] = []
    executable_resolved = prepared.executable.resolve()
    seen_targets: set[str] = set()
    for source in sorted(prepared.payload_dir.rglob("*")):
        if not source.is_file():
            continue
        relative = source.relative_to(prepared.payload_dir)
        target_relative = Path(running_exe.name) if source.resolve() == executable_resolved else relative
        if _is_protected(target_relative):
            _log("Preserve", target_relative)
            continue
        key = str(target_relative).casefold()
        if key in seen_targets:
            raise UpdateError(f"Gói cập nhật có file đích trùng nhau: {target_relative}")
        seen_targets.add(key)
        operations.append({"source": str(source.resolve()), "target": str(target_relative)})
    if running_exe.name.casefold() not in seen_targets:
        raise UpdateError("Gói cập nhật không tạo được file EXE đang chạy.")
    return operations


def _powershell_update_helper() -> str:
    """Return a path-safe helper; all runtime paths come from UTF-8 JSON."""
    return r'''param([Parameter(Mandatory=$true)][string]$TransactionPath)
$ErrorActionPreference = 'Stop'
$tx = Get-Content -LiteralPath $TransactionPath -Raw -Encoding UTF8 | ConvertFrom-Json
$applied = [System.Collections.Generic.List[object]]::new()

# The helper outlives the old PyInstaller one-file process. Every app instance
# started from here must unpack into a fresh _MEI directory; otherwise the old
# bootloader removes files such as base_library.zip while the new app imports.
$env:PYINSTALLER_RESET_ENVIRONMENT = '1'
Get-ChildItem Env: | Where-Object { $_.Name -like '_PYI_*' } | ForEach-Object {
    Remove-Item -LiteralPath "Env:$($_.Name)" -ErrorAction SilentlyContinue
}

function Write-UpdateLog([string]$Event, [string]$Detail = '') {
    $line = "$(Get-Date -Format 'yyyy-MM-ddTHH:mm:ss') | $Event"
    if ($Detail) { $line += ": $Detail" }
    try { Add-Content -LiteralPath $tx.log -Value $line -Encoding UTF8 -ErrorAction Stop } catch {}
}

function Restore-Update {
    Write-UpdateLog 'Rollback START'
    for ($i = $applied.Count - 1; $i -ge 0; $i--) {
        $item = $applied[$i]
        if (Test-Path -LiteralPath $item.target) {
            Remove-Item -LiteralPath $item.target -Force -Recurse -ErrorAction SilentlyContinue
        }
        if ($item.hadOriginal -and (Test-Path -LiteralPath $item.backup)) {
            $parent = Split-Path -Parent $item.target
            if ($parent) { New-Item -ItemType Directory -Path $parent -Force | Out-Null }
            Move-Item -LiteralPath $item.backup -Destination $item.target -Force
        }
    }
    Write-UpdateLog 'Rollback OK'
}

try {
    Write-UpdateLog 'PyInstaller environment' 'fresh _MEI forced'
    Write-UpdateLog 'Current EXE' $tx.executable
    Write-UpdateLog 'Current Folder' $tx.appRoot
    while (Get-Process -Id $tx.pid -ErrorAction SilentlyContinue) { Start-Sleep -Milliseconds 300 }
    New-Item -ItemType Directory -Path $tx.backupRoot -Force | Out-Null

    foreach ($operation in $tx.operations) {
        $target = Join-Path $tx.appRoot $operation.target
        $backup = Join-Path $tx.backupRoot $operation.target
        $targetParent = Split-Path -Parent $target
        if ($targetParent) { New-Item -ItemType Directory -Path $targetParent -Force | Out-Null }
        $hadOriginal = Test-Path -LiteralPath $target
        if ($hadOriginal) {
            $backupParent = Split-Path -Parent $backup
            if ($backupParent) { New-Item -ItemType Directory -Path $backupParent -Force | Out-Null }
            Move-Item -LiteralPath $target -Destination $backup -Force
        }
        $record = [pscustomobject]@{ target=$target; backup=$backup; hadOriginal=$hadOriginal }
        $applied.Add($record)
        Copy-Item -LiteralPath $operation.source -Destination $target -Force
    }
    Write-UpdateLog 'Replace OK' "$($tx.operations.Count) file(s)"

    $test = Start-Process -FilePath $tx.executable -ArgumentList '--self-test-update' -WorkingDirectory $tx.appRoot -Wait -PassThru
    if ($test.ExitCode -ne 0) { throw "Self-test failed with exit code $($test.ExitCode)" }
    if (-not $tx.skipRestart) {
        Start-Process -FilePath $tx.executable -WorkingDirectory $tx.appRoot
        Write-UpdateLog 'Restart OK' $tx.executable
    } else {
        Write-UpdateLog 'Restart SKIPPED' 'integration test'
    }
    Remove-Item -LiteralPath $tx.backupRoot -Force -Recurse -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $tx.stagingRoot -Force -Recurse -ErrorAction SilentlyContinue
    exit 0
} catch {
    Write-UpdateLog 'Update FAILED' $_.Exception.Message
    try { Restore-Update } catch { Write-UpdateLog 'Rollback FAILED' $_.Exception.Message }
    try {
        if (Test-Path -LiteralPath $tx.executable) {
            Start-Process -FilePath $tx.executable -WorkingDirectory $tx.appRoot
        }
    } catch { Write-UpdateLog 'Restart old version FAILED' $_.Exception.Message }
    exit 1
}
'''


def install_and_restart(prepared: PreparedUpdate) -> None:
    if not getattr(sys, "frozen", False):
        raise UpdateError("Chỉ có thể tự cài đặt trên bản .exe đã đóng gói.")
    if prepared.install_mode == "installer":
        try:
            installer_valid = (
                prepared.executable.is_file()
                and prepared.executable.stat().st_size > 0
            )
        except OSError:
            installer_valid = False
        if not installer_valid:
            raise UpdateError("File installer trong thư mục tạm không còn hợp lệ.")
        try:
            subprocess.Popen(
                [str(prepared.executable)],
                close_fds=True,
                cwd=str(prepared.staging_dir),
                env=_independent_subprocess_environment(),
            )
        except OSError as exc:
            _log("Installer start FAILED", exc)
            raise UpdateError(f"Không thể chạy installer cập nhật: {exc}") from exc
        _log("Installer started", prepared.executable)
        return
    ensure_installation_writable()
    running_exe = current_executable()
    root = app_dir().resolve()
    if running_exe.parent != root:
        raise UpdateError("EXE đang chạy không nằm trong thư mục ứng dụng hiện tại.")
    if not prepared.executable.is_file() or not prepared.payload_dir.is_dir():
        raise UpdateError("Bản cập nhật trong thư mục tạm không còn tồn tại.")

    _log_runtime_paths()
    operations = _install_operations(prepared, running_exe)
    backup_root = root / f".netflixmanager-update-backup-{uuid.uuid4().hex}"
    transaction = {
        "pid": os.getpid(),
        "appRoot": str(root),
        "executable": str(running_exe),
        "stagingRoot": str(prepared.staging_dir.resolve()),
        "backupRoot": str(backup_root),
        "log": str(update_log_path()),
        "skipRestart": False,
        "operations": operations,
    }
    transaction_path = prepared.staging_dir / "transaction.json"
    helper = prepared.staging_dir / "apply_update.ps1"
    transaction_path.write_text(
        json.dumps(transaction, ensure_ascii=False, indent=2), encoding="utf-8-sig"
    )
    helper.write_text(_powershell_update_helper(), encoding="utf-8-sig")
    try:
        subprocess.Popen(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(helper),
                str(transaction_path),
            ],
            creationflags=(
                getattr(subprocess, "CREATE_NO_WINDOW", 0)
                | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            ),
            close_fds=True,
            cwd=str(prepared.staging_dir),
            env=_independent_subprocess_environment(),
        )
    except OSError as exc:
        _log("Helper start FAILED", exc)
        raise UpdateError(f"Không thể khởi động trình cài đặt cập nhật: {exc}") from exc
    _log("Install scheduled", f"{len(operations)} file(s)")


def frozen_runtime_self_test() -> bool:
    """Small smoke test invoked against the replacement executable."""
    return bool(
        getattr(sys, "frozen", False)
        and current_executable().is_file()
        and current_executable().parent == app_dir().resolve()
        and release_api_url()
    )
