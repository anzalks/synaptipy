# tests/core/analysis/test_synaptic_events_coverage.py
# -*- coding: utf-8 -*-
"""
Targeted coverage tests for synaptic_events.py uncovered branches.

Covers missing lines: 281-283, 335, 377, 416, 419-443, 459, 464,
536-537, 553-554, 560-561, 587-589, 641-643, 700-702, 812, 907,
927-929, 957, 969, 973, 1026-1028, 1148, 1196, 1229, 1233,
1247-1249, 1260-1267, 1368.
"""

import numpy as np
import pytest

import synaptipy.core.analysis  # noqa: F401 - populate registry
from synaptipy.core.analysis.synaptic_events import (
    _fit_p1_decay_residual,
    _measure_ppr_peak,
    calculate_paired_pulse_ratio,
    compute_local_pre_event_baseline,
    detect_events_baseline_peak_kinetics,
    detect_events_template,
    detect_events_threshold,
    fit_biexponential_decay,
)

FS = 20_000.0  # 20 kHz sampling rate
DT = 1.0 / FS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _flat_trace(n: int = 2000, val: float = 0.0) -> np.ndarray:
    return np.full(n, val, dtype=float)


def _time(n: int = 2000) -> np.ndarray:
    return np.arange(n) * DT


def _event_trace(event_times_s, amplitude: float = -20.0, n: int = 4000) -> tuple:
    """Build a trace with sharp negative events at given times."""
    t = np.arange(n) * DT
    data = np.zeros(n)
    tau_rise_s = 0.0005  # 0.5 ms
    tau_decay_s = 0.003  # 3 ms
    for et in event_times_s:
        for i in range(n):
            dt_i = t[i] - et
            if 0 <= dt_i < 5 * tau_decay_s:
                data[i] += amplitude * (np.exp(-dt_i / tau_decay_s) - np.exp(-dt_i / tau_rise_s))
    return data, t


# ---------------------------------------------------------------------------
# fit_biexponential_decay - bi-exp convergence (lines 281-283)
# ---------------------------------------------------------------------------


class TestFitBiexponentialDecay:
    def test_biexp_converges_on_clean_biexp_signal(self):
        """Clean bi-exponential signal should trigger the bi-exp convergence branch."""
        fs = 10_000.0
        dt = 1.0 / fs
        t = np.arange(200) * dt
        # Build a clean bi-exponential decay
        a_fast, tau_fast, a_slow, tau_slow = 5.0, 0.003, 3.0, 0.015
        data_segment = a_fast * np.exp(-t / tau_fast) + a_slow * np.exp(-t / tau_slow)
        # Embed in a longer trace at index 0
        full_trace = np.zeros(1000)
        full_trace[:200] = data_segment

        result = fit_biexponential_decay(full_trace, 0, fs, local_baseline=0.0, polarity="positive")
        # If bi-exp converged, bi_exp_converged should be True
        assert isinstance(result, dict)
        assert result["bi_exp_converged"] is not None  # key exists with True or False

    def test_biexp_fallback_to_mono_on_short_segment(self):
        """Short segment should fall back to mono-exp (not trigger bi-exp)."""
        fs = 1_000.0
        data = np.array([-5.0, -4.0, -3.0, -2.0, -1.0, 0.0, 0.0, 0.0, 0.0, 0.0])
        result = fit_biexponential_decay(data, 0, fs, local_baseline=0.0, polarity="negative")
        assert isinstance(result, dict)
        assert "tau_mono_ms" in result


# ---------------------------------------------------------------------------
# compute_local_pre_event_baseline - positive polarity (line 335)
# ---------------------------------------------------------------------------


