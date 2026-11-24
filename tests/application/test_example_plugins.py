# tests/application/test_example_plugins.py
# -*- coding: utf-8 -*-
"""
Tests for the example plugins shipped in examples/plugins/.

Validates:
1. PluginManager discovers opto_jitter.py and synaptic_charge.py
   from the examples/plugins/ directory (and removed ap_repolarization.py is absent).
2. Example plugins register themselves with AnalysisRegistry.
3. The wrapper functions return the required nested schema
   ``{"module_used": ..., "metrics": {...}}`` alongside private overlay keys.
4. Core math is correct for multi-pulse, mV-TTL, and subthreshold inputs.
5. Edge cases (empty data, no TTL) yield graceful error dicts
   rather than raising exceptions.
"""

import copy
import importlib.util
import sys
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest

from synaptipy.core.analysis.registry import AnalysisRegistry

# ---------------------------------------------------------------------------
# Constant path to examples/plugins/
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLES_PLUGIN_DIR = _REPO_ROOT / "examples" / "plugins"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_module(plugin_path: Path, module_name: str):
    """Dynamically load a plugin module from an absolute path."""
    spec = importlib.util.spec_from_file_location(module_name, str(plugin_path))
    assert spec is not None and spec.loader is not None, f"Could not create spec for {plugin_path}"
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def isolate_registry():
    """Save and restore the AnalysisRegistry around every test."""
    saved_registry = dict(AnalysisRegistry._registry)
    saved_metadata = copy.deepcopy(AnalysisRegistry._metadata)
    saved_original = copy.deepcopy(AnalysisRegistry._original_metadata)
    yield
    AnalysisRegistry._registry.clear()
    AnalysisRegistry._metadata.clear()
    AnalysisRegistry._original_metadata.clear()
    AnalysisRegistry._registry.update(saved_registry)
    AnalysisRegistry._metadata.update(saved_metadata)
    AnalysisRegistry._original_metadata.update(saved_original)


@pytest.fixture(autouse=True)
def cleanup_plugin_modules():
    """Remove dynamically-loaded plugin modules from sys.modules after each test."""
    yield
    to_remove = [k for k in sys.modules if k.startswith("synaptipy_plugin_")]
    for k in to_remove:
        del sys.modules[k]


@pytest.fixture
def opto_module():
    """Load the opto_jitter example plugin module."""
    path = EXAMPLES_PLUGIN_DIR / "opto_jitter.py"
    assert path.exists(), f"opto_jitter.py not found at {path}"
    return _load_module(path, "synaptipy_plugin_opto_jitter")


@pytest.fixture
def sc_module():
    """Load the synaptic_charge example plugin module."""
    path = EXAMPLES_PLUGIN_DIR / "synaptic_charge.py"
    assert path.exists(), f"synaptic_charge.py not found at {path}"
    return _load_module(path, "synaptipy_plugin_synaptic_charge")


@pytest.fixture
def synthetic_spike():
    """
    Return a 1-second synthetic voltage trace containing one action potential.

    The AP peaks at t = 0.3 s with a peak voltage of +40 mV (above the default
    threshold of -20 mV).
    """
    fs = 10_000.0
    t = np.arange(0, 1.0, 1.0 / fs)
    # Baseline at -65 mV
    data = np.full_like(t, -65.0)
    # Gaussian-shaped AP centred at 0.3 s, width ~2 ms, peak +40 mV
    ap_centre = 0.3
    ap_sigma = 0.002
    ap = 105.0 * np.exp(-0.5 * ((t - ap_centre) / ap_sigma) ** 2) - 65.0
    # Repolarization: add a broader negative lobe after the peak
    repol_centre = 0.305
    repol_sigma = 0.003
    repol = -30.0 * np.exp(-0.5 * ((t - repol_centre) / repol_sigma) ** 2)
    data = data + ap + 65.0 + repol
    return data, t, fs


