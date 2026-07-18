import os
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QContextMenuEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox, QPushButton, QTableWidgetItem, QWidget

from dialogs import CopyableTableWidget
from nghia import MainWindow


class MultiSelectClickScopeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.toggled_rows = []
        self.ensured_rows = []
        self.cleared = []
        self.deleted = []
        self.drag_begins = []
        self.drag_updates = []
        self.drag_ends = []
        self.table = CopyableTableWidget()
        self.table.setColumnCount(4)
        self.table.setRowCount(8)
        for row in range(8):
            for column, text in enumerate((str(row + 1), f"email{row}", f"password{row}", f"note{row}")):
                self.table.setItem(row, column, QTableWidgetItem(text))
        self.table.set_stt_selection_callbacks(
            lambda row, modifiers: self.toggled_rows.append((row, modifiers)),
            self.ensured_rows.append,
            lambda: self.deleted.append(True),
            lambda: len(set(self.toggled_rows + self.ensured_rows)),
            lambda: self.cleared.append(True),
            lambda row, modifiers: self.drag_begins.append((row, modifiers)),
            lambda start, current, modifiers: self.drag_updates.append((start, current, modifiers)),
            lambda start, current, modifiers: self.drag_ends.append((start, current, modifiers)),
        )
        self.table.resize(640, 400)
        self.table.show()
        self.app.processEvents()

    def tearDown(self):
        self.table.close()

    def click_cell(
        self,
        row,
        column,
        button=Qt.MouseButton.LeftButton,
        modifiers=Qt.KeyboardModifier.NoModifier,
    ):
        index = self.table.model().index(row, column)
        point = self.table.visualRect(index).center()
        QTest.mouseClick(self.table.viewport(), button, modifiers, point)
        self.app.processEvents()

    def context_event(self, row, column):
        index = self.table.model().index(row, column)
        point = self.table.visualRect(index).center()
        global_point = self.table.viewport().mapToGlobal(point)
        return QContextMenuEvent(QContextMenuEvent.Reason.Mouse, point, global_point)

    def drag_cells(self, start_row, end_row, column=0, modifiers=Qt.KeyboardModifier.NoModifier):
        start = self.table.visualRect(self.table.model().index(start_row, column)).center()
        QTest.mousePress(self.table.viewport(), Qt.MouseButton.LeftButton, modifiers, start)
        step = 1 if end_row >= start_row else -1
        for row in range(start_row + step, end_row + step, step):
            point = self.table.visualRect(self.table.model().index(row, column)).center()
            QTest.mouseMove(self.table.viewport(), point)
            self.app.processEvents()
        end = self.table.visualRect(self.table.model().index(end_row, column)).center()
        QTest.mouseRelease(self.table.viewport(), Qt.MouseButton.LeftButton, modifiers, end)
        self.app.processEvents()

    def test_only_left_click_on_stt_toggles_business_selection(self):
        self.click_cell(0, 0)
        self.click_cell(1, 1)
        self.click_cell(1, 2)
        self.click_cell(1, 3)
        self.click_cell(2, 0)

        self.assertEqual(
            self.toggled_rows,
            [(0, Qt.KeyboardModifier.NoModifier), (2, Qt.KeyboardModifier.NoModifier)],
        )

    def test_stt_click_passes_windows_ctrl_and_shift_modifiers(self):
        self.click_cell(0, 0, modifiers=Qt.KeyboardModifier.ControlModifier)
        self.click_cell(2, 0, modifiers=Qt.KeyboardModifier.ShiftModifier)

        self.assertEqual(self.toggled_rows[0][0], 0)
        self.assertTrue(self.toggled_rows[0][1] & Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(self.toggled_rows[1][0], 2)
        self.assertTrue(self.toggled_rows[1][1] & Qt.KeyboardModifier.ShiftModifier)

    def test_stt_drag_emits_live_forward_and_reverse_ranges(self):
        self.drag_cells(0, 7)
        self.assertEqual(self.drag_begins[-1][0], 0)
        self.assertEqual(self.drag_updates[-1][:2], (0, 7))
        self.assertEqual(self.drag_ends[-1][:2], (0, 7))

        self.drag_cells(7, 0)
        self.assertEqual(self.drag_begins[-1][0], 7)
        self.assertEqual(self.drag_updates[-1][:2], (7, 0))
        self.assertEqual(self.drag_ends[-1][:2], (7, 0))

    def test_drag_starting_from_email_never_starts_row_drag(self):
        self.drag_cells(0, 5, column=1)

        self.assertEqual(self.drag_begins, [])
        self.assertEqual(self.drag_updates, [])
        self.assertEqual(self.drag_ends, [])
        self.assertEqual(self.toggled_rows, [])

    def test_data_cell_ctrl_c_still_copies_current_cell(self):
        self.click_cell(1, 1)
        QTest.keyClick(self.table, Qt.Key.Key_C, Qt.KeyboardModifier.ControlModifier)

        self.assertEqual(QApplication.clipboard().text(), "email1")
        self.assertEqual(self.toggled_rows, [])

    def test_switching_between_row_and_cell_modes_is_mutually_exclusive(self):
        selected_ids = set()

        def select_row(row, _modifiers):
            selected_ids.clear()
            selected_ids.add(100 + row)
            self.table.set_persistent_selected_rows({row})

        def clear_rows():
            selected_ids.clear()
            self.table.set_persistent_selected_rows(set())

        self.table.set_stt_selection_callbacks(
            select_row,
            self.ensured_rows.append,
            lambda: None,
            lambda: len(selected_ids),
            clear_rows,
        )

        self.click_cell(0, 0)
        self.assertEqual(selected_ids, {100})
        self.assertEqual(self.table.selectedItems(), [])
        self.assertIsNone(self.table.currentItem())

        self.click_cell(1, 1)
        self.assertEqual(selected_ids, set())
        self.assertEqual([(item.row(), item.column()) for item in self.table.selectedItems()], [(1, 1)])
        self.assertEqual((self.table.currentRow(), self.table.currentColumn()), (1, 1))

        self.click_cell(2, 0)
        self.assertEqual(selected_ids, {102})
        self.assertEqual(self.table.selectedItems(), [])
        self.assertIsNone(self.table.currentItem())

    def test_clicking_widget_backed_data_cell_clears_row_mode(self):
        selected_ids = {100}
        widget = QWidget()
        self.table.setCellWidget(1, 3, widget)
        self.table.set_stt_selection_callbacks(
            lambda _row, _modifiers: None,
            self.ensured_rows.append,
            lambda: None,
            lambda: len(selected_ids),
            selected_ids.clear,
        )
        self.table.set_persistent_selected_rows({0})

        QTest.mouseClick(widget, Qt.MouseButton.LeftButton)
        self.app.processEvents()

        self.assertEqual(selected_ids, set())
        self.assertEqual((self.table.currentRow(), self.table.currentColumn()), (1, 3))

    def test_action_widget_does_not_toggle_selection(self):
        clicked = []
        button = QPushButton("Edit")
        button.clicked.connect(lambda: clicked.append(True))
        self.table.setCellWidget(1, 3, button)
        QTest.mouseClick(button, Qt.MouseButton.LeftButton)

        self.assertEqual(clicked, [True])
        self.assertEqual(self.toggled_rows, [])

    def test_right_click_stt_ensures_selection_but_data_cell_does_not(self):
        with patch.object(self.table, "_exec_context_menu", return_value=None):
            self.table.contextMenuEvent(self.context_event(2, 0))
            self.table.contextMenuEvent(self.context_event(1, 1))

        self.assertEqual(self.ensured_rows, [2])
        self.assertEqual(self.toggled_rows, [])

    def test_full_row_highlight_does_not_disable_cell_widgets(self):
        widget = QWidget()
        self.table.setCellWidget(0, 3, widget)
        self.table.set_persistent_selected_rows({0})
        selected_style = widget.styleSheet()
        hover_point = self.table.visualRect(self.table.model().index(0, 1)).center()
        QTest.mouseMove(self.table.viewport(), hover_point)
        self.app.processEvents()

        backgrounds = {
            self.table.item(0, column).background().color().name()
            for column in range(self.table.columnCount())
        }
        self.assertEqual(len(backgrounds), 1)
        self.assertTrue(widget.isEnabled())
        self.assertEqual(widget.styleSheet(), selected_style)

    def test_escape_and_empty_area_clear_business_selection(self):
        QTest.keyClick(self.table, Qt.Key.Key_Escape)
        empty_point = QPoint(10, self.table.viewport().height() - 3)
        self.assertFalse(self.table.indexAt(empty_point).isValid())
        QTest.mouseClick(self.table.viewport(), Qt.MouseButton.LeftButton, pos=empty_point)

        self.assertEqual(len(self.cleared), 2)


class SelectedIdStorageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_selection_state_exists_before_the_first_table_click(self):
        with (
            patch("nghia.database.init_db"),
            patch.object(MainWindow, "init_ui"),
            patch.object(MainWindow, "switch_tab"),
            patch.object(MainWindow, "update_sync_status"),
            patch("nghia.QTimer.singleShot"),
        ):
            window = MainWindow()

        try:
            self.assertEqual(window.selected_account_ids, set())
            self.assertIsNone(window.account_selection_anchor_index)
            self.assertEqual(window._account_drag_base_ids, set())
            self.assertEqual(window.selected_order_ids, set())
            self.assertIsNone(window.order_selection_anchor_index)
            self.assertEqual(window._order_drag_base_ids, set())

            # These are the callbacks invoked by the first click on any
            # non-STT cell. They must be safe before a row was ever selected.
            window.clear_account_selection(update_styles=False)
            window.clear_order_selection(update_styles=False)
        finally:
            window.close()

    def test_account_selection_uses_database_ids_not_stt_numbers(self):
        highlighted = []
        window = SimpleNamespace(
            current_accounts=[{'id': 41}, {'id': 77}, {'id': 105}],
            selected_account_ids=set(),
            account_selection_anchor_index=None,
            acc_table=SimpleNamespace(
                set_persistent_selected_rows=lambda rows: highlighted.append(set(rows))
            ),
        )
        window._apply_account_selection_highlights = (
            lambda: MainWindow._apply_account_selection_highlights(window)
        )

        MainWindow.on_account_stt_click(window, 0)
        MainWindow.on_account_stt_click(window, 2, Qt.KeyboardModifier.ControlModifier)
        MainWindow.on_account_stt_click(window, 0, Qt.KeyboardModifier.ControlModifier)

        self.assertEqual(window.selected_account_ids, {105})
        self.assertEqual(highlighted[-1], {2})

    def test_order_selection_uses_database_ids_not_stt_numbers(self):
        highlighted = []
        window = SimpleNamespace(
            current_orders=[{'id': 501}, {'id': 900}],
            selected_order_ids=set(),
            order_selection_anchor_index=None,
            order_table=SimpleNamespace(
                set_persistent_selected_rows=lambda rows: highlighted.append(set(rows))
            ),
        )
        window._apply_order_selection_highlights = (
            lambda: MainWindow._apply_order_selection_highlights(window)
        )

        MainWindow.on_order_stt_click(window, 0)
        MainWindow.on_order_stt_click(window, 1, Qt.KeyboardModifier.ControlModifier)

        self.assertEqual(window.selected_order_ids, {501, 900})
        self.assertEqual(highlighted[-1], {0, 1})

    def test_plain_click_replaces_selection_and_shift_uses_visible_order(self):
        highlighted = []
        window = SimpleNamespace(
            current_accounts=[{'id': 90}, {'id': 10}, {'id': 70}, {'id': 30}],
            selected_account_ids=set(),
            account_selection_anchor_index=None,
            acc_table=SimpleNamespace(
                set_persistent_selected_rows=lambda rows: highlighted.append(set(rows))
            ),
        )
        window._apply_account_selection_highlights = (
            lambda: MainWindow._apply_account_selection_highlights(window)
        )

        MainWindow.on_account_stt_click(window, 1)
        MainWindow.on_account_stt_click(window, 2)
        self.assertEqual(window.selected_account_ids, {70})
        MainWindow.on_account_stt_click(window, 0)
        MainWindow.on_account_stt_click(window, 3, Qt.KeyboardModifier.ShiftModifier)

        self.assertEqual(window.selected_account_ids, {90, 10, 70, 30})
        self.assertEqual(highlighted[-1], {0, 1, 2, 3})

    def test_ctrl_shift_adds_visible_range_to_existing_selection(self):
        window = SimpleNamespace(
            current_orders=[{'id': 8}, {'id': 3}, {'id': 20}, {'id': 11}, {'id': 6}],
            selected_order_ids={6},
            order_selection_anchor_index=1,
            order_table=SimpleNamespace(set_persistent_selected_rows=lambda _rows: None),
        )
        window._apply_order_selection_highlights = (
            lambda: MainWindow._apply_order_selection_highlights(window)
        )

        modifiers = (
            Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier
        )
        MainWindow.on_order_stt_click(window, 3, modifiers)

        self.assertEqual(window.selected_order_ids, {3, 20, 11, 6})

    def test_right_click_unselected_stt_replaces_old_selection(self):
        window = SimpleNamespace(
            current_accounts=[{'id': 1}, {'id': 2}],
            selected_account_ids={1},
            account_selection_anchor_index=0,
            acc_table=SimpleNamespace(set_persistent_selected_rows=lambda _rows: None),
        )
        window._apply_account_selection_highlights = (
            lambda: MainWindow._apply_account_selection_highlights(window)
        )

        MainWindow.ensure_account_row_selection(window, 1)

        self.assertEqual(window.selected_account_ids, {2})
        self.assertEqual(window.account_selection_anchor_index, 1)

    def test_account_drag_selects_visible_range_live_in_both_directions(self):
        highlighted = []
        window = SimpleNamespace(
            current_accounts=[{'id': value} for value in (80, 10, 70, 20, 60, 30, 50, 40)],
            selected_account_ids={999},
            account_selection_anchor_index=None,
            _account_drag_base_ids=set(),
            acc_table=SimpleNamespace(
                set_persistent_selected_rows=lambda rows: highlighted.append(set(rows))
            ),
        )
        window._apply_account_selection_highlights = (
            lambda: MainWindow._apply_account_selection_highlights(window)
        )

        MainWindow.begin_account_stt_drag(window, 0, Qt.KeyboardModifier.NoModifier)
        MainWindow.update_account_stt_drag(window, 0, 7, Qt.KeyboardModifier.NoModifier)
        self.assertEqual(window.selected_account_ids, {80, 10, 70, 20, 60, 30, 50, 40})
        self.assertEqual(highlighted[-1], set(range(8)))

        MainWindow.begin_account_stt_drag(window, 7, Qt.KeyboardModifier.NoModifier)
        MainWindow.update_account_stt_drag(window, 7, 0, Qt.KeyboardModifier.NoModifier)
        self.assertEqual(window.selected_account_ids, {80, 10, 70, 20, 60, 30, 50, 40})

        MainWindow.begin_account_stt_drag(window, 2, Qt.KeyboardModifier.NoModifier)
        MainWindow.update_account_stt_drag(window, 2, 5, Qt.KeyboardModifier.NoModifier)
        self.assertEqual(window.selected_account_ids, {70, 20, 60, 30})
        self.assertEqual(highlighted[-1], {2, 3, 4, 5})

    def test_ctrl_drag_adds_order_range_to_existing_ids(self):
        highlighted = []
        window = SimpleNamespace(
            current_orders=[{'id': value} for value in (11, 22, 33, 44, 55, 66)],
            selected_order_ids={11, 66},
            order_selection_anchor_index=None,
            _order_drag_base_ids=set(),
            order_table=SimpleNamespace(
                set_persistent_selected_rows=lambda rows: highlighted.append(set(rows))
            ),
        )
        window._apply_order_selection_highlights = (
            lambda: MainWindow._apply_order_selection_highlights(window)
        )

        MainWindow.begin_order_stt_drag(window, 2, Qt.KeyboardModifier.ControlModifier)
        MainWindow.update_order_stt_drag(window, 2, 4, Qt.KeyboardModifier.ControlModifier)

        self.assertEqual(window.selected_order_ids, {11, 33, 44, 55, 66})
        self.assertEqual(highlighted[-1], {0, 2, 3, 4, 5})


class BulkDeleteWorkflowTests(unittest.TestCase):
    def test_account_bulk_delete_uses_one_transaction_call_and_refreshes(self):
        window = Mock()
        window.selected_account_ids = {4, 9, 12}
        with (
            patch("nghia.QMessageBox.question", return_value=QMessageBox.StandardButton.Yes) as confirm,
            patch("nghia.database.delete_accounts_soft_bulk", return_value=True) as bulk_delete,
        ):
            MainWindow.delete_selected_accounts(window)

        confirm.assert_called_once()
        bulk_delete.assert_called_once_with({4, 9, 12})
        window.clear_account_selection.assert_called_once_with(update_styles=False)
        window.refresh_accounts.assert_called_once_with()
        window.refresh_charts.assert_called_once_with()

    def test_order_bulk_delete_refreshes_orders_accounts_and_dashboard(self):
        window = Mock()
        window.selected_order_ids = {22, 31}
        with (
            patch("nghia.QMessageBox.question", return_value=QMessageBox.StandardButton.Yes) as confirm,
            patch("nghia.database.delete_orders_soft_bulk", return_value=True) as bulk_delete,
        ):
            MainWindow.delete_selected_orders(window)

        confirm.assert_called_once()
        bulk_delete.assert_called_once_with({22, 31})
        window.clear_order_selection.assert_called_once_with(update_styles=False)
        window.refresh_orders.assert_called_once_with()
        window.refresh_accounts.assert_called_once_with()
        window.refresh_charts.assert_called_once_with()

    def test_cancel_keeps_selection_and_does_not_delete(self):
        window = Mock()
        window.selected_order_ids = {5, 6}
        with (
            patch("nghia.QMessageBox.question", return_value=QMessageBox.StandardButton.No),
            patch("nghia.database.delete_orders_soft_bulk") as bulk_delete,
        ):
            MainWindow.delete_selected_orders(window)

        self.assertEqual(window.selected_order_ids, {5, 6})
        bulk_delete.assert_not_called()
        window.clear_order_selection.assert_not_called()


if __name__ == "__main__":
    unittest.main()
