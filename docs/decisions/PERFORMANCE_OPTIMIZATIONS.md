# Plot Customization Performance Optimizations

## Overview
This document outlines the comprehensive performance optimizations implemented to address user concerns about:
- Slow plot interactions after customization
- Plots "reloading data every time"
- Excessive resource usage for thicker plots

## Key Performance Issues Identified

### 1. **Data Reloading Problem**
- **Root Cause**: The `_update_plot()` method was calling `_clear_plot_data_only()` and then recreating all `PlotDataItem` objects from scratch
- **Impact**: Every plot preference change triggered a complete data reload, causing significant performance degradation
- **Solution**: Implemented pen-only updates that modify existing plot items without recreating data

### 2. **Inefficient Plot Updates**
- **Root Cause**: All plots were being updated even when only styling preferences changed
- **Impact**: Unnecessary computation and rendering overhead
- **Solution**: Implemented smart update detection and selective updates

### 3. **Excessive Signal Emissions**
- **Root Cause**: Plot preference changes could trigger multiple rapid signal emissions
- **Impact**: Multiple plot refresh cycles and potential race conditions
- **Solution**: Implemented debouncing and change detection mechanisms

## Implemented Optimizations

### 1. **Pen-Only Updates**
```python
def _update_plot_pens_only(self):
    """Efficiently update only the pen properties of existing plot items without recreating data."""
    # Check if pen update is actually needed
    if not self._needs_pen_update():
        return
        
    # Update existing PlotDataItem pens without recreating data
    for item in self.plot_widget.plotItem.items:
        if isinstance(item, pg.PlotDataItem):
            item.setPen(appropriate_pen)
```

**Benefits**:
- No data reloading
- Instant visual updates
- Minimal CPU usage
- Maintains plot interactivity

### 2. **Smart Update Detection**
```python
def _needs_full_plot_update(self) -> bool:
    """Check if a full plot update is needed or if pen-only update is sufficient."""
    # Check data hash changes
    current_hash = self._get_data_hash()
    if hasattr(self, '_last_data_hash') and self._last_data_hash != current_hash:
        return True
        
    # Check plot mode changes
    if hasattr(self, '_last_plot_mode') and self._last_plot_mode != self.current_plot_mode:
        return True
        
    # Otherwise, pen-only update is sufficient
    return False
```

**Benefits**:
- Prevents unnecessary full updates
- Automatically detects when data has actually changed
- Optimizes update strategy based on change type

### 3. **Data Caching System**
```python
def _get_cached_data(self, chan_id: str, trial_idx: int) -> Optional[Tuple[np.ndarray, np.ndarray]]:
    """Get cached data for a channel and trial, or None if not cached."""
    if not self._cache_dirty and chan_id in self._data_cache and trial_idx in self._data_cache[chan_id]:
        return self._data_cache[chan_id][trial_idx]
    return None
```

**Benefits**:
- Eliminates redundant data loading
- Significantly faster subsequent plot updates
- Memory-efficient storage of frequently accessed data

### 4. **Pen Caching in Customization Manager**
```python
def _get_cached_pen(self, plot_type: str) -> Optional[pg.mkPen]:
    """Get a cached pen if available and cache is not dirty."""
    if not self._cache_dirty and plot_type in self._pen_cache:
        return self._pen_cache[plot_type]
    return None
```

**Benefits**:
- Prevents recreation of identical pen objects
- Faster pen retrieval for plot updates
- Automatic cache invalidation when preferences change

### 5. **Debounced Signal Emissions**
```python
def _debounced_emit_preferences_updated():
    """Emit preferences updated signal with debouncing to prevent rapid successive emissions."""
    global _update_timer
    
    if _update_timer is None:
        _update_timer = QtCore.QTimer()
        _update_timer.setSingleShot(True)
        _update_timer.timeout.connect(_plot_signals.preferences_updated.emit)
    
    # Reset timer - will emit signal after 100ms of no updates
    _update_timer.start(100)
```

