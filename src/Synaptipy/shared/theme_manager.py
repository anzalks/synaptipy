# src/Synaptipy/shared/theme_manager.py
# -*- coding: utf-8 -*-
"""
Theme Manager Module for Synaptipy.

Manages application theme preferences with persistence via QSettings.
Supports Light, Dark, and System theme modes.
"""
import logging
from enum import Enum
from typing import Optional

from PySide6 import QtCore, QtGui, QtWidgets

from Synaptipy.shared.constants import APP_NAME, SETTINGS_SECTION

log = logging.getLogger(__name__)


class ThemeMode(Enum):
    """Application theme modes."""

    LIGHT = "light"
    DARK = "dark"
    SYSTEM = "system"


class ThemeSignals(QtCore.QObject):
    """Signals for theme changes."""

    theme_changed = QtCore.Signal(str)


# Global signal instance
_theme_signals: Optional[ThemeSignals] = None


def get_theme_signals() -> ThemeSignals:
    """Get the global theme signals instance."""
    global _theme_signals
    if _theme_signals is None:
        _theme_signals = ThemeSignals()
    return _theme_signals


def _get_settings() -> QtCore.QSettings:
    """Get QSettings instance for theme preferences."""
    return QtCore.QSettings(APP_NAME, SETTINGS_SECTION)


def get_theme_mode() -> ThemeMode:
    """Get the current theme mode setting."""
    settings = _get_settings()
    value = settings.value("appearance/theme", ThemeMode.SYSTEM.value, type=str)
    try:
        return ThemeMode(value)
    except ValueError:
        log.warning(f"Invalid theme mode value: {value}, defaulting to SYSTEM")
        return ThemeMode.SYSTEM


def set_theme_mode(mode: ThemeMode) -> None:
    """Set the theme mode setting."""
    settings = _get_settings()
    settings.setValue("appearance/theme", mode.value)
    settings.sync()
    log.debug(f"Theme mode set to: {mode.value}")

    # Emit signal
    signals = get_theme_signals()
    signals.theme_changed.emit(mode.value)


def is_dark_mode() -> bool:
    """
    Check if dark mode should be active based on current setting.

    Returns:
        True if dark mode should be used, False otherwise.
    """
    mode = get_theme_mode()

    if mode == ThemeMode.DARK:
        return True
    elif mode == ThemeMode.LIGHT:
        return False
    elif mode == ThemeMode.SYSTEM:
        return _detect_system_dark_mode()

    return False


def _detect_system_dark_mode() -> bool:
    """
    Detect if the system is using dark mode.

    Returns:
        True if system is in dark mode, False otherwise.
    """
    import sys

    if sys.platform == "win32":
        # Read Windows dark mode setting from registry
        try:
            import winreg

            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
            )
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            winreg.CloseKey(key)
            # 0 = Dark mode, 1 = Light mode
            is_dark = value == 0
            log.debug(f"Windows AppsUseLightTheme={value}, dark mode={is_dark}")
            return is_dark
        except Exception as e:
            log.debug(f"Could not read Windows theme setting: {e}")
            # Fallback to palette detection below

    # Fallback: use palette luminance detection
    app = QtWidgets.QApplication.instance()
    if app:
        palette = app.palette()
        # Compare window background luminance
        bg_color = palette.color(QtGui.QPalette.ColorRole.Window)
        # Calculate relative luminance
        luminance = (0.299 * bg_color.red() + 0.587 * bg_color.green() + 0.114 * bg_color.blue()) / 255
        return luminance < 0.5
    return False


def apply_theme(mode: Optional[ThemeMode] = None) -> None:
    """
    Apply the specified theme mode to the application.

    Args:
        mode: Theme mode to apply. If None, uses current setting.
    """
    if mode is None:
        mode = get_theme_mode()

    app = QtWidgets.QApplication.instance()
    if not app:
        log.warning("No QApplication instance found, cannot apply theme")
        return

    if mode == ThemeMode.SYSTEM:
        # Use native system theme (clear stylesheet and custom palette)
        app.setStyleSheet("")
        app.setPalette(app.style().standardPalette())
        log.debug("Applied active system theme (native)")

    elif mode == ThemeMode.LIGHT:
        _apply_light_theme(app)
        log.debug("Applied light theme")
    elif mode == ThemeMode.DARK:
        # Force dark stylesheet (custom)
        _apply_dark_theme(app)
        log.debug("Applied dark theme")


