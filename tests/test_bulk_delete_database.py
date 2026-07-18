import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import database


class BulkDeleteDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "bulk-delete.db"
        self.db_patch = patch.object(database, "DB_FILE", str(self.db_path))
        self.db_patch.start()

    def tearDown(self):
        self.db_patch.stop()
        self.temp_dir.cleanup()

    def connect(self):
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def create_tables(self):
        connection = self.connect()
        connection.executescript(
            """
            CREATE TABLE tai_khoan (
                id INTEGER PRIMARY KEY,
                email TEXT,
                ma_don_hang TEXT,
                trang_thai TEXT
            );
            CREATE TABLE don_hang (
                id INTEGER PRIMARY KEY,
                email_tai_khoan TEXT,
                da_xoa INTEGER DEFAULT 0
            );
            """
        )
        connection.commit()
        connection.close()

    def test_accounts_are_soft_deleted_together(self):
        self.create_tables()
        connection = self.connect()
        connection.executemany(
            "INSERT INTO tai_khoan(id, email, trang_thai) VALUES (?, ?, ?)",
            [(1, "one@example.com", "Đang hoạt động"), (2, "two@example.com", "Đang hoạt động")],
        )
        connection.commit()
        connection.close()

        self.assertTrue(database.delete_accounts_soft_bulk({1, 2}))

        connection = self.connect()
        statuses = {
            row['id']: row['trang_thai']
            for row in connection.execute("SELECT id, trang_thai FROM tai_khoan")
        }
        connection.close()
        self.assertEqual(statuses, {1: "Đã xóa", 2: "Đã xóa"})

    def test_orders_are_soft_deleted_and_linked_accounts_are_released(self):
        self.create_tables()
        connection = self.connect()
        connection.execute(
            "INSERT INTO tai_khoan VALUES (1, 'one@example.com', 'DH-0007', 'Đã bán')"
        )
        connection.execute("INSERT INTO don_hang VALUES (7, 'one@example.com', 0)")
        connection.commit()
        connection.close()

        self.assertTrue(database.delete_orders_soft_bulk({7}))

        connection = self.connect()
        order_deleted = connection.execute(
            "SELECT da_xoa FROM don_hang WHERE id = 7"
        ).fetchone()['da_xoa']
        account = connection.execute(
            "SELECT ma_don_hang, trang_thai FROM tai_khoan WHERE id = 1"
        ).fetchone()
        connection.close()
        self.assertEqual(order_deleted, 1)
        self.assertIsNone(account['ma_don_hang'])
        self.assertEqual(account['trang_thai'], "Đang hoạt động")

    def test_order_bulk_delete_rolls_back_when_link_release_fails(self):
        connection = self.connect()
        connection.execute(
            "CREATE TABLE don_hang (id INTEGER PRIMARY KEY, email_tai_khoan TEXT, da_xoa INTEGER)"
        )
        connection.execute("INSERT INTO don_hang VALUES (3, 'missing@example.com', 0)")
        connection.commit()
        connection.close()

        with patch("builtins.print"):
            self.assertFalse(database.delete_orders_soft_bulk({3}))

        connection = self.connect()
        deleted = connection.execute(
            "SELECT da_xoa FROM don_hang WHERE id = 3"
        ).fetchone()['da_xoa']
        connection.close()
        self.assertEqual(deleted, 0)


if __name__ == "__main__":
    unittest.main()
