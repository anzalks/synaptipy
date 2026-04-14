# Writing Custom Analysis Plugins for Synaptipy

This guide explains how to add your own analysis function to Synaptipy as a new
tab in the Analyser — **without modifying any Synaptipy source code**.  You write
a single Python file, drop it in a folder, and your analysis appears in the GUI
and batch engine the next time the application starts.

---

## Table of Contents

1. [Overview — How the Plugin System Works](#1-overview--how-the-plugin-system-works)
2. [Quick Start — Your First Plugin in 5 Minutes](#2-quick-start--your-first-plugin-in-5-minutes)
3. [The Plugin File — Anatomy of a Custom Analysis](#3-the-plugin-file--anatomy-of-a-custom-analysis)
   - [3.1 Part 1: Pure Analysis Logic](#31-part-1-pure-analysis-logic)
   - [3.2 Part 2: Registry Wrapper](#32-part-2-registry-wrapper)
   - [3.3 Return Dict Conventions](#33-return-dict-conventions)
4. [Defining GUI Parameters (`ui_params`)](#4-defining-gui-parameters-ui_params)
   - [4.1 `float` Parameter](#41-float-parameter)
   - [4.2 `int` Parameter](#42-int-parameter)
   - [4.3 `choice` / `combo` Parameter](#43-choice--combo-parameter)
   - [4.4 `bool` Parameter](#44-bool-parameter)
   - [4.5 Common Optional Fields](#45-common-optional-fields)
   - [4.6 Conditional Visibility (`visible_when`)](#46-conditional-visibility-visible_when)
5. [Defining Plot Overlays (`plots`)](#5-defining-plot-overlays-plots)
   - [5.1 `hlines` — Horizontal Lines](#51-hlines--horizontal-lines)
   - [5.2 `vlines` — Vertical Lines](#52-vlines--vertical-lines)
   - [5.3 `markers` — Scatter Points](#53-markers--scatter-points)
   - [5.4 `interactive_region` — Draggable Region](#54-interactive_region--draggable-region)
   - [5.5 `threshold_line` — Draggable Threshold](#55-threshold_line--draggable-threshold)
   - [5.6 `overlay_fit` — Curve Overlay](#56-overlay_fit--curve-overlay)
   - [5.7 `popup_xy` — Popup Scatter/Line Plot](#57-popup_xy--popup-scatterline-plot)
   - [5.8 `brackets` — Burst/Event Brackets](#58-brackets--burstevent-brackets)
   - [5.9 `event_markers` — Interactive Event Points](#59-event_markers--interactive-event-points)
   - [5.10 `trace` — Base Trace with Overlay](#510-trace--base-trace-with-overlay)
   - [5.11 `fill_between` — Shaded Region Between Two Curves](#511-fill_between--shaded-region-between-two-curves)
6. [Where to Put Your Plugin File](#6-where-to-put-your-plugin-file)
7. [For Core Contributors — Adding a Built-in Analysis](#7-for-core-contributors--adding-a-built-in-analysis)
8. [Testing Your Plugin](#8-testing-your-plugin)
9. [Full Annotated Example — Synaptic Charge Transfer](#9-full-annotated-example--synaptic-charge-transfer)
10. [Troubleshooting](#10-troubleshooting)

---

## 1. Overview — How the Plugin System Works

Synaptipy has a central **`AnalysisRegistry`** — a Python class that maps named
analysis functions to the GUI and batch engine.  You register a function by
decorating it with `@AnalysisRegistry.register(...)`.  The decorator stores the
function and its metadata (parameter definitions, plot overlays, label, etc.).

At startup, Synaptipy:

1. Loads all **built-in** analyses from `src/Synaptipy/core/analysis/`.
2. Scans **two** plugin directories in order:
   - `examples/plugins/` inside the Synaptipy installation — shipped example
     plugins that work out-of-the-box without any extra setup.
   - `~/.synaptipy/plugins/` — your personal or third-party additions.
   If a file with the same stem name exists in both directories, the user copy
   takes precedence and a warning is written to the log.
3. Builds the Analyser GUI.  For every registered analysis that does *not*
   already have a hand-coded tab class, a **metadata-driven tab is created
   automatically** — complete with parameter widgets, a Run button, a results
   table, and plot overlays.  Your function appears as a new sub-tab.

```
┌──────────────────────────────────────────────────────────┐
│  ~/.synaptipy/plugins/my_snr_analysis.py                 │
│                                                          │
│  @AnalysisRegistry.register(                             │
│      name="snr_analysis",                                │
│      label="Signal-to-Noise Ratio",                      │
│      ui_params=[...],                                    │
│      plots=[...]                                         │
│  )                                                       │
│  def run_snr(data, time, sampling_rate, **kwargs):        │
│      ...                                                 │
│      return {"module_used": "snr_analysis",              │
│              "metrics": {"snr_db": 42.3,                 │
│                          "noise_rms": 0.15}}             │
└──────────────────────────────────────────────────────────┘
         │
         ▼ startup → PluginManager.load_plugins()
┌──────────────────────────────────────────────────────────┐
│  AnalysisRegistry                                        │
│  ├── rmp_analysis          (built-in)                    │
│  ├── spike_detection       (built-in)                    │
│  ├── ...                                                 │
│  └── snr_analysis          ← YOUR PLUGIN                 │
└──────────────────────────────────────────────────────────┘
         │
         ▼ GUI build → auto-generated MetadataDrivenAnalysisTab
┌──────────────────────────────────────────────────────────┐
│  Analyser Tab:  ... | Baseline | Spikes | SNR ◄──────── │
│  ┌────────────────────────────────────────────┐          │
│  │ Noise Window Start (s):  [0.0        ]     │          │
│  │ Noise Window End (s):    [0.1        ]     │          │
│  │           [ ▶ Run Analysis ]               │          │
│  │ ──────────────────────────────────────      │          │
│  │ Results: SNR = 42.3 dB                     │          │
│  └────────────────────────────────────────────┘          │
└──────────────────────────────────────────────────────────┘
```

**You do not need to write any GUI code.** The `ui_params` list generates the
parameter widgets, and the `plots` list generates the plot overlays — all from
metadata.

---

## 2. Quick Start — Your First Plugin in 5 Minutes

1. Copy the template:
   ```bash
   # macOS / Linux
   cp src/Synaptipy/templates/plugin_template.py ~/.synaptipy/plugins/my_analysis.py

   # Windows (PowerShell)
   Copy-Item src\Synaptipy\templates\plugin_template.py ~\.synaptipy\plugins\my_analysis.py
   ```
   The plugin directory is created automatically the first time Synaptipy runs.
   If it does not exist yet, create it manually:
   - macOS / Linux: `mkdir -p ~/.synaptipy/plugins`
   - Windows (PowerShell): `New-Item -ItemType Directory -Force "$HOME\.synaptipy\plugins"`

   > **Where is the plugins folder?**
   >
   > | Platform | Path |
   > |----------|------|
   > | macOS / Linux | `~/.synaptipy/plugins/` |
   > | Windows | `C:\Users\<YourUsername>\.synaptipy\plugins\` |
   >
   > On Windows you can open it by typing `%USERPROFILE%\.synaptipy\plugins`
   > in the File Explorer address bar.

2. Open the copied file in any editor.

3. Rename the function, change the `name=` and `label=`, adjust the `ui_params`
   and `plots` lists, and write your analysis logic.

4. (Re)start Synaptipy.  Your analysis appears as a new tab in the Analyser.

No `pip install`, no editing `__init__.py`, no rebuilding — just save and restart.

---

## 3. The Plugin File — Anatomy of a Custom Analysis

A plugin file has two parts:

### 3.1 Part 1: Pure Analysis Logic

A regular Python function with explicit typed arguments and a return value.
No GUI dependencies (no PySide6, no pyqtgraph).

```python
import numpy as np

def calculate_snr(
    data: np.ndarray,
    sampling_rate: float,
    noise_start: float,
    noise_end: float,
    signal_start: float,
    signal_end: float,
) -> dict:
    """Calculate signal-to-noise ratio in decibels."""
    # ... your NumPy / SciPy logic ...
    return {"snr_db": snr, "noise_rms": noise_rms, "signal_rms": signal_rms}
```

**Rules for the logic function:**

- Takes explicit, typed arguments — no `**kwargs`.
- Returns a typed result object or a plain dict.
- Must handle edge cases (empty data, bad windows) gracefully.
- Must not import any GUI modules.

### 3.2 Part 2: Registry Wrapper

A thin wrapper decorated with `@AnalysisRegistry.register(...)`.  It extracts
parameters from `kwargs`, calls your logic function, and returns a dict that
follows the **nested output schema**.

```python
from Synaptipy.core.analysis.registry import AnalysisRegistry

@AnalysisRegistry.register(
    name="snr_analysis",              # unique internal name
    label="Signal-to-Noise Ratio",    # display name in the tab
    ui_params=[...],                  # parameter widgets (see §4)
    plots=[...],                      # plot overlays (see §5)
)
def run_snr_wrapper(
    data: np.ndarray,
    time: np.ndarray,
    sampling_rate: float,
    **kwargs,
) -> dict:
    """Registry wrapper for SNR analysis."""
    noise_start = kwargs.get("noise_start", 0.0)
    noise_end = kwargs.get("noise_end", 0.1)
    signal_start = kwargs.get("signal_start", 0.1)
    signal_end = kwargs.get("signal_end", 0.5)

    result = calculate_snr(data, sampling_rate, noise_start, noise_end,
                           signal_start, signal_end)

    if "error" in result:
        return result  # propagate error dict unchanged

    return {
        "module_used": "snr_analysis",
        "metrics": {
            "snr_db": result["snr_db"],
            "noise_rms": result["noise_rms"],
            "signal_rms": result["signal_rms"],
        },
    }
```

**The wrapper signature is fixed:**

```python
def wrapper(data: np.ndarray, time: np.ndarray, sampling_rate: float, **kwargs) -> Dict[str, Any]
```

| Parameter | Type | Description |
|---|---|---|
| `data` | `np.ndarray` | 1-D voltage/current trace for the selected sweep |
| `time` | `np.ndarray` | 1-D time array in seconds, same length as `data` |
| `sampling_rate` | `float` | Sampling rate in Hz |
| `**kwargs` | | All `ui_params` values, keyed by their `"name"` field |

### 3.3 Return Dict Conventions

Wrappers **must** return a `Dict[str, Any]` using the nested output schema:

```python
{
    "module_used": "my_plugin_name",   # string identifying the source module
    "metrics": {                       # all scalar results go here
        "MyMetric1": 1.0,
        "MyMetric2": 42,
    },
    # optional private keys for plot overlays (hidden from results table):
    "_fit_curve": np.array(...),
    "_event_indices": [...],
}
```

The `metrics` dict drives the results table and batch CSV columns.  Any key
in `metrics` appears as a column header; any value that is a number is
written to the CSV.

| Convention | Behaviour |
|---|---|
| `"module_used"` | Identifies the source; used by the batch engine to route results to the correct CSV file. |
| Keys inside `"metrics"` | Displayed in the results table and exported to CSV.  Use plain, human-readable names. |
| Keys starting with `_` at the **top level** | **Hidden** from the results table.  Use for arrays passed to plot overlays (e.g. `"_fit_curve"`, `"_event_indices"`). |
| Key named `"error"` at the top level | If present, the GUI shows an error message instead of results. |
| Numeric values in `metrics` (`int`, `float`) | Displayed as-is in the results table. |
| `np.ndarray` values in `metrics` | Displayed as shape summary (e.g. `"array(150,)"`). |
| `None` values in `metrics` | Displayed as `"N/A"`. |

---

## 4. Defining GUI Parameters (`ui_params`)

The `ui_params` list in `@AnalysisRegistry.register(...)` defines the parameter
widgets that appear in your tab.  Each entry is a dict describing one widget.

### 4.1 `float` Parameter

Creates a double-precision spin box.

```python
{
    "name": "threshold",          # kwarg name passed to your wrapper
    "label": "Threshold (mV):",   # label text shown in the GUI
    "type": "float",
    "default": -20.0,             # initial value (default: 0.0)
    "min": -200.0,                # minimum allowed (default: -1e9)
    "max": 200.0,                 # maximum allowed (default: 1e9)
    "decimals": 2,                # decimal places (default: 4)
    "step": 0.5,                  # step increment (optional)
}
```

### 4.2 `int` Parameter

Creates an integer spin box.

```python
{
    "name": "min_spikes",
    "label": "Min Spikes:",
    "type": "int",
    "default": 3,
    "min": 1,
    "max": 10000,
}
```

### 4.3 `choice` / `combo` Parameter

Creates a drop-down combo box.

```python
{
    "name": "direction",
    "label": "Detection Direction:",
    "type": "choice",             # "combo" also works
    "choices": ["negative", "positive", "both"],
    "default": "negative",        # pre-selected option
}
```

> **Note:** You can use `"options"` instead of `"choices"` — both keys are accepted.

### 4.4 `bool` Parameter

Creates a check box.

```python
{
    "name": "auto_detect",
    "label": "Auto-Detect Baseline",
    "type": "bool",
    "default": False,
}
```

### 4.5 Common Optional Fields

These fields work on any parameter type:

| Field | Type | Description |
|---|---|---|
| `"tooltip"` | `str` | Tooltip text shown on hover. |
| `"hidden"` | `bool` | If `True`, the widget is not created at all.  Use for internal params that should not be user-editable. |
| `"visible_when"` | `dict` | Conditional visibility — see below. |

### 4.6 Conditional Visibility (`visible_when`)

Show or hide a parameter widget based on the current value of another widget.

**Example:** Show `"spike_threshold"` only when `"event_type"` is set to
`"Spikes"`:

```python
ui_params=[
    {"name": "event_type", "type": "choice", "choices": ["Spikes", "EPSCs"],
     "label": "Event Type:", "default": "Spikes"},

    {"name": "spike_threshold", "type": "float", "default": -20.0,
     "label": "Spike Threshold (mV):",
     "visible_when": {"param": "event_type", "value": "Spikes"}},

    {"name": "epsc_threshold", "type": "float", "default": -5.0,
     "label": "EPSC Threshold (pA):",
     "visible_when": {"param": "event_type", "value": "EPSCs"}},
]
```

The `"param"` key names the sibling widget; `"value"` is the value that makes
this widget visible.  When the controlling widget changes, visibility updates
automatically.

There is also a `"context"` form for clamp-mode-aware parameters:

```python
"visible_when": {"context": "clamp_mode", "value": "current_clamp"}
```

---

## 5. Defining Plot Overlays (`plots`)

The `plots` list in `@AnalysisRegistry.register(...)` defines visual overlays
rendered on the data trace after analysis completes.  Each entry is a dict.

### 5.1 `hlines` — Horizontal Lines

Draw horizontal lines at y-positions taken from the result dict.

```python
{"type": "hlines", "data": ["threshold"], "color": "r", "styles": ["dash"]}
{"type": "hlines", "data": ["mean", "mean_plus_sd", "mean_minus_sd"],
 "color": "b", "styles": ["solid", "dash", "dash"]}
```

| Field | Description |
|---|---|
| `data` | List of result-dict keys.  Each key's value → one horizontal line. |
| `color` | Line colour (default `"r"`). |
| `styles` | List of `"solid"` or `"dash"`, one per key (default: all `"solid"`). |

### 5.2 `vlines` — Vertical Lines

Draw vertical lines at x-positions.

```python
{"type": "vlines", "data": "stimulus_times", "color": "c"}
```

| Field | Description |
|---|---|
| `data` | Result-dict key holding a scalar or array of x-positions. |
| `color` | Line colour (default `"b"`). |

### 5.3 `markers` — Scatter Points

Draw scatter points at (x, y) positions from result arrays.

```python
{"type": "markers", "x": "peak_times", "y": "peak_values", "color": "r"}
```

### 5.4 `interactive_region` — Draggable Region

A shaded region linked to two float spinboxes.  Dragging the region updates the
spinbox values, and changing a spinbox moves the region.

```python
{"type": "interactive_region", "data": ["window_start", "window_end"], "color": "g"}
```

`"data"` must be a 2-element list of `ui_params` names (not result keys).

### 5.5 `threshold_line` — Draggable Threshold

A horizontal line synced to a float parameter widget.

```python
{"type": "threshold_line", "param": "threshold"}
```

### 5.6 `overlay_fit` — Curve Overlay

Overlay a fitted curve on the trace.

```python
{
    "type": "overlay_fit",
    "x": "_fit_time",           # result key (use _ prefix to hide from table)
    "y": "_fit_values",
    "color": "r",
    "width": 2,
    "label": "Exponential Fit",
}
```

### 5.7 `popup_xy` — Popup Scatter/Line Plot

Open a separate window showing e.g. an I-V or F-I curve.

```python
{
    "type": "popup_xy",
    "title": "F-I Curve",
    "x": "current_steps_pa",
    "y": "firing_rates_hz",
    "x_label": "Current (pA)",
    "y_label": "Firing Rate (Hz)",
}
```

Optionally add `"slope_key"` and `"intercept_key"` for a regression line.

### 5.8 `brackets` — Burst/Event Brackets

Draw bracket bars above burst groups.

```python
{"type": "brackets", "data": "bursts", "color": "r"}
```

`"data"` key should hold a list of arrays (each array = spike times within one
burst).

### 5.9 `event_markers` — Interactive Event Points

Scatter plot with click-to-remove and Ctrl+click-to-add.

```python
{"type": "event_markers"}
```

Reads `result["event_indices"]` automatically.

### 5.10 `trace` — Base Trace with Overlay

Plot the trace with optional spike/event markers.

```python
{"type": "trace", "show_spikes": True}
```

### 5.11 `fill_between` — Shaded Region Between Two Curves

Draw a translucent filled area between a primary curve (`y1`) and a baseline
curve or constant (`y2`).  This is ideal for visualising integrated areas such
as synaptic charge transfer.

```python
{
    "type": "fill_between",
    "x": "_int_x",        # key for the shared time array
    "y1": "_int_y",       # key for the upper/primary curve (required)
    "y2": "_base",        # key for the lower curve or scalar baseline (default: 0.0)
    "brush": (0, 100, 255, 100),  # RGBA fill colour (optional)
}
```

The named keys are looked up first in the top-level result dict and then inside
the nested `result["metrics"]` dict, so both a flat schema and the standard
`{"module_used": ..., "metrics": {...}}` schema are supported transparently.

`y2` may be:
- a key pointing to an **array** of the same length as `y1` (arbitrary curve),
- a key pointing to a **scalar** (constant horizontal baseline), or
- omitted entirely (defaults to zero).

**Example — Synaptic Charge Transfer with shaded integral:**

```python
plots=[
    {"type": "interactive_region", "data": ["window_start", "window_end"], "color": "g"},
    {
        "type": "fill_between",
        "x": "_int_x",
        "y1": "_int_y",
        "y2": "_base",
        "brush": (0, 100, 255, 100),
    },
]
```

The corresponding return dict must include `_int_x`, `_int_y`, and `_base` as
private (hidden) keys:

```python
return {
    "module_used": "synaptic_charge",
    "metrics": {"Total_Charge_pC": charge},
    "Total_Charge_pC": charge,
    "_int_x": win_time.tolist(),
    "_int_y": win_data.tolist(),
    "_base": baseline_mean,
}
```

---

## 6. Where to Put Your Plugin File

> **Prerequisite — Enable Custom Plugins:** Before your plugin will load you
> must ensure the "Enable Custom Plugins" checkbox is checked in
> **Edit > Preferences > Extensions** (or **Synaptipy > Preferences** on
> macOS).  This setting is on by default.  After changing it, restart
> Synaptipy for the change to take effect.

### Option A: Built-in Examples Directory

Synaptipy ships ready-to-run example plugins in `examples/plugins/`.  These are
loaded automatically at startup so you can try them immediately and use them as
templates.  Enable them via **Edit > Preferences** (or **Synaptipy > Preferences**
on macOS) by checking **Enable Custom Plugins**, then restart Synaptipy.

---

#### Included Example Plugins

| File | Label in GUI | Purpose |
|------|-------------|---------|
| `examples/plugins/synaptic_charge.py` | Synaptic Charge (AUC) | Integrates a postsynaptic current trace over a user-defined window to compute total charge (pC) via the trapezoidal rule; highlights the integrated area with a shaded fill overlay and marks the peak amplitude with a star symbol. |
| `examples/plugins/opto_jitter.py` | Opto Latency Jitter | Detects the first spike in each sweep following a TTL pulse and reports trial-to-trial latency variability (jitter) for optogenetic monosynaptic verification. Requires a secondary digital/TTL channel. |
| `examples/plugins/ap_repolarization.py` | AP Repolarization Rate | Finds the steepest falling slope (dV/dt minimum) of the first action potential in a window, quantifying maximum repolarization rate in V/s as a proxy for potassium-channel dynamics. |

To use these plugins:

1. Open **Edit > Preferences** (or **Synaptipy > Preferences** on macOS).
2. Check **Enable Custom Plugins**.
3. Restart Synaptipy.  Each plugin appears as a new sub-tab in the Analyser.

To customise one, copy the file to `~/.synaptipy/plugins/` and edit your copy.  Synaptipy prefers the user copy over the bundled example, so your changes take effect immediately on the next restart.

### Option B: User Plugin Directory (recommended for personal additions)

| Platform | Full path |
|----------|----------|
| macOS / Linux | `~/.synaptipy/plugins/my_analysis.py` |
| Windows | `C:\Users\<YourUsername>\.synaptipy\plugins\my_analysis.py` |

- No Synaptipy source changes needed.
- File is auto-discovered at startup.
- Works for any number of `.py` files.
- Will not be overwritten by upgrades.
- On Windows, open the folder with `%USERPROFILE%\.synaptipy\plugins` in Explorer.

### Option C: Built-in Module (for core contributors)

If you are contributing to the Synaptipy repository itself:

1. Create your module in `src/Synaptipy/core/analysis/my_analysis.py`.
2. Add the import to `src/Synaptipy/core/analysis/__init__.py`:
   ```python
   from . import my_analysis  # noqa: F401 - registers: my_analysis_name
   ```
3. (Optional) Create a custom tab class in
   `src/Synaptipy/application/gui/analysis_tabs/` if you need GUI behaviour
   beyond what the metadata-driven tab provides.
4. Add a test in `tests/core/test_my_analysis.py`.

> **Important:** The `__init__.py` import is required.  Without it, the
> `@AnalysisRegistry.register` decorator never executes and your analysis will
> not appear (see the developer guide's *Registry import rule*).

---

## 7. For Core Contributors — Adding a Built-in Analysis

Step-by-step:

| Step | File | What to do |
|---|---|---|
| 1 | `src/Synaptipy/core/analysis/my_module.py` | Write pure logic + registry wrapper (see §3) |
| 2 | `src/Synaptipy/core/analysis/__init__.py` | Add `from . import my_module  # noqa: F401` |
| 3 | `tests/core/test_my_module.py` | Write pytest tests for the pure logic function |
| 4 | `tests/core/test_registry_metadata.py` | Add your `name` to `EXPECTED_BUILTIN_ANALYSES` |

**Do not create a custom tab class** unless you need interactive GUI features
(e.g. click-to-add events, drag-to-select spikes) that the metadata-driven tab
cannot provide.

---

## 8. Testing Your Plugin

### Unit-testing the logic function

Since the logic function is pure Python + NumPy, test it directly with pytest:

```python
# test_my_snr.py
import numpy as np
from my_analysis import calculate_snr   # or import from plugin path

def test_snr_basic():
    fs = 10000.0
    t = np.arange(0, 1.0, 1 / fs)
    # Known signal + noise
    signal = np.sin(2 * np.pi * 50 * t) * 10.0
    noise = np.random.default_rng(42).normal(0, 0.5, len(t))
    data = np.concatenate([noise[:1000], signal[1000:]])

    result = calculate_snr(data, fs, 0.0, 0.1, 0.1, 1.0)
    assert result["snr_db"] > 20.0
    assert result["noise_rms"] > 0
```

### Integration-testing the registry wrapper

```python
import numpy as np
from Synaptipy.core.analysis.registry import AnalysisRegistry

def test_snr_registered():
    # Ensure the plugin is loaded
    from Synaptipy.application.plugin_manager import PluginManager
    PluginManager.load_plugins()

    func = AnalysisRegistry.get_function("snr_analysis")
    assert func is not None

    meta = AnalysisRegistry.get_metadata("snr_analysis")
    assert "ui_params" in meta
    assert meta.get("label") == "Signal-to-Noise Ratio"
```

### Testing the template shipped with Synaptipy

The repository includes a test that validates the plugin template itself:

```bash
conda run -n synaptipy python -m pytest tests/core/test_plugin_template.py -v
```

---

## 9. Full Annotated Example — Synaptic Charge Transfer

This example measures the **total synaptic charge** ($Q$, in picocoulombs)
delivered during a postsynaptic current by integrating the current trace inside
a user-defined time window using the trapezoidal rule.

$$Q = \int_{t_1}^{t_2} I(t)\, dt$$

For a current trace in pA and time in seconds the result is in pA·s = pC.

Save this as `~/.synaptipy/plugins/synaptic_charge.py` (or copy it from
`examples/plugins/`):

```python
"""
Custom Synaptipy Plugin: Synaptic Charge Transfer (Area Under Curve).

Drop this file in ~/.synaptipy/plugins/ and restart Synaptipy.
A new "Synaptic Charge Transfer" tab will appear in the Analyser.
"""
import logging
from typing import Any, Dict

import numpy as np

from Synaptipy.core.analysis.registry import AnalysisRegistry

log = logging.getLogger(__name__)


# ── Part 1: Pure logic ─────────────────────────────────────────────
def calculate_synaptic_charge(
    data: np.ndarray,
    time: np.ndarray,
    sampling_rate: float,
    window_start: float,
    window_end: float,
    baseline_start: float,
    baseline_end: float,
) -> Dict[str, Any]:
    """
    Integrate the baseline-subtracted current trace to obtain total charge.

    Args:
        data: 1-D current trace in pA.
        time: 1-D time array in seconds, same length as data.
        sampling_rate: Sampling rate in Hz.
        window_start: Start of the integration window (seconds).
        window_end: End of the integration window (seconds).
        baseline_start: Start of the baseline window (seconds).
        baseline_end: End of the baseline window (seconds).

    Returns:
        Dict with 'Total_Charge_pC' and hidden keys for plot overlays.
        Returns {'error': ...} on invalid input.
    """
    if data.size == 0:
        return {"error": "Empty data array"}

    # Baseline window
    bl_i0 = int(np.searchsorted(time, baseline_start, side="left"))
    bl_i1 = int(np.searchsorted(time, baseline_end, side="right"))
    baseline_seg = data[bl_i0:bl_i1]
    if baseline_seg.size < 2:
        return {"error": "Baseline window too narrow (need >= 2 samples)"}
    baseline_mean = float(np.mean(baseline_seg))

    # Integration window
    win_i0 = int(np.searchsorted(time, window_start, side="left"))
    win_i1 = int(np.searchsorted(time, window_end, side="right"))
    win_time = time[win_i0:win_i1]
    win_data = data[win_i0:win_i1] - baseline_mean

    if win_data.size < 2:
        return {"error": "Integration window too narrow (need >= 2 samples)"}

    # np.trapz integrates pA * s = pC
    charge_pC = float(np.trapz(win_data, win_time))

    return {
        "module_used": "synaptic_charge",
        "metrics": {
            "Total_Charge_pC": round(charge_pC, 4),
        },
        # Scalar top-level key for the results table
        "Total_Charge_pC": round(charge_pC, 4),
        "Baseline_pA": round(baseline_mean, 4),
        # Private keys for plot overlays
        "_baseline_level": baseline_mean,
        "_int_x": win_time.tolist(),
        "_int_y": (data[win_i0:win_i1]).tolist(),
        "_base": baseline_mean,
    }


# ── Part 2: Registry wrapper ──────────────────────────────────────
@AnalysisRegistry.register(
    name="synaptic_charge",
    label="Synaptic Charge Transfer",
    ui_params=[
        {
            "name": "baseline_start",
            "label": "Baseline Start (s):",
            "type": "float",
            "default": 0.0,
            "min": 0.0,
            "max": 1e9,
            "decimals": 4,
        },
        {
            "name": "baseline_end",
            "label": "Baseline End (s):",
            "type": "float",
            "default": 0.05,
            "min": 0.0,
            "max": 1e9,
            "decimals": 4,
        },
        {
            "name": "window_start",
            "label": "Integration Start (s):",
            "type": "float",
            "default": 0.05,
            "min": 0.0,
            "max": 1e9,
            "decimals": 4,
        },
        {
            "name": "window_end",
            "label": "Integration End (s):",
            "type": "float",
            "default": 0.3,
            "min": 0.0,
            "max": 1e9,
            "decimals": 4,
        },
    ],
    plots=[
        # Draggable region over the baseline window
        {"type": "interactive_region", "data": ["baseline_start", "baseline_end"], "color": "b"},
        # Draggable region over the integration window
        {"type": "interactive_region", "data": ["window_start", "window_end"], "color": "g"},
        # Horizontal line at the baseline level
        {"type": "hlines", "data": ["_baseline_level"], "color": "b", "styles": ["dash"]},
        # Shaded fill between the raw current and the baseline level
        {
            "type": "fill_between",
            "x": "_int_x",
            "y1": "_int_y",
            "y2": "_base",
            "brush": (0, 100, 255, 100),
        },
    ],
)
def run_synaptic_charge_wrapper(
    data: np.ndarray,
    time: np.ndarray,
    sampling_rate: float,
    **kwargs,
) -> Dict[str, Any]:
    """Registry wrapper - extracts kwargs and calls pure logic."""
    return calculate_synaptic_charge(
        data=data,
        time=time,
        sampling_rate=sampling_rate,
        window_start=kwargs.get("window_start", 0.05),
        window_end=kwargs.get("window_end", 0.3),
        baseline_start=kwargs.get("baseline_start", 0.0),
        baseline_end=kwargs.get("baseline_end", 0.05),
    )
```

The key design points illustrated here:
- A dedicated **baseline window** is used to subtract the holding current
  before integration, keeping the result physically meaningful.
- `np.trapz` is used for trapezoidal integration (not a simple sum), which is
  exact for linear interpolations between sample points.
- The return dict follows the **nested output schema** `{"module_used": ...,
  "metrics": {...}}` alongside flat scalar keys for the results table.
- Two `interactive_region` overlays let the user drag both windows directly on
  the trace without typing numbers.
- A `fill_between` overlay shades the integrated area, making the charge
  visually obvious on the trace.
- `_baseline_level`, `_int_x`, `_int_y`, and `_base` (private keys) feed the
  plot overlays without appearing in the results table.

---

## 10. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Tab does not appear | Plugin file has a syntax error | Check the Synaptipy log (`~/.synaptipy/synaptipy.log`) for `SyntaxError` messages. |
| Tab does not appear | File not in the plugins folder | Verify the path: macOS/Linux: `ls ~/.synaptipy/plugins/` — Windows: `dir %USERPROFILE%\.synaptipy\plugins` |
| Tab does not appear | Missing `@AnalysisRegistry.register` decorator | The file must contain a decorated function. |
| `ImportError` in log | Plugin imports a package not installed in your environment | Install the dependency: `pip install <package>` |
| `name "X" is already registered` warning | Two plugins use the same `name=` string | Change one plugin's `name=` to something unique. |
| Parameters don't show up | `ui_params` has a typo in `"type"` | Must be one of: `"float"`, `"int"`, `"bool"`, `"choice"` |
| Plot overlay missing | Result dict key doesn't match `plots` data key | The key in `"data"` must exactly match a key in the returned dict. |
| Results table shows `_private` keys | Keys must start with underscore | Prefix with `_`: `"_fit_data"` |
| Built-in contrib: 0 tabs on Windows | Forgot to add `from . import X` in `__init__.py` | See §7, step 2. |
