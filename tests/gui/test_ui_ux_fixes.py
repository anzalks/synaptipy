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


def test_apply_theme_system_restores_native(qapp):
    """apply_theme(SYSTEM) must restore the saved native style name."""
    from synaptipy.shared import theme_manager
    from synaptipy.shared.theme_manager import ThemeMode, apply_theme

    # Pre-seed a known native style name.
    theme_manager._initial_style_name = "macintosh"

    with (
        patch.object(qapp, "setStyle") as mock_set_style,
        patch.object(qapp, "setStyleSheet"),
        patch.object(qapp, "setPalette"),
    ):
        apply_theme(ThemeMode.SYSTEM)

    mock_set_style.assert_called_once_with("macintosh")


def test_initial_style_name_captured_on_first_call(qapp):
    """_initial_style_name must be captured from app on the first apply_theme call."""
    from synaptipy.shared import theme_manager
    from synaptipy.shared.theme_manager import ThemeMode, apply_theme

    theme_manager._initial_style_name = None  # reset

    real_style_name = qapp.style().objectName()

    with patch.object(qapp, "setStyle"), patch.object(qapp, "setStyleSheet"), patch.object(qapp, "setPalette"):
        apply_theme(ThemeMode.DARK)

    assert theme_manager._initial_style_name == real_style_name


def test_apply_theme_system_clears_stylesheet(qapp):
    """apply_theme(SYSTEM) must call setStyleSheet('') to remove any custom CSS."""
    from synaptipy.shared import theme_manager
    from synaptipy.shared.theme_manager import ThemeMode, apply_theme

    theme_manager._initial_style_name = "fusion"

    with (
        patch.object(qapp, "setStyle"),
        patch.object(qapp, "setStyleSheet") as mock_ss,
        patch.object(qapp, "setPalette"),
    ):
        apply_theme(ThemeMode.SYSTEM)

    mock_ss.assert_called_once_with("")
