# tests/gui/test_cross_file_average.py
# -*- coding: utf-8 -*-
"""
Tests for the cross-file trial averaging feature in BaseAnalysisTab.

Covers:
- _get_cross_file_average: normal averaging, missing trials, mismatched lengths
- _populate_channel_and_source_comboboxes: "Cross-File Average" entry present
- _plot_selected_data: early-return when cross_file_average is selected
- _execute_cross_file_average_analysis: end-to-end integration via _trigger_analysis
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from Synaptipy.application.gui.analysis_tabs.metadata_driven import MetadataDrivenAnalysisTab
from Synaptipy.core.analysis.registry import AnalysisRegistry

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_channel(data_map, time_map):
    """Return a mock channel whose get_data / get_relative_time_vector use dicts."""
    ch = MagicMock()
    ch.get_data.side_effect = lambda idx: data_map.get(idx)
    ch.get_relative_time_vector.side_effect = lambda idx: time_map.get(idx)
    ch.num_trials = max(data_map.keys()) + 1 if data_map else 0
    ch.name = "Ch0"
    ch.units = "mV"
    return ch


def _make_recording(channel):
    """Return a mock Recording with a single channel keyed as 0."""
    rec = MagicMock()
    rec.channels = {0: channel}
    return rec


# ---------------------------------------------------------------------------
# Analysis registration fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def registered_passthrough():
    """Register a minimal passthrough analysis for the duration of the test."""
    name = "_cross_file_test_analysis"

    def _func(data, time, fs, **kwargs):
        return {"value": float(data[0])}

    decorator = AnalysisRegistry.register(
        name,
        label="Cross File Test",
        ui_params=[],
    )
    decorator(_func)
    yield name
    # Cleanup: remove after test so registry stays clean
    AnalysisRegistry._registry.pop(name, None)


# ---------------------------------------------------------------------------
# Tab fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def analysis_tab(qtbot, registered_passthrough, monkeypatch):
    """Create a MetadataDrivenAnalysisTab with heavy pyqtgraph bits mocked out."""
    monkeypatch.setattr(
        "Synaptipy.application.gui.analysis_tabs.base.BaseAnalysisTab._setup_plot_area",
        MagicMock(),
    )
    neo_adapter = MagicMock()
    tab = MetadataDrivenAnalysisTab(registered_passthrough, neo_adapter)
    qtbot.addWidget(tab)
    return tab


# ---------------------------------------------------------------------------
# Tests for _get_cross_file_average
# ---------------------------------------------------------------------------


class TestGetCrossFileAverage:
    def test_two_files_same_length(self, analysis_tab):
        """Grand average of two identical-length traces is correct."""
        t = np.linspace(0, 1, 100)
        d_a = np.ones(100) * 2.0
        d_b = np.ones(100) * 4.0

        ch_a = _make_channel({0: d_a}, {0: t.copy()})
        ch_b = _make_channel({0: d_b}, {0: t.copy()})
        rec_a = _make_recording(ch_a)
        rec_b = _make_recording(ch_b)

        analysis_tab.neo_adapter.read_recording.side_effect = [rec_a, rec_b]
        analysis_tab._analysis_items = [
            {"path": Path("file_a.abf")},
            {"path": Path("file_b.abf")},
        ]

        time_out, avg_out, n = analysis_tab._get_cross_file_average([0], 0)

        assert n == 2
        assert len(time_out) == 100
        np.testing.assert_allclose(avg_out, 3.0)  # mean(2, 4) == 3

    def test_mismatched_lengths_nan_padded(self, analysis_tab):
        """Arrays of different lengths are NaN-padded to the longest; nanmean used."""
        t_long = np.linspace(0, 1, 200)
        t_short = np.linspace(0, 0.5, 80)
        d_long = np.ones(200) * 1.0
        d_short = np.ones(80) * 3.0

        ch_a = _make_channel({0: d_long}, {0: t_long})
        ch_b = _make_channel({0: d_short}, {0: t_short})
        analysis_tab.neo_adapter.read_recording.side_effect = [
            _make_recording(ch_a),
            _make_recording(ch_b),
        ]
        analysis_tab._analysis_items = [
            {"path": Path("long.abf")},
            {"path": Path("short.abf")},
        ]

        _, avg_out, n = analysis_tab._get_cross_file_average([0], 0)

        assert n == 2
        # Result length equals the longest trace
        assert len(avg_out) == 200
        # First 80 samples: both files contribute, mean(1, 3) == 2
        np.testing.assert_allclose(avg_out[:80], 2.0)
        # Remaining 120 samples: only the long file contributes, nanmean == 1
        np.testing.assert_allclose(avg_out[80:], 1.0)

    def test_missing_trial_skipped(self, analysis_tab):
        """File missing the requested trial is silently skipped."""
        t = np.linspace(0, 1, 50)
        d_good = np.ones(50) * 5.0

        ch_good = _make_channel({20: d_good}, {20: t.copy()})
        # ch_bad has no trial index 20 — get_data raises IndexError
        ch_bad = MagicMock()
        ch_bad.get_data.side_effect = IndexError("no such trial")
        ch_bad.get_relative_time_vector.side_effect = IndexError("no such trial")

        analysis_tab.neo_adapter.read_recording.side_effect = [
            _make_recording(ch_good),
            _make_recording(ch_bad),
        ]
        analysis_tab._analysis_items = [
            {"path": Path("good.abf")},
            {"path": Path("bad.abf")},
        ]

        time_out, avg_out, n = analysis_tab._get_cross_file_average([20], 0)

        # Only the good file contributes
        assert n == 1
        np.testing.assert_allclose(avg_out, 5.0)

    def test_all_files_missing_trial_returns_none(self, analysis_tab):
        """Returns (None, None, 0) when no file can supply the trial."""
        ch = MagicMock()
        ch.get_data.return_value = None
        ch.get_relative_time_vector.return_value = None

        analysis_tab.neo_adapter.read_recording.return_value = _make_recording(ch)
        analysis_tab._analysis_items = [{"path": Path("a.abf")}, {"path": Path("b.abf")}]

        time_out, avg_out, n = analysis_tab._get_cross_file_average([0], 0)

        assert n == 0
        assert time_out is None
        assert avg_out is None

    def test_channel_index_out_of_range_skipped(self, analysis_tab):
        """File with fewer channels than requested is silently skipped."""
        rec = MagicMock()
        rec.channels = {}  # no channels at all
        analysis_tab.neo_adapter.read_recording.return_value = rec
        analysis_tab._analysis_items = [{"path": Path("narrow.abf")}]

        _, _, n = analysis_tab._get_cross_file_average([0], channel_idx=5)
        assert n == 0

    def test_multi_trial_within_file_averaged(self, analysis_tab):
        """Multiple parsed_trials from a single file are averaged then included."""
        t = np.linspace(0, 1, 100)
        ch = _make_channel(
            {0: np.ones(100) * 1.0, 1: np.ones(100) * 3.0},
            {0: t.copy(), 1: t.copy()},
        )
        analysis_tab.neo_adapter.read_recording.return_value = _make_recording(ch)
        analysis_tab._analysis_items = [{"path": Path("multi.abf")}]

        _, avg_out, n = analysis_tab._get_cross_file_average([0, 1], 0)

        assert n == 1
        np.testing.assert_allclose(avg_out, 2.0)  # mean(1, 3)


# ---------------------------------------------------------------------------
# Tests for combobox population
# ---------------------------------------------------------------------------


class TestComboboxPopulation:
    def test_cross_file_average_present_after_populate(self, analysis_tab):
        """'Cross-File Average' item with correct userData is always added."""
        # Build a minimal recording with one channel and one trial
        t = np.linspace(0, 1, 10)
        d = np.ones(10)
        ch = _make_channel({0: d}, {0: t})
        rec = MagicMock()
        rec.channels = {0: ch}

        analysis_tab._selected_item_recording = rec
        analysis_tab._analysis_items = [{"path": Path("x.abf"), "target_type": "Recording"}]
        analysis_tab._selected_item_index = 0

        # _setup_plot_navigation_controls is normally called from _setup_plot_area
        # (which is mocked).  Provide stub button widgets so _update_nav_buttons_state
        # does not raise AttributeError.
        from PySide6 import QtWidgets as _QW

        analysis_tab.prev_trial_btn = _QW.QPushButton()
        analysis_tab.next_trial_btn = _QW.QPushButton()

        # Simulate combobox being present (they are set up in _setup_data_selection_ui)
        assert analysis_tab.data_source_combobox is not None
        analysis_tab.data_source_combobox.setEnabled(True)
        analysis_tab.signal_channel_combobox.setEnabled(True)

        analysis_tab._populate_channel_and_source_comboboxes()

        all_data = [
            analysis_tab.data_source_combobox.itemData(i) for i in range(analysis_tab.data_source_combobox.count())
        ]
        assert "cross_file_average" in all_data


# ---------------------------------------------------------------------------
# Tests for _plot_selected_data early-return
# ---------------------------------------------------------------------------


class TestPlotSelectedDataCrossFile:
    def test_early_return_no_crash(self, analysis_tab):
        """Selecting Cross-File Average in the combobox must not raise."""
        # Add the option manually if no recording is loaded
        analysis_tab.data_source_combobox.addItem("Cross-File Average", "cross_file_average")
        idx = analysis_tab.data_source_combobox.findData("cross_file_average")
        analysis_tab.data_source_combobox.setCurrentIndex(idx)
        analysis_tab.data_source_combobox.setEnabled(True)
        analysis_tab.signal_channel_combobox.addItem("Ch0", 0)
        analysis_tab.signal_channel_combobox.setEnabled(True)

        # Attach a mock plot_widget so title update doesn't fail
        analysis_tab.plot_widget = MagicMock()

        # Should return early without raising
        analysis_tab._plot_selected_data()

        analysis_tab.plot_widget.setTitle.assert_called_once_with("Cross-File Average - Run analysis to compute")


# ---------------------------------------------------------------------------
# Integration: _trigger_analysis routes to cross-file path
# ---------------------------------------------------------------------------


class TestTriggerAnalysisCrossFileIntercept:
    def test_intercept_called_when_cross_file_selected(self, analysis_tab):
        """_trigger_analysis calls _execute_cross_file_average_analysis when mode active."""
        analysis_tab.data_source_combobox.addItem("Cross-File Average", "cross_file_average")
        idx = analysis_tab.data_source_combobox.findData("cross_file_average")
        analysis_tab.data_source_combobox.setCurrentIndex(idx)
        analysis_tab.data_source_combobox.setEnabled(True)
        analysis_tab.signal_channel_combobox.addItem("Ch0", 0)
        analysis_tab.signal_channel_combobox.setEnabled(True)

        with patch.object(analysis_tab, "_execute_cross_file_average_analysis", wraps=lambda _p: None) as mock_exec:
            # _gather_analysis_parameters must return a non-empty dict for the intercept to proceed
            with patch.object(analysis_tab, "_gather_analysis_parameters", return_value={"dummy": 1}):
                analysis_tab._trigger_analysis()

        mock_exec.assert_called_once()

    def test_normal_path_skipped_when_cross_file(self, analysis_tab):
        """Standard _execute_core_analysis is NOT called directly from _trigger_analysis."""
        analysis_tab.data_source_combobox.addItem("Cross-File Average", "cross_file_average")
        idx = analysis_tab.data_source_combobox.findData("cross_file_average")
        analysis_tab.data_source_combobox.setCurrentIndex(idx)
        analysis_tab.data_source_combobox.setEnabled(True)

        with patch.object(analysis_tab, "_execute_cross_file_average_analysis", return_value=None):
            with patch.object(analysis_tab, "_gather_analysis_parameters", return_value={"dummy": 1}):
                with patch.object(analysis_tab, "_execute_core_analysis") as mock_core:
                    analysis_tab._trigger_analysis()

        # _execute_core_analysis is NOT called by _trigger_analysis directly;
        # it is only called from within _execute_cross_file_average_analysis
        # (which is mocked to a no-op here).
        mock_core.assert_not_called()
