import os
import unittest
from datetime import date, timedelta
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QDate
from PySide6.QtWidgets import QApplication, QDialog

from dialogs import OrderDialog


class OrderDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def make_dialog(self, order_data=None):
        with (
            patch("dialogs.database.get_all_emails", return_value=["user@example.com"]),
            patch("dialogs.database.get_order_customer_suggestions", return_value=[]),
            patch("dialogs.database.get_order_amount_suggestions", return_value=[]),
        ):
            return OrderDialog(order_data=order_data)

    def test_new_order_defaults_to_today_plus_30_days_and_zalo(self):
        dialog = self.make_dialog()
        today = date.today()
        expected_expiry = today + timedelta(days=30)

        self.assertEqual(dialog.purchase_date.date().toPython(), today)
        self.assertEqual(dialog.expiry_date.date().toPython(), expected_expiry)
        self.assertEqual(dialog.platform_combo.currentText(), "Zalo")

    def test_purchase_date_change_recalculates_expiry_across_boundaries(self):
        dialog = self.make_dialog()

        dialog.purchase_date.setDate(QDate(2026, 1, 31))
        self.assertEqual(dialog.expiry_date.date(), QDate(2026, 3, 2))

        dialog.purchase_date.setDate(QDate(2026, 12, 20))
        self.assertEqual(dialog.expiry_date.date(), QDate(2027, 1, 19))

    def test_edit_keeps_saved_dates_and_platform_until_purchase_changes(self):
        dialog = self.make_dialog({
            "id": 7,
            "email_tai_khoan": "user@example.com",
            "nen_tang": "Facebook",
            "ten_khach_hang": "Khách cũ",
            "so_tien": 100000,
            "ngay_mua": "2026-05-10",
            "ngay_het_han": "2026-08-15",
            "ghi_chu": "Gói đặc biệt",
            "so_lan_thong_bao": 2,
        })

        self.assertEqual(dialog.purchase_date.date(), QDate(2026, 5, 10))
        self.assertEqual(dialog.expiry_date.date(), QDate(2026, 8, 15))
        self.assertEqual(dialog.platform_combo.currentText(), "Facebook")

        dialog.purchase_date.setDate(QDate(2026, 6, 1))
        self.assertEqual(dialog.expiry_date.date(), QDate(2026, 7, 1))

    def test_manual_expiry_is_saved_without_success_popup(self):
        dialog = self.make_dialog()
        dialog.amount_input.setText("100000")
        dialog.purchase_date.setDate(QDate(2026, 7, 18))
        dialog.expiry_date.setDate(QDate(2026, 9, 30))

        with (
            patch("dialogs.database.add_order", return_value=(True, "Thành công")) as add_order,
            patch("dialogs.QMessageBox.information") as information,
        ):
            dialog.save_data()

        add_order.assert_called_once_with(
            "user@example.com",
            "Zalo",
            "",
            100000.0,
            "2026-07-18",
            "2026-09-30",
            "",
        )
        information.assert_not_called()
        self.assertEqual(dialog.result(), QDialog.DialogCode.Accepted)

    def test_expiry_before_purchase_is_rejected(self):
        dialog = self.make_dialog()
        dialog.amount_input.setText("100000")
        dialog.purchase_date.setDate(QDate(2026, 7, 18))
        dialog.expiry_date.setDate(QDate(2026, 7, 17))

        with (
            patch("dialogs.database.add_order") as add_order,
            patch("dialogs.QMessageBox.warning") as warning,
        ):
            dialog.save_data()

        add_order.assert_not_called()
        warning.assert_called_once_with(
            dialog,
            "Lỗi Ngày Tháng",
            "Ngày hết hạn không được nhỏ hơn ngày mua!",
        )

    def test_invalid_typed_purchase_date_is_rejected_without_crashing(self):
        dialog = self.make_dialog()
        dialog.amount_input.setText("100000")

        with (
            patch("dialogs.database.add_order") as add_order,
            patch("dialogs.QMessageBox.warning") as warning,
            patch.object(dialog.purchase_date, "hasAcceptableInput", return_value=False),
        ):
            dialog.save_data()

        add_order.assert_not_called()
        warning.assert_called_once_with(
            dialog,
            "Lỗi Ngày Tháng",
            "Ngày mua không hợp lệ. Vui lòng nhập theo định dạng dd/MM/yyyy.",
        )


if __name__ == "__main__":
    unittest.main()
