import sqlite3
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import database


class FixedDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2026, 7, 22, tzinfo=tz)


class DashboardSoftDeletedOrderTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "dashboard.db"
        self.db_patch = patch.object(database, "DB_FILE", str(self.db_path))
        self.datetime_patch = patch.object(database, "datetime", FixedDateTime)
        self.db_patch.start()
        self.datetime_patch.start()

        connection = sqlite3.connect(self.db_path)
        connection.executescript(
            """
            CREATE TABLE tai_khoan (
                id INTEGER PRIMARY KEY, email TEXT, ma_don_hang TEXT,
                trang_thai TEXT
            );
            CREATE TABLE don_hang (
                id INTEGER PRIMARY KEY, email_tai_khoan TEXT, nen_tang TEXT,
                ten_khach_hang TEXT, so_tien REAL, ngay_mua TEXT,
                ngay_het_han TEXT, da_xoa INTEGER DEFAULT 0,
                deleted_at TIMESTAMP
            );
            INSERT INTO tai_khoan VALUES (1, 'history@example.test', 'DH-0001', 'Da ban');
            """
        )
        connection.executemany(
            """
            INSERT INTO don_hang
                (id, email_tai_khoan, nen_tang, ten_khach_hang, so_tien,
                 ngay_mua, ngay_het_han, da_xoa)
            VALUES (?, 'history@example.test', 'Netflix', ?, ?, ?, '2099-01-01', 0)
            """,
            [
                (order_id, f"Customer {order_id}", order_id * 100,
                 "2026-07-03" if order_id <= 2 else f"2026-07-{order_id + 2:02d}")
                for order_id in range(1, 11)
            ],
        )
        connection.commit()
        connection.close()

    def tearDown(self):
        self.datetime_patch.stop()
        self.db_patch.stop()
        self.temp_dir.cleanup()

    @staticmethod
    def _dashboard_snapshot():
        stats = database.get_dashboard_stats()
        chart = database.get_chart_data(2026, 7)
        july_3 = 2  # zero-based index for 03/07
        return {
            "total_orders": stats["total_orders"],
            "active_warranty": stats["active_warranty"],
            "total_revenue": stats["total_revenue"],
            "month_revenue": stats["month_revenue"],
            "day_3_orders": chart["orders"][july_3],
            "day_3_revenue": chart["revenue"][july_3],
        }

    def test_soft_delete_and_restore_preserve_history_until_permanent_delete(self):
        expected_all_orders = {
            "total_orders": 10,
            "active_warranty": 10,
            "total_revenue": 5500.0,
            "month_revenue": 5500.0,
            "day_3_orders": 2,
            "day_3_revenue": 300.0,
        }
        self.assertEqual(self._dashboard_snapshot(), expected_all_orders)

        self.assertTrue(database.delete_order_soft(1))
        self.assertEqual(self._dashboard_snapshot(), expected_all_orders)

        self.assertTrue(database.restore_order(1))
        self.assertEqual(self._dashboard_snapshot(), expected_all_orders)

        self.assertTrue(database.delete_order_soft(1))
        self.assertEqual(self._dashboard_snapshot(), expected_all_orders)

        self.assertTrue(database.delete_order_permanently(1))
        self.assertEqual(self._dashboard_snapshot(), {
            "total_orders": 9,
            "active_warranty": 9,
            "total_revenue": 5400.0,
            "month_revenue": 5400.0,
            "day_3_orders": 1,
            "day_3_revenue": 200.0,
        })


if __name__ == "__main__":
    unittest.main()
