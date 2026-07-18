# -*- coding: utf-8 -*-

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QTextEdit,
    QDateEdit, QPushButton, QComboBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QMessageBox, QFormLayout, QWidget, QAbstractItemView, QMenu,
    QCompleter, QStyledItemDelegate, QStyle, QStyleOptionViewItem
)
from PySide6.QtCore import QDate, QEvent, Qt, QStringListModel
from PySide6.QtGui import QBrush, QColor, QPalette, QKeySequence
from PySide6.QtWidgets import QApplication
from datetime import date, timedelta
import database


class PersistentRowSelectionDelegate(QStyledItemDelegate):
    """Paint business-selected rows above hover without changing input behavior."""

    def paint(self, painter, option, index):
        table = self.parent()
        if table is not None and index.row() in table._persistent_selected_rows:
            selected_option = QStyleOptionViewItem(option)
            selected_option.state &= ~QStyle.StateFlag.State_MouseOver
            selected_option.state |= QStyle.StateFlag.State_Selected
            super().paint(painter, selected_option, index)
            return
        if table is not None and index.row() == table._hovered_row:
            hover_option = QStyleOptionViewItem(option)
            hover_option.state |= QStyle.StateFlag.State_MouseOver
            super().paint(painter, hover_option, index)
            return
        super().paint(painter, option, index)


class AutocompleteLineEdit(QLineEdit):
    """QLineEdit with explicit, Windows-like popup completion."""

    def set_suggestions(self, suggestions):
        model = QStringListModel(suggestions, self)
        completer = QCompleter(model, self)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchStartsWith)
        completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        completer.setMaxVisibleItems(10)
        self.setCompleter(completer)

    def keyPressEvent(self, event):
        completer = self.completer()
        if (completer is not None
                and event.key() in (Qt.Key.Key_Tab, Qt.Key.Key_Backtab)
                and completer.popup().isVisible()):
            index = completer.popup().currentIndex()
            if not index.isValid() and completer.completionModel().rowCount() > 0:
                index = completer.completionModel().index(0, 0)
            if index.isValid():
                self.setText(str(index.data()))
                completer.popup().hide()
                event.accept()
                return
        super().keyPressEvent(event)


