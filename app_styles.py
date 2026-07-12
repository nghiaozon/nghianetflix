# -*- coding: utf-8 -*-

"""Shared visual system for the desktop dashboard."""

DARK_THEME_STYLE = r"""
QWidget {
    background-color: #08111d;
    color: #e8edf5;
    font-family: "Segoe UI";
    font-size: 13px;
}
QToolTip {
    background-color: #172235;
    color: #f8fafc;
    border: 1px solid #344258;
    padding: 6px 8px;
}
#SidebarFrame {
    background-color: #070d16;
    border-right: 1px solid #1b2738;
}
QPushButton.SidebarButton {
    min-height: 46px;
    background: transparent;
    color: #94a3b8;
    border: 0;
    border-left: 3px solid transparent;
    border-radius: 8px;
    padding: 0 16px;
    text-align: left;
    font-size: 14px;
    font-weight: 600;
}
QPushButton.SidebarButton:hover { background: #111d2c; color: #f8fafc; }
QPushButton.SidebarButton:checked {
    background: #13243a;
    color: #ffffff;
    border-left-color: #3b82f6;
}
#ContentFrame { background-color: #08111d; }
QLabel.TabTitle { color: #f8fafc; font-size: 26px; font-weight: 700; }
QLabel.PageSubtitle { color: #8391a7; font-size: 13px; }
QFrame.StatCard, QFrame.PanelCard {
    background-color: #101b2a;
    border: 1px solid #1d2b3e;
    border-radius: 12px;
}
QLabel.StatCardValue { color: #f8fafc; font-size: 25px; font-weight: 700; }
QLabel.StatCardLabel { color: #8fa0b7; font-size: 12px; font-weight: 600; }
QLineEdit, QComboBox, QDateEdit, QTextEdit {
    background-color: #101b2a;
    color: #e8edf5;
    border: 1px solid #2a394e;
    border-radius: 8px;
    padding: 0 12px;
    min-height: 38px;
    selection-background-color: #2563eb;
}
QTextEdit { padding: 8px 12px; }
QLineEdit:focus, QComboBox:focus, QDateEdit:focus, QTextEdit:focus { border-color: #3b82f6; }
QComboBox::drop-down { border: 0; width: 28px; }
QComboBox QAbstractItemView { background: #101b2a; border: 1px solid #2a394e; selection-background-color: #1d4ed8; }
QPushButton {
    min-height: 38px;
    background-color: #1b293b;
    color: #dbe4ef;
    border: 1px solid #304057;
    border-radius: 8px;
    padding: 0 15px;
    font-weight: 600;
}
QPushButton:hover { background-color: #24354b; border-color: #40536d; }
QPushButton:pressed { background-color: #142033; }
QPushButton.PrimaryButton { background: #2563eb; border-color: #2563eb; color: white; }
QPushButton.PrimaryButton:hover { background: #3475f5; }
QPushButton.DangerButton { background: #3a1d25; border-color: #6f2938; color: #fda4af; }
QPushButton.DangerButton:hover { background: #53222e; }
QPushButton.SecondaryButton { background: #172235; border-color: #2a394e; color: #cbd5e1; }
QTableWidget {
    background-color: #0e1928;
    alternate-background-color: #111e2e;
    color: #dce5ef;
    border: 1px solid #1e2c40;
    border-radius: 10px;
    gridline-color: #1b293b;
    outline: 0;
    selection-background-color: #173b69;
    selection-color: white;
}
QTableWidget::item { padding: 0 10px; border-bottom: 1px solid #1b293b; }
QTableWidget::item:hover { background-color: #16283c; }
QTableWidget::item:selected { background-color: #1b477c; color: white; }
QHeaderView::section {
    background-color: #0a1421;
    color: #aab8ca;
    border: 0;
    border-right: 1px solid #1b293b;
    border-bottom: 1px solid #26364b;
    padding: 12px 10px;
    font-weight: 700;
}
QTableCornerButton::section { background: #0a1421; border: 0; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: #344258; min-height: 28px; border-radius: 5px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 2px; }
QScrollBar::handle:horizontal { background: #344258; min-width: 28px; border-radius: 5px; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
QDialog { background-color: #0d1725; }
QDialog QLabel { background: transparent; color: #cbd5e1; font-weight: 600; }
QDialogButtonBox { background: transparent; }
QMessageBox { background: #101b2a; }
QCalendarWidget QWidget { background: #101b2a; color: #f8fafc; }
QCalendarWidget QAbstractItemView { background: #0d1725; color: #e8edf5; selection-background-color: #2563eb; }
"""
