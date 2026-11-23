# -*- coding: utf-8 -*-
"""GUI regression tests verifying MetadataDrivenAnalysisTab markers and threshold lines align on traces."""

from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np
import pytest

import synaptipy.core.analysis  # noqa: F401
from synaptipy.application.gui.analysis_tabs.metadata_driven import MetadataDrivenAnalysisTab
from synaptipy.core.analysis.single_spike import phase_plane_analysis_wrapper


def _make_two_ap_trace(fs: float = 20000.0):
    """Synthesize a 2-spike current-clamp trace for GUI phase-plane popup checks."""
    dt = 1.0 / fs
    t = np.arange(0.0, 0.12, dt) + 0.05
    v = np.full_like(t, -50.0)

    for spk_t, trough_depth in ((0.0773, 4.0), (0.0861, 1.5)):
        rel = t - spk_t
        upstroke = 94.0 * np.exp(-0.5 * (np.minimum(rel, 0.0) / 0.00025) ** 2)
        downstroke = 94.0 * np.exp(-0.5 * (np.maximum(rel, 0.0) / 0.00045) ** 2)
        ap_shape = np.where(rel <= 0.0, upstroke, downstroke)
        ahp_shape = -trough_depth * np.exp(-0.5 * ((rel - 0.0018) / 0.0007) ** 2) * (rel > 0.0)
        v += ap_shape + ahp_shape

    return t, v, fs


def test_phase_plane_popup_renders_per_spike_loop_markers_and_ignores_artifacts(qapp):
    """Phase-plane GUI popup renders per-spike loop markers without collapsing to mean voltage."""
    t, v, fs = _make_two_ap_trace(fs=20000.0)
    v_art = v.copy()
    v_art[20] = -30.0
    v_art[21] = -50.0

    res = phase_plane_analysis_wrapper(v_art, t, fs, sigma_ms=0.1, dvdt_threshold=20.0, spike_threshold=-10.0)
    m = res["metrics"]

    tab = MetadataDrivenAnalysisTab("phase_plane_analysis", neo_adapter=MagicMock())
    try:
        tab._current_plot_data = {"time": t, "data": v_art, "units": "mV"}
        tab._viz_popup_phase({"title": "Phase Plane"}, m)
        thresh_x, _ = tab._popup_curves["thresh_marker"].getData()
        max_x, _ = tab._popup_curves["max_marker"].getData()
        assert len(thresh_x) == 2 and len(max_x) == 2
        assert all(mx > -25.0 for mx in max_x)
    finally:
        for win in list(tab._popup_windows):
            win.close()
        tab.cleanup()


def test_burst_brackets_snap_to_nearest_sample_peak_under_float_perturbation(qapp):
    """Burst bracket markers with perturbed float timestamps snap to peak sample rather than k+1 slope."""
    t = np.linspace(0.0, 0.1, 1001)
    v_burst = np.full_like(t, -70.0)
    v_burst[200] = 35.0
    v_burst[201] = -40.0
    v_burst[250] = 32.0
    v_burst[251] = -42.0

    tab = MetadataDrivenAnalysisTab("burst_analysis", neo_adapter=MagicMock())
    try:
        tab._current_plot_data = {"time": t, "data": v_burst, "units": "mV"}
        perturbed_burst = [[float(t[200]) + 1e-12, float(t[250]) + 1e-12]]
        tab._viz_brackets({"data": "bursts", "color": "r"}, {"bursts": perturbed_burst})
        scatters = [it for it in tab._dynamic_plot_items if hasattr(it, "getData") and len(it.getData()[0]) == 2]
        scatter_item = scatters[-1]
        _, sy = scatter_item.getData()
        np.testing.assert_allclose(sy, [35.0, 32.0])
    finally:
        tab.cleanup()


def test_synaptic_threshold_line_renders_at_baseline_offset_level(qapp):
    """Synaptic event threshold line positions at _plot_threshold_level and tracks _baseline_median."""
    tab = MetadataDrivenAnalysisTab("event_detection_threshold", neo_adapter=MagicMock())
    try:
        assert tab._threshold_line is not None
        tab._viz_threshold_line(
            {},
            {"threshold": 8.0, "_plot_threshold_level": -123.0, "_baseline_median": -115.0},
        )
        assert tab._threshold_line.isVisible()
        assert float(tab._threshold_line.value()) == pytest.approx(-123.0)
        assert getattr(tab._threshold_line, "_synaptipy_baseline_median", None) == pytest.approx(-115.0)
    finally:
        tab.cleanup()
