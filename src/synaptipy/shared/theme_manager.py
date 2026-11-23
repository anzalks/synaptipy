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
_initial_system_dark: Optional[bool] = None
_palette_overwritten: bool = False
_preview_theme_mode: Optional[ThemeMode] = None
_applying_theme: bool = False


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


def set_theme_mode(mode: ThemeMode, emit_signal: bool = True) -> None:
    """Set the theme mode setting."""
    global _preview_theme_mode
    _preview_theme_mode = None
    settings = _get_settings()
    settings.setValue("appearance/theme", mode.value)
    settings.sync()
    log.debug(f"Theme mode set to: {mode.value}")

    if emit_signal:
        signals = get_theme_signals()
        signals.theme_changed.emit(mode.value)


def is_dark_mode() -> bool:
    """
    Check if dark mode should be active based on current or previewed setting.

    Returns:
        True if dark mode should be used, False otherwise.
    """
    mode = _preview_theme_mode if _preview_theme_mode is not None else get_theme_mode()

    if mode == ThemeMode.DARK:
        return True
    elif mode == ThemeMode.LIGHT:
        return False
    elif mode == ThemeMode.SYSTEM:
        return _detect_system_dark_mode()

    return False


def _snapshot_initial_system_dark(app: Optional[QtWidgets.QApplication]) -> None:
    """Capture initial OS window luminance before Synaptipy overwrites QApplication palette."""
    global _initial_system_dark
    if _initial_system_dark is not None or app is None or _palette_overwritten:
        return
    try:
        bg_color = app.palette().color(QtGui.QPalette.ColorRole.Window)
        luminance = (0.299 * bg_color.red() + 0.587 * bg_color.green() + 0.114 * bg_color.blue()) / 255.0
        _initial_system_dark = luminance < 0.5
    except Exception:
        pass


def _check_gtk_theme_env() -> Optional[bool]:
    """Inspect GTK_THEME environment variable for explicit light/dark suffix."""
    import os

    gtk_theme = os.environ.get("GTK_THEME", "").strip().lower()
    if not gtk_theme:
        return None
    if gtk_theme.endswith((":dark", "-dark")) or "dark" in gtk_theme:
        return True
    if gtk_theme.endswith((":light", "-light")):
        return False
    return None


def _check_gsettings_color_scheme() -> Optional[bool]:
    """Query GNOME/freedesktop color-scheme via gsettings when available."""
    import shutil
    import subprocess

    gsettings = shutil.which("gsettings")
    if not gsettings:
        return None
    try:
        proc = subprocess.run(
            [gsettings, "get", "org.gnome.desktop.interface", "color-scheme"],
            capture_output=True,
            text=True,
            timeout=0.5,
            check=False,
        )
        if proc.returncode == 0:
            val = proc.stdout.strip().strip("'\"").lower()
            if "dark" in val:
                return True
            if val in ("default", "prefer-light"):
                return False
    except (OSError, subprocess.SubprocessError):
        pass
    return None


def _check_kde_color_scheme() -> Optional[bool]:
    """Inspect ~/.config/kdeglobals ColorScheme for KDE Plasma dark themes."""
    from pathlib import Path

    kdeglobals = Path.home() / ".config" / "kdeglobals"
    if not kdeglobals.is_file():
        return None
    try:
        for raw_line in kdeglobals.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = raw_line.strip()
            if line.lower().startswith("colorscheme="):
                return "dark" in line.split("=", 1)[1].strip().lower()
    except OSError:
        pass
    return None


def _detect_linux_dark_mode() -> Optional[bool]:
    """Detect GNOME, GTK, or KDE dark-scheme preferences on Linux (including standalone AppImages)."""
    for probe in (_check_gtk_theme_env, _check_gsettings_color_scheme, _check_kde_color_scheme):
        detected = probe()
        if detected is not None:
            return detected
    return None


