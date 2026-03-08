# Explorer X-Axis Shift Fix

**Date:** March 2, 2026
**Author:** Anzal K Shahul
**Status:** ✅ COMPLETED

---

## Overview

Fixed a bug where the Explorer tab's X-axis would shift right (not starting
at 0) when cycling through files, especially with multichannel recordings.
The Y-axis was also too narrow in overlay mode when trial 0 was at resting
potential but other trials contained action potentials.

---

## Symptoms

1. **X-axis shifted right**: Opening a multichannel file (e.g. 4-channel ABF)
   after viewing a single-channel file caused the X-axis to not start at 0.
   The same file displayed correctly after pressing "Reset View" manually.
2. **Y-range too narrow in overlay mode**: When all trials were overlaid,
   only trial 0's amplitude range was used - if trial 0 was at resting
   potential the Y range missed action potentials in other trials.
3. **Inconsistent view on file cycling**: Rapidly cycling through files
   produced different view ranges than opening the same file fresh.

---

## Root Causes

### 1. Stale ViewBox signals from `deleteLater()`'d widgets

**File:** `src/Synaptipy/application/gui/explorer/plot_canvas.py`

`ExplorerPlotCanvas.rebuild_plots()` creates a new `GraphicsLayoutWidget` and
schedules the old widget for deletion via `deleteLater()`.  However, the old
ViewBoxes survive until the next event-loop iteration and can still emit
`sigXRangeChanged` / `sigYRangeChanged` / `sigResized` signals.  These signals
are connected via lambdas in `_configure_plot_item()` to the canvas's
`x_range_changed` signal, which feeds into the Explorer tab's
`_on_vb_x_range_changed()` → slider/scrollbar update logic.

When old ViewBoxes emit during destruction, they fire signals with channel IDs
that happen to match the new recording's channel IDs, corrupting the
slider/scrollbar values for the new display.

**Fix:** Explicitly disconnect all ViewBox signals (`sigXRangeChanged`,
`sigYRangeChanged`, `sigResized`) in `rebuild_plots()` BEFORE clearing Python
references to the old plot items.

### 2. X-link range recalculation from screen geometry

**File:** `src/Synaptipy/application/gui/explorer/explorer_tab.py`

In multichannel mode, ViewBoxes are X-linked so all channels share the same
time axis.  When `_reset_view()` calls `setXRange()` on one ViewBox, the linked
ViewBoxes receive a `linkedViewChanged()` callback that recalculates the X range
from screen-geometry pixel offsets between stacked ViewBoxes.  Because the
ViewBoxes have different pixel widths (different Y-axis label widths), this
recalculation produces slightly shifted X ranges.

**Fix:** Block link propagation with `vb.blockLink(True)` on ALL ViewBoxes
before setting ranges in `_reset_view()`, then unblock with
`vb.blockLink(False)` after all ranges are set.

### 3. Y range computed from trial 0 only

**File:** `src/Synaptipy/application/gui/explorer/explorer_tab.py`

`_compute_channel_y_range()` used only `channel.get_data(trial_idx=0)` to
compute the Y-axis range.  For recordings where trial 0 is at resting potential
(e.g. −65.65 to −65.10 mV) but other trials contain action potentials (e.g.
−80 to +40 mV), the Y range was far too narrow to display the full signal in
overlay mode.

**Fix:** Sample up to 50 trials evenly spaced across all available trials and
compute the global min/max from all sampled data.

---

## Deferred Initial Reset

A generation-counter-protected `_deferred_initial_reset()` was added for
multichannel recordings.  After Qt processes initial layout geometry events
(which cause `sigResized` callbacks that can shift ViewBox ranges), this
deferred callback re-applies `_reset_view()` to ensure correct initial
display.

The generation counter (`_display_generation`) prevents stale resets from
previous file loads from executing if the user has already navigated to a
different file.  The deferred reset is only scheduled for multichannel
recordings and only when no view state restoration is pending.

---

## Files Modified

| File | Change |
|------|--------|
| `src/Synaptipy/application/gui/explorer/plot_canvas.py` | Disconnect old ViewBox signals before widget replacement |
| `src/Synaptipy/application/gui/explorer/explorer_tab.py` | Block X-link in `_reset_view()`, all-trial Y range, deferred initial reset |

---

## Verification

- All 330 tests pass (zero failures)
- flake8 clean on both modified files
- State preservation tests (3/3) pass - deferred reset does not overwrite
  deliberate zoom/pan or restored view state
