import os
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from nghia import (
    ACCOUNT_DATABASE_FILTER_MAP,
    ORDER_DATABASE_FILTER_MAP,
    MainWindow,
    normalize_status_filter,
)


class StatusFilterTests(unittest.TestCase):
    def test_display_values_are_normalized_consistently(self):
        self.assertEqual(normalize_status_filter("Tất cả"), "all")
        self.assertEqual(normalize_status_filter("Đang hoạt động"), "active")
        self.assertEqual(normalize_status_filter("Đã hết hạn"), "expired")
        self.assertEqual(normalize_status_filter("Đơn hàng gần đây"), "recent")
        self.assertEqual(ACCOUNT_DATABASE_FILTER_MAP["active"], "Đang hoạt động")
        self.assertEqual(ORDER_DATABASE_FILTER_MAP["active"], "Đang hoạt động")
        self.assertEqual(ORDER_DATABASE_FILTER_MAP["recent"], "Đơn hàng gần đây")

    def test_account_selection_refreshes_once_and_scrolls_to_result_start(self):
        window = Mock()

        MainWindow.on_account_status_filter_changed(window, 1)

        window.refresh_accounts.assert_called_once_with(scroll_to_top=True)

    def test_order_selection_refreshes_once_and_scrolls_to_result_start(self):
        window = Mock()

        MainWindow.on_order_status_filter_changed(window, 2)

        window.refresh_orders.assert_called_once_with(scroll_to_top=True)

    def test_account_search_and_status_are_sent_in_the_same_query(self):
        window = Mock()
        window.acc_search_input.text.return_value = "netflix"
        window.acc_filter_combo.currentText.return_value = "Đang hoạt động"

        with patch("nghia.database.get_accounts", side_effect=RuntimeError("stop")) as query:
            with self.assertRaisesRegex(RuntimeError, "stop"):
                MainWindow.refresh_accounts(window)

        query.assert_called_once_with("netflix", "Đang hoạt động")

    def test_order_search_and_status_are_sent_in_the_same_query(self):
        window = Mock()
        window.order_search_input.text.return_value = "netflix"
        window.order_filter_combo.currentText.return_value = "Đã hết hạn"

        with patch("nghia.database.get_orders", side_effect=RuntimeError("stop")) as query:
            with self.assertRaisesRegex(RuntimeError, "stop"):
                MainWindow.refresh_orders(window)

        query.assert_called_once_with("netflix", "Đã hết hạn")


if __name__ == "__main__":
    unittest.main()
