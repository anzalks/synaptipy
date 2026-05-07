import importlib
from unittest.mock import MagicMock

import pytest
from PySide6 import QtWidgets

from Synaptipy.application.gui.analyser_tab import AnalyserTab
from Synaptipy.infrastructure.file_readers import NeoAdapter


@pytest.fixture
def app(qapp):
    return qapp


@pytest.fixture
def mock_neo_adapter():
    adapter = MagicMock(spec=NeoAdapter)
    return adapter


@pytest.fixture(autouse=True)
def _ensure_registry_populated():
    """Ensure all built-in analysis modules are registered.

    Other test modules (test_registry_metadata.py) use an autouse fixture that
    clears the registry before each test. When pytest collects tests from both
    files in the same session, the clear runs *after* module-level imports have
    already executed the @register decorators, leaving the registry empty for
    subsequent tests.  Reloading every analysis sub-module here re-executes the
    decorators and repopulates the registry so the GUI tests see all 15 analyses.
    """
    import Synaptipy.core.analysis.evoked_responses as m4
    import Synaptipy.core.analysis.firing_dynamics as m2
    import Synaptipy.core.analysis.passive_properties as m0
    import Synaptipy.core.analysis.single_spike as m1
    import Synaptipy.core.analysis.synaptic_events as m3

    for module in (m0, m1, m2, m3, m4):
        importlib.reload(module)


def test_analyser_tab_init(qtbot, mock_neo_adapter, monkeypatch):
    """Test that AnalyserTab initializes without error."""
    # Prevent heavy pyqtgraph instantiation to avoid macOS SIGABRT in offscreen runner
    monkeypatch.setattr(AnalyserTab, "_load_analysis_tabs", MagicMock())
    tab = AnalyserTab(neo_adapter=mock_neo_adapter)
    qtbot.addWidget(tab)
    assert tab is not None
    assert isinstance(tab, QtWidgets.QWidget)
    assert tab.sub_tab_widget is not None
    # Verify batch analysis button exists
    assert hasattr(tab, "batch_analysis_btn")
    assert tab.batch_analysis_btn is not None


def test_analyser_tab_loads_analysis_tabs(qtbot, mock_neo_adapter, monkeypatch):
    """Regression test: AnalyserTab must load at least one analysis tab on all
    platforms including Windows.

    Root cause of the Windows bug: _load_analysis_tabs() imported only
    ``Synaptipy.core.analysis.registry`` (the registry class), which does NOT
    execute the package __init__.py and therefore never calls
    ``from . import basic_features`` etc.  The registry stayed empty and
    no metadata-driven tabs were created.  The fix imports the full
    ``Synaptipy.core.analysis`` package before calling list_registered().
    """
    # Suppress heavy pyqtgraph plot-area creation to stay safe in offscreen mode
    monkeypatch.setattr("Synaptipy.application.gui.analysis_tabs.base.BaseAnalysisTab._setup_plot_area", MagicMock())
    tab = AnalyserTab(neo_adapter=mock_neo_adapter)
    qtbot.addWidget(tab)
    n_tabs = len(tab._loaded_analysis_tabs)
    assert n_tabs > 0, (
        f"AnalyserTab loaded {n_tabs} analysis sub-tabs (expected > 0). "
        "This is the Windows-specific bug where importing only "
        "registry.py leaves the AnalysisRegistry empty. "
        "The fix is: 'import Synaptipy.core.analysis' (full package) in "
        "_load_analysis_tabs() before calling list_registered()."
    )


def test_cursor_group_box_present(qtbot, mock_neo_adapter, monkeypatch):
    """BaseAnalysisTab._setup_cursor_group() must create a QGroupBox titled
    'Interactive Cursor' and add it to the supplied layout.

    We call the method directly on a minimal stub to avoid heavy pyqtgraph
    initialisation in offscreen mode.
    """
    from Synaptipy.application.gui.analysis_tabs.base import BaseAnalysisTab

    monkeypatch.setattr(
        "Synaptipy.application.gui.analysis_tabs.base.BaseAnalysisTab._setup_plot_area", MagicMock()
    )

    class _StubTab(BaseAnalysisTab):
        def get_display_name(self) -> str:
            return "Stub"

        def _setup_ui(self):
            pass

        def _plot_selected_data(self):
            pass

        def _trigger_analysis(self):
            pass

        def _load_analysis_tab_settings(self):
            pass

        def _save_analysis_tab_settings(self):
            pass

        def _build_ui(self, layout):
            pass

    tab = _StubTab(neo_adapter=mock_neo_adapter)
    qtbot.addWidget(tab)

    container = QtWidgets.QWidget()
    layout = QtWidgets.QVBoxLayout(container)
    tab._setup_cursor_group(layout)

    group_boxes = container.findChildren(QtWidgets.QGroupBox)
    titles = [gb.title() for gb in group_boxes]
    assert "Interactive Cursor" in titles, (
        f"Expected a QGroupBox titled 'Interactive Cursor', found: {titles}. "
        "Check that _setup_cursor_group() adds the group box correctly."
    )
