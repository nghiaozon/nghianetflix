"""Resolve writable files consistently in source and PyInstaller builds."""

import shutil
import sys
from pathlib import Path


def app_dir() -> Path:
    """Directory containing the executable (or source files in development)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def data_dir() -> Path:
    path = app_dir() / "data"
    path.mkdir(parents=True, exist_ok=True)
    return path


def data_file(name: str) -> str:
    return str(data_dir() / name)


def config_dir() -> Path:
    path = app_dir() / "config"
    path.mkdir(parents=True, exist_ok=True)
    return path


def config_file(name: str) -> str:
    target = config_dir() / name
    legacy = app_dir() / name
    if not target.exists() and legacy.is_file():
        try:
            shutil.copy2(legacy, target)
        except OSError:
            pass
    return str(target)


def external_file(name: str) -> str:
    """Resolve user-editable configuration beside the executable."""
    return str(app_dir() / name)
