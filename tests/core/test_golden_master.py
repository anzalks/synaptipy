"""
Golden master integration tests for the core analysis pipeline.

These tests exist strictly to detect if a future scipy, numpy, or neo update
silently alters mathematical behaviours.  They load real ABF files from the
examples/data/ directory, run the core passive-properties pipeline, and assert
that computed values match those produced by the reference implementation.

If a *deliberate* algorithm change is made, update the hardcoded constants here
after verifying the new outputs are scientifically correct.

Run only these tests:
    pytest tests/core/test_golden_master.py -v

ABF-dependent tests skip automatically when example data files are absent.
Deterministic synthetic tests still run to guard core math paths in CI.
"""

import pathlib

import numpy as np
import pytest

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_REPO_ROOT = pathlib.Path(__file__).parent.parent.parent
_DATA_DIR = _REPO_ROOT / "examples" / "data"

_ABF_0019 = _DATA_DIR / "2023_04_11_0019.abf"  # passive properties, -20 pA at 200-300 ms
_ABF_0021 = _DATA_DIR / "2023_04_11_0021.abf"  # firing / I-V curve
_ABF_0022 = _DATA_DIR / "2023_04_11_0022.abf"  # RMP + Rin, -20 pA at 15.95-16.35 s

_MISSING_DATA = not (_ABF_0019.exists() and _ABF_0021.exists() and _ABF_0022.exists())
_SKIP_REASON = "Example ABF data files not found - skipping golden master tests"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def neo_adapter():
    """Return a NeoAdapter instance (module-scoped to avoid repeated init)."""
    from Synaptipy.infrastructure.file_readers import NeoAdapter

    return NeoAdapter()


@pytest.fixture(scope="module")
def rec_0019(neo_adapter):
    """Recording from 0019.abf - passive properties file."""
    return neo_adapter.read_recording(str(_ABF_0019))


@pytest.fixture(scope="module")
def rec_0021(neo_adapter):
    """Recording from 0021.abf - firing / I-V curve file."""
    return neo_adapter.read_recording(str(_ABF_0021))


@pytest.fixture(scope="module")
def rec_0022(neo_adapter):
    """Recording from 0022.abf - synaptic / long-protocol file."""
    return neo_adapter.read_recording(str(_ABF_0022))


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _ch0(rec):
    """Return the first channel of a Recording."""
    return list(rec.channels.values())[0]


def _make_synaptic_trace(sampling_rate: float = 10_000.0, duration_s: float = 2.0):
    """Deterministic synthetic trace with 10 negative biexponential events."""
    t = np.arange(0.0, duration_s, 1.0 / sampling_rate)
    rng = np.random.default_rng(12345)
    data = rng.normal(0.0, 0.12, t.size)

    kt = np.arange(0.0, 0.05, 1.0 / sampling_rate)
    kernel = -(np.exp(-kt / 0.008) - np.exp(-kt / 0.001))
    kernel /= np.max(np.abs(kernel))
    kernel *= 8.0

    for onset in [0.2, 0.38, 0.56, 0.74, 0.92, 1.10, 1.28, 1.46, 1.64, 1.82]:
        idx = int(onset * sampling_rate)
        end = min(data.size, idx + kernel.size)
        data[idx:end] += kernel[: end - idx]

    return data, t, sampling_rate


def _make_opto_trace(sampling_rate: float = 10_000.0, duration_s: float = 1.0):
    """Deterministic synthetic trace for opto latency/jitter golden values."""
    t = np.arange(0.0, duration_s, 1.0 / sampling_rate)
    ttl = np.zeros_like(t)
    stimulus_onsets = [0.15, 0.35, 0.55, 0.75]
    for onset in stimulus_onsets:
        s = int(onset * sampling_rate)
        e = int((onset + 0.01) * sampling_rate)
        ttl[s:e] = 5.0

    data = np.full_like(t, -65.0)
    # Fixed post-stimulus event times -> fixed latency/jitter golden values.
    for spike_time in [0.154, 0.356, 0.555, 0.757]:
        idx = int(spike_time * sampling_rate)
        data[idx] = -5.0

    return data, t, ttl, stimulus_onsets, sampling_rate


