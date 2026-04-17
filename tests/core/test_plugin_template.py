# tests/core/test_plugin_template.py
# -*- coding: utf-8 -*-
"""
Tests for the plugin template and the PluginManager loading mechanism.

Validates that:
1. The plugin template's logic function works correctly.
2. The plugin template can be loaded by PluginManager from a temp directory.
3. The loaded plugin registers correctly with AnalysisRegistry.
4. The registered wrapper function is callable and returns expected results.
5. The metadata (ui_params, plots, label) is correct.
6. Private keys (starting with '_') are present in results but excluded
   from the public-facing subset.
"""

import copy
import importlib
import shutil
import sys
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest

from Synaptipy.core.analysis.registry import AnalysisRegistry

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def isolate_registry():
    """Save and restore the registry around each test for isolation."""
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


@pytest.fixture
def synthetic_trace():
    """Generate a 1-second synthetic voltage trace at 10 kHz."""
    fs = 10_000.0
    t = np.arange(0, 1.0, 1.0 / fs)
    # First 0.1 s = baseline noise, rest = sine wave signal
    rng = np.random.default_rng(42)
    noise = rng.normal(0, 0.5, len(t))
    signal = np.sin(2 * np.pi * 10 * t) * 5.0
    data = noise.copy()
    data[1000:] += signal[1000:]
    return data, t, fs


@pytest.fixture
def plugin_dir(tmp_path):
    """
    Copy the plugin template to a temporary directory and return the path.
    Cleans up the module from sys.modules after the test.
    """
    template_src = Path(__file__).resolve().parents[2] / "src" / "Synaptipy" / "templates" / "plugin_template.py"
    assert template_src.exists(), f"Plugin template not found at {template_src}"

    dest = tmp_path / "plugins"
    dest.mkdir()
    shutil.copy(template_src, dest / "my_test_plugin.py")

    yield dest

    # Cleanup: remove any modules loaded from the temp dir
    to_remove = [k for k in sys.modules if k.startswith("synaptipy_plugin_")]
    for k in to_remove:
        del sys.modules[k]


# ---------------------------------------------------------------------------
# Tests — plugin template logic function
# ---------------------------------------------------------------------------


