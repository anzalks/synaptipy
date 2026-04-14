# tests/application/test_plugin_system.py
# -*- coding: utf-8 -*-
"""
Test suite for the Synaptipy plugin system integration.

Validates:
1. PluginManager.load_plugins() is a no-op when the ``enable_plugins``
   QSettings key is ``False``.
2. PluginManager.load_plugins() discovers and loads all three example plugins
   (opto_jitter, ap_repolarization, synaptic_charge) when ``enable_plugins``
   is ``True``.
3. The wrapper functions registered by each example plugin return the
   required nested ``{"module_used": ..., "metrics": {...}}`` dictionary
   schema without crashing.
4. The synaptic_charge plugin returns the correct hidden plotting arrays
   required by its fill_between / markers overlays.
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
# Paths
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLES_PLUGIN_DIR = _REPO_ROOT / "examples" / "plugins"
_FAKE_USER_DIR = EXAMPLES_PLUGIN_DIR.parent / "_no_user_plugins_for_test"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def isolate_registry():
    """Save and restore the AnalysisRegistry state around every test."""
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


def _load_module(plugin_path: Path, module_name: str):
    """Dynamically load a plugin module from an absolute path."""
    spec = importlib.util.spec_from_file_location(module_name, str(plugin_path))
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def opto_module():
    """Load opto_jitter example plugin."""
    path = EXAMPLES_PLUGIN_DIR / "opto_jitter.py"
    assert path.exists(), f"opto_jitter.py not found at {path}"
    return _load_module(path, "synaptipy_plugin_opto_jitter")


@pytest.fixture
def ap_module():
    """Load ap_repolarization example plugin."""
    path = EXAMPLES_PLUGIN_DIR / "ap_repolarization.py"
    assert path.exists(), f"ap_repolarization.py not found at {path}"
    return _load_module(path, "synaptipy_plugin_ap_repolarization")


@pytest.fixture
def synthetic_spike():
    """
    1-second synthetic voltage trace with one action potential at t=0.3 s.

    Sampling rate: 10 kHz.  Spike peaks at +40 mV (above -20 mV threshold).
    Repolarization lobe ensures the gradient minimum is clearly defined.
    """
    fs = 10_000.0
    t = np.arange(0, 1.0, 1.0 / fs)
    data = np.full_like(t, -65.0)
    ap_centre, ap_sigma = 0.3, 0.002
    ap = 105.0 * np.exp(-0.5 * ((t - ap_centre) / ap_sigma) ** 2)
    repol_centre, repol_sigma = 0.305, 0.003
    repol = -30.0 * np.exp(-0.5 * ((t - repol_centre) / repol_sigma) ** 2)
    data = data + ap + repol
    return data, t, fs


@pytest.fixture
def synthetic_opto():
    """
    3-sweep dataset: 10 kHz, TTL onset at 10 ms, spike at 15 ms per sweep.

    Each sweep has 1 sample of extra jitter (0, 1, 2 samples) so jitter > 0.
    """
    fs = 10_000.0
    n_samples = 2000
    n_sweeps = 3
    t = np.arange(0, n_samples) / fs

    data = np.full((n_sweeps, n_samples), -65.0)
    ttl = np.zeros((n_sweeps, n_samples))
    ttl_onset = 100  # 10 ms
    ttl[:, ttl_onset:] = 5.0

    spike_offset = 50  # 5 ms post-TTL
    for sw in range(n_sweeps):
        sc = ttl_onset + spike_offset + sw
        if sc < n_samples:
            data[sw, sc - 2 : sc + 3] = 20.0
    return data, t, fs, ttl


# ---------------------------------------------------------------------------
# Tests: Settings gate
# ---------------------------------------------------------------------------


class TestSettingsGate:
    """PluginManager respects the enable_plugins QSettings key."""

    def test_skips_loading_when_disabled(self):
        """load_plugins() must be a no-op when enable_plugins=False."""
        from Synaptipy.application.plugin_manager import PluginManager

        before = dict(AnalysisRegistry._registry)

        with (
            patch("Synaptipy.application.plugin_manager.EXAMPLES_PLUGIN_DIR", EXAMPLES_PLUGIN_DIR),
            patch("Synaptipy.application.plugin_manager.PLUGIN_DIR", _FAKE_USER_DIR),
            patch("Synaptipy.application.plugin_manager.QSettings") as mock_settings_cls,
        ):
            mock_settings_cls.return_value.value.return_value = False
            PluginManager.load_plugins()

        after = dict(AnalysisRegistry._registry)
        # Registry must not have grown - no new plugins should be registered.
        new_keys = set(after) - set(before)
        assert not new_keys, f"Plugins were loaded despite enable_plugins=False: {new_keys}"

    def test_loads_plugins_when_enabled(self):
        """load_plugins() registers opto_jitter and ap_repolarization when enable_plugins=True."""
        from Synaptipy.application.plugin_manager import PluginManager

        with (
            patch("Synaptipy.application.plugin_manager.EXAMPLES_PLUGIN_DIR", EXAMPLES_PLUGIN_DIR),
            patch("Synaptipy.application.plugin_manager.PLUGIN_DIR", _FAKE_USER_DIR),
            patch("Synaptipy.application.plugin_manager.QSettings") as mock_settings_cls,
        ):
            mock_settings_cls.return_value.value.return_value = True
            PluginManager.load_plugins()

        assert (
            AnalysisRegistry.get_function("opto_jitter") is not None
        ), "opto_jitter not registered after load with enable_plugins=True"
        assert (
            AnalysisRegistry.get_function("ap_repolarization") is not None
        ), "ap_repolarization not registered after load with enable_plugins=True"
        assert (
            AnalysisRegistry.get_function("synaptic_charge") is not None
        ), "synaptic_charge not registered after load with enable_plugins=True"


# ---------------------------------------------------------------------------
# Tests: opto_jitter schema and correctness
# ---------------------------------------------------------------------------


class TestOptoJitterSchema:
    """Validate the opto_jitter wrapper return schema."""

    def test_returns_nested_schema(self, opto_module, synthetic_opto):
        """Wrapper must return {module_used, metrics: {Jitter_ms}} on success."""
        data, t, fs, ttl = synthetic_opto
        fn = AnalysisRegistry.get_function("opto_jitter")
        assert fn is not None, "opto_jitter not in registry after loading module"

        result = fn(
            data,
            t,
            fs,
            secondary_data=ttl,
            ttl_threshold=2.5,
            search_start=0.002,
            search_end=0.020,
            spike_threshold=-20.0,
        )

        assert isinstance(result, dict), f"Expected dict, got {type(result)}"
        assert "error" not in result, f"Unexpected error: {result.get('error')}"
        assert result.get("module_used") == "opto_jitter", f"module_used mismatch: {result.get('module_used')}"
        assert "metrics" in result, "Missing top-level 'metrics' key"
        assert "Jitter_ms" in result["metrics"], f"Missing 'Jitter_ms' in metrics: {result['metrics']}"

    def test_jitter_non_negative(self, opto_module, synthetic_opto):
        """Jitter (std dev of latencies) must be >= 0."""
        data, t, fs, ttl = synthetic_opto
        fn = AnalysisRegistry.get_function("opto_jitter")
        result = fn(
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

    def test_empty_data_returns_error(self, opto_module):
        """Empty arrays must return an error dict, not raise."""
        from Synaptipy.application.plugin_manager import PluginManager  # noqa: F401

        mod = opto_module
        result = mod.calculate_opto_jitter(
            data=np.array([]),
            time=np.array([]),
            sampling_rate=10_000.0,
            secondary_data=np.array([]),
            ttl_threshold=0.5,
            search_start=0.001,
            search_end=0.05,
            spike_threshold=-20.0,
        )
        assert "error" in result, "Expected error dict for empty data"

    def test_no_ttl_returns_error(self, opto_module):
        """No TTL crossing must produce a graceful error dict."""
        mod = opto_module
        fs = 10_000.0
        t = np.linspace(0, 0.2, 2000)
        data = np.full((3, 2000), -65.0)
        ttl = np.zeros((3, 2000))  # No TTL crossing

        result = mod.calculate_opto_jitter(
            data=data,
            time=t,
            sampling_rate=fs,
            secondary_data=ttl,
            ttl_threshold=2.5,
            search_start=0.001,
            search_end=0.05,
            spike_threshold=-20.0,
        )
        assert "error" in result, "Expected error dict when no TTL crossing"


# ---------------------------------------------------------------------------
# Tests: ap_repolarization schema and correctness
# ---------------------------------------------------------------------------


class TestApRepolarizationSchema:
    """Validate the ap_repolarization wrapper return schema."""

    def test_returns_nested_schema(self, ap_module, synthetic_spike):
        """Wrapper must return {module_used, metrics: {Max_Repol_V_s}} on success."""
        data, t, fs = synthetic_spike
        fn = AnalysisRegistry.get_function("ap_repolarization")
        assert fn is not None, "ap_repolarization not in registry after loading module"

        result = fn(
            data,
            t,
            fs,
            window_start=0.0,
            window_end=1.0,
            spike_threshold=-20.0,
        )

        assert isinstance(result, dict), f"Expected dict, got {type(result)}"
        assert "error" not in result, f"Unexpected error: {result.get('error')}"
        assert result.get("module_used") == "ap_repolarization", f"module_used mismatch: {result.get('module_used')}"
        assert "metrics" in result, "Missing top-level 'metrics' key"
        assert "Max_Repol_V_s" in result["metrics"], f"Missing 'Max_Repol_V_s' in metrics: {result['metrics']}"

    def test_repol_rate_is_negative(self, ap_module, synthetic_spike):
        """Max repolarization rate dV/dt must be negative (falling phase)."""
        data, t, fs = synthetic_spike
        fn = AnalysisRegistry.get_function("ap_repolarization")
        result = fn(
            data,
            t,
            fs,
            window_start=0.0,
            window_end=1.0,
            spike_threshold=-20.0,
        )
        if "error" not in result:
            assert result["metrics"]["Max_Repol_V_s"] < 0.0, "Repolarization rate must be negative (falling slope)"

    def test_private_keys_present(self, ap_module, synthetic_spike):
        """Private _repol_time and _repol_val must be in the result dict."""
        data, t, fs = synthetic_spike
        fn = AnalysisRegistry.get_function("ap_repolarization")
        result = fn(
            data,
            t,
            fs,
            window_start=0.0,
            window_end=1.0,
            spike_threshold=-20.0,
        )
        if "error" not in result:
            assert "_repol_time" in result, "Missing private key '_repol_time'"
            assert "_repol_val" in result, "Missing private key '_repol_val'"

    def test_empty_data_returns_error(self, ap_module):
        """Empty array must return an error dict, not raise."""
        mod = ap_module
        result = mod.calculate_ap_repolarization(
            data=np.array([]),
            time=np.array([]),
            sampling_rate=10_000.0,
            window_start=0.0,
            window_end=1.0,
            spike_threshold=-20.0,
        )
        assert "error" in result, "Expected error dict for empty data"

    def test_no_spike_returns_error(self, ap_module):
        """A flat sub-threshold trace must produce a graceful error dict."""
        mod = ap_module
        fs = 10_000.0
        t = np.linspace(0, 1.0, 10_000)
        data = np.full(10_000, -65.0)  # No AP

        result = mod.calculate_ap_repolarization(
            data=data,
            time=t,
            sampling_rate=fs,
            window_start=0.0,
            window_end=1.0,
            spike_threshold=-20.0,
        )
        assert "error" in result, "Expected error dict when no spike present"


# ---------------------------------------------------------------------------
# Fixtures: synaptic_charge
# ---------------------------------------------------------------------------


@pytest.fixture
def sc_module():
    """Load synaptic_charge example plugin."""
    path = EXAMPLES_PLUGIN_DIR / "synaptic_charge.py"
    assert path.exists(), f"synaptic_charge.py not found at {path}"
    return _load_module(path, "synaptipy_plugin_synaptic_charge")


@pytest.fixture
def synthetic_epsc():
    """
    1-second synthetic current trace (10 kHz) mimicking a brief inward EPSC.

    Baseline at 0 pA; a Gaussian-shaped inward current (negative) peaks at
    t=0.05 s with an amplitude of -100 pA and sigma of 0.01 s.
    """
    fs = 10_000.0
    t = np.arange(0, 1.0, 1.0 / fs)
    data = np.zeros_like(t)
    peak_t, peak_amp, sigma = 0.05, -100.0, 0.01
    data += peak_amp * np.exp(-0.5 * ((t - peak_t) / sigma) ** 2)
    return data, t, fs


# ---------------------------------------------------------------------------
# Tests: synaptic_charge schema and correctness
# ---------------------------------------------------------------------------


class TestSynapticChargeSchema:
    """Validate the synaptic_charge wrapper return schema."""

    def test_returns_nested_schema(self, sc_module, synthetic_epsc):
        """Wrapper must return {module_used, metrics: {Charge_pC, Peak_Amp}} on success."""
        data, t, fs = synthetic_epsc
        fn = AnalysisRegistry.get_function("synaptic_charge")
        assert fn is not None, "synaptic_charge not in registry after loading module"

        result = fn(data, t, fs, integration_start=0.0, integration_end=0.1)

        assert isinstance(result, dict), f"Expected dict, got {type(result)}"
        assert "error" not in result, f"Unexpected error: {result.get('error')}"
        assert result.get("module_used") == "synaptic_charge", f"module_used mismatch: {result.get('module_used')}"
        assert "metrics" in result, "Missing top-level 'metrics' key"
        assert "Charge_pC" in result["metrics"], f"Missing 'Charge_pC' in metrics: {result['metrics']}"
        assert "Peak_Amp" in result["metrics"], f"Missing 'Peak_Amp' in metrics: {result['metrics']}"

    def test_charge_is_negative_for_inward_current(self, sc_module, synthetic_epsc):
        """Integrating a purely negative (inward) trace must yield a negative charge."""
        data, t, fs = synthetic_epsc
        fn = AnalysisRegistry.get_function("synaptic_charge")
        result = fn(data, t, fs, integration_start=0.0, integration_end=0.1)
        if "error" not in result:
            assert result["metrics"]["Charge_pC"] < 0.0, "Charge must be negative for an inward current"

    def test_peak_amp_is_negative_for_inward_current(self, sc_module, synthetic_epsc):
        """Peak amplitude must be negative for an inward EPSC."""
        data, t, fs = synthetic_epsc
        fn = AnalysisRegistry.get_function("synaptic_charge")
        result = fn(data, t, fs, integration_start=0.0, integration_end=0.1)
        if "error" not in result:
            assert result["metrics"]["Peak_Amp"] < 0.0, "Peak_Amp must be negative for an inward current"

    def test_private_plotting_keys_present(self, sc_module, synthetic_epsc):
        """Hidden keys required by fill_between and markers overlays must be present."""
        data, t, fs = synthetic_epsc
        fn = AnalysisRegistry.get_function("synaptic_charge")
        result = fn(data, t, fs, integration_start=0.0, integration_end=0.1)
        if "error" not in result:
            for key in ("_int_x", "_int_y", "_baseline", "_peak_t", "_peak_v"):
                assert key in result, f"Missing private plotting key '{key}'"
            assert len(result["_int_x"]) == len(result["_int_y"]), "_int_x and _int_y must have the same length"
            assert len(result["_int_x"]) == len(result["_baseline"]), "_int_x and _baseline must have the same length"
            assert len(result["_peak_t"]) == 1, "_peak_t must contain exactly one element"
            assert len(result["_peak_v"]) == 1, "_peak_v must contain exactly one element"

    def test_empty_data_returns_error(self, sc_module):
        """Empty array must return an error dict, not raise."""
        mod = sc_module
        result = mod.calculate_synaptic_charge(
            data=np.array([]),
            time=np.array([]),
            sampling_rate=10_000.0,
            integration_start=0.0,
            integration_end=0.1,
        )
        assert "error" in result, "Expected error dict for empty data"

    def test_inverted_window_returns_error(self, sc_module, synthetic_epsc):
        """integration_start >= integration_end must produce a graceful error."""
        mod = sc_module
        data, t, fs = synthetic_epsc
        result = mod.calculate_synaptic_charge(
            data=data,
            time=t,
            sampling_rate=fs,
            integration_start=0.2,
            integration_end=0.1,
        )
        assert "error" in result, "Expected error dict for inverted window"

    def test_narrow_window_returns_error(self, sc_module, synthetic_epsc):
        """A window containing fewer than 2 samples must produce a graceful error."""
        mod = sc_module
        data, t, fs = synthetic_epsc
        # Window so narrow it encloses at most one sample at 10 kHz
        result = mod.calculate_synaptic_charge(
            data=data,
            time=t,
            sampling_rate=fs,
            integration_start=0.05,
            integration_end=0.05 + 5e-6,  # 5 microseconds = 0.05 samples
        )
        assert "error" in result, "Expected error dict for sub-sample window"