# ---------------------------------------------------------------------------
# File 0019 - passive properties (-20 pA step at 200-300 ms)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(_MISSING_DATA, reason=_SKIP_REASON)
class TestGoldenMaster0019:
    """Golden master values for 2023_04_11_0019.abf (passive properties)."""

    def test_recording_structure(self, rec_0019):
        """File should have 1 channel and 5 trials, 1 s each."""
        assert rec_0019.num_channels == 1
        ch = _ch0(rec_0019)
        assert ch.num_trials == 5
        t = ch.get_relative_time_vector(0)
        assert pytest.approx(t[-1], abs=1e-4) == 1.0

    def test_rmp_trial0(self, rec_0019):
        """RMP from trial 0 baseline (0-0.15 s) should match reference."""
        from Synaptipy.core.analysis.passive_properties import calculate_rmp

        ch = _ch0(rec_0019)
        d = ch.get_data(0)
        t = ch.get_relative_time_vector(0)
        result = calculate_rmp(d, t, baseline_window=(0.0, 0.15))
        assert result.is_valid
        assert result.unit == "mV"
        # Reference: -65.21112060546875
        assert pytest.approx(result.value, rel=1e-5) == -65.21112060546875

    def test_rin_trial0(self, rec_0019):
        """Rin (steady-state) from trial 0 (-20 pA step) should match reference."""
        from Synaptipy.core.analysis.passive_properties import calculate_rin

        ch = _ch0(rec_0019)
        d = ch.get_data(0)
        t = ch.get_relative_time_vector(0)
        result = calculate_rin(
            d,
            t,
            current_amplitude=-20.0,
            baseline_window=(0.0, 0.19),
            response_window=(0.2, 0.3),
        )
        assert result.is_valid
        # Reference steady-state Rin: 118.26362609863281 MOhm
        assert pytest.approx(result.rin_steady_state_mohm, rel=1e-5) == 118.26362609863281
        # Reference peak Rin: 122.87483215332031 MOhm
        assert pytest.approx(result.rin_peak_mohm, rel=1e-5) == 122.87483215332031

    def test_tau_trial0(self, rec_0019):
        """Membrane time constant from trial 0 should match reference."""
        from Synaptipy.core.analysis.passive_properties import calculate_tau

        ch = _ch0(rec_0019)
        d = ch.get_data(0)
        t = ch.get_relative_time_vector(0)
        result = calculate_tau(d, t, stim_start_time=0.2, fit_duration=0.08)
        assert result is not None
        tau_ms = float(result["tau_ms"])
        assert not np.isnan(tau_ms), "Tau fit returned NaN"
        # Reference tau: 84.29428907793942 ms - allow 1% relative tolerance
        # because curve_fit is iterative and small FP differences across platforms
        # may push the result slightly outside a tighter bound.
        assert pytest.approx(tau_ms, rel=1e-2) == 84.29428907793942


# ---------------------------------------------------------------------------
# File 0022 - long protocol (RMP + Rin at 15.95-16.35 s, -20 pA)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(_MISSING_DATA, reason=_SKIP_REASON)
class TestGoldenMaster0022:
    """Golden master values for 2023_04_11_0022.abf (long synaptic protocol)."""

    def test_recording_structure(self, rec_0022):
        """File should have 4 channels and 3 trials."""
        assert rec_0022.num_channels == 4
        ch = _ch0(rec_0022)
        assert ch.num_trials == 3

    def test_rmp_trial0(self, rec_0022):
        """RMP from trial 0, baseline window 0-15.9 s, should match reference."""
        from Synaptipy.core.analysis.passive_properties import calculate_rmp

        ch = _ch0(rec_0022)
        d = ch.get_data(0)
        t = ch.get_relative_time_vector(0)
        result = calculate_rmp(d, t, baseline_window=(0.0, 15.9))
        assert result.is_valid
        # Reference: -65.37178802490234
        assert pytest.approx(result.value, rel=1e-5) == -65.37178802490234

    def test_rin_trial0(self, rec_0022):
        """Rin from trial 0, step window 15.95-16.35 s, should match reference."""
        from Synaptipy.core.analysis.passive_properties import calculate_rin

        ch = _ch0(rec_0022)
        d = ch.get_data(0)
        t = ch.get_relative_time_vector(0)
        result = calculate_rin(
            d,
            t,
            current_amplitude=-20.0,
            baseline_window=(0.0, 15.9),
            response_window=(15.95, 16.35),
        )
        assert result.is_valid
        # Reference steady-state Rin: 75.36430358886719 MOhm
        assert pytest.approx(result.rin_steady_state_mohm, rel=1e-5) == 75.36430358886719
        # Reference peak Rin: 135.9516143798828 MOhm
        assert pytest.approx(result.rin_peak_mohm, rel=1e-5) == 135.9516143798828