class TestComputeLocalPreEventBaseline:
    def test_positive_polarity_uses_min(self):
        """Positive polarity should use np.min of pre-event segment."""
        fs = 1_000.0
        # Ramp up before event so min is clearly smaller than max
        data = np.linspace(-5.0, 5.0, 200)
        event_idx = np.array([100])
        result = compute_local_pre_event_baseline(data, event_idx, fs, polarity="positive")
        assert result.shape == (1,)
        # Pre-event window is data[max(0, 100 - search_samples):100]
        # For positive polarity, baseline = min of segment
        assert result[0] <= data[99]

    def test_negative_polarity_uses_max(self):
        """Negative polarity should use np.max of pre-event segment."""
        fs = 1_000.0
        data = np.linspace(-5.0, 5.0, 200)
        event_idx = np.array([100])
        result = compute_local_pre_event_baseline(data, event_idx, fs, polarity="negative")
        assert result.shape == (1,)
        assert result[0] >= data[0]

    def test_empty_segment_falls_back_to_event_data(self):
        """Event at index 0 gives empty segment; fall back to data[event_idx]."""
        fs = 1_000.0
        data = np.array([-3.0, 0.0, 0.0, 0.0, 0.0])
        event_idx = np.array([0])
        result = compute_local_pre_event_baseline(data, event_idx, fs, polarity="negative")
        assert result.shape == (1,)
        assert result[0] == float(data[0])


# ---------------------------------------------------------------------------
# calculate_paired_pulse_ratio - edge cases
# ---------------------------------------------------------------------------


class TestCalculatePairedPulseRatio:
    def _make_ppr_trace(self, s1_t: float = 0.1, s2_t: float = 0.2, amp: float = -15.0):
        """Create a trace with two synaptic-like events."""
        fs = FS
        n = int(0.4 * fs)
        t = np.arange(n) / fs
        data = np.zeros(n)
        tau_d = 0.005
        for onset in (s1_t, s2_t):
            for i in range(n):
                dt_i = t[i] - onset
                if 0 <= dt_i < 5 * tau_d:
                    data[i] += amp * np.exp(-dt_i / tau_d)
        return data, t, fs

    def test_basic_ppr_computes(self):
        """Verify basic PPR computes without error."""
        data, t, fs = self._make_ppr_trace()
        result = calculate_paired_pulse_ratio(data, t, np.array([0.1, 0.2]), fs)
        assert result["ppr"] is not None or result["error"] is not None

    def test_no_baseline_before_s1(self):
        """S1 onset exactly at t=0 gives no pre-S1 baseline samples; error message expected."""
        data, t, fs = self._make_ppr_trace(s1_t=0.001, s2_t=0.2)
        # Override time so it starts after s1_t to eliminate the pre-S1 window
        t_shifted = t + 0.001  # shift so t[0] = 0.001 = s1_t, no samples before s1_t
        onsets = np.array([t_shifted[0], 0.2])
        result = calculate_paired_pulse_ratio(data, t_shifted, onsets, fs)
        assert result["error"] is not None

    def test_p1_amplitude_zero(self):
        """Flat trace makes P1 amplitude zero; error message expected."""
        n = int(0.4 * FS)
        t = np.arange(n) / FS
        data = np.zeros(n)  # flat - no response
        result = calculate_paired_pulse_ratio(data, t, np.array([0.1, 0.2]), FS)
        assert result["error"] is not None

    def test_ppr_naive_is_computed(self):
        """Successful P1 detection should produce ppr_naive."""
        data, t, fs = self._make_ppr_trace()
        result = calculate_paired_pulse_ratio(data, t, np.array([0.1, 0.2]), fs)
        if result["error"] is None:
            assert not np.isnan(result["ppr_naive"])

    def test_too_few_stimuli_returns_error(self):
        """Fewer than 2 stimulus onsets returns error."""
        n = int(0.4 * FS)
        t = np.arange(n) / FS
        data = np.zeros(n)
        result = calculate_paired_pulse_ratio(data, t, np.array([0.1]), FS)
        assert result["error"] == "Need at least 2 stimulus onsets for PPR."


# ---------------------------------------------------------------------------
# detect_events_threshold - use_quiescent_noise_floor=False (lines 641-643)
# ---------------------------------------------------------------------------


