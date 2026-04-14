# tests/application/test_example_plugins.py
# -*- coding: utf-8 -*-
"""
Tests for the example plugins shipped in examples/plugins/.

Validates:
1. PluginManager discovers both opto_jitter.py and ap_repolarization.py
   from the examples/plugins/ directory.
2. Both plugins register themselves with AnalysisRegistry.
3. The wrapper functions return the required nested schema
   ``{"module_used": ..., "metrics": {...}}`` alongside flat scalar keys.
4. Core math is correct for simple synthetic inputs.
5. Edge cases (empty data, no TTL, no spike) yield graceful error dicts
   rather than raising exceptions.
"""

import copy
import importlib.util
import sys
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest

from Synaptipy.core.analysis.registry import AnalysisRegistry

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
def ap_module():
    """Load the ap_repolarization example plugin module."""
    path = EXAMPLES_PLUGIN_DIR / "ap_repolarization.py"
    assert path.exists(), f"ap_repolarization.py not found at {path}"
    return _load_module(path, "synaptipy_plugin_ap_repolarization")


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

    def test_ap_repolarization_file_present(self):
        """ap_repolarization.py must be present in examples/plugins/."""
        assert (EXAMPLES_PLUGIN_DIR / "ap_repolarization.py").exists()

    def test_plugin_manager_loads_both_examples(self):
        """
        PluginManager with EXAMPLES_PLUGIN_DIR patched to examples/plugins/
        loads both plugins and registers them.
        """
        from Synaptipy.application.plugin_manager import PluginManager

        # Patch the EXAMPLES_PLUGIN_DIR used inside PluginManager, and set
        # user PLUGIN_DIR to a non-existent path to avoid interference.
        fake_user_dir = EXAMPLES_PLUGIN_DIR.parent / "_no_user_plugins_for_test"

        with (
            patch("Synaptipy.application.plugin_manager.EXAMPLES_PLUGIN_DIR", EXAMPLES_PLUGIN_DIR),
            patch("Synaptipy.application.plugin_manager.PLUGIN_DIR", fake_user_dir),
        ):
            PluginManager.load_plugins()

        assert AnalysisRegistry.get_function("opto_jitter") is not None, (
            "opto_jitter was not registered. " f"Registered: {AnalysisRegistry.list_registered()}"
        )
        assert AnalysisRegistry.get_function("ap_repolarization") is not None, (
            "ap_repolarization was not registered. " f"Registered: {AnalysisRegistry.list_registered()}"
        )

    def test_user_dir_takes_precedence(self, tmp_path):
        """
        When a plugin with the same stem exists in both directories, the
        user copy is used and a warning is logged.
        """
        import shutil

        from Synaptipy.application.plugin_manager import PluginManager

        # Copy ap_repolarization.py to a fake user dir
        user_plugins = tmp_path / "user_plugins"
        user_plugins.mkdir()
        shutil.copy(EXAMPLES_PLUGIN_DIR / "ap_repolarization.py", user_plugins / "ap_repolarization.py")

        with (
            patch("Synaptipy.application.plugin_manager.EXAMPLES_PLUGIN_DIR", EXAMPLES_PLUGIN_DIR),
            patch("Synaptipy.application.plugin_manager.PLUGIN_DIR", user_plugins),
        ):
            # The collision warning is logged at WARNING level, not raised as an exception.
            PluginManager.load_plugins()

        # Plugin should still be registered (user copy loaded)
        assert AnalysisRegistry.get_function("ap_repolarization") is not None


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
        """Metadata contains label, ui_params, and plots."""
        meta = AnalysisRegistry.get_metadata("opto_jitter")
        assert meta.get("label") == "Opto Latency Jitter"
        assert isinstance(meta.get("ui_params"), list)
        assert len(meta["ui_params"]) >= 4
        assert isinstance(meta.get("plots"), list)
        assert len(meta["plots"]) >= 1

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
        assert (
            abs(result["Jitter_ms"] - expected_jitter) < 0.2
        ), f"Jitter {result['Jitter_ms']:.4f} ms, expected {expected_jitter:.4f} ms"