def _get_light_stylesheet() -> str:
    """Return comprehensive light theme stylesheet."""
    return """
    /* Global font */
    * {
        font-family: "Segoe UI", "Ubuntu", "Roboto", sans-serif;
    }

    /* Menus */
    QMenuBar {
        background-color: #f0f0f0;
        color: #000000;
        border-bottom: 1px solid #d0d0d0;
    }
    QMenuBar::item {
        background-color: transparent;
        color: #000000;
        padding: 4px 8px;
    }
    QMenuBar::item:selected {
        background-color: #0078d7;
        color: #ffffff;
    }
    QMenu {
        background-color: #ffffff;
        color: #000000;
        border: 1px solid #c0c0c0;
    }
    QMenu::item {
        padding: 6px 30px 6px 20px;
        background-color: transparent;
        color: #000000;
    }
    QMenu::item:selected {
        background-color: #0078d7;
        color: #ffffff;
    }
    QMenu::item:disabled {
        color: #a0a0a0;
    }
    QMenu::separator {
        height: 1px;
        background-color: #d0d0d0;
        margin: 4px 10px;
    }

    /* Tooltips */
    QToolTip {
        background-color: #ffffdc;
        color: #000000;
        border: 1px solid #c0c0c0;
        padding: 4px;
    }

    /* Group boxes */
    QGroupBox {
        border: 1px solid #c0c0c0;
        border-radius: 4px;
        margin-top: 8px;
        padding-top: 8px;
        color: #000000;
    }
    QGroupBox::title {
        subcontrol-origin: margin;
        left: 10px;
        padding: 0 3px;
        color: #000000;
    }

    /* Tabs - only color styling, preserve default alignment */
    QTabWidget::pane {
        border: 1px solid #c0c0c0;
        background-color: #ffffff;
    }
    QTabBar::tab {
        background-color: #e0e0e0;
        color: #000000;
        padding: 6px 12px;
    }
    QTabBar::tab:selected {
        background-color: #ffffff;
        color: #000000;
    }
    QTabBar::tab:hover:!selected {
        background-color: #d0d0d0;
    }

    /* Scrollbars */
    QScrollBar:vertical {
        background-color: #f0f0f0;
        width: 14px;
        border: none;
    }
    QScrollBar::handle:vertical {
        background-color: #c0c0c0;
        min-height: 30px;
        border-radius: 4px;
        margin: 2px;
    }
    QScrollBar::handle:vertical:hover {
        background-color: #a0a0a0;
    }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
        height: 0px;
    }
    QScrollBar:horizontal {
        background-color: #f0f0f0;
        height: 14px;
        border: none;
    }
    QScrollBar::handle:horizontal {
        background-color: #c0c0c0;
        min-width: 30px;
        border-radius: 4px;
        margin: 2px;
    }
    QScrollBar::handle:horizontal:hover {
        background-color: #a0a0a0;
    }
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
        width: 0px;
    }

    /* Buttons */
    QPushButton {
        background-color: #e1e1e1;
        color: #000000;
        border: 1px solid #adadad;
        padding: 5px 15px;
        border-radius: 3px;
    }
    QPushButton:hover {
        background-color: #d0d0d0;
        border-color: #0078d7;
    }
    QPushButton:pressed {
        background-color: #c0c0c0;
    }
    QPushButton:disabled {
        background-color: #f0f0f0;
        color: #a0a0a0;
    }

    /* Line edits and spin boxes */
    QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {
        background-color: #ffffff;
        color: #000000;
        border: 1px solid #c0c0c0;
        padding: 4px;
        border-radius: 2px;
    }
    QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {
        border-color: #0078d7;
    }

    /* Combo box dropdown */
    QComboBox::drop-down {
        border: none;
        width: 20px;
    }
    QComboBox QAbstractItemView {
        background-color: #ffffff;
        color: #000000;
        border: 1px solid #c0c0c0;
        selection-background-color: #0078d7;
        selection-color: #ffffff;
    }

    /* Checkboxes and radio buttons */
    QCheckBox, QRadioButton {
        color: #000000;
    }

    /* Labels */
    QLabel {
        color: #000000;
    }

    /* List and tree views */
    QListView, QTreeView, QTableView {
        background-color: #ffffff;
        color: #000000;
        border: 1px solid #c0c0c0;
        selection-background-color: #0078d7;
        selection-color: #ffffff;
    }
    QHeaderView::section {
        background-color: #f0f0f0;
        color: #000000;
        border: 1px solid #c0c0c0;
        padding: 4px;
    }

    /* Status bar */
    QStatusBar {
        background-color: #f0f0f0;
        color: #000000;
    }

    /* Splitters */
    QSplitter::handle {
        background-color: #c0c0c0;
    }
    """


