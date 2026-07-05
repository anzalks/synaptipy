"""Targeted tests for remaining coverage gaps across multiple modules."""

from __future__ import annotations

import numpy as np
from unittest.mock import MagicMock


# ---------------------------------------------------------------------------
# core/data_model.py — lines 213-215 (no valid trials), 276-278 (loader path)
# ---------------------------------------------------------------------------


class TestChannelNumSamples:
    def test_no_valid_trials_returns_zero(self):
        """Lines 213-215: channel with only None trials → num_samples = 0."""
        from synaptipy.core.data_model import Channel

        ch = Channel(id="x", name="x", units="mV", sampling_rate=10000.0, data_trials=[None])
        assert ch.num_samples == 0

    def test_non_array_trial_logs_warning(self):
        """Lines 210-211: non-ndarray trial type is skipped."""
        from synaptipy.core.data_model import Channel

        ch = Channel(id="x", name="x", units="mV", sampling_rate=10000.0, data_trials=["bad"])
        # Should not crash and returns 0 because no valid array was found
        assert ch.num_samples == 0

    def test_varying_length_trials_returns_first(self):
        """Lines 217-223: trials with different lengths → returns first trial length."""
        from synaptipy.core.data_model import Channel

        ch = Channel(
            id="x",
            name="x",
            units="mV",
            sampling_rate=10000.0,
            data_trials=[np.zeros(100), np.zeros(200)],
        )
        assert ch.num_samples == 100


class TestChannelGetDataWithLoader:
    def test_get_data_with_loader_calls_load_trial(self):
        """Lines 276-278: loader with load_trial method is called on cache miss."""
        from synaptipy.core.data_model import Channel

        arr = np.zeros(50)
        loader = MagicMock()
        loader.load_trial.return_value = arr

        ch = Channel(id="x", name="x", units="mV", sampling_rate=1000.0, data_trials=[])
        ch.loader = loader
        ch.get_data(0)
        loader.load_trial.assert_called_once_with(0)


# ---------------------------------------------------------------------------
# core/analysis/firing_dynamics.py — lines 412-420 (inter-burst voltage)
# ---------------------------------------------------------------------------


class TestBurstAnalysisInterBurstVoltage:
    def test_inter_burst_voltage_computed(self):
        """Lines 412-420: two bursts → inter-burst voltage is computed."""
        from synaptipy.core.analysis.firing_dynamics import calculate_bursts_logic

        fs = 10000.0
        n = int(fs * 1.0)
        data = np.full(n, -65.0)
        time = np.linspace(0, 1.0, n, endpoint=False)
        # Plant spikes in two tight clusters separated by a gap
        spike_times = np.array([0.10, 0.11, 0.12, 0.70, 0.71, 0.72])
        result = calculate_bursts_logic(
            spike_times,
            max_isi_start=0.05,
            max_isi_end=0.1,
            min_spikes=2,
            data=data,
            time=time,
        )
        assert result is not None
        # With two bursts, inter_burst_voltage_mv should be computed
        assert hasattr(result, "inter_burst_voltage_mv")


# ---------------------------------------------------------------------------
# core/analysis/firing_dynamics.py — lines 806-807 (exception in broadening)
# ---------------------------------------------------------------------------


class TestFiringDynamicsBroadening:
    def test_broadening_exception_caught(self):
        """Lines 806-807: exception during calculate_spike_features is caught.

        run_train_dynamics_wrapper sets spike_indices only via threshold detection
        (not when action_potential_times is passed directly).  We use fs=1000 so
        the 5 kHz low-pass is skipped, plant 3 single-sample spike peaks above
        threshold, then patch the LOCAL import inside the wrapper.
        """
        from synaptipy.core.analysis.firing_dynamics import run_train_dynamics_wrapper
        from unittest.mock import patch

        fs = 1000.0
        n = 500
        data = np.full(n, -65.0)
        time = np.linspace(0, 0.5, n, endpoint=False)

        # Plant 3 spikes well above the threshold so detection finds exactly 3
        for loc in [100, 200, 300]:
            data[loc] = 30.0

        # The wrapper does `from synaptipy.core.analysis.single_spike import
        # calculate_spike_features` at runtime, so patch the source module attribute
        with patch(
            "synaptipy.core.analysis.single_spike.calculate_spike_features",
            side_effect=RuntimeError("mock broadening error"),
        ):
            result = run_train_dynamics_wrapper(
                data, time, fs, spike_threshold=-50.0
            )
        assert result is not None


# ---------------------------------------------------------------------------
# core/analysis/passive_properties.py — lines 156 (empty data slice)
# ---------------------------------------------------------------------------


class TestCalculateRmpEdgeCases:
    def test_empty_baseline_window_returns_invalid(self):
        """Lines 150-156: baseline window outside data range → invalid result."""
        from synaptipy.core.analysis.passive_properties import calculate_rmp

        n = 10
        time = np.linspace(0, 0.1, n, endpoint=False)
        data = np.full(n, -65.0)
        # Baseline window after the data ends → no points found
        result = calculate_rmp(data, time, (99.0, 100.0))
        assert not result.is_valid

    def test_rmp_normal(self):
        """Normal path — flat data returns rmp = data value."""
        from synaptipy.core.analysis.passive_properties import calculate_rmp

        n = 1000
        data = np.full(n, -70.0)
        time = np.linspace(0, 0.1, n, endpoint=False)
        result = calculate_rmp(data, time, (0.0, 0.05))
        assert result.is_valid
        assert abs(result.value - (-70.0)) < 0.5


