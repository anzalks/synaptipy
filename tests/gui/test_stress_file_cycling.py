# tests/gui/test_stress_file_cycling.py
# -*- coding: utf-8 -*-
"""
UI stress tests: rapid file cycling and debounce validation.

These tests deliberately torture the plot-canvas rebuild path to expose
race conditions or C++ lifecycle bugs that only appear under rapid usage.

Platform notes
--------------
* All tests run in offscreen mode (QT_QPA_PLATFORM=offscreen set by CI).
* macOS: drain fixtures skipped; _unlink_all_plots + correct clear() order
  guard teardown (see conftest._drain_qt_events_after_test rationale).
* Win/Linux: the global autouse fixture in conftest drains posted events
  after every test with removePostedEvents().
"""

import sys
from pathlib import Path

import numpy as np
import pytest
from PySide6 import QtCore, QtWidgets  # noqa: F401

from Synaptipy.core.data_model import Channel, Recording
from Synaptipy.application.gui.explorer.plot_canvas import ExplorerPlotCanvas


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_recording(num_channels: int, num_trials: int = 3) -> Recording:
    """Build a lightweight synthetic Recording with *num_channels* channels."""
    rec = Recording(source_file=Path(f"synthetic_{num_channels}ch.abf"))
    t = np.linspace(0, 0.1, 1000)
    data = np.sin(2 * np.pi * 50 * t)  # 50 Hz sine, 100 ms, 10 kHz
    for ch_idx in range(num_channels):
        ch = Channel(
            id=str(ch_idx),
            name=f"Ch{ch_idx}",
            units="mV",
            sampling_rate=10_000.0,
            data_trials=[data.copy() for _ in range(num_trials)],
        )
        rec.channels[str(ch_idx)] = ch
    return rec


# ---------------------------------------------------------------------------
# Session-scoped canvas (one GraphicsLayoutWidget reused across all stress
# iterations — matches the in-app usage pattern).
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def stress_canvas(qapp):
    """Session-scoped ExplorerPlotCanvas for stress tests."""
    canvas = ExplorerPlotCanvas()
    yield canvas
    # Final teardown: clear before session ends.
    canvas.clear()


@pytest.fixture(autouse=True)
def _drain_after_stress_test(stress_canvas):
    """Per-test drain (Win/Linux only) — mirrors the global conftest pattern."""
    # Pre-test: clean slate.
    stress_canvas.clear()
    yield
    if sys.platform == 'darwin':
        return
    try:
        QtCore.QCoreApplication.removePostedEvents(None, 0)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Test 1 — Rapid rebuild: same channel count
# ---------------------------------------------------------------------------

class TestRapidRebuildSameChannelCount:
    """Cycle rebuild_plots 100× on recordings with the same channel layout."""

    ITERATIONS = 100
    NUM_CHANNELS = 3

    def test_no_crash_same_layout(self, stress_canvas):
        """100 rapid rebuild_plots calls must not crash or leak plot items."""
        rec = _make_recording(self.NUM_CHANNELS)
        for i in range(self.ITERATIONS):
            keys = stress_canvas.rebuild_plots(rec)
            assert len(keys) == self.NUM_CHANNELS, (
                f"Iteration {i}: expected {self.NUM_CHANNELS} channel keys, got {len(keys)}"
            )
        # Post condition: canvas tracking state is consistent.
        assert len(stress_canvas.plot_items) == self.NUM_CHANNELS
        assert len(stress_canvas.plot_widgets) == self.NUM_CHANNELS


# ---------------------------------------------------------------------------
# Test 2 — Rapid rebuild: alternating channel counts (stress the stretch-
# factor reset / ghost-row logic on Windows)
# ---------------------------------------------------------------------------

class TestRapidRebuildAlternatingChannelCount:
    """Alternate between a 2-channel and a 4-channel recording 50 times each."""

    ITERATIONS = 50

    def test_no_crash_alternating_layout(self, stress_canvas):
        """Alternating rebuild_plots calls with different channel counts."""
        rec2 = _make_recording(2)
        rec4 = _make_recording(4)
        for i in range(self.ITERATIONS):
            rec = rec2 if (i % 2 == 0) else rec4
            expected_n = 2 if (i % 2 == 0) else 4
            keys = stress_canvas.rebuild_plots(rec)
            assert len(keys) == expected_n, (
                f"Iteration {i}: expected {expected_n} channel keys, got {len(keys)}"
            )
        # Final state: last rec4 (even last index = 49, so rec2)
        # Just verify the count matches whatever was last.
        last_expected = 2 if ((self.ITERATIONS - 1) % 2 == 0) else 4
        assert len(stress_canvas.plot_items) == last_expected


# ---------------------------------------------------------------------------
# Test 3 — Clear on empty recording must not crash
# ---------------------------------------------------------------------------

def test_rebuild_empty_recording(stress_canvas):
    """rebuild_plots(empty Recording) must return [] without crashing."""
    empty_rec = _make_recording(0)
    keys = stress_canvas.rebuild_plots(empty_rec)
    assert keys == []
    assert len(stress_canvas.plot_items) == 0


def test_rebuild_none_recording(stress_canvas):
    """rebuild_plots(None) must return [] without crashing."""
    keys = stress_canvas.rebuild_plots(None)
    assert keys == []


# ---------------------------------------------------------------------------
# Test 4 — XLink stress: many channels all linked, then cleared
# ---------------------------------------------------------------------------

def test_xlink_stress(stress_canvas):
    """8-channel rebuild 50× to stress the X-axis link/unlink cycle."""
    rec = _make_recording(8)
    for i in range(50):
        keys = stress_canvas.rebuild_plots(rec)
        assert len(keys) == 8, f"Iteration {i}: got {len(keys)} channel keys"
    assert len(stress_canvas.plot_items) == 8


# ---------------------------------------------------------------------------
# Test 5 — Debounce timer coalesces rapid nav calls
# ---------------------------------------------------------------------------

class TestFileNavDebounceTimer:
    """Verify the QTimer debounce pattern fires exactly once per burst.

    This test validates the debounce mechanism in isolation using a raw QTimer
    (the same pattern used in ExplorerTab._file_nav_timer) rather than
    instantiating the full ExplorerTab which requires many heavy dependencies.
    """

    def test_rapid_starts_coalesced_to_one_fire(self, qapp, qtbot):
        """Starting a single-shot QTimer N times quickly fires it exactly once."""
        call_count = [0]
        timer = QtCore.QTimer()
        timer.setSingleShot(True)
        timer.setInterval(40)  # 40 ms
        timer.timeout.connect(lambda: call_count.__setitem__(0, call_count[0] + 1))

        # Simulate 20 rapid navigation clicks — each restarts the timer.
        for _ in range(20):
            timer.start()

        # Wait well past the interval.
        qtbot.wait(200)

        assert call_count[0] == 1, (
            f"Timer fired {call_count[0]} times; expected exactly 1 (debounce coalesces bursts)"
        )

    def test_separate_bursts_fire_separately(self, qapp, qtbot):
        """Two distinct bursts separated by more than the interval fire twice."""
        call_count = [0]
        timer = QtCore.QTimer()
        timer.setSingleShot(True)
        timer.setInterval(40)
        timer.timeout.connect(lambda: call_count.__setitem__(0, call_count[0] + 1))

        # First burst.
        for _ in range(5):
            timer.start()
        # Let it fire.
        qtbot.wait(150)
        assert call_count[0] == 1, "First burst should have fired once"

        # Second burst.
        for _ in range(5):
            timer.start()
        qtbot.wait(150)
        assert call_count[0] == 2, "Second burst should have fired once more"
