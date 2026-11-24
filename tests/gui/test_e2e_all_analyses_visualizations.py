# -*- coding: utf-8 -*-
"""
End-to-end live GUI verification across all core analysis pillars, sub-methods,
bundled plugins, _viz_* overlays, popups, live plot customization updates, exports,
and static AST resolution of all top-level and lazy/nested internal imports.

Crucially attaches a logging.ERROR trap to the ``synaptipy`` logger hierarchy so
exceptions caught inside ``BaseAnalysisTab._trigger_analysis`` or
``_update_plot_pens_only`` cannot pass silently.
"""

from __future__ import annotations

import ast
import importlib
import importlib.util
import logging
from pathlib import Path
from typing import List
from unittest.mock import patch

import numpy as np
import pytest
from PySide6 import QtWidgets

import synaptipy.core.analysis  # noqa: F401
from synaptipy.application.gui.analysis_config_dialog import AnalysisConfigDialog
from synaptipy.application.gui.plot_customization_dialog import PlotCustomizationDialog
from synaptipy.application.gui.preferences_dialog import PreferencesDialog
from synaptipy.application.gui.session_summary_dialog import SessionSummaryDialog
from synaptipy.application.plugin_manager import PluginManager
from synaptipy.core.data_model import Channel, Recording
from synaptipy.infrastructure.exporters.csv_exporter import CSVExporter
from synaptipy.shared.plot_exporter import PlotExporter

_PA_ANALYSES = {
    "capacitance_analysis",
    "synaptic_charge",
    "miniml_events",
    "event_detection_threshold",
    "event_detection_deconvolution",
}

_SPIKE_TRIAL_ANALYSES = {
    "spike_detection",
    "phase_plane_analysis",
    "burst_analysis",
    "train_dynamics",
}

_EXPECTED_CORE_ANALYSES = {
    "rmp_analysis",
    "rin_analysis",
    "tau_analysis",
    "sag_ratio_analysis",
    "iv_curve_analysis",
    "capacitance_analysis",
    "spike_detection",
    "phase_plane_analysis",
    "excitability_analysis",
    "burst_analysis",
    "train_dynamics",
    "event_detection_threshold",
    "event_detection_deconvolution",
    "optogenetic_sync",
    "paired_pulse_ratio",
    "stimulus_train_stp",
}