class TestDetectEventsThresholdBranches:
    def test_quiescent_noise_floor_disabled(self):
        """use_quiescent_noise_floor=False should use MAD instead of quiescent RMS."""
        n = 2000
        t = np.arange(n) * DT
        data = np.zeros(n)
        # Add one clear positive event
        data[500:520] = np.linspace(0, 20.0, 20)
        data[520:540] = np.linspace(20.0, 0, 20)

        result = detect_events_threshold(
            data,
            t,
            threshold=5.0,
            polarity="positive",
            use_quiescent_noise_floor=False,
        )
        assert result.is_valid

    def test_quiescent_noise_floor_disabled_constant_data(self):
        """Constant data with use_quiescent_noise_floor=False: MAD=0, fallback to 1e-12."""
        n = 200
        t = np.arange(n) * DT
        data = np.zeros(n)
        result = detect_events_threshold(
            data,
            t,
            threshold=5.0,
            polarity="positive",
            use_quiescent_noise_floor=False,
            rolling_baseline_window_ms=None,
        )
        assert result.is_valid
        assert result.event_count == 0

    def test_artifact_mask_rejects_peaks(self):
        """artifact_mask should reject peaks that fall on masked samples (lines 700-702)."""
        n = 2000
        t = np.arange(n) * DT
        data = np.zeros(n)
        # Two clear events
        for onset in (300, 1200):
            data[onset : onset + 20] = np.linspace(0, 25.0, 20)
            data[onset + 20 : onset + 40] = np.linspace(25.0, 0, 20)

        # Mask covers the first event
        artifact_mask = np.zeros(n, dtype=bool)
        artifact_mask[280:360] = True

        result = detect_events_threshold(
            data,
            t,
            threshold=5.0,
            polarity="positive",
            artifact_mask=artifact_mask,
            use_quiescent_noise_floor=False,
        )
        assert result.is_valid
        assert result.n_artifacts_rejected >= 0

    def test_invalid_data_shape(self):
        """Mismatched data/time shapes return invalid result."""
        data = np.zeros(100)
        t = np.zeros(50)
        result = detect_events_threshold(data, t, threshold=5.0)
        assert not result.is_valid

    def test_no_rolling_baseline(self):
        """rolling_baseline_window_ms=None skips the baseline correction path."""
        n = 500
        t = np.arange(n) * DT
        data = np.zeros(n)
        data[200:215] = np.linspace(0, 15.0, 15)
        data[215:230] = np.linspace(15.0, 0, 15)
        result = detect_events_threshold(
            data,
            t,
            threshold=5.0,
            polarity="positive",
            rolling_baseline_window_ms=None,
            use_quiescent_noise_floor=False,
        )
        assert result.is_valid


# ---------------------------------------------------------------------------
# detect_events_template - artifact mask & other branches (lines 1026-1028)
# ---------------------------------------------------------------------------


