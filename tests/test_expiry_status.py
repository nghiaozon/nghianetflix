import sqlite3
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

import database
from expiry_status import (
    STATUS_ACTIVE,
    STATUS_EXPIRED,
    STATUS_UNKNOWN,
    get_status_from_expiry,
    is_expired,
    parse_expiry_date,
)
from google_sheets_service import GoogleSheetsService


TEST_TODAY = date(2026, 7, 22)


class ExpiryStatusRuleTests(unittest.TestCase):
    def test_expiry_day_is_expired_from_midnight(self):
        self.assertEqual(get_status_from_expiry("21/07/2026", today=TEST_TODAY), STATUS_EXPIRED)
        self.assertEqual(get_status_from_expiry("22/07/2026", today=TEST_TODAY), STATUS_EXPIRED)
        self.assertEqual(get_status_from_expiry("23/07/2026", today=TEST_TODAY), STATUS_ACTIVE)
        self.assertTrue(is_expired("2026-07-22", today=TEST_TODAY))

    def test_parsing_and_date_boundaries(self):
        self.assertEqual(parse_expiry_date("29/02/2024"), date(2024, 2, 29))
        self.assertEqual(
            get_status_from_expiry("31/12/2026", today=date(2027, 1, 1)),
            STATUS_EXPIRED,
        )
        self.assertEqual(
            get_status_from_expiry("01/03/2024", today=date(2024, 2, 29)),
            STATUS_ACTIVE,
        )
        self.assertIsNone(parse_expiry_date("31/02/2026"))
        self.assertEqual(get_status_from_expiry(None, today=TEST_TODAY), STATUS_UNKNOWN)
        self.assertEqual(get_status_from_expiry("bad-date", today=TEST_TODAY), STATUS_UNKNOWN)

    def test_google_sheets_uses_the_shared_rule(self):
        with patch("expiry_status.local_today", return_value=TEST_TODAY):
            self.assertEqual(
                GoogleSheetsService._calculate_order_status("22/07/2026"),
                STATUS_EXPIRED,
            )


class ExpiryStatusDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "expiry-status.db"
        self.db_patch = patch.object(database, "DB_FILE", str(self.db_path))
        self.today_patch = patch.object(database, "local_today", return_value=TEST_TODAY)
        self.db_patch.start()
        self.today_patch.start()
        connection = sqlite3.connect(self.db_path)
        connection.executescript(
            """
            CREATE TABLE tai_khoan (
                id INTEGER PRIMARY KEY, email TEXT, mat_khau TEXT,
                ngay_het_han TEXT, trang_thai TEXT, lien_ket TEXT,
                ghi_chu TEXT, nguon TEXT
            );
            CREATE TABLE don_hang (
                id INTEGER PRIMARY KEY, email_tai_khoan TEXT, nen_tang TEXT,
                ten_khach_hang TEXT, so_tien REAL, ngay_mua TEXT,
                ngay_het_han TEXT, ghi_chu TEXT, da_xoa INTEGER DEFAULT 0
            );
            """
        )
        connection.executemany(
            "INSERT INTO tai_khoan VALUES (?, ?, '', ?, 'Đang hoạt động', '', '', '')",
            [(1, "past@test", "2026-07-21"), (2, "today@test", "22/07/2026"),
             (3, "future@test", "2026-07-23"), (4, "bad@test", "not-a-date")],
        )
        connection.executemany(
            "INSERT INTO don_hang(id, email_tai_khoan, nen_tang, ten_khach_hang, ngay_het_han, da_xoa) VALUES (?, ?, 'Netflix', '', ?, 0)",
            [(1, "past@test", "2026-07-21"), (2, "today@test", "22/07/2026"),
             (3, "future@test", "2026-07-23"), (4, "bad@test", "not-a-date")],
        )
        connection.commit()
        connection.close()

    def tearDown(self):
        self.today_patch.stop()
        self.db_patch.stop()
        self.temp_dir.cleanup()

    def test_account_and_order_filters_share_the_expiry_rule(self):
        self.assertEqual([row['id'] for row in database.get_accounts('', STATUS_ACTIVE)], [3])
        self.assertEqual([row['id'] for row in database.get_accounts('', STATUS_EXPIRED)], [1, 2])
        self.assertEqual([row['id'] for row in database.get_orders('', STATUS_ACTIVE)], [3])
        self.assertEqual([row['id'] for row in database.get_orders('', STATUS_EXPIRED)], [1, 2])

    def test_sync_and_dashboard_use_the_same_rule(self):
        database.sync_account_status_by_expire_date()
        connection = sqlite3.connect(self.db_path)
        statuses = dict(connection.execute("SELECT id, trang_thai FROM tai_khoan"))
        connection.close()
        self.assertEqual(statuses, {
            1: STATUS_EXPIRED, 2: STATUS_EXPIRED,
            3: STATUS_ACTIVE, 4: STATUS_UNKNOWN,
        })
        self.assertEqual(database.get_dashboard_stats()['active_warranty'], 1)


if __name__ == '__main__':
    unittest.main()
