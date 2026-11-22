"""Targeted regression tests for the Synaptipy scientific rigor audit fixes."""

import importlib.util
import math
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pytest

from synaptipy.core.analysis.batch_engine import BatchAnalysisEngine
from synaptipy.core.analysis.evoked_responses import calculate_paired_pulse_ratio
from synaptipy.core.analysis.passive_properties import (
    calculate_capacitance_vc,
    calculate_iv_curve,
    find_stable_baseline,
)
from synaptipy.core.analysis.single_spike import calculate_spike_features, detect_spikes_threshold
from synaptipy.core.analysis.synaptic_events import run_event_detection_threshold_wrapper
from synaptipy.core.data_model import Channel, Recording
from synaptipy.core.processing_pipeline import apply_trace_corrections
from synaptipy.core.signal_processor import bandpass_filter, highpass_filter, lowpass_filter
from synaptipy.infrastructure.exporters.csv_exporter import CSVExporter, _round_sig
from synaptipy.infrastructure.exporters.nwb_exporter import NWBExporter


def test_nwb_exporter_si_scaling_ramp_and_scalar_metrics(tmp_path: Path) -> None:
    """Verify NWB export scales mV/pA to SI once (conversion=1.0), synthesizes ramps, and saves scalar metrics."""
    pynwb = pytest.importorskip("pynwb")

    fs = 10000.0
    n_samples = 1000
    v_mv = np.full(n_samples, -70.0, dtype=float)
    i_pa = np.full(n_samples, -200.0, dtype=float)

    ch_v = Channel(id="0", name="Vm", units="mV", sampling_rate=fs, data_trials=[v_mv])
    ch_i = Channel(id="1", name="Im", units="pA", sampling_rate=fs, data_trials=[i_pa])

    rec = Recording(source_file=tmp_path / "test.abf")
    rec.channels = {"0": ch_v, "1": ch_i}
    rec.sampling_rate = fs
    rec.metadata = {
        "liquid_junction_potential_mv": 12.5,
        "abf_holding_level": -70.0,
        "abf_pre_epoch_samples": 100,
        "abf_epochs": [
            {
                "nEpochType": 2,
                "fEpochInitLevel": -50.0,
                "fEpochLevelInc": 0.0,
                "lEpochInitDuration": 400,
                "lEpochDurationInc": 0,
            },
        ],
    }

    analysis_results = [
        {"analysis": "rmp_analysis", "rmp_mv": -70.0, "baseline_sd": 0.05},
    ]

    out_nwb = tmp_path / "exported.nwb"
    exporter = NWBExporter()
    exporter.export(
        rec,
        out_nwb,
        session_metadata={
            "session_description": "Audit test",
            "identifier": "audit-001",
            "session_start_time": datetime.now(timezone.utc),
            "subject_id": "mouse-001",
            "species": "Mus musculus",
            "device_description": "MultiClamp 700B",
        },
        analysis_results=analysis_results,
    )

    with pynwb.NWBHDF5IO(str(out_nwb), "r") as io:
        nwbfile = io.read()
        acq_keys = list(nwbfile.acquisition.keys())
        assert len(acq_keys) == 2

        ts_v = [ts for ts in nwbfile.acquisition.values() if ts.unit == "volts"][0]
        ts_i = [ts for ts in nwbfile.acquisition.values() if ts.unit == "amperes"][0]

        assert math.isclose(float(ts_v.conversion), 1.0, rel_tol=1e-12)
        assert math.isclose(float(ts_i.conversion), 1.0, rel_tol=1e-12)
        assert np.allclose(ts_v.data[:] * ts_v.conversion, -0.070, atol=1e-9)
        assert np.allclose(ts_i.data[:] * ts_i.conversion, -200e-12, atol=1e-18)

        assert "Im_stim_trial_000_synth" in nwbfile.stimulus
        stim_vc = nwbfile.stimulus["Im_stim_trial_000_synth"]
        assert stim_vc.unit == "volts"
        stim_data = stim_vc.data[:]
        assert math.isclose(float(stim_data[50]), -0.070, abs_tol=1e-9)
        assert -0.070 < float(stim_data[300]) < -0.050

        stim_cc = nwbfile.stimulus["Vm_stim_trial_000_synth"]
        assert stim_cc.unit == "amperes"
        assert math.isclose(float(stim_cc.data[50]), -70e-12, abs_tol=1e-18)

        assert "analysis" in nwbfile.processing
        assert "scalar_metrics" in nwbfile.processing["analysis"].data_interfaces