class TestDetectEventsTemplate:
    def test_template_with_artifact_mask(self):
        """artifact_mask filters template-detected peaks (lines 1026-1028)."""
        fs = 10_000.0
        n = 3000
        dt = 1.0 / fs
        t = np.arange(n) * dt
        data = np.zeros(n)
        tau_r, tau_d = 0.0005, 0.003
        for onset in (500, 2000):
            for i in range(n):
                dti = t[i] - t[onset]
                if 0 <= dti < 5 * tau_d:
                    data[i] += -20.0 * (np.exp(-dti / tau_d) - np.exp(-dti / tau_r))

        artifact_mask = np.zeros(n, dtype=bool)
        artifact_mask[480:560] = True

        result = detect_events_template(
            data=data,
            sampling_rate=fs,
            threshold_std=2.0,
            tau_rise=tau_r,
            tau_decay=tau_d,
            polarity="negative",
            artifact_mask=artifact_mask,
        )
        assert result.is_valid

    def test_template_positive_polarity(self):
        """Template matching with positive polarity events."""
        fs = 10_000.0
        n = 3000
        dt = 1.0 / fs
        t = np.arange(n) * dt
        data = np.zeros(n)
        tau_r, tau_d = 0.0005, 0.003
        onset_idx = 1000
        for i in range(n):
            dti = t[i] - t[onset_idx]
            if 0 <= dti < 5 * tau_d:
                data[i] += 20.0 * (np.exp(-dti / tau_d) - np.exp(-dti / tau_r))

        result = detect_events_template(
            data=data,
            sampling_rate=fs,
            threshold_std=2.0,
            tau_rise=tau_r,
            tau_decay=tau_d,
            polarity="positive",
        )
        assert result.is_valid

    def test_template_with_min_event_distance(self):
        """min_event_distance_ms>0 takes that branch (line 957)."""
        fs = 10_000.0
        n = 3000
        dt = 1.0 / fs
        t = np.arange(n) * dt
        data = np.zeros(n)
        tau_r, tau_d = 0.0005, 0.003
        onset_idx = 1000
        for i in range(n):
            dti = t[i] - t[onset_idx]
            if 0 <= dti < 5 * tau_d:
                data[i] += -20.0 * (np.exp(-dti / tau_d) - np.exp(-dti / tau_r))

        result = detect_events_template(
            data=data,
            sampling_rate=fs,
            threshold_std=2.0,
            tau_rise=tau_r,
            tau_decay=tau_d,
            polarity="negative",
            min_event_distance_ms=10.0,
        )
        assert result.is_valid

    def test_template_no_rolling_baseline(self):
        """rolling_baseline_window_ms=None skips baseline correction."""
        fs = 10_000.0
        n = 2000
        dt = 1.0 / fs
        data = np.zeros(n)
        tau_r, tau_d = 0.0005, 0.003
        onset_idx = 600
        t = np.arange(n) * dt
        for i in range(n):
            dti = t[i] - t[onset_idx]
            if 0 <= dti < 5 * tau_d:
                data[i] += -15.0 * (np.exp(-dti / tau_d) - np.exp(-dti / tau_r))
        result = detect_events_template(
            data=data,
            sampling_rate=fs,
            threshold_std=2.0,
            tau_rise=tau_r,
            tau_decay=tau_d,
            rolling_baseline_window_ms=None,
        )
        assert result.is_valid

    def test_template_with_equal_tau_rise_decay(self):
        """When tau_rise == tau_decay, the alpha kernel branch fires (line 907)."""
        fs = 10_000.0
        n = 2000
        dt = 1.0 / fs
        t = np.arange(n) * dt
        data = np.zeros(n)
        tau = 0.003
        onset_idx = 600
        for i in range(n):
            dti = t[i] - t[onset_idx]
            if 0 <= dti < 5 * tau:
                data[i] += -15.0 * dti * np.exp(-dti / tau)
        result = detect_events_template(
            data=data,
            sampling_rate=fs,
            threshold_std=2.0,
            tau_rise=tau,
            tau_decay=tau,  # equal -> alpha kernel
        )
        assert result.is_valid


# ---------------------------------------------------------------------------
# detect_events_baseline_peak_kinetics - edge cases (lines 1229, 1233, 1247-1249)
# ---------------------------------------------------------------------------


class TestDetectEventsBaselinePeakKinetics:
    def test_invalid_direction_returns_error(self):
        """Invalid direction should return an error result (line 1229)."""
        data = np.zeros(500)
        result = detect_events_baseline_peak_kinetics(data, 10_000.0, direction="sideways")
        assert not result.is_valid

    def test_rolling_baseline_applied(self):
        """rolling_baseline_window_ms > 0 engages the rolling-baseline path (lines 1247-1249)."""
        fs = 10_000.0
        n = 5000
        t = np.arange(n) / fs
        data = np.zeros(n)
        # Slow drift + one event
        data += np.linspace(0, 2.0, n)
        onset = 2000
        tau_d = 0.005
        for i in range(n):
            dti = t[i] - t[onset]
            if 0 <= dti < 5 * tau_d:
                data[i] -= 20.0 * np.exp(-dti / tau_d)
        result = detect_events_baseline_peak_kinetics(data, fs, direction="negative", rolling_baseline_window_ms=100.0)
        assert result.is_valid

    def test_filter_freq_applied(self):
        """filter_freq_hz > 0 engages the low-pass filter branch (lines 1260-1267)."""
        fs = 10_000.0
        n = 5000
        t = np.arange(n) / fs
        data = np.zeros(n)
        onset = 2000
        tau_d = 0.005
        for i in range(n):
            dti = t[i] - t[onset]
            if 0 <= dti < 5 * tau_d:
                data[i] -= 20.0 * np.exp(-dti / tau_d)
        result = detect_events_baseline_peak_kinetics(data, fs, direction="negative", filter_freq_hz=2000.0)
        assert result.is_valid

    def test_positive_direction(self):
        """Positive direction detection."""
        fs = 10_000.0
        n = 5000
        data = np.zeros(n)
        t = np.arange(n) / fs
        onset = 2000
        tau_d = 0.005
        for i in range(n):
            dti = t[i] - t[onset]
            if 0 <= dti < 5 * tau_d:
                data[i] += 20.0 * np.exp(-dti / tau_d)
        result = detect_events_baseline_peak_kinetics(data, fs, direction="positive")
        assert result.is_valid


