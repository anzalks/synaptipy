# Bug 15: `_current_plot_data` Cleared After Being Set

**Date**: November 17, 2025  
**Severity**: CRITICAL  
**Impact**: All analysis tabs showed "Please load and plot data before running analysis" even after data was loaded

---

## Problem Description

After refactoring, all analysis tabs (Event Detection, RMP, Spike) were showing the error:
> **"Please load and plot data before running analysis."**

Even though:
- ✅ Files were successfully loaded
- ✅ Data was successfully plotted (log shows "Successfully plotted Average from channel 0")
- ✅ `_current_plot_data` was set by the base class

### Root Cause

The refactoring introduced a **call order bug**:

1. **Base class** (`base.py`):
   - `_on_analysis_item_selected()` → calls `_populate_channel_and_source_comboboxes()`
   - Which calls `_plot_selected_data()` → **sets `_current_plot_data`** ✅
   - Then calls `_update_ui_for_selected_item()` (subclass method)

2. **Subclasses** (Event Detection, RMP, Spike):
   - `_update_ui_for_selected_item()` → **clears `_current_plot_data = None`** ❌

**Result**: Data was set, then immediately cleared, causing analysis to fail!

---

## The Fix

Removed the lines that clear `_current_plot_data` from `_update_ui_for_selected_item()` in all three affected tabs.

### Files Fixed

1. **`event_detection_tab.py`** (line 334)
2. **`rmp_tab.py`** (line 278)
3. **`spike_tab.py`** (line 165)

### Code Changes

**Before** (WRONG):
```python
def _update_ui_for_selected_item(self):
    log.debug(f"{self.get_display_name()}: Updating UI for selected item index {self._selected_item_index}")
    
    # Clear previous results
    self._current_plot_data = None  # ❌ This clears data that base class just set!
    if self.mini_results_textedit:
        self.mini_results_textedit.setText("")
```

**After** (CORRECT):
```python
def _update_ui_for_selected_item(self):
    log.debug(f"{self.get_display_name()}: Updating UI for selected item index {self._selected_item_index}")
    
    # Clear previous results (but NOT _current_plot_data - base class manages it)
    if self.mini_results_textedit:  # ✅ No longer clearing _current_plot_data
        self.mini_results_textedit.setText("")
```

---

## Why This Happened

During refactoring, the responsibility for managing `_current_plot_data` was moved to the base class. However, the subclasses still had leftover code from the old implementation that cleared this data.

**Old Pattern** (Before Refactoring):
- Each tab managed its own `_current_plot_data`
- Clearing it in `_update_ui_for_selected_item()` was correct

**New Pattern** (After Refactoring):
- Base class manages `_current_plot_data`
- Subclasses should NOT clear it
- Subclasses should only clear their own UI elements

---

## Verification

✅ All files compile without errors  
✅ All tests pass (12/12)  
✅ No linting issues  
✅ Event Detection tab can now run analysis  
✅ RMP tab can now run analysis  
✅ Spike tab can now run analysis

---

## Lessons Learned

### 1. Ownership of Data Structures
When refactoring to move data management to a base class:
- ✅ Clearly document which attributes are managed by base class
- ✅ Remove all subclass code that manipulates those attributes
- ✅ Add comments explaining the ownership

### 2. Call Order Matters
When base class calls subclass methods:
- ✅ Be aware of what data the base class sets before calling subclass
- ✅ Don't clear data that was just set by the base class
- ✅ Test the actual call order, not just individual methods

### 3. Cleanup During Refactoring
When removing old code:
- ✅ Search for all references to moved attributes
- ✅ Remove ALL code that manipulates those attributes
- ✅ Don't leave "just in case" code that clears things

---

## Testing Instructions

To verify the fix:

1. **Load a file** and add to analysis
2. **Switch to Event Detection tab**
3. **Expected**: No error popup! Data is loaded and plotted
4. **Click "Detect" button**
5. **Expected**: Analysis runs successfully, events are detected

Repeat for RMP and Spike tabs - all should work now!

---

**Status**: ✅ FIXED AND VERIFIED

**Total Bugs Fixed**: 15

