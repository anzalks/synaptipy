
import sys
import pytest
from unittest.mock import MagicMock
from pathlib import Path
from PySide6 import QtWidgets
from PySide6.QtCore import QCoreApplication
import numpy as np

from Synaptipy.application.gui.explorer.explorer_tab import ExplorerTab
from Synaptipy.infrastructure.file_readers import NeoAdapter
from Synaptipy.infrastructure.exporters.nwb_exporter import NWBExporter
from Synaptipy.core.data_model import Recording, Channel


@pytest.fixture(scope="session")
def explorer_tab(qapp):
    """Session-scoped ExplorerTab to avoid PlotItem teardown crashes.

    scope="module" tears down between test modules, corrupting Qt state
    for any subsequent module that creates a PlotItem.  scope="session"
    defers teardown to session-end, which os._exit(0) skips entirely.
    """
    neo_adapter = MagicMock(spec=NeoAdapter)
    nwb_exporter = MagicMock(spec=NWBExporter)
    status_bar = QtWidgets.QStatusBar()

    tab = ExplorerTab(neo_adapter, nwb_exporter, status_bar)
    yield tab
    # No teardown — session-end is handled by os._exit(0).


@pytest.fixture(autouse=True)
def reset_explorer_tab_state(explorer_tab):
    """Reset ExplorerTab state before each test for isolation."""
    explorer_tab._pending_view_state = None
    explorer_tab._pending_trial_params = None
    explorer_tab._current_trial_selection_params = None
    explorer_tab.selected_trial_indices = set()
    explorer_tab._is_loading = False
    # Reset file-nav debounce state introduced in the debounce PR.
    explorer_tab._pending_nav_target = None
    if hasattr(explorer_tab, '_file_nav_timer'):
        explorer_tab._file_nav_timer.stop()
    try:
        explorer_tab.toolbar.lock_zoom_cb.setChecked(False)
    except Exception:
        pass
    yield
    # Drain any pending Qt events queued during the test (e.g. from zoom
    # changes, sidebar signals, lock_zoom_cb toggles).  Use removePostedEvents
    # rather than processEvents: the former cancels queued events (safe, no code
    # executed) while the latter executes them and can cause re-entrant crashes
    # on Windows in offscreen mode with PySide6 >= 6.7.
    #
    # macOS guard: pyqtgraph keeps live state in its AllViews registry and
    # geometry caches via posted events between tests.  Discarding them on macOS
    # corrupts that state and causes the next rebuild_plots() to segfault or
    # mis-render.  This mirrors the documented rule from copilot-instructions.md
    # and the behaviour of all other per-test drain fixtures in this repo.
    if sys.platform == 'darwin':
        return
    try:
        from PySide6.QtCore import QCoreApplication
        QCoreApplication.removePostedEvents(None, 0)
    except Exception:
        pass


def create_mock_recording(name="test.wcp", duration=1.0, channels=["ch1"]):
    recording = MagicMock(spec=Recording)
    recording.source_file = Path(name)
    # recording.source_file.name is already correct from Path(name)
    recording.duration = duration
    recording.sampling_rate = 1000.0
    recording.max_trials = 10

    recording.channels = {}
    for c_name in channels:
        channel = MagicMock(spec=Channel)
        channel.name = c_name
        channel.units = "mV"
        channel.num_trials = 10
        channel.sampling_rate = 1000.0

        # Correctly mock data retrieval
        t = np.linspace(0, duration, int(duration * 1000))
        d = np.zeros_like(t)
        channel.get_data.return_value = d
        channel.get_relative_time_vector.return_value = t
        channel.get_averaged_data.return_value = d

        recording.channels[c_name] = channel

    return recording


