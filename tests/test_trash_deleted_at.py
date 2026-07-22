import sqlite3
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import database


class TrashDeletedAtTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "trash-deleted-at.db"
        self.db_patch = patch.object(database, "DB_FILE", str(self.db_path))
        self.db_patch.start()
        database.init_db()

    def tearDown(self):
        self.db_patch.stop()
        self.temp_dir.cleanup()

    def connection(self):
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def set_deleted_at(self, table, item_id, deleted_at):
        connection = self.connection()
        connection.execute(
            f"UPDATE {table} SET deleted_at = ? WHERE id = ?",
            (deleted_at, item_id),
        )
        connection.commit()
        connection.close()

    def test_migration_adds_deleted_at_to_both_tables(self):
        connection = self.connection()
        account_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(tai_khoan)")
        }
        order_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(don_hang)")
        }
        connection.close()

        self.assertIn("deleted_at", account_columns)
        self.assertIn("deleted_at", order_columns)

    def test_account_trash_uses_deletion_time_and_restore_clears_it(self):
        self.assertTrue(database.add_account("trash-a@example.test", "pw", "2099-01-01")[0])
        self.assertTrue(database.add_account("trash-b@example.test", "pw", "2099-01-01")[0])
        connection = self.connection()
        account_ids = {
            row["email"]: row["id"]
            for row in connection.execute(
                "SELECT id, email FROM tai_khoan WHERE email LIKE 'trash-%@example.test'"
            )
        }
        connection.close()
        account_a = account_ids["trash-a@example.test"]
        account_b = account_ids["trash-b@example.test"]

        self.assertTrue(database.delete_account_soft(account_a))
        connection = self.connection()
        stored_timestamp = connection.execute(
            "SELECT deleted_at FROM tai_khoan WHERE id = ?", (account_a,)
        ).fetchone()["deleted_at"]
        connection.close()
        datetime.strptime(stored_timestamp, "%Y-%m-%d %H:%M:%S")

        self.set_deleted_at("tai_khoan", account_a, "2026-07-22 21:35:10")
        self.assertTrue(database.delete_account_soft(account_b))
        self.set_deleted_at("tai_khoan", account_b, "2026-07-22 21:35:15")

        deleted_ids = [row["id"] for row in database.get_deleted_accounts()]
        self.assertEqual(deleted_ids[:2], [account_b, account_a])

        self.assertTrue(database.restore_account(account_b))
        connection = self.connection()
        restored_timestamp = connection.execute(
            "SELECT deleted_at FROM tai_khoan WHERE id = ?", (account_b,)
        ).fetchone()["deleted_at"]
        connection.close()
        self.assertIsNone(restored_timestamp)
        self.assertNotIn(account_b, [row["id"] for row in database.get_deleted_accounts()])
        self.assertIn(account_a, [row["id"] for row in database.get_deleted_accounts()])
        self.assertTrue(database.delete_account_permanently(account_a))
        self.assertNotIn(account_a, [row["id"] for row in database.get_deleted_accounts()])

    def test_order_trash_uses_deletion_time_and_legacy_null_is_last(self):
        email = "trash-orders@example.test"
        self.assertTrue(database.add_account(email, "pw", "2099-01-01")[0])
        self.assertTrue(database.add_order(
            email, "Netflix", "Trash order A", 100000, "2026-01-01", "2099-01-01"
        )[0])
        self.assertTrue(database.add_order(
            email, "Netflix", "Trash order B", 100000, "2026-01-01", "2099-01-01"
        )[0])
        connection = self.connection()
        order_ids = {
            row["ten_khach_hang"]: row["id"]
            for row in connection.execute(
                "SELECT id, ten_khach_hang FROM don_hang WHERE ten_khach_hang LIKE 'Trash order %'"
            )
        }
        connection.close()
        order_a = order_ids["Trash order A"]
        order_b = order_ids["Trash order B"]

        self.assertTrue(database.delete_order_soft(order_a))
        self.assertTrue(database.delete_order_soft(order_b))
        self.set_deleted_at("don_hang", order_a, None)
        self.set_deleted_at("don_hang", order_b, "2026-07-22 21:35:15")

        deleted_ids = [row["id"] for row in database.get_deleted_orders()]
        self.assertEqual(deleted_ids[:2], [order_b, order_a])

        self.assertTrue(database.restore_order(order_b))
        connection = self.connection()
        restored_timestamp = connection.execute(
            "SELECT deleted_at FROM don_hang WHERE id = ?", (order_b,)
        ).fetchone()["deleted_at"]
        connection.close()
        self.assertIsNone(restored_timestamp)
        self.assertNotIn(order_b, [row["id"] for row in database.get_deleted_orders()])
        self.assertIn(order_a, [row["id"] for row in database.get_deleted_orders()])
        self.assertTrue(database.delete_order_permanently(order_a))
        self.assertNotIn(order_a, [row["id"] for row in database.get_deleted_orders()])


if __name__ == "__main__":
    unittest.main()