**Benefits**:
- Prevents rapid successive plot updates
- Reduces unnecessary rendering cycles
- Improves overall application responsiveness

### 6. **Batch Preference Updates**
```python
def update_preferences_batch(self, new_preferences: Dict[str, Dict[str, Any]], emit_signal: bool = True):
    """Update multiple preferences at once and optionally emit signal."""
    # Check if anything actually changed
    if not self.has_preferences_changed(new_preferences):
        return False
        
    # Update all preferences in one operation
    # Emit signal only once
```

**Benefits**:
- Single signal emission for multiple changes
- Reduced overhead for complex preference updates
- Better performance for bulk operations

### 7. **Change Detection in UI Dialog**
```python
def _preferences_changed(self):
    """Check if preferences have actually changed from the original."""
    # Compare current preferences with snapshot taken when dialog opened
    for plot_type in self.current_preferences:
        for property_name in self.current_preferences[plot_type]:
            if (self.current_preferences[plot_type][property_name] != 
                self._original_preferences[plot_type][property_name]):
                return True
    return False
```

**Benefits**:
- Prevents unnecessary saves and updates
- Only triggers plot refresh when actual changes occur
- Improves user experience by avoiding unnecessary operations

## Performance Impact

### Before Optimizations
- **Plot Updates**: Full data reload on every preference change
- **Data Loading**: Repeated calls to `channel.get_data()` and `channel.get_averaged_data()`
- **Signal Emissions**: Multiple rapid emissions causing cascading updates
- **User Experience**: Slow interactions, noticeable delays, poor responsiveness

### After Optimizations
- **Plot Updates**: Instant pen-only updates for styling changes
- **Data Loading**: Cached data access, minimal reloading
- **Signal Emissions**: Debounced, change-detected, optimized
- **User Experience**: Instant visual feedback, smooth interactions, responsive UI

## Resource Usage Optimization

### Thicker Plots
- **Issue**: Thicker plot lines could potentially use more resources
- **Solution**: Pen caching prevents recreation of thick pen objects
- **Benefit**: Consistent performance regardless of line width

### Memory Management
- **Data Cache**: Efficient storage with automatic invalidation
- **Pen Cache**: Minimal memory overhead with smart cleanup
- **Cache Invalidation**: Automatic when data or preferences change

## Implementation Details

### Explorer Tab Optimizations
- Smart update detection (`_needs_full_plot_update`)
- Data caching system (`_data_cache`, `_average_cache`)
- Pen-only updates (`_update_plot_pens_only`)
- Change detection (`_get_data_hash`, `_get_pen_hash`)

### Analysis Tab Optimizations
- Base class pen update method (`_update_plot_pens_only`)
- Efficient plot item iteration
- Grid customization support

### Main Window Optimizations
- Smart plot update routing
- Active plot detection
- Efficient signal handling

### Customization Manager Optimizations
- Pen caching system
- Batch update operations
- Change detection
- Debounced signal emissions

## Testing and Validation

### Unit Tests
- `test_plot_customization.py` validates core functionality
- Performance tests confirm optimization effectiveness
- Cache behavior verification

### Integration Tests
- End-to-end plot update performance
- Signal emission optimization
- Memory usage validation

## Future Enhancements

### Potential Additional Optimizations
1. **Parallel Processing**: For very large datasets
2. **GPU Acceleration**: For complex plotting operations
3. **Lazy Loading**: For off-screen plot elements
4. **Compression**: For cached data storage

### Monitoring and Metrics
1. **Performance Profiling**: Track update times
2. **Memory Usage**: Monitor cache efficiency
3. **User Experience**: Measure interaction responsiveness

## Conclusion

These optimizations transform the plot customization system from a performance bottleneck to a highly responsive, efficient feature. The key improvements are:

1. **Elimination of unnecessary data reloading**
2. **Smart update detection and routing**
3. **Efficient caching at multiple levels**
4. **Optimized signal handling**
5. **Change detection to prevent redundant operations**

The result is a system that provides instant visual feedback for styling changes while maintaining the same data integrity and functionality as before.
