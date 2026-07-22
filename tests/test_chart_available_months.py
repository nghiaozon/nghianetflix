import sqlite3
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

import database


class ChartAvailableMonthsTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "chart_months.db"
        self.db_patch = patch.object(database, "DB_FILE", str(self.db_path))
        self.db_patch.start()
        connection = sqlite3.connect(self.db_path)
        connection.executescript(
            """
            CREATE TABLE don_hang (
                id INTEGER PRIMARY KEY,
                ngay_mua TEXT,
                so_tien REAL,
                ngay_het_han TEXT,
                da_xoa INTEGER DEFAULT 0
            );
            INSERT INTO don_hang (ngay_mua, so_tien, da_xoa) VALUES
                ('2026-07-22', 100, 0),
                ('2025-10-05', 200, 1),
                ('2026-12-20', 300, 0),
                ('not-a-date', 400, 0);
            """
        )
        connection.commit()
        connection.close()

    def tearDown(self):
        self.db_patch.stop()
        self.temp_dir.cleanup()

    def test_current_month_is_first_and_order_months_are_newest_first(self):
        self.assertEqual(
            database.build_available_months(
                date(2026, 8, 1), months_before=0, months_after=0
            ),
            [(2026, 12), (2026, 8), (2026, 7), (2025, 10)],
        )

    def test_current_month_is_included_even_when_no_orders_exist_for_it(self):
        months = database.build_available_months(
            date(2026, 7, 22), months_before=0, months_after=0
        )
        self.assertIn((2026, 7), months)

    def test_rollover_to_august_includes_empty_current_month(self):
        months = database.build_available_months(
            date(2026, 8, 1), months_before=0, months_after=0
        )
        self.assertEqual(months[1:3], [(2026, 8), (2026, 7)])
        august_chart = database.get_chart_data(2026, 8)
        self.assertEqual(sum(august_chart["orders"]), 0)
        self.assertEqual(sum(august_chart["revenue"]), 0)

    def test_rollover_across_years_is_sorted_by_year_then_month(self):
        months = database.build_available_months(
            date(2027, 1, 1), months_before=0, months_after=0
        )
        self.assertEqual(months[:2], [(2027, 1), (2026, 12)])

    def test_default_range_contains_twelve_months_before_and_after(self):
        months = database.build_available_months(date(2026, 7, 22))
        self.assertIn((2025, 7), months)
        self.assertIn((2026, 7), months)
        self.assertIn((2027, 7), months)

    def test_month_and_year_options_cover_the_calendar_and_practical_years(self):
        self.assertEqual(database.build_month_options(), list(range(1, 13)))
        self.assertEqual(
            database.build_year_options(date(2026, 7, 22)),
            [2027, 2026, 2025, 2024],
        )

    def test_selected_period_stats_and_empty_month_use_the_selected_period(self):
        july_stats = database.get_dashboard_stats(2026, 7)
        august_stats = database.get_dashboard_stats(2026, 8)
        self.assertEqual((july_stats["total_orders"], july_stats["total_revenue"]), (1, 100.0))
        self.assertEqual((august_stats["total_orders"], august_stats["total_revenue"]), (0, 0.0))

    def test_february_uses_the_correct_number_of_days_for_leap_years(self):
        self.assertEqual(len(database.get_chart_data(2024, 2)["days"]), 29)
        self.assertEqual(len(database.get_chart_data(2026, 2)["days"]), 28)


if __name__ == "__main__":
    unittest.main()
