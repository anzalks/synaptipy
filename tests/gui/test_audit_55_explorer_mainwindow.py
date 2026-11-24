# -*- coding: utf-8 -*-
"""
Regression tests for Codebase Defect Audit 55 - Worker 3 (Explorer, MainWindow, Exporter).

Covers:
- A1: ExplorerSidebar._refresh_project_tree bounded os.scandir walk and root guard
- A5-exp: ExplorerTab.apply_batch_load_context channel isolation and cycle-trial sync
- A5-mw: MainWindow._on_analyser_load_file_request sibling scan, protocol suffix, and cache-hit apply
- A7-mw: MainWindow._offer_session_restore saved index restoration and clamping
- A9: ExplorerTab.load_recording_data lazy/force_units propagation and sibling retention on error retry
- A12: MainWindow Export to NWB menu state via current_recording_changed and _on_data_error cleanup
- A14: ExplorerTab._resolve_peak_y_values real peak amplitudes and active_scatter_items lifecycle
- A15: ExplorerConfigPanel & ExplorerTab manual trial averaging state sync and ::Protocol preservation
- A18-mw: MainWindow._on_loading_progress non-cumulative percentage formatting
- D6-exporter_tab: ExporterTab._do_export_analysis_results JSON column filtering
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from PySide6 import QtCore, QtWidgets

from synaptipy.application.gui.explorer.config_panel import ExplorerConfigPanel
from synaptipy.core.data_model import Channel, Recording
from synaptipy.core.results import SpikeTrainResult
from synaptipy.shared.constants import APP_NAME, SETTINGS_SECTION


def _make_recording(path: Path, num_trials: int = 4, dual_channel: bool = True) -> Recording:
    """Build an in-memory Recording with deterministic multi-trial traces."""
    rec = Recording(source_file=path)
    fs = 1000.0
    rec.sampling_rate = fs
    rec.duration = 0.1

    trials_vm = []
    for i in range(num_trials):
        arr = np.full(100, -70.0 + i, dtype=float)
        arr[25] = 35.0 + i * 2.0  # True spike peak well above -20 mV threshold
        trials_vm.append(arr)

    ch0 = Channel("0", "Vm", "mV", fs, trials_vm)
    ch0.t_start = 0.0
    rec.channels["0"] = ch0

    if dual_channel:
        trials_im = [np.zeros(100, dtype=float) + i * 10.0 for i in range(num_trials)]
        ch1 = Channel("1", "Im", "pA", fs, trials_im)
        ch1.t_start = 0.0
        rec.channels["1"] = ch1

    return rec


@pytest.fixture(scope="session")
def shared_mw(qapp):
    """Session-scoped MainWindow to avoid mid-session PlotItem C++ teardown races."""
    from synaptipy.application.gui.main_window import MainWindow

    with (
        patch("PySide6.QtWidgets.QFileDialog") as mock_dialog,
        patch("PySide6.QtWidgets.QMessageBox") as mock_msgbox,
        patch.object(MainWindow, "_offer_session_restore"),
    ):
        mock_dialog.return_value.exec.return_value = False
        mock_dialog.getSaveFileName.return_value = ("", "")
        mock_dialog.getOpenFileName.return_value = ("", "")
        mock_msgbox.critical.return_value = None
        mock_msgbox.warning.return_value = None
        mock_msgbox.information.return_value = None

        win = MainWindow()
        qapp.processEvents()

    yield win


@pytest.fixture(autouse=True)
def _reset_shared_mw_state(shared_mw):
    """Reset transient state on the shared MainWindow before and after each test."""
    sm = shared_mw.session_manager
    exp = shared_mw.explorer_tab
    sm.batch_load_context = None
    sm.current_recording = None
    shared_mw._pending_load_requests.clear()
    shared_mw._load_request_serial = 0
    shared_mw._latest_load_request = 0
    shared_mw.saved_analysis_results.clear()
    shared_mw.status_bar.clearMessage()
    exp.global_manual_trials.clear()
    exp._clear_active_scatter_items()
    exp._live_analysis_enabled = False
    exp.pipeline.clear()
    exp.current_plot_mode = exp.PlotMode.OVERLAY_AVG
    was_blocked = exp.config_panel.plot_mode_combo.blockSignals(True)
    exp.config_panel.plot_mode_combo.setCurrentIndex(exp.PlotMode.OVERLAY_AVG)
    exp.config_panel.plot_mode_combo.blockSignals(was_blocked)
    exp.config_panel._update_visibility(exp.PlotMode.OVERLAY_AVG)
    yield
    sm.batch_load_context = None


# ---------------------------------------------------------------------------
# 1. Defect A1 - ExplorerSidebar._refresh_project_tree
# ---------------------------------------------------------------------------


def test_a1_sidebar_refresh_project_tree_bounded_and_root_guarded(shared_mw, tmp_path):
    """_refresh_project_tree resolves active dir (never '/'), bounds depth <= 5, and skips hidden dirs."""
    sidebar = shared_mw.explorer_tab.sidebar

    # Build directory hierarchy under tmp_path
    valid_cell = tmp_path / "Animal1" / "Slice1" / "Cell1" / "Prot1"
    valid_cell.mkdir(parents=True)
    f_shallow = tmp_path / "top.abf"
    f_shallow.write_bytes(b"x")
    f_level4 = valid_cell / "sweep0.ABF"  # case-insensitive check
    f_level4.write_bytes(b"x")
    f_level5_dir = valid_cell / "Sub5"
    f_level5_dir.mkdir()
    f_level5 = f_level5_dir / "sweep5.abf"
    f_level5.write_bytes(b"x")

    # Depth 6 directory (must be excluded by max_depth <= 5)
    too_deep_dir = f_level5_dir / "TooDeep6"
    too_deep_dir.mkdir()
    f_too_deep = too_deep_dir / "deep6.abf"
    f_too_deep.write_bytes(b"x")

    # Hidden directory (must be skipped)
    hidden_dir = tmp_path / ".hidden_cache"
    hidden_dir.mkdir()
    (hidden_dir / "secret.abf").write_bytes(b"x")

    # Extensionless file named 'abf' must not falsely match '*.abf'
    (tmp_path / "abf").write_bytes(b"x")

    # Point sidebar file_tree rootIndex at tmp_path while file_model.rootPath() may still be '/'
    sidebar.file_model.setRootPath(str(tmp_path))
    root_idx = sidebar.file_model.index(str(tmp_path))
    sidebar.file_tree.setRootIndex(root_idx)

    # Make get_file_protocols raise on one file to verify exception guard
    def _proto_side_effect(p):
        if Path(p).name == "top.abf":
            raise RuntimeError("Corrupt header")
        return ["ProtA", "ProtB"]

    with patch.object(sidebar.neo_adapter, "get_file_protocols", side_effect=_proto_side_effect):
        sidebar._refresh_project_tree()

    # Collect all UserRole paths in project_tree
    collected_paths = set()

    def _collect(parent_item):
        for i in range(parent_item.childCount()):
            child = parent_item.child(i)
            data = child.data(0, QtCore.Qt.ItemDataRole.UserRole)
            if isinstance(data, tuple) and data[0]:
                collected_paths.add(Path(data[0]))
            _collect(child)

    _collect(sidebar.project_tree.invisibleRootItem())

    assert f_shallow in collected_paths
    assert f_level4 in collected_paths
    assert f_level5 in collected_paths
    assert f_too_deep not in collected_paths
    assert (hidden_dir / "secret.abf") not in collected_paths
    assert (tmp_path / "abf") not in collected_paths


def test_a1_sidebar_root_anchor_fallback_never_scans_filesystem_root(shared_mw, tmp_path):
    """When rootIndex points to filesystem root '/', fallback guards to Path.home() instead of '/'."""
    sidebar = shared_mw.explorer_tab.sidebar
    fake_home = tmp_path / "fake_home"
    fake_home.mkdir()
    (fake_home / "home_rec.abf").write_bytes(b"x")

    QtCore.QSettings(APP_NAME, SETTINGS_SECTION).setValue("lastDirectory", "/")

    scanned_roots = []
    real_scandir = __import__("os").scandir

    def _spy_scandir(path):
        scanned_roots.append(Path(path))
        return real_scandir(path)

    with (
        patch.object(sidebar.file_tree, "rootIndex", return_value=QtCore.QModelIndex()),
        patch("synaptipy.application.gui.explorer.sidebar.Path.home", return_value=fake_home),
        patch("synaptipy.application.gui.explorer.sidebar.os.scandir", side_effect=_spy_scandir),
        patch.object(sidebar.neo_adapter, "get_file_protocols", return_value=[]),
    ):
        sidebar._refresh_project_tree()

    assert scanned_roots, "Expected bounded scandir to scan fallback home directory"
    assert Path("/") not in scanned_roots
    assert scanned_roots[0] == fake_home


# ---------------------------------------------------------------------------
# 2. Defect A5-exp & A5-mw - Batch-to-Explorer context and jump
# ---------------------------------------------------------------------------


def test_a5_exp_apply_batch_load_context_matches_channel_name_and_trial(shared_mw, tmp_path):
    """apply_batch_load_context isolates channel by name/id/key, switches to CYCLE_SINGLE at trial, and clears ctx."""
    exp = shared_mw.explorer_tab
    rec_file = tmp_path / "batch_cell.abf"
    rec_file.write_bytes(b"x")
    rec = _make_recording(rec_file, num_trials=5, dual_channel=True)

    shared_mw.session_manager.batch_load_context = {
        "file_path": rec_file,
        "channel_id": "Im",  # Match by ch.name ("Im" -> channel key "1")
        "trial_index": 3,
    }

    exp._display_recording(rec)

    assert shared_mw.session_manager.batch_load_context is None
    assert exp.current_plot_mode == exp.PlotMode.CYCLE_SINGLE
    assert exp.config_panel.plot_mode_combo.currentIndex() == exp.PlotMode.CYCLE_SINGLE
    assert exp.current_trial_index == 3
    assert exp.config_panel.channel_checkboxes["1"].isChecked() is True
    assert exp.config_panel.channel_checkboxes["0"].isChecked() is False
    assert exp.plot_canvas._channel_visible_pref["1"] is True
    assert exp.plot_canvas._channel_visible_pref["0"] is False


def test_a5_mw_analyser_load_request_and_cache_hit_context(shared_mw, tmp_path):
    """_on_analyser_load_file_request scans siblings, preserves ::protocol, and _on_data_ready handles cache hits."""
    f1 = tmp_path / "a.nwb"
    f2 = tmp_path / "b.nwb"
    f1.write_bytes(b"x")
    f2.write_bytes(b"x")

    virtual_f2 = Path(f"{f2}::StepProtocol")
    shared_mw.tab_widget.setCurrentWidget(shared_mw.analyser_tab)

    with (
        patch.object(shared_mw, "_load_in_explorer") as mock_load,
        patch.object(shared_mw, "raise_") as mock_raise,
        patch.object(shared_mw, "activateWindow") as mock_activate,
    ):
        shared_mw._on_analyser_load_file_request(virtual_f2)

    assert shared_mw.tab_widget.currentWidget() is shared_mw.explorer_tab
    mock_raise.assert_called_once()
    mock_activate.assert_called_once()
    mock_load.assert_called_once()
    target_arg, siblings_arg, idx_arg, lazy_arg = mock_load.call_args.args
    assert target_arg == virtual_f2
    assert len(siblings_arg) == 2
    assert siblings_arg[idx_arg] == virtual_f2
    assert idx_arg == 1
    assert lazy_arg is False

    # Now verify _on_data_ready cache-hit path where recording_data == session_manager.current_recording
    rec = _make_recording(f2, num_trials=4, dual_channel=True)
    shared_mw.explorer_tab._display_recording(rec)
    shared_mw.session_manager.current_recording = rec

    shared_mw.session_manager.batch_load_context = {
        "file_path": virtual_f2,
        "channel_id": "1",
        "trial_index": 2,
    }
    key = shared_mw._load_path_key(virtual_f2)
    shared_mw._latest_load_request = 1
    shared_mw._pending_load_requests[key] = [{"id": 1, "file_list": [f1, virtual_f2], "current_index": 1}]

    shared_mw._on_data_ready(rec)

    assert shared_mw.session_manager.batch_load_context is None
    assert shared_mw.explorer_tab.current_plot_mode == shared_mw.explorer_tab.PlotMode.CYCLE_SINGLE
    assert shared_mw.explorer_tab.current_trial_index == 2
    assert shared_mw.explorer_tab.config_panel.channel_checkboxes["1"].isChecked() is True
    assert shared_mw.explorer_tab.config_panel.channel_checkboxes["0"].isChecked() is False


# ---------------------------------------------------------------------------
# 3. Defect A9 - force_units=True, lazy propagation, and sibling preservation
# ---------------------------------------------------------------------------


def test_a9_load_recording_data_propagates_lazy_and_force_units(shared_mw, tmp_path):
    """load_recording_data forwards lazy and force_units to _load_and_check_quality and read_recording."""
    exp = shared_mw.explorer_tab
    fpath = tmp_path / "low_fs.abf"
    fpath.write_bytes(b"x")

    captured_worker = {}

    def _capture_start(worker):
        captured_worker["worker"] = worker

    with patch.object(exp.thread_pool, "start", side_effect=_capture_start):
        exp.load_recording_data(fpath, file_list=[fpath], selected_index=0, lazy=True, force_units=True)
        exp._finalize_loading_state()

    worker = captured_worker["worker"]
    assert worker.args == (exp.neo_adapter, fpath, True, True)

    mock_adapter = MagicMock()
    rec = _make_recording(fpath, num_trials=1, dual_channel=False)
    mock_adapter.read_recording.return_value = rec
    exp._load_and_check_quality(mock_adapter, fpath, True, True)
    mock_adapter.read_recording.assert_called_once_with(fpath, lazy=True, force_kHz_to_Hz=True)


def test_a9_file_load_error_unit_conversion_preserves_siblings(shared_mw, tmp_path):
    """Clicking Yes on kHz->Hz prompt preserves file_list and current_file_index."""
    exp = shared_mw.explorer_tab
    siblings = [tmp_path / "s0.abf", tmp_path / "s1.abf", tmp_path / "s2.abf"]
    exp.file_list = siblings
    exp.current_file_index = 1

    unit_err = ValueError("Critical Safety: Sampling Rate (20.0 Hz) is dangerously low.")

    with (
        patch.object(
            QtWidgets.QMessageBox,
            "question",
            return_value=QtWidgets.QMessageBox.StandardButton.Yes,
        ),
        patch.object(QtCore.QTimer, "singleShot", side_effect=lambda _ms, cb: cb()),
        patch.object(exp, "load_recording_data") as mock_reload,
    ):
        exp._on_file_load_error(unit_err, siblings[1])

    mock_reload.assert_called_once_with(
        siblings[1],
        file_list=siblings,
        selected_index=1,
        force_units=True,
    )


# ---------------------------------------------------------------------------
# 4. Defect A14 - Explorer live analysis scatter peak values and cleanup
# ---------------------------------------------------------------------------


def test_a14_live_analysis_scatter_peaks_and_trial_mode_cleanup(shared_mw, tmp_path):
    """_resolve_peak_y_values resolves true trace peaks (including pipeline) and clears stale scatter items."""
    exp = shared_mw.explorer_tab
    rec = _make_recording(tmp_path / "spikes.abf", num_trials=3, dual_channel=False)
    exp._display_recording(rec)
    exp._on_plot_mode_changed(exp.PlotMode.CYCLE_SINGLE)

    # Without caches populated, _resolve_peak_y_values must read channel trace peak (35.0 mV on trial 0 at index 25)
    spike_times = np.array([0.025])
    spike_indices = np.array([25])
    x_out, y_out = exp._resolve_peak_y_values("0", 0, spike_times, spike_indices, threshold=-20.0)
    assert np.allclose(x_out, [0.025])
    assert np.allclose(y_out, [35.0])  # NOT flat at -20.0!

    # Verify 3-arg call compatibility (interpolation when spike_indices omitted)
    x_interp, y_interp = exp._resolve_peak_y_values("0", spike_times, -20.0)
    assert np.allclose(x_interp, [0.025])
    assert np.allclose(y_interp, [35.0])

    # Emit live analysis result onto trial 0 and verify scatter item added
    exp._live_analysis_enabled = True
    res = SpikeTrainResult(
        value=10.0,
        unit="Hz",
        spike_times=spike_times,
        spike_indices=spike_indices,
        parameters={"channel_id": "0", "trial_index": 0, "threshold": -20.0},
    )
    exp._on_live_analysis_finished(res)
    assert "spikes_0" in exp.active_scatter_items

    # Advancing trial clears stale scatter item and re-triggers live analysis
    with patch.object(exp, "_request_live_analysis") as mock_req:
        exp._next_trial()
    assert exp.current_trial_index == 1
    assert exp.active_scatter_items == {}
    mock_req.assert_called_once()

    # Switching plot mode clears stale scatter items
    exp._on_live_analysis_finished(
        SpikeTrainResult(
            value=10.0,
            unit="Hz",
            spike_times=spike_times,
            spike_indices=spike_indices,
            parameters={"channel_id": "0", "trial_index": 1, "threshold": -20.0},
        )
    )
    assert "spikes_0" in exp.active_scatter_items
    exp._on_plot_mode_changed(exp.PlotMode.OVERLAY_AVG)
    assert exp.active_scatter_items == {}

    # Loading a new recording clears active_scatter_items
    exp.active_scatter_items["spikes_0"] = MagicMock()
    exp._display_recording(rec)
    assert exp.active_scatter_items == {}


# ---------------------------------------------------------------------------
# 5. Defect A15 - Manual trial averaging state sync & ::Protocol preservation
# ---------------------------------------------------------------------------


def test_a15_manual_trial_averaging_visibility_reset_and_virtual_path(shared_mw, tmp_path):
    """ConfigPanel disables cycle buttons initially, unchecks avg on mode switch, resets input, keeps ::Protocol."""
    fresh_panel = ExplorerConfigPanel()
    assert fresh_panel.select_trial_btn.isEnabled() is False
    assert fresh_panel.show_avg_btn.isEnabled() is False
    assert fresh_panel.clear_sel_btn.isEnabled() is False

    exp = shared_mw.explorer_tab
    phys_nwb = tmp_path / "exp.nwb"
    phys_nwb.write_bytes(b"x")
    rec = _make_recording(phys_nwb, num_trials=4, dual_channel=False)
    rec.imported_protocol_label = "CC_Step"

    exp.current_loaded_path = Path(f"{phys_nwb}::CC_Step")
    exp._display_recording(rec)

    # Switch to Cycle Mode, mark trial 1, and enable Plot Selected Avg
    exp.config_panel.plot_mode_combo.setCurrentIndex(exp.PlotMode.CYCLE_SINGLE)
    assert exp.config_panel.select_trial_btn.isEnabled() is True
    exp._next_trial()
    exp._toggle_select_current_trial()

    assert len(exp.global_manual_trials) == 1
    assert exp.global_manual_trials[0]["path"] == Path(f"{phys_nwb}::CC_Step")
    assert exp.add_marked_trials_btn.isEnabled() is True

    exp.config_panel.show_avg_btn.setChecked(True)
    assert exp.config_panel.show_avg_btn.isChecked() is True

    # Switching back to OVERLAY_AVG must uncheck show_avg_btn and disable manual controls
    exp.config_panel.plot_mode_combo.setCurrentIndex(exp.PlotMode.OVERLAY_AVG)
    assert exp.config_panel.show_avg_btn.isChecked() is False
    assert exp.config_panel.select_trial_btn.isEnabled() is False

    # _clear_avg_selection must immediately disable add_marked_trials_btn
    exp.config_panel.plot_mode_combo.setCurrentIndex(exp.PlotMode.CYCLE_SINGLE)
    exp._clear_avg_selection()
    assert exp.global_manual_trials == []
    assert exp.add_marked_trials_btn.isEnabled() is False

    # _on_trial_selection_reset_requested must clear stale text in trial_selection_input
    exp._on_trial_selection_requested("0, 2")
    assert exp.config_panel.trial_selection_input.text() == "0, 2"
    exp._on_trial_selection_reset_requested()
    assert exp.config_panel.trial_selection_input.text() == ""
    assert len(exp.selected_trial_indices) == 0


# ---------------------------------------------------------------------------
# 6. Defects A12, A7-mw, A18-mw - MainWindow menu sync, session restore, progress
# ---------------------------------------------------------------------------


def test_a12_export_nwb_menu_sync_and_data_error_cleanup(shared_mw, tmp_path):
    """Export to NWB enables on sidebar/session load and _on_data_error updates menu and exporter state."""
    assert not shared_mw.export_nwb_action.isEnabled()

    rec = _make_recording(tmp_path / "sidebar_loaded.abf", num_trials=2, dual_channel=False)
    # Simulate ExplorerTab._on_file_load_success setting session_manager.current_recording
    shared_mw.explorer_tab._on_file_load_success((rec, {"is_good": True, "warnings": []}))
    assert shared_mw.export_nwb_action.isEnabled() is True

    # Clearing session recording disables Export to NWB
    shared_mw.session_manager.current_recording = None
    assert shared_mw.export_nwb_action.isEnabled() is False

    # _on_data_error executes UI cleanup (previously unreachable after return in _take_pending_load)
    err_path = tmp_path / "bad.abf"
    key = shared_mw._load_path_key(err_path)
    shared_mw._latest_load_request = 1
    shared_mw._pending_load_requests[key] = [{"id": 1, "file_list": [err_path], "current_index": 0}]

    with (
        patch("PySide6.QtWidgets.QMessageBox.critical"),
        patch.object(shared_mw, "_update_menu_state", wraps=shared_mw._update_menu_state) as spy_menu,
        patch.object(shared_mw.exporter_tab, "update_state", wraps=shared_mw.exporter_tab.update_state) as spy_exp,
    ):
        shared_mw._on_data_error(err_path, "Corrupted file")

    spy_menu.assert_called_once()
    spy_exp.assert_called_once()


def test_a7_mw_session_restore_loads_saved_file_index_and_clamps(shared_mw, tmp_path):
    """_offer_session_restore loads file_paths[idx] instead of always file_paths[0]."""
    files = [tmp_path / "f0.abf", tmp_path / "f1.abf", tmp_path / "f2.abf"]
    for f in files:
        f.write_bytes(b"x")

    session_data = {
        "file_paths": files,
        "current_file_index": 2,
        "active_tab_index": 0,
    }

    with (
        patch.object(shared_mw.session_manager, "load_session", return_value=session_data),
        patch.object(shared_mw.session_manager, "apply_session"),
        patch.object(
            QtWidgets.QMessageBox,
            "question",
            return_value=QtWidgets.QMessageBox.StandardButton.Yes,
        ),
        patch.object(shared_mw, "_load_in_explorer") as mock_load,
        patch.object(QtCore.QTimer, "singleShot"),
    ):
        shared_mw._offer_session_restore()

    mock_load.assert_called_once_with(files[2], files, 2, lazy_load=False)

    # Out-of-bounds index clamps cleanly to 0
    session_oob = {"file_paths": files, "current_file_index": 99, "active_tab_index": 0}
    with (
        patch.object(shared_mw.session_manager, "load_session", return_value=session_oob),
        patch.object(shared_mw.session_manager, "apply_session"),
        patch.object(
            QtWidgets.QMessageBox,
            "question",
            return_value=QtWidgets.QMessageBox.StandardButton.Yes,
        ),
        patch.object(shared_mw, "_load_in_explorer") as mock_load_oob,
        patch.object(QtCore.QTimer, "singleShot"),
    ):
        shared_mw._offer_session_restore()

    mock_load_oob.assert_called_once_with(files[0], files, 0, lazy_load=False)


def test_a18_mw_loading_progress_replaces_trailing_percentage(shared_mw):
    """_on_loading_progress strips previous '(NN%)' suffix instead of accumulating percentages."""
    shared_mw._on_loading_started("/tmp/recording_01.abf")
    assert shared_mw.status_bar.currentMessage() == "Loading recording_01.abf..."

    for pct in (10, 20, 80, 100):
        shared_mw._on_loading_progress(pct)
        assert shared_mw.status_bar.currentMessage() == f"Loading recording_01.abf... ({pct}%)"


# ---------------------------------------------------------------------------
# 7. Defect D6-exporter_tab - JSON export filters private columns & plot_payload
# ---------------------------------------------------------------------------


def test_d6_exporter_tab_json_export_strips_private_and_plot_payload(shared_mw, tmp_path):
    """JSON export excludes '_*' internal columns and 'plot_payload'."""
    exporter = shared_mw.exporter_tab
    shared_mw.saved_analysis_results = [
        {
            "analysis_type": "Spike Detection",
            "source_file_name": "cell1.abf",
            "metrics": {
                "spike_count": 12,
                "_raw_spike_train": [0.01, 0.05],
                "plot_payload": {"x": [1, 2, 3], "y": [4, 5, 6]},
            },
            "_private_artifact": "do_not_export",
            "plot_payload": {"overlay": [1, 2]},
        }
    ]

    out_json = tmp_path / "exported_results.json"
    exporter.analysis_results_path_edit.setText(str(out_json))
    exporter._refresh_analysis_results()
    exporter.analysis_results_table.selectAll()

    with patch.object(QtWidgets.QMessageBox, "information"):
        exporter._do_export_analysis_results()

    assert out_json.is_file()
    payload = json.loads(out_json.read_text(encoding="utf-8"))
    assert len(payload) == 1
    row = payload[0]
    assert row["analysis_type"] == "Spike Detection"
    assert row["spike_count"] == 12
    assert "plot_payload" not in row
    assert not any(k.startswith("_") for k in row.keys())