def _detect_system_dark_mode() -> bool:  # noqa: C901
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

    if sys.platform.startswith("linux"):
        linux_dark = _detect_linux_dark_mode()
        if linux_dark is not None:
            return linux_dark

    if _palette_overwritten and _initial_system_dark is not None:
        return _initial_system_dark

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
    _snapshot_initial_system_dark(app)
    if _system_theme_listener_installed:
        return

    style_hints = app.styleHints()
    signal = getattr(style_hints, "colorSchemeChanged", None)
    if signal is None:
        return

    def _on_color_scheme_changed(_scheme) -> None:
        if _preview_theme_mode is None and not _applying_theme and get_theme_mode() == ThemeMode.SYSTEM:
            apply_theme(ThemeMode.SYSTEM)

    signal.connect(_on_color_scheme_changed)
    _system_theme_listener_installed = True


def _get_macos_objc_handles():
    """Return cached ARM64/x86_64-safe libobjc function wrappers on macOS Cocoa."""
    import ctypes
    import sys

    if sys.platform != "darwin":
        return None
    app = QtWidgets.QApplication.instance()
    if app is None or getattr(app, "platformName", lambda: "")().lower() != "cocoa":
        return None
    try:
        objc = ctypes.cdll.LoadLibrary("/usr/lib/libobjc.A.dylib")
        objc.objc_getClass.argtypes = [ctypes.c_char_p]
        objc.objc_getClass.restype = ctypes.c_void_p
        objc.sel_registerName.argtypes = [ctypes.c_char_p]
        objc.sel_registerName.restype = ctypes.c_void_p
        msg_addr = ctypes.cast(objc.objc_msgSend, ctypes.c_void_p).value
        return {
            "objc": objc,
            "msg0": ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)(msg_addr),
            "msg1_ptr": ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)(msg_addr),
            "msg1_void": ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)(msg_addr),
            "msg1_long": ctypes.CFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_long)(msg_addr),
            "msg1_bool": ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_bool)(msg_addr),
            "msg_utf8": ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_char_p)(msg_addr),
        }
    except Exception as exc:
        log.debug("Could not initialize macOS Objective-C bridge: %s", exc)
        return None


def activate_macos_foreground_app(focus: bool = False) -> None:
    """Promote CLI/Conda Python on macOS to a regular foreground app so the native menu bar shows."""
    import os

    if os.environ.get("PYTEST_CURRENT_TEST"):
        return
    handles = _get_macos_objc_handles()
    if handles is None:
        return
    try:
        objc = handles["objc"]
        ns_app = handles["msg0"](objc.objc_getClass(b"NSApplication"), objc.sel_registerName(b"sharedApplication"))
        if not ns_app:
            return
        # 0 == NSApplicationActivationPolicyRegular (owns Dock icon + native top menu bar)
        handles["msg1_long"](ns_app, objc.sel_registerName(b"setActivationPolicy:"), 0)
        if focus:
            handles["msg1_bool"](ns_app, objc.sel_registerName(b"activateIgnoringOtherApps:"), True)
    except Exception as exc:
        log.debug("macOS foreground activation skipped: %s", exc)


def _set_macos_native_appearance(mode: Optional[ThemeMode]) -> bool:
    """Set NSApp.appearance on macOS Cocoa so native QMacStyle tabs/controls/menus switch Light/Dark."""
    handles = _get_macos_objc_handles()
    if handles is None:
        return False
    try:
        objc = handles["objc"]
        ns_app = handles["msg0"](objc.objc_getClass(b"NSApplication"), objc.sel_registerName(b"sharedApplication"))
        if not ns_app:
            return False
        if mode == ThemeMode.DARK:
            apr_name = b"NSAppearanceNameDarkAqua"
        elif mode == ThemeMode.LIGHT:
            apr_name = b"NSAppearanceNameAqua"
        else:
            apr_name = None

        apr_ptr = None
        if apr_name is not None:
            ns_str = handles["msg_utf8"](
                objc.objc_getClass(b"NSString"),
                objc.sel_registerName(b"stringWithUTF8String:"),
                apr_name,
            )
            apr_ptr = handles["msg1_ptr"](
                objc.objc_getClass(b"NSAppearance"),
                objc.sel_registerName(b"appearanceNamed:"),
                ns_str,
            )
        handles["msg1_void"](ns_app, objc.sel_registerName(b"setAppearance:"), apr_ptr)
        return True
    except Exception as exc:
        log.debug("Could not set macOS NSAppearance: %s", exc)
        return False


