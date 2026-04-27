# -*- coding: utf-8 -*-
"""Targeted biological edge-case tests for Synaptipy.

Three specific regression tests that verify biological logic cannot be silently
corrupted by common experimental artefacts:

1. ``test_rs_tolerance_rejection`` - Rs drift > 20% is flagged in batch output.
2. ``test_opto_artifact_survival`` - photo-electric artefact at TTL onset does not
   mask the biological spike 3 ms later.
3. ``test_drifting_synaptic_charge`` - local dynamic baseline yields better AUC
   accuracy than a global average on a heavily drifting trace.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np

import Synaptipy.core.analysis  # noqa: F401 – populate the AnalysisRegistry
from Synaptipy.core.analysis.batch_engine import BatchAnalysisEngine
from Synaptipy.core.analysis.registry import AnalysisRegistry
from Synaptipy.core.data_model import Channel, Recording

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _RegistryGuard:
    """Context manager that saves and restores the AnalysisRegistry state."""

    def __enter__(self):
        self._saved_r = dict(AnalysisRegistry._registry)
        self._saved_m = dict(AnalysisRegistry._metadata)
        return self

    def __exit__(self, *_):
        AnalysisRegistry._registry.clear()
        AnalysisRegistry._metadata.clear()
        AnalysisRegistry._registry.update(self._saved_r)
        AnalysisRegistry._metadata.update(self._saved_m)


def _make_channel_with_trials(trial_values, fs=10_000.0, n=100):
    """Return a Channel whose trials have data[0] == trial_values[i]."""
    trials = [np.full(n, v) for v in trial_values]
    return Channel(id="0", name="V", units="mV", sampling_rate=fs, data_trials=trials)


def _make_rec_with_channel(channel):
    rec = Recording(source_file=Path("test_cell.abf"))
    rec.channels["0"] = channel
    return rec


# ---------------------------------------------------------------------------
# Test 1 – Rs stability: sweeps with >20 % Rs rise must be flagged
# ---------------------------------------------------------------------------


def test_rs_tolerance_rejection():
    """
    Batch engine flags every trial whose Rs exceeds 120 % of Sweep-1's Rs.

    Protocol:
    - 10 trials per cell.  Trials 0-4: Rs = 10.0 MOhm.
                            Trials 5-9: Rs = 13.0 MOhm (+30 %).
    - rs_tolerance = 0.20 (20 %).
    - Expected: trials 5-9 have a non-empty ``rs_qc_warning`` string.
                trials 0-4 have no warning.
    """
    with _RegistryGuard():
        # Mock analysis: report data[0] as Rs in MOhm.
        @AnalysisRegistry.register("_rs_probe_test")
        def _rs_probe(data, time, sampling_rate, **kwargs):
            return {"rs_mohm": float(data[0])}

        # Trials 0-4 stable at 10 MOhm; trials 5-9 drift to 13 MOhm (+30 %).
        rs_values = [10.0] * 5 + [13.0] * 5
        channel = _make_channel_with_trials(rs_values)
        rec = _make_rec_with_channel(channel)

        engine = BatchAnalysisEngine(max_workers=1)
        engine.neo_adapter.read_recording = MagicMock(return_value=rec)

        pipeline = [{"analysis": "_rs_probe_test", "scope": "all_trials", "params": {}}]
        df = engine.run_batch([Path("test_cell.abf")], pipeline, rs_tolerance=0.20)

        assert len(df) == 10, f"Expected 10 rows, got {len(df)}"

        # Trials 0-4: no warning expected.
        for i in range(5):
            val = df.iloc[i].get("rs_qc_warning")
            assert val in (None, np.nan, "") or (
                isinstance(val, float) and np.isnan(val)
            ), f"Trial {i} should not carry rs_qc_warning, but got: {val!r}"

        # Trials 5-9: warning must be present and non-empty.
        assert "rs_qc_warning" in df.columns, "rs_qc_warning column must be present in output"
        for i in range(5, 10):
            val = df.iloc[i]["rs_qc_warning"]
            assert (
                isinstance(val, str) and len(val) > 0
            ), f"Trial {i} (Rs=13 MOhm) should have rs_qc_warning, but got: {val!r}"
            assert (
                "13" in val or "destabilized" in val.lower()
            ), f"Warning text for trial {i} does not mention Rs value: {val!r}"


# ---------------------------------------------------------------------------
# Test 2 – Opto blanking: photo-electric artefact must not mask biological spike
# ---------------------------------------------------------------------------


def test_opto_artifact_survival():
    """
    ``calculate_opto_jitter`` must detect the 3 ms biological spike, not the
    0.1 ms photo-electric artefact at the TTL onset.

    Protocol (10 sweeps, single-sweep geometry):
    - TTL pulse rises at sample 500 (t = 25 ms).
    - Massive artefact spike (+200 mV, half-width 2 samples) centred at sample 501.
    - Biological spike (+40 mV above threshold, half-width 5 samples)
      centred at sample 560 (= TTL onset + 3 ms at 20 kHz).
    - blanking_window = 1.0 ms  → skips samples 1-20 after TTL.
    - Expected mean latency ≈ 3 ms (not 0.05 ms from the artefact).
    """
    # Lazy import to keep this module importable without optional packages.
    sys.path.insert(0, str(Path(__file__).parents[2] / "examples" / "plugins"))
    from opto_jitter import calculate_opto_jitter  # noqa: PLC0415

    fs = 20_000.0
    n_samples = 1000
    n_sweeps = 10
    ttl_onset_sample = 500
    bio_offset_samples = int(round(0.003 * fs))  # 3 ms = 60 samples
    bio_spike_sample = ttl_onset_sample + bio_offset_samples

    time = np.linspace(0, n_samples / fs, n_samples, endpoint=False)
    resting = -65.0
    spike_threshold = -20.0  # mV

    data = np.full((n_sweeps, n_samples), resting)
    ttl = np.zeros((n_sweeps, n_samples))

    for sw in range(n_sweeps):
        # TTL: step up at ttl_onset_sample
        ttl[sw, ttl_onset_sample:] = 5.0

        # Photo-electric artefact: huge, fast spike at TTL onset (0.1 ms wide)
        art_half = max(1, int(round(0.0001 * fs / 2)))
        for j in range(ttl_onset_sample, min(n_samples, ttl_onset_sample + art_half * 2)):
            frac = 1.0 - abs(j - ttl_onset_sample) / art_half
            data[sw, j] = resting + (200.0 - resting) * max(0.0, frac)

        # Biological spike: above spike_threshold, 3 ms latency
        bio_half = 5  # samples
        for j in range(max(0, bio_spike_sample - bio_half), min(n_samples, bio_spike_sample + bio_half)):
            frac = 1.0 - abs(j - bio_spike_sample) / bio_half
            data[sw, j] = resting + (40.0 - resting) * max(0.0, frac)

    result = calculate_opto_jitter(
        data=data,
        time=time,
        sampling_rate=fs,
        secondary_data=ttl,
        ttl_threshold=2.5,
        search_start=0.0,
        search_end=0.020,  # 20 ms search window
        spike_threshold=spike_threshold,
        blanking_window=1.0,  # 1 ms blanking
    )

    assert "error" not in result, f"Plugin returned error: {result.get('error')}"
    metrics = result.get("metrics", {})
    mean_lat = metrics.get("Mean_Latency_ms")
    assert mean_lat is not None, "Mean_Latency_ms missing from result"
    # The biological spike is at 3 ms; allow ±1 ms tolerance for rounding.
    assert 2.0 <= mean_lat <= 4.5, (
        f"Expected biological latency ~3 ms but got {mean_lat:.3f} ms. "
        "The blanking window may not be suppressing the photo-electric artefact."
    )


# ---------------------------------------------------------------------------
# Test 3 – Drifting baseline: local dynamic baseline outperforms global mean
# ---------------------------------------------------------------------------


def test_drifting_synaptic_charge():
    """
    On a trace with a large step-change in holding current, the local dynamic
    baseline (10 ms pre-window) must recover the true EPSC charge substantially
    more accurately than a global trace mean.

    Protocol (1 s at 20 kHz):
    - t = 0.0 – 0.5 s : holding current = +10 pA
    - t = 0.5 – 1.0 s : holding current jumps to +90 pA  (+80 pA step)
    - EPSC at t = 0.800 s: additional -60 pA rectangular pulse, 10 ms duration.
    - True charge = -60 pA × 0.010 s = -0.600 pC.

    Global mean ≈ (10 k × 10 + 10 k × 90) / 20 k ≈ 50 pA, which is 40 pA
    below the actual pre-event level of 90 pA.  The global-baseline-subtracted
    EPSC only dips to -20 pA (= 30 - 50), giving an integrated charge of
    ≈ -0.20 pC — an error of 0.40 pC.

    The local 10 ms window (t = 0.790 – 0.800 s) sees +90 pA throughout,
    so baseline_val = 90 pA and the charge integral recovers -0.60 pC
    with near-zero error.
    """
    sys.path.insert(0, str(Path(__file__).parents[2] / "examples" / "plugins"))
    from synaptic_charge import calculate_synaptic_charge  # noqa: PLC0415

    fs = 20_000.0
    n = int(fs * 1.0)
    time = np.linspace(0, 1.0, n, endpoint=False)

    # Step-change drift: +10 pA for first 500 ms, +90 pA for the rest.
    step_idx = int(0.5 * fs)
    data = np.empty(n, dtype=float)
    data[:step_idx] = 10.0
    data[step_idx:] = 90.0

    # EPSC: -60 pA rectangular pulse at t = 0.800 s, 10 ms long.
    epsc_amp = -60.0
    epsc_start_idx = int(0.800 * fs)
    epsc_end_idx = int(0.810 * fs)
    data[epsc_start_idx:epsc_end_idx] += epsc_amp

    # True charge: -60 pA × 0.010 s = -0.600 pC
    true_charge_pc = epsc_amp * 0.010  # pA × s = pC

    # Search window spans 5 ms before EPSC through 20 ms after onset.
    window_start = 0.795
    window_end = 0.825

    # --- Local baseline (10 ms pre-window, tracks the step-change) ---
    res_local = calculate_synaptic_charge(
        data=data,
        time=time,
        sampling_rate=fs,
        window_start=window_start,
        window_end=window_end,
        baseline_method="Pre-Window",
        detection_method="Negative Peak",
        local_baseline_window_ms=10.0,
    )
    assert "error" not in res_local, f"Local baseline run failed: {res_local}"

    # --- Global baseline (entire-trace mean, dominated by the step history) ---
    res_global = calculate_synaptic_charge(
        data=data,
        time=time,
        sampling_rate=fs,
        window_start=window_start,
        window_end=window_end,
        baseline_method="Global",
        detection_method="Negative Peak",
    )
    assert "error" not in res_global, f"Global baseline run failed: {res_global}"

    charge_local = res_local["metrics"]["Charge_pC"]
    charge_global = res_global["metrics"]["Charge_pC"]

    err_local = abs(charge_local - true_charge_pc)
    err_global = abs(charge_global - true_charge_pc)

    # Local baseline must be substantially closer to the true charge.
    assert err_local < err_global, (
        f"Local baseline (error={err_local:.4f} pC) should outperform "
        f"global baseline (error={err_global:.4f} pC) on step-change trace. "
        f"Local charge={charge_local:.4f} pC, global={charge_global:.4f} pC, "
        f"true={true_charge_pc:.4f} pC."
    )

    # Local baseline error must be within 10 % of the true EPSC charge.
    rel_err_local = err_local / abs(true_charge_pc)
    assert rel_err_local < 0.10, (
        f"Local baseline relative error {rel_err_local:.1%} exceeds 10 %. "
        f"Charge_pC={charge_local:.4f}, true={true_charge_pc:.4f}."
    )
