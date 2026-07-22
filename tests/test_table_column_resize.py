import json
import os
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, QPoint, Qt
from PySide6.QtGui import QHelpEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QHeaderView, QTableWidgetItem

from dialogs import CopyableTableWidget


ORDER_COLUMNS = [
    {"key": "stt", "width": 70, "min_width": 55},
    {"key": "email", "width": 250, "min_width": 180},
    {"key": "platform", "width": 120, "min_width": 100},
    {"key": "customer_name", "width": 220, "min_width": 140},
    {"key": "amount", "width": 120, "min_width": 110},
]


class TableColumnResizeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.settings_path = os.path.join(self.tempdir.name, "settings.json")
        with open(self.settings_path, "w", encoding="utf-8") as config:
            json.dump({"theme": "dark_neon"}, config)
        self.config_file = patch("dialogs.config_file", return_value=self.settings_path)
        self.config_file.start()
        self.table = CopyableTableWidget()
        self.table.setColumnCount(len(ORDER_COLUMNS))
        self.table.setRowCount(1)
        for column, value in enumerate(("1", "very-long-email-address@example.com", "Netflix", "Nguyễn Văn Khách Hàng Có Tên Rất Dài", "100.000 ₫")):
            self.table.setItem(0, column, QTableWidgetItem(value))
        self.table.configure_resizable_columns("order_table_columns", ORDER_COLUMNS, tooltip_columns=(1, 2, 3))
        self.table.resize(820, 180)
        self.table.show()
        self.app.processEvents()

    def tearDown(self):
        self.table.close()
        self.config_file.stop()
        self.tempdir.cleanup()

    def test_all_columns_are_interactive_and_customer_default_is_wider(self):
        header = self.table.horizontalHeader()
        self.assertEqual(header.sectionResizeMode(3), QHeaderView.ResizeMode.Interactive)
        self.assertGreaterEqual(header.sectionSize(3), 220)
        self.assertGreater(self.table.columnWidth(3), self.table.columnWidth(2))

    def test_resize_clamps_to_per_column_minimum_and_persists(self):
        header = self.table.horizontalHeader()
        header.resizeSection(3, 40)
        self.app.processEvents()
        self.assertEqual(header.sectionSize(3), 140)

        header.resizeSection(3, 280)
        self.app.processEvents()
        with open(self.settings_path, "r", encoding="utf-8") as config:
            saved = json.load(config)
        self.assertEqual(saved["order_table_columns"]["customer_name"], 280)
        self.assertEqual(saved["theme"], "dark_neon")

        restored = CopyableTableWidget()
        restored.setColumnCount(len(ORDER_COLUMNS))
        restored.configure_resizable_columns("order_table_columns", ORDER_COLUMNS)
        self.assertEqual(restored.columnWidth(3), 280)
        restored.close()

    def test_tooltip_is_only_shown_for_truncated_configured_data(self):
        customer_index = self.table.model().index(0, 3)
        customer_point = self.table.visualRect(customer_index).center()
        customer_event = QHelpEvent(
            QEvent.Type.ToolTip,
            customer_point,
            self.table.viewport().mapToGlobal(customer_point),
        )
        with patch("dialogs.QToolTip.showText") as show_tooltip:
            self.table.eventFilter(self.table.viewport(), customer_event)
        show_tooltip.assert_called_once()

        platform_index = self.table.model().index(0, 2)
        platform_point = self.table.visualRect(platform_index).center()
        platform_event = QHelpEvent(
            QEvent.Type.ToolTip,
            platform_point,
            self.table.viewport().mapToGlobal(platform_point),
        )
        with patch("dialogs.QToolTip.showText") as show_tooltip:
            self.table.eventFilter(self.table.viewport(), platform_event)
        show_tooltip.assert_not_called()
