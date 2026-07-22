import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import database


class RecentOrdersTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "recent-orders.db"
        self.db_patch = patch.object(database, "DB_FILE", str(self.db_path))
        self.db_patch.start()
        connection = sqlite3.connect(self.db_path)
        connection.executescript(
            """
            CREATE TABLE tai_khoan (
                id INTEGER PRIMARY KEY,
                ma_don_hang TEXT,
                email TEXT UNIQUE NOT NULL,
                mat_khau TEXT NOT NULL,
                lien_ket TEXT,
                ghi_chu TEXT,
                thong_bao TEXT,
                ngay_het_han TEXT,
                trang_thai TEXT,
                nguon TEXT
            );
            CREATE TABLE don_hang (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email_tai_khoan TEXT,
                nen_tang TEXT NOT NULL,
                ten_khach_hang TEXT,
                so_tien REAL,
                so_lan_thong_bao INTEGER DEFAULT 0,
                ghi_chu TEXT,
                ngay_mua TEXT,
                ngay_het_han TEXT,
                ngay_tao TEXT,
                da_xoa INTEGER DEFAULT 0
            );
            INSERT INTO tai_khoan(
                id, email, mat_khau, ngay_het_han, trang_thai, nguon
            ) VALUES (1, 'orders@netflix.test', 'secret', '2099-12-31',
                      'Đang hoạt động', 'Khách hàng');
            INSERT INTO don_hang(
                id, email_tai_khoan, nen_tang, ten_khach_hang, so_tien,
                ngay_mua, ngay_het_han, ngay_tao, da_xoa
            ) VALUES (1, 'orders@netflix.test', 'Netflix', 'Legacy', 1,
                      '2000-01-01', '2099-12-31', '2026-01-01 08:00:00', 0);
            """
        )
        connection.commit()
        connection.close()
        database.init_db()

    def tearDown(self):
        self.db_patch.stop()
        self.temp_dir.cleanup()

    def connect(self):
        return sqlite3.connect(self.db_path)

    def test_migration_adds_created_at_and_backfills_legacy_creation_time(self):
        connection = self.connect()
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(don_hang)")
        }
        created_at = connection.execute(
            "SELECT created_at FROM don_hang WHERE id = 1"
        ).fetchone()[0]
        connection.close()

        self.assertIn("created_at", columns)
        self.assertEqual(created_at, "2026-01-01 08:00:00")

    def test_recent_order_sort_uses_creation_time_then_id_not_purchase_date(self):
        connection = self.connect()
        connection.executemany(
            """INSERT INTO don_hang(
                    id, email_tai_khoan, nen_tang, ten_khach_hang, so_tien,
                    ngay_mua, ngay_het_han, created_at, da_xoa
                ) VALUES (?, ?, 'Netflix', ?, 1, ?, '2099-12-31', ?, 0)""",
            [
                (2, "orders@netflix.test", "A", "2099-12-31", "2026-03-01 12:00:00"),
                (3, "orders@netflix.test", "B", "1999-01-01", "2026-03-02 12:00:00"),
                (4, "orders@netflix.test", "No timestamp", "2020-01-01", None),
                (5, "orders@netflix.test", "Also no timestamp", "2020-01-01", None),
            ],
        )
        connection.commit()
        connection.close()

        rows = database.get_orders("netflix", "Đơn hàng gần đây")

        self.assertEqual([row["id"] for row in rows], [3, 2, 1, 5, 4])
        self.assertEqual(rows[0]["ngay_mua"], "1999-01-01")

    def test_new_historical_purchase_is_recent_and_edit_keeps_created_at(self):
        success, message = database.add_order(
            "orders@netflix.test", "Netflix", "New", 100000,
            "1999-01-01", "2099-12-31", "entered today",
        )
        self.assertTrue(success, message)

        recent_row = database.get_orders("", "Đơn hàng gần đây")[0]
        created_at = recent_row["created_at"]
        self.assertEqual(recent_row["ngay_mua"], "1999-01-01")

        success, message = database.update_order(
            recent_row["id"], "orders@netflix.test", "Netflix", "Edited",
            120000, "1999-01-02", "2099-12-31", "updated", 0,
        )
        self.assertTrue(success, message)
        connection = self.connect()
        stored_created_at = connection.execute(
            "SELECT created_at FROM don_hang WHERE id = ?", (recent_row["id"],)
        ).fetchone()[0]
        connection.close()

        self.assertEqual(stored_created_at, created_at)


if __name__ == "__main__":
    unittest.main()