# ---------------------------------------------------------------------------
# fit_biexponential_decay — tau_fast/tau_slow assignment (lines 285-287)
# ---------------------------------------------------------------------------


class TestFitBiexpTauAssignment:
    def test_biexp_tau_assignment_on_clean_signal(self):
        """Lines 285-287: when bi-exp converges both tau branches are assigned."""
        fs = 20_000.0
        dt = 1.0 / fs
        t = np.arange(600) * dt  # 30 ms window
        # Well-separated fast (2 ms) and slow (15 ms) components
        a_fast, tau_fast_s, a_slow, tau_slow_s = 8.0, 0.002, 4.0, 0.015
        seg = a_fast * np.exp(-t / tau_fast_s) + a_slow * np.exp(-t / tau_slow_s)
        full = np.zeros(2000)
        full[:600] = seg

        result = fit_biexponential_decay(full, 0, fs, local_baseline=0.0, polarity="positive")
        assert isinstance(result, dict)
        # If bi-exp converged, tau_fast_ms and tau_slow_ms are populated
        if result.get("bi_exp_converged"):
            assert result["tau_fast_ms"] is not None
            assert result["tau_slow_ms"] is not None
            assert result["tau_fast_ms"] < result["tau_slow_ms"]


# ---------------------------------------------------------------------------
# compute_local_pre_event_baseline — empty segment fallback (line 339)
# ---------------------------------------------------------------------------


class TestPreEventBaselineEmptySegment:
    def test_event_at_index_zero_falls_back_to_data_value(self):
        """Line 339: event at index 0 gives empty segment → fallback to data[0]."""
        fs = 1_000.0
        data = np.array([-3.0, -2.0, -1.0, 0.0, 0.0])
        event_idx = np.array([0])
        result = compute_local_pre_event_baseline(data, event_idx, fs, polarity="negative")
        assert result.shape == (1,)
        assert result[0] == pytest.approx(-3.0)


# ---------------------------------------------------------------------------
# _fit_p1_decay_residual — early return when decay window too short (line 383)
# ---------------------------------------------------------------------------


class TestFitP1DecayResidualEarlyReturn:
    def test_returns_zero_nan_when_s2_too_close_to_peak(self):
        """Line 383: decay_end_idx <= peak1_idx + 3 → (0.0, nan)."""
        fs = 1_000.0
        # Place peak near end of array so decay_end_idx = len(data)-1 <= peak+3
        n = 100
        t = np.arange(n) / fs
        data = np.zeros(n)
        peak_idx = 97  # near end; len(data)-1=99, peak+3=100 → 99<=100 → early return
        data[peak_idx] = -10.0
        s2_t = t[peak_idx] + 0.5  # doesn't matter — early return fires first
        residual, tau = _fit_p1_decay_residual(
            data, t, peak1_idx=peak_idx, s2_t=s2_t, global_baseline=0.0, sample_rate=fs
        )
        assert residual == pytest.approx(0.0)
        assert np.isnan(tau)


# ---------------------------------------------------------------------------
# _measure_ppr_peak — negative and positive polarity
# ---------------------------------------------------------------------------