def _get_dark_stylesheet() -> str:
    """Return comprehensive dark theme stylesheet."""
    return """
    /* Global font */
    * {
        font-family: "Segoe UI", "Ubuntu", "Roboto", sans-serif;
    }

    /* Menus */
    QMenuBar {
        background-color: #353535;
        color: #ffffff;
        border-bottom: 1px solid #2a2a2a;
    }
    QMenuBar::item {
        background-color: transparent;
        color: #ffffff;
        padding: 4px 8px;
    }
    QMenuBar::item:selected {
        background-color: #2a82da;
        color: #ffffff;
    }
    QMenu {
        background-color: #2d2d2d;
        color: #ffffff;
        border: 1px solid #3d3d3d;
    }
    QMenu::item {
        padding: 6px 30px 6px 20px;
        background-color: transparent;
        color: #ffffff;
    }
    QMenu::item:selected {
        background-color: #2a82da;
        color: #ffffff;
    }
    QMenu::item:disabled {
        color: #808080;
    }
    QMenu::separator {
        height: 1px;
        background-color: #3d3d3d;
        margin: 4px 10px;
    }

    /* Tooltips */
    QToolTip {
        background-color: #1e1e1e;
        color: #ffffff;
        border: 1px solid #3d3d3d;
        padding: 4px;
    }

    /* Group boxes */
    QGroupBox {
        border: 1px solid #3d3d3d;
        border-radius: 4px;
        margin-top: 8px;
        padding-top: 8px;
        color: #ffffff;
    }
    QGroupBox::title {
        subcontrol-origin: margin;
        left: 10px;
        padding: 0 3px;
        color: #ffffff;
    }

    /* Tabs - only color styling, preserve default alignment */
    QTabWidget::pane {
        border: 1px solid #3d3d3d;
        background-color: #2d2d2d;
    }
    QTabBar::tab {
        background-color: #353535;
        color: #ffffff;
        padding: 6px 12px;
    }
    QTabBar::tab:selected {
        background-color: #2d2d2d;
        color: #ffffff;
    }
    QTabBar::tab:hover:!selected {
        background-color: #404040;
    }

    /* Scrollbars */
    QScrollBar:vertical {
        background-color: #2d2d2d;
        width: 14px;
        border: none;
    }
    QScrollBar::handle:vertical {
        background-color: #5a5a5a;
        min-height: 30px;
        border-radius: 4px;
        margin: 2px;
    }
    QScrollBar::handle:vertical:hover {
        background-color: #6a6a6a;
    }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
        height: 0px;
    }
    QScrollBar:horizontal {
        background-color: #2d2d2d;
        height: 14px;
        border: none;
    }
    QScrollBar::handle:horizontal {
        background-color: #5a5a5a;
        min-width: 30px;
        border-radius: 4px;
        margin: 2px;
    }
    QScrollBar::handle:horizontal:hover {
        background-color: #6a6a6a;
    }
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
        width: 0px;
    }

    /* Buttons */
    QPushButton {
        background-color: #414141;
        color: #ffffff;
        border: 1px solid #3d3d3d;
        padding: 5px 15px;
        border-radius: 3px;
    }
    QPushButton:hover {
        background-color: #505050;
        border-color: #2a82da;
    }
    QPushButton:pressed {
        background-color: #353535;
    }
    QPushButton:disabled {
        background-color: #2d2d2d;
        color: #808080;
    }

    /* Line edits and spin boxes */
    QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {
        background-color: #232323;
        color: #ffffff;
        border: 1px solid #3d3d3d;
        padding: 4px;
        border-radius: 2px;
    }
    QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {
        border-color: #2a82da;
    }

    /* Combo box dropdown */
    QComboBox::drop-down {
        border: none;
        width: 20px;
    }
    QComboBox QAbstractItemView {
        background-color: #2d2d2d;
        color: #ffffff;
        border: 1px solid #3d3d3d;
        selection-background-color: #2a82da;
        selection-color: #ffffff;
    }

    /* Checkboxes and radio buttons */
    QCheckBox, QRadioButton {
        color: #ffffff;
    }

    /* Labels */
    QLabel {
        color: #ffffff;
    }

    /* List and tree views */
    QListView, QTreeView, QTableView {
        background-color: #232323;
        color: #ffffff;
        border: 1px solid #3d3d3d;
        selection-background-color: #2a82da;
        selection-color: #ffffff;
    }
    QHeaderView::section {
        background-color: #353535;
        color: #ffffff;
        border: 1px solid #3d3d3d;
        padding: 4px;
    }

    /* Status bar */
    QStatusBar {
        background-color: #353535;
        color: #ffffff;
    }

    /* Splitters */
    QSplitter::handle {
        background-color: #3d3d3d;
    }
    """