class CopyableTableWidget(QTableWidget):
    """Bảng hỗ trợ chọn/copy từng ô hoặc cả dòng theo định dạng Excel."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self._edit_row_callback = None
        self._delete_row_callback = None
        self._toggle_stt_selection_callback = None
        self._ensure_stt_selection_callback = None
        self._delete_selected_callback = None
        self._selected_count_callback = None
        self._clear_business_selection_callback = None
        self._begin_stt_drag_callback = None
        self._update_stt_drag_callback = None
        self._end_stt_drag_callback = None
        self._persistent_selected_rows = set()
        self._hovered_row = None
        self._stt_drag_active = False
        self._stt_drag_moved = False
        self._stt_drag_start_row = None
        self._stt_drag_current_row = None
        self._stt_drag_modifiers = Qt.KeyboardModifier.NoModifier
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        self.setMouseTracking(True)
        self.setItemDelegate(PersistentRowSelectionDelegate(self))
        self.ApplyDataGridViewTheme()

    def set_row_action_callbacks(self, edit_callback=None, delete_callback=None):
        """Gắn hành động sửa/xóa cho menu chuột phải của từng bảng."""
        self._edit_row_callback = edit_callback
        self._delete_row_callback = delete_callback

    def set_stt_selection_callbacks(
        self,
        toggle_callback=None,
        ensure_callback=None,
        delete_selected_callback=None,
        selected_count_callback=None,
        clear_selection_callback=None,
        begin_drag_callback=None,
        update_drag_callback=None,
        end_drag_callback=None,
    ):
        """Configure multi-row selection, restricted to the STT column only."""
        self._toggle_stt_selection_callback = toggle_callback
        self._ensure_stt_selection_callback = ensure_callback
        self._delete_selected_callback = delete_selected_callback
        self._selected_count_callback = selected_count_callback
        self._clear_business_selection_callback = clear_selection_callback
        self._begin_stt_drag_callback = begin_drag_callback
        self._update_stt_drag_callback = update_drag_callback
        self._end_stt_drag_callback = end_drag_callback

    def set_persistent_selected_rows(self, rows):
        """Highlight complete rows without disabling or covering cell widgets."""
        self._persistent_selected_rows = set(rows)
        self.ApplyDataGridViewTheme()

    def clear_transient_state(self):
        """Clear native focus/hover state without invoking business callbacks."""
        self.clearSelection()
        self.setCurrentItem(None)
        self._set_hovered_row(None)

    def setCellWidget(self, row, column, widget):
        """Track widget-backed cells so their row background follows hover/selected."""
        super().setCellWidget(row, column, widget)
        if widget is not None:
            widget.setProperty("copyable_table_row", row)
            widget.setProperty("copyable_table_column", column)
            widget.setMouseTracking(True)
            widget.installEventFilter(self)

    def eventFilter(self, watched, event):
        row = watched.property("copyable_table_row") if isinstance(watched, QWidget) else None
        if row is not None:
            column = watched.property("copyable_table_column")
            if event.type() == QEvent.Type.Enter:
                self._set_hovered_row(int(row))
            elif event.type() == QEvent.Type.Leave and self._hovered_row == int(row):
                self._set_hovered_row(None)
            elif (
                event.type() == QEvent.Type.MouseButtonPress
                and event.button() == Qt.MouseButton.LeftButton
                and column is not None
                and int(column) != 0
                and self._clear_business_selection_callback is not None
            ):
                self._clear_business_selection_callback()
                self.clearSelection()
                self.setCurrentCell(int(row), int(column))
        return super().eventFilter(watched, event)

    def _set_hovered_row(self, row):
        if row == self._hovered_row:
            return
        self._hovered_row = row
        self.viewport().update()
        self._update_cell_widget_styles()

    def _update_cell_widget_styles(self):
        from app_styles import ThemeManager
        theme = ThemeManager.get_active_theme()
        for row in range(self.rowCount()):
            if row in self._persistent_selected_rows:
                background_css = theme.BUTTON_PRIMARY
                border = theme.BORDER
            elif row == self._hovered_row:
                background_css = theme.TABLE_ROW_HOVER
                border = None
            else:
                background_css = theme.INPUT_BACKGROUND if row % 2 else theme.TABLE_BACKGROUND
                border = None
            for column in range(self.columnCount()):
                cell_widget = self.cellWidget(row, column)
                if cell_widget is not None:
                    if not cell_widget.objectName():
                        cell_widget.setObjectName("DataGridCellWidget")
                    cell_widget.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
                    cell_widget.setStyleSheet(
                        f"QWidget#{cell_widget.objectName()} {{"
                        f"background: {background_css}; color: {theme.TEXT_PRIMARY};"
                        f"border-top: {'1px solid ' + border if border else 'none'};"
                        f"border-bottom: {'1px solid ' + border if border else 'none'};}}"
                    )

    @staticmethod
    def _selected_background_color(theme):
        selected_color_str = theme.BUTTON_PRIMARY_HOVER
        if "qlineargradient" in selected_color_str:
            import re
            gradient_colors = re.findall(r"#[0-9a-fA-F]{6}", selected_color_str)
            selected_color_str = gradient_colors[len(gradient_colors) // 2] if gradient_colors else "#6150F1"
        return QColor(selected_color_str)

    def ApplyDataGridViewTheme(self):
        """Apply theme color scheme dynamically based on active theme."""
        from app_styles import ThemeManager
        theme = ThemeManager.get_active_theme()

        dark = QColor(theme.TABLE_BACKGROUND)
        alternate = QColor(theme.INPUT_BACKGROUND)
        foreground = QColor(theme.TEXT_PRIMARY)
        header_background = QColor(theme.TABLE_HEADER)
        header_foreground = QColor(theme.TEXT_SECONDARY)
        
        selected = self._selected_background_color(theme)

        palette = self.palette()
        for group in (QPalette.ColorGroup.Active,
                      QPalette.ColorGroup.Inactive,
                      QPalette.ColorGroup.Disabled):
            palette.setColor(group, QPalette.ColorRole.Window, dark)
            palette.setColor(group, QPalette.ColorRole.Base, dark)
            palette.setColor(group, QPalette.ColorRole.AlternateBase, alternate)
            palette.setColor(group, QPalette.ColorRole.Text, foreground)
            palette.setColor(group, QPalette.ColorRole.WindowText, foreground)
            palette.setColor(group, QPalette.ColorRole.Highlight, selected)
            palette.setColor(group, QPalette.ColorRole.HighlightedText, QColor("#FFFFFF") if theme.BACKGROUND != "#F1F5F9" else QColor("#000000"))
        self.setPalette(palette)
        self.viewport().setPalette(palette)
        self.viewport().setAutoFillBackground(True)
        self.setAlternatingRowColors(True)
        self.setShowGrid(False)
        self.setWordWrap(False)
        self.verticalHeader().setVisible(False)
        self.horizontalHeader().setMinimumSectionSize(80)

        # Explicitly colour all current cells (including cells underneath custom
        # button/badge widgets). Preserve deliberately coloured status text.
        for row in range(self.rowCount()):
            is_persistently_selected = row in self._persistent_selected_rows
            row_background = selected if is_persistently_selected else (alternate if row % 2 else dark)
            for column in range(self.columnCount()):
                item = self.item(row, column)
                if item is None:
                    item = QTableWidgetItem("")
                    self.setItem(row, column, item)
                item.setBackground(QBrush(row_background))
                if item.foreground().style() == Qt.BrushStyle.NoBrush:
                    item.setForeground(QBrush(foreground))

        self._update_cell_widget_styles()

        header_palette = self.horizontalHeader().palette()
        header_palette.setColor(QPalette.ColorRole.Button, header_background)
        header_palette.setColor(QPalette.ColorRole.Window, header_background)
        header_palette.setColor(QPalette.ColorRole.ButtonText, header_foreground)
        header_palette.setColor(QPalette.ColorRole.WindowText, header_foreground)
        self.horizontalHeader().setPalette(header_palette)
        self.verticalHeader().setPalette(header_palette)

    def keyPressEvent(self, event):
        """Xử lý phím Ctrl+C để copy dữ liệu bảng."""
        if event.key() == Qt.Key.Key_Escape and self._clear_business_selection_callback is not None:
            self._clear_business_selection_callback()
            self.clearSelection()
            self.setCurrentItem(None)
            event.accept()
        elif event.matches(QKeySequence.StandardKey.Copy):
            self.copy_to_clipboard()
            event.accept()
        else:
            super().keyPressEvent(event)

    def mousePressEvent(self, event):
        """Only a direct left click in column 0 may toggle a business row selection."""
        index = self.indexAt(event.position().toPoint())
        if (
            event.button() == Qt.MouseButton.LeftButton
            and index.isValid()
            and index.column() == 0
            and self._toggle_stt_selection_callback is not None
        ):
            # Row mode and native cell mode are mutually exclusive. Remove the
            # focused/selected data cell before applying the STT row selection.
            self.clearSelection()
            self.setCurrentItem(None)
            self._stt_drag_active = True
            self._stt_drag_moved = False
            self._stt_drag_start_row = index.row()
            self._stt_drag_current_row = index.row()
            self._stt_drag_modifiers = event.modifiers()
            if self._begin_stt_drag_callback is not None:
                self._begin_stt_drag_callback(index.row(), event.modifiers())
            event.accept()
            return
        if (
            event.button() == Qt.MouseButton.LeftButton
            and index.isValid()
            and index.column() != 0
            and self._clear_business_selection_callback is not None
        ):
            # Let QTableWidget select/focus the clicked data cell only after the
            # business row IDs and persistent row highlight have been cleared.
            self._clear_business_selection_callback()
            self.clearSelection()
            self.setCurrentItem(None)
            super().mousePressEvent(event)
            return
        if (
            event.button() == Qt.MouseButton.LeftButton
            and not index.isValid()
            and self._clear_business_selection_callback is not None
        ):
            self._clear_business_selection_callback()
            self.clearSelection()
            self.setCurrentItem(None)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        index = self.indexAt(event.position().toPoint())
        if self._stt_drag_active and event.buttons() & Qt.MouseButton.LeftButton:
            current_row = index.row() if index.isValid() else self._drag_edge_row(event.position().toPoint().y())
            if current_row is not None:
                self._set_hovered_row(current_row)
                if current_row != self._stt_drag_current_row:
                    self._stt_drag_moved = True
                    self._stt_drag_current_row = current_row
                    if self._update_stt_drag_callback is not None:
                        self._update_stt_drag_callback(
                            self._stt_drag_start_row,
                            current_row,
                            self._stt_drag_modifiers,
                        )
            event.accept()
            return
        self._set_hovered_row(index.row() if index.isValid() else None)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._stt_drag_active:
            start_row = self._stt_drag_start_row
            current_row = self._stt_drag_current_row
            modifiers = self._stt_drag_modifiers
            moved = self._stt_drag_moved
            self._reset_stt_drag_state()
            if moved:
                if self._end_stt_drag_callback is not None:
                    self._end_stt_drag_callback(start_row, current_row, modifiers)
            else:
                self._toggle_stt_selection_callback(start_row, modifiers)
                if self._end_stt_drag_callback is not None:
                    self._end_stt_drag_callback(start_row, start_row, modifiers)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _drag_edge_row(self, y_position):
        if self.rowCount() == 0:
            return None
        if y_position < 0:
            return 0
        if y_position >= self.viewport().height():
            return self.rowCount() - 1
        return None

    def _reset_stt_drag_state(self):
        self._stt_drag_active = False
        self._stt_drag_moved = False
        self._stt_drag_start_row = None
        self._stt_drag_current_row = None
        self._stt_drag_modifiers = Qt.KeyboardModifier.NoModifier

    def leaveEvent(self, event):
        self._set_hovered_row(None)
        super().leaveEvent(event)

    def _exec_context_menu(self, menu, event):
        """Open a native menu; kept separate so offscreen interaction tests do not block."""
        return menu.exec(event.globalPos())

    def contextMenuEvent(self, event):
        """Hiện menu copy tại đúng ô được bấm chuột phải."""
        item = self.itemAt(event.pos())
        if item is None:
            return

        clicked_row = item.row()
        clicked_column = item.column()

        if clicked_column == 0 and self._ensure_stt_selection_callback is not None:
            self.clearSelection()
            self.setCurrentItem(None)
            self._ensure_stt_selection_callback(clicked_row)
            menu = QMenu(self)
            count = self._selected_count_callback() if self._selected_count_callback else 0
            delete_selected_action = menu.addAction(f"Xóa {count} mục đã chọn")
            delete_selected_action.setEnabled(count > 0 and self._delete_selected_callback is not None)
            selected_action = self._exec_context_menu(menu, event)
            if selected_action == delete_selected_action and self._delete_selected_callback is not None:
                self._delete_selected_callback()
            return

        if self._clear_business_selection_callback is not None:
            self._clear_business_selection_callback()
        self.clearSelection()
        self.setCurrentCell(clicked_row, clicked_column)

        menu = QMenu(self)
        edit_action = menu.addAction("Chỉnh sửa")
        delete_action = menu.addAction("Xóa")
        edit_action.setEnabled(self._edit_row_callback is not None)
        delete_action.setEnabled(self._delete_row_callback is not None)
        menu.addSeparator()
        copy_cell_action = menu.addAction("Copy ô này")
        copy_row_action = menu.addAction("Copy cả dòng")
        selected_action = self._exec_context_menu(menu, event)

        if selected_action == edit_action and self._edit_row_callback is not None:
            self._edit_row_callback(clicked_row)
        elif selected_action == delete_action and self._delete_row_callback is not None:
            self._delete_row_callback(clicked_row)
        elif selected_action == copy_cell_action:
            self.copy_cell(clicked_row, clicked_column)
        elif selected_action == copy_row_action:
            self.copy_row(clicked_row)

    def _cell_text(self, row, column):
        """Lấy giá trị gốc của ô, không phụ thuộc text đang bị elide bằng dấu ba chấm."""
        item = self.item(row, column)
        if item is not None and item.text():
            return item.text()

        # Một số cột dùng widget (badge/nút) thay vì QTableWidgetItem.
        cell_widget = self.cellWidget(row, column)
        if cell_widget is not None:
            label = cell_widget.findChild(QLabel)
            if label is not None:
                return label.text()
            button = cell_widget.findChild(QPushButton)
            if button is not None:
                return button.text()
        return ""

    def copy_cell(self, row, column):
        QApplication.clipboard().setText(self._cell_text(row, column))

    def copy_row(self, row):
        """Copy toàn bộ cột dữ liệu của một dòng, bỏ cột Thao tác."""
        last_data_column = max(0, self.columnCount() - 1)
        values = [self._cell_text(row, column) for column in range(last_data_column)]
        QApplication.clipboard().setText("\t".join(values))

    def copy_to_clipboard(self):
        """Copy dữ liệu từ các ô được chọn vào clipboard với định dạng Excel."""
        selected_ranges = self.selectedRanges()
        if not selected_ranges:
            return
        
        # Lấy min/max của row và col từ các ô được chọn
        min_row = min(r.topRow() for r in selected_ranges)
        max_row = max(r.bottomRow() for r in selected_ranges)
        min_col = min(r.leftColumn() for r in selected_ranges)
        max_col = max(r.rightColumn() for r in selected_ranges)
        
        # Bỏ qua cột "Thao tác" (thường là cột cuối cùng)
        max_col = min(max_col, self.columnCount() - 2)
        
        # Tạo dữ liệu 2D array
        rows = []
        for row_idx in range(min_row, max_row + 1):
            cols = []
            for col_idx in range(min_col, max_col + 1):
                cols.append(self._cell_text(row_idx, col_idx))
            if any(cols):  # Chỉ thêm dòng nếu có dữ liệu
                rows.append("\t".join(cols))
        
        # Ghép các dòng bằng newline
        clipboard_text = "\n".join(rows)
        
        # Copy vào clipboard
        clipboard = QApplication.clipboard()
        clipboard.setText(clipboard_text)



class AccountDialog(QDialog):
    """Hộp thoại Thêm hoặc Sửa Tài khoản."""
    def __init__(self, parent=None, account_data=None):
        super().__init__(parent)
        self.account_data = account_data  # Nếu có dữ liệu tức là chế độ Sửa (Edit)
        self.is_edit = account_data is not None
        
        self.setWindowTitle("Sửa Tài Khoản" if self.is_edit else "Thêm Tài Khoản")
        self.setMinimumWidth(500)
        self.setModal(True)
        
        self.init_ui()
        if self.is_edit:
            self.load_data()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(18)
        
        title_label = QLabel("THÔNG TIN TÀI KHOẢN")
        title_label.setProperty("class", "DialogTitle")
        title_label.setStyleSheet("font-size: 20px; font-weight: 700; margin-bottom: 8px;")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_label)
        
        form_layout = QFormLayout()
        form_layout.setHorizontalSpacing(20)
        form_layout.setVerticalSpacing(14)
        form_layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        
        # Email
        self.email_input = QLineEdit()
        self.email_input.setPlaceholderText("example@gmail.com")
        form_layout.addRow("Email (*):", self.email_input)
        
        # Mật khẩu
        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("Mật khẩu")
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        form_layout.addRow("Mật khẩu (*):", self.password_input)
        
        # Ngày hết hạn
        self.expiry_date = QDateEdit()
        self.expiry_date.setCalendarPopup(True)
        self.expiry_date.setDisplayFormat("dd/MM/yyyy")
        if not self.is_edit:
            self.expiry_date.setDate(QDate.currentDate().addDays(30))
        form_layout.addRow("Ngày hết hạn (*):", self.expiry_date)
        
        # Nguồn
        self.source_input = AutocompleteLineEdit()
        self.source_input.setPlaceholderText("Nhập nguồn tài khoản...")
        self.source_input.set_suggestions(database.get_account_source_suggestions())
        form_layout.addRow("Nguồn:", self.source_input)
        
        # Trạng thái (Chỉ hiển thị khi Sửa)
        if self.is_edit:
            self.status_combo = QComboBox()
            self.status_combo.addItems(["Đang hoạt động", "Đã bán", "Hết hạn"])
            form_layout.addRow("Trạng thái:", self.status_combo)
            
        # Ghi chú
        self.note_input = QTextEdit()
        self.note_input.setPlaceholderText("Ghi chú thêm về tài khoản...")
        self.note_input.setMaximumHeight(80)
        form_layout.addRow("Ghi chú:", self.note_input)
        
        layout.addLayout(form_layout)
        
        # Nút hành động
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(15)
        
        self.cancel_btn = QPushButton("Hủy")
        self.cancel_btn.setProperty("class", "SecondaryButton")
        self.cancel_btn.clicked.connect(self.reject)
        
        self.save_btn = QPushButton("Lưu")
        self.save_btn.setProperty("class", "PrimaryButton")
        self.save_btn.setDefault(True)
        self.save_btn.setAutoDefault(True)
        self.save_btn.clicked.connect(self.save_data)
        
        btn_layout.addWidget(self.cancel_btn)
        btn_layout.addWidget(self.save_btn)
        layout.addLayout(btn_layout)

    def load_data(self):
        """Đổ dữ liệu cũ vào các trường khi ở chế độ Edit."""
        self.email_input.setText(self.account_data.get('email', ''))
        self.password_input.setText(self.account_data.get('mat_khau', ''))
        
        # Load ngày
        expiry_str = self.account_data.get('ngay_het_han', '')
        if expiry_str:
            qdate = QDate.fromString(expiry_str, "yyyy-MM-dd")
            if qdate.isValid():
                self.expiry_date.setDate(qdate)
                
        self.source_input.setText(self.account_data.get('nguon', 'Khách hàng'))
        self.note_input.setPlainText(self.account_data.get('ghi_chu', ''))
        
        if hasattr(self, 'status_combo'):
            status = self.account_data.get('trang_thai', 'Đang hoạt động')
            idx = self.status_combo.findText(status)
            if idx >= 0:
                self.status_combo.setCurrentIndex(idx)

    def save_data(self):
        """Xử lý lưu dữ liệu và kiểm tra hợp lệ."""
        email = self.email_input.text().strip()
        password = self.password_input.text().strip()
        expiry_qdate = self.expiry_date.date()
        expiry_str = expiry_qdate.toString("yyyy-MM-dd")
        source = self.source_input.text().strip() or "Khách hàng"
        notes = self.note_input.toPlainText().strip()
        
        if not email or not password:
            QMessageBox.warning(self, "Lỗi Nhập Liệu", "Vui lòng nhập đầy đủ Email và Mật khẩu!")
            return
            
        if self.is_edit:
            status = self.status_combo.currentText()
            success, msg = database.update_account(
                self.account_data['id'],
                email,
                password,
                expiry_str,
                lien_ket=self.account_data.get('lien_ket', ''),
                ghi_chu=notes,
                nguon=source,
                thong_bao=self.account_data.get('thong_bao', '0/1'),
                trang_thai=status,
            )
        else:
            success, msg = database.add_account(
                email,
                password,
                expiry_str,
                ghi_chu=notes,
                nguon=source,
            )
            
        if success:
            if self.is_edit:
                QMessageBox.information(self, "Thành Công", msg)
            self.accept()
        else:
            QMessageBox.critical(self, "Thất Bại", msg)


class OrderDialog(QDialog):
    """Hộp thoại Thêm hoặc Sửa Đơn hàng."""
    def __init__(self, parent=None, order_data=None):
        super().__init__(parent)
        self.order_data = order_data
        self.is_edit = order_data is not None
        
        self.setWindowTitle("Sửa Đơn Hàng" if self.is_edit else "Thêm Đơn Hàng")
        self.setMinimumWidth(520)
        self.setModal(True)
        
        self.init_ui()
        if self.is_edit:
            self.load_data()
        # Chỉ bắt đầu tự tính sau khi dữ liệu cũ đã được nạp đầy đủ. Nhờ đó,
        # mở đơn hàng để sửa không làm thay đổi ngày hết hạn đã lưu.
        self.purchase_date.dateChanged.connect(self.on_purchase_date_changed)

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(18)
        
        title_label = QLabel("THÔNG TIN ĐƠN HÀNG")
        title_label.setProperty("class", "DialogTitle")
        title_label.setStyleSheet("font-size: 20px; font-weight: 700; margin-bottom: 8px;")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_label)
        
        form_layout = QFormLayout()
        form_layout.setHorizontalSpacing(20)
        form_layout.setVerticalSpacing(14)
        form_layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        
        # Chọn tài khoản (Email) - chỉ cho phép chọn từ danh sách đã tạo
        self.email_combo = QComboBox()
        self.email_combo.setEditable(False)

        # Đổ danh sách tất cả email tài khoản (trừ đã xóa) vào dropdown để người bán chọn
        available_emails = database.get_all_emails()
        if available_emails:
            self.email_combo.addItems(available_emails)
        else:
            # Nếu không có tài khoản rảnh, hiển thị thông báo trong dropdown và khóa lại
            self.email_combo.addItem("Không có tài khoản rảnh")
            self.email_combo.setEnabled(False)

        form_layout.addRow("Tài khoản Email (*):", self.email_combo)
        
        # Nền tảng
        self.platform_combo = QComboBox()
        self.platform_combo.setEditable(False)
        self.platform_combo.addItems(["Tiktok", "Zalo", "Facebook", "Khác..."])
        if not self.is_edit:
            self.platform_combo.setCurrentText("Zalo")
        form_layout.addRow("Nền tảng (*):", self.platform_combo)
        
        # Tên khách hàng
        self.customer_input = AutocompleteLineEdit()
        self.customer_input.setPlaceholderText("Nguyễn Văn A")
        self.customer_input.set_suggestions(database.get_order_customer_suggestions())
        form_layout.addRow("Tên khách hàng:", self.customer_input)
        
        # Số tiền
        self.amount_input = AutocompleteLineEdit()
        self.amount_input.setPlaceholderText("Ví dụ: 100000")
        self.amount_input.set_suggestions(database.get_order_amount_suggestions())
        form_layout.addRow("Số tiền (VND) (*):", self.amount_input)
        
        # Ngày mua (ngày tạo đơn/ngày khách mua)
        self.purchase_date = QDateEdit()
        self.purchase_date.setCalendarPopup(True)
        self.purchase_date.setDisplayFormat("dd/MM/yyyy")
        today = date.today()
        purchase_qdate = QDate(today.year, today.month, today.day)
        self.purchase_date.setDate(purchase_qdate)
        form_layout.addRow("Ngày mua (*):", self.purchase_date)
            
        # Ngày hết hạn
        self.expiry_date = QDateEdit()
        self.expiry_date.setCalendarPopup(True)
        self.expiry_date.setDisplayFormat("dd/MM/yyyy")
        if not self.is_edit:
            self.expiry_date.setDate(self.calculate_expiry_date(purchase_qdate))
        form_layout.addRow("Ngày hết hạn (*):", self.expiry_date)
        
        # Ghi chú
        self.note_input = QTextEdit()
        self.note_input.setPlaceholderText("Thông tin bảo hành, tên slot, ghi chú bán hàng...")
        self.note_input.setMaximumHeight(80)
        form_layout.addRow("Ghi chú:", self.note_input)
        
        layout.addLayout(form_layout)
        
        # Nút hành động
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(15)
        
        self.cancel_btn = QPushButton("Hủy")
        self.cancel_btn.setProperty("class", "SecondaryButton")
        self.cancel_btn.clicked.connect(self.reject)
        
        self.save_btn = QPushButton("Lưu")
        self.save_btn.setProperty("class", "PrimaryButton")
        self.save_btn.setDefault(True)
        self.save_btn.setAutoDefault(True)
        self.save_btn.clicked.connect(self.save_data)
        
        btn_layout.addWidget(self.cancel_btn)
        btn_layout.addWidget(self.save_btn)
        layout.addLayout(btn_layout)

    @staticmethod
    def calculate_expiry_date(purchase_qdate):
        """Tính ngày hết hạn bằng phép cộng ngày thực tế, không xử lý chuỗi."""
        if not purchase_qdate.isValid():
            return QDate()
        purchase_python_date = purchase_qdate.toPython()
        expiry_python_date = purchase_python_date + timedelta(days=30)
        return QDate(
            expiry_python_date.year,
            expiry_python_date.month,
            expiry_python_date.day,
        )

    def on_purchase_date_changed(self, purchase_qdate):
        """Tự tính lại hạn 30 ngày khi người dùng thay đổi ngày mua."""
        calculated_expiry = self.calculate_expiry_date(purchase_qdate)
        if calculated_expiry.isValid():
            self.expiry_date.setDate(calculated_expiry)

    def _validated_date(self, date_input, field_label):
        """Đọc ngày theo đúng định dạng hiển thị và báo lỗi thân thiện."""
        date_format = date_input.displayFormat()
        entered_text = date_input.lineEdit().text().strip()
        parsed_date = QDate.fromString(entered_text, date_format)
        if (not date_input.hasAcceptableInput()
                or not parsed_date.isValid()
                or parsed_date.toString(date_format) != entered_text):
            QMessageBox.warning(
                self,
                "Lỗi Ngày Tháng",
                f"{field_label} không hợp lệ. Vui lòng nhập theo định dạng dd/MM/yyyy.",
            )
            return None
        return parsed_date

    def load_data(self):
        """Đổ dữ liệu cũ vào các trường khi ở chế độ Edit."""
        email = self.order_data.get('email_tai_khoan', '')
        # Nếu email chưa nằm trong combo box, ta add thêm vào để chọn
        if self.email_combo.findText(email) < 0 and email:
            # Nếu trước đó combo bị khóa vì không có tài khoản rảnh, bật lại và xóa placeholder
            if not self.email_combo.isEnabled():
                self.email_combo.clear()
                self.email_combo.setEnabled(True)
            self.email_combo.addItem(email)
        self.email_combo.setCurrentText(email)
        
        platform = self.order_data.get('nen_tang', 'Netflix')
        if self.platform_combo.findText(platform) < 0 and platform:
            self.platform_combo.addItem(platform)
        self.platform_combo.setCurrentText(platform)
        
        self.customer_input.setText(self.order_data.get('ten_khach_hang', ''))
        
        # Load số tiền
        so_tien = self.order_data.get('so_tien', 0.0)
        # Bỏ phần .0 nếu là số nguyên
        if so_tien == int(so_tien):
            self.amount_input.setText(str(int(so_tien)))
        else:
            self.amount_input.setText(str(so_tien))
            
        # Load ngày mua đã lưu; không ghi đè bằng ngày hiện tại khi sửa.
        purchase_str = self.order_data.get('ngay_mua', '')
        if purchase_str:
            qdate = QDate.fromString(purchase_str, "yyyy-MM-dd")
            if qdate.isValid():
                self.purchase_date.setDate(qdate)

        # Load ngày hết hạn
        expiry_str = self.order_data.get('ngay_het_han', '')
        if expiry_str:
            qdate = QDate.fromString(expiry_str, "yyyy-MM-dd")
            if qdate.isValid():
                self.expiry_date.setDate(qdate)
                
        self.note_input.setPlainText(self.order_data.get('ghi_chu', ''))
        
    def save_data(self):
        """Lưu dữ liệu đơn hàng và cập nhật database."""
        email = self.email_combo.currentText().strip()
        platform = self.platform_combo.currentText().strip()
        customer = self.customer_input.text().strip()
        amount_str = self.amount_input.text().strip()
        notes = self.note_input.toPlainText().strip()
        
        # Nếu combo bị vô hiệu (không có tài khoản rảnh) hoặc email không hợp lệ
        if not self.email_combo.isEnabled() or not email or not platform or not amount_str:
            QMessageBox.warning(self, "Lỗi Nhập Liệu", "Vui lòng chọn Email tài khoản, Nền tảng và Số tiền!")
            return

        purchase_qdate = self._validated_date(self.purchase_date, "Ngày mua")
        if purchase_qdate is None:
            return
        expiry_qdate = self._validated_date(self.expiry_date, "Ngày hết hạn")
        if expiry_qdate is None:
            return
        if expiry_qdate < purchase_qdate:
            QMessageBox.warning(
                self,
                "Lỗi Ngày Tháng",
                "Ngày hết hạn không được nhỏ hơn ngày mua!",
            )
            return

        purchase_str = purchase_qdate.toString("yyyy-MM-dd")
        expiry_str = expiry_qdate.toString("yyyy-MM-dd")
            
        try:
            # Làm sạch định dạng tiền trước khi parse (ví dụ xóa "đ", "VND", chấm, phẩy...)
            clean_amount = amount_str.replace("đ", "").replace("VND", "").replace("vnd", "").replace(".", "").replace(",", "").strip()
            amount = float(clean_amount)
        except ValueError:
            QMessageBox.warning(self, "Lỗi Định Dạng", "Số tiền phải là một con số hợp lệ!")
            return
            
        if self.is_edit:
            # The notification count is managed by the reminder workflow, not by
            # the order editor. Preserve it when other order fields are updated.
            notify_count = self.order_data.get('so_lan_thong_bao', 0)
            success, msg = database.update_order(
                self.order_data['id'], email, platform, customer, amount, purchase_str, expiry_str, notes, notify_count
            )
        else:
            success, msg = database.add_order(
                email, platform, customer, amount, purchase_str, expiry_str, notes
            )
            
        if success:
            self.accept()
        else:
            QMessageBox.critical(self, "Thất Bại", msg)


class TrashBinDialog(QDialog):
    """Hộp thoại Thùng rác chứa Tài khoản và Đơn hàng đã xóa."""
    ACTION_COLUMN_WIDTH = 260
    ACTION_ROW_HEIGHT = 52
    ACTION_BUTTON_HEIGHT = 36

    def __init__(self, parent=None, is_account_mode=True):
        super().__init__(parent)
        self.is_account_mode = is_account_mode  # True: Tài khoản, False: Đơn hàng
        
        self.setWindowTitle("Thùng Rác - Tài Khoản" if self.is_account_mode else "Thùng Rác - Đơn Hàng")
        self.resize(900, 450)
        self.setMinimumWidth(800)
        self.setModal(True)
        
        self.init_ui()
        self.refresh_table()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(14)
        
        title_label = QLabel("THÙNG RÁC - ĐÃ XÓA MỀM")
        title_label.setProperty("class", "DialogTitle")
        title_label.setStyleSheet("font-size: 20px; font-weight: 700; margin-bottom: 8px;")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_label)
        
        # Bảng hiển thị
        self.table = CopyableTableWidget()
        self.table.setObjectName("TrashTable")
        # Chừa thêm không gian thực cho widget ở cột Thao tác (theme chung dùng 10px).
        self.table.setStyleSheet(
            "QTableWidget#TrashTable::item { padding: 0 5px; }"
        )
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        
        if self.is_account_mode:
            self.headers = ["ID", "Email", "Mật khẩu", "Ngày hết hạn", "Ghi chú", "Thao tác"]
        else:
            self.headers = ["Mã ĐH", "Tài khoản", "Nền tảng", "Tên khách hàng", "Số tiền", "Thao tác"]
            
        self.table.setColumnCount(len(self.headers))
        self.table.setHorizontalHeaderLabels(self.headers)
        
        # Co dãn cột
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        if self.is_account_mode:
            header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        else:
            header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
            header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)

        # Cột thao tác luôn đủ chỗ cho hai nút và không bị co khi dialog đổi cỡ.
        action_column = len(self.headers) - 1
        header.setSectionResizeMode(action_column, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(action_column, self.ACTION_COLUMN_WIDTH)
        self.table.verticalHeader().setMinimumSectionSize(self.ACTION_ROW_HEIGHT)
        self.table.verticalHeader().setDefaultSectionSize(self.ACTION_ROW_HEIGHT)
            
        layout.addWidget(self.table)
        self.table.ApplyDataGridViewTheme()
        
        # Hướng dẫn bên dưới
        help_label = QLabel("(*) Khôi phục sẽ đưa dữ liệu quay lại giao diện chính. Xóa vĩnh viễn không thể hoàn tác.")
        help_label.setStyleSheet("font-style:italic; color:#8391A7; font-size:11px;")
        layout.addWidget(help_label)
        
        # Nút Đóng
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.close_btn = QPushButton("Đóng")
        self.close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(self.close_btn)
        layout.addLayout(btn_layout)

    def refresh_table(self):
        """Tải dữ liệu từ thùng rác lên bảng."""
        self.table.setRowCount(0)
        
        if self.is_account_mode:
            data = database.get_deleted_accounts()
            self.table.setRowCount(len(data))
            for row_idx, row in enumerate(data):
                self.table.setItem(row_idx, 0, QTableWidgetItem(str(row['id'])))
                self.table.setItem(row_idx, 1, QTableWidgetItem(row['email']))
                self.table.setItem(row_idx, 2, QTableWidgetItem(row['mat_khau']))
                
                # Format ngày
                exp_date = row['ngay_het_han']
                try:
                    qdate = QDate.fromString(exp_date, "yyyy-MM-dd")
                    exp_date_display = qdate.toString("dd/MM/yyyy")
                except:
                    exp_date_display = exp_date
                self.table.setItem(row_idx, 3, QTableWidgetItem(exp_date_display))
                self.table.setItem(row_idx, 4, QTableWidgetItem(row['ghi_chu'] or ""))
                
                # Buttons
                self.table.setCellWidget(row_idx, 5, self.create_action_widget(row['id']))

        else:
            data = database.get_deleted_orders()
            self.table.setRowCount(len(data))
            for row_idx, row in enumerate(data):
                ma_dh = f"DH-{row['id']:04d}"
                self.table.setItem(row_idx, 0, QTableWidgetItem(ma_dh))
                self.table.setItem(row_idx, 1, QTableWidgetItem(row['email_tai_khoan'] or ""))
                self.table.setItem(row_idx, 2, QTableWidgetItem(row['nen_tang']))
                self.table.setItem(row_idx, 3, QTableWidgetItem(row['ten_khach_hang'] or ""))
                
                # Format tiền
                tien = row['so_tien'] or 0.0
                self.table.setItem(row_idx, 4, QTableWidgetItem(f"{tien:,.0f}đ"))
                
                # Buttons
                self.table.setCellWidget(row_idx, 5, self.create_action_widget(row['id']))

        # setRowCount() tạo lại các hàng, nên áp chiều cao sau khi nạp dữ liệu.
        for row_idx in range(self.table.rowCount()):
            self.table.setRowHeight(row_idx, self.ACTION_ROW_HEIGHT)

        self.table.ApplyDataGridViewTheme()

    def create_action_widget(self, item_id):
        """Tạo cột Thao tác chứa 2 nút: Khôi phục & Xóa vĩnh viễn."""
        widget = QWidget()
        widget.setObjectName("TrashActionCell")
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(1, 0, 1, 0)
        layout.setSpacing(8)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # Nút Khôi phục
        restore_btn = QPushButton("↩ Khôi phục")
        restore_btn.setFixedSize(102, self.ACTION_BUTTON_HEIGHT)
        restore_btn.setProperty("class", "RestoreButton")
        restore_btn.clicked.connect(lambda: self.on_restore(item_id))
        
        # Nút Xóa vĩnh viễn
        delete_btn = QPushButton("🗑 Xóa vĩnh viễn")
        delete_btn.setFixedSize(138, self.ACTION_BUTTON_HEIGHT)
        delete_btn.setProperty("class", "DeletePermanentButton")
        delete_btn.clicked.connect(lambda: self.on_delete_permanent(item_id))
        
        layout.addWidget(restore_btn)
        layout.addWidget(delete_btn)
        return widget

    def on_restore(self, item_id):
        """Logic khôi phục."""
        if self.is_account_mode:
            if database.restore_account(item_id):
                QMessageBox.information(self, "Thành Công", "Đã khôi phục tài khoản thành công!")
                self.refresh_table()
        else:
            if database.restore_order(item_id):
                QMessageBox.information(self, "Thành Công", "Đã khôi phục đơn hàng thành công!")
                self.refresh_table()

    def on_delete_permanent(self, item_id):
        """Logic xóa vĩnh viễn sau khi người dùng xác nhận."""
        confirm = QMessageBox.question(
            self, "Xác Nhận Xóa Vĩnh Viễn",
            "Bạn có chắc chắn muốn xóa vĩnh viễn dữ liệu này? Hành động này KHÔNG THỂ HOÀN TÁC!",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes
        )
        
        if confirm == QMessageBox.StandardButton.Yes:
            if self.is_account_mode:
                if database.delete_account_permanently(item_id):
                    QMessageBox.information(self, "Thành Công", "Đã xóa vĩnh viễn tài khoản!")
                    self.refresh_table()
            else:
                if database.delete_order_permanently(item_id):
                    QMessageBox.information(self, "Thành Công", "Đã xóa vĩnh viễn đơn hàng!")
                    self.refresh_table()