def select_platform_style(
    dark: bool,
    platform_str: Optional[str] = None,
    qt_platform_name: Optional[str] = None,
    available_keys: Optional[list[str]] = None,
) -> tuple[str, bool]:
    """Select the native Qt widget style for each OS and return ``(style_name, uses_native_palette)``.

    - **macOS (Cocoa)**: ``"macOS"`` (native pill/segmented tabs, native controls, driven by ``NSAppearance``).
    - **Windows**: ``"windows11"`` when available (Win11 native Light/Dark), ``"windowsvista"`` on Win10 Light,
      and ``"Fusion"`` on Win10 Dark (since Win32 ``uxtheme`` does not support dark controls).
    - **Linux**: ``"Breeze"`` / ``"adwaita"`` when matching the desktop scheme, else ``"Fusion"`` (standard
      freedesktop Qt style with full Light/Dark palette support).
    - **Headless (offscreen)**: ``"Fusion"`` for deterministic cross-platform CI rendering.
    """
    import sys

    plat = (platform_str or sys.platform).lower()
    app = QtWidgets.QApplication.instance()
    qpa = (
        qt_platform_name
        if qt_platform_name is not None
        else (getattr(app, "platformName", lambda: "")() if app is not None else "")
    ).lower()
    raw_keys = available_keys if available_keys is not None else list(QtWidgets.QStyleFactory.keys())
    available = {k.lower(): k for k in raw_keys}
    fusion = available.get("fusion", "Fusion")

    if qpa == "offscreen":
        return (fusion, False)

    if plat == "darwin" and "macos" in available:
        return (available["macos"], True)

    if plat == "win32":
        if "windows11" in available:
            return (available["windows11"], False)
        if not dark and "windowsvista" in available:
            return (available["windowsvista"], True)
        return (fusion, False)

    if plat.startswith("linux"):
        sys_dark = _detect_system_dark_mode()
        if dark == sys_dark:
            for linux_native in ("breeze", "adwaita", "kvantum"):
                if linux_native in available:
                    return (available[linux_native], True)
        return (fusion, False)

    return (fusion, False)


def _build_global_stylesheet(dark: bool, native_macos: bool = False) -> str:
    """Build minimal semantic QSS rules without overriding native platform tabs, menus, or controls."""
    if dark:
        subdued = "#a0a0a0"
        primary_bg = "#2a82da"
        primary_hover = "#3b93eb"
        primary_pressed = "#1f6ec0"
        primary_disabled_bg = "#4a4a4a"
        primary_disabled_fg = "#888888"
        danger_fg = "#ff7b7b"
        danger_border = "#8b3a3a"
        danger_hover = "#4a2424"
        banner_bg = "#2b313a"
        banner_border = "#444c56"
        splash_border = "#5a5a5a"
    else:
        subdued = "#666666"
        primary_bg = "#0078d7"
        primary_hover = "#1084e0"
        primary_pressed = "#0063b1"
        primary_disabled_bg = "#d6d6d6"
        primary_disabled_fg = "#888888"
        danger_fg = "#b91c1c"
        danger_border = "#e0a0a0"
        danger_hover = "#fde8e8"
        banner_bg = "#f4f7fb"
        banner_border = "#d0d7de"
        splash_border = "#b8b8b8"

    primary_qss = (
        ""
        if native_macos
        else (
            f'QPushButton[buttonRole="primary"] {{ background-color: {primary_bg}; color: #ffffff;'
            f" border: 1px solid {primary_pressed}; border-radius: 4px; padding: 4px 12px; font-weight: 600; }}"
            f'QPushButton[buttonRole="primary"]:hover {{ background-color: {primary_hover}; }}'
            f'QPushButton[buttonRole="primary"]:pressed {{ background-color: {primary_pressed}; }}'
            f'QPushButton[buttonRole="primary"]:disabled {{ background-color: {primary_disabled_bg};'
            f" color: {primary_disabled_fg}; border-color: {primary_disabled_bg}; }}"
        )
    )
    return (
        f'QLabel[subdued="true"] {{ color: {subdued}; }}'
        f"{primary_qss}"
        f'QPushButton[buttonRole="danger"] {{ color: {danger_fg}; border: 1px solid {danger_border};'
        f" border-radius: 4px; padding: 4px 10px; }}"
        f'QPushButton[buttonRole="danger"]:hover {{ background-color: {danger_hover}; }}'
        f"QFrame#DemoDownloadBanner {{ background-color: {banner_bg};"
        f" border-bottom: 1px solid {banner_border}; }}"
        f"QWidget#WelcomeScreen {{ border: 1px solid {splash_border}; }}"
    )