@pytest.fixture
def synthetic_opto():
    """
    Return a 3-sweep (n_sweeps=3) synthetic dataset with TTL + voltage traces.

    TTL pulses at t=0.05 s (5000 samples at 10 kHz), spike at ~5 ms post-TTL.
    """
    fs = 10_000.0
    n_samples = 2000  # 0.2 s per sweep
    n_sweeps = 3
    t = np.arange(0, n_samples) / fs

    # Voltage: baseline -65 mV, spike 5 ms after TTL for each sweep
    data = np.full((n_sweeps, n_samples), -65.0)
    # TTL: low for first 0.01 s (100 samples), then high
    ttl = np.zeros((n_sweeps, n_samples))
    ttl_onset_sample = 100  # 0.01 s
    ttl[:, ttl_onset_sample:] = 5.0  # 5 V TTL

    # Spike 5 ms = 50 samples after TTL onset
    spike_offset = 50
    spike_centre = ttl_onset_sample + spike_offset
    for sw in range(n_sweeps):
        # Add a little jitter per sweep (1 sample = 0.1 ms)
        jitter_samples = sw  # 0, 1, 2
        sc = spike_centre + jitter_samples
        if sc < n_samples:
            data[sw, sc - 2 : sc + 3] = 20.0  # spike above -20 mV threshold

    return data, t, fs, ttl


# ---------------------------------------------------------------------------
# Phase 6 Test 1 - Discovery
# ---------------------------------------------------------------------------


class TestPluginDiscovery:
    """PluginManager correctly discovers example plugins."""

    def test_examples_dir_exists(self):
        """examples/plugins/ directory must exist."""
        assert EXAMPLES_PLUGIN_DIR.exists(), f"Directory not found: {EXAMPLES_PLUGIN_DIR}"
        assert EXAMPLES_PLUGIN_DIR.is_dir()

    def test_opto_jitter_file_present(self):
        """opto_jitter.py must be present in examples/plugins/."""
        assert (EXAMPLES_PLUGIN_DIR / "opto_jitter.py").exists()

    def test_synaptic_charge_file_present(self):
        """synaptic_charge.py must be present in examples/plugins/."""
        assert (EXAMPLES_PLUGIN_DIR / "synaptic_charge.py").exists()

    def test_removed_ap_repolarization_absent(self):
        """Redundant undocumented ap_repolarization.py must remain removed."""
        assert not (EXAMPLES_PLUGIN_DIR / "ap_repolarization.py").exists()

    def test_plugin_manager_loads_bundled_examples(self):
        """
        PluginManager with EXAMPLES_PLUGIN_DIR patched to examples/plugins/
        loads bundled plugins and registers them without ap_repolarization.
        """
        from synaptipy.application.plugin_manager import PluginManager

        fake_user_dir = EXAMPLES_PLUGIN_DIR.parent / "_no_user_plugins_for_test"

        with (
            patch(
                "synaptipy.application.plugin_manager._get_bundled_plugin_dir",
                return_value=EXAMPLES_PLUGIN_DIR,
            ),
            patch("synaptipy.application.plugin_manager.PLUGIN_DIR", fake_user_dir),
        ):
            PluginManager.load_plugins()

        assert AnalysisRegistry.get_function("opto_jitter") is not None, (
            "opto_jitter was not registered. " f"Registered: {AnalysisRegistry.list_registered()}"
        )
        assert AnalysisRegistry.get_function("synaptic_charge") is not None, (
            "synaptic_charge was not registered. " f"Registered: {AnalysisRegistry.list_registered()}"
        )
        assert AnalysisRegistry.get_function("ap_repolarization") is None

    def test_user_dir_takes_precedence(self, tmp_path):
        """
        When a plugin with the same stem exists in both directories, the
        user copy is used and a warning is logged.
        """
        import shutil

        from synaptipy.application.plugin_manager import PluginManager

        user_plugins = tmp_path / "user_plugins"
        user_plugins.mkdir()
        shutil.copy(EXAMPLES_PLUGIN_DIR / "synaptic_charge.py", user_plugins / "synaptic_charge.py")

        with (
            patch(
                "synaptipy.application.plugin_manager._get_bundled_plugin_dir",
                return_value=EXAMPLES_PLUGIN_DIR,
            ),
            patch("synaptipy.application.plugin_manager.PLUGIN_DIR", user_plugins),
        ):
            PluginManager.load_plugins()

        assert AnalysisRegistry.get_function("synaptic_charge") is not None


