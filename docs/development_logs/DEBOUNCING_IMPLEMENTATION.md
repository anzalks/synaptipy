# Interaction Debouncing Implementation

**Author:** Anzal K Shahul  
**Email:** anzal.ks@gmail.com  
**Date:** October 21, 2025

## Overview

Implemented comprehensive interaction debouncing for all zoom and scroll controls in the `ExplorerTab` to eliminate lag and improve UI responsiveness during rapid slider/scrollbar adjustments.

## Changes Made

### 1. Timer Initialization in `__init__` (Lines 135-164)

Added debounce timers for all zoom/scroll controls:

- **X-axis Zoom Timer**: `_x_zoom_apply_timer` (50ms delay)
- **X-axis Scroll Timer**: `_x_scroll_apply_timer` (50ms delay)
- **Global Y-axis Zoom Timer**: `_y_global_zoom_apply_timer` (50ms delay)
- **Global Y-axis Scroll Timer**: `_y_global_scroll_apply_timer` (50ms delay)
- **Individual Y-axis Zoom Timers**: `_individual_y_zoom_timers` (per-channel, 50ms delay)
- **Individual Y-axis Scroll Timers**: `_individual_y_scroll_timers` (per-channel, 50ms delay)

Each timer is configured as single-shot with a 50ms interval, meaning the actual action is delayed by 50ms after the last slider/scrollbar event.

### 2. Signal Handler Updates

Modified all zoom/scroll signal handlers to use the debouncing pattern:

#### X-axis Controls:
- `_on_x_zoom_changed`: Stores value, starts timer, logs debouncing
- `_on_x_scrollbar_changed`: Stores value, starts timer (only if not updating), logs debouncing

#### Global Y-axis Controls:
- `_on_global_y_zoom_changed`: Stores value, starts timer, logs debouncing
- `_on_global_y_scrollbar_changed`: Stores value, starts timer (only if not updating), logs debouncing

#### Individual Y-axis Controls:
- `_on_individual_y_zoom_changed`: Stores value per channel, creates/starts timer, logs debouncing
- `_on_individual_y_scrollbar_changed`: Stores value per channel, creates/starts timer (only if not updating), logs debouncing

### 3. Debounced Apply Methods

Added dedicated methods that contain the actual zoom/scroll logic, called after the debounce delay:

#### X-axis:
- `_apply_debounced_x_zoom`: Applies X zoom with full logic inline
- `_apply_debounced_x_scroll`: Applies X scroll with full logic inline

#### Global Y-axis:
- `_apply_debounced_y_global_zoom`: Applies global Y zoom with full logic inline (not delegating to helper)
- `_apply_debounced_y_global_scroll`: Applies global Y scroll with full logic inline (not delegating to helper)

#### Individual Y-axis:
- `_get_or_create_individual_y_zoom_timer`: Helper to lazily create per-channel timers
- `_get_or_create_individual_y_scroll_timer`: Helper to lazily create per-channel timers
- `_apply_debounced_individual_y_zoom`: Applies individual Y zoom with full logic inline
- `_apply_debounced_individual_y_scroll`: Applies individual Y scroll with full logic inline

### 4. Key Implementation Details

1. **Inline Logic**: All debounced apply methods contain the full logic inline rather than delegating to helper methods. This eliminates additional function call overhead and potential signal cascades.

2. **State Guards**: Each apply method checks `_updating_viewranges` and `_updating_scrollbars` flags to prevent recursive updates during the application of changes.

3. **Lazy Timer Creation**: Individual Y-axis timers are created on-demand per channel to avoid memory overhead for channels that aren't used.

4. **Debug Logging**: All methods include detailed debug logging to track debouncing behavior and actual application of changes.

5. **Scrollbar Blocking**: Scroll handlers check `if not self._updating_scrollbars` before triggering debounce to prevent feedback loops.

## Performance Benefits

1. **Reduced Redraws**: Instead of redrawing on every slider/scrollbar event (potentially hundreds per second), redraws only occur 50ms after the user stops adjusting.

2. **Eliminated Cascading Updates**: Inline logic prevents helper methods from triggering additional signals or updates.

3. **Smoother User Experience**: The 50ms delay is imperceptible to users but dramatically reduces computational load.

4. **Scalability**: Per-channel timers for individual controls ensure efficient resource usage even with many channels.

## Verification

All tests passing (73 passed, 1 skipped):
- No regressions in existing functionality
- Debouncing implementation doesn't interfere with test behavior
- Signal handlers properly guard against update loops

## Usage

When running the application with debug logging enabled, you'll see messages like:
```
[_on_x_zoom_changed] Debouncing X zoom: 150
[_apply_debounced_x_zoom] Applying X zoom: 150
```

This confirms the debouncing is working: the first message appears immediately when the slider moves, the second appears 50ms after the last movement.

## Future Enhancements

If additional lag is observed:
1. Consider increasing debounce interval to 75-100ms for slower systems
2. Implement adaptive debouncing based on render time
3. Add downsampling hints to PyQtGraph during active zooming
4. Consider using QTimer.singleShot with lambda for even lighter-weight timers

