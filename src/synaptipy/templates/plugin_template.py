# src/synaptipy/templates/plugin_template.py
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
5. Enable "Enable Custom Plugins" in **Edit > Preferences > Extensions**
   (plugins reload in-process without restarting).

Your analysis appears as a sub-tab in the Analyser automatically.
No core Synaptipy files need to be modified.

FULL EXAMPLES
-------------
- ``examples/plugins/opto_jitter.py``                 - optogenetic / evoked latency jitter
- ``examples/plugins/synaptic_charge.py``             - postsynaptic charge (pC) & EPSP AUC (mV*ms)
- ``examples/plugins/miniml_integration.py``          - miniML deep-learning events
- ``examples/plugins/spike_interface_integration.py`` - SpikeInterface spike detection wrapper

DOCUMENTATION
-------------
- ``docs/extending_synaptipy.md``                     - complete reference including
  all ui_params types and plot overlay types (markers, fill_between, hlines, etc.)

This file is part of Synaptipy, licensed under the GNU Affero General Public License v3.0.
See the LICENSE file in the root of the repository for full license details.
"""

import logging
from typing import Any, Dict

import numpy as np

from synaptipy.core.analysis.registry import AnalysisRegistry

log = logging.getLogger(__name__)


# ============================================================
# PART 1 - PURE ANALYSIS LOGIC
# Write your algorithm here. No GUI imports; NumPy / SciPy only.
# ============================================================


def calculate_my_metric(
    data: np.ndarray,
    time: np.ndarray,
    sampling_rate: float,
) -> Dict[str, Any]:
    """
    Replace this docstring and body with your own analysis logic.

    Args:
        data: 1-D NumPy array - voltage or current trace for one sweep.
        time: 1-D NumPy array - time in seconds, same length as data.
        sampling_rate: Sampling rate in Hz.

    Returns:
        Flat dictionary of results. ``AnalysisRegistry.execute`` wraps this
        automatically into the versioned ``AnalysisResult`` schema for the GUI,
        batch engine, and exporters. Public keys appear in the results table;
        keys prefixed with ``_`` pass hidden array data to plot overlays; a key
        named ``"error"`` reports a graceful analysis error in the UI::

            {
                "My_Value": 42.0,
                "_plot_x": [...],
                "_plot_y": [...],
            }
    """
    if data.size == 0:
        return {"error": "Empty data array"}

    return {
        "Mean_Value": float(round(float(np.mean(data)), 4)),
    }


# ============================================================
# PART 2 - REGISTRY WRAPPER
# Configure the decorator to define your tab name, parameters,
# and plot overlays. The wrapper extracts kwargs and calls Part 1.
# ============================================================


@AnalysisRegistry.register(
    name="my_custom_metric",  # CHANGE: unique internal registry name
    label="My Custom Metric",  # CHANGE: display label in the Analyser UI
    expects_list=False,  # Set True only if your function consumes a list of sweeps
    ui_params=[
        # See docs/extending_synaptipy.md section 4 for all available widget types.
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
        # See docs/extending_synaptipy.md section 5 for all overlay types:
        #   {"type": "interactive_region", "data": ["window_start", "window_end"]}
        #   {"type": "markers", "x": "_peak_t", "y": "_peak_v", "color": "r"}
        #   {"type": "hlines", "data": ["Mean_Value"], "color": "b", "styles": ["dash"]}
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
    Update ``kwargs.get()`` calls to forward any custom ``ui_params`` names to
    your pure logic function.
    """
    _ = kwargs
    return calculate_my_metric(
        data=data,
        time=time,
        sampling_rate=sampling_rate,
    )