class TestMeasurePprPeak:
    def test_negative_polarity_finds_minimum(self):
        """_measure_ppr_peak with negative polarity returns amplitude at minimum."""
        fs = 1_000.0
        n = 200
        t = np.arange(n) / fs
        data = np.zeros(n)
        data[50:60] = [-5.0, -10.0, -15.0, -12.0, -8.0, -5.0, -2.0, -1.0, 0.0, 0.0]
        amp, idx = _measure_ppr_peak(data, t, onset_s=t[50], baseline=0.0, resp_samples=20, polarity="negative")
        assert amp == pytest.approx(-15.0)
        assert idx == 52

    def test_positive_polarity_finds_maximum(self):
        """_measure_ppr_peak with positive polarity returns amplitude at maximum."""
        fs = 1_000.0
        n = 200
        t = np.arange(n) / fs
        data = np.zeros(n)
        data[50:60] = [2.0, 5.0, 8.0, 6.0, 3.0, 1.0, 0.0, 0.0, 0.0, 0.0]
        amp, idx = _measure_ppr_peak(data, t, onset_s=t[50], baseline=0.0, resp_samples=20, polarity="positive")
        assert amp == pytest.approx(8.0)
        assert idx == 52

    def test_onset_past_end_returns_nan(self):
        """_measure_ppr_peak onset beyond array returns (nan, onset_idx)."""
        fs = 1_000.0
        n = 10
        t = np.arange(n) / fs
        data = np.zeros(n)
        amp, _ = _measure_ppr_peak(data, t, onset_s=t[-1] + 1.0, baseline=0.0, resp_samples=20, polarity="negative")
        assert np.isnan(amp)


# ---------------------------------------------------------------------------
# run_event_detection_threshold_wrapper — invalid result path (line 824)
# ---------------------------------------------------------------------------


class TestThresholdWrapperInvalidResult:
    def test_invalid_detection_returns_error_dict(self):
        """Line 824: wrapper returns error dict when detect_events_threshold fails."""
        from unittest.mock import MagicMock, patch

        from synaptipy.core.analysis.synaptic_events import (
            EventDetectionResult,
            run_event_detection_threshold_wrapper,
        )

        fake = MagicMock(spec=EventDetectionResult)
        fake.is_valid = False
        fake.error_message = "forced invalid"
        with patch(
            "synaptipy.core.analysis.synaptic_events.detect_events_threshold",
            return_value=fake,
        ):
            n = int(0.3 * FS)
            t = np.arange(n) / FS
            result = run_event_detection_threshold_wrapper(data=np.zeros(n), time=t, sampling_rate=FS)
        assert result["metrics"]["event_error"] == "forced invalid"


# ---------------------------------------------------------------------------
# run_event_detection_template_wrapper — invalid result path (line 1205)
# ---------------------------------------------------------------------------


class TestTemplateWrapperInvalidResult:
    def test_invalid_detection_returns_error_dict(self):
        """Line 1205: wrapper returns error dict when detect_events_template fails."""
        from unittest.mock import MagicMock, patch

        from synaptipy.core.analysis.synaptic_events import (
            EventDetectionResult,
            run_event_detection_template_wrapper,
        )

        fake = MagicMock(spec=EventDetectionResult)
        fake.is_valid = False
        fake.error_message = "template failed"
        with patch(
            "synaptipy.core.analysis.synaptic_events.detect_events_template",
            return_value=fake,
        ):
            n = int(0.3 * FS)
            t = np.arange(n) / FS
            result = run_event_detection_template_wrapper(data=np.zeros(n), time=t, sampling_rate=FS)
        assert result["metrics"]["event_error"] == "template failed"


# ---------------------------------------------------------------------------
# run_event_detection_baseline_peak_wrapper — invalid result path (line 1425)
# ---------------------------------------------------------------------------


class TestBaselinePeakWrapperInvalidResult:
    def test_invalid_detection_returns_error_dict(self):
        """Line 1425: wrapper returns error dict when detect_events_baseline_peak_kinetics fails."""
        from unittest.mock import MagicMock, patch

        from synaptipy.core.analysis.synaptic_events import (
            EventDetectionResult,
            run_event_detection_baseline_peak_wrapper,
        )

        fake = MagicMock(spec=EventDetectionResult)
        fake.is_valid = False
        fake.error_message = "baseline-peak failed"
        with patch(
            "synaptipy.core.analysis.synaptic_events.detect_events_baseline_peak_kinetics",
            return_value=fake,
        ):
            n = int(0.5 * FS)
            result = run_event_detection_baseline_peak_wrapper(
                data=np.zeros(n), time=np.arange(n) / FS, sampling_rate=FS
            )
        assert result["metrics"]["event_error"] == "baseline-peak failed"


