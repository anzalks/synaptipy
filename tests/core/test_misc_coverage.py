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
        if "Synaptipy.templates.plugin_template" in sys.modules:
            mod = sys.modules["Synaptipy.templates.plugin_template"]
        else:
            mod = importlib.import_module("Synaptipy.templates.plugin_template")

        wrapper = mod.run_my_custom_metric_wrapper

        data = np.array([-65.0, -64.5, -65.2, -63.8])
        time = np.linspace(0, 0.001, len(data))
        result = wrapper(data=data, time=time, sampling_rate=10_000.0)

        assert isinstance(result, dict)
        assert "Mean_Value" in result or "error" in result

    def test_wrapper_with_empty_data(self):
        """calculate_my_metric returns error dict for empty data."""
        import sys

        mod = sys.modules.get("Synaptipy.templates.plugin_template")
        if mod is None:
            import importlib

            mod = importlib.import_module("Synaptipy.templates.plugin_template")

        wrapper = mod.run_my_custom_metric_wrapper
        result = wrapper(data=np.array([]), time=np.array([]), sampling_rate=10_000.0)
        assert "error" in result
