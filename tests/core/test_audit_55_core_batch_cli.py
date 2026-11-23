# -*- coding: utf-8 -*-
"""
Regression test suite for Codebase Defect Audit (Worker 1: Core DSP, Biophysics, Batch & CLI).

Covers defects:
- A4-core: run_baseline_subtraction_processor no-op when method in ("none", "off", "")
- B1/B10: synaptic_events template kernel guards (tau_decay <= 0, tau_rise <= 0),
          find_quiescent_baseline_rms short/empty guards, filter_freq_hz wiring,
          tau_decay_ms min=0.05 in registry ui_params
- B2: evoked_responses run_opto_sync_wrapper inter-stimulus window cap & baseline-relative abs polarity
- B3/B6: passive_properties run_rin_analysis_wrapper current-unit handling &
         calculate_iv_curve empty post-baseline guard
- B4/B7: firing_dynamics min_spikes threading, train_dynamics sliced segment onset, empty clip mask handling,
         excitability current_steps override
- B5/B10: single_spike ahp_window=0 guard, fahp/mahp forwarding, calculate_dvdt & phase_plane guards,
          epoch_manager from_ttl boundary edge guard
- B8/B9: data_model Dask / None trial handling, empty trial_indices average,
         processing_pipeline LJP units & artifact guard
- C1-C5, D5-close: BatchAnalysisEngine channel filter by name/id, secondary channel whitelist & cross-file averaging,
                   preprocessing default scope & unequal-length averaging, manual_stimulus_timing, selected_trials
                   with expects_list, pure method_selector rejection, recording.close() on disk-loaded recordings
- CLI & ParameterTemplateManager: _list_analyses aggregator filtering, private column stripping, invalid pipeline error
                                  handling, slash-containing template names, valid built-in template schemas
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest

import synaptipy.core.analysis  # noqa: F401
from synaptipy.application.cli.main import _list_analyses, _run_batch
from synaptipy.application.services.parameter_templates import ParameterTemplateManager
from synaptipy.core.analysis.batch_engine import BatchAnalysisEngine
from synaptipy.core.analysis.epoch_manager import EpochManager
from synaptipy.core.analysis.evoked_responses import evoked_responses_module, run_opto_sync_wrapper
from synaptipy.core.analysis.firing_dynamics import (
    firing_dynamics_module,
    run_burst_analysis_wrapper,
    run_excitability_analysis_wrapper,
    run_train_dynamics_wrapper,
)
from synaptipy.core.analysis.passive_properties import (
    calculate_iv_curve,
    passive_properties_module,
    run_rin_analysis_wrapper,
)
from synaptipy.core.analysis.preprocessing import run_baseline_subtraction_processor
from synaptipy.core.analysis.registry import AnalysisRegistry
from synaptipy.core.analysis.single_spike import (
    calculate_dvdt,
    calculate_spike_features,
    phase_plane_analysis_wrapper,
    run_spike_detection_wrapper,
    single_spike_module,
)
from synaptipy.core.analysis.synaptic_events import (
    detect_events_template,
    find_quiescent_baseline_rms,
    run_event_detection_template_wrapper,
    synaptic_events_module,
)
from synaptipy.core.constants import NOISE_FLOOR_MIN_RMS
from synaptipy.core.data_model import Channel, Recording
from synaptipy.core.processing_pipeline import _apply_ljp_offset, apply_trace_corrections
from synaptipy.core.protocols import ProtocolAssignment, ProtocolSource

# ---------------------------------------------------------------------------
# 1. A4-core: Baseline subtraction processor "none" / "off" / "" no-op
# ---------------------------------------------------------------------------


class TestBaselineSubtractionNoOp:
    @pytest.mark.parametrize("method", ["none", "None", "off", "OFF", "", None])
    def test_disabled_method_returns_trace_unchanged(self, method):
        fs = 1000.0
        t = np.arange(100) / fs
        data = np.full(100, -68.5)
        out = run_baseline_subtraction_processor(data, t, fs, method=method)
        np.testing.assert_allclose(out, data)

    def test_default_still_subtracts_mean(self):
        fs = 1000.0
        t = np.arange(100) / fs
        data = np.full(100, -65.0)
        out = run_baseline_subtraction_processor(data, t, fs)
        np.testing.assert_allclose(out, 0.0, atol=1e-12)


# ---------------------------------------------------------------------------
# 2. B1 & B10: Synaptic events guards, instantaneous rise, filter_freq_hz
# ---------------------------------------------------------------------------


class TestSynapticEventsAuditFixes:
    def test_tau_decay_min_in_ui_params(self):
        deconv_meta = AnalysisRegistry.get_metadata("event_detection_deconvolution")
        td_param = next(p for p in deconv_meta["ui_params"] if p["name"] == "tau_decay_ms")
        assert td_param["min"] == pytest.approx(0.05)

        opto_meta = AnalysisRegistry.get_metadata("optogenetic_sync")
        opto_td = next(p for p in opto_meta["ui_params"] if p["name"] == "template_tau_decay_ms")
        assert opto_td["min"] == pytest.approx(0.05)

    @pytest.mark.parametrize("bad_decay", [0.0, -0.005])
    def test_detect_events_template_rejects_nonpositive_tau_decay(self, bad_decay):
        data = np.zeros(1000)
        res = detect_events_template(
            data, sampling_rate=10000.0, threshold_std=4.0, tau_rise=0.001, tau_decay=bad_decay
        )
        assert not res.is_valid
        assert "tau_decay must be positive" in (res.error_message or "")

    def test_detect_events_template_zero_tau_rise_no_nan(self):
        fs = 10000.0
        t = np.arange(2000) / fs
        data = np.zeros_like(t)
        # Instantaneous-rise negative event at 0.05 s
        onset = 500
        kt = np.arange(250) / fs
        data[onset : onset + 250] = -25.0 * np.exp(-kt / 0.005)
        res = detect_events_template(
            data,
            sampling_rate=fs,
            threshold_std=3.5,
            tau_rise=0.0,
            tau_decay=0.005,
            polarity="negative",
            kernel_shape="bi-exponential",
        )
        assert res.is_valid
        assert res.event_count >= 1
        assert np.all(np.isfinite(res.event_amplitudes))

    def test_find_quiescent_baseline_rms_edge_guards(self):
        rms_none, bounds_none = find_quiescent_baseline_rms(None, 10000.0)
        assert rms_none == NOISE_FLOOR_MIN_RMS
        assert bounds_none == (0, 0)

        rms_short, bounds_short = find_quiescent_baseline_rms(np.array([1.0]), 10000.0)
        assert rms_short == NOISE_FLOOR_MIN_RMS
        assert bounds_short == (0, 1)

        rms_bad_fs, bounds_bad_fs = find_quiescent_baseline_rms(np.zeros(100), 0.0)
        assert rms_bad_fs == NOISE_FLOOR_MIN_RMS
        assert bounds_bad_fs == (0, 100)

    def test_template_wrapper_wires_filter_freq_hz(self):
        fs = 20000.0
        n = 4000
        t = np.arange(n) / fs
        rng = np.random.default_rng(123)
        # High-frequency noise + clean negative synaptic event
        hf_noise = 8.0 * np.sin(2.0 * np.pi * 5000.0 * t) + rng.normal(0.0, 0.2, n)
        event = np.zeros(n)
        kt = np.arange(400) / fs
        event[1000:1400] = -15.0 * (np.exp(-kt / 0.006) - np.exp(-kt / 0.0006))
        trace = event + hf_noise

        out = run_event_detection_template_wrapper(
            trace,
            t,
            fs,
            tau_rise_ms=0.6,
            tau_decay_ms=6.0,
            threshold_sd=4.0,
            direction="negative",
            filter_freq_hz=800.0,
        )
        assert out["metrics"]["event_count"] >= 1


# ---------------------------------------------------------------------------
# 3. B2: Optogenetic sync window cap and baseline-centered abs polarity
# ---------------------------------------------------------------------------


class TestOptoSyncAuditFixes:
    def test_multi_pulse_window_capped_before_next_stimulus(self):
        fs = 10000.0
        t = np.arange(0.0, 0.5, 1.0 / fs)
        ttl = np.zeros_like(t)
        # Two pulses 20 ms apart (0.10 s and 0.12 s), amplitude_window_ms = 100 ms
        ttl[1000:1020] = 5.0
        ttl[1200:1220] = 5.0

        data = np.zeros_like(t)
        # Pulse 1 response = +5 mV at 0.105 s; Pulse 2 huge response = +50 mV at 0.125 s
        data[1050] = 5.0
        data[1250] = 50.0

        res = run_opto_sync_wrapper(
            data,
            t,
            fs,
            ttl_data=ttl,
            amplitude_window_ms=100.0,
            artifact_blanking_ms=1.0,
            response_polarity="max",
        )
        amps = res["metrics"]["response_amplitudes"]
        assert len(amps) == 2
        assert amps[0] == pytest.approx(5.0, abs=1e-6)
        assert amps[1] == pytest.approx(50.0, abs=1e-6)

    def test_abs_polarity_subtracts_resting_baseline_before_argmax(self):
        fs = 10000.0
        t = np.arange(0.0, 0.3, 1.0 / fs)
        ttl = np.zeros_like(t)
        ttl[1000:1050] = 5.0

        # Resting potential at -70 mV with a +12 mV EPSP reaching -58 mV
        data = np.full_like(t, -70.0)
        data[1050:1150] = -58.0

        res = run_opto_sync_wrapper(
            data,
            t,
            fs,
            ttl_data=ttl,
            amplitude_window_ms=50.0,
            artifact_blanking_ms=1.0,
            response_polarity="abs",
        )
        amps = res["metrics"]["response_amplitudes"]
        assert len(amps) == 1
        assert amps[0] == pytest.approx(12.0, abs=1e-6)


# ---------------------------------------------------------------------------
# 4. B3 & B6: Passive properties Rin current units & IV curve post-baseline guard
# ---------------------------------------------------------------------------


class TestPassivePropertiesAuditFixes:
    def test_rin_wrapper_current_units_zeroes_conflicting_current_amplitude(self):
        fs = 10000.0
        t = np.linspace(0.0, 0.6, int(0.6 * fs), endpoint=False)
        # Voltage-clamp trace in pA: -10 mV step evokes -50 pA steady-state current -> Rin = 200 MOhm
        i_trace = np.zeros_like(t)
        i_trace[(t >= 0.1) & (t < 0.5)] = -50.0

        out = run_rin_analysis_wrapper(
            i_trace,
            t,
            fs,
            units="pA",
            current_amplitude=-50.0,
            voltage_step=-10.0,
            auto_detect_pulse=False,
            baseline_start=0.0,
            baseline_end=0.08,
            response_start=0.2,
            response_end=0.45,
        )
        assert out["metrics"]["rin_mohm"] == pytest.approx(200.0, rel=0.02)

    def test_rin_wrapper_omitted_steps_default_by_channel_unit(self):
        fs = 10000.0
        t = np.linspace(0.0, 0.6, int(0.6 * fs), endpoint=False)
        i_trace = np.zeros_like(t)
        i_trace[(t >= 0.1) & (t < 0.5)] = -50.0
        out_vc = run_rin_analysis_wrapper(
            i_trace,
            t,
            fs,
            units="pA",
            auto_detect_pulse=False,
            baseline_start=0.0,
            baseline_end=0.08,
            response_start=0.2,
            response_end=0.45,
        )
        assert out_vc["metrics"]["rin_mohm"] == pytest.approx(200.0, rel=0.02)

        v_trace = np.full_like(t, -65.0)
        v_trace[(t >= 0.1) & (t < 0.5)] = -75.0  # -10 mV for default -50 pA -> 200 MOhm
        out_cc = run_rin_analysis_wrapper(
            v_trace,
            t,
            fs,
            units="mV",
            auto_detect_pulse=False,
            baseline_start=0.0,
            baseline_end=0.08,
            response_start=0.2,
            response_end=0.45,
        )
        assert out_cc["metrics"]["rin_mohm"] == pytest.approx(200.0, rel=0.02)

    def test_rin_wrapper_explicit_zeros_still_error(self):
        fs = 1000.0
        t = np.linspace(0.0, 0.5, 500, endpoint=False)
        out = run_rin_analysis_wrapper(np.zeros(500), t, fs, current_amplitude=0.0, voltage_step=0.0, units="pA")
        assert "rin_error" in out["metrics"]

    def test_calculate_iv_curve_late_baseline_window_does_not_crash(self):
        fs = 1000.0
        # t[-1] = 0.999 < baseline_window[1] = 1.0 -> time >= 1.0 is empty!
        t = np.linspace(0.0, 1.0, int(fs), endpoint=False)
        sweeps = []
        steps = [-100.0, -50.0, 0.0]
        for c in steps:
            v = np.full_like(t, -65.0)
            v[(t >= 0.1) & (t < 0.6)] = -65.0 + (c / 1000.0) * 200.0  # 200 MOhm
            sweeps.append(v)

        res = calculate_iv_curve(
            sweeps,
            [t, t, t],
            steps,
            baseline_window=(0.8, 1.0),
            response_window=(0.2, 0.5),
        )
        assert res["rin_aggregate_mohm"] == pytest.approx(200.0, rel=1e-3)


# ---------------------------------------------------------------------------
# 5. B4 & B7: Firing dynamics min_spikes, sliced onset, empty clip, current_steps
# ---------------------------------------------------------------------------


class TestFiringDynamicsAuditFixes:
    @staticmethod
    def _make_spike_trace(spike_times, duration=1.0, fs=10000.0):
        n = int(duration * fs)
        t = np.linspace(0.0, duration, n, endpoint=False)
        v = np.full(n, -65.0)
        for st in spike_times:
            idx = int(st * fs)
            if 5 <= idx < n - 5:
                v[idx - 3 : idx + 1] = np.linspace(-65.0, 30.0, 4)
                v[idx + 1 : idx + 5] = np.linspace(20.0, -65.0, 4)
        return v, t, fs

    def test_burst_wrapper_threads_min_spikes(self):
        # 2-spike doublet (5 ms apart) + 3-spike triplet (5 ms apart)
        v, t, fs = self._make_spike_trace([0.100, 0.105, 0.500, 0.505, 0.510])
        res_2 = run_burst_analysis_wrapper(
            v, t, fs, threshold=-20.0, max_isi_start=0.01, max_isi_end=0.02, min_spikes=2
        )
        res_3 = run_burst_analysis_wrapper(
            v, t, fs, threshold=-20.0, max_isi_start=0.01, max_isi_end=0.02, min_spikes=3
        )
        assert res_2["metrics"]["burst_count"] == 2
        assert res_3["metrics"]["burst_count"] == 1

    def test_train_dynamics_unclipped_uses_segment_t0_for_delay(self):
        v, t, fs = self._make_spike_trace([0.050, 0.100, 0.150], duration=0.3)
        # Shift segment time axis so segment starts at t = 2.0 s; first spike at 2.050 s -> 50 ms delay
        t_shifted = t + 2.0
        res = run_train_dynamics_wrapper(v, t_shifted, fs, spike_threshold=-20.0)
        assert res["metrics"]["first_spike_delay_ms"] == pytest.approx(50.0, abs=1.0)

    def test_out_of_bounds_analysis_window_does_not_keep_unclipped_spikes(self):
        v, t, fs = self._make_spike_trace([0.10, 0.11, 0.12, 0.13])
        ex = run_excitability_analysis_wrapper([v], [t], fs, analysis_start_s=5.0, analysis_end_s=6.0)
        assert ex["metrics"]["max_freq_hz"] == 0.0

        bu = run_burst_analysis_wrapper(v, t, fs, analysis_start_s=5.0, analysis_end_s=6.0)
        assert bu["metrics"]["burst_count"] == 0

        td = run_train_dynamics_wrapper(v, t, fs, analysis_start_s=5.0, analysis_end_s=6.0)
        assert td["metrics"]["spike_count"] == 0

    def test_excitability_honors_explicit_current_steps(self):
        v_sub, t, fs = self._make_spike_trace([])
        v_sp1, _, _ = self._make_spike_trace([0.1, 0.2, 0.3])
        v_sp2, _, _ = self._make_spike_trace([0.1, 0.15, 0.2, 0.25, 0.3])
        custom_steps = [0.0, 125.0, 250.0]
        res = run_excitability_analysis_wrapper(
            [v_sub, v_sp1, v_sp2],
            [t, t, t],
            fs,
            current_steps=custom_steps,
        )
        assert res["metrics"]["current_steps"] == custom_steps
        assert res["metrics"]["rheobase_pa"] == pytest.approx(125.0)


# ---------------------------------------------------------------------------
# 6. B5 & B10: Single spike ahp_window=0, fahp/mahp kwargs, dvdt/phase-plane, TTL edge
# ---------------------------------------------------------------------------


class TestSingleSpikeAndEpochAuditFixes:
    def test_spike_features_ahp_window_zero_preserves_ap_metrics(self):
        fs = 20000.0
        t = np.arange(2000) / fs
        v = np.full_like(t, -70.0)
        # Synthetic spike peaking at index 400
        v[380:401] = np.linspace(-70.0, 35.0, 21)
        v[401:440] = np.linspace(35.0, -75.0, 39)
        v[440:600] = np.linspace(-75.0, -70.0, 160)

        feats = calculate_spike_features(v, t, np.array([400]), ahp_window_sec=0.0)
        assert len(feats) == 1
        assert np.isfinite(feats[0].amplitude)
        assert np.isfinite(feats[0].half_width)
        assert np.isnan(feats[0].trough_v)
        assert np.isnan(feats[0].ahp_duration_half)
        assert np.isnan(feats[0].adp_amplitude)

    def test_spike_detection_wrapper_forwards_fahp_mahp_windows(self):
        fs = 20000.0
        t = np.arange(4000) / fs
        v = np.full_like(t, -65.0)
        v[380:401] = np.linspace(-65.0, 30.0, 21)
        v[401:420] = np.linspace(30.0, -68.0, 19)
        # Distinct deep trough at +25 ms (index 900)
        v[850:950] = -82.0

        res_narrow = run_spike_detection_wrapper(
            v, t, fs, threshold=-20.0, ahp_window=0.0, fahp_window_ms=[1.0, 3.0], mahp_window_ms=[5.0, 10.0]
        )
        res_wide = run_spike_detection_wrapper(
            v, t, fs, threshold=-20.0, ahp_window=0.0, fahp_window_ms=[1.0, 3.0], mahp_window_ms=[20.0, 30.0]
        )
        assert res_wide["metrics"]["mahp_depth_mean"] > res_narrow["metrics"]["mahp_depth_mean"] + 10.0

    def test_dvdt_and_phase_plane_short_or_invalid_inputs_do_not_crash(self):
        assert calculate_dvdt(np.array([1.0]), 10000.0).shape == (1,)
        assert calculate_dvdt(np.array([1.0, 2.0]), 0.0).shape == (2,)
        assert calculate_dvdt(None, 10000.0).size == 0

        res_short = phase_plane_analysis_wrapper(np.array([-65.0]), np.array([0.0]), 10000.0)
        assert "phase_plane_error" in res_short["metrics"]

        res_bad_fs = phase_plane_analysis_wrapper(np.array([-65.0, -64.0]), np.array([0.0, 0.001]), 0.0)
        assert "phase_plane_error" in res_bad_fs["metrics"]

    def test_module_aggregators_accept_positional_and_keyword_args(self):
        for fn in (
            passive_properties_module,
            single_spike_module,
            firing_dynamics_module,
            synaptic_events_module,
            evoked_responses_module,
        ):
            assert fn(np.zeros(10), np.zeros(10), 1000.0, extra=1) == {}

    def test_epoch_manager_from_ttl_final_sample_edge_with_zero_pre_stim(self):
        t = np.linspace(0.0, 1.0, 101)
        ttl = np.zeros_like(t)
        ttl[-1] = 5.0  # Rising edge on very last sample
        em = EpochManager()
        epochs = em.from_ttl(ttl, t, pre_stim_s=0.0, post_stim_s=0.5, min_inter_epoch_s=0.5)
        # Baseline [0, 1.0] is valid; zero-duration Stim [1.0, 1.0] must be skipped without ValueError
        assert any(e.name == "Baseline" for e in epochs)
        assert all(e.duration > 0 for e in epochs)


# ---------------------------------------------------------------------------
# 7. B8 & B9: Data model Dask / None trials, empty average, LJP & artifact guards
# ---------------------------------------------------------------------------


class _FakeDaskArray:
    """Lightweight Dask-like array stub with __dask_graph__ that tracks materialization."""

    def __init__(self, arr: np.ndarray):
        self._arr = np.asarray(arr, dtype=float)
        self.shape = self._arr.shape
        self.ndim = self._arr.ndim
        self.size = self._arr.size
        self.computed = False

    def __dask_graph__(self):
        return {"x": 1}

    def __array__(self, dtype=None):
        self.computed = True
        return np.asarray(self._arr, dtype=dtype) if dtype is not None else self._arr


class TestDataModelAndPipelineAuditFixes:
    def test_channel_preserves_dask_and_partial_none_trials(self):
        dask_t0 = _FakeDaskArray(np.array([-60.0, -62.0, -64.0]))
        ch = Channel("0", "Vm", "mV", 1000.0, [dask_t0, None, [1.0, 2.0, 3.0]])
        # Dask trial is NOT eagerly computed during __init__ or num_samples
        assert not dask_t0.computed
        assert ch.num_trials == 3
        assert ch.num_samples == 3
        assert ch.data_trials[1] is None

        # Bounds skip None safely and materialize valid arrays
        lo, hi = ch.get_data_bounds()
        assert lo == pytest.approx(-64.0)
        assert hi == pytest.approx(3.0)

        fin_lo, fin_hi = ch.get_finite_data_bounds()
        assert fin_lo == pytest.approx(-64.0)
        assert fin_hi == pytest.approx(3.0)

        # get_data materializes Dask array to np.ndarray
        t0_data = ch.get_data(0)
        assert isinstance(t0_data, np.ndarray)
        np.testing.assert_allclose(t0_data, [-60.0, -62.0, -64.0])

    def test_get_time_aligned_average_empty_trial_indices_returns_empty(self):
        ch = Channel("0", "Vm", "mV", 1000.0, [np.ones(20) * 5.0, np.ones(20) * 10.0])
        avg = ch.get_time_aligned_average(trial_indices=[])
        assert avg.is_empty
        assert avg.data is None

    @pytest.mark.parametrize(
        "unit", ["nanoamperes", "amp", "amps", "uA", "\u00b5A", "\u03bcA", "microampere", "microamperes"]
    )
    def test_ljp_offset_skips_all_current_unit_spellings(self, unit):
        arr = np.array([-100.0, -50.0])
        out = _apply_ljp_offset(arr.copy(), ljp_mv=12.0, units=unit)
        np.testing.assert_allclose(out, arr)

    @pytest.mark.parametrize("unit", ["uV", "\u00b5V", "\u03bcV", "microvolts"])
    def test_ljp_offset_scales_microvolt_spellings(self, unit):
        arr = np.array([-60000.0, -50000.0])
        out = _apply_ljp_offset(arr.copy(), ljp_mv=10.0, units=unit)
        np.testing.assert_allclose(out, [-70000.0, -60000.0])

    def test_apply_trace_corrections_artifact_guard_and_method_forwarding(self):
        data = np.array([0.0, 0.0, 100.0, 100.0, 0.0, 0.0])
        # time=None must not crash when artifact_interp_steps is supplied
        out_no_time = apply_trace_corrections(
            data,
            None,
            1000.0,
            artifact_interp_steps=[{"onset_time": 0.002, "duration_ms": 2.0, "method": "zero"}],
        )
        np.testing.assert_allclose(out_no_time, data)

        # Custom method="zero" is forwarded rather than hardcoded "linear"
        t = np.arange(len(data)) / 1000.0
        out_zero = apply_trace_corrections(
            np.ones_like(data) * 10.0,
            t,
            1000.0,
            artifact_interp_steps=[{"onset_time": 0.001, "duration_ms": 2.5, "method": "zero"}],
        )
        assert np.any(out_zero == 0.0)


# ---------------------------------------------------------------------------
# 8. C1-C5 & D5-close: BatchAnalysisEngine fixes
# ---------------------------------------------------------------------------


class TestBatchEngineAuditFixes:
    def test_channel_filter_matches_channel_name_and_whitelists_secondary_channel(self, tmp_path):
        rec = Recording(tmp_path / "opto.abf")
        fs = 10000.0
        n = 5000
        vm = np.full(n, -65.0)
        vm[1050] = 20.0
        ttl = np.zeros(n)
        ttl[1000:1100] = 5.0
        # Dict keys are numeric IDs ("0", "1"), while human names are "Vm" and "LaserTTL"
        rec.channels = {
            "0": Channel("0", "Vm", "mV", fs, [vm]),
            "1": Channel("1", "LaserTTL", "V", fs, [ttl]),
        }
        rec.source_handle = MagicMock()

        engine = BatchAnalysisEngine()
        read_mock = MagicMock(return_value=rec)
        engine.neo_adapter.read_recording = read_mock

        pipeline = [
            {
                "analysis": "optogenetic_sync",
                "scope": "first_trial",
                "secondary_channel": "LaserTTL",
                "params": {"spike_threshold": 0.0},
            }
        ]
        f_path = tmp_path / "opto.abf"
        f_path.write_bytes(b"")
        df = engine.run_batch([f_path], pipeline, channel_filter=["Vm"])

        # Whitelist passed to reader must include both primary ("Vm") and secondary ("LaserTTL")
        _, call_kwargs = read_mock.call_args
        assert set(call_kwargs["channel_whitelist"]) == {"Vm", "LaserTTL"}
        # Output only contains primary channel "Vm", with valid opto sync result and closed handle
        assert len(df) == 1
        assert df.iloc[0]["channel"] == "Vm"
        assert df.iloc[0]["stimulus_count"] == 1
        rec.source_handle.close.assert_called_once()

    def test_preprocessing_default_scope_and_unequal_trial_averaging(self):
        rec = Recording(Path("unequal.abf"))
        fs = 1000.0
        # Two trials of different lengths, both with +50 mV DC offset
        t0 = np.full(500, 50.0)
        t1 = np.full(800, 50.0)
        rec.channels = {"Vm": Channel("Vm", "Vm", "mV", fs, [t0, t1])}

        engine = BatchAnalysisEngine()
        # Note: preprocessing task omits "scope", downstream uses "average"
        pipeline = [
            {"analysis": "baseline_subtraction", "params": {"method": "constant", "offset_value": 50.0}},
            {"analysis": "rmp_analysis", "scope": "average", "params": {"baseline_start": 0.0, "baseline_end": 0.2}},
        ]
        df = engine.run_batch([rec], pipeline)
        assert len(df) == 1
        assert df.iloc[0]["rmp_mv"] == pytest.approx(0.0, abs=1e-6)

    def test_manual_stimulus_timing_bypasses_secondary_channel_requirement(self):
        rec = Recording(Path("ppr_manual.abf"))
        fs = 10000.0
        n = 5000
        t = np.arange(n) / fs
        trace = np.zeros(n)
        for onset, amp in ((0.1, -20.0), (0.2, -30.0)):
            idx = int(onset * fs)
            kt = np.arange(300) / fs
            trace[idx : idx + 300] += amp * np.exp(-kt / 0.01)
        rec.channels = {"Im": Channel("Im", "Im", "pA", fs, [trace])}
        assert len(t) == n

        engine = BatchAnalysisEngine()
        pipeline = [
            {
                "analysis": "paired_pulse_ratio",
                "scope": "first_trial",
                "params": {
                    "use_ttl": False,
                    "stim1_onset_s": 0.1,
                    "stim2_onset_s": 0.2,
                    "polarity": "negative",
                },
            },
            {
                "analysis": "stimulus_train_stp",
                "scope": "first_trial",
                "params": {
                    "use_ttl": False,
                    "stim_start_s": 0.1,
                    "stim_frequency_hz": 10.0,
                    "n_pulses": 2,
                    "polarity": "negative",
                },
            },
        ]
        df = engine.run_batch([rec], pipeline)
        assert len(df) == 2
        assert "error" not in df.columns or df["error"].isna().all()
        ppr_row = df[df["analysis"] == "paired_pulse_ratio"].iloc[0]
        stp_row = df[df["analysis"] == "stimulus_train_stp"].iloc[0]
        assert ppr_row["ratio_p2"] > 1.2
        assert stp_row["pulse_count"] == 2

    def test_cross_file_average_injects_averaged_secondary_channel_and_closes_disk_files(self, tmp_path):
        fs = 10000.0
        n = 4000
        recs = []
        paths = []
        for idx, resp_amp in enumerate((-20.0, -40.0)):
            p = tmp_path / f"f{idx}.abf"
            p.write_bytes(b"")
            paths.append(p)
            rec = Recording(p)
            rec.source_handle = MagicMock()
            im = np.zeros(n)
            im[1020:1150] = resp_amp
            ttl = np.zeros(n)
            ttl[1000:1050] = 5.0
            rec.channels = {
                "0": Channel("0", "Im", "pA", fs, [im]),
                "1": Channel("1", "TTL", "V", fs, [ttl]),
            }
            recs.append(rec)

        engine = BatchAnalysisEngine()
        engine.neo_adapter.read_recording = MagicMock(side_effect=recs)
        pipeline = [
            {
                "analysis": "optogenetic_sync",
                "scope": "average",
                "secondary_channel": "TTL",
                "params": {"response_polarity": "min", "amplitude_window_ms": 30.0},
            }
        ]
        df = engine.run_batch(paths, pipeline, channel_filter=["Im"], cross_file_average=True)
        assert len(df) == 1
        assert df.iloc[0]["mean_response_amplitude"] == pytest.approx(-30.0, abs=1e-4)
        assert df.iloc[0]["secondary_channel"] == "TTL"
        for rec in recs:
            rec.source_handle.close.assert_called_once()

    def test_selected_trials_with_expects_list_and_mixed_protocol_check(self):
        rec = Recording(Path("iv.abf"))
        fs = 1000.0
        t_len = 600
        # 4 trials: trials 0, 1, 2 are subthreshold steps; trial 3 is excluded
        trials = []
        for c in (-100.0, -50.0, 0.0, 500.0):
            v = np.full(t_len, -65.0)
            v[100:500] = -65.0 + (c / 1000.0) * 150.0
            trials.append(v)
        rec.channels = {"Vm": Channel("Vm", "Vm", "mV", fs, trials)}

        engine = BatchAnalysisEngine()
        pipeline = [
            {
                "analysis": "iv_curve_analysis",
                "scope": "selected_trials",
                "params": {
                    "trial_indices": "0,1,2",
                    "start_current": -100.0,
                    "step_current": 50.0,
                    "baseline_start": 0.0,
                    "baseline_end": 0.08,
                    "response_start": 0.2,
                    "response_end": 0.45,
                },
            }
        ]
        df = engine.run_batch([rec], pipeline)
        assert len(df) == 1
        assert df.iloc[0]["selected_trial_indices"] == "0,1,2"
        assert df.iloc[0]["rin_aggregate_mohm"] == pytest.approx(150.0, rel=1e-3)

        # Mixed explicit protocol segments across selected_trials for expects_list must block
        rec.protocol_map.add(
            ProtocolAssignment(
                "current_step",
                (0,),
                profile_id="proto_a",
                source=ProtocolSource.RECORDED,
                parameters={"command": "recorded"},
                verified=True,
            )
        )
        rec.protocol_map.add(
            ProtocolAssignment(
                "current_step",
                (1,),
                profile_id="proto_b",
                source=ProtocolSource.RECORDED,
                parameters={"command": "recorded"},
                verified=True,
            )
        )
        df_mixed = engine.run_batch([rec], pipeline)
        assert df_mixed.iloc[0]["protocol_status"] == "mixed_protocol"

    def test_pure_method_selector_rejected_in_batch_and_rin_units_forwarded(self):
        rec = Recording(Path("vc.abf"))
        fs = 1000.0
        i_trace = np.zeros(600)
        i_trace[100:500] = -50.0
        rec.channels = {"Im": Channel("Im", "Im", "pA", fs, [i_trace])}

        engine = BatchAnalysisEngine()
        pipeline = [
            {"analysis": "passive_properties", "scope": "first_trial"},
            {
                "analysis": "rin_analysis",
                "scope": "first_trial",
                "params": {
                    "auto_detect_pulse": False,
                    "baseline_start": 0.0,
                    "baseline_end": 0.08,
                    "response_start": 0.2,
                    "response_end": 0.45,
                },
            },
        ]
        df = engine.run_batch([rec], pipeline)
        agg_row = df[df["analysis"] == "passive_properties"].iloc[0]
        rin_row = df[df["analysis"] == "rin_analysis"].iloc[0]
        assert "UI group aggregator" in agg_row["error"]
        assert rin_row["rin_mohm"] == pytest.approx(200.0, rel=0.02)


# ---------------------------------------------------------------------------
# 9. CLI & ParameterTemplateManager fixes
# ---------------------------------------------------------------------------


class TestCliAndTemplatesAuditFixes:
    def test_cli_list_analyses_excludes_pure_method_selectors(self, capsys):
        rc = _list_analyses()
        assert rc == 0
        listed = set(capsys.readouterr().out.strip().splitlines())
        for aggregator in (
            "passive_properties",
            "single_spike",
            "firing_dynamics",
            "synaptic_events",
            "evoked_responses",
        ):
            assert aggregator not in listed
        assert "rmp_analysis" in listed
        assert "spike_detection" in listed

    def test_cli_run_batch_handles_invalid_pipeline_and_strips_private_csv_cols(self, tmp_path, capsys):
        bad_pl = tmp_path / "bad.json"
        bad_pl.write_text("{not valid json")
        rec_file = tmp_path / "rec.abf"
        rec_file.write_bytes(b"")
        out_csv = tmp_path / "out.csv"

        args_bad = argparse.Namespace(
            files=[str(rec_file)],
            pipeline=bad_pl,
            output=out_csv,
            channel=None,
            max_workers=1,
            cross_file_average=False,
        )
        assert _run_batch(args_bad) == 2
        assert "Invalid pipeline file" in capsys.readouterr().err

        # Valid run with private _-prefixed columns in DataFrame
        good_pl = tmp_path / "good.json"
        good_pl.write_text(json.dumps([{"analysis": "rmp_analysis"}]))
        args_good = argparse.Namespace(
            files=[str(rec_file)],
            pipeline=good_pl,
            output=out_csv,
            channel=None,
            max_workers=1,
            cross_file_average=False,
        )
        from unittest.mock import patch

        import pandas as pd

        fake_df = pd.DataFrame([{"analysis": "rmp_analysis", "rmp_mv": -65.0, "_raw_arrays": {"a": [1, 2]}}])
        with patch("synaptipy.application.cli.main.BatchAnalysisEngine") as mock_cls:
            mock_cls.return_value.run_batch.return_value = fake_df
            assert _run_batch(args_good) == 0

        csv_header = out_csv.read_text(encoding="utf-8").splitlines()[0].split(",")
        assert "rmp_mv" in csv_header
        assert "_raw_arrays" not in csv_header

    def test_parameter_templates_slash_name_and_valid_builtins(self, tmp_path):
        mgr = ParameterTemplateManager(template_dir=tmp_path)
        path = mgr.save_template("I/V\\Curve: Standard", {"start_current": -100.0}, analysis_type="iv_curve_analysis")
        assert path.exists()
        assert path.parent == tmp_path
        assert mgr.load_template("I/V\\Curve: Standard") == {"start_current": -100.0}
        listed = mgr.list_templates()
        assert listed[0]["name"] == "I/V\\Curve: Standard"
        assert mgr.delete_template("I/V\\Curve: Standard") is True
        assert mgr.load_template("I/V\\Curve: Standard") is None

        registered = set(AnalysisRegistry.list_registered())
        for tmpl in mgr.get_builtin_templates():
            a_type = tmpl["analysis_type"]
            assert a_type in registered
            meta = AnalysisRegistry.get_metadata(a_type)
            assert not (bool(meta.get("method_selector")) and not meta.get("ui_params"))