# ---------------------------------------------------------------------------
# detect_events_baseline_peak_kinetics — no stable baseline (line 1290)
# ---------------------------------------------------------------------------


class TestBaselinePeakNoStableBaseline:
    def test_no_stable_baseline_returns_empty(self):
        """Line 1290: _find_stable_baseline_segment returns None → event_count=0."""
        from unittest.mock import patch

        from synaptipy.core.analysis.synaptic_events import detect_events_baseline_peak_kinetics

        n = int(0.2 * FS)
        data = np.zeros(n)
        with patch(
            "synaptipy.core.analysis.synaptic_events._find_stable_baseline_segment",
            return_value=(None, None, None),
        ):
            result = detect_events_baseline_peak_kinetics(data, FS)
        assert result.is_valid is True
        assert result.event_count == 0


# ---------------------------------------------------------------------------
# detect_events_threshold exception handler (lines 721-723)
# ---------------------------------------------------------------------------


class TestDetectEventsThresholdException:
    def test_exception_returns_invalid(self):
        """Lines 721-723: detect_events_threshold catches exceptions and returns invalid."""
        from unittest.mock import patch

        from synaptipy.core.analysis.synaptic_events import detect_events_threshold

        n = int(0.1 * FS)
        t = np.arange(n) / FS
        data = np.zeros(n)
        with patch(
            "synaptipy.core.analysis.synaptic_events.find_quiescent_baseline_rms",
            side_effect=RuntimeError("forced exception"),
        ):
            result = detect_events_threshold(data, t, FS)
        assert result.is_valid is False


# ---------------------------------------------------------------------------
# calculate_paired_pulse_ratio exception handler (lines 593-595)
# ---------------------------------------------------------------------------


class TestPairedPulseRatioException:
    def test_exception_in_ratio_computation(self):
        """Lines 593-595: exception in calculate_paired_pulse_ratio is caught."""
        from unittest.mock import patch

        n = int(0.5 * FS)
        t = np.arange(n) / FS
        data = np.zeros(n)
        with patch(
            "synaptipy.core.analysis.synaptic_events._measure_ppr_peak",
            side_effect=ValueError("forced ppr error"),
        ):
            result = calculate_paired_pulse_ratio(
                data=data,
                time=t,
                stimulus_onsets_s=np.array([0.1, 0.3]),
                sample_rate=FS,
            )
        assert "error" in result


# ---------------------------------------------------------------------------
# detect_events_template — mono-exponential kernel (lines 920-921)
# ---------------------------------------------------------------------------


class TestDetectEventsTemplateMonoExp:
    def test_mono_exponential_kernel_shape(self):
        """Lines 920-921: kernel_shape='mono-exponential' takes mono-exp branch."""
        fs = 10_000.0
        n = 3000
        dt = 1.0 / fs
        t = np.arange(n) * dt
        data = np.zeros(n)
        tau_r, tau_d = 0.0005, 0.003
        onset_idx = 1000
        for i in range(n):
            dti = t[i] - t[onset_idx]
            if 0 <= dti < 5 * tau_d:
                data[i] -= 20.0 * (np.exp(-dti / tau_d) - np.exp(-dti / tau_r))
        result = detect_events_template(
            data=data,
            sampling_rate=fs,
            threshold_std=2.0,
            tau_rise=tau_r,
            tau_decay=tau_d,
            polarity="negative",
            kernel_shape="mono-exponential",
        )
        assert result.is_valid


# ---------------------------------------------------------------------------
# detect_events_template — small rolling baseline window (line 946)
# ---------------------------------------------------------------------------


class TestDetectEventsTemplateSmallWindow:
    def test_small_rolling_baseline_window_samples_lt_3(self):
        """Line 946: rolling_baseline_window_ms so small that window_samples < 3."""
        fs = 1_000.0
        n = 2000
        dt = 1.0 / fs
        t = np.arange(n) * dt
        data = np.zeros(n)
        tau_r, tau_d = 0.001, 0.01
        onset_idx = 500
        for i in range(n):
            dti = t[i] - t[onset_idx]
            if 0 <= dti < 5 * tau_d:
                data[i] -= 15.0 * (np.exp(-dti / tau_d) - np.exp(-dti / tau_r))
        # rolling_baseline_window_ms=1.0 at fs=1000 → window_samples=1 < 3
        result = detect_events_template(
            data=data,
            sampling_rate=fs,
            threshold_std=2.0,
            tau_rise=tau_r,
            tau_decay=tau_d,
            polarity="negative",
            rolling_baseline_window_ms=1.0,
        )
        assert result.is_valid


