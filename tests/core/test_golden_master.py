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


# ---------------------------------------------------------------------------
# Expanded Golden-Master Lie Detector: passive-properties VC/CC paths and
# spike-feature kinetics — all SciPy-dependent and historically untested.
# ---------------------------------------------------------------------------

# ── Shared synthetic-data helpers ──────────────────────────────────────────


def _make_vc_transient(
    rs_mohm: float = 10.0,
    cm_pf: float = 100.0,
    v_step_mv: float = -10.0,
    onset_s: float = 0.010,
    i_hold_pa: float = -50.0,
    sampling_rate: float = 50_000.0,
    duration_s: float = 0.05,
) -> tuple:
    """Return (current_trace, time_vector) for a synthetic VC capacitive transient.

    Physics: I(t) = I_hold + I_peak * exp(-t / tau_c)
    where I_peak = V_step / Rs  and  tau_c = Rs * Cm.
    """
    t = np.arange(0.0, duration_s, 1.0 / sampling_rate)
    tau_c = rs_mohm * 1e6 * cm_pf * 1e-12  # seconds
    i_peak_pa = (v_step_mv * 1e-3) / (rs_mohm * 1e6) * 1e12  # pA
    i = np.full_like(t, i_hold_pa)
    oi = int(onset_s * sampling_rate)
    i[oi:] += i_peak_pa * np.exp(-(t[oi:] - onset_s) / tau_c)
    return i, t


def _make_cc_rs_trace(
    rs_mohm: float = 15.0,
    rin_mohm: float = 200.0,
    tau_ms: float = 20.0,
    i_step_pa: float = -20.0,
    onset_s: float = 0.1,
    v_rest_mv: float = -65.0,
    sampling_rate: float = 20_000.0,
    duration_s: float = 0.2,
) -> tuple:
    """Return (voltage_trace, time_vector) for a synthetic CC voltage response.

    The trace contains a fast Rs artifact (tau_fast = Rs*Cm) followed by a
    slow membrane response (tau_mem).  Cm is fixed at 100 pF internally.
    """
    t = np.arange(0.0, duration_s, 1.0 / sampling_rate)
    tau_fast_s = rs_mohm * 1e6 * 100e-12  # 100 pF assumed
    dv_fast = (rs_mohm * 1e6 * i_step_pa * 1e-12) * 1e3  # mV
    dv_ss = (rin_mohm * 1e6 * i_step_pa * 1e-12) * 1e3  # mV
    v = np.full_like(t, v_rest_mv)
    oi = int(onset_s * sampling_rate)
    tp = t[oi:] - onset_s
    v[oi:] = v_rest_mv + dv_fast * np.exp(-tp / tau_fast_s) + dv_ss * (1.0 - np.exp(-tp / (tau_ms / 1000.0)))
    return v, t


def _make_iv_sweeps(
    rin_mohm: float = 200.0,
    v_rest_mv: float = -65.0,
    current_steps_pa: tuple = (-60.0, -40.0, -20.0, 0.0, 20.0),
    sampling_rate: float = 10_000.0,
    duration_s: float = 0.5,
    step_start_s: float = 0.1,
    step_end_s: float = 0.4,
) -> tuple:
    """Return (sweeps, time_vectors, current_steps) for a linear Ohmic I-V protocol."""
    t = np.arange(0.0, duration_s, 1.0 / sampling_rate)
    sweeps, tvecs = [], []
    for i_pa in current_steps_pa:
        dv = (rin_mohm * 1e6 * i_pa * 1e-12) * 1e3  # mV
        v = np.full_like(t, v_rest_mv)
        v[int(step_start_s * sampling_rate) : int(step_end_s * sampling_rate)] += dv
        sweeps.append(v)
        tvecs.append(t.copy())
    return sweeps, tvecs, list(current_steps_pa)


def _make_spike_trace(
    spike_times_s: tuple = (0.1, 0.3),
    sampling_rate: float = 40_000.0,
    duration_s: float = 0.5,
    v_rest: float = -70.0,
    v_peak: float = 40.0,
    v_ahp: float = -80.0,
    rise_ms: float = 0.3,
    fall_ms: float = 0.8,
    ahp_ms: float = 15.0,
) -> tuple:
    """Return (voltage_trace, time_vector) with deterministic triangular AP waveforms."""
    t = np.arange(0.0, duration_s, 1.0 / sampling_rate)
    v = np.full(len(t), v_rest)
    for st in spike_times_s:
        for i, tt in enumerate(t):
            dt = (tt - st) * 1000.0  # ms
            if dt < 0.0:
                continue
            elif dt < rise_ms:
                v[i] += (v_peak - v_rest) * (dt / rise_ms)
            elif dt < rise_ms + fall_ms:
                v[i] += (v_peak - v_rest) * (1.0 - (dt - rise_ms) / fall_ms)
            elif dt < rise_ms + fall_ms + ahp_ms:
                v[i] += (v_ahp - v_rest) * np.exp(-(dt - rise_ms - fall_ms) / (ahp_ms * 0.3))
    return v, t


