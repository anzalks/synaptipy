# src/Synaptipy/templates/plugin_template.py
# -*- coding: utf-8 -*-
"""
Synaptipy Plugin Template - Copy, Customise, and Drop In.

HOW TO USE
----------
1. Copy this file to ``~/.synaptipy/plugins/``
   (on Windows: ``C:\\Users\\<you>\\.synaptipy\\plugins\\``)
2. Rename it to something descriptive, e.g. ``my_analysis.py``.
3. Implement your analysis logic in ``calculate_my_metric`` (Part 1).
4. Configure the decorator in Part 2 (name, label, ui_params, plots).
5. Ensure "Enable Custom Plugins" is checked in
   **Edit > Preferences > Extensions** (requires a restart).

Your analysis appears as a new tab in the Analyser automatically.
No other Synaptipy files need to be modified.

FULL EXAMPLES
-------------
- ``examples/plugins/opto_jitter.py``         - optogenetic latency jitter
- ``examples/plugins/ap_repolarization.py``   - max AP repolarization rate

DOCUMENTATION
-------------
- ``docs/extending_synaptipy.md``             - complete reference including
  all ui_params types and plot overlay types (markers, fill_between, etc.)

This file is part of Synaptipy, licensed under the GNU Affero General Public License v3.0.
See the LICENSE file in the root of the repository for full license details.
"""

import logging
from typing import Any, Dict

import numpy as np

from Synaptipy.core.analysis.registry import AnalysisRegistry

log = logging.getLogger(__name__)


# ============================================================
# PART 1 - PURE ANALYSIS LOGIC
# Write your algorithm here.  No GUI imports.  Just NumPy / SciPy.
# ============================================================


def calculate_my_metric(
    data: np.ndarray,
    time: np.ndarray,
    sampling_rate: float,
    # TODO: add parameters that match your ui_params names below
) -> Dict[str, Any]:
    """
    Replace this docstring and body with your own analysis logic.

    Args:
        data: 1-D NumPy array - the voltage (or current) trace for one sweep.
        time: 1-D NumPy array - time in seconds, same length as data.
        sampling_rate: Sampling rate in Hz.
        # TODO: document your additional parameters here.

    Returns:
        Dict with your results.  Keys become rows in the results table.
        Keys starting with ``_`` are hidden from the table (use for plot data).
        A key named ``"error"`` triggers an error message in the GUI.

        Recommended output schema::

            {
                "module_used": "my_custom_metric",   # module identifier
                "metrics": {"My_Value": 42.0},       # nested metrics dict
                "My_Value": 42.0,                    # flat key for table
                "_plot_x": [...],                    # hidden: plot data
                "_plot_y": [...],                    # hidden: plot data
            }
    """
    # TODO: implement your analysis here.
    if data.size == 0:
        return {"error": "Empty data array"}

    return {
        "module_used": "my_custom_metric",
        "metrics": {
            "Mean_Value": float(round(float(np.mean(data)), 4)),
        },
        "Mean_Value": float(round(float(np.mean(data)), 4)),
    }


# ============================================================
# PART 2 - REGISTRY WRAPPER
# Configure the decorator to define your tab name, parameters,
# and plot overlays.  The function body just calls Part 1.
# ============================================================


@AnalysisRegistry.register(
    name="my_custom_metric",  # CHANGE: unique internal name
    label="My Custom Metric",  # CHANGE: display name for the tab
    ui_params=[
        # CHANGE: define your parameter widgets here.
        # See docs/extending_synaptipy.md section 4 for all available types.
        {
            "name": "window_start",
            "label": "Window Start (s):",
            "type": "float",
            "default": 0.0,
            "min": 0.0,
            "max": 1e9,
            "decimals": 4,
        },
        {
            "name": "window_end",
            "label": "Window End (s):",
            "type": "float",
            "default": 0.5,
            "min": 0.0,
            "max": 1e9,
            "decimals": 4,
        },
    ],
    plots=[
        # CHANGE: define your plot overlays here.
        # See docs/extending_synaptipy.md section 5 for all overlay types.
        # Examples:
        #   {"type": "interactive_region", "data": ["window_start", "window_end"], "color": "g"}
        #   {"type": "markers", "x": "_peak_t", "y": "_peak_v", "color": "r"}
        #   {"type": "fill_between", "x": "_int_x", "y1": "_int_y", "y2": "_base"}
    ],
)
def run_my_custom_metric_wrapper(
    data: np.ndarray,
    time: np.ndarray,
    sampling_rate: float,
    **kwargs,
) -> Dict[str, Any]:
    """
    Registry wrapper - extracts GUI parameters and calls the logic function.

    The signature ``(data, time, sampling_rate, **kwargs)`` is fixed.
    CHANGE: update ``kwargs.get()`` calls to match your ui_params names.

    Global Themes
    -------------
    Synaptipy injects a ``theme_config`` dict into ``kwargs`` whenever the
    user changes plot-customisation settings (colours, line widths, etc.).
    Use it to tint your result overlays so they stay visually consistent::

        theme_config = kwargs.get("theme_config", {})
        trace_color = theme_config.get("single_trial_color", (200, 200, 200))
        avg_color   = theme_config.get("average_color", (255, 255, 0))

    The dict contains the same keys as
    :func:`~Synaptipy.shared.plot_customization.get_plot_customization_manager`
    properties (``single_trial_color``, ``average_color``, ``scatter_color``,
    ``line_width``, etc.).  If the key is absent, fall back to a sensible
    default so your plugin works even without custom styling.
    """
    return calculate_my_metric(
        data=data,
        time=time,
        sampling_rate=sampling_rate,
        # TODO: pass your ui_params kwargs here, e.g.:
        # window_start=kwargs.get("window_start", 0.0),
        # window_end=kwargs.get("window_end", 0.5),
    )
