import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

import database
from dialogs import OrderDialog


class AccountEmailOrderingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "accounts.db"
        self.db_patch = patch.object(database, "DB_FILE", str(self.db_path))
        self.db_patch.start()
        database.init_db()

    def tearDown(self):
        self.db_patch.stop()
        self.temp_dir.cleanup()

    def test_newest_accounts_are_first_and_default_for_new_orders(self):
        for email in ("a@example.test", "b@example.test"):
            success, message = database.add_account(email, "pw", "2099-01-01")
            self.assertTrue(success, message)

        self.assertEqual(database.get_all_emails()[:2], ["b@example.test", "a@example.test"])
        dialog = OrderDialog()
        self.assertEqual(dialog.email_combo.currentText(), "b@example.test")
        self.assertEqual(
            [dialog.email_combo.itemText(index) for index in range(2)],
            ["b@example.test", "a@example.test"],
        )

        success, message = database.add_account("c@example.test", "pw", "2099-01-01")
        self.assertTrue(success, message)
        dialog = OrderDialog()
        self.assertEqual(dialog.email_combo.currentText(), "c@example.test")
        self.assertEqual(database.get_all_emails()[:3], ["c@example.test", "b@example.test", "a@example.test"])

    def test_edit_order_keeps_the_saved_email(self):
        for email in ("a@example.test", "c@example.test"):
            success, message = database.add_account(email, "pw", "2099-01-01")
            self.assertTrue(success, message)

        dialog = OrderDialog(order_data={
            "id": 1,
            "email_tai_khoan": "a@example.test",
            "nen_tang": "Zalo",
            "ten_khach_hang": "Customer",
            "so_tien": 100000,
            "ngay_mua": "2026-07-22",
            "ngay_het_han": "2026-08-21",
            "ghi_chu": "",
        })
        self.assertEqual(dialog.email_combo.currentText(), "a@example.test")

    def test_legacy_accounts_without_creation_time_fall_back_to_descending_id(self):
        connection = sqlite3.connect(self.db_path)
        connection.execute("UPDATE tai_khoan SET created_at = NULL")
        connection.execute(
            "INSERT INTO tai_khoan(email, mat_khau, ngay_het_han, trang_thai, created_at) "
            "VALUES ('legacy-low@example.test', 'pw', '2099-01-01', 'Đang hoạt động', NULL)"
        )
        connection.execute(
            "INSERT INTO tai_khoan(email, mat_khau, ngay_het_han, trang_thai, created_at) "
            "VALUES ('legacy-high@example.test', 'pw', '2099-01-01', 'Đang hoạt động', NULL)"
        )
        connection.commit()
        connection.close()

        self.assertEqual(
            database.get_all_emails()[:2],
            ["legacy-high@example.test", "legacy-low@example.test"],
        )

    def test_migration_backfills_created_time_and_keeps_deleted_accounts_out(self):
        legacy_path = Path(self.temp_dir.name) / "legacy-accounts.db"
        connection = sqlite3.connect(legacy_path)
        connection.executescript("""
            CREATE TABLE tai_khoan (
                id INTEGER PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                mat_khau TEXT NOT NULL,
                ngay_het_han TEXT NOT NULL,
                trang_thai TEXT NOT NULL,
                created_time TEXT
            );
            CREATE TABLE don_hang (
                id INTEGER PRIMARY KEY,
                nen_tang TEXT NOT NULL,
                ngay_tao TEXT
            );
            INSERT INTO tai_khoan VALUES
                (1, 'old@example.test', 'pw', '2099-01-01', 'Đang hoạt động', '2026-01-01 10:00:00'),
                (2, 'new@example.test', 'pw', '2099-01-01', 'Đang hoạt động', '2026-02-01 10:00:00'),
                (3, 'trash@example.test', 'pw', '2099-01-01', 'Đã xóa', '2026-03-01 10:00:00');
        """)
        connection.commit()
        connection.close()

        self.db_patch.stop()
        self.db_patch = patch.object(database, "DB_FILE", str(legacy_path))
        self.db_patch.start()
        database.init_db()

        connection = sqlite3.connect(legacy_path)
        created_at = connection.execute(
            "SELECT created_at FROM tai_khoan WHERE email = 'new@example.test'"
        ).fetchone()[0]
        connection.close()
        self.assertEqual(created_at, "2026-02-01 10:00:00")
        self.assertEqual(database.get_all_emails(), ["new@example.test", "old@example.test"])


if __name__ == "__main__":
    unittest.main()