# ---------------------------------------------------------------------------
# File 0021 - firing / I-V curve
# ---------------------------------------------------------------------------


@pytest.mark.skipif(_MISSING_DATA, reason=_SKIP_REASON)
class TestGoldenMaster0021:
    """Golden master values for 2023_04_11_0021.abf (firing properties)."""

    def test_recording_structure(self, rec_0021):
        """File should have 1 channel and 20 trials, 0.5 s each."""
        assert rec_0021.num_channels == 1
        ch = _ch0(rec_0021)
        assert ch.num_trials == 20
        t = ch.get_relative_time_vector(0)
        assert pytest.approx(t[-1], abs=1e-4) == 0.5

    def test_rmp_baseline_trial0(self, rec_0021):
        """RMP from trial 0 baseline (0-0.1 s) should match reference."""
        from Synaptipy.core.analysis.passive_properties import calculate_rmp

        ch = _ch0(rec_0021)
        d = ch.get_data(0)
        t = ch.get_relative_time_vector(0)
        result = calculate_rmp(d, t, baseline_window=(0.0, 0.1))
        assert result.is_valid
        # Reference: -65.36598205566406
        assert pytest.approx(result.value, rel=1e-5) == -65.36598205566406

    def test_action_potential_peak_last_trial(self, rec_0021):
        """Last trial (highest current injection) should contain action potentials."""
        ch = _ch0(rec_0021)
        last_idx = ch.num_trials - 1
        d = ch.get_data(last_idx)
        # Reference max voltage: 42.6971 mV (action potential peak)
        ap_peak = float(np.max(d))
        assert pytest.approx(ap_peak, rel=1e-4) == 42.6971435546875
        # Sanity: last trial mean is depolarised relative to rest
        assert float(np.mean(d)) > -65.0, "Last trial mean should be depolarised"


# ---------------------------------------------------------------------------
# Expanded Golden-Master Lie Detector: 5 primary analysis pipelines
# ---------------------------------------------------------------------------


@pytest.mark.skipif(_MISSING_DATA, reason=_SKIP_REASON)
class TestGoldenMasterPrimaryPipelinesABF:
    """ABF-backed golden values for passive, single-spike, and firing dynamics."""

    def test_passive_wrappers_rmp_rin_cm_sag(self, rec_0019):
        """Passive wrapper outputs should remain stable across dependency updates."""
        from Synaptipy.core.analysis.passive_properties import (
            run_capacitance_analysis_wrapper,
            run_rin_analysis_wrapper,
            run_rmp_analysis_wrapper,
            run_sag_ratio_wrapper,
        )

        ch = _ch0(rec_0019)
        data = ch.get_data(0)
        time = ch.get_relative_time_vector(0)
        sampling_rate = float(ch.sampling_rate)

        rmp = run_rmp_analysis_wrapper(data, time, sampling_rate, baseline_start=0.0, baseline_end=0.15)
        rin = run_rin_analysis_wrapper(
            data,
            time,
            sampling_rate,
            current_amplitude=-20.0,
            auto_detect_pulse=False,
            baseline_start=0.0,
            baseline_end=0.19,
            response_start=0.2,
            response_end=0.3,
        )
        cm = run_capacitance_analysis_wrapper(
            data,
            time,
            sampling_rate,
            mode="Current-Clamp",
            current_amplitude_pa=-20.0,
            baseline_start_s=0.0,
            baseline_end_s=0.19,
            response_start_s=0.2,
            response_end_s=0.3,
        )
        sag = run_sag_ratio_wrapper(
            data,
            time,
            sampling_rate,
            baseline_start=0.0,
            baseline_end=0.19,
            peak_window_start=0.2,
            peak_window_end=0.23,
            ss_window_start=0.27,
            ss_window_end=0.3,
        )

        assert pytest.approx(rmp["metrics"]["rmp_mv"], rel=1e-3) == -65.21163940429688
        assert pytest.approx(rin["metrics"]["rin_mohm"], rel=1e-3) == 73.80752563476562
        assert pytest.approx(cm["metrics"]["capacitance_pf"], rel=1e-3) == 795.8314483676529
        assert pytest.approx(sag["metrics"]["sag_ratio"], rel=1e-3) == 0.6329649948769828

    def test_single_spike_wrapper_threshold_max_dvdt_half_width(self, rec_0021):
        """Single-spike kinetic features should remain stable on the last sweep."""
        from Synaptipy.core.analysis.single_spike import run_spike_detection_wrapper

        ch = _ch0(rec_0021)
        last_idx = ch.num_trials - 1
        data = ch.get_data(last_idx)
        time = ch.get_relative_time_vector(last_idx)
        sampling_rate = float(ch.sampling_rate)

        result = run_spike_detection_wrapper(
            data,
            time,
            sampling_rate,
            threshold=-20.0,
            refractory_period=0.002,
            dvdt_threshold=20.0,
        )
        metrics = result["metrics"]

        assert metrics["spike_count"] == 12
        assert pytest.approx(float(metrics["spike_times"][0]), rel=1e-3) == 0.07475
        assert pytest.approx(metrics["ap_threshold_mean"], rel=1e-3) == -13.583119710286459
        assert pytest.approx(metrics["max_dvdt_mean"], rel=1e-3) == 256.05010986328125
        assert pytest.approx(metrics["half_width_mean"], rel=1e-3) == 0.7067198666588714

    def test_firing_dynamics_fi_curve_spike_count_and_adaptation(self, rec_0021):
        """F-I extractor should preserve spike counts and first finite adaptation ratio."""
        from Synaptipy.core.analysis.firing_dynamics import calculate_fi_curve

        ch = _ch0(rec_0021)
        sweeps = [ch.get_data(i) for i in range(ch.num_trials)]
        times = [ch.get_relative_time_vector(i) for i in range(ch.num_trials)]

        fi = calculate_fi_curve(
            sweeps=sweeps,
            time_vectors=times,
            current_steps=list(range(ch.num_trials)),
            threshold=-20.0,
            refractory_ms=2.0,
        )

        assert fi["spike_counts"][-1] == 12
        first_finite_adaptation = next(v for v in fi["adaptation_ratios"] if np.isfinite(v))
        assert pytest.approx(first_finite_adaptation, rel=1e-3) == 1.6642066420664208


