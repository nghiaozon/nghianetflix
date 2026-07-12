"""Verify a public update manifest and its release package."""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

import requests

# Running this file directly makes Python use tools/ as sys.path[0]. Add the
# repository root so the verifier can import the same updater module as the app.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import updater


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest_url")
    args = parser.parse_args()

    response = requests.get(args.manifest_url, timeout=30)
    response.raise_for_status()
    info = updater.validate_manifest(response.json(), require_hash=True)

    digest = hashlib.sha256()
    with requests.get(info["download_url"], stream=True, timeout=(15, 180)) as package:
        package.raise_for_status()
        for chunk in package.iter_content(1024 * 1024):
            if chunk:
                digest.update(chunk)
    if digest.hexdigest() != info["sha256"]:
        raise updater.UpdateError("Release asset không khớp SHA-256 trong manifest.")
    print(f"OK: v{info['version']} - {info['package_name']}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        raise SystemExit(1)