class _ErrorLogTrap(logging.Handler):
    """Collect any ERROR/CRITICAL log records emitted under ``synaptipy``."""

    def __init__(self) -> None:
        super().__init__(level=logging.ERROR)
        self.records: List[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(self.format(record))


def _resolve_relative_module(py_file: Path, src_root: Path, module: str | None, level: int) -> str:
    """Resolve a relative ``from ... import`` inside ``src/synaptipy`` to an absolute dotted module."""
    rel_parts = list(py_file.relative_to(src_root).with_suffix("").parts)
    pkg_parts = rel_parts[:-1]
    ascend = max(0, level - 1)
    base_parts = pkg_parts[: len(pkg_parts) - ascend]
    if module:
        base_parts.extend(module.split("."))
    return ".".join(base_parts)


def _is_synaptipy_module(mod_name: str | None) -> bool:
    """Return True if *mod_name* refers to ``synaptipy`` or one of its submodules."""
    return bool(mod_name and (mod_name == "synaptipy" or mod_name.startswith("synaptipy.")))


def _check_import_node(node: ast.Import, py_file: Path) -> List[str]:
    """Validate an ``ast.Import`` statement for ``synaptipy.*`` targets."""
    errors: List[str] = []
    for alias in node.names:
        if _is_synaptipy_module(alias.name):
            try:
                importlib.import_module(alias.name)
            except Exception as exc:
                errors.append(f"{py_file}:{node.lineno} import {alias.name} -> {exc}")
    return errors


def _verify_imported_symbols(mod_obj: object, target_mod: str, names: List[ast.alias], loc: str) -> List[str]:
    """Verify each symbol in ``from <target_mod> import ...`` exists as attribute or submodule."""
    errors: List[str] = []
    for alias in names:
        if alias.name == "*" or hasattr(mod_obj, alias.name):
            continue
        try:
            importlib.import_module(f"{target_mod}.{alias.name}")
        except Exception:
            errors.append(f"{loc} cannot import name '{alias.name}' from '{target_mod}'")
    return errors


def _check_import_from_node(node: ast.ImportFrom, py_file: Path, src_root: Path) -> List[str]:
    """Validate an ``ast.ImportFrom`` statement for ``synaptipy.*`` targets."""
    target_mod = None
    if node.level > 0 and src_root in py_file.parents:
        target_mod = _resolve_relative_module(py_file, src_root, node.module, node.level)
    elif node.level == 0 and _is_synaptipy_module(node.module):
        target_mod = node.module

    if not _is_synaptipy_module(target_mod):
        return []

    loc = f"{py_file}:{node.lineno}"
    try:
        mod_obj = importlib.import_module(target_mod)  # type: ignore[arg-type]
    except Exception as exc:
        return [f"{loc} from {target_mod} -> {exc}"]

    return _verify_imported_symbols(mod_obj, target_mod, node.names, loc)  # type: ignore[arg-type]


def _scan_file_imports(py_file: Path, src_root: Path) -> List[str]:
    """Parse *py_file* and validate all internal ``synaptipy`` imports at any AST depth."""
    tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
    errors: List[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            errors.extend(_check_import_node(node, py_file))
        elif isinstance(node, ast.ImportFrom):
            errors.extend(_check_import_from_node(node, py_file, src_root))
    return errors


def test_all_top_level_and_lazy_synaptipy_imports_resolve():
    """Verify every top-level and function-local ``synaptipy.*`` import resolves to a real module/symbol."""
    repo_root = Path(__file__).resolve().parents[2]
    src_root = repo_root / "src"
    scan_dirs = [src_root / "synaptipy", repo_root / "examples", repo_root / "scripts", repo_root / "validation"]

    unresolved: List[str] = []
    for scan_dir in scan_dirs:
        if scan_dir.exists():
            for py_file in sorted(scan_dir.rglob("*.py")):
                unresolved.extend(_scan_file_imports(py_file, src_root))

    assert not unresolved, "Unresolved internal imports found:\n" + "\n".join(unresolved)


def _build_physiological_recording(tmp_path: Path) -> Recording:
    """Synthesize a multi-trial, 3-channel (Vm mV, Im pA, TTL V) physiological recording."""
    fs = 20000.0
    t = np.arange(0.0, 1.0, 1.0 / fs)
    n = len(t)
    stim_times = (0.20, 0.25, 0.30, 0.35, 0.40)

    ttl = np.zeros(n, dtype=float)
    for st in stim_times:
        i0 = int(st * fs)
        ttl[i0 : min(n, i0 + int(0.002 * fs))] = 5.0
    ttl_trials = [ttl.copy() for _ in range(4)]

    step_mask = (t >= 0.10) & (t < 0.60)
    t_step = t[step_mask] - 0.10
    post_mask = t >= 0.60

    v0 = np.full(n, -65.0, dtype=float)
    v0[step_mask] = -65.0 - 15.0 * (1.0 - np.exp(-t_step / 0.015)) + 5.0 * (1.0 - np.exp(-t_step / 0.080))
    v0[post_mask] = -65.0 - 10.0 * np.exp(-(t[post_mask] - 0.60) / 0.020)

    v1 = np.full(n, -65.0, dtype=float)
    v1[step_mask] = -65.0 - 5.0 * (1.0 - np.exp(-t_step / 0.018))
    v1[post_mask] = -65.0 - 5.0 * np.exp(-(t[post_mask] - 0.60) / 0.018)

    v2 = np.full(n, -65.0, dtype=float)
    v2[step_mask] = -52.0
    for spk_t in (0.140, 0.148, 0.156, 0.203, 0.253, 0.303, 0.353, 0.403):
        rel = t - spk_t
        up = 92.0 * np.exp(-0.5 * (np.minimum(rel, 0.0) / 0.00025) ** 2)
        dn = 92.0 * np.exp(-0.5 * (np.maximum(rel, 0.0) / 0.00045) ** 2)
        ahp = -5.0 * np.exp(-0.5 * ((rel - 0.0018) / 0.0008) ** 2) * (rel > 0.0)
        v2 += np.where(rel <= 0.0, up, dn) + ahp

    v3 = np.full(n, -65.0, dtype=float)
    v3[step_mask] = -65.0 + 4.0 * (1.0 - np.exp(-t_step / 0.018))
    for ev_t, amp in ((0.202, 8.0), (0.252, 11.0), (0.302, 9.5), (0.352, 8.5), (0.402, 8.0)):
        m = t >= ev_t
        rel = t[m] - ev_t
        v3[m] += amp * (np.exp(-rel / 0.012) - np.exp(-rel / 0.0015))

    im_trials = []
    for tr_idx in range(4):
        im = np.full(n, -40.0, dtype=float)
        im[step_mask] = -40.0 - 50.0 - 350.0 * np.exp(-t_step / 0.0012)
        epsc_specs = [
            (0.045, -28.0),
            (0.075, -32.0),
            (0.202, -60.0 - tr_idx * 2.0),
            (0.252, -85.0 - tr_idx * 2.0),
            (0.302, -72.0),
            (0.352, -64.0),
            (0.402, -58.0),
        ]
        for ev_t, peak_pa in epsc_specs:
            m = t >= ev_t
            rel = t[m] - ev_t
            im[m] += peak_pa * 1.45 * (np.exp(-rel / 0.006) - np.exp(-rel / 0.0006))
        im_trials.append(im)

    fake_file = tmp_path / "synthetic_e2e.abf"
    fake_file.write_bytes(b"ABF2")

    rec = Recording(source_file=fake_file)
    rec.sampling_rate = fs
    rec.duration = 1.0
    rec.t_start = 0.0

    ch_vm = Channel("0", "Vm", "mV", fs, [v0, v1, v2, v3])
    ch_vm.t_start = 0.0
    ch_im = Channel("1", "Im", "pA", fs, im_trials)
    ch_im.t_start = 0.0
    ch_ttl = Channel("2", "FrameTTL", "V", fs, ttl_trials)
    ch_ttl.t_start = 0.0
    rec.channels = {"0": ch_vm, "1": ch_im, "2": ch_ttl}
    return rec


@pytest.fixture(scope="session")
def e2e_main_window(qapp):
    """Session-scoped MainWindow with bundled plugins loaded for comprehensive E2E verification."""
    from synaptipy.application.gui.main_window import MainWindow

    names = ("critical", "warning", "information", "question")
    originals = {name: getattr(QtWidgets.QMessageBox, name) for name in names}
    try:
        for name in names:
            setattr(
                QtWidgets.QMessageBox,
                name,
                staticmethod(lambda *_a, **_kw: QtWidgets.QMessageBox.StandardButton.Yes),
            )
        PluginManager.load_plugins()
        with (
            patch("PySide6.QtWidgets.QFileDialog") as mock_dialog,
            patch.object(MainWindow, "_offer_session_restore"),
        ):
            mock_dialog.return_value.exec.return_value = False
            mock_dialog.getSaveFileName.return_value = ("", "")
            mock_dialog.getOpenFileName.return_value = ("", "")

            win = MainWindow()
            win.analyser_tab.rebuild_analysis_tabs()
            qapp.processEvents()
    finally:
        for name, orig in originals.items():
            setattr(QtWidgets.QMessageBox, name, orig)

    yield win
    win.close()
    qapp.processEvents()


def _select_combo_by_data(combo: QtWidgets.QComboBox | None, target_data: object) -> None:
    """Select the combobox entry matching *target_data* if present."""
    if combo is None:
        return
    idx = combo.findData(target_data)
    if idx >= 0:
        combo.setCurrentIndex(idx)


def _enable_optional_overlay_params(tab: object, a_name: str) -> dict:
    """Enable rich overlay checkboxes (kinetics, artifact rejection, decay subtraction) when present."""
    widgets = getattr(getattr(tab, "param_generator", None), "widgets", {})
    if a_name == "event_detection_threshold":
        for key in ("compute_kinetics", "reject_artifacts"):
            if key in widgets:
                widgets[key].setChecked(True)
    elif a_name == "paired_pulse_ratio" and "subtract_residual_decay" in widgets:
        widgets["subtract_residual_decay"].setChecked(True)
    return widgets


def _run_tau_biexponential_branch(tab: object, widgets: dict, qapp: object) -> None:
    """Also exercise the bi-exponential Tau fit branch so ``secondary_fit`` overlays render."""
    tab._update_plot_pens_only()
    bi_idx = widgets["tau_model"].findText("bi")
    if bi_idx >= 0:
        widgets["tau_model"].setCurrentIndex(bi_idx)
    tab._trigger_analysis()
    qapp.processEvents()


def _exercise_plugin_branches(tab: object, a_name: str, widgets: dict, qapp: object) -> None:
    """Exercise current-clamp EPSP AUC and low-frequency intracellular SpikeInterface branches."""
    import pyqtgraph as pg

    if a_name == "synaptic_charge":
        _select_combo_by_data(tab.signal_channel_combobox, "0")
        _select_combo_by_data(tab.data_source_combobox, 3)
        if "window_start" in widgets and "window_end" in widgets:
            widgets["window_start"].setValue(0.195)
            widgets["window_end"].setValue(0.245)
        tab._trigger_analysis()
        qapp.processEvents()
        dyn_auc = getattr(tab, "_dynamic_plot_items", [])
        assert any(isinstance(it, pg.FillBetweenItem) for it in dyn_auc), "Missing AUC FillBetweenItem on mV trace"
        assert "AUC (mV*ms)" in (tab._last_analysis_result or {}).get("metrics", {})
    elif a_name == "spike_interface_detection":
        _select_combo_by_data(tab.signal_channel_combobox, "0")
        _select_combo_by_data(tab.data_source_combobox, 2)
        if "freq_min" in widgets and "freq_max" in widgets:
            widgets["freq_min"].setValue(10.0)
            widgets["freq_max"].setValue(500.0)
        if "peak_sign" in widgets:
            pos_i = widgets["peak_sign"].findText("pos")
            if pos_i >= 0:
                widgets["peak_sign"].setCurrentIndex(pos_i)
        if "exclude_sweep_ms" in widgets:
            widgets["exclude_sweep_ms"].setValue(2.0)
        tab._trigger_analysis()
        qapp.processEvents()
        si_metrics = (tab._last_analysis_result or {}).get("metrics", {})
        if importlib.util.find_spec("spikeinterface") is not None:
            assert "error" not in si_metrics, f"SpikeInterface low freq_min failed: {si_metrics}"
            assert si_metrics.get("Spike_Count", 0) >= 8
        else:
            assert "SpikeInterface is not installed" in str(
                si_metrics.get("error", "")
            ), f"Expected graceful missing-dependency message when spikeinterface is absent, got: {si_metrics}"


def _assert_evoked_overlays_and_vlines(tab: object, a_name: str) -> None:
    """Verify multi-pulse trigger lines and cyan response overlays on evoked tabs."""
    import pyqtgraph as pg

    dyn_items = getattr(tab, "_dynamic_plot_items", [])
    vlines = [it for it in dyn_items if isinstance(it, pg.InfiniteLine) and it.angle == 90]
    overlays = [
        it
        for it in dyn_items
        if isinstance(it, pg.PlotCurveItem) and getattr(it, "_synaptipy_role", None) == "trace_overlay"
    ]
    expected_min = 2 if a_name == "paired_pulse_ratio" else 5
    assert len(vlines) >= expected_min, f"{a_name}: expected >= {expected_min} trigger vlines, got {len(vlines)}"
    assert (
        len(overlays) >= expected_min
    ), f"{a_name}: expected >= {expected_min} cyan curve overlays, got {len(overlays)}"


def _run_single_method_on_tab(tab: object, m_label: str, qapp: object) -> str:
    """Configure and execute a single analysis sub-method on *tab*, returning its registry key."""
    method_combo = getattr(tab, "method_combobox", None)
    if method_combo is not None and method_combo.count() > 0:
        idx = method_combo.findText(m_label)
        if idx >= 0:
            method_combo.setCurrentIndex(idx)
            qapp.processEvents()

    a_name = getattr(tab, "analysis_name", m_label)
    _select_combo_by_data(tab.signal_channel_combobox, "1" if a_name in _PA_ANALYSES else "0")
    _select_combo_by_data(tab.data_source_combobox, 2 if a_name in _SPIKE_TRIAL_ANALYSES else "average")
    _select_combo_by_data(getattr(tab, "_secondary_channel_combobox", None), "2")

    widgets = _enable_optional_overlay_params(tab, a_name)
    tab._trigger_analysis()
    qapp.processEvents()

    if a_name == "tau_analysis" and "tau_model" in widgets:
        _run_tau_biexponential_branch(tab, widgets, qapp)

    if a_name in ("synaptic_charge", "spike_interface_detection"):
        _exercise_plugin_branches(tab, a_name, widgets, qapp)

    if a_name in ("optogenetic_sync", "paired_pulse_ratio", "stimulus_train_stp", "opto_jitter"):
        _assert_evoked_overlays_and_vlines(tab, a_name)

    tab._update_plot_pens_only()

    if a_name != "miniml_events" and tab._last_analysis_result and getattr(tab, "save_button", None):
        if tab.save_button.isEnabled():
            tab._on_save_button_clicked_base()

    for pop in list(getattr(tab, "_popup_windows", [])):
        pop.close()

    return a_name


def _exercise_analyser_tabs(analyser: object, rec: Recording, qapp: object) -> List[str]:
    """Load *rec* into every Analyser tab and run all sub-methods and pen updates."""
    executed_methods: List[str] = []
    for tab in analyser._loaded_analysis_tabs:
        tab._analysis_items = [{"path": rec.source_file, "target_type": "Recording"}]
        tab._selected_item_index = 0
        tab._on_item_load_success(rec, seq=tab._item_load_seq)

        if getattr(tab, "metadata", {}).get("run_button"):
            assert not tab._analysis_debounce_timer.isActive()
        supported = tuple(getattr(tab, "metadata", {}).get("supported_channel_units", ()))
        if supported and set(supported).issubset({"pA", "nA"}):
            assert tab.signal_channel_combobox.currentData() == "1"

        qapp.processEvents()
        method_combo = getattr(tab, "method_combobox", None)
        methods = (
            [method_combo.itemText(i) for i in range(method_combo.count())]
            if method_combo is not None and method_combo.count() > 0
            else [tab.get_display_name()]
        )
        for m_label in methods:
            executed_methods.append(_run_single_method_on_tab(tab, m_label, qapp))
    return executed_methods


def _exercise_dialogs_and_exporters(win: object, rec: Recording, tmp_path: Path) -> None:
    """Verify Explorer/Analyser plot exports, configuration dialogs, session summary, and CSV exports."""
    assert PlotExporter(rec, win.explorer_tab.plot_canvas.widget).export(str(tmp_path / "explorer.png"), "png", 150)
    assert PlotExporter(rec, win.explorer_tab.plot_canvas.widget).export(str(tmp_path / "explorer.pdf"), "pdf", 150)
    first_plot = win.analyser_tab._loaded_analysis_tabs[0].plot_widget
    assert PlotExporter(rec, first_plot).export(str(tmp_path / "analyser.pdf"), "pdf", 150)

    pc_dlg = PlotCustomizationDialog(win)
    pc_dlg._apply_changes()
    pc_dlg.close()

    for dlg_cls in (PreferencesDialog, AnalysisConfigDialog):
        dlg = dlg_cls(win)
        dlg.close()

    assert len(win.saved_analysis_results) > 0
    sum_dlg = SessionSummaryDialog(win.saved_analysis_results, win)
    sum_dlg.close()

    exporter = CSVExporter()
    assert exporter.export_analysis_results(win.saved_analysis_results, tmp_path / "summary.csv")
    assert exporter.export_tidy(win.saved_analysis_results, tmp_path / "tidy.csv")
    assert exporter.export_to_prism_format(win.saved_analysis_results, tmp_path / "prism_rmp.csv", metric="rmp_mv")


@pytest.mark.timeout(180)
def test_every_analysis_visualization_customization_and_export_runs_without_errors(e2e_main_window, qapp, tmp_path):
    """Exercise all 5 pillars, all 16 core methods, bundled plugins, live pen updates, popups, and exports."""
    syn_logger = logging.getLogger("synaptipy")
    trap = _ErrorLogTrap()
    trap.setFormatter(logging.Formatter("%(name)s [%(levelname)s]: %(message)s"))
    syn_logger.addHandler(trap)

    shown_modals: List[tuple[str, str]] = []
    msg_names = ("critical", "warning", "information", "question")
    orig_msg = {name: getattr(QtWidgets.QMessageBox, name) for name in msg_names}
    for name in msg_names:

        def _spy(*args, _kind=name, **_kwargs):
            shown_modals.append((_kind, str(args[2]) if len(args) > 2 else ""))
            return QtWidgets.QMessageBox.StandardButton.Yes

        setattr(QtWidgets.QMessageBox, name, staticmethod(_spy))

    rec = _build_physiological_recording(tmp_path)
    win = e2e_main_window

    try:
        with (
            patch.object(win.neo_adapter, "read_recording", return_value=rec),
            patch.object(QtWidgets.QMessageBox, "exec", return_value=int(QtWidgets.QMessageBox.StandardButton.Yes)),
        ):
            win.session_manager.current_recording = rec
            win.explorer_tab._display_recording(rec)
            qapp.processEvents()
            win.explorer_tab.update_plot_pens()

            executed = _exercise_analyser_tabs(win.analyser_tab, rec, qapp)
            missing = _EXPECTED_CORE_ANALYSES - set(executed)
            assert not missing, f"Core analyses not exercised: {sorted(missing)}"

            _exercise_dialogs_and_exporters(win, rec, tmp_path)

        critical_modals = [m for m in shown_modals if m[0] == "critical"]
        assert not critical_modals, f"Unexpected critical modal dialogs: {critical_modals}"
        assert not trap.records, "Errors logged during E2E GUI execution:\n" + "\n---\n".join(trap.records)
    finally:
        for name, orig in orig_msg.items():
            setattr(QtWidgets.QMessageBox, name, orig)
        syn_logger.removeHandler(trap)
