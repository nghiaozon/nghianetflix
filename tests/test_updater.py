import hashlib
import io
import json
import os
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import updater


class FakeResponse:
    def __init__(self, content: bytes = b"", json_data=None):
        self.content = content
        self._json_data = json_data
        self.text = content.decode("utf-8", errors="replace")
        self.headers = {"content-length": str(len(content))}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def raise_for_status(self):
        return None

    def iter_content(self, _size):
        yield self.content

    def json(self):
        return self._json_data


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

    def release(self, *, version="9.0.0", asset_name="NetflixManager.exe", **changes):
        content = b"release executable"
        result = {
            "tag_name": f"v{version}",
            "name": f"Netflix Manager {version}",
            "body": "Release notes",
            "assets": [
                {
                    "name": asset_name,
                    "browser_download_url": f"https://example.test/{asset_name}",
                    "size": len(content),
                    "digest": f"sha256:{hashlib.sha256(content).hexdigest()}",
                }
            ],
        }
        result.update(changes)
        return result

    def test_manifest_requires_https_and_safe_names(self):
        with self.assertRaises(updater.UpdateError):
            updater.validate_manifest(
                self.manifest(b"x", download_url="http://example.test/a.exe")
            )
        with self.assertRaises(updater.UpdateError):
            updater.validate_manifest(self.manifest(b"x", package_name="../a.exe"))

    def test_download_requires_sha256(self):
        with self.assertRaises(updater.UpdateError):
            updater.validate_manifest(self.manifest(b"x", sha256=""), require_hash=True)

    def test_check_uses_github_latest_release_api(self):
        response = FakeResponse(json_data=self.release())
        with tempfile.TemporaryDirectory() as temp_dir, patch.object(
            updater, "app_dir", return_value=Path(temp_dir)
        ), patch.object(updater.requests, "get", return_value=response) as get:
            info = updater.check_for_update()
        self.assertTrue(info["update_available"])
        self.assertEqual(info["version"], "9.0.0")
        self.assertEqual(info["package_name"], "NetflixManager.exe")
        self.assertEqual(get.call_args.args[0], updater.release_api_url())

    def test_version_normalization_and_current_release(self):
        self.assertEqual(updater.normalize_version("v1.0.7"), "1.0.7")
        self.assertEqual(updater.normalize_version("Netflix Manager v01.02.003"), "1.2.3")
        response = FakeResponse(json_data=self.release(version=updater.APP_VERSION))
        with tempfile.TemporaryDirectory() as temp_dir, patch.object(
            updater, "app_dir", return_value=Path(temp_dir)
        ), patch.object(updater.requests, "get", return_value=response):
            info = updater.check_for_update()
        self.assertFalse(info["update_available"])

    def test_release_name_is_used_when_tag_is_not_a_version(self):
        release = self.release()
        release["tag_name"] = "latest-windows"
        response = FakeResponse(json_data=release)
        with tempfile.TemporaryDirectory() as temp_dir, patch.object(
            updater, "app_dir", return_value=Path(temp_dir)
        ), patch.object(updater.requests, "get", return_value=response):
            info = updater.check_for_update()
        self.assertEqual(info["version"], "9.0.0")

    def test_unknown_or_empty_release_asset_is_rejected(self):
        for asset_name, size, message in (
            ("random.exe", 10, "Không tìm thấy asset"),
            ("NetflixManager.exe", 0, "dung lượng bằng 0"),
        ):
            release = self.release(asset_name=asset_name)
            release["assets"][0]["size"] = size
            response = FakeResponse(json_data=release)
            with tempfile.TemporaryDirectory() as temp_dir, patch.object(
                updater, "app_dir", return_value=Path(temp_dir)
            ), patch.object(updater.requests, "get", return_value=response):
                with self.assertRaisesRegex(updater.UpdateError, message):
                    updater.check_for_update()

    def test_sidecar_hash_is_used_when_api_digest_is_missing(self):
        release = self.release()
        release["assets"][0]["digest"] = None
        release["assets"].append(
            {
                "name": "NetflixManager.exe.sha256",
                "browser_download_url": "https://example.test/app.sha256",
                "size": 86,
            }
        )
        digest = hashlib.sha256(b"release executable").hexdigest()
        responses = [
            FakeResponse(json_data=release),
            FakeResponse(f"{digest}  NetflixManager.exe\n".encode()),
        ]
        with tempfile.TemporaryDirectory() as temp_dir, patch.object(
            updater, "app_dir", return_value=Path(temp_dir)
        ), patch.object(updater.requests, "get", side_effect=responses):
            info = updater.check_for_update()
        self.assertEqual(info["sha256"], digest)

    def test_network_error_is_user_friendly(self):
        with tempfile.TemporaryDirectory() as temp_dir, patch.object(
            updater, "app_dir", return_value=Path(temp_dir)
        ), patch.object(
            updater.requests,
            "get",
            side_effect=updater.requests.ConnectionError("offline"),
        ):
            with self.assertRaisesRegex(updater.UpdateError, "Không thể kết nối GitHub"):
                updater.check_for_update()

    def test_download_exe_and_verify_hash(self):
        content = b"fake executable"
        with tempfile.TemporaryDirectory() as temp_dir, patch.object(
            updater, "app_dir", return_value=Path(temp_dir)
        ), patch.object(updater.requests, "get", return_value=FakeResponse(content)):
            prepared = updater.download_update(self.manifest(content))
            self.assertEqual(prepared.executable.read_bytes(), content)
            self.assertEqual(prepared.payload_dir, prepared.executable.parent)

    def test_download_zip_extracts_complete_program_tree(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("release/NetflixManager.exe", b"zip executable")
            archive.writestr("release/lib/runtime.dll", b"dll")
            archive.writestr("release/assets/theme.bin", b"resource")
        content = buffer.getvalue()
        info = self.manifest(
            content,
            download_url="https://example.test/NetflixManager.zip",
            package_type="zip",
            package_name="NetflixManager.zip",
        )
        with tempfile.TemporaryDirectory() as temp_dir, patch.object(
            updater, "app_dir", return_value=Path(temp_dir)
        ), patch.object(updater.requests, "get", return_value=FakeResponse(content)):
            prepared = updater.download_update(info)
            self.assertEqual(prepared.executable.read_bytes(), b"zip executable")
            self.assertEqual((prepared.payload_dir / "lib/runtime.dll").read_bytes(), b"dll")
            self.assertEqual((prepared.payload_dir / "assets/theme.bin").read_bytes(), b"resource")

    def test_zip_path_traversal_is_rejected(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("../NetflixManager.exe", b"bad")
        content = buffer.getvalue()
        info = self.manifest(
            content,
            download_url="https://example.test/update.zip",
            package_type="zip",
            package_name="update.zip",
        )
        with tempfile.TemporaryDirectory() as temp_dir, patch.object(
            updater, "app_dir", return_value=Path(temp_dir)
        ), patch.object(updater.requests, "get", return_value=FakeResponse(content)):
            with self.assertRaisesRegex(updater.UpdateError, "không an toàn"):
                updater.download_update(info)

    def test_hash_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir, patch.object(
            updater, "app_dir", return_value=Path(temp_dir)
        ), patch.object(updater.requests, "get", return_value=FakeResponse(b"changed")):
            with self.assertRaisesRegex(updater.UpdateError, "SHA-256"):
                updater.download_update(self.manifest(b"expected"))

    def test_empty_download_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir, patch.object(
            updater, "app_dir", return_value=Path(temp_dir)
        ), patch.object(updater.requests, "get", return_value=FakeResponse(b"")):
            with self.assertRaisesRegex(updater.UpdateError, "tải về rỗng"):
                updater.download_update(self.manifest(b""))

    def test_unwritable_installation_has_clear_error(self):
        with patch.object(Path, "write_bytes", side_effect=PermissionError):
            with self.assertRaisesRegex(updater.UpdateError, "không có quyền ghi"):
                updater.ensure_installation_writable(Path.cwd())

    def test_install_plan_renames_executable_and_preserves_user_data(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            payload = root / "payload"
            payload.mkdir()
            executable = payload / "ReleaseName.exe"
            executable.write_bytes(b"exe")
            (payload / "runtime.dll").write_bytes(b"dll")
            (payload / "settings.json").write_text("{}", encoding="utf-8")
            (payload / "data").mkdir()
            (payload / "data/user.db").write_bytes(b"db")
            prepared = updater.PreparedUpdate(root, payload, executable)

            with patch.object(updater, "app_dir", return_value=root):
                operations = updater._install_operations(
                    prepared, root / "Tên ứng dụng đang chạy.exe"
                )
            targets = {item["target"] for item in operations}
            self.assertEqual(targets, {"Tên ứng dụng đang chạy.exe", "runtime.dll"})

    def test_transaction_is_utf8_and_helper_contains_rollback(self):
        helper = updater._powershell_update_helper()
        self.assertIn("Restore-Update", helper)
        self.assertIn("Rollback OK", helper)
        self.assertIn("Replace OK", helper)
        self.assertIn("Restart OK", helper)
        self.assertNotIn("NetflixManager.exe", helper)
        with tempfile.TemporaryDirectory() as temp_dir:
            unicode_path = Path(temp_dir) / "Ứng dụng" / "Quản lý Netflix.exe"
            encoded = json.dumps(
                {"executable": str(unicode_path)}, ensure_ascii=False
            ).encode("utf-8")
            self.assertIn("Ứng dụng".encode("utf-8"), encoded)

    @unittest.skipUnless(os.name == "nt", "PowerShell helper is Windows-specific")
    def test_powershell_helper_has_valid_syntax(self):
        parser = (
            "$source=[Console]::In.ReadToEnd();$tokens=$null;$errors=$null;"
            "[Management.Automation.Language.Parser]::ParseInput($source,"
            "[ref]$tokens,[ref]$errors)|Out-Null;"
            "if($errors.Count){$errors|ForEach-Object{$_.Message};exit 1}"
        )
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", parser],
            input=updater._powershell_update_helper(),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_install_transaction_keeps_unicode_runtime_path_out_of_script(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            app_root = base / "Ứng dụng & dữ liệu"
            staging = base / "Tạm cập nhật"
            payload = staging / "payload"
            app_root.mkdir()
            payload.mkdir(parents=True)
            running_exe = app_root / "Quản lý Netflix.exe"
            running_exe.write_bytes(b"old")
            release_exe = payload / "NetflixManager.exe"
            release_exe.write_bytes(b"new")
            prepared = updater.PreparedUpdate(staging, payload, release_exe)

            with patch.object(updater.sys, "frozen", True, create=True), patch.object(
                updater, "app_dir", return_value=app_root
            ), patch.object(
                updater, "current_executable", return_value=running_exe
            ), patch.object(updater.subprocess, "Popen") as popen:
                updater.install_and_restart(prepared)

            transaction = json.loads(
                (staging / "transaction.json").read_text(encoding="utf-8-sig")
            )
            self.assertEqual(transaction["executable"], str(running_exe))
            self.assertEqual(transaction["appRoot"], str(app_root))
            self.assertEqual(transaction["operations"][0]["target"], running_exe.name)
            self.assertNotIn(str(app_root), (staging / "apply_update.ps1").read_text(encoding="utf-8-sig"))
            popen.assert_called_once()

    def test_installer_is_started_from_temp_without_overwriting_running_exe(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            staging = Path(temp_dir)
            payload = staging / "payload"
            payload.mkdir()
            installer = payload / "NetflixManager-Setup.exe"
            installer.write_bytes(b"installer")
            prepared = updater.PreparedUpdate(
                staging, payload, installer, install_mode="installer"
            )
            with patch.object(updater.sys, "frozen", True, create=True), patch.object(
                updater.subprocess, "Popen"
            ) as popen, patch.object(updater, "ensure_installation_writable") as writable:
                updater.install_and_restart(prepared)
            writable.assert_not_called()
            popen.assert_called_once()


if __name__ == "__main__":
    unittest.main()
