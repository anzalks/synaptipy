# tests/gui/test_audit_55_analyser_dialogs_session.py
# -*- coding: utf-8 -*-
"""
Regression tests for Audit-55 fixes across Analyser tabs, SessionManager,
DataLoader, DataLoaderService, BatchAnalysisDialog, PreferencesDialog,
NwbMetadataDialog, and PlotSaveDialog.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pyqtgraph as pg
import pytest
from PySide6 import QtCore, QtWidgets

from synaptipy.application.data_loader import DataLoader
from synaptipy.application.data_loader import _physical_path as loader_physical_path
from synaptipy.application.gui.analyser_tab import AnalyserTab
from synaptipy.application.gui.analysis_tabs.base import BaseAnalysisTab
from synaptipy.application.gui.analysis_tabs.metadata_driven import MetadataDrivenAnalysisTab
from synaptipy.application.gui.batch_dialog import AddStepDialog, BatchAnalysisDialog
from synaptipy.application.gui.nwb_dialog import NwbMetadataDialog
from synaptipy.application.gui.plot_save_dialog import PlotSaveDialog
from synaptipy.application.gui.preferences_dialog import PreferencesDialog
from synaptipy.application.services.data_loader_service import DataLoaderService
from synaptipy.application.session_manager import SessionManager
from synaptipy.application.session_manager import _physical_path as session_physical_path
from synaptipy.core.analysis.registry import AnalysisRegistry
from synaptipy.core.data_model import Channel, Recording
from synaptipy.core.results import EventDetectionResult
from synaptipy.shared.constants import APP_NAME, SETTINGS_SECTION
from synaptipy.shared.plot_customization import get_plot_customization_signals


class _FakePlotItem:
    """Lightweight PlotItem stand-in for headless unit tests."""

    def __init__(self):
        self.items = []
        self.plotted = []
        self._x_range = [0.0, 1.0]
        self._y_range = [-80.0, 20.0]
        self.title = ""

    def addItem(self, item):
        if item not in self.items:
            self.items.append(item)

    def removeItem(self, item):
        if item in self.items:
            self.items.remove(item)

    def clear(self):
        self.items.clear()
        self.plotted.clear()

    def plot(self, x=None, y=None, **kwargs):
        curve = pg.PlotDataItem(x, y) if x is not None and y is not None else MagicMock()
        self.items.append(curve)
        self.plotted.append((x, y, kwargs))
        return curve

    def setLabel(self, *args, **kwargs):
        pass

    def setTitle(self, title):
        self.title = title

    def getAxis(self, _name):
        return MagicMock()

    def getViewBox(self):
        return None

    def autoRange(self):
        pass

    def viewRange(self):
        return [list(self._x_range), list(self._y_range)]

    def setXRange(self, x0, x1, padding=0):
        self._x_range = [float(x0), float(x1)]

    def setRange(self, xRange=None, yRange=None, padding=0):
        if xRange is not None:
            self._x_range = [float(xRange[0]), float(xRange[1])]
        if yRange is not None:
            self._y_range = [float(yRange[0]), float(yRange[1])]

    def listDataItems(self):
        return [it for it in self.items if isinstance(it, pg.PlotDataItem)]

    def scene(self):
        return None


def _make_synth_recording(
    source_file: Path | None = Path("/fake/rec.abf"),
    n_trials: int = 3,
    n_samples: int = 1000,
    fs: float = 10000.0,
    with_ttl: bool = False,
) -> Recording:
    rec = Recording(source_file=source_file)
    rec.sampling_rate = fs
    trials = [np.full(n_samples, -70.0 + i, dtype=float) for i in range(n_trials)]
    ch0 = Channel(id="0", name="Vm", units="mV", sampling_rate=fs, data_trials=trials)
    rec.channels["0"] = ch0
    if with_ttl:
        ttl_trials = []
        for i in range(n_trials):
            arr = np.zeros(n_samples, dtype=float)
            arr[100 + i * 5 : 150 + i * 5] = 5.0
            ttl_trials.append(arr)
        ch1 = Channel(id="1", name="TTL_Stim", units="V", sampling_rate=fs, data_trials=ttl_trials)
        rec.channels["1"] = ch1
    return rec


@pytest.fixture
def clean_registry_entries():
    """Track and clean up temporary AnalysisRegistry registrations created in a test."""
    created = []

    def _register(name, func, **meta):
        dec = AnalysisRegistry.register(name, **meta)
        dec(func)
        created.append(name)
        return name

    yield _register

    for name in created:
        AnalysisRegistry._registry.pop(name, None)
        AnalysisRegistry._metadata.pop(name, None)
        AnalysisRegistry._original_metadata.pop(name, None)


# ===========================================================================
# 1. metadata_driven.py: A6, A2, E1-gui, E2-gui, E3
# ===========================================================================


def test_a6_analysis_region_readded_on_data_plotted(qtbot, clean_registry_entries, monkeypatch):
    """A6: MetadataDrivenAnalysisTab._on_data_plotted calls super()._on_data_plotted()."""
    name = clean_registry_entries(
        "_test_a6_analysis",
        lambda data, time, fs, **kw: {"metrics": {"val": 1.0}},
        label="A6 Test",
        ui_params=[],
    )
    monkeypatch.setattr(BaseAnalysisTab, "_setup_plot_area", lambda self, layout, stretch_factor=1: None)
    tab = MetadataDrivenAnalysisTab(name, MagicMock())
    qtbot.addWidget(tab)

    fake_plot = _FakePlotItem()
    tab.plot_widget = fake_plot
    tab.restrict_analysis_checkbox = QtWidgets.QCheckBox()
    tab.restrict_analysis_checkbox.setChecked(True)
    tab.analysis_region = pg.LinearRegionItem(values=[0.1, 0.3])
    tab.analysis_region.setVisible(False)

    # Simulate plot_widget.clear() having wiped items before _on_data_plotted
    assert tab.analysis_region not in fake_plot.items
    tab._on_data_plotted()

    assert tab.analysis_region in fake_plot.items
    assert tab.analysis_region.isVisible() is True


def test_a2_manual_event_curation_amplitudes_text_and_export(qtbot, clean_registry_entries, monkeypatch):
    """A2: Curation computes baseline-relative amplitudes, updates text item, and writes back to result."""
    name = clean_registry_entries(
        "_test_a2_events",
        lambda data, time, fs, **kw: {"metrics": {}},
        label="A2 Events",
        ui_params=[],
        plots=[{"type": "event_markers"}],
    )
    monkeypatch.setattr(BaseAnalysisTab, "_setup_plot_area", lambda self, layout, stretch_factor=1: None)
    tab = MetadataDrivenAnalysisTab(name, MagicMock())
    qtbot.addWidget(tab)

    fake_plot = _FakePlotItem()
    tab.plot_widget = fake_plot
    tab._setup_custom_plot_items()
    tab.data_source_combobox.addItem("Average Trace", userData="average")
    tab.data_source_combobox.setEnabled(True)

    fs = 10000.0
    t = np.arange(1000) / fs  # 0.1 s duration
    # Holding current at -200 pA with three negative EPSC deflections
    trace = np.full(1000, -200.0, dtype=float)
    trace[200] = -230.0  # 30 pA inward event
    trace[500] = -250.0  # 50 pA inward event
    trace[800] = -240.0  # 40 pA inward event (will be added via curation)

    tab._current_plot_data = {
        "data": trace,
        "time": t,
        "sampling_rate": fs,
        "units": "pA",
        "channel_id": "0",
        "channel_name": "Im",
        "data_source": "average",
    }

    ev_obj = EventDetectionResult(
        value=20.0,
        unit="Hz",
        is_valid=True,
        event_count=2,
        frequency_hz=20.0,
        mean_amplitude=40.0,
        amplitude_sd=10.0,
        event_indices=np.array([200, 500], dtype=int),
        event_times=t[[200, 500]],
        event_amplitudes=np.array([30.0, 50.0], dtype=float),
        direction="negative",
    )
    tab._last_analysis_result = {
        "metrics": {
            "event_count": 2,
            "frequency_hz": 20.0,
            "mean_amplitude": 40.0,
            "mean_amplitude_pa": 40.0,
            "amplitude_sd": 10.0,
            "_result_obj": ev_obj,
        }
    }

    tab._viz_event_markers({}, tab._last_analysis_result["metrics"])
    assert tab._event_count_text_item is not None
    assert tab._event_count_text_item.toPlainText() == "Events: 2"

    # Simulate removing index 200 and Ctrl+Click adding index 800 (-240 pA vs -200 pA baseline -> +40 pA)
    tab._current_event_indices = [500, 800]
    tab._refresh_event_markers()

    assert tab._event_count_text_item.toPlainText() == "Events: 2"
    # Amplitudes must be [50.0, 40.0] -> mean 45.0, NEVER raw holding current (-245 pA)!
    metrics = tab._last_analysis_result["metrics"]
    assert metrics["event_count"] == 2
    assert metrics["mean_amplitude"] == pytest.approx(45.0, abs=1e-3)
    assert metrics["mean_amplitude_pa"] == pytest.approx(45.0, abs=1e-3)
    assert tab._last_analysis_result["mean_amplitude"] == pytest.approx(45.0, abs=1e-3)
    assert list(metrics["event_indices"]) == [500, 800]
    np.testing.assert_allclose(metrics["event_amplitudes"], [50.0, 40.0], rtol=1e-3)

    saved_payload = tab._get_specific_result_data()
    assert saved_payload is not None
    assert saved_payload["mean_amplitude"] == pytest.approx(45.0, abs=1e-3)
    assert saved_payload["metrics"]["mean_amplitude_pa"] == pytest.approx(45.0, abs=1e-3)

    # Removing all events updates text to Events: 0 and count to 0
    tab._current_event_indices = []
    tab._refresh_event_markers()
    assert tab._event_count_text_item.toPlainText() == "Events: 0"
    assert tab._last_analysis_result["event_count"] == 0
    assert tab._last_analysis_result["metrics"]["event_count"] == 0

    # Teardown clears _event_count_text_item
    tab._teardown_custom_plot_items()
    assert tab._event_count_text_item is None


def test_e1_viz_markers_scalar_values_render(qtbot, clean_registry_entries, monkeypatch):
    """E1-gui: _viz_markers wraps scalar float/int/np.number values so single-point markers render."""
    name = clean_registry_entries(
        "_test_e1_scalar_markers",
        lambda data, time, fs, **kw: {"metrics": {"_peak_t": 0.025, "_peak_v": np.float64(-42.5)}},
        label="E1 Markers",
        ui_params=[],
        plots=[{"type": "markers", "x": "_peak_t", "y": "_peak_v", "color": "r"}],
    )
    monkeypatch.setattr(BaseAnalysisTab, "_setup_plot_area", lambda self, layout, stretch_factor=1: None)
    tab = MetadataDrivenAnalysisTab(name, MagicMock())
    qtbot.addWidget(tab)

    fake_plot = _FakePlotItem()
    tab.plot_widget = fake_plot
    tab._plot_analysis_visualizations({"metrics": {"_peak_t": 0.025, "_peak_v": np.float64(-42.5)}})

    scatters = [it for it in fake_plot.items if isinstance(it, pg.ScatterPlotItem)]
    assert len(scatters) == 1
    x_pts, y_pts = scatters[0].getData()
    np.testing.assert_allclose(x_pts, [0.025])
    np.testing.assert_allclose(y_pts, [-42.5])


def test_e2_multi_trial_secondary_channel_list_injected(qtbot, clean_registry_entries, monkeypatch):
    """E2-gui: Multi-trial analysis receives sweep-aligned sec_data_list (sliced by t_start/t_end)."""
    captured = {}

    def _opto_stub(data, time, fs, **kwargs):
        captured["data"] = data
        captured["secondary_data"] = kwargs.get("secondary_data")
        return {"metrics": {"jitter_ms": 0.5}}

    name = clean_registry_entries(
        "_test_e2_opto",
        _opto_stub,
        label="E2 Opto",
        requires_multi_trial=True,
        requires_secondary_channel={"param_name": "secondary_data", "label": "TTL:"},
        ui_params=[],
    )
    monkeypatch.setattr(BaseAnalysisTab, "_setup_plot_area", lambda self, layout, stretch_factor=1: None)
    tab = MetadataDrivenAnalysisTab(name, MagicMock())
    qtbot.addWidget(tab)

    rec = _make_synth_recording(n_trials=3, n_samples=200, fs=1000.0, with_ttl=True)
    tab._selected_item_recording = rec
    tab.signal_channel_combobox.addItem("Vm", userData="0")
    tab.signal_channel_combobox.setCurrentIndex(0)
    tab._populate_secondary_channel_combobox()
    # TTL_Stim should be preselected or explicitly chosen
    ttl_idx = tab._secondary_channel_combobox.findData("1")
    tab._secondary_channel_combobox.setCurrentIndex(ttl_idx)

    params = {"t_start": 0.05, "t_end": 0.18}
    plot_data = {
        "data": rec.channels["0"].get_data(0),
        "time": rec.channels["0"].get_relative_time_vector(0),
        "sampling_rate": 1000.0,
    }
    out = tab._execute_core_analysis(params, plot_data)

    assert out is not None
    assert isinstance(captured["secondary_data"], list)
    assert len(captured["secondary_data"]) == 3
    for primary_sweep, sec_sweep in zip(captured["data"], captured["secondary_data"]):
        assert len(sec_sweep) == len(primary_sweep)


def test_e3_interactive_region_persists_across_runs_and_syncs(qtbot, clean_registry_entries, monkeypatch):
    """E3: _viz_interactive_region persists across _clear_dynamic_plot_items and syncs bi-directionally."""
    name = clean_registry_entries(
        "_test_e3_region",
        lambda data, time, fs, **kw: {"metrics": {"charge": 1.0}},
        label="E3 Region",
        ui_params=[
            {"name": "window_start", "type": "float", "default": 0.1, "label": "Start"},
            {"name": "window_end", "type": "float", "default": 0.4, "label": "End"},
        ],
        plots=[{"type": "interactive_region", "data": ["window_start", "window_end"], "color": "g"}],
    )
    monkeypatch.setattr(BaseAnalysisTab, "_setup_plot_area", lambda self, layout, stretch_factor=1: None)
    tab = MetadataDrivenAnalysisTab(name, MagicMock())
    qtbot.addWidget(tab)

    fake_plot = _FakePlotItem()
    tab.plot_widget = fake_plot

    # Run visualizations twice - second run calls _clear_dynamic_plot_items()
    tab._plot_analysis_visualizations({"metrics": {"charge": 1.0}})
    assert tab._custom_interactive_region is not None
    assert tab._custom_interactive_region in fake_plot.items
    assert tab._custom_interactive_region not in tab._dynamic_plot_items

    tab._plot_analysis_visualizations({"metrics": {"charge": 2.0}})
    assert tab._custom_interactive_region in fake_plot.items

    # Spinbox -> Region sync
    tab.param_generator.widgets["window_start"].setValue(0.2)
    tab.param_generator.widgets["window_end"].setValue(0.6)
    r0, r1 = tab._custom_interactive_region.getRegion()
    assert r0 == pytest.approx(0.2)
    assert r1 == pytest.approx(0.6)

    # Region -> Spinbox sync
    tab._custom_interactive_region.setRegion([0.15, 0.55])
    tab._custom_interactive_region.sigRegionChangeFinished.emit(tab._custom_interactive_region)
    assert tab.param_generator.widgets["window_start"].value() == pytest.approx(0.15)
    assert tab.param_generator.widgets["window_end"].value() == pytest.approx(0.55)

    # Teardown removes it cleanly
    tab._teardown_custom_plot_items()
    assert tab._custom_interactive_region is None


# ===========================================================================
# 2. analyser_tab.py, base.py, data_loader_service.py:
#    A3, A4, A11, A13, A16, A17, GUI-18, A18-base
# ===========================================================================


def test_a3_this_tab_only_preprocessing_persists_across_item_load(qtbot, clean_registry_entries, monkeypatch):
    """A3: tab_only=True keeps preprocessing on the target tab without leaking globally."""
    monkeypatch.setattr(BaseAnalysisTab, "_setup_plot_area", lambda self, layout, stretch_factor=1: None)
    sm = SessionManager()
    orig_prep = sm.preprocessing_settings
    try:
        analyser = AnalyserTab(MagicMock())
        qtbot.addWidget(analyser)
        assert len(analyser._loaded_analysis_tabs) >= 2

        tab0 = analyser._loaded_analysis_tabs[0]
        tab1 = analyser._loaded_analysis_tabs[1]

        prep_cfg = {"baseline": {"type": "baseline", "method": "mean", "start_t": 0.0, "end_t": 0.05}}
        sm.preprocessing_settings = prep_cfg
        analyser._global_preprocessing_confirmed = False

        monkeypatch.setattr(analyser, "_show_global_preprocessing_popup", lambda _s: "tab_only")
        analyser._check_preprocessing_on_enter()

        assert analyser.get_global_preprocessing() is None
        assert tab0._tab_local_preprocessing_settings == prep_cfg
        assert tab1._tab_local_preprocessing_settings is None

        # Selecting a new item on tab0 must preserve tab0's tab-local preprocessing
        rec = _make_synth_recording()
        tab0._analysis_items = [
            {"path": Path("/fake/rec.abf"), "target_type": "MultifileAverage", "recording_ref": rec}
        ]
        tab0._on_analysis_item_selected(0)
        assert tab0._active_preprocessing_settings == prep_cfg
        assert len(tab0.pipeline.get_steps()) == 1

        # Tab1 remains without preprocessing when loading the same item
        tab1._analysis_items = [
            {"path": Path("/fake/rec.abf"), "target_type": "MultifileAverage", "recording_ref": rec}
        ]
        tab1._on_analysis_item_selected(0)
        assert tab1._active_preprocessing_settings is None

        # Resetting preprocessing clears _tab_local_preprocessing_settings
        tab0._handle_preprocessing_reset()
        assert tab0._tab_local_preprocessing_settings is None
        assert tab0._active_preprocessing_settings is None
    finally:
        sm.preprocessing_settings = orig_prep


def test_a4_baseline_none_stripped_and_not_prepended_to_batch(qtbot, monkeypatch):
    """A4: Baseline method 'None'/'none' removes baseline slot, deep-copies to tabs, and skips batch step."""
    monkeypatch.setattr(BaseAnalysisTab, "_setup_plot_area", lambda self, layout, stretch_factor=1: None)
    sm = SessionManager()
    orig_prep = sm.preprocessing_settings
    try:
        analyser = AnalyserTab(MagicMock())
        qtbot.addWidget(analyser)

        analyser.set_global_preprocessing({"type": "baseline", "method": "mean"})
        assert analyser.get_global_preprocessing() is not None

        # Sub-tabs must hold distinct dict instances (never shared mutable dict)
        if len(analyser._loaded_analysis_tabs) >= 2:
            t0_cfg = analyser._loaded_analysis_tabs[0]._active_preprocessing_settings
            t1_cfg = analyser._loaded_analysis_tabs[1]._active_preprocessing_settings
            assert t0_cfg is not t1_cfg

        # Setting baseline method to "None" clears baseline and resets global settings to None
        analyser.set_global_preprocessing({"type": "baseline", "method": "None"})
        assert analyser.get_global_preprocessing() is None
        assert sm.preprocessing_settings is None

        # Even if a dict with baseline method="None" is inspected during batch launch, it is skipped
        analyser._analysis_items = [{"path": Path("/fake/a.abf"), "target_type": "Recording"}]
        analyser._global_preprocessing_settings = {
            "baseline": {"type": "baseline", "method": "None"},
            "filters": {"lowpass": {"type": "filter", "method": "lowpass", "cutoff": 500}},
        }
        captured_pipeline = {}

        class _FakeBatchDialog(QtWidgets.QDialog):
            load_file_request = QtCore.Signal(str, dict, object, object)

            def __init__(self, files, pipeline_config=None, default_channels=None, parent=None):
                super().__init__(parent)
                captured_pipeline["steps"] = pipeline_config

        monkeypatch.setattr("synaptipy.application.gui.batch_dialog.BatchAnalysisDialog", _FakeBatchDialog)
        analyser._on_batch_analysis_clicked()

        steps = captured_pipeline.get("steps") or []
        analyses = [s["analysis"] for s in steps]
        assert "baseline_subtraction" not in analyses
        assert "lowpass_filter" in analyses
        if analyser._batch_dialog is not None:
            analyser._batch_dialog.close()
    finally:
        sm.preprocessing_settings = orig_prep


def test_a11_result_saving_dedup_cross_file_and_cancel_overwrite(qtbot, clean_registry_entries, monkeypatch):
    """A11: _request_save_result handles cross_file_average, channel/cursor dedup, and bool return."""
    name = clean_registry_entries(
        "_test_a11_save",
        lambda data, time, fs, **kw: {"metrics": {"rmp": -65.0}},
        label="A11 Save",
        ui_params=[],
    )
    monkeypatch.setattr(BaseAnalysisTab, "_setup_plot_area", lambda self, layout, stretch_factor=1: None)

    class _HostWindow(QtWidgets.QWidget):
        def __init__(self):
            super().__init__()
            self.saved_results = []

        def add_saved_result(self, res):
            self.saved_results.append(res)

    win = _HostWindow()
    qtbot.addWidget(win)
    lay = QtWidgets.QVBoxLayout(win)
    tab = MetadataDrivenAnalysisTab(name, MagicMock(), parent=win)
    lay.addWidget(tab)

    tab._analysis_items = [{"path": Path("/fake/cell1.abf"), "target_type": "Recording"}]
    tab._selected_item_index = 0
    tab._last_analysis_result = {"metrics": {"rmp": -65.0}}

    # Verify _get_cursor_data_source uses currentData()
    tab.data_source_combobox.addItem("Average Trace", userData="average")
    tab.data_source_combobox.addItem("Trial 1", userData=0)
    tab.data_source_combobox.addItem("Cross-File Average", userData="cross_file_average")
    tab.data_source_combobox.setEnabled(True)
    tab.data_source_combobox.setCurrentIndex(2)
    assert tab._get_cursor_data_source() == "cross_file_average"

    # First save on Ch0 succeeds
    tab._current_plot_data = {"channel_id": "0", "channel_name": "Vm0"}
    tab._on_save_button_clicked_base()
    assert len(win.saved_results) == 1
    assert win.saved_results[0]["data_source_used"] == "Cross-File Average"
    assert tab._saved_results_list.count() == 1

    # Saving on Ch1 is NOT a duplicate -> no overwrite prompt
    tab._current_plot_data = {"channel_id": "1", "channel_name": "Vm1"}
    with patch.object(QtWidgets.QMessageBox, "question") as mock_q:
        tab._on_save_button_clicked_base()
        mock_q.assert_not_called()
    assert len(win.saved_results) == 2
    assert tab._saved_results_list.count() == 2

    # Saving duplicate on Ch1 and clicking No returns False and does NOT add to _saved_results_list
    tab.status_label.setText("Ready")
    with patch.object(
        QtWidgets.QMessageBox,
        "question",
        return_value=QtWidgets.QMessageBox.StandardButton.No,
    ):
        tab._on_save_button_clicked_base()
    assert len(win.saved_results) == 2
    assert tab._saved_results_list.count() == 2
    assert tab.status_label.text() == "Ready"

    # Two distinct manual cursors on the same channel do not collide
    c1 = {"data_source": "average", "channel_id": "0", "is_manual_cursor": True, "x_cursor": 0.1, "y_cursor": -65.0}
    c2 = {"data_source": "average", "channel_id": "0", "is_manual_cursor": True, "x_cursor": 0.2, "y_cursor": -64.0}
    assert tab._request_save_result(c1) is True
    with patch.object(QtWidgets.QMessageBox, "question") as mock_q2:
        assert tab._request_save_result(c2) is True
        mock_q2.assert_not_called()


def test_a13_navigate_trial_alias_cycles_combobox(qtbot, clean_registry_entries, monkeypatch):
    """A13: BaseAnalysisTab._navigate_trial aliases _navigate_combobox."""
    name = clean_registry_entries(
        "_test_a13_nav",
        lambda data, time, fs, **kw: {"metrics": {}},
        label="A13 Nav",
        ui_params=[],
    )
    monkeypatch.setattr(BaseAnalysisTab, "_setup_plot_area", lambda self, layout, stretch_factor=1: None)
    tab = MetadataDrivenAnalysisTab(name, MagicMock())
    qtbot.addWidget(tab)

    tab.data_source_combobox.blockSignals(True)
    tab.data_source_combobox.addItem("Average", userData="average")
    tab.data_source_combobox.addItem("Trial 1", userData=0)
    tab.data_source_combobox.addItem("Trial 2", userData=1)
    tab.data_source_combobox.setCurrentIndex(0)
    tab.data_source_combobox.blockSignals(False)

    monkeypatch.setattr(tab, "_plot_selected_data", lambda: None)
    tab._navigate_trial(1)
    assert tab.data_source_combobox.currentIndex() == 1
    tab._navigate_trial(-1)
    assert tab.data_source_combobox.currentIndex() == 0


def test_a16_rebuild_analysis_tabs_calls_cleanup_and_disconnects_signals(qtbot, monkeypatch):
    """A16: rebuild_analysis_tabs calls widget.cleanup() and disconnects plot customization signals."""
    monkeypatch.setattr(BaseAnalysisTab, "_setup_plot_area", lambda self, layout, stretch_factor=1: None)
    analyser = AnalyserTab(MagicMock())
    qtbot.addWidget(analyser)

    old_tabs = list(analyser._loaded_analysis_tabs)
    assert len(old_tabs) > 0
    cleanup_spy = MagicMock(wraps=old_tabs[0].cleanup)
    old_tabs[0].cleanup = cleanup_spy

    popup = QtWidgets.QWidget()
    popup.show()
    old_tabs[0]._popup_windows.append(popup)

    analyser.rebuild_analysis_tabs()
    cleanup_spy.assert_called_once()
    assert popup.isVisible() is False

    # Emitting plot preferences signal after rebuild must not invoke old tab slot or raise
    old_tabs[0]._current_plot_data = {"data": np.zeros(5), "time": np.arange(5)}
    old_tabs[0].plot_widget = MagicMock()
    get_plot_customization_signals().preferences_updated.emit()
    old_tabs[0].plot_widget.assert_not_called()


def test_a17_async_load_race_drops_stale_completion_and_balances_wait_cursor(
    qtbot, clean_registry_entries, monkeypatch
):
    """A17: Out-of-order async load is ignored and QApplication override cursor stays balanced."""
    while QtWidgets.QApplication.overrideCursor() is not None:
        QtWidgets.QApplication.restoreOverrideCursor()

    slow_started = threading.Event()
    slow_gate = threading.Event()
    rec_slow = _make_synth_recording(source_file=Path("/fake/slow.abf"))
    rec_fast = _make_synth_recording(source_file=Path("/fake/fast.abf"))

    def _read_recording(path):
        if "slow" in str(path):
            slow_started.set()
            slow_gate.wait(timeout=2.0)
            return rec_slow
        return rec_fast

    adapter = MagicMock()
    adapter.read_recording.side_effect = _read_recording

    svc = DataLoaderService(adapter)
    svc.thread_pool.setMaxThreadCount(max(2, svc.thread_pool.maxThreadCount()))
    loaded = []
    svc.recording_loaded.connect(loaded.append)

    svc.load_recording(Path("/fake/slow.abf"))
    assert slow_started.wait(timeout=2.0)
    with qtbot.waitSignal(svc.recording_loaded, timeout=3000):
        svc.load_recording(Path("/fake/fast.abf"))
    slow_gate.set()
    svc.wait_for_done()
    QtCore.QCoreApplication.processEvents()

    assert loaded == [rec_fast]

    # Also verify BaseAnalysisTab._item_load_seq and balanced WaitCursor
    name = clean_registry_entries(
        "_test_a17_tab",
        lambda data, time, fs, **kw: {"metrics": {}},
        label="A17 Tab",
        ui_params=[],
    )
    monkeypatch.setattr(BaseAnalysisTab, "_setup_plot_area", lambda self, layout, stretch_factor=1: None)
    tab = MetadataDrivenAnalysisTab(name, MagicMock())
    qtbot.addWidget(tab)
    tab._data_loader = MagicMock()

    tab._analysis_items = [
        {"path": Path("/fake/one.abf"), "target_type": "Recording"},
        {"path": Path("/fake/two.abf"), "target_type": "Recording"},
    ]
    tab._on_analysis_item_selected(0)
    seq_first = tab._item_load_seq
    assert tab._wait_cursor_active is True
    assert QtWidgets.QApplication.overrideCursor() is not None

    # Rapid second selection must NOT push a second WaitCursor onto the stack
    tab._on_analysis_item_selected(1)
    seq_second = tab._item_load_seq
    assert seq_second > seq_first

    # Stale completion for seq_first is ignored
    tab._on_item_load_success(rec_slow, seq=seq_first)
    assert tab._selected_item_recording is None
    assert tab._wait_cursor_active is True

    # Current completion for seq_second succeeds and restores cursor to None
    tab._on_item_load_success(rec_fast, seq=seq_second)
    assert tab._selected_item_recording is rec_fast
    assert tab._wait_cursor_active is False
    assert QtWidgets.QApplication.overrideCursor() is None


def test_gui18_tab_switch_syncs_x_range_after_initial_load(qtbot, monkeypatch):
    """GUI-18: _last_active_tab is initialized on load and synced X-range survives initial auto-range."""
    monkeypatch.setattr(BaseAnalysisTab, "_setup_plot_area", lambda self, layout, stretch_factor=1: None)
    analyser = AnalyserTab(MagicMock())
    qtbot.addWidget(analyser)
    assert analyser._last_active_tab is analyser.sub_tab_widget.currentWidget()

    tab0 = analyser._loaded_analysis_tabs[0]
    tab1 = analyser._loaded_analysis_tabs[1]
    tab0.plot_widget = _FakePlotItem()
    tab1.plot_widget = _FakePlotItem()
    tab0.prev_trial_btn = QtWidgets.QPushButton()
    tab0.next_trial_btn = QtWidgets.QPushButton()
    tab1.prev_trial_btn = QtWidgets.QPushButton()
    tab1.next_trial_btn = QtWidgets.QPushButton()

    rec = _make_synth_recording(n_trials=2, n_samples=1000, fs=1000.0)  # 0.0 to 0.999 s
    items = [{"path": Path("/fake/z.abf"), "target_type": "MultifileAverage", "recording_ref": rec}]
    analyser.update_analysis_sources(items)

    # Simulate user zooming Tab 0 to [0.2, 0.6] s
    tab0.plot_widget.setXRange(0.2, 0.6)
    assert tab0._current_plot_data is not None

    # Switch to Tab 1 -> triggers item load + auto-range + applies synced [0.2, 0.6]
    analyser.sub_tab_widget.setCurrentIndex(1)
    assert tab1.plot_widget.viewRange()[0] == pytest.approx([0.2, 0.6])


def test_a18_base_no_duplicate_filtered_traces_and_cross_file_fs_pipeline(qtbot, clean_registry_entries, monkeypatch):
    """A18-base: Filtered average plots context traces once; XFA derives fs and preprocesses per-file traces."""
    captured_fs = {}

    def _rec_fs(data, time, fs, **kw):
        captured_fs["fs"] = fs
        captured_fs["mean"] = float(np.mean(data))
        return {"metrics": {"v": float(np.mean(data))}}

    name = clean_registry_entries("_test_a18_base", _rec_fs, label="A18 Base", ui_params=[])
    monkeypatch.setattr(BaseAnalysisTab, "_setup_plot_area", lambda self, layout, stretch_factor=1: None)
    tab = MetadataDrivenAnalysisTab(name, MagicMock())
    qtbot.addWidget(tab)

    fake_plot = _FakePlotItem()
    tab.plot_widget = fake_plot
    tab.prev_trial_btn = QtWidgets.QPushButton()
    tab.next_trial_btn = QtWidgets.QPushButton()

    rec = _make_synth_recording(n_trials=4, n_samples=200, fs=5000.0)
    tab._selected_item_recording = rec
    tab._analysis_items = [{"path": Path("/fake/r1.abf"), "target_type": "Recording"}]
    tab._selected_item_index = 0
    tab._filtered_indices = {0, 2}

    tab._populate_channel_and_source_comboboxes()
    # 2 filtered trial context traces + 1 average trace = 3 total plotted curves (not 5!)
    assert len(fake_plot.plotted) == 3

    # Cross-file average with empty _current_plot_data and active baseline subtraction pipeline
    rec2 = _make_synth_recording(source_file=Path("/fake/r2.abf"), n_trials=4, n_samples=200, fs=5000.0)
    tab.neo_adapter.read_recording.side_effect = lambda p: rec if "r1" in str(p) else rec2
    tab._analysis_items = [
        {"path": Path("/fake/r1.abf"), "target_type": "Recording"},
        {"path": Path("/fake/r2.abf"), "target_type": "Recording"},
    ]
    tab._current_plot_data = None
    tab._active_preprocessing_settings = {"baseline": {"type": "baseline", "method": "mean"}}
    tab._rebuild_pipeline_from_settings()

    fake_plot.clear()
    tab._execute_cross_file_average_analysis({})

    assert captured_fs["fs"] == pytest.approx(5000.0)
    assert captured_fs["mean"] == pytest.approx(0.0, abs=1e-6)
    # Both per-file background traces + grand average were preprocessed toward 0 mV
    assert len(fake_plot.plotted) == 3
    for _x, y_vals, _kw in fake_plot.plotted:
        assert abs(float(np.mean(y_vals))) < 1e-6


# ===========================================================================
# 3. batch_dialog.py, session_manager.py, data_loader.py,
#    preferences_dialog.py, nwb_dialog.py, plot_save_dialog.py
# ===========================================================================


def test_a5_add_step_dialog_forces_all_trials_for_preprocessing(qtbot, clean_registry_entries):
    """A5-dialog: AddStepDialog._on_add_clicked forces scope='all_trials' for preprocessing steps."""
    prep_name = clean_registry_entries(
        "_test_a5_prep_step",
        lambda data, fs, **kw: data,
        type="preprocessing",
        label="Test Prep Step",
        ui_params=[],
    )
    dlg = AddStepDialog()
    qtbot.addWidget(dlg)

    idx = dlg.analysis_combo.findData(prep_name, QtCore.Qt.ItemDataRole.UserRole)
    assert idx >= 0
    dlg.analysis_combo.setCurrentIndex(idx)
    dlg._on_add_clicked()

    cfg = dlg.get_step_config()
    assert cfg is not None
    assert cfg["scope"] == "all_trials"


def test_c2_batch_dialog_row_double_click_emits_and_unblocks_modal(qtbot):
    """C2-dialog: Double-clicking a batch result row emits load_file_request and hides modal dialog."""
    dlg = BatchAnalysisDialog(files=[Path("/fake/test.abf")])
    qtbot.addWidget(dlg)
    dlg.setModal(True)
    dlg.show()

    dlg.result_df = pd.DataFrame(
        [{"file_path": "/fake/test.abf", "channel": "0", "trial_index": 1, "analysis": "rmp_analysis", "rmp": -65.0}]
    )
    dlg._display_results(dlg.result_df)

    emitted = []
    dlg.load_file_request.connect(lambda fp, p, ch, tr: emitted.append((fp, p, ch, tr)))
    dlg._on_result_row_clicked(0, 0)

    assert len(emitted) == 1
    assert emitted[0][0] == "/fake/test.abf"
    assert dlg.isVisible() is False


def test_a7_virtual_protocol_paths_and_session_index_recomputation(tmp_path, monkeypatch):
    """A7: ::protocol paths survive SessionManager.load_session() and DataLoader.load_file()."""
    import synaptipy.application.session_manager as sm_mod

    nwb_file = tmp_path / "multi.nwb"
    nwb_file.write_bytes(b"\x00" * 256)
    other_file = tmp_path / "cell2.abf"
    other_file.write_bytes(b"\x00" * 256)
    missing_file = tmp_path / "deleted.abf"

    virt_proto = Path(f"{nwb_file}::CurrentClamp")
    assert session_physical_path(virt_proto) == nwb_file
    assert loader_physical_path(virt_proto) == nwb_file

    session_json = tmp_path / "session.json"
    monkeypatch.setattr(sm_mod, "_SESSION_DIR", tmp_path)
    monkeypatch.setattr(sm_mod, "_SESSION_FILE", session_json)

    # Case 1: missing_file at index 0 is removed; target at index 2 (other_file) shifts to index 1
    payload = {
        "schema_version": 1,
        "active_tab_index": 0,
        "file_paths": [str(missing_file), str(virt_proto), str(other_file)],
        "current_file_index": 2,
        "global_settings": {},
        "performance_settings": {},
        "analysis_params": {},
    }
    session_json.write_text(json.dumps(payload), encoding="utf-8")
    loaded = SessionManager.load_session()
    assert loaded is not None
    assert loaded["file_paths"] == [virt_proto, other_file]
    assert loaded["current_file_index"] == 1

    # Case 2: target itself was deleted -> fallback to 0
    payload["current_file_index"] = 0
    session_json.write_text(json.dumps(payload), encoding="utf-8")
    loaded2 = SessionManager.load_session()
    assert loaded2["current_file_index"] == 0

    # Case 3: all files missing -> fallback to -1
    payload["file_paths"] = [str(missing_file)]
    session_json.write_text(json.dumps(payload), encoding="utf-8")
    loaded3 = SessionManager.load_session()
    assert loaded3["file_paths"] == []
    assert loaded3["current_file_index"] == -1

    # DataLoader.load_file accepts virtual ::protocol path
    loader = DataLoader()
    loader.cache.clear()
    ready = []
    errors = []
    loader.data_ready.connect(ready.append)
    loader.data_error.connect(lambda p, m: errors.append((p, m)))

    rec = _make_synth_recording(source_file=virt_proto)
    with patch.object(loader.neo_adapter, "read_recording", return_value=rec) as mock_read:
        loader.load_file(virt_proto)
        mock_read.assert_called_once_with(virt_proto, lazy=False)

    assert not errors
    assert ready == [rec]


def _make_fake_qsettings_class(store: dict):
    """Build an in-memory QSettings stand-in backed by *store*."""

    class _FakeQSettings:
        def __init__(self, org=APP_NAME, app=SETTINGS_SECTION):
            self._org = org
            self._app = app

        def organizationName(self):
            return self._org

        def applicationName(self):
            return self._app

        def value(self, key, default=None, val_type=None, **kwargs):
            tp = kwargs.get("type", val_type)
            val = store.get(key, default)
            if tp in (bool, int, float):
                return tp(val)
            return val

        def setValue(self, key, val):
            store[key] = val

        def sync(self):
            pass

    return _FakeQSettings


def test_a10_preferences_and_session_manager_persist_opengl_and_performance(qtbot, monkeypatch):
    """A10: PreferencesDialog saves OpenGL to QSettings and SessionManager.__init__ reads QSettings."""
    store = {
        "enable_plugins": True,
        "performance/max_cpu_cores": 2,
        "performance/max_ram_allocation_gb": 8.5,
        "performance/enable_opengl_experimental": False,
    }
    fake_cls = _make_fake_qsettings_class(store)

    monkeypatch.setattr("synaptipy.application.gui.preferences_dialog.QtCore.QSettings", fake_cls)
    monkeypatch.setattr("synaptipy.application.session_manager.QtCore.QSettings", fake_cls)
    monkeypatch.setattr("synaptipy.application.gui.preferences_dialog.apply_theme", lambda *a, **kw: None)
    monkeypatch.setattr("synaptipy.application.gui.preferences_dialog.set_theme_mode", lambda *a, **kw: None)
    monkeypatch.setattr("synaptipy.application.gui.preferences_dialog.set_scroll_direction", lambda *a, **kw: None)

    sm = SessionManager()
    orig_global = dict(sm._global_settings)
    orig_perf = dict(sm._performance_settings)
    prev_instance = SessionManager._instance
    try:
        dlg = PreferencesDialog()
        qtbot.addWidget(dlg)
        dlg.enable_opengl_checkbox.setChecked(True)
        dlg._apply_settings()

        assert store["performance/enable_opengl_experimental"] is True
        assert sm.global_settings["enable_opengl_experimental"] is True

        # Verify fallback read from QSettings when key is absent in global_settings
        sm._global_settings.pop("enable_opengl_experimental", None)
        dlg2 = PreferencesDialog()
        qtbot.addWidget(dlg2)
        assert dlg2.enable_opengl_checkbox.isChecked() is True

        # Verify SessionManager.__init__ reads CPU, RAM, and OpenGL from QSettings on fresh init
        SessionManager._instance = None
        fresh_sm = SessionManager()
        assert fresh_sm.performance_settings["max_cpu_cores"] == 2
        assert fresh_sm.performance_settings["max_ram_allocation_gb"] == pytest.approx(8.5)
        assert fresh_sm.global_settings["enable_opengl_experimental"] is True
    finally:
        SessionManager._instance = prev_instance
        sm._global_settings = orig_global
        sm._performance_settings = orig_perf


def test_a8_nwb_dialog_none_source_file_and_validation_on_accept(qtbot):
    """A8: NwbMetadataDialog handles source_file=None and keeps dialog open on invalid _on_accept."""
    in_mem_rec = Recording(source_file=Path("/fake/tmp.abf"))
    in_mem_rec.source_file = None  # Explicitly None as in synthetic/in-memory recordings
    dlg = NwbMetadataDialog(recording=in_mem_rec)
    qtbot.addWidget(dlg)
    assert dlg.session_description.text() == "In-memory Recording"
    assert dlg.session_id.text() == ""

    # Empty description -> _on_accept warns and does NOT accept
    dlg.session_description.setText("")
    dlg.tab_widget.setCurrentWidget(dlg.device_tab)
    accepted_spy = []
    dlg.accepted.connect(lambda: accepted_spy.append(True))

    with patch.object(QtWidgets.QMessageBox, "warning") as mock_warn:
        dlg._on_accept()
        mock_warn.assert_called_once()
    assert not accepted_spy
    assert dlg.tab_widget.currentWidget() is dlg.session_tab

    # Subject species filled without Subject ID -> switches to subject_tab and stays open
    dlg.session_description.setText("Valid Session")
    dlg.species.setCurrentText("Mus musculus")
    dlg.subject_id.setText("")
    with patch.object(QtWidgets.QMessageBox, "warning") as mock_warn2:
        dlg._on_accept()
        mock_warn2.assert_called_once()
    assert not accepted_spy
    assert dlg.tab_widget.currentWidget() is dlg.subject_tab

    # Supplying Subject ID allows _on_accept to succeed and caches _validated_metadata
    dlg.subject_id.setText("mouse-01")
    dlg._on_accept()
    assert accepted_spy == [True]
    meta = dlg.get_metadata()
    assert meta is not None
    assert meta["session_description"] == "Valid Session"
    assert meta["subject_id"] == "mouse-01"


def test_a18_plot_save_dialog_updates_extension_label(qtbot):
    """A18-plotsave: Switching format combo updates extension_label between .png and .pdf."""
    dlg = PlotSaveDialog(default_filename="trace_export")
    qtbot.addWidget(dlg)

    assert dlg.extension_label.text() == ".png"
    dlg.format_combo.setCurrentText("PDF")
    assert dlg.extension_label.text() == ".pdf"
    assert dlg.preview_label.text().endswith(".pdf")

    dlg.format_combo.setCurrentText("PNG")
    assert dlg.extension_label.text() == ".png"
    assert dlg.preview_label.text().endswith(".png")