class TestFindStableBaseline:
    def test_single_sample_window_returns_global(self):
        """Lines 229-231: window >= n_points → returns global stats immediately."""
        from synaptipy.core.analysis.passive_properties import find_stable_baseline

        data = np.array([-65.0, -65.5, -64.8])
        mean, sd, window = find_stable_baseline(data, sample_rate=10000.0, window_duration_s=1.0)
        assert mean is not None
        assert sd is not None
        assert window is not None

    def test_empty_data_returns_none(self):
        """Line 219-220: empty data → (None, None, None)."""
        from synaptipy.core.analysis.passive_properties import find_stable_baseline

        result = find_stable_baseline(np.array([]), sample_rate=10000.0)
        assert result == (None, None, None)


# ---------------------------------------------------------------------------
# core/analysis/batch_engine — selected_trials scope (lines 1424-1449)
# ---------------------------------------------------------------------------


class TestBatchEngineSelectedTrials:
    def _make_channel(self, n_trials=5, fs=10000.0, duration=0.5):
        n = int(fs * duration)
        time = np.linspace(0, duration, n, endpoint=False)
        ch = MagicMock()
        ch.sampling_rate = fs
        ch.units = "mV"
        ch.name = "Vm"
        ch.num_trials = n_trials
        ch.get_data.return_value = np.full(n, -65.0)
        ch.get_relative_time_vector.return_value = time
        return ch

    def _make_rec(self, n_trials=5):
        from pathlib import Path
        from unittest.mock import MagicMock
        from synaptipy.core.data_model import Recording

        rec = MagicMock(spec=Recording)
        ch = self._make_channel(n_trials=n_trials)
        rec.channels = {"Vm": ch}
        rec.source_file = Path("sel.abf")
        rec.protocol_name = None
        rec.subject_id = None
        rec.cell_id = None
        rec.duration = 0.5
        return rec

    def test_selected_trials_scope(self):
        """Lines 1424-1449: scope='selected_trials' iterates specific trials."""
        from synaptipy.core.analysis.batch_engine import BatchAnalysisEngine

        rec = self._make_rec(n_trials=5)
        engine = BatchAnalysisEngine(max_workers=1)
        pipeline = [
            {
                "analysis": "rmp_analysis",
                "scope": "selected_trials",
                "params": {"trial_indices": "0, 2"},
            }
        ]
        df = engine.run_batch([rec], pipeline)
        assert df is not None

    def test_selected_trials_no_indices_string(self):
        """Lines 1446-1447: empty trial_indices string → all trials."""
        from synaptipy.core.analysis.batch_engine import BatchAnalysisEngine

        rec = self._make_rec(n_trials=3)
        engine = BatchAnalysisEngine(max_workers=1)
        pipeline = [
            {
                "analysis": "rmp_analysis",
                "scope": "selected_trials",
                "params": {"trial_indices": ""},
            }
        ]
        df = engine.run_batch([rec], pipeline)
        assert df is not None

    def test_all_trials_scope_iterates(self):
        """Lines 1448-1449: scope='all_trials' → all trials iterated."""
        from synaptipy.core.analysis.batch_engine import BatchAnalysisEngine

        rec = self._make_rec(n_trials=2)
        engine = BatchAnalysisEngine(max_workers=1)
        pipeline = [{"analysis": "rmp_analysis", "scope": "all_trials"}]
        df = engine.run_batch([rec], pipeline)
        assert df is not None
        assert len(df) >= 1


# ---------------------------------------------------------------------------
# batch_engine — cross-file average progress callback (lines 574-575, 584-585)
# ---------------------------------------------------------------------------


class TestCrossFileAverageProgressCallback:
    def test_progress_callback_called(self):
        """Lines 574-575, 584-585: progress_callback invoked during cross-file average."""
        from pathlib import Path
        from unittest.mock import MagicMock
        from synaptipy.core.analysis.batch_engine import BatchAnalysisEngine
        from synaptipy.core.data_model import Recording

        rec = MagicMock(spec=Recording)
        ch = MagicMock()
        ch.sampling_rate = 10000.0
        ch.units = "mV"
        ch.name = "Vm"
        ch.num_trials = 1
        ch.get_data.return_value = np.zeros(100)
        ch.get_relative_time_vector.return_value = np.linspace(0, 0.01, 100)
        rec.channels = {"Vm": ch}
        rec.source_file = Path("cb.abf")
        rec.protocol_name = None
        rec.subject_id = None
        rec.cell_id = None
        rec.duration = 0.01

        calls = []
        engine = BatchAnalysisEngine(max_workers=1)
        engine.run_batch(
            [rec],
            [{"analysis": "rmp_analysis"}],
            cross_file_average=True,
            progress_callback=lambda c, t, m: calls.append((c, t, m)),
        )
        assert len(calls) > 0
