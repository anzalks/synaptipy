# Synaptipy Styling Guide

This document describes the Qt6 palette theming, button role conventions, and
PyQtGraph plot styling utilities used across Synaptipy.

## Overview

Synaptipy separates application palette management (`src/synaptipy/shared/theme_manager.py`)
from widget and plot helper utilities (`src/synaptipy/shared/styling.py` and
`src/synaptipy/shared/plot_factory.py`):

1. **Theme Manager** (`theme_manager.py`) applies Qt's `"Fusion"` style with
   explicit dark or light `QPalette` definitions and tracks OS color-scheme
   changes when `ThemeMode.SYSTEM` is selected.
2. **Plot Factory** (`plot_factory.py`) constructs all `PyQtGraph` plot widgets
   and layout containers with safe software-rendering defaults and scientific
   axes formatting.
3. **Styling Helpers** (`styling.py`) provide semantic button/label helpers and
   theme-aware `PyQtGraph` pens.

## Theme Mode Management

Application theme state is managed in `src/synaptipy/shared/theme_manager.py`:

- `ThemeMode`: Enum with `LIGHT`, `DARK`, and `SYSTEM` modes.
- `get_theme_mode()`: Returns the persisted `ThemeMode` from `QSettings`.
- `set_theme_mode(mode)`: Persists `mode`, applies the resolved palette immediately
  via `apply_theme(mode)`, and notifies registered listeners.
- `apply_theme(mode=None)`: Applies Qt `"Fusion"` style with `_apply_dark_palette`
  or `_apply_light_palette` according to `is_dark_mode()`.
- `install_system_theme_listener(app)`: Connects to `QStyleHints.colorSchemeChanged`
  so `ThemeMode.SYSTEM` updates live when the OS switches between light and dark
  appearance.

```python
from synaptipy.shared.theme_manager import ThemeMode, apply_theme, set_theme_mode

# Switch to dark mode and persist preference
set_theme_mode(ThemeMode.DARK)

# Re-apply the currently saved preference at startup
apply_theme()
```

Scientific trace canvases keep a white (`"w"`) background with black foreground
axes (`configure_plot_widget`) regardless of whether the surrounding UI chrome
uses the dark or light Fusion palette, ensuring publication-consistent contrast.

## Creating and Styling PyQtGraph Plots

Direct instantiation of `pg.PlotWidget()` or `pg.GraphicsLayoutWidget()` is
forbidden because unguarded OpenGL/ViewBox configurations cause platform-specific
crashes. Always construct plot widgets through `SynaptipyPlotFactory`:

```python
from synaptipy.shared.plot_factory import SynaptipyPlotFactory
from synaptipy.shared.styling import configure_plot_widget, get_average_pen, get_trial_pen

plot_widget = SynaptipyPlotFactory.create_plot_widget(
    title="Membrane Potential",
    labels={"left": ("Voltage", "mV"), "bottom": ("Time", "s")},
)
configure_plot_widget(plot_widget)

plot_widget.plot(time, trial_data, pen=get_trial_pen())
plot_widget.plot(time, avg_data, pen=get_average_pen())
```

User-configurable trace, scatter, and overlay pens are managed through
`get_plot_customization_manager()` (`src/synaptipy/shared/plot_customization.py`),
accessible in the UI under **View > Plot Customization...**.

## Widget Helpers and Button Roles

All widget colors inherit from the active `QPalette`; avoid hardcoding hex
stylesheets on individual controls. Assign button semantics via `style_button`:

```python
from PySide6 import QtWidgets
from synaptipy.shared.styling import style_button, style_label

run_btn = QtWidgets.QPushButton("Run Analysis")
reset_btn = QtWidgets.QPushButton("Reset View")
heading = QtWidgets.QLabel("Passive Properties")

style_button(run_btn, "primary")
style_button(reset_btn, "secondary")
style_label(heading, "heading")
```

| Role | Intended Action | Appearance |
|---|---|---|
| `secondary` (default) | Navigation and supporting controls (`Previous`, `Next`, `Reset View`, `Browse`, `Refresh`, `Undo`) | Neutral palette button |
| `primary` | The single primary action advancing the panel workflow (`Run Analysis`, `Run Batch Analysis`, `Export`) | Default/accent button (`setDefault(True)`) |

Use at most one visible `primary` button per panel or dialog, and guard
destructive reset/delete operations with an explicit confirmation dialog.
