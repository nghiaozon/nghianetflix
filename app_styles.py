# -*- coding: utf-8 -*-

"""Shared neon visual system for the desktop dashboard.

This module deliberately contains presentation rules only.  Business widgets keep
their existing object references and signal connections in ``nghia.py``.
"""

import os
import json
import importlib
from runtime_paths import config_file

# Default visual tokens for safety/legacy fallback
BACKGROUND = "#070D1A"
SURFACE = "#0F1B2D"
BORDER = "#1F2D44"
TEXT = "#FFFFFF"
MUTED = "#AAB6C8"
BLUE = "#2F8CFF"
PURPLE = "#A020F0"


class ThemeManager:
    _active_theme_name = "dark_neon"
    _active_theme_module = None

    @classmethod
    def load_theme(cls):
        """Loads theme name from config/settings.json, defaults to 'dark_neon'."""
        config_path = config_file("settings.json")
        if os.path.exists(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    theme_name = data.get("theme", "dark_neon")
                    if theme_name in ["dark_neon", "classic_dark", "light"]:
                        cls._active_theme_name = theme_name
            except Exception as e:
                print(f"Error loading theme config: {e}")
        
        cls._load_module()

    @classmethod
    def _load_module(cls):
        try:
            cls._active_theme_module = importlib.import_module(f"themes.{cls._active_theme_name}")
        except Exception as e:
            print(f"Error importing theme module {cls._active_theme_name}, falling back to dark_neon: {e}")
            try:
                cls._active_theme_module = importlib.import_module("themes.dark_neon")
                cls._active_theme_name = "dark_neon"
            except Exception:
                # Absolute fallback theme
                class FallbackTheme:
                    BACKGROUND = "#070D1A"
                    SIDEBAR = "#060C17"
                    CARD = "#0C1728"
                    TABLE_BACKGROUND = "#0D192A"
                    TABLE_HEADER = "#0A1423"
                    TABLE_ROW = "#0D192A"
                    TABLE_ROW_HOVER = "#162A43"
                    TEXT_PRIMARY = "#FFFFFF"
                    TEXT_SECONDARY = "#AAB6C8"
                    BORDER = "#1F2D44"
                    INPUT_BACKGROUND = "#111D30"
                    BUTTON_PRIMARY = "qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #267DFF, stop:0.52 #6150F1, stop:1 #A020F0)"
                    BUTTON_PRIMARY_HOVER = "qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #4397FF, stop:0.52 #7965FF, stop:1 #B43CFF)"
                    BUTTON_SECONDARY = "#142136"
                    SUCCESS = "#69F59A"
                    WARNING = "#F7BE4C"
                    ERROR = "#ff6b6b"
                    BADGE_ACTIVE = "#10271E"
                    BADGE_EXPIRED = "#4a1519"
                cls._active_theme_module = FallbackTheme()
                cls._active_theme_name = "dark_neon"

    @classmethod
    def get_active_theme(cls):
        if cls._active_theme_module is None:
            cls.load_theme()
        return cls._active_theme_module

    @classmethod
    def get_theme_name(cls):
        return cls._active_theme_name

    @classmethod
    def set_theme(cls, theme_name):
        if theme_name not in ["dark_neon", "classic_dark", "light"]:
            return False
        
        cls._active_theme_name = theme_name
        cls._load_module()
        
        # Save to config/settings.json
        config_path = config_file("settings.json")
        try:
            os.makedirs(os.path.dirname(config_path), exist_ok=True)
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump({"theme": theme_name}, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"Error saving theme config: {e}")
            return False

    @classmethod
    def get_stylesheet(cls):
        theme = cls.get_active_theme()
        colors = {
            "BACKGROUND": theme.BACKGROUND,
            "SIDEBAR": theme.SIDEBAR,
            "CARD": theme.CARD,
            "TABLE_BACKGROUND": theme.TABLE_BACKGROUND,
            "TABLE_HEADER": theme.TABLE_HEADER,
            "TABLE_ROW": theme.TABLE_ROW,
            "TABLE_ROW_HOVER": theme.TABLE_ROW_HOVER,
            "TEXT_PRIMARY": theme.TEXT_PRIMARY,
            "TEXT_SECONDARY": theme.TEXT_SECONDARY,
            "BORDER": theme.BORDER,
            "INPUT_BACKGROUND": theme.INPUT_BACKGROUND,
            "BUTTON_PRIMARY": theme.BUTTON_PRIMARY,
            "BUTTON_PRIMARY_HOVER": theme.BUTTON_PRIMARY_HOVER,
            "BUTTON_SECONDARY": theme.BUTTON_SECONDARY,
            "SUCCESS": theme.SUCCESS,
            "WARNING": theme.WARNING,
            "ERROR": theme.ERROR,
            "BADGE_ACTIVE": theme.BADGE_ACTIVE,
            "BADGE_EXPIRED": theme.BADGE_EXPIRED,
        }
        style = THEME_STYLE_TEMPLATE
        for key, value in colors.items():
            style = style.replace(f"{{{key}}}", value)
        return style


THEME_STYLE_TEMPLATE = r"""
QWidget {
    background-color: {BACKGROUND};
    color: {TEXT_PRIMARY};
    font-family: "Segoe UI";
    font-size: 13px;
}
QLabel { background: transparent; }
QMainWindow, QWidget#PageRoot, #ContentFrame { background-color: {BACKGROUND}; }
QToolTip {
    background-color: {INPUT_BACKGROUND};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 7px 9px;
}

/* Sidebar */
#SidebarFrame {
    background-color: {SIDEBAR};
    border-right: 1px solid {BORDER};
}
#AvatarFrame {
    background: qradialgradient(cx:0.5, cy:0.5, radius:0.75,
        stop:0 {INPUT_BACKGROUND}, stop:0.72 {SIDEBAR}, stop:0.86 {BUTTON_PRIMARY}, stop:1 {BUTTON_PRIMARY_HOVER});
    border: 2px solid {BORDER};
    border-radius: 58px;
}
#UserName { color: {TEXT_PRIMARY}; font-size: 18px; font-weight: 700; }
#AdminBadge {
    background-color: {BADGE_ACTIVE};
    color: {SUCCESS};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 3px 9px;
    font-size: 11px;
    font-weight: 700;
}
#SidebarDivider { background-color: {BORDER}; border: 0; max-height: 1px; }
QPushButton.SidebarButton {
    min-height: 48px;
    background: transparent;
    color: {TEXT_SECONDARY};
    border: 1px solid transparent;
    border-radius: 10px;
    padding: 0 15px;
    text-align: left;
    font-size: 13px;
    font-weight: 600;
}
QPushButton.SidebarButton:hover {
    background-color: {TABLE_ROW_HOVER};
    color: {TEXT_PRIMARY};
    border-color: {BORDER};
}
QPushButton.SidebarButton:checked {
    background: {BUTTON_PRIMARY};
    color: #FFFFFF;
    border: 1px solid {BORDER};
}
#SyncStatusBox {
    background-color: {INPUT_BACKGROUND};
    color: {WARNING};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 9px;
    font-size: 11px;
    font-weight: 600;
}
#VersionLabel { color: {TEXT_SECONDARY}; font-size: 10px; }

/* Page headings and surfaces */
QLabel.TabTitle { color: {TEXT_PRIMARY}; font-size: 27px; font-weight: 750; }
QLabel.PageSubtitle { color: {TEXT_SECONDARY}; font-size: 13px; }
QLabel.SectionTitle { color: {TEXT_PRIMARY}; font-size: 17px; font-weight: 700; }
#ToolbarCard, QFrame.PanelCard {
    background-color: {CARD};
    border: 1px solid {BORDER};
    border-radius: 13px;
}
#TableCard {
    background-color: {CARD};
    border: 1px solid {BORDER};
    border-radius: 13px;
}
#InfoCard {
    background-color: {CARD};
    border: 1px solid {BORDER};
    border-radius: 14px;
}

/* Inputs */
QLineEdit, QComboBox, QDateEdit, QTextEdit {
    background-color: {INPUT_BACKGROUND};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER};
    border-radius: 9px;
    padding: 0 13px;
    min-height: 40px;
    selection-background-color: {BUTTON_PRIMARY_HOVER};
}
QTextEdit { padding: 9px 12px; }
QLineEdit:hover, QComboBox:hover, QDateEdit:hover, QTextEdit:hover { border-color: {BORDER}; }
QLineEdit:focus, QComboBox:focus, QDateEdit:focus, QTextEdit:focus {
    border: 1px solid {BUTTON_PRIMARY};
    background-color: {INPUT_BACKGROUND};
}
QComboBox::drop-down { border: 0; width: 30px; }
QComboBox QAbstractItemView {
    background: {INPUT_BACKGROUND};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER};
    selection-background-color: {BUTTON_PRIMARY_HOVER};
    padding: 5px;
}

/* Buttons */
QPushButton {
    min-height: 40px;
    background-color: {BUTTON_SECONDARY};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER};
    border-radius: 9px;
    padding: 0 15px;
    font-weight: 650;
}
QPushButton:hover { background-color: {TABLE_ROW_HOVER}; color: {TEXT_PRIMARY}; border-color: {BORDER}; }
QPushButton:pressed { background-color: {INPUT_BACKGROUND}; padding-top: 1px; }
QPushButton:disabled { color: {TEXT_SECONDARY}; background-color: {INPUT_BACKGROUND}; border-color: {BORDER}; }
QPushButton.PrimaryButton, QPushButton.SyncButton, QPushButton.PageCurrent {
    background: {BUTTON_PRIMARY};
    border: 1px solid {BORDER};
    color: #FFFFFF;
}
QPushButton.PrimaryButton:hover, QPushButton.SyncButton:hover, QPushButton.PageCurrent:hover {
    background: {BUTTON_PRIMARY_HOVER};
    border-color: {BORDER};
}
QPushButton.SecondaryButton { background-color: {INPUT_BACKGROUND}; border-color: {BORDER}; color: {TEXT_PRIMARY}; }
QPushButton.SecondaryButton:hover { background-color: {TABLE_ROW_HOVER}; border-color: {BORDER}; }
QPushButton.DangerButton { background-color: {BADGE_EXPIRED}; border-color: {ERROR}; color: {ERROR}; }
QPushButton.DangerButton:hover { background-color: {ERROR}; border-color: {BORDER}; color: #FFFFFF; }
QPushButton.ActionEdit {
    min-height: 32px; max-height: 32px; min-width: 34px; max-width: 34px;
    padding: 0; background-color: {INPUT_BACKGROUND}; border-color: {WARNING}; border-radius: 8px;
    color: {WARNING};
}
QPushButton.ActionEdit:hover { background-color: {WARNING}; border-color: {BORDER}; color: #FFFFFF; }
QPushButton.ActionDelete {
    min-height: 32px; max-height: 32px; min-width: 34px; max-width: 34px;
    padding: 0; background-color: {BADGE_EXPIRED}; border-color: {ERROR}; border-radius: 8px;
    color: {ERROR};
}
QPushButton.ActionDelete:hover { background-color: {ERROR}; border-color: {BORDER}; color: #FFFFFF; }
QPushButton.PageButton { min-width: 34px; max-width: 34px; min-height: 34px; max-height: 34px; padding: 0; }

/* Data tables */
QTableWidget {
    background-color: {TABLE_BACKGROUND};
    alternate-background-color: {INPUT_BACKGROUND};
    color: {TEXT_PRIMARY};
    border: 0;
    border-radius: 10px;
    gridline-color: {BORDER};
    outline: 0;
    selection-background-color: {BUTTON_PRIMARY_HOVER};
    selection-color: #FFFFFF;
}
QTableWidget::item { padding: 0 10px; border-bottom: 1px solid {BORDER}; }
QTableWidget::item:hover { background-color: {TABLE_ROW_HOVER}; }
QTableWidget::item:selected { background-color: {BUTTON_PRIMARY}; color: #FFFFFF; }
QHeaderView::section {
    background-color: {TABLE_HEADER};
    color: {TEXT_SECONDARY};
    border: 0;
    border-right: 1px solid {BORDER};
    border-bottom: 1px solid {BORDER};
    padding: 12px 10px;
    font-weight: 700;
}
QTableCornerButton::section { background: {TABLE_HEADER}; border: 0; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 3px; }
QScrollBar::handle:vertical { background: {BORDER}; min-height: 28px; border-radius: 5px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 3px; }
QScrollBar::handle:horizontal { background: {BORDER}; min-width: 28px; border-radius: 5px; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
#PaginationLabel { color: {TEXT_SECONDARY}; font-size: 11px; }

/* Dialogs */
QDialog { background-color: {BACKGROUND}; }
QDialog QLabel { background: transparent; color: {TEXT_PRIMARY}; font-weight: 600; }
QDialogButtonBox { background: transparent; }
QMessageBox { background: {CARD}; }
QCalendarWidget QWidget { background: {INPUT_BACKGROUND}; color: {TEXT_PRIMARY}; }
QCalendarWidget QAbstractItemView { background: {TABLE_BACKGROUND}; color: {TEXT_PRIMARY}; selection-background-color: {BUTTON_PRIMARY_HOVER}; }

/* Custom items */
QLabel.DialogTitle {
    font-size: 20px;
    font-weight: 700;
    color: {TEXT_PRIMARY};
}

/* Trash dialog buttons */
QPushButton.RestoreButton {
    background-color: {BADGE_ACTIVE};
    color: {SUCCESS};
    border: 1px solid {SUCCESS};
    border-radius: 7px;
    padding: 0;
    font-size: 9px;
    font-weight: 600;
    min-height: 36px;
    max-height: 36px;
}
QPushButton.RestoreButton:hover { background-color: {SUCCESS}; border-color: {BORDER}; color: #FFFFFF; }

QPushButton.DeletePermanentButton {
    background-color: {BADGE_EXPIRED};
    color: {ERROR};
    border: 1px solid {ERROR};
    border-radius: 7px;
    padding: 0;
    font-size: 9px;
    font-weight: 600;
    min-height: 36px;
    max-height: 36px;
}
QPushButton.DeletePermanentButton:hover { background-color: {ERROR}; border-color: {BORDER}; color: #FFFFFF; }

/* Settings page custom styles */
QFrame.ThemeOptionCard {
    background-color: {INPUT_BACKGROUND};
    border: 2px solid {BORDER};
    border-radius: 12px;
    margin: 4px;
    padding: 10px;
}
QFrame.ThemeOptionCard:hover {
    background-color: {TABLE_ROW_HOVER};
    border-color: {BUTTON_PRIMARY_HOVER};
    margin: 2px;
    padding: 12px;
}
QFrame.ThemeOptionCard[selected="true"] {
    background-color: {TABLE_ROW_HOVER};
    border-color: {BUTTON_PRIMARY};
    margin: 2px;
    padding: 12px;
}

QLabel.SafetyLabel {
    color: {SUCCESS};
    background-color: {BADGE_ACTIVE};
    border: 1px solid {SUCCESS};
    border-radius: 8px;
    padding: 12px;
    font-weight: 600;
}
"""

# Initialize active theme on import
ThemeManager.load_theme()
DARK_THEME_STYLE = ThemeManager.get_stylesheet()
