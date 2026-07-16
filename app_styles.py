# -*- coding: utf-8 -*-

"""Shared neon visual system for the desktop dashboard.

This module deliberately contains presentation rules only.  Business widgets keep
their existing object references and signal connections in ``nghia.py``.
"""

BACKGROUND = "#070D1A"
SURFACE = "#0F1B2D"
BORDER = "#1F2D44"
TEXT = "#FFFFFF"
MUTED = "#AAB6C8"
BLUE = "#2F8CFF"
PURPLE = "#A020F0"


DARK_THEME_STYLE = r"""
QWidget {
    background-color: #070D1A;
    color: #EAF0F8;
    font-family: "Segoe UI";
    font-size: 13px;
}
QLabel { background: transparent; }
QMainWindow, QWidget#PageRoot, #ContentFrame { background-color: #070D1A; }
QToolTip {
    background-color: #17243A;
    color: #FFFFFF;
    border: 1px solid #526784;
    border-radius: 6px;
    padding: 7px 9px;
}

/* Sidebar */
#SidebarFrame {
    background-color: #060C17;
    border-right: 1px solid #1B2940;
}
#AvatarFrame {
    background: qradialgradient(cx:0.5, cy:0.5, radius:0.75,
        stop:0 #14233A, stop:0.72 #0A1424, stop:0.86 #2F8CFF, stop:1 #A020F0);
    border: 2px solid #438CFF;
    border-radius: 58px;
}
#UserName { color: #FFFFFF; font-size: 18px; font-weight: 700; }
#AdminBadge {
    background-color: #241149;
    color: #C58AFF;
    border: 1px solid #6532B2;
    border-radius: 8px;
    padding: 3px 9px;
    font-size: 11px;
    font-weight: 700;
}
#SidebarDivider { background-color: #1F2D44; border: 0; max-height: 1px; }
QPushButton.SidebarButton {
    min-height: 48px;
    background: transparent;
    color: #9EABC0;
    border: 1px solid transparent;
    border-radius: 10px;
    padding: 0 15px;
    text-align: left;
    font-size: 13px;
    font-weight: 600;
}
QPushButton.SidebarButton:hover {
    background-color: #101D31;
    color: #FFFFFF;
    border-color: #263A59;
}
QPushButton.SidebarButton:checked {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 #245DDE, stop:0.52 #5130C9, stop:1 #251357);
    color: #FFFFFF;
    border: 1px solid #596BFF;
}
#SyncStatusBox {
    background-color: #101A2C;
    color: #F7BE4C;
    border: 1px solid #2A3953;
    border-radius: 8px;
    padding: 9px;
    font-size: 11px;
    font-weight: 600;
}
#VersionLabel { color: #66758D; font-size: 10px; }

/* Page headings and surfaces */
QLabel.TabTitle { color: #FFFFFF; font-size: 27px; font-weight: 750; }
QLabel.PageSubtitle { color: #AAB6C8; font-size: 13px; }
QLabel.SectionTitle { color: #F8FAFC; font-size: 17px; font-weight: 700; }
#ToolbarCard, QFrame.PanelCard {
    background-color: #0C1728;
    border: 1px solid #1F2D44;
    border-radius: 13px;
}
#TableCard {
    background-color: #0B1626;
    border: 1px solid #1F2D44;
    border-radius: 13px;
}
#InfoCard {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #101D32, stop:1 #11162B);
    border: 1px solid #263B5E;
    border-radius: 14px;
}

/* Inputs */
QLineEdit, QComboBox, QDateEdit, QTextEdit {
    background-color: #111D30;
    color: #EEF4FC;
    border: 1px solid #2A3A55;
    border-radius: 9px;
    padding: 0 13px;
    min-height: 40px;
    selection-background-color: #5A42E8;
}
QTextEdit { padding: 9px 12px; }
QLineEdit:hover, QComboBox:hover, QDateEdit:hover, QTextEdit:hover { border-color: #3D5276; }
QLineEdit:focus, QComboBox:focus, QDateEdit:focus, QTextEdit:focus {
    border: 1px solid #438CFF;
    background-color: #132137;
}
QComboBox::drop-down { border: 0; width: 30px; }
QComboBox QAbstractItemView {
    background: #101B2D;
    color: #EEF4FC;
    border: 1px solid #334766;
    selection-background-color: #3D2DA8;
    padding: 5px;
}

/* Buttons */
QPushButton {
    min-height: 40px;
    background-color: #142136;
    color: #DCE6F4;
    border: 1px solid #2A3B58;
    border-radius: 9px;
    padding: 0 15px;
    font-weight: 650;
}
QPushButton:hover { background-color: #1B2C47; color: #FFFFFF; border-color: #4B6287; }
QPushButton:pressed { background-color: #101A2B; padding-top: 1px; }
QPushButton:disabled { color: #637086; background-color: #101827; border-color: #1D293B; }
QPushButton.PrimaryButton, QPushButton.SyncButton, QPushButton.PageCurrent {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 #267DFF, stop:0.52 #6150F1, stop:1 #A020F0);
    border: 1px solid #6B72FF;
    color: #FFFFFF;
}
QPushButton.PrimaryButton:hover, QPushButton.SyncButton:hover, QPushButton.PageCurrent:hover {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 #4397FF, stop:0.52 #7965FF, stop:1 #B43CFF);
    border-color: #9AA8FF;
}
QPushButton.SecondaryButton { background-color: #111D30; border-color: #293A56; color: #D3DCE9; }
QPushButton.SecondaryButton:hover { background-color: #1A2940; border-color: #496080; }
QPushButton.DangerButton { background-color: #351923; border-color: #652A3B; color: #FF9AAB; }
QPushButton.DangerButton:hover { background-color: #4B1E2A; border-color: #A53B53; color: #FFD1D9; }
QPushButton.ActionEdit {
    min-height: 32px; max-height: 32px; min-width: 34px; max-width: 34px;
    padding: 0; background-color: #392C18; border-color: #6E5321; border-radius: 8px;
}
QPushButton.ActionEdit:hover { background-color: #594019; border-color: #F5A91C; }
QPushButton.ActionDelete {
    min-height: 32px; max-height: 32px; min-width: 34px; max-width: 34px;
    padding: 0; background-color: #3D1B25; border-color: #6B293A; border-radius: 8px;
}
QPushButton.ActionDelete:hover { background-color: #5C2130; border-color: #FF4D6D; }
QPushButton.PageButton { min-width: 34px; max-width: 34px; min-height: 34px; max-height: 34px; padding: 0; }

/* Data tables */
QTableWidget {
    background-color: #0D192A;
    alternate-background-color: #0F1D30;
    color: #DDE7F3;
    border: 0;
    border-radius: 10px;
    gridline-color: #1E2D43;
    outline: 0;
    selection-background-color: #183D70;
    selection-color: #FFFFFF;
}
QTableWidget::item { padding: 0 10px; border-bottom: 1px solid #1D2B40; }
QTableWidget::item:hover { background-color: #162A43; }
QTableWidget::item:selected { background-color: #1B477C; color: #FFFFFF; }
QHeaderView::section {
    background-color: #0A1423;
    color: #ADB9CB;
    border: 0;
    border-right: 1px solid #1B2A40;
    border-bottom: 1px solid #2A3A55;
    padding: 12px 10px;
    font-weight: 700;
}
QTableCornerButton::section { background: #0A1423; border: 0; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 3px; }
QScrollBar::handle:vertical { background: #354866; min-height: 28px; border-radius: 5px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 3px; }
QScrollBar::handle:horizontal { background: #354866; min-width: 28px; border-radius: 5px; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
#PaginationLabel { color: #8391A7; font-size: 11px; }

/* Dialogs */
QDialog { background-color: #091321; }
QDialog QLabel { background: transparent; color: #CBD5E1; font-weight: 600; }
QDialogButtonBox { background: transparent; }
QMessageBox { background: #0F1B2D; }
QCalendarWidget QWidget { background: #101B2D; color: #F8FAFC; }
QCalendarWidget QAbstractItemView { background: #0D1725; color: #E8EDF5; selection-background-color: #5A42E8; }
"""
