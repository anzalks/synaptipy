# Refactoring Test Plan

## Objective
Test the refactoring approach on ONE tab (RMP tab) first, verify it works correctly, then apply to remaining tabs.

## Test Strategy

### Phase 1: Pre-Refactoring Tests
1. **Verify Current Functionality**
   - Run existing unit tests for analysis tabs
   - Document current behavior
   - Create baseline for comparison

2. **Check for Existing Test Coverage**
   - Review test_rin_tab.py for testing patterns
   - Identify what needs to be tested
   - Create missing tests if needed

### Phase 2: Incremental Refactoring with Testing

#### Step 1: Modify BaseAnalysisTab
- **Action**: Add data selection infrastructure to base class
- **Test**: 
  - Check for linting errors
  - Verify no existing tabs are broken
  - Run existing tests to ensure backward compatibility

#### Step 2: Refactor RMP Tab Only
- **Action**: Apply refactoring to rmp_tab.py
- **Test**:
  - Linting: No errors
  - Unit tests: All pass
  - Manual test: Load data and verify plotting works
  - Manual test: Verify baseline analysis works
  - Manual test: Verify all three modes (Interactive/Automatic/Manual)

#### Step 3: Validate Before Proceeding
- **Criteria for Success**:
  - ✅ No linting errors
  - ✅ All existing tests pass
  - ✅ Manual testing confirms functionality preserved
  - ✅ Code is cleaner and more maintainable

### Phase 3: Expand to Other Tabs
- Only proceed if Phase 2 validates successfully
- Apply same pattern to remaining tabs one at a time
- Test each tab before moving to next

## Test Execution Plan

### 1. Run Existing Tests
```bash
cd /Users/anzalks/PycharmProjects/Synaptipy
conda activate synaptipy
python -m pytest tests/application/gui/test_rin_tab.py -v
```

### 2. Check Linting
```bash
# Check specific files for linting
python -m pylint src/Synaptipy/application/gui/analysis_tabs/base.py
python -m pylint src/Synaptipy/application/gui/analysis_tabs/rmp_tab.py
```

### 3. Manual Testing Checklist for RMP Tab
- [ ] Open Synaptipy application
- [ ] Load test data file (examples/data/2023_04_11_0018.abf)
- [ ] Navigate to Baseline Analysis tab
- [ ] Verify channel selection works
- [ ] Verify data source selection works
- [ ] Verify plot displays correctly
- [ ] Test Interactive mode:
  - [ ] Region selector appears
  - [ ] Can drag region
  - [ ] Analysis runs automatically
  - [ ] Results display correctly
- [ ] Test Manual mode:
  - [ ] Time spinboxes appear
  - [ ] Can enter time values
  - [ ] Run button works
  - [ ] Results display correctly
- [ ] Test Automatic mode:
  - [ ] Auto-calculation runs
  - [ ] Results display correctly
- [ ] Verify Save button works
- [ ] Verify results are saved to exporter

### 4. Regression Testing
- [ ] Test other tabs still work (Rin, Spike, Event Detection)
- [ ] Verify no crashes or errors
- [ ] Check console for warnings

## Risk Mitigation

### Low Risk Changes:
- Adding new methods to BaseAnalysisTab (backward compatible)
- Adding attributes to __init__

### Medium Risk Changes:
- Modifying _on_analysis_item_selected to call new population method
- This could affect all tabs if not done carefully

### High Risk Changes:
- Removing methods from subclasses
- Changing signal connections

### Mitigation Strategy:
1. Make changes incrementally
2. Test after each major change
3. Keep git commits small and focused
4. Can revert easily if something breaks
5. Test on ONE tab first before applying to others

## Success Metrics

### Quantitative:
- ✅ Zero linting errors
- ✅ All existing tests pass
- ✅ No new console warnings/errors
- ✅ Code reduced by ~200 lines in RMP tab

### Qualitative:
- ✅ Code is more readable
- ✅ Future maintenance easier
- ✅ Functionality preserved exactly
- ✅ User experience unchanged

## Rollback Plan

If testing reveals issues:
1. Revert changes using git
2. Analyze what went wrong
3. Adjust approach
4. Try again with smaller changes

## Timeline

- Phase 1 (Pre-refactoring tests): 15 minutes
- Phase 2 (Refactor + test RMP tab): 30 minutes  
- Phase 3 (Validation): 15 minutes
- **Total**: ~1 hour for safe, tested refactoring of ONE tab

## Decision Point

After completing testing of RMP tab refactoring:
- ✅ **Proceed**: If all tests pass and functionality works
- ❌ **Stop**: If tests fail or functionality broken
- 🔄 **Adjust**: If minor issues found, fix and retest

---
*Test Plan Created: 2025-01-06*