def apply_theme(mode: Optional[ThemeMode] = None, preview: bool = False) -> None:
    """
    Apply the specified theme mode using native OS styling on macOS, Windows, and Linux.

    Args:
        mode: Theme mode to apply. If None, uses current setting.
        preview: True when previewing an unsaved theme selection in PreferencesDialog.
    """
    global _preview_theme_mode, _applying_theme
    if mode is None:
        _preview_theme_mode = None
        mode = get_theme_mode()
    elif preview:
        _preview_theme_mode = mode
    else:
        _preview_theme_mode = None

    app = QtWidgets.QApplication.instance()
    if not app:
        log.warning("No QApplication instance found, cannot apply theme")
        return

    _snapshot_initial_system_dark(app)

    _applying_theme = True
    try:
        # On macOS Cocoa, set NSAppearance first so SYSTEM resets to nil before querying OS dark mode
        _set_macos_native_appearance(mode if mode in (ThemeMode.LIGHT, ThemeMode.DARK) else None)

        if mode == ThemeMode.SYSTEM:
            dark = _detect_system_dark_mode()
        else:
            dark = mode == ThemeMode.DARK

        if dark:
            _apply_dark_theme(app)
            log.debug("Applied dark theme")
        else:
            _apply_light_theme(app)
            log.debug("Applied light theme")

        try:
            from synaptipy.shared.zoom_theme import refresh_cached_pen_brush

            refresh_cached_pen_brush()
        except Exception:
            pass
    finally:
        _applying_theme = False

    get_theme_signals().theme_changed.emit(mode.value)


def _apply_light_theme(app: QtWidgets.QApplication) -> None:
    """Apply light theme using the native OS style and palette."""
    global _palette_overwritten
    style_name, uses_native_palette = select_platform_style(dark=False)
    app.setStyle(style_name)
    if uses_native_palette:
        if _palette_overwritten:
            app.setPalette(QtGui.QPalette())
            _palette_overwritten = False
    else:
        _apply_light_palette(app)
    app.setStyleSheet(_build_global_stylesheet(dark=False, native_macos=(style_name.lower() == "macos")))


def _apply_dark_theme(app: QtWidgets.QApplication) -> None:
    """Apply dark theme using the native OS style and palette."""
    global _palette_overwritten
    style_name, uses_native_palette = select_platform_style(dark=True)
    app.setStyle(style_name)
    if uses_native_palette:
        if _palette_overwritten:
            app.setPalette(QtGui.QPalette())
            _palette_overwritten = False
    else:
        _apply_dark_palette(app)
    app.setStyleSheet(_build_global_stylesheet(dark=True, native_macos=(style_name.lower() == "macos")))


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
    if hasattr(QtGui.QPalette.ColorRole, "Accent"):
        palette.setColor(QtGui.QPalette.ColorRole.Accent, highlight)

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

    global _palette_overwritten
    _palette_overwritten = True
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
    if hasattr(QtGui.QPalette.ColorRole, "Accent"):
        palette.setColor(QtGui.QPalette.ColorRole.Accent, highlight)

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

    global _palette_overwritten
    _palette_overwritten = True
    app.setPalette(palette)


