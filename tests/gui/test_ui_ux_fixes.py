"""
Tests for the three UI/UX fixes:

1. Explorer Tab resizable side panels (QSplitter).
2. Preferences Dialog - no spurious theme preview on open.
3. Theme Manager - Light/Dark/System cycle using Fusion style + QPalette.
"""

from unittest.mock import MagicMock, patch

from PySide6 import QtCore, QtWidgets

# ---------------------------------------------------------------------------
# 1. Explorer Tab: QSplitter replaces fixed QHBoxLayout
# ---------------------------------------------------------------------------


def test_explorer_layout_uses_splitter(qtbot):
    """The main layout of ExplorerTab must contain a QSplitter with 3 children."""
    from synaptipy.application.gui.explorer.explorer_tab import ExplorerTab
    from synaptipy.infrastructure.exporters.nwb_exporter import NWBExporter
    from synaptipy.infrastructure.file_readers import NeoAdapter

    neo_adapter = MagicMock(spec=NeoAdapter)
    nwb_exporter = MagicMock(spec=NWBExporter)
    status_bar = QtWidgets.QStatusBar()

    tab = ExplorerTab(neo_adapter, nwb_exporter, status_bar)
    qtbot.addWidget(tab)

    # The outer layout must hold exactly one QSplitter.
    layout = tab.layout()
    splitter = None
    for i in range(layout.count()):
        item = layout.itemAt(i)
        if item and isinstance(item.widget(), QtWidgets.QSplitter):
            splitter = item.widget()
            break

    assert splitter is not None, "ExplorerTab layout must contain a QSplitter"
    assert splitter.orientation() == QtCore.Qt.Orientation.Horizontal
    assert splitter.count() == 3, "Splitter must have exactly 3 panels"


def test_explorer_splitter_sizes(qtbot):
    """Splitter must have 3 panels; centre must be wider than either side panel."""
    from synaptipy.application.gui.explorer.explorer_tab import ExplorerTab
    from synaptipy.infrastructure.exporters.nwb_exporter import NWBExporter
    from synaptipy.infrastructure.file_readers import NeoAdapter

    neo_adapter = MagicMock(spec=NeoAdapter)
    nwb_exporter = MagicMock(spec=NWBExporter)
    status_bar = QtWidgets.QStatusBar()

    tab = ExplorerTab(neo_adapter, nwb_exporter, status_bar)
    qtbot.addWidget(tab)

    layout = tab.layout()
    splitter = None
    for i in range(layout.count()):
        item = layout.itemAt(i)
        if item and isinstance(item.widget(), QtWidgets.QSplitter):
            splitter = item.widget()
            break

    assert splitter is not None
    sizes = splitter.sizes()
    assert len(sizes) == 3
    # Centre panel must be wider than either side panel (proportional to 800 vs 320/360).
    assert sizes[1] > sizes[0], f"Centre ({sizes[1]}) should be wider than left ({sizes[0]})"
    assert sizes[1] > sizes[2], f"Centre ({sizes[1]}) should be wider than right ({sizes[2]})"


# ---------------------------------------------------------------------------
# 2. Preferences Dialog: no spurious theme call on open
# ---------------------------------------------------------------------------


def test_preferences_no_theme_preview_on_open(qapp, qtbot):
    """Opening PreferencesDialog must not call apply_theme."""
    with patch("synaptipy.application.gui.preferences_dialog.apply_theme") as mock_apply:
        from synaptipy.application.gui.preferences_dialog import PreferencesDialog

        dlg = PreferencesDialog()
        qtbot.addWidget(dlg)

    mock_apply.assert_not_called(), ("apply_theme() must not be called when the Preferences dialog is opened")


def test_preferences_theme_radios_initialized_correctly(qapp, qtbot):
    """After opening, exactly one theme radio is checked and signals work."""
    from synaptipy.application.gui.preferences_dialog import PreferencesDialog
    from synaptipy.shared.theme_manager import ThemeMode, get_theme_mode

    dlg = PreferencesDialog()
    qtbot.addWidget(dlg)

    # Exactly one must be checked.
    checked = sum(
        [
            dlg.theme_light_radio.isChecked(),
            dlg.theme_dark_radio.isChecked(),
            dlg.theme_system_radio.isChecked(),
        ]
    )
    assert checked == 1, f"Exactly one theme radio must be checked, got {checked}"

    # The checked one must match the stored setting.
    current = get_theme_mode()
    if current == ThemeMode.LIGHT:
        assert dlg.theme_light_radio.isChecked()
    elif current == ThemeMode.DARK:
        assert dlg.theme_dark_radio.isChecked()
    else:
        assert dlg.theme_system_radio.isChecked()