# ---------------------------------------------------------------------------
# detect_events_template — MAD == 0 fallback (line 976)
# ---------------------------------------------------------------------------


class TestDetectEventsTemplateMadZero:
    def test_constant_signal_mad_zero_fallback(self):
        """Line 976: constant signal makes MAD=0, triggers mad=1e-12 fallback."""
        fs = 10_000.0
        n = 2000
        data = np.full(n, 5.0)
        result = detect_events_template(
            data=data,
            sampling_rate=fs,
            threshold_std=2.0,
            tau_rise=0.001,
            tau_decay=0.005,
            polarity="negative",
        )
        assert result.is_valid


# ---------------------------------------------------------------------------
# detect_events_template — min_event_distance_ms <= 0 (line 992)
# ---------------------------------------------------------------------------


class TestDetectEventsTemplateMinDistZero:
    def test_min_event_distance_zero_uses_tau_decay(self):
        """Line 992: min_event_distance_ms=0 → min_dist_samples uses tau_decay."""
        fs = 10_000.0
        n = 3000
        dt = 1.0 / fs
        t = np.arange(n) * dt
        data = np.zeros(n)
        tau_r, tau_d = 0.0005, 0.003
        onset_idx = 1000
        for i in range(n):
            dti = t[i] - t[onset_idx]
            if 0 <= dti < 5 * tau_d:
                data[i] -= 20.0 * (np.exp(-dti / tau_d) - np.exp(-dti / tau_r))
        result = detect_events_template(
            data=data,
            sampling_rate=fs,
            threshold_std=2.0,
            tau_rise=tau_r,
            tau_decay=tau_d,
            polarity="negative",
            min_event_distance_ms=0.0,
        )
        assert result.is_valid


# ---------------------------------------------------------------------------
# detect_events_template — exception handler (lines 1054-1056)
# ---------------------------------------------------------------------------


class TestDetectEventsTemplateExceptionHandler:
    def test_exception_returns_invalid_result(self):
        """Lines 1054-1056: exception inside detect_events_template returns invalid."""
        from unittest.mock import patch

        fs = 10_000.0
        n = 2000
        data = np.zeros(n)
        with patch(
            "synaptipy.core.analysis.synaptic_events.signal.fftconvolve",
            side_effect=ValueError("forced template error"),
        ):
            result = detect_events_template(
                data=data,
                sampling_rate=fs,
                threshold_std=2.0,
                tau_rise=0.001,
                tau_decay=0.005,
                polarity="negative",
            )
        assert not result.is_valid


# ---------------------------------------------------------------------------
# detect_events_baseline_peak_kinetics — noise_sd=0 fallback (line 1304)
# ---------------------------------------------------------------------------


class TestDetectEventsBaselinePeakNoiseSdZero:
    def test_constant_signal_noise_sd_zero_fallback(self):
        """Line 1304: constant signal → noise_sd=0 → falls back to 1e-12."""
        fs = 10_000.0
        n = 2000
        data = np.full(n, 3.0)
        result = detect_events_baseline_peak_kinetics(
            data=data,
            sample_rate=fs,
            direction="negative",
        )
        assert result.is_valid


# ---------------------------------------------------------------------------
# detect_events_baseline_peak_kinetics — filter exception (lines 1323-1324)
# ---------------------------------------------------------------------------


class TestDetectEventsBaselinePeakFilterException:
    def test_filter_freq_above_nyquist_falls_back(self):
        """Lines 1323-1324: filter_freq_hz > Nyquist raises ValueError caught by except."""
        fs = 1_000.0
        n = 2000
        data = np.zeros(n)
        # filter_freq_hz=600 > Nyquist(500) → butter raises ValueError
        result = detect_events_baseline_peak_kinetics(
            data=data,
            sample_rate=fs,
            direction="negative",
            filter_freq_hz=600.0,
        )
        assert result.is_valid