class TestPluginTemplateLogic:
    """Tests for the pure logic function in the plugin template."""

    def test_import_template_module(self):
        """The plugin template module can be imported directly."""
        spec = importlib.util.spec_from_file_location(
            "plugin_template",
            str(Path(__file__).resolve().parents[2] / "src" / "Synaptipy" / "templates" / "plugin_template.py"),
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        assert hasattr(mod, "calculate_my_metric")
        assert hasattr(mod, "run_my_custom_metric_wrapper")

    def test_logic_basic(self, synthetic_trace):
        """Logic function returns correct keys for a normal trace."""
        data, time, fs = synthetic_trace
        # Import the logic function
        spec = importlib.util.spec_from_file_location(
            "plugin_template_logic",
            str(Path(__file__).resolve().parents[2] / "src" / "Synaptipy" / "templates" / "plugin_template.py"),
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        result = mod.calculate_my_metric(
            data=data,
            time=time,
            sampling_rate=fs,
        )

        assert isinstance(result, dict)
        assert "Mean_Value" in result
        assert "module_used" in result
        assert "metrics" in result
        assert "error" not in result

    def test_logic_empty_data(self):
        """Logic function returns error dict for empty data."""
        spec = importlib.util.spec_from_file_location(
            "plugin_template_empty",
            str(Path(__file__).resolve().parents[2] / "src" / "Synaptipy" / "templates" / "plugin_template.py"),
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        result = mod.calculate_my_metric(
            data=np.array([]),
            time=np.array([]),
            sampling_rate=10000.0,
        )
        assert "error" in result

    def test_logic_mean_value_correct(self):
        """Logic function computes mean correctly for a simple array."""
        spec = importlib.util.spec_from_file_location(
            "plugin_template_mean",
            str(Path(__file__).resolve().parents[2] / "src" / "Synaptipy" / "templates" / "plugin_template.py"),
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        data = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        time = np.array([0.0, 0.1, 0.2, 0.3, 0.4])

        result = mod.calculate_my_metric(data=data, time=time, sampling_rate=10.0)
        assert "error" not in result
        assert abs(result["Mean_Value"] - 3.0) < 1e-6

    def test_public_keys_convention(self, synthetic_trace):
        """Result dict has at least one public key and the nested 'metrics' schema."""
        data, time, fs = synthetic_trace
        spec = importlib.util.spec_from_file_location(
            "plugin_template_keys",
            str(Path(__file__).resolve().parents[2] / "src" / "Synaptipy" / "templates" / "plugin_template.py"),
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        result = mod.calculate_my_metric(data=data, time=time, sampling_rate=fs)
        public_keys = [k for k in result if not k.startswith("_")]
        assert len(public_keys) >= 1, "Expected at least one public key"
        assert isinstance(result.get("metrics"), dict), "Expected nested 'metrics' dict"


# ---------------------------------------------------------------------------
# Tests — PluginManager loading
# ---------------------------------------------------------------------------


class TestPluginManagerLoading:
    """Tests for PluginManager discovering and loading the template."""

    def test_load_plugin_from_directory(self, plugin_dir, synthetic_trace):
        """
        PluginManager.load_plugins() loads the template from a custom dir
        and registers the analysis in AnalysisRegistry.
        """
        from Synaptipy.application.plugin_manager import PluginManager

        # Patch PLUGIN_DIR to point to our temp directory
        with patch("Synaptipy.application.plugin_manager.PLUGIN_DIR", plugin_dir):
            PluginManager.load_plugins()

        # The template registers "my_custom_metric"
        func = AnalysisRegistry.get_function("my_custom_metric")
        assert func is not None, (
            "Plugin was not registered. " f"Currently registered: {AnalysisRegistry.list_registered()}"
        )

    def test_loaded_plugin_metadata(self, plugin_dir):
        """Metadata (label, ui_params, plots) is correctly stored."""
        from Synaptipy.application.plugin_manager import PluginManager

        with patch("Synaptipy.application.plugin_manager.PLUGIN_DIR", plugin_dir):
            PluginManager.load_plugins()

        meta = AnalysisRegistry.get_metadata("my_custom_metric")
        assert meta.get("label") == "My Custom Metric"
        assert "ui_params" in meta
        assert "plots" in meta
        assert isinstance(meta["ui_params"], list)
        assert len(meta["ui_params"]) >= 2  # window_start, window_end

    def test_loaded_plugin_ui_param_types(self, plugin_dir):
        """All ui_params have valid type fields."""
        from Synaptipy.application.plugin_manager import PluginManager

        with patch("Synaptipy.application.plugin_manager.PLUGIN_DIR", plugin_dir):
            PluginManager.load_plugins()

        meta = AnalysisRegistry.get_metadata("my_custom_metric")
        valid_types = {"float", "int", "bool", "choice", "combo"}
        for param in meta["ui_params"]:
            assert "name" in param, f"ui_param missing 'name': {param}"
            assert "type" in param, f"ui_param missing 'type': {param}"
            assert param["type"] in valid_types, f"ui_param '{param['name']}' has invalid type '{param['type']}'"

    def test_loaded_plugin_callable(self, plugin_dir, synthetic_trace):
        """The registered wrapper function is callable and returns results."""
        from Synaptipy.application.plugin_manager import PluginManager

        with patch("Synaptipy.application.plugin_manager.PLUGIN_DIR", plugin_dir):
            PluginManager.load_plugins()

        func = AnalysisRegistry.get_function("my_custom_metric")
        data, time, fs = synthetic_trace

        result = func(data, time, fs, window_start=0.0, window_end=0.5)
        assert isinstance(result, dict)
        assert "Mean_Value" in result
        assert "error" not in result

    def test_loaded_plugin_plots_reference_valid_keys(self, plugin_dir, synthetic_trace):
        """
        Plot overlay data keys must either reference ui_param names
        (for interactive_region) or result-dict keys.
        """
        from Synaptipy.application.plugin_manager import PluginManager

        with patch("Synaptipy.application.plugin_manager.PLUGIN_DIR", plugin_dir):
            PluginManager.load_plugins()

        meta = AnalysisRegistry.get_metadata("my_custom_metric")
        func = AnalysisRegistry.get_function("my_custom_metric")
        data, time, fs = synthetic_trace

        result = func(data, time, fs, window_start=0.0, window_end=0.5, threshold=0.0)
        param_names = {p["name"] for p in meta["ui_params"]}
        result_keys = set(result.keys())

        for plot in meta.get("plots", []):
            plot_type = plot.get("type", "")
            data_ref = plot.get("data")
            if data_ref is None:
                continue

            if plot_type == "interactive_region":
                # Data keys must be param names
                if isinstance(data_ref, list):
                    for key in data_ref:
                        assert key in param_names, (
                            f"interactive_region references param '{key}' " f"not in ui_params: {param_names}"
                        )
            else:
                # Data keys must be result-dict keys
                refs = data_ref if isinstance(data_ref, list) else [data_ref]
                for key in refs:
                    assert key in result_keys, (
                        f"Plot type '{plot_type}' references result key '{key}' " f"not in result dict: {result_keys}"
                    )

    def test_no_plugins_does_not_crash(self, tmp_path):
        """Loading from an empty directory succeeds without errors."""
        from Synaptipy.application.plugin_manager import PluginManager

        empty_dir = tmp_path / "empty_plugins"
        empty_dir.mkdir()

        with patch("Synaptipy.application.plugin_manager.PLUGIN_DIR", empty_dir):
            PluginManager.load_plugins()  # should not raise

    def test_bad_plugin_does_not_crash(self, tmp_path):
        """A plugin with a syntax error is skipped gracefully."""
        from Synaptipy.application.plugin_manager import PluginManager

        bad_dir = tmp_path / "bad_plugins"
        bad_dir.mkdir()
        (bad_dir / "broken.py").write_text("def oops(\n")  # syntax error

        with patch("Synaptipy.application.plugin_manager.PLUGIN_DIR", bad_dir):
            PluginManager.load_plugins()  # should not raise

    def test_plugin_dir_creation(self, tmp_path):
        """PluginManager.create_plugin_directory() creates missing dirs."""
        from Synaptipy.application.plugin_manager import PluginManager

        new_dir = tmp_path / "new" / "plugin" / "path"
        assert not new_dir.exists()

        with patch("Synaptipy.application.plugin_manager.PLUGIN_DIR", new_dir):
            PluginManager.create_plugin_directory()

        assert new_dir.exists()


# ---------------------------------------------------------------------------
# Tests — wrapper signature and return-dict conventions
# ---------------------------------------------------------------------------


class TestWrapperConventions:
    """Verify the wrapper function follows the registry interface conventions."""

    def test_wrapper_signature(self, plugin_dir, synthetic_trace):
        """Wrapper accepts (data, time, sampling_rate, **kwargs)."""
        from Synaptipy.application.plugin_manager import PluginManager

        with patch("Synaptipy.application.plugin_manager.PLUGIN_DIR", plugin_dir):
            PluginManager.load_plugins()

        func = AnalysisRegistry.get_function("my_custom_metric")
        data, time, fs = synthetic_trace

        # Call with kwargs matching ui_params
        result = func(data, time, fs, window_start=0.0, window_end=1.0)
        assert isinstance(result, dict)

    def test_wrapper_defaults_work(self, plugin_dir, synthetic_trace):
        """Wrapper works with zero kwargs (uses defaults)."""
        from Synaptipy.application.plugin_manager import PluginManager

        with patch("Synaptipy.application.plugin_manager.PLUGIN_DIR", plugin_dir):
            PluginManager.load_plugins()

        func = AnalysisRegistry.get_function("my_custom_metric")
        data, time, fs = synthetic_trace

        result = func(data, time, fs)
        assert isinstance(result, dict)
        assert "error" not in result