# ---------------------------------------------------------------------------
# Phase 6 Test 2 - Schema validation and math
# ---------------------------------------------------------------------------


class TestOptoJitterPlugin:
    """Tests for examples/plugins/opto_jitter.py."""

    def test_module_has_required_attributes(self, opto_module):
        """Module exposes logic function and wrapper."""
        assert hasattr(opto_module, "calculate_opto_jitter")
        assert hasattr(opto_module, "run_opto_jitter_wrapper")

    def test_registry_registration(self, opto_module):
        """opto_jitter registers with name='opto_jitter'."""
        func = AnalysisRegistry.get_function("opto_jitter")
        assert func is not None

    def test_metadata_shape(self, opto_module):
        """Metadata contains label, ui_params, plots, and expects_list=True."""
        meta = AnalysisRegistry.get_metadata("opto_jitter")
        assert meta.get("label") == "Opto Latency Jitter"
        assert isinstance(meta.get("ui_params"), list)
        assert len(meta["ui_params"]) >= 4
        assert isinstance(meta.get("plots"), list)
        assert len(meta["plots"]) >= 1
        assert meta.get("expects_list") is True
        assert meta["requires_secondary_channel"]["param_name"] == "secondary_data"
        assert "optogenetic" in meta["protocol_requirements"]["families"]
        assert "stimulus_train" in meta["protocol_requirements"]["families"]

    def test_output_schema(self, opto_module, synthetic_opto):
        """Wrapper returns the nested {module_used, metrics} schema."""
        data, t, fs, ttl = synthetic_opto
        func = AnalysisRegistry.get_function("opto_jitter")
        result = func(
            data,
            t,
            fs,
            secondary_data=ttl,
            ttl_threshold=2.5,
            search_start=0.002,
            search_end=0.020,
            spike_threshold=-20.0,
        )
        assert isinstance(result, dict), f"Expected dict, got: {type(result)}"
        # Must not be an error result for valid synthetic data
        assert "error" not in result, f"Unexpected error: {result.get('error')}"
        # Required nested schema
        assert "module_used" in result, "Missing 'module_used' key"
        assert result["module_used"] == "opto_jitter"
        assert "metrics" in result, "Missing 'metrics' key"
        assert "Jitter_ms" in result["metrics"], "metrics dict missing 'Jitter_ms'"

    def test_jitter_is_non_negative(self, opto_module, synthetic_opto):
        """Jitter (standard deviation) is always >= 0."""
        data, t, fs, ttl = synthetic_opto
        func = AnalysisRegistry.get_function("opto_jitter")
        result = func(
            data,
            t,
            fs,
            secondary_data=ttl,
            ttl_threshold=2.5,
            search_start=0.002,
            search_end=0.020,
            spike_threshold=-20.0,
        )
        if "error" not in result:
            assert result["metrics"]["Jitter_ms"] >= 0.0

    def test_private_arrays_present(self, opto_module, synthetic_opto):
        """Private _sweep_numbers and _latencies arrays are returned."""
        data, t, fs, ttl = synthetic_opto
        func = AnalysisRegistry.get_function("opto_jitter")
        result = func(
            data,
            t,
            fs,
            secondary_data=ttl,
            ttl_threshold=2.5,
            search_start=0.002,
            search_end=0.020,
            spike_threshold=-20.0,
        )
        if "error" not in result:
            assert "_sweep_numbers" in result
            assert "_latencies" in result
            assert isinstance(result["_sweep_numbers"], np.ndarray)
            assert isinstance(result["_latencies"], np.ndarray)

    def test_empty_data_returns_error(self, opto_module):
        """Empty data array produces an error dict, not an exception."""
        func = AnalysisRegistry.get_function("opto_jitter")
        result = func(np.array([]), np.array([]), 10000.0)
        assert "error" in result

    def test_no_ttl_returns_error_or_graceful(self, opto_module, synthetic_spike):
        """Data with no TTL crossing produces an error dict, not an exception."""
        data, t, fs = synthetic_spike
        flat_ttl = np.zeros_like(data)  # no TTL crossing
        func = AnalysisRegistry.get_function("opto_jitter")
        result = func(
            data,
            t,
            fs,
            secondary_data=flat_ttl,
            ttl_threshold=2.5,
            search_start=0.002,
            search_end=0.020,
            spike_threshold=-20.0,
        )
        assert "error" in result

    def test_direct_logic_function_correct_latency(self, opto_module):
        """
        Direct test of calculate_opto_jitter with known latencies.

        Three sweeps with spikes at exactly 5, 6, and 7 ms post-TTL.
        Expected jitter = std([5, 6, 7], ddof=1) = 1.0 ms.
        """
        fs = 10_000.0
        n_samples = 1000
        t = np.arange(n_samples) / fs
        n_sweeps = 3
        ttl_onset = 100  # sample 100 = 10 ms

        data = np.full((n_sweeps, n_samples), -70.0)
        ttl = np.zeros((n_sweeps, n_samples))
        ttl[:, ttl_onset:] = 5.0

        spike_offsets_ms = [5.0, 6.0, 7.0]
        for sw, delay_ms in enumerate(spike_offsets_ms):
            spike_sample = ttl_onset + int(round(delay_ms * 1e-3 * fs))
            if spike_sample < n_samples:
                data[sw, spike_sample] = 20.0

        result = opto_module.calculate_opto_jitter(
            data=data,
            time=t,
            sampling_rate=fs,
            secondary_data=ttl,
            ttl_threshold=2.5,
            search_start=0.001,
            search_end=0.020,
            spike_threshold=-20.0,
        )
        assert "error" not in result, f"Unexpected error: {result.get('error')}"
        expected_jitter = float(np.std([5.0, 6.0, 7.0], ddof=1))
        jitter_val = result["metrics"]["Jitter_ms"]
        assert abs(jitter_val - expected_jitter) < 0.2, f"Jitter {jitter_val:.4f} ms, expected {expected_jitter:.4f} ms"


