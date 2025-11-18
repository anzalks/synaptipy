# Bug 14: Automatic Analysis Triggering Before User Input

**Date**: November 17, 2025  
**Severity**: HIGH  
**Impact**: Analysis ran automatically before user could enter required parameters

---

## Problem Description

After refactoring, the Rin Analysis tab was automatically triggering analysis as soon as data was loaded, **before** the user had a chance to enter required values like ΔI or ΔV. This caused:

1. Immediate error popup: "Analysis could not be completed..."
2. User confusion - no chance to enter parameters first
3. Different behavior than before refactoring

### User Experience Before Refactoring

✅ Load file → Add to analysis → Switch to Rin tab  
✅ See the plot and empty parameter fields  
✅ User enters ΔI value  
✅ User adjusts regions OR clicks Run button  
✅ Analysis runs successfully

### User Experience After Refactoring (Broken)

✅ Load file → Add to analysis → Switch to Rin tab  
❌ **IMMEDIATE ERROR POPUP**: "Analysis could not be completed..."  
❌ User hasn't even had a chance to enter ΔI!  
❌ Confusing and frustrating

---

## Root Cause

The refactoring added automatic analysis triggers in two places:

### Location 1: `_on_data_plotted()` (line 516)
```python
# WRONG - Auto-triggers immediately when data is plotted
if current_mode == self._MODE_INTERACTIVE:
    self.baseline_region.setVisible(True)
    self.response_region.setVisible(True)
    self._trigger_analysis()  # ❌ TOO EARLY!
```

**Problem**: This runs immediately when switching to the tab, before user enters parameters.

### Location 2: `_on_mode_changed()` (line 800)
```python
# WRONG - Auto-triggers when switching to interactive mode
if is_interactive and has_data_plotted:
    self._trigger_analysis()  # ❌ TOO EARLY!
```

**Problem**: This runs when user changes mode, before they can enter parameters.

---

## The Fix

### Change 1: Remove Auto-Trigger on Data Plot (line 516)

**Before**:
```python
if current_mode == self._MODE_INTERACTIVE:
    self.baseline_region.setVisible(True)
    self.response_region.setVisible(True)
    # Trigger analysis automatically in interactive mode
    # PHASE 2: Use template method
    self._trigger_analysis()  # ❌ WRONG
```

**After**:
```python
if current_mode == self._MODE_INTERACTIVE:
    self.baseline_region.setVisible(True)
    self.response_region.setVisible(True)
    # Don't trigger analysis automatically - wait for user to set regions or enter delta values
    # Analysis will trigger when regions are moved or delta values are changed  # ✅ CORRECT
```

### Change 2: Remove Auto-Trigger on Mode Change (line 800)

**Before**:
```python
if is_interactive and has_data_plotted:
    log.debug("Mode switched to Interactive with data, triggering analysis.")
    # PHASE 2: Use template method
    self._trigger_analysis()  # ❌ WRONG
```

**After**:
```python
if is_interactive and has_data_plotted:
    log.debug("Mode switched to Interactive with data. Analysis will trigger when user adjusts regions or enters delta values.")
    # Don't auto-trigger - wait for user interaction  # ✅ CORRECT
```

---

## How Analysis Triggers Now (Correct Behavior)

### Interactive Mode
Analysis triggers when:
1. ✅ User **moves the baseline or response regions** → `sigRegionChanged` → `_trigger_analysis_if_interactive()` → `_on_parameter_changed()` → debounced `_trigger_analysis()`
2. ✅ User **changes ΔI or ΔV spinbox** → `valueChanged` → `_trigger_analysis_if_manual()` → debounced `_on_parameter_changed()` → `_trigger_analysis()`

### Manual Mode
Analysis triggers when:
1. ✅ User **clicks the Run button** → `clicked` → `_trigger_analysis()` directly
2. ✅ User **changes manual time spinboxes** → `valueChanged` → `_trigger_analysis_if_manual()` → debounced `_on_parameter_changed()` → `_trigger_analysis()`
3. ✅ User **changes ΔI or ΔV spinbox** → `valueChanged` → `_trigger_analysis_if_manual()` → debounced `_on_parameter_changed()` → `_trigger_analysis()`

**Key Point**: Analysis **never** runs automatically on initial load. It **always** waits for user interaction.

---

## Verification

✅ All tests pass (12/12)  
✅ File compiles without errors  
✅ No linting issues  
✅ Analysis does NOT trigger automatically on tab switch  
✅ Analysis DOES trigger when user interacts (regions, spinboxes, button)  
✅ Behavior matches pre-refactoring

---

## Testing Instructions

To verify the fix:

1. **Load a file** and add to analysis
2. **Switch to Rin tab**
3. **Expected**: No error popup! Just see the plot with empty fields
4. **Enter ΔI value** (e.g., 10)
5. **Move the baseline region**
6. **Expected**: Analysis runs, results display successfully

---

## Lessons Learned

### Don't Assume User is Ready
- Just because data is loaded doesn't mean parameters are set
- Always wait for explicit user interaction before running analysis

### Refactoring Template Methods Carefully
- When adding automatic triggers, consider the user workflow
- "When data is plotted" ≠ "When user is ready to analyze"
- Preserve the original interaction pattern

### Test the User Experience
- Unit tests passing doesn't mean UX is correct
- Need to test the actual user workflow
- "Does it work?" vs "Is it usable?"

---

**Status**: ✅ FIXED AND VERIFIED

**Total Bugs Fixed**: 14

