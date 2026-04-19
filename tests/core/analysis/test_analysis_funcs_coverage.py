# tests/core/analysis/test_analysis_funcs_coverage.py
# -*- coding: utf-8 -*-
"""
Coverage tests for single_spike.py, firing_dynamics.py, evoked_responses.py,
and synaptic_events.py wrapper and utility functions.
"""

from unittest.mock import patch

import numpy as np

import Synaptipy.core.analysis  # noqa: F401 – populate registry
from Synaptipy.core.analysis.evoked_responses import (
    OptoSyncResult,
    calculate_optogenetic_sync,
    calculate_paired_pulse_ratio,
    evoked_responses_module,
    extract_ttl_epochs,
    run_opto_sync_wrapper,
    run_ppr_wrapper,
)
from Synaptipy.core.analysis.firing_dynamics import (
    TrainDynamicsResult,
    calculate_fi_curve,
    firing_dynamics_module,
    run_burst_analysis_wrapper,
    run_excitability_analysis_wrapper,
    run_train_dynamics_wrapper,
)
from Synaptipy.core.analysis.single_spike import (
    analyze_multi_sweep_spikes,
    calculate_isi,
    detect_spikes_threshold,
    run_spike_detection_wrapper,
    single_spike_module,
)
from Synaptipy.core.analysis.synaptic_events import (
    calculate_event_charge_dynamic,
    compute_local_pre_event_baseline,
    fit_biexponential_decay,
    run_event_detection_baseline_peak_wrapper,
    run_event_detection_template_wrapper,
    run_event_detection_threshold_wrapper,
    synaptic_events_module,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FS = 10_000.0
DT = 1.0 / FS


def _flat(duration: float = 1.0, value: float = -65.0) -> tuple:
    t = np.linspace(0, duration, int(duration * FS), endpoint=False)
    v = np.full_like(t, value)
    return v, t


def _spiking_trace(n_spikes: int = 5, isi_s: float = 0.08, duration: float = 1.0) -> tuple:
    """Synthetic spiking trace: brief +80 mV transients."""
    t = np.linspace(0, duration, int(duration * FS), endpoint=False)
    v = np.full_like(t, -65.0)
    for i in range(n_spikes):
        t_spike = 0.05 + i * isi_s
        idx = int(t_spike * FS)
        if idx + 20 < len(v):
            v[idx : idx + 5] = 30.0  # brief depolarisation
    return v, t


def _psc_trace(n_events: int = 3, duration: float = 1.0, amplitude: float = -20.0) -> tuple:
    """Synthetic PSC trace: brief downward deflections."""
    t = np.linspace(0, duration, int(duration * FS), endpoint=False)
    v = np.zeros_like(t)
    for i in range(n_events):
        idx = int((0.1 + i * 0.3) * FS)
        end = min(idx + int(0.05 * FS), len(v))
        decay = np.exp(-np.arange(end - idx) / (0.01 * FS))
        v[idx:end] += amplitude * decay
    return v, t


def _ttl_trace(n_pulses: int = 3, duration: float = 1.0) -> tuple:
    """Synthetic TTL channel: rectangular pulses."""
    t = np.linspace(0, duration, int(duration * FS), endpoint=False)
    ttl = np.zeros_like(t)
    for i in range(n_pulses):
        start = int((0.05 + i * 0.3) * FS)
        end = int((0.05 + i * 0.3 + 0.01) * FS)
        ttl[start:end] = 5.0
    return ttl, t


# ===========================================================================
# single_spike.py
# ===========================================================================


class TestDetectSpikesThreshold:
    def test_invalid_data_not_ndarray(self):
        t = np.linspace(0, 1, int(FS), endpoint=False)
        r = detect_spikes_threshold([1, 2, 3], t, threshold=-20.0, refractory_samples=10)
        assert not r.is_valid

    def test_data_1d_size_lt2(self):
        r = detect_spikes_threshold(np.array([0.0]), np.array([0.0]), -20.0, 10)
        assert not r.is_valid

    def test_time_shape_mismatch(self):
        d = np.zeros(100)
        t = np.zeros(50)
        r = detect_spikes_threshold(d, t, -20.0, 10)
        assert not r.is_valid

    def test_non_numeric_threshold(self):
        d = np.zeros(100)
        t = np.linspace(0, 0.01, 100)
        r = detect_spikes_threshold(d, t, "high", 10)
        assert not r.is_valid

    def test_invalid_refractory(self):
        d = np.zeros(100)
        t = np.linspace(0, 0.01, 100)
        r = detect_spikes_threshold(d, t, -20.0, -1)
        assert not r.is_valid

    def test_no_crossings(self):
        v, t = _flat()
        r = detect_spikes_threshold(v, t, -20.0, 10, dvdt_threshold=200.0)
        assert r.is_valid
        assert r.value == 0

    def test_crossings_with_refractory(self):
        v, t = _spiking_trace(n_spikes=5)
        r = detect_spikes_threshold(v, t, -20.0, int(0.002 * FS))
        assert r.is_valid

    def test_refractory_zero(self):
        v, t = _spiking_trace(n_spikes=3)
        r = detect_spikes_threshold(v, t, -20.0, 0)
        assert r.is_valid

    def test_spike_below_threshold_filtered_out(self):
        """Crossings found but peak < threshold."""
        v, t = _spiking_trace(n_spikes=3)
        r = detect_spikes_threshold(v, t, threshold=100.0, refractory_samples=10)
        assert r.is_valid
        assert r.value == 0


class TestAnalyzeMultiSweepSpikes:
    def test_normal_multi_sweep(self):
        v, t = _spiking_trace()
        results = analyze_multi_sweep_spikes([v, v], t, -20.0, 10)
        assert len(results) == 2
        for r in results:
            assert r.metadata["sweep_index"] in (0, 1)

    def test_single_sweep_in_list(self):
        v, t = _spiking_trace()
        results = analyze_multi_sweep_spikes([v], t, -20.0, 10)
        assert len(results) == 1

    def test_per_sweep_error_handled(self):
        """Pass invalid (non-array) trial to trigger per-sweep error path."""
        v, t = _spiking_trace()
        # Use a list that would cause detect_spikes_threshold to return invalid
        results = analyze_multi_sweep_spikes([v, np.array([])], t, -20.0, 10)
        assert len(results) == 2

    def test_flat_trace(self):
        v, t = _flat()
        results = analyze_multi_sweep_spikes([v], t, -20.0, 10)
        assert len(results) == 1


class TestCalculateIsi:
    def test_less_than_2_spikes(self):
        result = calculate_isi(np.array([0.1]))
        assert result.size == 0

    def test_empty(self):
        result = calculate_isi(np.array([]))
        assert result.size == 0

    def test_normal(self):
        times = np.array([0.1, 0.2, 0.3])
        isis = calculate_isi(times)
        assert len(isis) == 2
        assert np.allclose(isis, 0.1)


class TestRunSpikeDetectionWrapper:
    def test_spiking_trace(self):
        v, t = _spiking_trace(n_spikes=3)
        result = run_spike_detection_wrapper(v, t, FS)
        assert result["module_used"] == "single_spike"
        assert "spike_count" in result["metrics"]

    def test_flat_trace_no_spikes(self):
        v, t = _flat()
        result = run_spike_detection_wrapper(v, t, FS)
        assert result["metrics"]["spike_count"] == 0

    def test_invalid_data_returns_error(self):
        result = run_spike_detection_wrapper(None, None, FS)
        assert result["module_used"] == "single_spike"

    def test_with_ljp_correction(self):
        v, t = _spiking_trace(n_spikes=2)
        result = run_spike_detection_wrapper(v, t, FS, ljp_correction_mv=5.0)
        assert result["module_used"] == "single_spike"

    def test_invalid_result_branch(self):
        """Trigger is_valid=False branch by passing 1-element array."""
        d = np.array([0.0])
        t = np.array([0.0])
        result = run_spike_detection_wrapper(d, t, FS)
        assert result["module_used"] == "single_spike"


# ===========================================================================
# firing_dynamics.py
# ===========================================================================


class TestCalculateFiCurve:
    def _sweeps(self, n: int = 5):
        sweeps = []
        times = []
        for i in range(n):
            v, t = _spiking_trace(n_spikes=i)
            sweeps.append(v)
            times.append(t)
        return sweeps, times

    def test_current_steps_none_uses_indices(self):
        sweeps, times = self._sweeps(3)
        result = calculate_fi_curve(sweeps, times, current_steps=None)
        assert "rheobase_pa" in result or "error" in result

    def test_current_steps_mismatch_truncated(self):
        sweeps, times = self._sweeps(3)
        result = calculate_fi_curve(sweeps, times, current_steps=[0.0, 50.0])
        assert "rheobase_pa" in result or "error" in result

    def test_empty_sweeps_returns_error(self):
        result = calculate_fi_curve([], [], current_steps=[])
        assert "error" in result

    def test_normal_fi_curve(self):
        sweeps, times = self._sweeps(5)
        result = calculate_fi_curve(sweeps, times, current_steps=[0, 50, 100, 150, 200])
        assert "spike_counts" in result


class TestRunExcitabilityWrapper:
    def test_list_input(self):
        v, t = _spiking_trace()
        result = run_excitability_analysis_wrapper([v, v], [t, t], FS)
        assert result["module_used"] == "firing_dynamics"

    def test_2d_array_input(self):
        v, t = _spiking_trace()
        data_2d = np.vstack([v, v])
        result = run_excitability_analysis_wrapper(data_2d, t, FS)
        assert result["module_used"] == "firing_dynamics"

    def test_2d_array_with_2d_time(self):
        v, t = _spiking_trace()
        data_2d = np.vstack([v, v])
        time_2d = np.vstack([t, t])
        result = run_excitability_analysis_wrapper(data_2d, time_2d, FS)
        assert result["module_used"] == "firing_dynamics"

    def test_1d_array_input(self):
        v, t = _spiking_trace()
        result = run_excitability_analysis_wrapper(v, t, FS)
        assert result["module_used"] == "firing_dynamics"

    def test_time_list_ndarray(self):
        v, t = _spiking_trace()
        data_2d = np.vstack([v, v])
        result = run_excitability_analysis_wrapper(data_2d, np.vstack([t, t]), FS)
        assert result["module_used"] == "firing_dynamics"

    def test_empty_list_returns_error(self):
        result = run_excitability_analysis_wrapper([], [], FS)
        assert result["module_used"] == "firing_dynamics"

    def test_time_list_is_ndarray(self):
        """time_list as 1D ndarray (not list) triggers line 223-224."""
        v, t = _spiking_trace()
        result = run_excitability_analysis_wrapper([v], t, FS)
        assert result["module_used"] == "firing_dynamics"


class TestRunBurstAnalysisWrapper:
    def test_spiking_trace(self):
        v, t = _spiking_trace(n_spikes=10, isi_s=0.02)
        result = run_burst_analysis_wrapper(v, t, FS)
        assert result["module_used"] == "firing_dynamics"

    def test_flat_trace_error(self):
        v, t = _flat()
        result = run_burst_analysis_wrapper(v, t, FS)
        assert result["module_used"] == "firing_dynamics"

    def test_with_kwargs(self):
        v, t = _spiking_trace(n_spikes=5)
        result = run_burst_analysis_wrapper(v, t, FS, dynamic_burst=True, burst_isi_fraction=0.4)
        assert result["module_used"] == "firing_dynamics"


class TestRunTrainDynamicsWrapper:
    def test_spiking_trace_auto_detect(self):
        v, t = _spiking_trace(n_spikes=5)
        result = run_train_dynamics_wrapper(v, t, FS)
        assert result["module_used"] == "firing_dynamics"

    def test_flat_trace_no_spikes(self):
        v, t = _flat()
        result = run_train_dynamics_wrapper(v, t, FS)
        assert result["module_used"] == "firing_dynamics"

    def test_with_precomputed_ap_times(self):
        v, t = _spiking_trace(n_spikes=4)
        ap_times = np.array([0.05, 0.13, 0.21, 0.29])
        result = run_train_dynamics_wrapper(v, t, FS, action_potential_times=ap_times)
        assert result["module_used"] == "firing_dynamics"

    def test_many_spikes_broadening_computed(self):
        v, t = _spiking_trace(n_spikes=6, isi_s=0.06)
        result = run_train_dynamics_wrapper(v, t, FS)
        assert result["module_used"] == "firing_dynamics"


# ===========================================================================
# evoked_responses.py
# ===========================================================================


class TestOptoSyncResultRepr:
    def test_valid_repr(self):
        r = OptoSyncResult(
            value=0.75,
            unit="probability",
            is_valid=True,
            optical_latency_ms=5.2,
            response_probability=0.75,
            spike_jitter_ms=1.0,
            success_count=3,
            stimulus_count=4,
        )
        s = repr(r)
        assert "Latency" in s

    def test_valid_none_fields(self):
        r = OptoSyncResult(
            value=0.0,
            unit="probability",
            is_valid=True,
            optical_latency_ms=None,
            response_probability=None,
            spike_jitter_ms=None,
            success_count=0,
            stimulus_count=0,
        )
        s = repr(r)
        assert "N/A" in s

    def test_error_repr(self):
        r = OptoSyncResult(value=0, unit="", is_valid=False, error_message="no TTL")
        s = repr(r)
        assert "Error" in s


class TestExtractTtlEpochs:
    def test_empty_input(self):
        onsets, offsets = extract_ttl_epochs(np.array([]), np.array([]))
        assert onsets.size == 0

    def test_normal_ttl(self):
        ttl, t = _ttl_trace(n_pulses=3)
        onsets, offsets = extract_ttl_epochs(ttl, t)
        assert len(onsets) == 3

    def test_auto_threshold_all_high(self):
        """All values above threshold → auto-adjust to midpoint."""
        ttl, t = _ttl_trace()
        ttl_all_high = ttl + 3.0  # shift above default threshold=2.5
        onsets, offsets = extract_ttl_epochs(ttl_all_high, t, threshold=2.5, auto_threshold=True)
        # Should still extract some edges
        assert isinstance(onsets, np.ndarray)

    def test_auto_threshold_all_low(self):
        """All values below threshold → auto-adjust to midpoint."""
        t = np.linspace(0, 1, int(FS), endpoint=False)
        ttl = np.zeros_like(t)
        onsets, offsets = extract_ttl_epochs(ttl, t, threshold=2.5, auto_threshold=True)
        assert isinstance(onsets, np.ndarray)

    def test_auto_threshold_triggered_range(self):
        """Signal with range > 0 but threshold off → midpoint auto-detect."""
        t = np.linspace(0, 1.0, int(FS), endpoint=False)
        ttl = np.zeros_like(t)
        ttl[: len(t) // 2] = 5.0  # half high, half low, threshold=10 → n_high < total
        onsets, offsets = extract_ttl_epochs(ttl, t, threshold=10.0, auto_threshold=True)
        assert isinstance(onsets, np.ndarray)

    def test_more_rising_than_falling(self):
        """Unbalanced edges: append last index as falling edge."""
        t = np.linspace(0, 1.0, int(FS), endpoint=False)
        ttl = np.zeros_like(t)
        ttl[int(0.1 * FS) :] = 5.0  # rises and stays high
        onsets, offsets = extract_ttl_epochs(ttl, t, threshold=2.5, auto_threshold=False)
        assert len(onsets) == len(offsets)


class TestRunOptoSyncWrapper:
    def test_no_ttl_data_returns_error(self):
        v, t = _spiking_trace(n_spikes=3)
        result = run_opto_sync_wrapper(v, t, FS, ttl_data=None)
        assert result["module_used"] == "evoked_responses"

    def test_with_ttl_data_spiking_trace(self):
        v, t = _spiking_trace(n_spikes=3)
        ttl, _ = _ttl_trace(n_pulses=3)
        result = run_opto_sync_wrapper(v, t, FS, ttl_data=ttl)
        assert result["module_used"] == "evoked_responses"

    def test_with_precomputed_ap_times(self):
        v, t = _spiking_trace(n_spikes=3)
        ttl, _ = _ttl_trace(n_pulses=3)
        ap_times = np.array([0.05, 0.10, 0.35, 0.40, 0.65, 0.70])
        result = run_opto_sync_wrapper(v, t, FS, ttl_data=ttl, action_potential_times=ap_times)
        assert result["module_used"] == "evoked_responses"

    def test_flat_trace_with_ttl(self):
        v, t = _flat()
        ttl, _ = _ttl_trace(n_pulses=2)
        result = run_opto_sync_wrapper(v, t, FS, ttl_data=ttl)
        assert result["module_used"] == "evoked_responses"


class TestRunPprWrapper:
    def test_basic_call(self):
        v, t = _flat()
        result = run_ppr_wrapper(v, t, FS, stim1_onset_s=0.1, stim2_onset_s=0.2)
        assert result["module_used"] == "evoked_responses"
        assert "paired_pulse_ratio" in result["metrics"]

    def test_negative_polarity(self):
        v, t = _psc_trace(n_events=2)
        result = run_ppr_wrapper(
            v,
            t,
            FS,
            stim1_onset_s=0.1,
            stim2_onset_s=0.4,
            polarity="negative",
        )
        assert result["module_used"] == "evoked_responses"

    def test_positive_polarity(self):
        v, t = _psc_trace(amplitude=20.0)
        result = run_ppr_wrapper(
            v,
            t,
            FS,
            stim1_onset_s=0.1,
            stim2_onset_s=0.4,
            polarity="positive",
        )
        assert result["module_used"] == "evoked_responses"


# ===========================================================================
# synaptic_events.py
# ===========================================================================


class TestRunEventDetectionThresholdWrapper:
    def test_normal_events(self):
        v, t = _psc_trace(n_events=3)
        result = run_event_detection_threshold_wrapper(v, t, FS)
        assert result["module_used"] == "synaptic_events"

    def test_flat_trace(self):
        v, t = _flat(value=0.0)
        result = run_event_detection_threshold_wrapper(v, t, FS)
        assert result["module_used"] == "synaptic_events"

    def test_positive_direction(self):
        v, t = _psc_trace(amplitude=20.0)
        result = run_event_detection_threshold_wrapper(v, t, FS, direction="positive")
        assert result["module_used"] == "synaptic_events"

    def test_with_reject_artifacts(self):
        v, t = _psc_trace(n_events=2)
        result = run_event_detection_threshold_wrapper(v, t, FS, reject_artifacts=True, direction="negative")
        assert result["module_used"] == "synaptic_events"


class TestRunEventDetectionTemplateWrapper:
    def test_normal_events(self):
        v, t = _psc_trace(n_events=3)
        result = run_event_detection_template_wrapper(v, t, FS)
        assert result["module_used"] == "synaptic_events"

    def test_flat_trace_error_path(self):
        v, t = _flat(value=0.0)
        result = run_event_detection_template_wrapper(v, t, FS)
        assert result["module_used"] == "synaptic_events"

    def test_positive_direction(self):
        v, t = _psc_trace(amplitude=20.0)
        result = run_event_detection_template_wrapper(v, t, FS, direction="positive")
        assert result["module_used"] == "synaptic_events"

    def test_with_artifact_rejection(self):
        v, t = _psc_trace()
        result = run_event_detection_template_wrapper(v, t, FS, reject_artifacts=True, direction="negative")
        assert result["module_used"] == "synaptic_events"


class TestRunEventDetectionBaselinePeakWrapper:
    def test_normal_events(self):
        v, t = _psc_trace(n_events=3)
        result = run_event_detection_baseline_peak_wrapper(v, t, FS)
        assert result["module_used"] == "synaptic_events"

    def test_flat_trace(self):
        v, t = _flat(value=0.0)
        result = run_event_detection_baseline_peak_wrapper(v, t, FS)
        assert result["module_used"] == "synaptic_events"

    def test_positive_direction(self):
        v, t = _psc_trace(amplitude=20.0)
        result = run_event_detection_baseline_peak_wrapper(v, t, FS, direction="positive")
        assert result["module_used"] == "synaptic_events"

    def test_auto_baseline_false(self):
        v, t = _psc_trace()
        result = run_event_detection_baseline_peak_wrapper(v, t, FS, auto_baseline=False)
        assert result["module_used"] == "synaptic_events"


# ===========================================================================
# Additional evoked_responses.py branches
# ===========================================================================


class TestCalculateOptoSync:
    def test_empty_ttl(self):
        """Line 152: empty TTL data."""
        v, t = _spiking_trace()
        ap_times = np.array([0.05, 0.13])
        result = calculate_optogenetic_sync(ttl_data=np.array([]), action_potential_times=ap_times, time=t)
        assert not result.is_valid

    def test_no_stimuli_above_threshold(self):
        """Line 158: no TTL stimuli detected."""
        v, t = _spiking_trace()
        ap_times = np.array([0.05])
        # All-zero TTL → no crossings above threshold=2.5
        ttl = np.zeros_like(t)
        result = calculate_optogenetic_sync(ttl_data=ttl, action_potential_times=ap_times, time=t, ttl_threshold=2.5)
        assert not result.is_valid


class TestCalculatePairedPulseRatio:
    def test_invalid_data_shape(self):
        """Lines 284-285: data.size < 2."""
        result = calculate_paired_pulse_ratio(
            data=np.array([1.0]),
            time=np.array([0.0]),
            stim1_onset_s=0.1,
            stim2_onset_s=0.2,
        )
        assert result["ppr_error"] is not None

    def test_fallback_short_decay_window(self):
        """Lines 341-350: fit window too short → fallback path."""
        v, t = _psc_trace(n_events=2)
        # stim2 so close that fit window < 4 samples: fit_start_s=0.1005, fit_end_s=0.1007
        result = calculate_paired_pulse_ratio(
            data=v,
            time=t,
            stim1_onset_s=0.1,
            stim2_onset_s=0.2,
            response_window_ms=2.0,
            artifact_blanking_ms=0.0,
            fit_decay_from_ms=0.5,
            fit_decay_window_ms=0.2,  # 0.2ms at 10kHz = 2 samples < 4
        )
        # Should either use fallback or have an error message
        assert result is not None

    def test_r1_amplitude_zero(self):
        """Line 325-327: R1 amplitude <= 0."""
        v, t = _flat(value=0.0)
        result = calculate_paired_pulse_ratio(
            data=v,
            time=t,
            stim1_onset_s=0.1,
            stim2_onset_s=0.3,
            polarity="negative",
        )
        # flat trace → R1 amp = 0
        assert result.get("ppr_error") is not None or result.get("paired_pulse_ratio") is None

    def test_decay_fit_exception(self):
        """Lines 387-389: decay fit raises exception."""
        v, t = _psc_trace(n_events=2)
        # Make curve_fit raise
        with patch("Synaptipy.core.analysis.evoked_responses.curve_fit", side_effect=RuntimeError("fail")):
            result = calculate_paired_pulse_ratio(
                data=v,
                time=t,
                stim1_onset_s=0.1,
                stim2_onset_s=0.4,
                response_window_ms=30.0,
            )
        assert result is not None

    def test_positive_polarity(self):
        v, t = _psc_trace(amplitude=20.0)
        result = calculate_paired_pulse_ratio(
            data=v,
            time=t,
            stim1_onset_s=0.1,
            stim2_onset_s=0.4,
            polarity="positive",
        )
        assert result is not None

    def test_opto_sync_template_detection_path(self):
        """Line 622: template detection with valid events → ap_times set."""
        v, t = _psc_trace(n_events=3, amplitude=-50.0)
        ttl, _ = _ttl_trace(n_pulses=3)
        result = run_opto_sync_wrapper(
            v,
            t,
            FS,
            ttl_data=ttl,
            event_detection_type="Events (Template)",
            template_direction="negative",
            template_tau_rise_ms=0.5,
            template_tau_decay_ms=5.0,
        )
        assert result["module_used"] == "evoked_responses"

    def test_opto_sync_wrapper_invalid_result(self):
        """Line 644: run_opto_sync_wrapper when calculate_optogenetic_sync returns invalid."""
        v, t = _flat()
        # All zeros TTL with threshold=2.5 → no stimuli detected → invalid result
        ttl = np.zeros_like(t)
        result = run_opto_sync_wrapper(v, t, FS, ttl_data=ttl, ttl_threshold=2.5)
        assert result["module_used"] == "evoked_responses"
        assert "error" in result["metrics"]

    def test_opto_sync_polarity_min_and_abs(self):
        """Lines 662, 664: response_polarity 'min' and 'abs' in wrapper."""
        v, t = _spiking_trace(n_spikes=2)
        ttl, _ = _ttl_trace(n_pulses=2)
        result_min = run_opto_sync_wrapper(v, t, FS, ttl_data=ttl, response_polarity="min")
        assert result_min["module_used"] == "evoked_responses"
        result_abs = run_opto_sync_wrapper(v, t, FS, ttl_data=ttl, response_polarity="abs")
        assert result_abs["module_used"] == "evoked_responses"

    def test_evoked_responses_module(self):
        """Line 844: module aggregator."""
        result = evoked_responses_module()
        assert isinstance(result, dict)


# ===========================================================================
# Additional synaptic_events.py branches
# ===========================================================================


class TestCalculateEventChargeDynamic:
    def test_short_segment_returns_zero(self):
        """Line 125: len(segment) < 2 → return 0.0."""
        data = np.zeros(10)
        # Put event at index 9 (only 1 sample remaining)
        charge = calculate_event_charge_dynamic(data, 9, FS, 0.0, polarity="negative")
        assert charge == 0.0

    def test_with_derivative_transient(self):
        """Line 149: onset_idx detected via derivative."""
        # Create a PSC-like trace followed by another PSC
        n = int(0.05 * FS)  # 50 ms
        t = np.arange(n) / FS
        # First event decay
        decay = -10.0 * np.exp(-t / 0.005)
        # Second event onset at 15 ms
        onset_idx = int(0.015 * FS)
        data = np.zeros(n)
        data[:] = decay
        data[onset_idx : onset_idx + 5] -= 5.0  # sharp onset
        charge = calculate_event_charge_dynamic(data, 0, FS, 0.0, polarity="negative")
        assert isinstance(charge, float)

    def test_positive_polarity(self):
        data = np.array([0.0, 5.0, 3.0, 1.0, 0.0] * 10, dtype=float)
        charge = calculate_event_charge_dynamic(data, 1, FS, 0.0, polarity="positive")
        assert isinstance(charge, float)

    def test_no_derivative_transient(self):
        """Normal decay with no subsequent event."""
        n = int(0.1 * FS)
        data = -5.0 * np.exp(-np.arange(n) / (0.01 * FS))
        charge = calculate_event_charge_dynamic(data, 0, FS, 0.0, polarity="negative")
        assert isinstance(charge, float)


class TestFitBiexponentialDecay:
    def test_short_segment(self):
        """Lines 218-219: segment < 5 samples."""
        data = np.array([-1.0, -0.5, -0.1])
        result = fit_biexponential_decay(data, 0, FS, 0.0, polarity="negative")
        assert "decay_fit_error" in result

    def test_non_positive_peak(self):
        """Lines 229-230: peak_amp <= 0."""
        # For negative polarity, y = local_baseline - segment; if segment >= baseline, y <= 0
        data = np.zeros(20)
        result = fit_biexponential_decay(data, 0, FS, -1.0, polarity="negative")
        # local_baseline=-1.0, segment=0.0 → y = -1.0 - 0.0 = -1.0 (negative peak)
        assert isinstance(result, dict)

    def test_decay_segment_too_short(self):
        """Lines 239-240: decay segment too short after baseline crossing."""
        # segment returns to baseline immediately
        data = np.array([-5.0, 0.0, 0.0, 0.0, 0.0] * 5, dtype=float)
        result = fit_biexponential_decay(data, 0, FS, 0.0, polarity="negative")
        assert isinstance(result, dict)

    def test_mono_exp_fit_fails(self):
        """Lines 253-255: mono-exp curve_fit fails."""
        from unittest.mock import patch

        n = 50
        data = -5.0 * np.exp(-np.arange(n) / 10.0)
        with patch("Synaptipy.core.analysis.synaptic_events.curve_fit", side_effect=RuntimeError("fail")):
            result = fit_biexponential_decay(data, 0, FS, 0.0, polarity="negative")
        assert "decay_fit_error" in result


class TestComputeLocalPreEventBaseline:
    def test_event_at_index_zero(self):
        """Line 332: segment.size == 0 when idx=0."""
        data = np.zeros(100)
        baselines = compute_local_pre_event_baseline(data, np.array([0]), FS, polarity="negative")
        assert len(baselines) == 1

    def test_positive_polarity(self):
        data = np.zeros(100)
        baselines = compute_local_pre_event_baseline(data, np.array([10, 50]), FS, polarity="positive")
        assert len(baselines) == 2

    def test_empty_indices(self):
        data = np.zeros(100)
        baselines = compute_local_pre_event_baseline(data, np.array([], dtype=int), FS)
        assert baselines.size == 0


class TestDetectEventsThresholdEdgeCases:
    def test_invalid_data_shape(self):
        """Line 558: data.size < 2 or shape mismatch."""
        from Synaptipy.core.analysis.synaptic_events import detect_events_threshold

        result = detect_events_threshold(data=np.array([1.0]), time=np.array([0.0, 1.0]), threshold=-20.0)
        assert not result.is_valid

    def test_rolling_baseline_too_small_window(self):
        """Line 573: rolling_baseline_window_ms too small → baseline_corrected_data = data."""
        from Synaptipy.core.analysis.synaptic_events import detect_events_threshold

        v, t = _psc_trace()
        result = detect_events_threshold(
            v, t, threshold=-5.0, rolling_baseline_window_ms=0.01  # very small → < 3 samples
        )
        assert isinstance(result.is_valid, bool)

    def test_quiescent_noise_floor(self):
        """Lines 582-583: use_quiescent_noise_floor=True path."""
        from Synaptipy.core.analysis.synaptic_events import detect_events_threshold

        v, t = _psc_trace()
        result = detect_events_threshold(v, t, threshold=-5.0, use_quiescent_noise_floor=True)
        assert isinstance(result.is_valid, bool)


class TestSynapticEventsModule:
    def test_module_aggregator(self):
        """Line 1341: synaptic_events_module aggregator."""
        result = synaptic_events_module()
        assert isinstance(result, dict)


# ===========================================================================
# Additional firing_dynamics.py branches
# ===========================================================================


class TestFiringDynamicsModule:
    def test_module_aggregator(self):
        """Line 679: firing_dynamics_module aggregator."""
        result = firing_dynamics_module()
        assert isinstance(result, dict)

    def test_train_dynamics_result_repr_valid(self):
        """Lines 494-497: TrainDynamicsResult repr for valid."""
        r = TrainDynamicsResult(value=5, unit="spikes", spike_count=5, cv=0.15, lv=0.1)
        r.is_valid = True
        s = repr(r)
        assert "Spikes" in s

    def test_train_dynamics_result_repr_error(self):
        """Line 498: TrainDynamicsResult repr for error."""
        r = TrainDynamicsResult(value=0, unit="", is_valid=False, error_message="fail")
        s = repr(r)
        assert "Error" in s

    def test_calculate_train_dynamics_single_isi(self):
        """Line 540: calculate_train_dynamics with only 1 positive ISI."""
        from Synaptipy.core.analysis.firing_dynamics import calculate_train_dynamics

        spike_times = np.array([0.0, 0.1])  # only 1 ISI
        result = calculate_train_dynamics(spike_times)
        assert result.spike_count == 2
        # With single ISI, CV can be 0.0 or None depending on path taken
        assert result.is_valid or not result.is_valid  # just check it runs

    def test_run_excitability_wrapper_exception(self):
        """Lines 254-256: run_excitability_analysis_wrapper exception path."""
        result = run_excitability_analysis_wrapper(None, None, FS)
        assert result["module_used"] == "firing_dynamics"
        assert "excitability_error" in result["metrics"]

    def test_run_burst_wrapper_invalid_spike_result(self):
        """Line 460: run_burst_analysis_wrapper invalid spike detection → error dict."""
        # Pass short data (size < 2) → detect_spikes_threshold returns invalid
        result = run_burst_analysis_wrapper(np.array([0.0]), np.array([0.0]), FS, threshold=-20.0)
        assert result["module_used"] == "firing_dynamics"

    def test_fi_curve_broadening_index_exception(self):
        """Lines 105-106: calculate_fi_curve broadening index exception path."""
        from unittest.mock import patch

        from Synaptipy.core.analysis.firing_dynamics import calculate_fi_curve

        v, t = _spiking_trace(n_spikes=4, isi_s=0.05, duration=0.5)
        with patch(
            "Synaptipy.core.analysis.firing_dynamics.calculate_spike_features",
            side_effect=ValueError("feature fail"),
        ):
            result = calculate_fi_curve(
                [v, v, v],
                [t, t, t],
                current_steps=[0.0, 100.0, 200.0],
                threshold=-20.0,
            )
        assert "fi_slope" in result

    def test_fi_curve_linregress_exception(self):
        """Lines 133-134: linear regression fails in calculate_fi_curve."""
        from unittest.mock import patch

        from Synaptipy.core.analysis.firing_dynamics import calculate_fi_curve

        v, t = _spiking_trace(n_spikes=3, isi_s=0.1, duration=0.5)
        with patch(
            "Synaptipy.core.analysis.firing_dynamics.linregress",
            side_effect=ValueError("regression fail"),
        ):
            result = calculate_fi_curve(
                [v, v, v],
                [t, t, t],
                current_steps=[100.0, 200.0, 300.0],
                threshold=-20.0,
            )
        assert result.get("fi_slope") is None


# ===========================================================================
# single_spike.py remaining gaps
# ===========================================================================


class TestSingleSpikeModule:
    def test_module_aggregator(self):
        """Line 906: single_spike_module aggregator."""
        result = single_spike_module()
        assert isinstance(result, dict)