class TestOptoJitterMultiPulseAndSubthreshold:
    """Tests for multi-pulse trains, mV-scaled TTL channels, and subthreshold EPSP fallback."""

    def test_multi_pulse_mv_ttl_and_subthreshold_auto_fallback(self, opto_module):
        """
        Simulate a 3-sweep x 3-pulse optogenetic recording where FrameTTL is recorded
        in mV (12..1600 mV) and responses are subthreshold EPSPs (~6 mV above -65 mV).
        """
        fs = 20_000.0
        t = np.arange(0.0, 0.5, 1.0 / fs)
        n_samples = t.size
        n_sweeps = 3
        pulse_times = (0.08, 0.20, 0.32)

        data = np.full((n_sweeps, n_samples), -65.0)
        ttl = np.full((n_sweeps, n_samples), 12.0)  # Resting TTL baseline in mV (> 2.5 V threshold!)
        for st in pulse_times:
            i0 = int(round(st * fs))
            ttl[:, i0 : i0 + 40] = 1600.0

        for sw in range(n_sweeps):
            for p_idx, st in enumerate(pulse_times):
                ev_onset = st + 0.004 + (sw * 0.0002) + (p_idx * 0.0001)
                mask = t >= ev_onset
                rel = t[mask] - ev_onset
                data[sw, mask] += 9.0 * (np.exp(-rel / 0.010) - np.exp(-rel / 0.0015))

        fn = AnalysisRegistry.get_function("opto_jitter")
        res = fn(
            data,
            t,
            fs,
            secondary_data=ttl,
            ttl_threshold=2.5,
            search_start=0.001,
            search_end=0.040,
            spike_threshold=-20.0,
        )
        assert "error" not in res, f"Unexpected error: {res.get('error')}"
        assert res["metrics"]["N_Sweeps_Detected"] == 9
        assert res["metrics"]["Detection_Mode_Used"] == "Peak Deflection"
        assert len(res["_stim_onsets"]) == 3
        assert len(res["_window_starts_s"]) == 3
        assert len(res["_window_ends_s"]) == 3
        assert len(res["_detected_times"]) == 3
        assert res["metrics"]["Jitter_ms"] > 0.0
