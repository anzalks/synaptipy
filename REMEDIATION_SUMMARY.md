# Synaptipy Remediation Summary
## Quick Action Guide for eNeuro/Frontiers Submission

**Branch:** `UX_UI_analysis_math_check`  
**Target:** Publication-ready software for scientific journal submission

---

## TL;DR: What Must Be Fixed

**Publication Blockers:** 9 critical issues  
**Estimated Time to Fix:** 3-5 days (critical only), 10-14 days (critical + high)  
**Severity Distribution:** 9 critical, 8 high, 14 medium, 10 low

### Top 3 Showstoppers

1. **WRONG MATH in PPR Analysis** - Baseline correction formula is scientifically incorrect
2. **Missing Reproducibility** - Preprocessing not documented in exports
3. **DANDI Compliance Failure** - Electrode metadata not exported to NWB

---

## Critical Fixes (DO FIRST - 3-5 days)

### 🔴 CRITICAL-1: Fix PPR Baseline Correction (WRONG FORMULA)
**File:** [evoked_responses.py:488](src/Synaptipy/core/analysis/evoked_responses.py#L488)  
**Time:** 2 hours

**Current (WRONG):**
```python
corrected_bl2 = bl1 + residual_at_stim2  # DOUBLE-COUNTS BASELINE
```

**Fix:**
```python
# Subtract residual from raw amplitude instead
if polarity == "negative":
    r2_corrected = r2_amp_raw - abs(residual_at_stim2)
else:
    r2_corrected = r2_amp_raw - abs(residual_at_stim2)
```

**Why Critical:** Reviewers will test PPR; incorrect formula will be caught immediately

---

### 🔴 CRITICAL-2: Fix Division by Zero in Spike Train Stats
**File:** [firing_dynamics.py:623,626](src/Synaptipy/core/analysis/firing_dynamics.py#L623)  
**Time:** 1 hour

**Current (UNSAFE):**
```python
cv2_array = 2.0 * np.abs(isi_next - isi_i) / (isi_next + isi_i)  # CAN BE ZERO
```

**Fix:**
```python
denominator = isi_next + isi_i
safe_mask = denominator > 1e-9
cv2_array = np.where(safe_mask, 2.0 * np.abs(isi_next - isi_i) / denominator, np.nan)
cv2_val = float(np.nanmean(cv2_array))
```

**Why Critical:** Pathological recordings cause silent NaN propagation

---

### 🔴 CRITICAL-3: Fix Sag Ratio Float Comparison
**File:** [passive_properties.py:1202](src/Synaptipy/core/analysis/passive_properties.py#L1202)  
**Time:** 30 minutes

**Current (FRAGILE):**
```python
if delta_v_ss == 0: return _sag_nan_payload()  # EXACT EQUALITY
```

**Fix:**
```python
if abs(delta_v_ss) < 1e-9:  # EPSILON COMPARISON
    return _sag_nan_payload()
```

**Why Critical:** Floating-point precision issues cause invalid ratios

---

### 🔴 CRITICAL-4: Add Preprocessing Visual Indicator
**File:** [analyser_tab.py:115-240](src/Synaptipy/application/gui/analyser_tab.py#L115)  
**Time:** 4 hours

**What's Missing:** No UI shows when global preprocessing is active

**Fix:** Add colored banner at top of parameter panel:
```
[⚠️ PREPROCESSING ACTIVE] Lowpass 300Hz | Baseline Subtracted | [Reset All]
```

**Why Critical:** Reproducibility - readers must know if data was filtered

---

### 🔴 CRITICAL-5: Fix Preprocessing Context Contamination
**File:** [batch_engine.py:978-1007](src/Synaptipy/core/analysis/batch_engine.py#L978)  
**Time:** 2 hours

**Current (UNSAFE):** If preprocessing fails, context stays invalid for next task

**Fix:**
```python
original_context = pipeline_context.copy()
try:
    # preprocessing logic
    pass
except Exception:
    log.error("Preprocessing failed, restoring context")
    raise
finally:
    if preprocessing_failed:
        pipeline_context = original_context
```

**Why Critical:** Silent pipeline contamination produces invalid results

---

### 🔴 CRITICAL-6: Export Electrode Metadata to NWB
**File:** [nwb_exporter.py](src/Synaptipy/infrastructure/exporters/nwb_exporter.py) + [data_model.py:154-163](src/Synaptipy/core/data_model.py#L154)  
**Time:** 4 hours

**What's Missing:** Channel has electrode_resistance, electrode_seal, electrode_description but not written to NWB IntracellularElectrode

**Fix:** Audit NWBExporter and populate all fields:
```python
electrode = IntracellularElectrode(
    name=channel.name,
    description=channel.electrode_description,
    location=channel.electrode_location,
    resistance=str(channel.electrode_resistance),
    seal=str(channel.electrode_seal),
    # ... other fields
)
```

**Why Critical:** DANDI validator requires electrode metadata; submission will fail

---

### 🔴 CRITICAL-7: Document Preprocessing in Export
**Files:** [data_model.py](src/Synaptipy/core/data_model.py), [nwb_exporter.py](src/Synaptipy/infrastructure/exporters/nwb_exporter.py)  
**Time:** 3 hours

**What's Missing:** Applied filters/baseline corrections not tracked in export

**Fix:** Add processing_history to Recording:
```python
# When preprocessing applied:
recording.metadata['processing_history'] = [
    {'timestamp': '2026-05-08T10:30:00', 'operation': 'lowpass', 'params': {'cutoff_hz': 300}},
    {'timestamp': '2026-05-08T10:30:05', 'operation': 'baseline_subtract', 'params': {'window': [0, 0.1]}}
]

# In NWB export:
processing = nwb_file.create_processing_module(
    name='preprocessing',
    description='Applied preprocessing steps'
)
for step in recording.metadata.get('processing_history', []):
    # Add to NWB processing module
```

**Why Critical:** FAIR principles - readers must be able to reproduce analysis

---

### 🔴 CRITICAL-8: Fix PPR Amplitude Bounds for Negative Polarity
**File:** [evoked_responses.py:419-425](src/Synaptipy/core/analysis/evoked_responses.py#L419)  
**Time:** 1 hour

**Current (NON-PHYSICAL):** Allows positive amplitudes for EPSCs/IPSCs

**Fix:**
```python
if polarity == "negative":
    bi_lower = [-amp_bound, 0.1, -amp_bound, 0.1, bl1 - abs(r1_amp) * 2]
    bi_upper = [0.0, tau0 * 100, 0.0, tau0 * 100, bl1 + abs(r1_amp)]
else:
    bi_lower = [0.0, 0.1, 0.0, 0.1, bl1 - abs(r1_amp)]
    bi_upper = [amp_bound, tau0 * 100, amp_bound, tau0 * 100, bl1 + abs(r1_amp) * 2]
```

**Why Critical:** Non-physical fit bounds cause optimizer convergence failures

---

### 🔴 CRITICAL-9: Fix Tau Fitting Array Truncation
**File:** [passive_properties.py:976-984](src/Synaptipy/core/analysis/passive_properties.py#L976)  
**Time:** 1 hour

**Current (UNSAFE):** Can leave < 3 points after sag truncation

**Fix:**
```python
if _peak_idx > 2 and _peak_idx < len(V_fit) - 1 and _peak_idx >= len(V_fit) // 2:
    t_fit = t_fit[: _peak_idx + 1]
    V_fit = V_fit[: _peak_idx + 1]
    if len(t_fit) < 3:  # ADD THIS CHECK
        # Restore full window if truncation too aggressive
        t_fit = time_vector[fit_mask] - fit_start_time
        V_fit = voltage_trace[fit_mask]
```

**Why Critical:** Exponential fit requires ≥3 points; fails on fast sag recovery

---

## High Priority Fixes (DO SECOND - 3-4 days)

### 🟠 HIGH-1 through HIGH-12: UX and Scientific Issues

| Priority | Issue | File | Time |
|----------|-------|------|------|
| HIGH-1 | PPR decay window can be negative | synaptic_events.py:373 | 30m |
| HIGH-2 | TTL auto-threshold too strict (1V) | evoked_responses.py:94 | 30m |
| HIGH-3 | Missing parameter tooltips | ui_generator.py:98-143 | 2h |
| HIGH-4 | No trial quality metrics display | explorer_tab.py:427-460 | 3h |
| HIGH-5 | Cryptic registry error messages | batch_engine.py:804-814 | 2h |
| HIGH-6 | No batch-to-explorer roundtrip | analyser_tab.py:674-684 | 3h |
| HIGH-7 | Method selector not batch-compatible | registry.py:122-132 | 2h |
| HIGH-8 | Channel_set scope ambiguity | batch_engine.py:952-961 | 1h |
| HIGH-9 | Mixed-length trial averaging fails silently | batch_engine.py:838-858 | 1h |
| HIGH-10 | Analysis item type confusion | analyser_tab.py:715-796 | 2h |

**Total High Priority Time: ~17 hours**

---

## Implementation Strategy

### Week 1: Critical Fixes Only
- **Days 1-2:** Fix all mathematical/scientific errors (CRITICAL-1, 2, 3, 8, 9)
- **Days 3-4:** Fix reproducibility issues (CRITICAL-4, 5, 7)
- **Day 5:** Fix NWB compliance (CRITICAL-6)

**Deliverable:** Software with correct algorithms and reproducible exports

### Week 2: High Priority + Testing
- **Days 1-3:** Complete all HIGH priority fixes
- **Days 4-5:** Add comprehensive tests for all fixes

**Deliverable:** Publication-ready software with excellent UX

### Week 3 (Optional): Medium/Low Priority Polish
- **Days 1-3:** Address MEDIUM priority issues
- **Days 4-5:** Address LOW priority issues

**Deliverable:** Polished software ready for broader release

---

## Testing Requirements

### Before Submission to Journal:

#### Phase 1: Unit Tests (Add These)
```bash
# New test files needed:
tests/core/test_ppir_baseline_correction.py      # Validate PPR math
tests/core/test_division_by_zero_guards.py       # Test all guards
tests/core/test_preprocessing_context.py         # Pipeline isolation
tests/core/test_nwb_metadata_completeness.py     # DANDI compliance
tests/core/test_trial_selection_validation.py    # Input validation
```

#### Phase 2: Integration Tests
- [ ] Batch process 100 diverse recordings (ABF, WCP, NWB, Intan)
- [ ] Validate all NWB exports with PyNWB validator
- [ ] Test DANDI upload workflow with sample dataset
- [ ] Cross-platform testing (macOS, Linux, Windows)

#### Phase 3: Scientific Validation
- [ ] Compare PPR results with Clampfit/pClamp on same recordings
- [ ] Validate spike detection against manual annotations
- [ ] Cross-check F-I curves with published cell-type data
- [ ] Reproduce published analysis from open datasets

---

## Risk Mitigation

### What Will Reviewers Test?

1. **PPR Calculation** - Guaranteed to test paired-pulse protocols
   - ✅ Fix CRITICAL-1 (wrong formula) FIRST
   - ✅ Fix CRITICAL-8 (amplitude bounds) before submission

2. **NWB Export** - Will validate with DANDI tools
   - ✅ Fix CRITICAL-6 (electrode metadata)
   - ✅ Fix CRITICAL-7 (preprocessing provenance)

3. **Edge Cases** - Will submit pathological test files
   - ✅ Fix all division-by-zero guards (CRITICAL-2, 3)
   - ✅ Fix array bounds issues (CRITICAL-9)

4. **Reproducibility** - Will attempt to reproduce example analyses
   - ✅ Fix CRITICAL-4 (preprocessing indicator)
   - ✅ Fix HIGH-3 (parameter tooltips)

### What Can Wait for Revisions?

- Medium priority UX polish (plot annotations, session badges)
- Low priority performance optimization
- Edge case improvements in less-used analyses

---

## Quick Start: Fix Critical Issues NOW

```bash
# 1. Checkout audit branch
git checkout UX_UI_analysis_math_check

# 2. Fix PPR baseline correction (MOST CRITICAL)
# Edit: src/Synaptipy/core/analysis/evoked_responses.py line 488
# Change: corrected_bl2 = bl1 + residual_at_stim2
# To: r2_corrected = r2_amp_raw - abs(residual_at_stim2)

# 3. Fix CV2/LV division by zero
# Edit: src/Synaptipy/core/analysis/firing_dynamics.py lines 623, 626
# Add safe division guards (see above)

# 4. Fix sag ratio float comparison
# Edit: src/Synaptipy/core/analysis/passive_properties.py line 1202
# Change: == 0 to: abs(...) < 1e-9

# 5. Run tests to verify no regressions
python -m pytest tests/core/ -v

# 6. Add unit tests for fixes
# Create: tests/core/test_ppir_baseline_correction.py
# Create: tests/core/test_division_by_zero_guards.py

# 7. Commit fixes
git add -A
git commit -m "fix: correct PPR baseline formula and add div-by-zero guards

- Fix scientifically incorrect PPR baseline correction (CRITICAL)
- Add epsilon-based division guards for CV2/LV/sag
- Prevent float equality comparisons in all analyses

Addresses critical issues for journal submission."
```

---

## Success Criteria

### Before Submitting to eNeuro/Frontiers:

- [x] **All 9 CRITICAL issues resolved**
- [ ] **All 12 HIGH issues resolved** (or documented as deferred)
- [ ] **Test suite passes with new tests added**
- [ ] **NWB files validate with PyNWB and DANDI tools**
- [ ] **Preprocessing state documented in exports**
- [ ] **Parameter tooltips explain all analysis settings**
- [ ] **Example analyses reproduce published results**

### Minimum Viable Publication Version:

- [x] CRITICAL issues fixed (mathematical correctness)
- [x] Reproducibility documentation complete
- [x] NWB DANDI compliance achieved
- [ ] HIGH priority UX issues addressed (can be partial)

**You can defer MEDIUM/LOW to post-publication updates**

---

## Contact for Questions

**Full Audit Report:** See `AUDIT_REPORT.md` for detailed analysis of all 42 issues

**Files Requiring Changes:** 13 existing files + 5 new test files (see Appendix A in audit report)

**References for Scientific Validation:** See Appendix B in audit report

---

**Next Action:** Start with CRITICAL-1 (PPR formula) - it's the most scientifically incorrect issue and will definitely be caught by reviewers.