def _repolish_widget(widget: QtWidgets.QWidget) -> None:
    """Refresh QSS property evaluation on *widget* without recreating it."""
    style = widget.style()
    if style is not None:
        style.unpolish(widget)
        style.polish(widget)
    widget.update()


def style_as_subdued(widget, italic: bool = False, font_size: Optional[int] = None) -> None:
    """Style a widget's text as subdued/secondary while tracking live theme switches."""
    if isinstance(widget, QtWidgets.QWidget):
        widget.setProperty("subdued", True)
        widget.setAttribute(QtCore.Qt.WidgetAttribute.WA_SetPalette, False)
        _repolish_widget(widget)
    else:
        p = widget.palette()
        p.setColor(widget.foregroundRole(), p.color(QtGui.QPalette.ColorRole.PlaceholderText))
        widget.setPalette(p)
    if italic or font_size:
        f = widget.font()
        if italic:
            f.setItalic(True)
        if font_size:
            f.setPointSize(font_size)
        widget.setFont(f)


def clear_subdued_style(widget) -> None:
    """Restore normal theme foreground text color on a widget previously styled as subdued."""
    if isinstance(widget, QtWidgets.QWidget):
        widget.setProperty("subdued", False)
        widget.setAttribute(QtCore.Qt.WidgetAttribute.WA_SetPalette, False)
        f = widget.font()
        if f.italic():
            f.setItalic(False)
            widget.setFont(f)
        _repolish_widget(widget)


def warning_banner_stylesheet() -> str:
    """Return a scoped banner stylesheet that avoids double borders on child QLabels."""
    if is_dark_mode():
        return (
            "QFrame#UpdateBanner, .QFrame { background-color: #3d3520; border: 1px solid #665b30;"
            " border-radius: 4px; color: #e0c870; }"
            " QFrame#UpdateBanner QLabel { border: none; background: transparent; color: #e0c870; }"
            " QFrame#UpdateBanner QPushButton { color: #e0c870; background: transparent;"
            " border: 1px solid #8a7b42; border-radius: 3px; padding: 2px 8px; }"
            " QFrame#UpdateBanner QPushButton:hover { background-color: #4f4528; }"
        )
    return (
        "QFrame#UpdateBanner, .QFrame { background-color: #fff3cd; border: 1px solid #ffc107;"
        " border-radius: 4px; color: #664d03; }"
        " QFrame#UpdateBanner QLabel { border: none; background: transparent; color: #664d03; }"
        " QFrame#UpdateBanner QPushButton { color: #664d03; background: transparent;"
        " border: 1px solid #d39e00; border-radius: 3px; padding: 2px 8px; }"
        " QFrame#UpdateBanner QPushButton:hover { background-color: #ffe69c; }"
    )


def warning_label_stylesheet() -> str:
    """Return a QLabel stylesheet for warning/info labels that respects the current theme."""
    if is_dark_mode():
        return (
            "QLabel { background-color: #3d3520; color: #e0c870;"
            " border: 1px solid #665b30; border-radius: 4px;"
            " padding: 8px; font-weight: bold; }"
        )
    return (
        "QLabel { background-color: #FFF3CD; color: #664d03;"
        " border: 1px solid #FFEAA7; border-radius: 4px;"
        " padding: 8px; font-weight: bold; }"
    )


def status_html_colors() -> dict[str, str]:
    """Return WCAG-compliant ``{"warning": hex, "error": hex, "success": hex}`` for rich-text status labels."""
    if is_dark_mode():
        return {"warning": "#f0b429", "error": "#ff6b6b", "success": "#51cf66"}
    return {"warning": "#9a6700", "error": "#c92a2a", "success": "#2b8a3e"}


def themed_plot_colors() -> tuple:
    """Return (background_color, foreground_color) for plots (white canvas in both themes)."""
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
    "select_platform_style",
    "activate_macos_foreground_app",
    "install_system_theme_listener",
    "get_theme_signals",
    "style_as_subdued",
    "clear_subdued_style",
    "warning_banner_stylesheet",
    "warning_label_stylesheet",
    "status_html_colors",
    "themed_plot_colors",
    "get_themed_icon",
]