def test_csv_rounding_timestamps_and_prism_anti_pseudoreplication(tmp_path: Path) -> None:
    """Verify _round_sig safety, 10-sig-fig timestamps, and file-level Prism aggregation."""
    assert math.isnan(_round_sig(float("nan"), 6))
    assert math.isinf(_round_sig(float("inf"), 6))
    assert math.isclose(_round_sig(1.23456e-310, 4), 1.235e-310, rel_tol=1e-3)

    exporter = CSVExporter()
    tidy_path = tmp_path / "tidy.csv"
    exporter.export_tidy(
        [{"file": "rec1.abf", "spike_time_s": 3600.0012, "amplitude": 45.12345678}],
        tidy_path,
    )
    tidy_text = tidy_path.read_text(encoding="utf-8")
    assert "3600.0012" in tidy_text

    # 2 files x 2 sweeps each -> aggregate_by_file=True yields 2 biological replicates
    sweep_rows = [
        {"file_name": "cellA.abf", "group": "WT", "rmp_mv": -70.0},
        {"file_name": "cellA.abf", "group": "WT", "rmp_mv": -72.0},
        {"file_name": "cellB.abf", "group": "WT", "rmp_mv": -65.0},
        {"file_name": "cellB.abf", "group": "WT", "rmp_mv": -67.0},
    ]
    prism_path = tmp_path / "prism_cell_means.csv"
    exporter.export_to_prism_format(
        sweep_rows,
        prism_path,
        metric="rmp_mv",
        group_by_key="group",
        aggregate_by_file=True,
    )
    actual_prism = prism_path.with_name(f"{prism_path.stem}_prism_rmp_mv.csv")
    lines = [ln for ln in actual_prism.read_text(encoding="utf-8").splitlines() if ln and not ln.startswith("#")]
    assert len(lines) == 3  # header + 2 cells (-71.0 and -66.0)


def test_lazy_channel_multi_trial_access() -> None:
    """Ensure lazy Channel.get_data(trial_index) loads sweeps >= 1 after sweep 0 is cached."""
    calls = []

    class DummyLoader:
        def load_trial(self, trial_idx: int) -> np.ndarray:
            calls.append(trial_idx)
            return np.full(10, float(trial_idx), dtype=float)

    ch = Channel(
        id="0",
        name="Vm",
        units="mV",
        sampling_rate=1000.0,
        data_trials=[],
        loader=DummyLoader(),
    )
    ch.metadata["num_trials"] = 3

    t0 = ch.get_data(0)
    t1 = ch.get_data(1)
    t2 = ch.get_data(2)
    t3 = ch.get_data(3)

    assert t0 is not None and np.all(t0 == 0.0)
    assert t1 is not None and np.all(t1 == 1.0)
    assert t2 is not None and np.all(t2 == 2.0)
    assert t3 is None
    assert calls == [0, 1, 2]


def test_sosfiltfilt_safe_zero_dc_edge_transient_and_filter_types() -> None:
    """Verify _sosfiltfilt_safe eliminates step edge ringing on -70 mV resting potential traces."""
    fs = 20000.0
    dc_trace = np.full(4000, -70.0, dtype=float)

    for ftype in ("butterworth", "bessel", "gaussian"):
        lp = lowpass_filter(dc_trace, cutoff=1000.0, fs=fs, order=4, filter_type=ftype)
        assert np.max(np.abs(lp - (-70.0))) < 1e-7

    hp = highpass_filter(dc_trace, cutoff=1.0, fs=fs, order=4, filter_type="butterworth")
    assert np.max(np.abs(hp)) < 1e-7

    bp = bandpass_filter(dc_trace, lowcut=1.0, highcut=1000.0, fs=fs, order=4, filter_type="bessel")
    assert np.max(np.abs(bp)) < 1e-7

    # LJP unit awareness: skip current channels, scale Volts properly
    t_small = np.arange(100) / fs
    i_pa = np.full(100, -100.0, dtype=float)
    assert np.allclose(apply_trace_corrections(i_pa, t_small, fs, ljp_mv=15.0, units="pA"), -100.0)
    v_volts = np.full(100, -0.055, dtype=float)
    assert np.allclose(apply_trace_corrections(v_volts, t_small, fs, ljp_mv=15.0, units="V"), -0.070)


