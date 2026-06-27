# tests/core/test_misc_coverage.py
# -*- coding: utf-8 -*-
"""
Coverage-boosting tests for various core modules.

Targets:
  templates/plugin_template.py:161 : wrapper calling calculate_my_metric
"""

from __future__ import annotations

import numpy as np

# ---------------------------------------------------------------------------
# plugin_template.run_my_custom_metric_wrapper — line 161
# ---------------------------------------------------------------------------


class TestPluginTemplateWrapper:
    def test_wrapper_calls_calculate_my_metric(self):
        """Line 161: run_my_custom_metric_wrapper delegates to calculate_my_metric."""
        import importlib
        import sys

        # Import the template module (it self-registers but that's OK)
        if "synaptipy.templates.plugin_template" in sys.modules:
            mod = sys.modules["synaptipy.templates.plugin_template"]
        else:
            mod = importlib.import_module("synaptipy.templates.plugin_template")

        wrapper = mod.run_my_custom_metric_wrapper

        data = np.array([-65.0, -64.5, -65.2, -63.8])
        time = np.linspace(0, 0.001, len(data))
        result = wrapper(data=data, time=time, sampling_rate=10_000.0)

        assert isinstance(result, dict)
        assert "Mean_Value" in result or "error" in result

    def test_wrapper_with_empty_data(self):
        """calculate_my_metric returns error dict for empty data."""
        import sys

        mod = sys.modules.get("synaptipy.templates.plugin_template")
        if mod is None:
            import importlib

            mod = importlib.import_module("synaptipy.templates.plugin_template")

        wrapper = mod.run_my_custom_metric_wrapper
        result = wrapper(data=np.array([]), time=np.array([]), sampling_rate=10_000.0)
        assert "error" in result


# ---------------------------------------------------------------------------
# cli/__init__.py — lines 10-11 (module-level __all__)
# ---------------------------------------------------------------------------


class TestCliInit:
    def test_cli_import_succeeds(self):
        """Importing the CLI subpackage must not raise."""
        import synaptipy.application.cli as cli  # noqa: F401

        assert hasattr(cli, "__all__")
        assert cli.__all__ == []


# ---------------------------------------------------------------------------
# epoch_manager.py — lines 281-291 (remove_epoch, clear)
# ---------------------------------------------------------------------------


class TestEpochManagerMutations:
    def _make_manager(self):
        from synaptipy.core.analysis.epoch_manager import EpochManager

        return EpochManager()

    def test_remove_epoch_existing_returns_true(self):
        mgr = self._make_manager()
        mgr.add_manual_epoch("stim", 0.1, 0.2)
        assert mgr.remove_epoch("stim") is True

    def test_remove_epoch_nonexistent_returns_false(self):
        mgr = self._make_manager()
        assert mgr.remove_epoch("ghost") is False

    def test_remove_epoch_case_insensitive(self):
        mgr = self._make_manager()
        mgr.add_manual_epoch("Stim", 0.1, 0.2)
        assert mgr.remove_epoch("stim") is True

    def test_clear_removes_all_epochs(self):
        mgr = self._make_manager()
        mgr.add_manual_epoch("a", 0.0, 0.1)
        mgr.add_manual_epoch("b", 0.2, 0.3)
        mgr.clear()
        assert mgr.epoch_names == []


# ---------------------------------------------------------------------------
# registry.py — lines 57-66 (collision: plugin shadows core analysis)
# ---------------------------------------------------------------------------


class TestRegistryCollision:
    def setup_method(self):
        from synaptipy.core.analysis.registry import AnalysisRegistry

        self._saved_registry = dict(AnalysisRegistry._registry)
        self._saved_metadata = dict(AnalysisRegistry._metadata)
        self._saved_original = dict(AnalysisRegistry._original_metadata)
        self._saved_core = set(AnalysisRegistry._core_analyses)
        AnalysisRegistry.clear()

    def teardown_method(self):
        from synaptipy.core.analysis.registry import AnalysisRegistry

        AnalysisRegistry.clear()
        AnalysisRegistry._registry.update(self._saved_registry)
        AnalysisRegistry._metadata.update(self._saved_metadata)
        AnalysisRegistry._original_metadata.update(self._saved_original)
        AnalysisRegistry._core_analyses = self._saved_core

    def test_plugin_collision_with_core_gets_suffixed(self):
        """Lines 57-66: plugin that shadows a core name is renamed."""
        from synaptipy.core.analysis.registry import AnalysisRegistry

        @AnalysisRegistry.register("core_analysis")
        def core_fn(**kwargs):
            return {}

        # Mark as core snapshot so the name is protected
        AnalysisRegistry.mark_core_snapshot()

        @AnalysisRegistry.register("core_analysis")
        def plugin_fn(**kwargs):
            return {}

        # The plugin must NOT replace the core; it gets a suffixed name
        assert "core_analysis" in AnalysisRegistry._registry
        assert AnalysisRegistry._registry["core_analysis"] is core_fn
        assert "core_analysis_1" in AnalysisRegistry._registry
        assert AnalysisRegistry._registry["core_analysis_1"] is plugin_fn

    def test_two_plugin_collisions_both_suffixed_incrementally(self):
        """Counter keeps incrementing on repeated collisions."""
        from synaptipy.core.analysis.registry import AnalysisRegistry

        @AnalysisRegistry.register("base")
        def fn_core(**kwargs):
            return {}

        AnalysisRegistry.mark_core_snapshot()

        @AnalysisRegistry.register("base")
        def fn_plugin1(**kwargs):
            return {}

        @AnalysisRegistry.register("base")
        def fn_plugin2(**kwargs):
            return {}

        assert "base_1" in AnalysisRegistry._registry
        assert "base_2" in AnalysisRegistry._registry
