import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import database


class AutocompleteDataTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test.db"
        self.db_patch = patch.object(database, "DB_FILE", self.db_path)
        self.db_patch.start()
        conn = sqlite3.connect(self.db_path)
        try:
            conn.executescript("""
                CREATE TABLE tai_khoan (nguon TEXT, trang_thai TEXT);
                CREATE TABLE don_hang (
                    ten_khach_hang TEXT, so_tien FLOAT, da_xoa INTEGER
                );
                INSERT INTO tai_khoan VALUES
                    ('Đại lý A', 'Đang hoạt động'),
                    ('đại lý a', 'Đã bán'),
                    ('Đại lý B', 'Đang hoạt động'),
                    ('Bỏ qua', 'Đã xóa');
                INSERT INTO don_hang VALUES
                    ('Nguyễn Văn A', 49000, 0),
                    ('nguyễn văn a', 49000, 0),
                    ('Phạm Văn Cường', 130000, 0),
                    ('Bỏ qua', 999, 1);
            """)
            conn.commit()
        finally:
            conn.close()

    def tearDown(self):
        self.db_patch.stop()
        self.temp_dir.cleanup()

    def test_sources_are_unique_and_ignore_deleted_rows(self):
        self.assertEqual(
            database.get_account_source_suggestions(),
            ["Đại lý A", "Đại lý B"],
        )

    def test_order_suggestions_are_unique_and_input_friendly(self):
        self.assertEqual(
            database.get_order_customer_suggestions(),
            ["Nguyễn Văn A", "Phạm Văn Cường"],
        )
        self.assertEqual(
            database.get_order_amount_suggestions(),
            ["130000", "49000"],
        )


if __name__ == "__main__":
    unittest.main()
