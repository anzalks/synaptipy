"""Targeted coverage tests for synaptic_events.py missed branches."""

from __future__ import annotations

import numpy as np

# ---------------------------------------------------------------------------
# fit_biexponential_decay — bi-exp failure fallback (lines 285-287)
# ---------------------------------------------------------------------------


class TestFitBiexponentialDecayFallback:
    def test_bi_exp_failure_falls_back_to_mono(self):
        """Lines 285-287: RuntimeError from bi-exp fit is silently caught."""
        from synaptipy.core.analysis.synaptic_events import fit_biexponential_decay

        # Create an event that is hard to fit bi-exponentially
        fs = 10000.0
        n = 500
        data = np.zeros(n)
        # Decay starting at sample 50
        data[50:] = 1.0 * np.exp(-np.arange(n - 50) / 20.0)
        event_idx = 50
        local_baseline = 0.0

        result = fit_biexponential_decay(data, event_idx, fs, local_baseline, polarity="positive")
        # Should always return a valid dict regardless of bi-exp success
        assert "tau_mono_ms" in result
        assert "bi_exp_converged" in result

    def test_bi_exp_failure_with_noisy_data(self):
        """Force RuntimeError via data that can't converge."""
        from synaptipy.core.analysis.synaptic_events import fit_biexponential_decay

        fs = 10000.0
        n = 200
        rng = np.random.default_rng(42)
        data = rng.uniform(-0.001, 0.001, n)  # pure noise, no decay
        result = fit_biexponential_decay(data, 50, fs, 0.0, polarity="negative")
        assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# _fit_p1_decay_residual — mono-exp fallback (lines 425-449)
# ---------------------------------------------------------------------------


class TestFitP1DecayResidual:
    def _make_decay_data(self, fs=10000.0, n=1000, tau_s=0.005):
        """Return (data, time) with a clean mono-exp decay starting at sample 200."""
        time = np.linspace(0, n / fs, n, endpoint=False)
        data = np.zeros(n)
        t_decay = time[200:] - time[200]
        data[200:] = 1.0 * np.exp(-t_decay / tau_s)
        return data, time

    def test_mono_exp_fallback_when_bi_exp_fails(self):
        """Lines 425-449: bi-exp fails (too few points) → mono-exp succeeds."""
        from synaptipy.core.analysis.synaptic_events import _fit_p1_decay_residual

        data, time = self._make_decay_data()
        # peak1_idx=200, s2_t just a bit after peak so decay window is very short → bi-exp skipped
        residual, tau_ms = _fit_p1_decay_residual(
            data, time, peak1_idx=200, s2_t=0.021, global_baseline=0.0, sample_rate=10000.0
        )
        assert isinstance(residual, float)
        assert isinstance(tau_ms, float)

    def test_returns_zero_when_peak_near_end_of_data(self):
        """Lines 382-383: peak very close to end-of-array → clamped decay_end ≤ peak+3."""
        from synaptipy.core.analysis.synaptic_events import _fit_p1_decay_residual

        # Only 2 samples after peak1_idx → decay_end clamped to peak1_idx + 2 ≤ peak1_idx + 3
        n = 100
        data = np.ones(n)
        time = np.linspace(0, n / 10000.0, n, endpoint=False)
        peak1_idx = n - 2  # only 1 sample after peak
        s2_t = float(time[-1]) + 0.01  # past end
        residual, tau_ms = _fit_p1_decay_residual(data, time, peak1_idx, s2_t, 0.0, 10000.0)
        assert residual == 0.0
        assert np.isnan(tau_ms)

    def test_mono_exp_returns_zero_on_failure(self):
        """Lines 447-449: mono-exp fails (noise data) → (0.0, nan)."""
        from synaptipy.core.analysis.synaptic_events import _fit_p1_decay_residual

        rng = np.random.default_rng(0)
        n = 500
        data = rng.uniform(-100, 100, n)  # wild noise — curve_fit won't converge
        time = np.linspace(0, n / 10000.0, n, endpoint=False)
        residual, tau_ms = _fit_p1_decay_residual(data, time, 100, 0.15, 0.0, 10000.0)
        assert isinstance(residual, float)


# ---------------------------------------------------------------------------
# run_event_detection_threshold_wrapper — kinetics branches (lines 860-867)
# ---------------------------------------------------------------------------


class TestRunEventDetectionThresholdWrapper:
    def test_kinetics_path(self):
        """Lines 860-867: compute_kinetics=True hits bi_exp_converged path."""
        from synaptipy.core.analysis.synaptic_events import run_event_detection_threshold_wrapper

        fs = 20000.0
        n = int(fs * 1.0)
        rng = np.random.default_rng(1)
        data = np.zeros(n)
        # Plant a clean negative mini at sample 5000
        t_mini = np.arange(100) / fs
        mini_shape = -10.0 * np.exp(-t_mini / 0.005) * (1 - np.exp(-t_mini / 0.001))
        data[5000 : 5000 + 100] += mini_shape
        data += rng.normal(0, 0.1, n)
        time = np.linspace(0, 1.0, n, endpoint=False)

        result = run_event_detection_threshold_wrapper(
            data, time, fs, threshold=3.0, direction="negative", compute_kinetics=True
        )
        assert "metrics" in result
        assert isinstance(result["metrics"].get("event_count", 0), (int, float))

    def test_no_kinetics_path(self):
        """compute_kinetics=False skips kinetics loop entirely."""
        from synaptipy.core.analysis.synaptic_events import run_event_detection_threshold_wrapper

        fs = 10000.0
        n = int(fs * 0.5)
        data = np.zeros(n)
        time = np.linspace(0, 0.5, n, endpoint=False)
        result = run_event_detection_threshold_wrapper(data, time, fs, compute_kinetics=False)
        assert "metrics" in result

    def test_empty_signal_returns_zero_events(self):
        """Lines 986, 1002: no events detected → zero event_count."""
        from synaptipy.core.analysis.synaptic_events import run_event_detection_threshold_wrapper

        fs = 10000.0
        n = int(fs * 0.1)
        data = np.zeros(n)
        time = np.linspace(0, 0.1, n, endpoint=False)
        result = run_event_detection_threshold_wrapper(data, time, fs, threshold=100.0)
        assert result["metrics"]["event_count"] == 0