def _apply_light_theme(app: QtWidgets.QApplication) -> None:
    """Apply complete light theme with palette and stylesheet."""
    _apply_light_palette(app)
    app.setStyleSheet(_get_light_stylesheet())


def _apply_dark_theme(app: QtWidgets.QApplication) -> None:
    """Apply complete dark theme with palette and stylesheet."""
    _apply_dark_palette(app)
    app.setStyleSheet(_get_dark_stylesheet())


def _apply_light_palette(app: QtWidgets.QApplication) -> None:
    """Apply a comprehensive light color palette for all UI elements."""
    palette = QtGui.QPalette()

    # Main colors - ensure good contrast for readability
    window_bg = QtGui.QColor(240, 240, 240)
    base_bg = QtGui.QColor(255, 255, 255)
    text_color = QtGui.QColor(0, 0, 0)
    button_bg = QtGui.QColor(225, 225, 225)
    highlight = QtGui.QColor(0, 120, 215)

    # Active/Normal state colors
    palette.setColor(QtGui.QPalette.ColorRole.Window, window_bg)
    palette.setColor(QtGui.QPalette.ColorRole.WindowText, text_color)
    palette.setColor(QtGui.QPalette.ColorRole.Base, base_bg)
    palette.setColor(QtGui.QPalette.ColorRole.AlternateBase, QtGui.QColor(245, 245, 245))
    palette.setColor(QtGui.QPalette.ColorRole.Text, text_color)
    palette.setColor(QtGui.QPalette.ColorRole.Button, button_bg)
    palette.setColor(QtGui.QPalette.ColorRole.ButtonText, text_color)
    palette.setColor(QtGui.QPalette.ColorRole.BrightText, QtGui.QColor(255, 0, 0))

    # Selection colors
    palette.setColor(QtGui.QPalette.ColorRole.Highlight, highlight)
    palette.setColor(QtGui.QPalette.ColorRole.HighlightedText, QtGui.QColor(255, 255, 255))

    # Link colors
    palette.setColor(QtGui.QPalette.ColorRole.Link, QtGui.QColor(0, 100, 200))
    palette.setColor(QtGui.QPalette.ColorRole.LinkVisited, QtGui.QColor(100, 0, 150))

    # Tooltip colors
    palette.setColor(QtGui.QPalette.ColorRole.ToolTipBase, QtGui.QColor(255, 255, 220))
    palette.setColor(QtGui.QPalette.ColorRole.ToolTipText, text_color)

    # Placeholder text (for input fields)
    palette.setColor(QtGui.QPalette.ColorRole.PlaceholderText, QtGui.QColor(120, 120, 120))

    # 3D effect colors for borders and frames
    palette.setColor(QtGui.QPalette.ColorRole.Light, QtGui.QColor(255, 255, 255))
    palette.setColor(QtGui.QPalette.ColorRole.Midlight, QtGui.QColor(227, 227, 227))
    palette.setColor(QtGui.QPalette.ColorRole.Dark, QtGui.QColor(160, 160, 160))
    palette.setColor(QtGui.QPalette.ColorRole.Mid, QtGui.QColor(180, 180, 180))
    palette.setColor(QtGui.QPalette.ColorRole.Shadow, QtGui.QColor(105, 105, 105))

    # Disabled state colors - ensure they're visible but dimmed
    disabled_text = QtGui.QColor(120, 120, 120)
    palette.setColor(QtGui.QPalette.ColorGroup.Disabled, QtGui.QPalette.ColorRole.WindowText, disabled_text)
    palette.setColor(QtGui.QPalette.ColorGroup.Disabled, QtGui.QPalette.ColorRole.Text, disabled_text)
    palette.setColor(QtGui.QPalette.ColorGroup.Disabled, QtGui.QPalette.ColorRole.ButtonText, disabled_text)
    palette.setColor(
        QtGui.QPalette.ColorGroup.Disabled, QtGui.QPalette.ColorRole.Highlight, QtGui.QColor(200, 200, 200)
    )
    palette.setColor(
        QtGui.QPalette.ColorGroup.Disabled, QtGui.QPalette.ColorRole.HighlightedText, QtGui.QColor(120, 120, 120)
    )
    palette.setColor(QtGui.QPalette.ColorGroup.Disabled, QtGui.QPalette.ColorRole.Base, QtGui.QColor(240, 240, 240))

    app.setPalette(palette)


