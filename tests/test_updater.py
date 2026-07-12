import hashlib
import io
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import updater


class FakeResponse:
    def __init__(self, content: bytes):
        self.content = content
        self.headers = {"content-length": str(len(content))}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def raise_for_status(self):
        return None

    def iter_content(self, _size):
        yield self.content


class UpdaterTests(unittest.TestCase):
    def manifest(self, content: bytes, **changes):
        result = {
            "version": "9.0.0",
            "download_url": "https://example.test/NetflixManager.exe",
            "package_type": "exe",
            "package_name": "NetflixManager.exe",
            "executable_name": "NetflixManager.exe",
            "sha256": hashlib.sha256(content).hexdigest(),
        }
        result.update(changes)
        return result

    def test_manifest_requires_https_and_safe_names(self):
        with self.assertRaises(updater.UpdateError):
            updater.validate_manifest(self.manifest(b"x", download_url="http://example.test/a.exe"))
        with self.assertRaises(updater.UpdateError):
            updater.validate_manifest(self.manifest(b"x", package_name="../a.exe"))

    def test_download_requires_sha256(self):
        with self.assertRaises(updater.UpdateError):
            updater.validate_manifest(self.manifest(b"x", sha256=""), require_hash=True)

    def test_new_version_without_sha256_is_rejected_during_check(self):
        response = FakeResponse(b"")
        response.json = lambda: self.manifest(b"x", sha256="")
        with patch.object(updater.requests, "get", return_value=response):
            with self.assertRaisesRegex(updater.UpdateError, "thiếu SHA-256"):
                updater.check_for_update()

    def test_download_exe_and_verify_hash(self):
        content = b"fake executable"
        with tempfile.TemporaryDirectory() as temp_dir, \
                patch.object(updater, "app_dir", return_value=Path(temp_dir)), \
                patch.object(updater.requests, "get", return_value=FakeResponse(content)):
            prepared = updater.download_update(self.manifest(content))
            self.assertEqual(prepared.read_bytes(), content)

    def test_download_zip_extracts_declared_executable(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("release/NetflixManager.exe", b"zip executable")
        content = buffer.getvalue()
        info = self.manifest(
            content,
            download_url="https://example.test/NetflixManager.zip",
            package_type="zip",
            package_name="NetflixManager.zip",
        )
        with tempfile.TemporaryDirectory() as temp_dir, \
                patch.object(updater, "app_dir", return_value=Path(temp_dir)), \
                patch.object(updater.requests, "get", return_value=FakeResponse(content)):
            prepared = updater.download_update(info)
            self.assertEqual(prepared.name, "NetflixManager.exe")
            self.assertEqual(prepared.read_bytes(), b"zip executable")

    def test_hash_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir, \
                patch.object(updater, "app_dir", return_value=Path(temp_dir)), \
                patch.object(updater.requests, "get", return_value=FakeResponse(b"changed")):
            with self.assertRaisesRegex(updater.UpdateError, "SHA-256"):
                updater.download_update(self.manifest(b"expected"))

    def test_unwritable_installation_has_clear_error(self):
        with patch.object(Path, "write_bytes", side_effect=PermissionError):
            with self.assertRaisesRegex(updater.UpdateError, "không có quyền ghi"):
                updater.ensure_installation_writable(Path.cwd())


if __name__ == "__main__":
    unittest.main()
