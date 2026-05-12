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

# The style name active at application startup (captured lazily on first apply).
# Restored when the user switches back to System theme.
_initial_style_name: Optional[str] = None


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

    # Capture the native style name once, before we ever change it.
    global _initial_style_name
    if _initial_style_name is None:
        _initial_style_name = app.style().objectName()
        log.debug("Captured initial style name: %s", _initial_style_name)

    if mode == ThemeMode.SYSTEM:
        # Restore the OS-native appearance: reset to the original platform style,
        # clear any custom CSS, and reset the palette to the platform default.
        app.setStyle(_initial_style_name)
        app.setStyleSheet("")
        app.setPalette(app.style().standardPalette())
        log.debug("Applied system theme (native: %s)", _initial_style_name)

    elif mode == ThemeMode.LIGHT:
        _apply_light_theme(app)
        log.debug("Applied light theme")
    elif mode == ThemeMode.DARK:
        _apply_dark_theme(app)
        log.debug("Applied dark theme")


def _apply_light_theme(app: QtWidgets.QApplication) -> None:
    """Apply light theme using Fusion style and an explicit light QPalette."""
    # Fusion style fully respects QPalette on all platforms (including macOS).
    app.setStyle("Fusion")
    app.setStyleSheet("")
    _apply_light_palette(app)


def _apply_dark_theme(app: QtWidgets.QApplication) -> None:
    """Apply dark theme using Fusion style and an explicit dark QPalette."""
    # Fusion style fully respects QPalette on all platforms (including macOS).
    app.setStyle("Fusion")
    app.setStyleSheet("")
    _apply_dark_palette(app)


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