def test_ppr_residual_tail_subtraction_recovers_unity_ratio() -> None:
    """Identical summating PSCs (R1=-50, R2=-50, ISI=50 ms, tau=20 ms) must yield PPR ~ 1.0."""
    fs = 20000.0
    t = np.arange(0, 0.25, 1.0 / fs)
    trace = np.zeros_like(t)

    t1, t2 = 0.02, 0.07
    tau_s = 0.020
    # Add realistic 2 ms post-stimulus onset delay so peak occurs after 1 ms artifact blanking
    p1_t, p2_t = t1 + 0.002, t2 + 0.002
    m1 = t >= p1_t
    trace[m1] += -50.0 * np.exp(-(t[m1] - p1_t) / tau_s)
    m2 = t >= p2_t
    trace[m2] += -50.0 * np.exp(-(t[m2] - p2_t) / tau_s)

    res = calculate_paired_pulse_ratio(
        trace,
        t,
        stim1_onset_s=t1,
        stim2_onset_s=t2,
        response_window_ms=20.0,
        polarity="negative",
    )
    assert math.isclose(res["paired_pulse_ratio"], 1.0, rel_tol=0.02)


def test_adp_noise_immunity_on_monotonic_repolarization() -> None:
    """Monotonic AP repolarization with white noise must return NaN for adp_amplitude (never negative/noise)."""
    rng = np.random.default_rng(42)
    fs = 20000.0
    t = np.arange(0.0, 0.1, 1.0 / fs)
    v = np.full_like(t, -70.0)

    idx_peak = int(0.020 * fs)
    v[idx_peak - 10 : idx_peak + 1] = np.linspace(-70.0, 40.0, 11)
    v[idx_peak : idx_peak + 30] = np.linspace(40.0, -78.0, 30)
    tail_t = np.arange(len(t) - (idx_peak + 29)) / fs
    v[idx_peak + 29 :] = -70.0 - 8.0 * np.exp(-tail_t / 0.015)
    v += rng.normal(0.0, 0.02, size=len(v))

    det = detect_spikes_threshold(v, t, threshold=-20.0, refractory_samples=int(0.002 * fs))
    feats = calculate_spike_features(v, t, det.spike_indices)
    assert len(feats) == 1
    assert feats[0].adp_amplitude is None or math.isnan(feats[0].adp_amplitude)


def test_passive_and_synaptic_edge_cases() -> None:
    """Check zero-event NaN amplitude, clipped-rail rejection, VC charge capacitance, and IV spiking filter."""
    fs = 10000.0
    t = np.arange(0.0, 0.5, 1.0 / fs)
    flat = np.zeros_like(t)
    ev = run_event_detection_threshold_wrapper(flat, t, fs, threshold=10.0, direction="negative")
    assert ev["metrics"]["event_count"] == 0
    assert math.isnan(ev["metrics"]["mean_amplitude"])

    # Clipped rail (0 variance) at start followed by physiological baseline with realistic noise
    rng = np.random.default_rng(7)
    clipped_then_normal = np.concatenate([np.full(2000, 100.0), -70.0 + rng.normal(0.0, 0.05, 3000)])
    mean_v, _, win = find_stable_baseline(
        clipped_then_normal, sample_rate=fs, window_duration_s=0.1, step_duration_s=0.05, t_start=5.0
    )
    assert mean_v is not None and math.isclose(mean_v, -70.0, abs_tol=0.1)
    assert win is not None and win[0] >= 5.19 and win[1] <= 5.51

    # VC charge integration capacitance: Cm = 100 pF, Rs = 10 MOhm -> tau = 1 ms, dV = -10 mV
    t_vc = np.arange(0.0, 0.05, 1.0 / 50000.0)
    i_vc = np.zeros_like(t_vc)
    step = t_vc >= 0.005
    i_vc[step] = -1000.0 * np.exp(-(t_vc[step] - 0.005) / 0.001)
    cap = calculate_capacitance_vc(
        i_vc,
        t_vc,
        baseline_window=(0.0, 0.004),
        transient_window=(0.005, 0.020),
        voltage_step_amplitude_mv=-10.0,
    )
    assert math.isclose(cap["capacitance_charge_pf"], 100.0, rel_tol=0.05)

    # IV curve excludes suprathreshold spiking sweeps from subthreshold Rin regression
    t_iv = np.arange(0.0, 0.2, 1.0 / 1000.0)
    sweeps = []
    currents = np.array([-100.0, -50.0, 0.0, 100.0])
    for curr in currents:
        tr = np.full_like(t_iv, -70.0)
        tr[50:150] = -70.0 + curr * 0.2
        if curr > 50.0:
            tr[80] = 35.0
        sweeps.append(tr)
    iv_res = calculate_iv_curve(
        sweeps=sweeps,
        time_vectors=[t_iv] * len(sweeps),
        current_steps=list(currents),
        baseline_window=(0.0, 0.04),
        response_window=(0.10, 0.14),
    )
    assert math.isclose(iv_res["rin_aggregate_mohm"], 200.0, rel_tol=0.02)


