import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from dialogs import AccountDialog


class AccountDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    @patch("dialogs.QMessageBox.information")
    @patch("dialogs.database.add_account", return_value=(True, "Đã thêm tài khoản"))
    @patch("dialogs.database.get_account_source_suggestions", return_value=[])
    def test_save_uses_values_entered_in_visible_fields(
        self,
        _suggestions,
        add_account,
        _information,
    ):
        dialog = AccountDialog()
        dialog.email_input.setText("user@example.com")
        dialog.password_input.setText("secret")

        dialog.save_data()

        add_account.assert_called_once()
        args, kwargs = add_account.call_args
        self.assertEqual(args[0], "user@example.com")
        self.assertEqual(args[1], "secret")
        self.assertIn("ghi_chu", kwargs)
        self.assertIn("nguon", kwargs)


if __name__ == "__main__":
    unittest.main()