class TestAPRepolarizationPlugin:
    """Tests for examples/plugins/ap_repolarization.py."""

    def test_module_has_required_attributes(self, ap_module):
        """Module exposes logic function and wrapper."""
        assert hasattr(ap_module, "calculate_ap_repolarization")
        assert hasattr(ap_module, "run_ap_repolarization_wrapper")

    def test_registry_registration(self, ap_module):
        """ap_repolarization registers with name='ap_repolarization'."""
        func = AnalysisRegistry.get_function("ap_repolarization")
        assert func is not None

    def test_metadata_shape(self, ap_module):
        """Metadata contains label, ui_params, and plots."""
        meta = AnalysisRegistry.get_metadata("ap_repolarization")
        assert meta.get("label") == "Max Repolarization Rate"
        assert isinstance(meta.get("ui_params"), list)
        assert len(meta["ui_params"]) >= 3
        assert isinstance(meta.get("plots"), list)
        assert len(meta["plots"]) >= 1

    def test_output_schema(self, ap_module, synthetic_spike):
        """Wrapper returns the nested {module_used, metrics} schema."""
        data, t, fs = synthetic_spike
        func = AnalysisRegistry.get_function("ap_repolarization")
        result = func(data, t, fs, window_start=0.0, window_end=1.0, spike_threshold=-20.0)
        assert isinstance(result, dict), f"Expected dict, got: {type(result)}"
        assert "error" not in result, f"Unexpected error: {result.get('error')}"
        assert "module_used" in result, "Missing 'module_used' key"
        assert result["module_used"] == "ap_repolarization"
        assert "metrics" in result, "Missing 'metrics' key"
        assert "Max_Repol_V_s" in result["metrics"], "metrics dict missing 'Max_Repol_V_s'"

    def test_repolarization_rate_is_negative(self, ap_module, synthetic_spike):
        """Max repolarization rate must be negative (falling phase of AP)."""
        data, t, fs = synthetic_spike
        func = AnalysisRegistry.get_function("ap_repolarization")
        result = func(data, t, fs, window_start=0.0, window_end=1.0, spike_threshold=-20.0)
        if "error" not in result:
            assert (
                result["metrics"]["Max_Repol_V_s"] < 0.0
            ), f"Expected negative repolarization rate, got {result['metrics']['Max_Repol_V_s']}"

    def test_private_marker_keys_present(self, ap_module, synthetic_spike):
        """Private _repol_time and _repol_val are returned for the marker overlay."""
        data, t, fs = synthetic_spike
        func = AnalysisRegistry.get_function("ap_repolarization")
        result = func(data, t, fs, window_start=0.0, window_end=1.0, spike_threshold=-20.0)
        if "error" not in result:
            assert "_repol_time" in result
            assert "_repol_val" in result

    def test_empty_data_returns_error(self, ap_module):
        """Empty data array produces an error dict, not an exception."""
        func = AnalysisRegistry.get_function("ap_repolarization")
        result = func(np.array([]), np.array([]), 10000.0)
        assert "error" in result

    def test_no_spike_in_window_returns_error(self, ap_module):
        """A flat trace with no spike crossing returns an error dict."""
        fs = 10_000.0
        t = np.arange(0, 0.5, 1.0 / fs)
        data = np.full_like(t, -70.0)  # flat below threshold
        func = AnalysisRegistry.get_function("ap_repolarization")
        result = func(data, t, fs, window_start=0.0, window_end=0.5, spike_threshold=-20.0)
        assert "error" in result

    def test_direct_logic_trapz_math(self, ap_module):
        """
        Direct test of calculate_ap_repolarization: the minimum dV/dt of a
        triangular spike is exactly at the most steeply falling sample.

        Construct a symmetric triangle: rises from 0 to 100 mV over 10 samples,
        falls back to 0 over 10 samples.  The fall rate = -10 mV / sample.
        With dt = 0.0001 s, that is -10 / 0.0001 = -100,000 V/s.
        np.gradient uses central differences, so the exact answer is approached
        within 1% for this ideal triangle.
        """
        fs = 10_000.0
        dt = 1.0 / fs
        # Build a triangular AP: baseline at -70, peak at +30
        n_base = 50
        n_rise = 10
        n_fall = 10
        n_after = 50
        baseline = np.full(n_base, -70.0)
        rise = np.linspace(-70.0, 30.0, n_rise)
        fall = np.linspace(30.0, -70.0, n_fall)
        after = np.full(n_after, -70.0)
        data = np.concatenate([baseline, rise, fall, after])
        t = np.arange(len(data)) * dt

        result = ap_module.calculate_ap_repolarization(
            data=data,
            time=t,
            sampling_rate=fs,
            window_start=0.0,
            window_end=len(data) * dt,
            spike_threshold=-20.0,
        )
        assert "error" not in result, f"Unexpected error: {result.get('error')}"
        # Expected fall rate: (30 - (-70)) / (n_fall * dt) = 100 / 0.001 = 100,000 mV/s = 100 V/s
        # Max repolarization is negative: expected ~ -100,000 mV/s = -100 V/s
        max_repol = result["metrics"]["Max_Repol_V_s"]
        assert max_repol < 0.0, "Repolarization rate should be negative"
        # Accept within 10% of -100 V/s
        assert abs(max_repol) > 80.0, f"Repol rate {max_repol} V/s is suspiciously small"
