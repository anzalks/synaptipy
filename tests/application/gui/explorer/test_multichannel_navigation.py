"""
Tests for multi-channel plot rebuild and repeated navigation.

Regression guard for:
  - SIGBUS caused by gc.collect() inside Qt signal handler on macOS
    (PySide6 >= 6.7) when navigating between files with multiple channels.
  - Lambda closure bug: sigXRangeChanged lambdas must use default-arg capture
    (pid=plot_id) so each VB emits the correct channel id after rebuild.
  - autoRange() re-entrancy: _handle_preprocessing_reset must not call
    plot.autoRange() per channel (fires sigXRangeChanged without
    _updating_viewranges guard -> cascade -> SIGBUS on large files).
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest
from PySide6 import QtWidgets

from Synaptipy.application.gui.explorer.explorer_tab import ExplorerTab
from Synaptipy.application.gui.explorer.plot_canvas import ExplorerPlotCanvas
from Synaptipy.core.data_model import Channel, Recording
from Synaptipy.infrastructure.exporters.nwb_exporter import NWBExporter
from Synaptipy.infrastructure.file_readers import NeoAdapter


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_recording(name: str, num_channels: int, num_trials: int, duration: float = 1.0):
    """Create a mock Recording with *num_channels* channels, each with *num_trials* trials."""
    rec = MagicMock(spec=Recording)
    rec.source_file = Path(name)
    rec.duration = duration
    rec.sampling_rate = 10_000.0
    rec.max_trials = num_trials

    t = np.linspace(0, duration, int(duration * 10_000))
    d = np.sin(2 * np.pi * 10 * t)

    channels = {}
    for i in range(num_channels):
        cid = f"ch{i}"
        ch = MagicMock(spec=Channel)
        ch.name = cid
        ch.units = "mV"
        ch.num_trials = num_trials
        ch.sampling_rate = 10_000.0
        ch.get_data.return_value = d.copy()
        ch.get_relative_time_vector.return_value = t.copy()
        ch.get_averaged_data.return_value = d.copy()
        channels[cid] = ch

    rec.channels = channels
    return rec


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def nav_explorer_tab(qapp):
    """Session-scoped ExplorerTab for navigation tests."""
    neo_adapter = MagicMock(spec=NeoAdapter)
    nwb_exporter = MagicMock(spec=NWBExporter)
    status_bar = QtWidgets.QStatusBar()
    tab = ExplorerTab(neo_adapter, nwb_exporter, status_bar)
    tab.thread_pool = MagicMock()
    yield tab
    # os._exit(0) at session end skips teardown — no explicit cleanup needed.


@pytest.fixture(autouse=True)
def _reset_nav_tab(nav_explorer_tab):
    nav_explorer_tab._pending_view_state = None
    nav_explorer_tab._pending_trial_params = None
    nav_explorer_tab.selected_trial_indices = set()
    nav_explorer_tab._is_loading = False
    yield


# ---------------------------------------------------------------------------
# Tests: basic multi-channel rebuild
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("num_channels", [1, 2, 4])
def test_rebuild_plots_creates_correct_channel_count(nav_explorer_tab, num_channels):
    """rebuild_plots must create exactly one PlotItem per channel."""
    rec = _make_recording("test.wcp", num_channels=num_channels, num_trials=5)
    nav_explorer_tab._display_recording(rec)

    assert len(nav_explorer_tab.plot_canvas.channel_plots) == num_channels
    for i in range(num_channels):
        assert f"ch{i}" in nav_explorer_tab.plot_canvas.channel_plots


@pytest.mark.parametrize("num_channels", [1, 2, 4])
def test_rebuild_plots_repeated_no_crash(nav_explorer_tab, num_channels):
    """Calling _display_recording repeatedly must not crash (SIGBUS regression)."""
    rec = _make_recording("test.wcp", num_channels=num_channels, num_trials=10)
    for _ in range(5):
        nav_explorer_tab._display_recording(rec)

    assert len(nav_explorer_tab.plot_canvas.channel_plots) == num_channels


# ---------------------------------------------------------------------------
# Tests: multi-channel → single-channel navigation and back
# ---------------------------------------------------------------------------

def test_navigate_multichannel_to_single_and_back(nav_explorer_tab):
    """
    Navigate: 4-ch recording → 1-ch recording → 4-ch recording
    Must not crash and channel_plots must reflect the new recording each time.
    """
    rec4 = _make_recording("four_ch.wcp", num_channels=4, num_trials=20)
    rec1 = _make_recording("one_ch.wcp", num_channels=1, num_trials=5)

    nav_explorer_tab._display_recording(rec4)
    assert len(nav_explorer_tab.plot_canvas.channel_plots) == 4

    nav_explorer_tab._display_recording(rec1)
    assert len(nav_explorer_tab.plot_canvas.channel_plots) == 1

    nav_explorer_tab._display_recording(rec4)
    assert len(nav_explorer_tab.plot_canvas.channel_plots) == 4


def test_navigate_many_files_no_crash(nav_explorer_tab):
    """Simulate cycling through 10 files with varying channel counts."""
    configs = [4, 1, 2, 4, 2, 1, 4, 3, 1, 4]
    for i, n in enumerate(configs):
        rec = _make_recording(f"file_{i}.wcp", num_channels=n, num_trials=20)
        nav_explorer_tab._display_recording(rec)
        assert len(nav_explorer_tab.plot_canvas.channel_plots) == n


# ---------------------------------------------------------------------------
# Tests: sigXRangeChanged lambda closure correctness
# ---------------------------------------------------------------------------

def test_xrange_signal_contains_correct_channel_id(qapp, qtbot):
    """
    sigXRangeChanged emitted from each ViewBox must carry the correct channel id.

    Regression for: lambda _, range: emit(plot_id, range) — late-binding bug
    where all lambdas in a rebuild loop capture the *same* plot_id from the
    enclosing scope, so all emit the last channel id.

    Uses a standalone ExplorerPlotCanvas (no XLink) so each setXRange is
    independent and the emitted cid is unambiguous.
    """
    canvas = ExplorerPlotCanvas()
    rec = _make_recording("sig_test.wcp", num_channels=4, num_trials=5)
    canvas.rebuild_plots(rec)

    received: list = []

    def _collector(cid, r):
        received.append((cid, round(r[0], 4)))

    canvas.x_range_changed.connect(_collector)
    try:
        # Unlink all so each setXRange is independent (no cascade confusion)
        plots = list(canvas.channel_plots.values())
        for p in plots:
            p.getViewBox().setXLink(None)

        unique_ranges = {
            "ch0": (0.10, 0.20),
            "ch1": (0.30, 0.40),
            "ch2": (0.50, 0.60),
            "ch3": (0.70, 0.80),
        }
        for cid, (xmin, xmax) in unique_ranges.items():
            canvas.channel_plots[cid].setXRange(xmin, xmax, padding=0)
            qtbot.wait(10)

        # Every unique xmin we set should map to the correct cid
        received_map = {r: c for c, r in received}  # xmin -> emitted_cid
        for cid, (xmin, _) in unique_ranges.items():
            key = round(xmin, 4)
            assert key in received_map, (
                f"No x_range_changed emission received for channel '{cid}' "
                f"with xmin={xmin}.  Lambda may not be connected."
            )
            emitted_cid = received_map[key]
            assert emitted_cid == cid, (
                f"Channel '{cid}': x_range_changed emitted cid='{emitted_cid}'. "
                "Lambda closure bug: use pid=plot_id default-arg capture."
            )
    finally:
        canvas.x_range_changed.disconnect(_collector)
        # Clear plots so all pending ViewBox callbacks fire while C++ objects
        # are still alive.  Without this the global processEvents() drain runs
        # after this test and executes stale callbacks against freed objects
        # causing an access-violation on Windows.
        canvas.clear_plots()


# ---------------------------------------------------------------------------
# Tests: platform-gated gc drain in clear_plots / rebuild_plots
# ---------------------------------------------------------------------------

def test_clear_plots_no_gc_on_darwin():
    """
    On macOS, clear_plots() must NOT call gc.collect() (SIGBUS regression).
    On other platforms it's allowed.  This test only enforces the darwin guard.
    """
    if sys.platform != 'darwin':
        pytest.skip("macOS-specific regression test")

    import unittest.mock as mock

    canvas = ExplorerPlotCanvas()
    rec = _make_recording("gc_test.wcp", num_channels=2, num_trials=3)
    # Populate the canvas first so clear_plots has something to clear.
    canvas.rebuild_plots(rec)

    with mock.patch('gc.collect') as mock_gc:
        canvas.clear_plots()

    mock_gc.assert_not_called(), (
        "gc.collect() must not be called from clear_plots() on macOS — "
        "races with PySide6 tp_dealloc -> SIGBUS."
    )
    # Canvas is already cleared; explicit no-op for symmetry with other tests.
    canvas.clear_plots()


def test_rebuild_plots_no_gc_on_darwin():
    """
    On macOS, rebuild_plots() must NOT call gc.collect() (SIGBUS regression).
    """
    if sys.platform != 'darwin':
        pytest.skip("macOS-specific regression test")

    import unittest.mock as mock

    canvas = ExplorerPlotCanvas()
    rec = _make_recording("gc_test2.wcp", num_channels=3, num_trials=5)

    with mock.patch('gc.collect') as mock_gc:
        canvas.rebuild_plots(rec)

    mock_gc.assert_not_called(), (
        "gc.collect() must not be called from rebuild_plots() on macOS — "
        "races with PySide6 tp_dealloc -> SIGBUS."
    )
    # Clear so no stale callbacks remain for the global processEvents() drain.
    canvas.clear_plots()