# ── Test class ─────────────────────────────────────────────────────────────


class TestGoldenMasterExtendedSynthetic:
    """Golden master assertions for SciPy-dependent passive-properties and
    spike-kinetics functions that previously lacked numerical snapshots.

    All data is deterministic (no random seeds needed) and all reference
    values were computed on the reference implementation; update them only
    after verifying the new outputs are scientifically correct.
    """

    # ── calculate_vc_transient_parameters ────────────────────────────────

    def test_vc_transient_rs_cm_tau_charge(self):
        """VC transient: Rs, Cm (charge method), tau_c, and peak current must be stable.

        Synthetic ground truth: Rs=10 MΩ, Cm=100 pF, V_step=-10 mV.
          I_peak = V_step / Rs = -1000 pA
          tau_c  = Rs * Cm = 1.0 ms
        """
        from Synaptipy.core.analysis.passive_properties import calculate_vc_transient_parameters

        i_trace, t = _make_vc_transient(rs_mohm=10.0, cm_pf=100.0, v_step_mv=-10.0)
        result = calculate_vc_transient_parameters(
            current_trace=i_trace,
            time_vector=t,
            step_onset_time=0.010,
            voltage_step_mv=-10.0,
            baseline_window_s=0.005,
            transient_window_ms=5.0,
        )

        # Series resistance: exact by construction (no fitting involved)
        assert not np.isnan(result["rs_mohm"]), "rs_mohm should not be NaN"
        assert pytest.approx(result["rs_mohm"], rel=1e-6) == 10.0

        # Transient peak current
        assert pytest.approx(result["transient_peak_pa"], rel=1e-6) == -1000.0

        # Capacitive time constant (mono-exp fit — allow 1 % relative tolerance)
        assert not np.isnan(result["tau_c_ms"]), "tau_c_ms should not be NaN"
        assert pytest.approx(result["tau_c_ms"], rel=1e-2) == 1.0

        # Cm from charge integral — reference value from calibration run
        # Reference: 99.31590414197261 pF  (slight underestimate due to finite
        # transient window capturing only ~98% of the exponential tail)
        assert not np.isnan(result["cm_pf"]), "cm_pf should not be NaN"
        assert pytest.approx(result["cm_pf"], rel=1e-3) == 99.31590414197261

        # Cm from exponential fit — should be much closer to the exact 100 pF
        assert not np.isnan(result["cm_fit_pf"]), "cm_fit_pf should not be NaN"
        assert pytest.approx(result["cm_fit_pf"], rel=1e-2) == 100.0

    # ── calculate_cc_series_resistance_fast ──────────────────────────────

    def test_cc_series_resistance_and_derived_cm(self):
        """CC Rs fast-artifact: Rs and Cm-derived must be numerically stable.

        Synthetic ground truth: Rs=15 MΩ, Rin=200 MΩ, tau=20 ms, I=-20 pA.
          delta_V_fast = Rs * I = -0.3 mV
          Rs (MΩ)      = 0.3 mV / 20 pA * 1e3 = 15 MΩ
          Cm_derived   = tau / Rin = 20 ms / 200 MΩ = 100 pF
        """
        from Synaptipy.core.analysis.passive_properties import calculate_cc_series_resistance_fast

        v_trace, t = _make_cc_rs_trace(rs_mohm=15.0, rin_mohm=200.0, tau_ms=20.0, i_step_pa=-20.0)
        result = calculate_cc_series_resistance_fast(
            voltage_trace=v_trace,
            time_vector=t,
            step_onset_time=0.1,
            current_step_pa=-20.0,
            artifact_window_ms=0.1,
            tau_ms=20.0,
            rin_mohm=200.0,
        )

        # Rs — extrapolation introduces small deviation; allow 0.1 % tolerance
        assert not np.isnan(result["rs_cc_mohm"]), "rs_cc_mohm should not be NaN"
        # Reference: 15.003808513868933 MΩ
        assert pytest.approx(result["rs_cc_mohm"], rel=1e-3) == 15.003808513868933

        # Cm derived analytically — exact by construction
        assert not np.isnan(result["cm_derived_pf"]), "cm_derived_pf should not be NaN"
        assert pytest.approx(result["cm_derived_pf"], rel=1e-6) == 100.0

    # ── calculate_iv_curve ───────────────────────────────────────────────

    def test_iv_curve_linear_membrane_rin_r2_intercept(self):
        """I-V curve linear regression must recover exact Rin for a perfect Ohmic membrane.

        Synthetic ground truth: Rin=200 MΩ, 5 symmetric current steps.
          Slope of delta_V vs I (nA) = Rin (MΩ) = 200 MΩ exactly.
          R² = 1.0 for a perfect linear I-V.
          Intercept ≈ 0 V (floating-point machine epsilon).
        """
        from Synaptipy.core.analysis.passive_properties import calculate_iv_curve

        sweeps, tvecs, isteps = _make_iv_sweeps(
            rin_mohm=200.0,
            current_steps_pa=(-60.0, -40.0, -20.0, 0.0, 20.0),
        )
        result = calculate_iv_curve(
            sweeps=sweeps,
            time_vectors=tvecs,
            current_steps=isteps,
            baseline_window=(0.0, 0.09),
            response_window=(0.15, 0.39),
        )

        # Slope = Rin (MΩ) from linregress on (I_nA, delta_V_mV)
        assert result["rin_aggregate_mohm"] is not None
        assert pytest.approx(result["rin_aggregate_mohm"], rel=1e-6) == 200.0

        # Perfect linear fit → R² = 1.0 exactly
        assert pytest.approx(result["iv_r_squared"], rel=1e-9) == 1.0

        # Intercept ≈ 0 (allow 1 μV absolute tolerance — floating-point residual)
        assert pytest.approx(result["iv_intercept"], abs=1e-6) == 0.0

        # Linear Ohmic membrane → no rectification (RI = 1.0)
        assert result["rectification_index"] is not None
        assert pytest.approx(result["rectification_index"], rel=1e-6) == 1.0

        # Verify the five delta_V values match Rin * I_nA exactly
        expected_dvs = [-12.0, -8.0, -4.0, 0.0, 4.0]  # mV
        for measured, expected in zip(result["delta_vs"], expected_dvs):
            assert pytest.approx(float(measured), rel=1e-6) == expected

    # ── calculate_spike_features ─────────────────────────────────────────

    def test_spike_features_half_width_fahp_mahp_stable(self):
        """AP waveform kinetics (half-width, fAHP, mAHP) must be numerically stable.

        Synthetic ground truth: triangular AP with known geometry.
          rise_ms=0.3, fall_ms=0.8 → half-width at 50% amplitude level.
          At 40 kHz, expected half-width ≈ 0.55 ms (verified on reference run).
          fAHP window (1-5 ms post-peak): AHP depth ≈ 9.565 mV.
          mAHP window (10-50 ms post-peak): AHP depth ≈ 1.295 mV.
        """
        from Synaptipy.core.analysis.single_spike import calculate_spike_features, detect_spikes_threshold

        v_trace, t = _make_spike_trace(spike_times_s=(0.1, 0.3))
        spike_result = detect_spikes_threshold(
            data=v_trace,
            time=t,
            threshold=-20.0,
            refractory_samples=int(0.002 * 40_000.0),
            dvdt_threshold=5.0,
        )
        assert spike_result.value == 2, "Should detect exactly 2 synthetic spikes"

        features = calculate_spike_features(
            data=v_trace,
            time=t,
            spike_indices=spike_result.spike_indices,
            dvdt_threshold=5.0,
            ahp_window_sec=0.05,
        )
        assert len(features) == 2

        for feat in features:
            # Half-width at 50 % amplitude level (ms) — Reference: 0.55 ms
            assert not np.isnan(feat["half_width"]), "half_width should not be NaN"
            assert pytest.approx(feat["half_width"], rel=1e-3) == 0.55

            # Peak amplitude: v_peak - v_threshold = 40 - (-70) = 110 mV
            assert pytest.approx(feat["amplitude"], rel=1e-6) == 110.0

            # fast-AHP depth (1-5 ms post-peak) — Reference: 9.56528739 mV
            assert not np.isnan(feat["fahp_depth"]), "fahp_depth should not be NaN"
            assert pytest.approx(feat["fahp_depth"], rel=1e-4) == 9.565287387880084

            # medium-AHP depth (10-50 ms post-peak) — Reference: 1.29452088 mV
            assert not np.isnan(feat["mahp_depth"]), "mahp_depth should not be NaN"
            assert pytest.approx(feat["mahp_depth"], rel=1e-4) == 1.2945208811655853

            # max dV/dt (upstroke rate) — Reference: 366.667 V/s
            assert pytest.approx(feat["max_dvdt"], rel=1e-3) == 366.6666666666667