def test_preserve_state_on_cycle(explorer_tab):
    """
    Verify that view state (zoom) and trial selection parameters are preserved
    when 'preserve_state=True' is used during file loading.
    """
    # 1. Setup Initial State with File A
    rec_a = create_mock_recording("FileA.wcp")
    rec_a = create_mock_recording("FileA.wcp")
    # Removed MagicMock of rebuild_plots to allow real plot creation
    # Actually we want real plots to test ViewBox state.
    # But explorer_tab._display_recording CALLS rebuild_plots.
    # We should let it run but maybe mock the heavy parts?
    # Let's rely on standard pg behavior, it works in test_explorer_refactor.py

    # We need to mock AnalysisWorker to avoid threads
    explorer_tab.thread_pool = MagicMock()

    # Manual load A
    explorer_tab._display_recording(rec_a)

    # Verify plot exists
    assert "ch1" in explorer_tab.plot_canvas.channel_plots
    plot_a = explorer_tab.plot_canvas.channel_plots["ch1"]
    plot_a.isVisible = MagicMock(return_value=True)  # Force visibility for capture logic check

    # 2. Modify State (Zoom in)
    target_x_range = (0.2, 0.4)
    target_y_range = (-5.0, 5.0)
    plot_a.setXRange(*target_x_range, padding=0)
    plot_a.setYRange(*target_y_range, padding=0)
    # Let Qt process deferred geometry callbacks so the ViewBox
    # actually commits the requested range before we capture it.
    QCoreApplication.processEvents()
    explorer_tab.toolbar.lock_zoom_cb.setChecked(True)

    # Set Trial Selection (Every 2nd trial)
    gap_n = 1  # Every 2nd
    start_idx = 0
    explorer_tab._on_trial_selection_requested(gap_n, start_idx)
    assert explorer_tab._current_trial_selection_params == (gap_n, start_idx)

    # 3. Simulate Cycling to File B (preserve_state=True)
    rec_b = create_mock_recording("FileB.wcp")
    file_list = [Path("FileA.wcp"), Path("FileB.wcp")]

    # Call load_recording_data to trigger CAPTURE
    explorer_tab.load_recording_data(rec_b.source_file, file_list, 1, preserve_state=True)

    # Verify State Captured
    assert explorer_tab._pending_view_state is not None
    assert "ch1" in explorer_tab._pending_view_state
    captured_x = explorer_tab._pending_view_state["ch1"][0]
    # Check approximately equal due to float precision
    assert abs(captured_x[0] - target_x_range[0]) < 0.01
    assert abs(captured_x[1] - target_x_range[1]) < 0.01

    assert explorer_tab._pending_trial_params == (gap_n, start_idx)

    # 4. Simulate Load Completion (RESTORE)
    # This calls _display_recording -> _update_plot
    explorer_tab._display_recording(rec_b)

    # 5. Verify State Restored
    plot_b = explorer_tab.plot_canvas.channel_plots["ch1"]  # Might be new object

    # Let Qt settle deferred geometry callbacks from rebuild_plots()
    # before checking viewRange().  This is an inline processEvents (not
    # a drain fixture) so it only runs events while the session-scoped
    # widget is alive — safe on all platforms.
    QCoreApplication.processEvents()

    # Verify View Range
    view_range_x = plot_b.viewRange()[0]
    view_range_y = plot_b.viewRange()[1]

    # Should match target, NOT default (0, 1.0)
    assert abs(view_range_x[0] - target_x_range[0]) < 0.01
    assert abs(view_range_x[1] - target_x_range[1]) < 0.01
    assert abs(view_range_y[0] - target_y_range[0]) < 0.01

    # Verify Trial Params restored
    assert explorer_tab._current_trial_selection_params == (gap_n, start_idx)
    # Check selection indices were recalculated (max trials 10, skip 1 -> 5 selected)
    assert len(explorer_tab.selected_trial_indices) == 5


def test_no_preserve_state_default(explorer_tab):
    """Verify that state is NOT preserved by default (or when opening new file manually)."""
    # 1. Setup
    rec_a = create_mock_recording("FileA.wcp")
    explorer_tab.thread_pool = MagicMock()
    explorer_tab._display_recording(rec_a)

    plot_a = explorer_tab.plot_canvas.channel_plots["ch1"]
    plot_a.setXRange(0.2, 0.4, padding=0)
    explorer_tab._on_trial_selection_requested(1, 0)

    # 2. Load File B WITHOUT preserve_state
    rec_b = create_mock_recording("FileB.wcp")
    explorer_tab.load_recording_data(rec_b.source_file, preserve_state=False)

    # Verify NO capture
    assert explorer_tab._pending_view_state is None
    assert explorer_tab._pending_trial_params is None

    # 3. Complete Load
    explorer_tab._display_recording(rec_b)

    # 4. Verify Reset
    plot_b = explorer_tab.plot_canvas.channel_plots["ch1"]
    # Let deferred geometry callbacks settle before checking viewRange().
    QCoreApplication.processEvents()
    view_range_x = plot_b.viewRange()[0]

    # Should be default range (0 to duration=1.0)
    assert view_range_x[0] <= 0.01
    assert view_range_x[1] >= 0.99

    assert explorer_tab._current_trial_selection_params is None
    assert len(explorer_tab.selected_trial_indices) == 0  # Reset to empty (all)


def test_preserve_state_on_sidebar_selection(explorer_tab):
    """Verify that selecting a file from the sidebar also preserves state."""
    # 1. Setup
    rec_a = create_mock_recording("FileA.wcp")
    explorer_tab.thread_pool = MagicMock()
    explorer_tab._display_recording(rec_a)

    # Modify State
    plot_a = explorer_tab.plot_canvas.channel_plots["ch1"]
    plot_a.isVisible = MagicMock(return_value=True)
    plot_a.setXRange(0.2, 0.4, padding=0)
    QCoreApplication.processEvents()
    explorer_tab.toolbar.lock_zoom_cb.setChecked(True)
    explorer_tab._on_trial_selection_requested(1, 0)  # Gap 1

    # 2. Emit Signal from Sidebar (simulate user double-click)
    rec_b = create_mock_recording("FileB.wcp")
    file_list = [Path("FileA.wcp"), Path("FileB.wcp")]

    # This should trigger the lambda with preserve_state=True
    explorer_tab.sidebar.file_selected.emit(rec_b.source_file, file_list, 1)

    # 3. Verify State Captured (Pending)
    # Since we mocked the thread pool, load_recording_data runs but worker start is instant/mocked.
    # But checking _pending_view_state confirms preserve_state=True was passed.
    assert explorer_tab._pending_view_state is not None
    assert explorer_tab._pending_trial_params == (1, 0)

    # 4. Finish Load
    explorer_tab._display_recording(rec_b)

    # 5. Verify Restored
    assert explorer_tab._current_trial_selection_params == (1, 0)