class TestGoldenMasterPrimaryPipelinesSynthetic:
    """Deterministic synthetic golden values for synaptic and evoked pipelines."""

    def test_synaptic_threshold_event_detection_count_amplitude_tau(self):
        """Threshold event detector should preserve event count, amplitude, and kinetics."""
        from Synaptipy.core.analysis.synaptic_events import run_event_detection_threshold_wrapper

        data, time, sampling_rate = _make_synaptic_trace()
        result = run_event_detection_threshold_wrapper(
            data,
            time,
            sampling_rate,
            threshold=4.0,
            direction="negative",
            refractory_period=0.03,
            rolling_baseline_window_ms=50.0,
            use_quiescent_noise_floor=True,
            quiescent_window_ms=20.0,
        )
        metrics = result["metrics"]

        assert metrics["event_count"] == 10
        assert pytest.approx(metrics["mean_local_amplitude"], rel=1e-3) == 4.742394087490832
        assert pytest.approx(metrics["tau_mono_ms"], rel=1e-3) == 3.9788918575712935
        assert pytest.approx(metrics["mean_event_charge"], rel=1e-3) == -0.02025645611362655

    def test_evoked_opto_latency_jitter_and_integrated_charge(self):
        """Opto wrapper latency/jitter and AUC proxy should remain numerically stable."""
        from Synaptipy.core.analysis.evoked_responses import run_opto_sync_wrapper

        data, time, ttl, onsets, sampling_rate = _make_opto_trace()
        result = run_opto_sync_wrapper(
            data,
            time,
            sampling_rate,
            ttl_data=ttl,
            event_detection_type="Spikes",
            spike_threshold=-10.0,
            response_window_ms=20.0,
        )
        metrics = result["metrics"]

        assert pytest.approx(metrics["optical_latency_ms"], rel=1e-3) == 5.500000000000005
        assert pytest.approx(metrics["spike_jitter_ms"], rel=1e-3) == 1.1180339887498958
        assert pytest.approx(metrics["response_probability"], rel=1e-3) == 1.0

        # Integrated charge proxy: baseline-subtracted AUC in each 20 ms post-stimulus window.
        auc_values = []
        for onset in onsets:
            response_mask = (time >= onset) & (time < onset + 0.02)
            baseline_mask = (time >= onset - 0.01) & (time < onset)
            baseline = float(np.mean(data[baseline_mask]))
            auc_values.append(float(np.trapezoid(data[response_mask] - baseline, time[response_mask])))

        assert pytest.approx(float(np.mean(auc_values)), rel=1e-3) == 0.005999999999999964