def test_preferences_uses_canonical_settings_namespace(qapp, qtbot):
    """Preferences and startup must read the same persistent settings store."""
    from synaptipy.application.gui.preferences_dialog import PreferencesDialog
    from synaptipy.shared.constants import APP_NAME, SETTINGS_SECTION

    dlg = PreferencesDialog()
    qtbot.addWidget(dlg)

    assert dlg._settings.organizationName() == APP_NAME
    assert dlg._settings.applicationName() == SETTINGS_SECTION


def test_saved_theme_is_applied_before_welcome_screen_creation(qapp):
    """The first visible widget must be constructed with the saved theme."""
    from synaptipy.application.startup_manager import StartupManager

    events = []
    welcome = MagicMock()
    with (
        patch("synaptipy.shared.theme_manager.install_system_theme_listener"),
        patch("synaptipy.shared.theme_manager.apply_theme", side_effect=lambda: events.append("theme")),
        patch(
            "synaptipy.application.startup_manager.WelcomeScreen",
            side_effect=lambda: events.append("welcome") or welcome,
        ),
        patch("synaptipy.application.startup_manager.QtCore.QTimer.singleShot"),
    ):
        result = StartupManager(qapp).start_loading()

    assert result is welcome
    assert events == ["theme", "welcome"]


# ---------------------------------------------------------------------------
# 3. Theme Manager: apply_theme cycles correctly
# ---------------------------------------------------------------------------


class _FakeStyle:
    """Minimal stand-in for a QStyle to track setStyle calls."""

    def __init__(self, name: str):
        self._name = name

    def objectName(self) -> str:
        return self._name

    def standardPalette(self):
        from PySide6 import QtGui

        return QtGui.QPalette()


def test_apply_theme_dark_uses_fusion(qapp):
    """apply_theme(DARK) must call app.setStyle('Fusion')."""
    from synaptipy.shared import theme_manager
    from synaptipy.shared.theme_manager import ThemeMode, apply_theme

    # Reset module-level cached style name so the test is isolated.
    theme_manager._initial_style_name = None

    with (
        patch.object(qapp, "setStyle") as mock_set_style,
        patch.object(qapp, "setStyleSheet"),
        patch.object(qapp, "setPalette"),
    ):
        apply_theme(ThemeMode.DARK)

    mock_set_style.assert_called_once_with("Fusion")


def test_apply_theme_light_uses_fusion(qapp):
    """apply_theme(LIGHT) must call app.setStyle('Fusion')."""
    from synaptipy.shared import theme_manager
    from synaptipy.shared.theme_manager import ThemeMode, apply_theme

    theme_manager._initial_style_name = None

    with (
        patch.object(qapp, "setStyle") as mock_set_style,
        patch.object(qapp, "setStyleSheet"),
        patch.object(qapp, "setPalette"),
    ):
        apply_theme(ThemeMode.LIGHT)

    mock_set_style.assert_called_once_with("Fusion")


def test_apply_theme_system_uses_detected_dark_palette(qapp):
    """System mode must resolve the operating-system preference before painting."""
    from synaptipy.shared.theme_manager import ThemeMode, apply_theme

    with (
        patch("synaptipy.shared.theme_manager._detect_system_dark_mode", return_value=True),
        patch("synaptipy.shared.theme_manager._apply_dark_theme") as apply_dark,
        patch("synaptipy.shared.theme_manager._apply_light_theme") as apply_light,
    ):
        apply_theme(ThemeMode.SYSTEM)

    apply_dark.assert_called_once_with(qapp)
    apply_light.assert_not_called()


def test_apply_theme_system_uses_detected_light_palette(qapp):
    """System mode must use the light palette when the operating system is light."""
    from synaptipy.shared.theme_manager import ThemeMode, apply_theme

    with (
        patch("synaptipy.shared.theme_manager._detect_system_dark_mode", return_value=False),
        patch("synaptipy.shared.theme_manager._apply_dark_theme") as apply_dark,
        patch("synaptipy.shared.theme_manager._apply_light_theme") as apply_light,
    ):
        apply_theme(ThemeMode.SYSTEM)

    apply_light.assert_called_once_with(qapp)
    apply_dark.assert_not_called()


def test_system_detection_uses_qt_color_scheme_before_palette():
    """A prior explicit palette must not be mistaken for the OS preference."""
    from synaptipy.shared.theme_manager import _detect_system_dark_mode

    app = MagicMock()
    app.styleHints.return_value.colorScheme.return_value = QtCore.Qt.ColorScheme.Dark
    with patch("synaptipy.shared.theme_manager.QtWidgets.QApplication.instance", return_value=app):
        assert _detect_system_dark_mode() is True
