import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QPushButton, QVBoxLayout

import database
from dialogs import AutocompleteLineEdit


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


class AutocompleteWidgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.dialog = QDialog()
        layout = QVBoxLayout(self.dialog)
        self.input = AutocompleteLineEdit(self.dialog)
        layout.addWidget(self.input)
        self.input.resize(240, 32)
        self.dialog.show()
        self.input.setFocus()
        self.app.processEvents()
        QTest.qWait(5)

    def tearDown(self):
        self.input._popup.hide()
        self.dialog.close()

    def type_text(self, value):
        QTest.keyClicks(self.input, value)
        QTest.qWait(5)
        self.app.processEvents()

    def test_first_suggestion_is_highlighted_and_enter_accepts_it(self):
        self.input.set_suggestions(["523543", "523999", "4523"])
        self.type_text("523")

        self.assertTrue(self.input._popup.isVisible())
        self.assertEqual(self.input._popup.currentIndex().row(), 0)
        self.assertEqual(self.input._current_completion(), "523543")

        QTest.keyClick(self.input, Qt.Key.Key_Return)

        self.assertEqual(self.input.text(), "523543")
        self.assertEqual(self.input.cursorPosition(), len("523543"))
        self.assertFalse(self.input._popup.isVisible())
        self.assertTrue(self.input.hasFocus())

    def test_arrow_keys_move_highlight_without_leaving_the_list(self):
        self.input.set_suggestions(["523543", "53453", "534535"])
        self.type_text("5")

        QTest.keyClick(self.input, Qt.Key.Key_Up)
        self.assertEqual(self.input._popup.currentIndex().row(), 0)

        QTest.keyClick(self.input, Qt.Key.Key_Down)
        self.assertEqual(self.input._popup.currentIndex().row(), 1)
        QTest.keyClick(self.input, Qt.Key.Key_Down)
        self.assertEqual(self.input._popup.currentIndex().row(), 2)
        QTest.keyClick(self.input, Qt.Key.Key_Down)
        self.assertEqual(self.input._popup.currentIndex().row(), 2)

        QTest.keyClick(self.input, Qt.Key.Key_Return)
        self.assertEqual(self.input.text(), "534535")

    def test_escape_closes_popup_without_changing_typed_text(self):
        self.input.set_suggestions(["Khach hang", "Khach quen"])
        self.type_text("Kh")

        QTest.keyClick(self.input, Qt.Key.Key_Escape)

        self.assertEqual(self.input.text(), "Kh")
        self.assertFalse(self.input._popup.isVisible())

    def test_typing_continues_when_a_matching_popup_is_open(self):
        self.input.set_suggestions(["523543", "53453"])

        # The initial ``5`` opens suggestions, but later keystrokes must still
        # be delivered to the editor even when the final value has no match.
        self.type_text("599")

        self.assertEqual(self.input.text(), "599")
        self.assertFalse(self.input._popup.isVisible())
        self.assertTrue(self.input.hasFocus())

    def test_clicking_a_suggestion_accepts_it_and_returns_focus(self):
        self.input.set_suggestions(["Anna", "Annie", "An"])
        self.type_text("an")
        second_item = self.input._model.index(1, 0)

        QTest.mouseClick(
            self.input._popup.viewport(),
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            self.input._popup.visualRect(second_item).center(),
        )

        self.assertEqual(self.input.text(), "Annie")
        self.assertFalse(self.input._popup.isVisible())
        self.assertTrue(self.input.hasFocus())

    def test_matching_is_case_insensitive_and_values_are_deduplicated(self):
        self.input.set_suggestions(["Dai ly A", "dai ly a", "Dai ly B"])
        self.input.setText("DAI")
        QTest.qWait(5)

        self.assertEqual(self.input._model.stringList(), ["Dai ly A", "Dai ly B"])
        self.assertEqual(self.input._popup.currentIndex().row(), 0)

    def test_enter_with_open_popup_does_not_trigger_default_save_button(self):
        dialog = QDialog()
        layout = QVBoxLayout(dialog)
        field = AutocompleteLineEdit(dialog)
        field.set_suggestions(["100000"])
        save_button = QPushButton("Luu", dialog)
        save_button.setDefault(True)
        clicks = []
        save_button.clicked.connect(lambda: clicks.append(True))
        layout.addWidget(field)
        layout.addWidget(save_button)
        dialog.show()
        field.setFocus()
        self.app.processEvents()
        QTest.qWait(5)

        QTest.keyClicks(field, "1")
        QTest.qWait(5)
        QTest.keyClick(field, Qt.Key.Key_Return)

        self.assertEqual(field.text(), "100000")
        self.assertEqual(clicks, [])
        field._popup.hide()
        dialog.close()


if __name__ == "__main__":
    unittest.main()