def _apply_dark_palette(app: QtWidgets.QApplication) -> None:
    """Apply a comprehensive dark color palette for all UI elements."""
    palette = QtGui.QPalette()

    # Main colors
    window_bg = QtGui.QColor(53, 53, 53)
    base_bg = QtGui.QColor(35, 35, 35)
    text_color = QtGui.QColor(255, 255, 255)
    button_bg = QtGui.QColor(65, 65, 65)
    highlight = QtGui.QColor(42, 130, 218)

    # Active/Normal state colors
    palette.setColor(QtGui.QPalette.ColorRole.Window, window_bg)
    palette.setColor(QtGui.QPalette.ColorRole.WindowText, text_color)
    palette.setColor(QtGui.QPalette.ColorRole.Base, base_bg)
    palette.setColor(QtGui.QPalette.ColorRole.AlternateBase, QtGui.QColor(45, 45, 45))
    palette.setColor(QtGui.QPalette.ColorRole.Text, text_color)
    palette.setColor(QtGui.QPalette.ColorRole.Button, button_bg)
    palette.setColor(QtGui.QPalette.ColorRole.ButtonText, text_color)
    palette.setColor(QtGui.QPalette.ColorRole.BrightText, QtGui.QColor(255, 0, 0))

    # Selection colors
    palette.setColor(QtGui.QPalette.ColorRole.Highlight, highlight)
    palette.setColor(QtGui.QPalette.ColorRole.HighlightedText, QtGui.QColor(255, 255, 255))

    # Link colors
    palette.setColor(QtGui.QPalette.ColorRole.Link, QtGui.QColor(42, 130, 218))
    palette.setColor(QtGui.QPalette.ColorRole.LinkVisited, QtGui.QColor(120, 100, 180))

    # Tooltip colors
    palette.setColor(QtGui.QPalette.ColorRole.ToolTipBase, QtGui.QColor(25, 25, 25))
    palette.setColor(QtGui.QPalette.ColorRole.ToolTipText, text_color)

    # Placeholder text (for input fields)
    palette.setColor(QtGui.QPalette.ColorRole.PlaceholderText, QtGui.QColor(140, 140, 140))

    # 3D effect colors for borders and frames
    palette.setColor(QtGui.QPalette.ColorRole.Light, QtGui.QColor(100, 100, 100))
    palette.setColor(QtGui.QPalette.ColorRole.Midlight, QtGui.QColor(70, 70, 70))
    palette.setColor(QtGui.QPalette.ColorRole.Dark, QtGui.QColor(30, 30, 30))
    palette.setColor(QtGui.QPalette.ColorRole.Mid, QtGui.QColor(50, 50, 50))
    palette.setColor(QtGui.QPalette.ColorRole.Shadow, QtGui.QColor(10, 10, 10))

    # Disabled state colors
    disabled_text = QtGui.QColor(127, 127, 127)
    palette.setColor(QtGui.QPalette.ColorGroup.Disabled, QtGui.QPalette.ColorRole.WindowText, disabled_text)
    palette.setColor(QtGui.QPalette.ColorGroup.Disabled, QtGui.QPalette.ColorRole.Text, disabled_text)
    palette.setColor(QtGui.QPalette.ColorGroup.Disabled, QtGui.QPalette.ColorRole.ButtonText, disabled_text)
    palette.setColor(QtGui.QPalette.ColorGroup.Disabled, QtGui.QPalette.ColorRole.Highlight, QtGui.QColor(80, 80, 80))
    palette.setColor(QtGui.QPalette.ColorGroup.Disabled, QtGui.QPalette.ColorRole.HighlightedText, disabled_text)
    palette.setColor(QtGui.QPalette.ColorGroup.Disabled, QtGui.QPalette.ColorRole.Base, QtGui.QColor(45, 45, 45))

    app.setPalette(palette)


__all__ = [
    "ThemeMode",
    "get_theme_mode",
    "set_theme_mode",
    "is_dark_mode",
    "apply_theme",
    "get_theme_signals",
]
