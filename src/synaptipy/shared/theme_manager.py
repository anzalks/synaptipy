# src/synaptipy/shared/theme_manager.py
# -*- coding: utf-8 -*-
"""
Theme Manager Module for synaptipy.

Manages application theme preferences with persistence via QSettings.
Supports Light, Dark, and System theme modes.
"""

import logging
from enum import Enum
from typing import Optional

from PySide6 import QtCore, QtGui, QtWidgets

from synaptipy.shared.constants import APP_NAME, SETTINGS_SECTION

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

_system_theme_listener_installed = False


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

    app = QtWidgets.QApplication.instance()
    if app is not None:
        try:
            scheme = app.styleHints().colorScheme()
            if scheme == QtCore.Qt.ColorScheme.Dark:
                return True
            if scheme == QtCore.Qt.ColorScheme.Light:
                return False
        except (AttributeError, RuntimeError):
            log.debug("Qt color-scheme detection unavailable; using platform fallback")

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
    if app:
        palette = app.palette()
        # Compare window background luminance
        bg_color = palette.color(QtGui.QPalette.ColorRole.Window)
        # Calculate relative luminance
        luminance = (0.299 * bg_color.red() + 0.587 * bg_color.green() + 0.114 * bg_color.blue()) / 255
        return luminance < 0.5
    return False


def install_system_theme_listener(app: QtWidgets.QApplication) -> None:
    """Reapply System mode when Qt reports an operating-system theme change."""
    global _system_theme_listener_installed
    if _system_theme_listener_installed:
        return

    style_hints = app.styleHints()
    signal = getattr(style_hints, "colorSchemeChanged", None)
    if signal is None:
        return

    def _on_color_scheme_changed(_scheme) -> None:
        if get_theme_mode() == ThemeMode.SYSTEM:
            apply_theme(ThemeMode.SYSTEM)

    signal.connect(_on_color_scheme_changed)
    _system_theme_listener_installed = True


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
        if _detect_system_dark_mode():
            _apply_dark_theme(app)
            log.debug("Applied detected system dark theme")
        else:
            _apply_light_theme(app)
            log.debug("Applied detected system light theme")

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


def style_as_subdued(widget, italic: bool = False, font_size: Optional[int] = None) -> None:
    """Style a widget's text as subdued/secondary using the current palette."""
    p = widget.palette()
    p.setColor(widget.foregroundRole(), p.color(QtGui.QPalette.ColorRole.PlaceholderText))
    widget.setPalette(p)
    if italic or font_size:
        f = widget.font()
        if italic:
            f.setItalic(True)
        if font_size:
            f.setPixelSize(font_size)
        widget.setFont(f)


def warning_banner_stylesheet() -> str:
    """Return a QFrame stylesheet for warning/info banners that respects the current theme."""
    if is_dark_mode():
        return "QFrame { background: #3d3520; border: 1px solid #665b30;" " border-radius: 4px; color: #e0c870; }"
    return "QFrame { background: #fff3cd; border: 1px solid #ffc107;" " border-radius: 4px; color: #856404; }"


def warning_label_stylesheet() -> str:
    """Return a QLabel stylesheet for warning/info labels that respects the current theme."""
    if is_dark_mode():
        return (
            "QLabel { background-color: #3d3520; color: #e0c870;"
            " border: 1px solid #665b30; border-radius: 4px;"
            " padding: 8px; font-weight: bold; }"
        )
    return (
        "QLabel { background-color: #FFF3CD; color: #856404;"
        " border: 1px solid #FFEAA7; border-radius: 4px;"
        " padding: 8px; font-weight: bold; }"
    )


def themed_plot_colors() -> tuple:
    """Return (background_color, foreground_color) for plots based on the current theme."""
    if is_dark_mode():
        return ("#232323", "#cccccc")
    return ("white", "black")


def get_themed_icon(theme_name: str, fallback_standard_pixmap=None) -> QtGui.QIcon:
    """Get a themed icon with a fallback for platforms without Freedesktop icon themes."""
    icon = QtGui.QIcon.fromTheme(theme_name)
    if icon.isNull() and fallback_standard_pixmap is not None:
        app = QtWidgets.QApplication.instance()
        if app:
            icon = app.style().standardIcon(fallback_standard_pixmap)
    return icon


__all__ = [
    "ThemeMode",
    "get_theme_mode",
    "set_theme_mode",
    "is_dark_mode",
    "apply_theme",
    "install_system_theme_listener",
    "get_theme_signals",
    "style_as_subdued",
    "warning_banner_stylesheet",
    "warning_label_stylesheet",
    "themed_plot_colors",
    "get_themed_icon",
]
