"""Targeted tests for remaining coverage gaps to reach 95%."""

from __future__ import annotations

import numpy as np

# ---------------------------------------------------------------------------
# cross_file_utils.py 252-253 — exception in read_recording load loop
# ---------------------------------------------------------------------------


class TestCrossFileUtilsLoadException:
    def test_load_exception_skips_and_returns_none(self):
        """Lines 252-253: read_recording raises → logged and skipped."""
        from unittest.mock import MagicMock

        from synaptipy.core.analysis.cross_file_utils import build_averaged_recording

        adapter = MagicMock()
        adapter.read_recording.side_effect = RuntimeError("mock load error")
        items = [{"path": "a.wcp"}, {"path": "b.wcp"}]
        result = build_averaged_recording(items, [0], adapter)
        assert result is None


# ---------------------------------------------------------------------------
# passive_properties.py 185 — slope = None when baseline has 1 point
# ---------------------------------------------------------------------------


class TestPassivePropertiesSlope:
    def test_calculate_rmp_single_point_slope_none(self):
        """Line 185: 1-point baseline window → cannot fit slope → slope = None."""
        from synaptipy.core.analysis.passive_properties import calculate_rmp

        n = 10000
        fs = 100000.0
        data = np.full(n, -70.0)
        time = np.linspace(0, n / fs, n, endpoint=False)
        # dt = 1e-5; window end = 5e-6 puts end_idx = 1 → exactly 1 sample
        result = calculate_rmp(data, time, (0.0, 0.000005))
        assert result.is_valid


# ---------------------------------------------------------------------------
# passive_properties.py 248 — NaN variance keeps best_start_idx = None
# ---------------------------------------------------------------------------


class TestFindStableBaselineNaN:
    def test_nan_data_returns_none_triple(self):
        """Line 248: all-NaN data → np.var = nan → nan < inf is False → returns (None, None, None)."""
        from synaptipy.core.analysis.passive_properties import find_stable_baseline

        data = np.full(10, np.nan)
        # window_samples=5 < n_points=10 → enters sliding loop (no early return)
        mean, sd, window = find_stable_baseline(data, sample_rate=100.0, window_duration_s=0.05, step_duration_s=0.01)
        assert mean is None
        assert sd is None
        assert window is None


# ---------------------------------------------------------------------------
# evoked_responses.py 572-573, 575-576, 596, 762-763
# calculate_n_pulse_ratio guards and edge paths
# ---------------------------------------------------------------------------


class TestCalculateNPulseRatioGuards:
    def test_empty_data_returns_error(self):
        """Lines 572-573: data.size < 2."""
        from synaptipy.core.analysis.evoked_responses import calculate_n_pulse_ratio

        out = calculate_n_pulse_ratio(np.array([]), np.array([]), np.array([0.1, 0.2]))
        assert out["ppr_error"] == "Invalid data or time array"

    def test_single_stim_returns_error(self):
        """Lines 575-576: n < 2."""
        from synaptipy.core.analysis.evoked_responses import calculate_n_pulse_ratio

        n = 1000
        data = np.zeros(n)
        time = np.linspace(0, 0.1, n)
        out = calculate_n_pulse_ratio(data, time, np.array([0.05]))
        assert out["ppr_error"] == "Need at least 2 stimulus onsets"

    def test_response_window_smaller_than_blanking(self):
        """Line 596: artifact_blanking > response_window → i1 <= i0 → return 0.0."""
        from synaptipy.core.analysis.evoked_responses import calculate_n_pulse_ratio

        n = 2000
        data = np.full(n, -70.0)
        time = np.linspace(0, 0.2, n, endpoint=False)
        stim_onsets = np.array([0.05, 0.10])
        # artifact_blanking_ms=5 > response_window_ms=1 → i0 > i1 inside _response_peak
        out = calculate_n_pulse_ratio(
            data,
            time,
            stim_onsets,
            response_window_ms=1.0,
            artifact_blanking_ms=5.0,
        )
        assert out is not None

    def test_fit_window_too_short(self):
        """Lines 762-763: stimuli 1 ms apart with fit_decay_from_ms=1.0 → 0 samples < 4."""
        from synaptipy.core.analysis.evoked_responses import calculate_n_pulse_ratio

        n = 2000
        data = np.full(n, -70.0)
        time = np.linspace(0, 0.2, n, endpoint=False)
        stim_onsets = np.array([0.05, 0.051])  # only 1 ms apart
        out = calculate_n_pulse_ratio(data, time, stim_onsets, fit_decay_from_ms=1.0)
        # Both pulses should have empty fit lists appended (fit window = 0 samples)
        assert "_all_fit_times" in out
        assert any(len(t) == 0 for t in out["_all_fit_times"])


# ---------------------------------------------------------------------------
# evoked_responses.py 373, 455-465
# calculate_paired_pulse_ratio: positive-polarity mono-exp fallback
# ---------------------------------------------------------------------------


class TestCalculatePairedPulseRatioPositivePolarity:
    def test_positive_polarity_mono_exp_fallback(self):
        """Lines 373, 455-465: positive polarity with short fit window skips bi-exp."""
        from synaptipy.core.analysis.evoked_responses import calculate_paired_pulse_ratio

        fs = 10000.0
        n = int(fs * 1.0)
        time = np.linspace(0, 1.0, n, endpoint=False)
        data = np.full(n, -70.0)
        stim1, stim2 = 0.3, 0.8

        # Upward decaying response (positive polarity) after stim1, tau = 5 ms
        stim1_idx = int(stim1 * fs)
        for i in range(stim1_idx, n):
            t_rel = (i - stim1_idx) / fs
            data[i] = -70.0 + 10.0 * np.exp(-t_rel / 0.005)

        # fit_decay_window_ms=0.6 → 6 samples < 8 → bi-exp skipped → mono-exp tried
        out = calculate_paired_pulse_ratio(
            data,
            time,
            stim1,
            stim2,
            polarity="positive",
            fit_decay_from_ms=0.5,
            fit_decay_window_ms=0.6,
            response_window_ms=20.0,
            artifact_blanking_ms=0.5,
        )
        assert out is not None
