import sqlite3
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

import database


class ExpirySortingTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "expiry-sorting.db"
        self.db_patch = patch.object(database, "DB_FILE", str(self.db_path))
        self.today_patch = patch.object(database, "local_today", return_value=date(2026, 7, 22))
        self.db_patch.start()
        self.today_patch.start()
        connection = sqlite3.connect(self.db_path)
        connection.executescript(
            """
            CREATE TABLE tai_khoan (
                id INTEGER PRIMARY KEY,
                email TEXT,
                mat_khau TEXT,
                ngay_het_han TEXT,
                trang_thai TEXT,
                lien_ket TEXT,
                ghi_chu TEXT,
                nguon TEXT
            );
            CREATE TABLE don_hang (
                id INTEGER PRIMARY KEY,
                email_tai_khoan TEXT,
                nen_tang TEXT,
                ten_khach_hang TEXT,
                so_tien REAL,
                ngay_mua TEXT,
                ngay_het_han TEXT,
                ngay_tao TEXT,
                ghi_chu TEXT,
                da_xoa INTEGER DEFAULT 0
            );
            """
        )
        connection.commit()
        connection.close()

    def tearDown(self):
        self.today_patch.stop()
        self.db_patch.stop()
        self.temp_dir.cleanup()

    def connect(self):
        return sqlite3.connect(self.db_path)

    def seed_accounts(self):
        rows = [
            (1, "aug26@netflix.test", "2026-08-26", "Đang hoạt động"),
            (2, "jul11@netflix.test", "2026-07-11", "Đang hoạt động"),
            (3, "invalid@netflix.test", "11/07/2026", "Đang hoạt động"),
            (4, "jul07@other.test", "2026-07-07", "Đã hết hạn"),
            (5, "empty@netflix.test", "", "Đang hoạt động"),
            (6, "nextyear@netflix.test", "2027-01-02", "Đang hoạt động"),
            (7, "null@netflix.test", None, "Đang hoạt động"),
            (8, "feb30@netflix.test", "2026-02-30", "Đang hoạt động"),
        ]
        connection = self.connect()
        connection.executemany(
            "INSERT INTO tai_khoan(id, email, ngay_het_han, trang_thai) VALUES (?, ?, ?, ?)",
            rows,
        )
        connection.commit()
        connection.close()

    def seed_orders(self):
        rows = [
            (1, "a@netflix.test", "Netflix", "A", "2026-08-17"),
            (2, "b@netflix.test", "Netflix", "B", "2026-07-11"),
            (3, "c@other.test", "Other", "C", "bad-date"),
            (4, "d@netflix.test", "Netflix", "D", "2026-07-07"),
            (5, "e@netflix.test", "Netflix", "E", None),
            (6, "f@netflix.test", "Netflix", "F", "2027-01-02"),
        ]
        connection = self.connect()
        connection.executemany(
            """INSERT INTO don_hang(
                   id, email_tai_khoan, nen_tang, ten_khach_hang, ngay_het_han, da_xoa
               ) VALUES (?, ?, ?, ?, ?, 0)""",
            rows,
        )
        connection.commit()
        connection.close()

    def test_accounts_sort_real_dates_across_months_and_years_then_invalid_values(self):
        self.seed_accounts()

        rows = database.get_accounts()

        # dd/MM/yyyy is also a supported date format, so it is ordered as a
        # real date rather than being treated as invalid legacy data.
        self.assertEqual([row["id"] for row in rows], [4, 2, 3, 1, 6, 5, 7, 8])

    def test_account_search_and_status_filter_keep_expiry_order(self):
        self.seed_accounts()

        rows = database.get_accounts("netflix", "Đang hoạt động")

        self.assertEqual([row["id"] for row in rows], [1, 6])

    def test_editing_expiry_changes_position_after_refresh_query(self):
        self.seed_accounts()
        connection = self.connect()
        connection.execute(
            "UPDATE tai_khoan SET ngay_het_han = '2026-06-30' WHERE id = 1"
        )
        connection.commit()
        connection.close()

        self.assertEqual(database.get_accounts()[0]["id"], 1)

    def test_orders_sort_before_any_page_slice_and_keep_search_order(self):
        self.seed_orders()

        all_rows = database.get_orders("netflix", "Tất cả")
        first_page = all_rows[:2]
        second_page = all_rows[2:4]

        self.assertEqual([row["id"] for row in all_rows], [4, 2, 1, 6, 5])
        self.assertEqual([row["id"] for row in first_page], [4, 2])
        self.assertEqual([row["id"] for row in second_page], [1, 6])

    def test_order_status_filter_keeps_expiry_ascending(self):
        self.seed_orders()

        rows = database.get_orders("", "Đã hết hạn")

        self.assertEqual(
            [row["ngay_het_han"] for row in rows],
            sorted(row["ngay_het_han"] for row in rows),
        )


if __name__ == "__main__":
    unittest.main()
