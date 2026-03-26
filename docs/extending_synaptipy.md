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
6. [Where to Put Your Plugin File](#6-where-to-put-your-plugin-file)
7. [For Core Contributors — Adding a Built-in Analysis](#7-for-core-contributors--adding-a-built-in-analysis)
8. [Testing Your Plugin](#8-testing-your-plugin)
9. [Full Annotated Example — Signal-to-Noise Ratio](#9-full-annotated-example--signal-to-noise-ratio)
10. [Troubleshooting](#10-troubleshooting)

---

## 1. Overview — How the Plugin System Works

Synaptipy has a central **`AnalysisRegistry`** — a Python class that maps named
analysis functions to the GUI and batch engine.  You register a function by
decorating it with `@AnalysisRegistry.register(...)`.  The decorator stores the
function and its metadata (parameter definitions, plot overlays, label, etc.).

At startup, Synaptipy:

1. Loads all **built-in** analyses from `src/Synaptipy/core/analysis/`.
2. Scans `~/.synaptipy/plugins/` for `.py` files and imports each one.
   Importing executes the `@AnalysisRegistry.register` decorators, adding your
   functions to the registry.
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
│      return {"snr_db": 42.3, "noise_rms": 0.15}          │
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
parameters from `kwargs`, calls your logic function, and returns a flat dict.

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
    return result
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

The wrapper must return a `Dict[str, Any]`.  Every key–value pair appears as a
row in the results table.

| Convention | Behaviour |
|---|---|
| Keys starting with `_` (underscore) | **Hidden** from the results table and batch dialog.  Use for internal data passed to plot overlays (e.g. `"_fit_curve"`, `"_event_indices"`). |
| Key named `"error"` | If present, the GUI shows an error message instead of results. |
| Numeric values (`int`, `float`) | Displayed as-is in the results table. |
| `np.ndarray` values | Displayed as shape summary (e.g. `"array(150,)"`). |
| `None` values | Displayed as `"N/A"`. |

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

---

## 6. Where to Put Your Plugin File

### Option A: User Plugin Directory (recommended for end users)

| Platform | Full path |
|----------|----------|
| macOS / Linux | `~/.synaptipy/plugins/my_analysis.py` |
| Windows | `C:\Users\<YourUsername>\.synaptipy\plugins\my_analysis.py` |

- No Synaptipy source changes needed.
- File is auto-discovered at startup.
- Works for any number of `.py` files.
- Will not be overwritten by upgrades.
- On Windows, open the folder with `%USERPROFILE%\.synaptipy\plugins` in Explorer.

### Option B: Built-in Module (for core contributors)

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

## 9. Full Annotated Example — Signal-to-Noise Ratio

Save this as `~/.synaptipy/plugins/snr_analysis.py`:

```python
"""
Custom Synaptipy Plugin: Signal-to-Noise Ratio (SNR) Analysis.

Drop this file in ~/.synaptipy/plugins/ and restart Synaptipy.
A new "Signal-to-Noise Ratio" tab will appear in the Analyser.
"""
import numpy as np
import logging
from typing import Dict, Any
from Synaptipy.core.analysis.registry import AnalysisRegistry

log = logging.getLogger(__name__)


# ── Part 1: Pure logic ─────────────────────────────────────────────
def calculate_snr(
    data: np.ndarray,
    time: np.ndarray,
    sampling_rate: float,
    noise_start: float,
    noise_end: float,
    signal_start: float,
    signal_end: float,
) -> Dict[str, Any]:
    """
    Calculate signal-to-noise ratio.

    Args:
        data: 1-D voltage trace.
        time: 1-D time array in seconds.
        sampling_rate: Sampling rate in Hz.
        noise_start: Start of the noise-only window (seconds).
        noise_end: End of the noise-only window (seconds).
        signal_start: Start of the signal window (seconds).
        signal_end: End of the signal window (seconds).

    Returns:
        Dict with 'snr_db', 'noise_rms', 'signal_rms'.
    """
    if data.size == 0:
        return {"error": "Empty data array"}

    # Convert time boundaries to sample indices
    noise_i0 = int(np.searchsorted(time, noise_start, side="left"))
    noise_i1 = int(np.searchsorted(time, noise_end, side="right"))
    sig_i0 = int(np.searchsorted(time, signal_start, side="left"))
    sig_i1 = int(np.searchsorted(time, signal_end, side="right"))

    noise_segment = data[noise_i0:noise_i1]
    signal_segment = data[sig_i0:sig_i1]

    if noise_segment.size < 2 or signal_segment.size < 2:
        return {"error": "Window too narrow — need at least 2 samples"}

    noise_rms = float(np.sqrt(np.mean(noise_segment ** 2)))
    signal_rms = float(np.sqrt(np.mean(signal_segment ** 2)))

    if noise_rms == 0:
        return {"error": "Noise RMS is zero — cannot compute SNR"}

    snr_db = float(20.0 * np.log10(signal_rms / noise_rms))

    return {
        "snr_db": round(snr_db, 2),
        "noise_rms": round(noise_rms, 4),
        "signal_rms": round(signal_rms, 4),
        # Hidden keys for plot overlays (not shown in results table)
        "_noise_level": noise_rms,
        "_signal_level": signal_rms,
    }


# ── Part 2: Registry wrapper ──────────────────────────────────────
@AnalysisRegistry.register(
    name="snr_analysis",
    label="Signal-to-Noise Ratio",
    ui_params=[
        {
            "name": "noise_start",
            "label": "Noise Window Start (s):",
            "type": "float",
            "default": 0.0,
            "min": 0.0,
            "max": 1e9,
            "decimals": 4,
        },
        {
            "name": "noise_end",
            "label": "Noise Window End (s):",
            "type": "float",
            "default": 0.1,
            "min": 0.0,
            "max": 1e9,
            "decimals": 4,
        },
        {
            "name": "signal_start",
            "label": "Signal Window Start (s):",
            "type": "float",
            "default": 0.1,
            "min": 0.0,
            "max": 1e9,
            "decimals": 4,
        },
        {
            "name": "signal_end",
            "label": "Signal Window End (s):",
            "type": "float",
            "default": 0.5,
            "min": 0.0,
            "max": 1e9,
            "decimals": 4,
        },
    ],
    plots=[
        # Draggable region for noise window (blue)
        {"type": "interactive_region", "data": ["noise_start", "noise_end"], "color": "b"},
        # Draggable region for signal window (green)
        {"type": "interactive_region", "data": ["signal_start", "signal_end"], "color": "g"},
        # Horizontal line at noise RMS level
        {"type": "hlines", "data": ["_noise_level"], "color": "b", "styles": ["dash"]},
        # Horizontal line at signal RMS level
        {"type": "hlines", "data": ["_signal_level"], "color": "g", "styles": ["solid"]},
    ],
)
def run_snr_wrapper(
    data: np.ndarray,
    time: np.ndarray,
    sampling_rate: float,
    **kwargs,
) -> Dict[str, Any]:
    """Registry wrapper — extracts kwargs and calls pure logic."""
    return calculate_snr(
        data=data,
        time=time,
        sampling_rate=sampling_rate,
        noise_start=kwargs.get("noise_start", 0.0),
        noise_end=kwargs.get("noise_end", 0.1),
        signal_start=kwargs.get("signal_start", 0.1),
        signal_end=kwargs.get("signal_end", 0.5),
    )
```

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
