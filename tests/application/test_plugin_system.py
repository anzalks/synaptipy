# tests/application/test_plugin_system.py
# -*- coding: utf-8 -*-
"""
Test suite for the Synaptipy plugin system integration.

Validates:
1. PluginManager.load_plugins() is a no-op when the ``enable_plugins``
   QSettings key is ``False``.
2. PluginManager.load_plugins() discovers and loads bundled example plugins
   (opto_jitter, synaptic_charge, miniml_events, spike_interface_detection)
   when ``enable_plugins`` is ``True``.
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

from synaptipy.core.analysis.registry import AnalysisRegistry

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
def miniml_module():
    """Load miniml_integration example plugin."""
    path = EXAMPLES_PLUGIN_DIR / "miniml_integration.py"
    assert path.exists(), f"miniml_integration.py not found at {path}"
    return _load_module(path, "synaptipy_plugin_miniml_integration")


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
        from synaptipy.application.plugin_manager import PluginManager

        before = dict(AnalysisRegistry._registry)

        with (
            patch(
                "synaptipy.application.plugin_manager._get_bundled_plugin_dir",
                return_value=EXAMPLES_PLUGIN_DIR,
            ),
            patch("synaptipy.application.plugin_manager.PLUGIN_DIR", _FAKE_USER_DIR),
            patch("synaptipy.application.plugin_manager.QSettings") as mock_settings_cls,
        ):
            mock_settings_cls.return_value.value.return_value = False
            PluginManager.load_plugins()

        after = dict(AnalysisRegistry._registry)
        # Registry must not have grown - no new plugins should be registered.
        new_keys = set(after) - set(before)
        assert not new_keys, f"Plugins were loaded despite enable_plugins=False: {new_keys}"

    def test_plugin_manager_uses_canonical_settings_namespace(self):
        """Plugin discovery must read the same store shown by Preferences."""
        from synaptipy.application.plugin_manager import _get_settings
        from synaptipy.shared.constants import APP_NAME, SETTINGS_SECTION

        settings = _get_settings()
        assert settings.organizationName() == APP_NAME
        assert settings.applicationName() == SETTINGS_SECTION

    def test_loads_plugins_when_enabled(self):
        """load_plugins() registers bundled plugins when enable_plugins=True."""
        from synaptipy.application.plugin_manager import PluginManager

        with (
            patch(
                "synaptipy.application.plugin_manager._get_bundled_plugin_dir",
                return_value=EXAMPLES_PLUGIN_DIR,
            ),
            patch("synaptipy.application.plugin_manager.PLUGIN_DIR", _FAKE_USER_DIR),
            patch("synaptipy.application.plugin_manager.QSettings") as mock_settings_cls,
        ):
            mock_settings_cls.return_value.value.return_value = True
            PluginManager.load_plugins()

        for expected_key in ("opto_jitter", "synaptic_charge", "miniml_events", "spike_interface_detection"):
            assert (
                AnalysisRegistry.get_function(expected_key) is not None
            ), f"{expected_key} not registered after load with enable_plugins=True"
        assert AnalysisRegistry.get_function("ap_repolarization") is None

    def test_failed_plugin_rolls_back_partial_registration(self, tmp_path):
        """A plugin that raises after registering must not leave an unsafe analysis visible."""
        from synaptipy.application.plugin_manager import PluginManager

        plugin_path = tmp_path / "partially_broken.py"
        plugin_path.write_text(
            "from synaptipy.core.analysis.registry import AnalysisRegistry\n"
            "@AnalysisRegistry.register('partial_failure_test')\n"
            "def partial(data, time, sampling_rate, **kwargs):\n"
            "    return {}\n"
            "raise RuntimeError('plugin setup failed')\n",
            encoding="utf-8",
        )
        empty_user_dir = tmp_path / "no_user_plugins"

        with (
            patch("synaptipy.application.plugin_manager._get_bundled_plugin_dir", return_value=tmp_path),
            patch("synaptipy.application.plugin_manager.PLUGIN_DIR", empty_user_dir),
            patch("synaptipy.application.plugin_manager.QSettings") as mock_settings_cls,
        ):
            mock_settings_cls.return_value.value.return_value = True
            failures = PluginManager.load_plugins()

        assert len(failures) == 1
        assert AnalysisRegistry.get_function("partial_failure_test") is None

    def test_reload_disabled_preserves_core_registry_entries(self):
        """Disabling extensions must never unregister built-in analyses."""
        from synaptipy.application.plugin_manager import PluginManager

        original_registry = dict(AnalysisRegistry._registry)
        original_metadata = dict(AnalysisRegistry._metadata)
        original_defaults = dict(AnalysisRegistry._original_metadata)
        original_core = set(AnalysisRegistry._core_analyses)
        try:
            AnalysisRegistry.clear()

            @AnalysisRegistry.register("core_for_reload_test")
            def core_analysis(data, time, sampling_rate, **kwargs):
                return {}

            AnalysisRegistry.mark_core_snapshot()

            @AnalysisRegistry.register("plugin_for_reload_test")
            def plugin_analysis(data, time, sampling_rate, **kwargs):
                return {}

            with patch("synaptipy.application.plugin_manager.QSettings") as mock_settings_cls:
                mock_settings_cls.return_value.value.return_value = False
                assert PluginManager.reload_plugins() == []

            assert AnalysisRegistry.get_function("core_for_reload_test") is core_analysis
            assert AnalysisRegistry.get_function("plugin_for_reload_test") is None
        finally:
            AnalysisRegistry._registry = original_registry
            AnalysisRegistry._metadata = original_metadata
            AnalysisRegistry._original_metadata = original_defaults
            AnalysisRegistry._core_analyses = original_core


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
        from synaptipy.application.plugin_manager import PluginManager  # noqa: F401

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
# Tests: miniml_events units and unconfigured guidance
# ---------------------------------------------------------------------------


class TestMiniMLPluginUX:
    """Validate miniML channel unit compatibility and unconfigured setup prompt."""

    def test_supports_both_current_and_voltage_channels(self, miniml_module):
        """miniML must accept both voltage-clamp (pA/nA) and current-clamp (mV/V/uV) channels."""
        meta = AnalysisRegistry.get_metadata("miniml_events")
        units = set(meta.get("supported_channel_units", ()))
        assert {"pA", "nA", "mV", "V", "uV"}.issubset(units)

    def test_unconfigured_paths_raise_analysis_not_configured(self, miniml_module):
        """Missing core/model paths raise AnalysisNotConfigured instead of returning a red error."""
        from synaptipy.application.gui.analysis_tabs.base import AnalysisNotConfigured

        fn = AnalysisRegistry.get_function("miniml_events")
        assert fn is not None
        with pytest.raises(AnalysisNotConfigured, match="miniML Events needs"):
            fn(np.zeros(200), np.arange(200) * 1e-4, 10_000.0)

    def test_repo_root_resolution_and_baseline_subtracted_event_stats(self, miniml_module, tmp_path):
        """miniML resolves repo_root/core, uses event_peak_locations + event_stats.amplitudes, and labels units."""
        repo_root = tmp_path / "miniML_repo"
        core_dir = repo_root / "core"
        core_dir.mkdir(parents=True)
        model_file = repo_root / "GC_mEPSP.h5"
        model_file.write_bytes(b"H5")
        (core_dir / "miniML.py").write_text(
            "import numpy as np\n"
            "class MiniTrace:\n"
            "    def __init__(self, data, sampling_interval=1.0, y_unit=''):\n"
            "        self.data = data\n"
            "class _Stats:\n"
            "    amplitudes = np.array([0.65, 0.45])\n"
            "    risetimes = np.array([0.0012, 0.0016])\n"
            "    halfdecays = np.array([0.0090, 0.0110])\n"
            "class EventDetection:\n"
            "    def __init__(self, **kw):\n"
            "        self.kw = kw\n"
            "    def detect_events(self, **dkw):\n"
            "        self.dkw = dkw\n"
            "        self.event_locations = np.array([100, 500])\n"
            "        self.event_peak_locations = np.array([115, 520])\n"
            "        self.event_scores = np.array([0.92, 0.88])\n"
            "        self.event_stats = _Stats()\n",
            encoding="utf-8",
        )
        fs = 20_000.0
        t = np.arange(1000) / fs
        v = np.full(1000, -65.0)
        v[115] = -64.35
        v[520] = -64.55

        saved_path = list(sys.path)
        try:
            with patch.object(miniml_module, "_save_miniml_paths"):
                res = miniml_module.run_miniml_events_wrapper(
                    v,
                    t,
                    fs,
                    miniml_core_path=str(repo_root),  # Repo root auto-resolves to repo_root/core!
                    model_path=str(model_file),
                    direction="positive",
                    channel_units="mV",
                )
        finally:
            sys.path[:] = saved_path
            sys.modules.pop("miniML", None)

        assert res["module_used"] == "miniml_events"
        m = res["metrics"]
        assert m["Event_Count"] == 2
        # Must report true baseline-subtracted amplitude (~0.55 mV), NOT resting potential (-64.45 mV)!
        assert m["Mean_Amplitude_mV"] == pytest.approx(0.55, abs=1e-4)
        assert m["Mean_Rise_Time_ms"] == pytest.approx(1.4, abs=1e-4)
        assert m["Mean_Half_Decay_ms"] == pytest.approx(10.0, abs=1e-4)
        # Markers still sit on the raw DC-offset trace (-64.35, -64.55 mV) at exact event_peak_locations
        assert res["_event_times"] == pytest.approx([115 / fs, 520 / fs])
        assert res["_event_peaks"] == pytest.approx([-64.35, -64.55])


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

        result = fn(data, t, fs, window_start=0.0, window_end=0.1)

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
        result = fn(data, t, fs, window_start=0.0, window_end=0.1)
        if "error" not in result:
            assert result["metrics"]["Charge_pC"] < 0.0, "Charge must be negative for an inward current"

    def test_peak_amp_is_negative_for_inward_current(self, sc_module, synthetic_epsc):
        """Peak amplitude must be negative for an inward EPSC."""
        data, t, fs = synthetic_epsc
        fn = AnalysisRegistry.get_function("synaptic_charge")
        result = fn(data, t, fs, window_start=0.0, window_end=0.1)
        if "error" not in result:
            assert result["metrics"]["Peak_Amp"] < 0.0, "Peak_Amp must be negative for an inward current"

    def test_private_plotting_keys_present(self, sc_module, synthetic_epsc):
        """Hidden keys required by fill_between and markers overlays must be present."""
        data, t, fs = synthetic_epsc
        fn = AnalysisRegistry.get_function("synaptic_charge")
        result = fn(data, t, fs, window_start=0.0, window_end=0.1)
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
            window_start=0.0,
            window_end=0.1,
        )
        assert "error" in result, "Expected error dict for empty data"

    def test_inverted_window_returns_error(self, sc_module, synthetic_epsc):
        """window_start >= window_end must produce a graceful error."""
        mod = sc_module
        data, t, fs = synthetic_epsc
        result = mod.calculate_synaptic_charge(
            data=data,
            time=t,
            sampling_rate=fs,
            window_start=0.2,
            window_end=0.1,
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
            window_start=0.05,
            window_end=0.05 + 5e-6,  # 5 microseconds = 0.05 samples
        )
        assert "error" in result, "Expected error dict for sub-sample window"

    def test_current_clamp_mv_epsp_auc_and_na_scaling(self, sc_module):
        """Voltage traces (mV) report EPSP AUC (mV*ms / mV*s), and nA traces scale Charge_pC by 1000x."""
        fn = AnalysisRegistry.get_function("synaptic_charge")
        fs = 20_000.0
        t = np.arange(0.0, 1.0, 1.0 / fs)

        # Depolarizing EPSP on a -65.5 mV resting baseline: +7.0 mV rectangular pulse of 20 ms -> 140 mV*ms
        v_trace = np.full_like(t, -65.5)
        v_trace[(t >= 0.200) & (t < 0.220)] += 7.0
        res_mv = fn(
            v_trace,
            t,
            fs,
            window_start=0.195,
            window_end=0.240,
            detection_method="Positive Peak",
            channel_units="mV",
        )
        assert "error" not in res_mv
        assert res_mv["metrics"]["AUC (mV*ms)"] == pytest.approx(140.0, rel=0.03)
        assert res_mv["metrics"]["AUC (mV*s)"] == pytest.approx(0.140, rel=0.03)
        assert res_mv["metrics"]["Baseline_mV"] == pytest.approx(-65.5, abs=1e-3)
        assert res_mv["metrics"]["_baseline_level"] == pytest.approx(-65.5, abs=1e-3)

        # Inward EPSC recorded in nA: -0.5 nA (-500 pA) for 10 ms -> -5.0 pC
        i_na = np.zeros_like(t)
        i_na[(t >= 0.200) & (t < 0.210)] = -0.5
        res_na = fn(i_na, t, fs, window_start=0.195, window_end=0.230, channel_units="nA")
        assert "error" not in res_na
        assert res_na["metrics"]["Charge_pC"] == pytest.approx(-5.0, rel=0.03)
        assert res_na["metrics"]["_baseline_level"] == pytest.approx(0.0, abs=1e-6)


class TestPluginDownloaderOfflineFallback:
    """Verify PluginDownloader cleans up retired plugins and falls back to bundled plugins offline."""

    def test_offline_fallback_copies_bundled_plugins_and_removes_retired(self, tmp_path):
        from synaptipy.application.gui.welcome_screen import _PLUGIN_FILES, PluginDownloader

        dest_dir = tmp_path / "user_plugins"
        dest_dir.mkdir()
        retired = dest_dir / "ap_repolarization.py"
        retired.write_text('"""Plugin: Maximum Action Potential Repolarization Rate."""\n', encoding="utf-8")

        dl = PluginDownloader()
        with (
            patch.object(dl, "_do_download", return_value="Network error: offline"),
            patch(
                "synaptipy.application.plugin_manager._get_bundled_plugin_dir",
                return_value=EXAMPLES_PLUGIN_DIR,
            ),
        ):
            out_dir, err = dl._download_all(dest_dir)

        assert err is None
        assert out_dir == dest_dir
        assert not retired.exists(), "Retired ap_repolarization.py should be removed on plugin refresh"
        for fname in _PLUGIN_FILES:
            assert (dest_dir / fname).is_file(), f"Missing fallback-copied plugin {fname}"

    def test_offline_without_bundled_dir_reports_error(self, tmp_path):
        from synaptipy.application.gui.welcome_screen import PluginDownloader

        dest_dir = tmp_path / "user_plugins_empty"
        dest_dir.mkdir()
        dl = PluginDownloader()
        with (
            patch.object(dl, "_do_download", return_value="Network error: offline"),
            patch("synaptipy.application.plugin_manager._get_bundled_plugin_dir", return_value=None),
        ):
            out_dir, err = dl._download_all(dest_dir)

        assert out_dir is None
        assert err == "Network error: offline"
