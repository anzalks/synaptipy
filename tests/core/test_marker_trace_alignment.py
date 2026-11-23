# -*- coding: utf-8 -*-
"""Regression suite verifying core plot marker and overlay coordinates lie strictly on trace waveforms."""

from __future__ import annotations

import numpy as np
import pytest

import synaptipy.core.analysis  # noqa: F401
from synaptipy.core.analysis.evoked_responses import _peak_pos_s, calculate_n_pulse_ratio
from synaptipy.core.analysis.single_spike import (
    phase_plane_analysis_wrapper,
    run_spike_detection_wrapper,
)
from synaptipy.core.analysis.synaptic_events import (
    run_event_detection_template_wrapper,
    run_event_detection_threshold_wrapper,
)


def _make_two_ap_trace(fs: float = 20000.0):
    """Synthesize a realistic 2-spike current-clamp trace with steep downstrokes and fast AHP troughs."""
    dt = 1.0 / fs
    t = np.arange(0.0, 0.12, dt) + 0.05  # Non-zero t0 = 50 ms
    v = np.full_like(t, -50.0)

    for spk_t, trough_depth in ((0.0773, 4.0), (0.0861, 1.5)):
        # Slow pre-spike ramp + sharp upstroke + rapid repolarization + fast AHP trough
        rel = t - spk_t
        upstroke = 94.0 * np.exp(-0.5 * (np.minimum(rel, 0.0) / 0.00025) ** 2)
        downstroke = 94.0 * np.exp(-0.5 * (np.maximum(rel, 0.0) / 0.00045) ** 2)
        ap_shape = np.where(rel <= 0.0, upstroke, downstroke)
        ahp_shape = -trough_depth * np.exp(-0.5 * ((rel - 0.0018) / 0.0007) ** 2) * (rel > 0.0)
        v += ap_shape + ahp_shape

    return t, v, fs


def test_spike_detection_peak_threshold_and_ahp_markers_sit_on_trace():
    """Peak, threshold, and AHP markers must all lie on the plotted trace (never floating above trough)."""
    t, v, fs = _make_two_ap_trace(fs=20000.0)
    ljp_mv = 12.0
    res = run_spike_detection_wrapper(
        v.copy(),
        t,
        fs,
        threshold=-20.0,
        dvdt_threshold=20.0,
        ahp_window=0.05,
        onset_lookback=0.01,
        ljp_correction_mv=ljp_mv,
    )
    m = res["metrics"]
    assert m["spike_count"] == 2

    # Interpolate plotted raw trace v(t) linearly (exact polyline geometry drawn by PyQtGraph)
    for x_key, y_key in (
        ("spike_times", "_plot_spike_voltages"),
        ("_threshold_times", "_plot_threshold_voltages"),
        ("_ahp_times", "_plot_ahp_voltages"),
    ):
        xs = np.asarray(m[x_key], dtype=float)
        ys = np.asarray(m[y_key], dtype=float)
        assert len(xs) == 2 and len(ys) == 2
        trace_y_at_x = np.interp(xs, t, v)
        np.testing.assert_allclose(ys, trace_y_at_x, atol=1e-6, err_msg=f"{y_key} drifted off raw trace")

    # AHP marker on first spike must sit at the true fast-AHP minimum (~ -54 mV raw), not ~3 mV above
    assert m["_plot_ahp_voltages"][0] < -53.5


def test_phase_plane_markers_align_with_per_spike_loops_and_ignore_artifacts():
    """Phase-plane threshold and max-dV/dt markers sit on each spike loop and ignore non-spike artifacts."""
    t, v, fs = _make_two_ap_trace(fs=20000.0)
    # Inject a brief subthreshold capacitive artifact at start of trace with large dV/dt but peak < -25 mV
    v_art = v.copy()
    v_art[20] = -30.0
    v_art[21] = -50.0

    res = phase_plane_analysis_wrapper(v_art, t, fs, sigma_ms=0.1, dvdt_threshold=20.0, spike_threshold=-10.0)
    m = res["metrics"]
    assert len(m["_thresh_marker_v"]) == 2
    assert len(m["_max_dvdt_marker_v"]) == 2
    assert all(val == pytest.approx(20.0) for val in m["_thresh_marker_dvdt"])
    # Subthreshold artifact at v=-30..-50 must not be selected as max_dvdt_marker_v
    assert all(mv > -25.0 for mv in m["_max_dvdt_marker_v"])