def test_batch_engine_preprocessing_to_analysis_parity(tmp_path: Path) -> None:
    """Ensure registered preprocessing steps execute in BatchAnalysisEngine and feed downstream analyses."""
    fs = 10000.0
    v = np.full(2000, -65.0, dtype=float)
    ch = Channel(id="0", name="Vm", units="mV", sampling_rate=fs, data_trials=[v, v.copy()])
    rec = Recording(source_file=tmp_path / "batch_pre.abf")
    rec.channels = {"0": ch}
    rec.sampling_rate = fs

    pipeline = [
        {
            "analysis": "lowpass_filter",
            "type": "preprocessing",
            "scope": "all_trials",
            "params": {"cutoff": 1000.0, "order": 4},
        },
        {
            "analysis": "baseline_subtraction",
            "type": "preprocessing",
            "scope": "all_trials",
            "params": {"method": "mean"},
        },
        {
            "analysis": "rmp_analysis",
            "scope": "first_trial",
            "params": {"baseline_start": 0.0, "baseline_end": 0.1},
        },
    ]

    engine = BatchAnalysisEngine(max_workers=1)
    df = engine.run_batch([rec], pipeline)
    assert not df.empty
    assert math.isclose(float(df["rmp_mv"].iloc[0]), 0.0, abs_tol=1e-5)


def test_paper_tables_sustained_step_ignores_pre_sweep_test_pulse() -> None:
    """Verify detect_sustained_step skips brief pre-sweep test pulses and finds the 1.0 s Long Square step."""
    script_path = Path(__file__).resolve().parents[2] / "paper" / "scripts" / "generate_paper_tables.py"
    spec = importlib.util.spec_from_file_location("generate_paper_tables", script_path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    fs = 10000.0
    t = np.arange(0.0, 3.0, 1.0 / fs)
    i = np.zeros_like(t)
    i[(t >= 0.02) & (t <= 0.07)] = -50.0
    i[(t >= 1.02) & (t <= 2.02)] = -110.0

    step = mod.detect_sustained_step(i, t, polarity="negative", min_duration_s=0.2, threshold_pa=10.0)
    assert step is not None
    _, _, s_t, e_t, amp = step
    assert math.isclose(s_t, 1.02, abs_tol=1e-3)
    assert math.isclose(e_t, 2.02, abs_tol=1e-3)
    assert math.isclose(amp, -110.0, abs_tol=0.5)


def test_tau_wrapper_exposes_95_ci_bounds() -> None:
    """Verify run_tau_analysis_wrapper populates finite tau_ci_95_low and tau_ci_95_high bounds."""
    from synaptipy.core.analysis.passive_properties import run_tau_analysis_wrapper

    fs = 20000.0
    t = np.arange(0.0, 0.25, 1.0 / fs)
    v = np.full_like(t, -70.0)
    step_mask = t >= 0.05
    v[step_mask] = -80.0 + 10.0 * np.exp(-(t[step_mask] - 0.05) / 0.020)
    rng = np.random.default_rng(123)
    v += rng.normal(0.0, 0.02, size=len(v))

    res = run_tau_analysis_wrapper(
        v,
        t,
        fs,
        stim_start_time=0.05,
        fit_duration=0.12,
        tau_model="mono",
    )
    metrics = res["metrics"]
    assert metrics["tau_ci_95_low"] is not None and math.isfinite(metrics["tau_ci_95_low"])
    assert metrics["tau_ci_95_high"] is not None and math.isfinite(metrics["tau_ci_95_high"])
    assert metrics["tau_ci_95_low"] < metrics["tau_ms"] < metrics["tau_ci_95_high"]