def test_synaptic_events_markers_stay_on_peaks_under_drifting_baseline_and_threshold_line_tracks_holding():
    """Event markers must not walk down a drifting baseline, and threshold_line sits at holding +/- threshold."""
    fs = 10000.0
    t = np.arange(0.0, 0.5, 1.0 / fs)
    # Holding current drifting steeply (-200 pA/s = -0.2 pA/ms) around -65 pA
    holding = -65.0 - 200.0 * t
    trace = holding.copy()
    # Add two sharp inward mEPSCs (-20 pA amplitude, 0.5 ms rise, 3 ms decay)
    event_onsets = (0.10, 0.25)
    expected_peaks = []
    for t0 in event_onsets:
        rel = np.maximum(0.0, t - t0)
        mask = t >= t0
        ev = -28.0 * (np.exp(-rel[mask] / 0.003) - np.exp(-rel[mask] / 0.0005))
        trace[mask] += ev
        pk_rel = int(np.argmin(ev))
        expected_peaks.append(int(np.searchsorted(t, t0)) + pk_rel)

    res_thr = run_event_detection_threshold_wrapper(
        trace,
        t,
        fs,
        threshold=8.0,
        direction="negative",
        refractory_period=0.040,  # Wide 40 ms refractory window (used to drift +/-20 ms!)
        rolling_baseline_window_ms=50.0,
        compute_kinetics=True,
    )
    mt = res_thr["metrics"]
    assert mt["event_count"] == 2
    np.testing.assert_allclose(mt["_event_peaks"], np.interp(mt["_event_times"], t, trace), atol=1e-9)
    for det_t, exp_idx in zip(mt["_event_times"], expected_peaks):
        assert abs(det_t - t[exp_idx]) <= 0.001  # Within 1 ms of true synaptic peak despite steep drift

    # Threshold line level must sit near trace median (~ -115 pA - 8 pA = -123 pA), not +8 pA
    assert mt["_plot_threshold_level"] == pytest.approx(np.median(trace) - 8.0)

    # Filtered template detection must also snap markers onto raw trace extrema
    res_tpl = run_event_detection_template_wrapper(
        trace,
        t,
        fs,
        threshold_sd=4.0,
        direction="negative",
        tau_rise_ms=0.5,
        tau_decay_ms=3.0,
        filter_freq_hz=1000.0,
    )
    mp = res_tpl["metrics"]
    assert mp["event_count"] >= 2
    np.testing.assert_allclose(mp["_event_peaks"], np.interp(mp["_event_times"], t, trace), atol=1e-9)


def test_evoked_degenerate_windows_stay_on_trace():
    """Degenerate PPR/STP windows must not emit y=0.0 markers off a -70 pA trace."""
    t = np.linspace(0.0, 0.1, 1001)
    v = np.full_like(t, -70.0)

    # Pulse 2 right at end of recording so blanked window is empty (i1 <= i0)
    n_res = calculate_n_pulse_ratio(
        v,
        t,
        stim_onsets=np.array([0.02, 0.0998]),
        response_window_ms=5.0,
        artifact_blanking_ms=2.0,
        polarity="negative",
    )
    for pt, pa in zip(n_res["_peak_times"], n_res["_peak_amps"]):
        assert pa == pytest.approx(-70.0)
        assert 0.0 <= pt <= 0.1

    pt_fb, pv_fb = _peak_pos_s(v, t, onset_s=0.0998, polarity="negative", blank_s=0.002, win_s=0.001)
    assert pv_fb == pytest.approx(-70.0)
    assert pt_fb == pytest.approx(np.interp(pt_fb, t, t))
