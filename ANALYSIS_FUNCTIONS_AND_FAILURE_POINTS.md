# Analysis Functions, UI Elements, and Failure Points

## Overview
This document provides a comprehensive list of all analysis functions in Synaptipy, their associated UI elements, and potential failure points.

---

## 1. Basic Features Analysis

### 1.1 Resting Membrane Potential (RMP) / Baseline Analysis

**Core Function:** `calculate_rmp()` in `src/Synaptipy/core/analysis/basic_features.py`
- **Location:** Lines 12-68
- **Function Signature:** `calculate_rmp(data: np.ndarray, time: np.ndarray, baseline_window: Tuple[float, float]) -> Optional[float]`

**UI Tab:** `BaselineAnalysisTab` in `src/Synaptipy/application/gui/analysis_tabs/rmp_tab.py`

**UI Elements:**
- `analysis_item_combo` - Selects analysis item from Explorer
- `signal_channel_combobox` - Selects signal channel
- `data_source_combobox` - Selects trial or average trace
- `mode_combobox` - Selects analysis mode (Interactive/Automatic/Manual)
- `interactive_region` (pg.LinearRegionItem) - Interactive region selector for baseline window
- `manual_start_time_spinbox` / `manual_end_time_spinbox` - Manual time window inputs
- `auto_sd_threshold_spinbox` - Auto-calculation threshold parameter
- `run_button` - Triggers manual/auto analysis
- `mean_sd_result_label` - Displays calculated mean ± SD
- `status_label` - Shows analysis status
- `save_button` - Saves results
- `plot_widget` - Displays trace with baseline visualization lines
- `baseline_mean_line`, `baseline_plus_sd_line`, `baseline_minus_sd_line` - Visualization lines

**Helper Function:** `calculate_baseline_stats()` in `rmp_tab.py` (Lines 22-48)
- Calculates mean and SD over a time window

**Failure Points:**

1. **Input Validation Failures:**
   - Invalid data array (not 1D numpy array, empty, wrong shape)
   - Time/data shape mismatch
   - Invalid baseline_window (not tuple, wrong length, non-numeric values)
   - Start time >= end time
   - No data points in baseline window (empty slice)

2. **Data Access Failures:**
   - Recording not loaded (`_selected_item_recording` is None)
   - Channel not found in recording
   - Trial index out of range
   - Average data not available when selected
   - Missing time vector or data vector

3. **Calculation Failures:**
   - IndexError during window slicing
   - Empty baseline data slice after filtering
   - Division by zero (shouldn't occur but defensive)
   - NaN/Inf values in data causing invalid mean

4. **UI State Failures:**
   - Mode combobox not initialized when `_on_mode_changed()` called
   - Plot widget cleared before regions added back
   - Interactive region bounds not set before use
   - Manual spinboxes not initialized before value access

5. **Auto-Calculation Specific Failures:**
   - Insufficient data points for mode calculation (< 10 points)
   - No unique voltage values after rounding
   - Initial SD estimate fails (empty noise window)
   - Tolerance band yields no matching points

6. **Visualization Failures:**
   - Plot items not added before setting visibility
   - InfiniteLine items removed but references still used
   - Grid pen alpha extraction fails (fallback to default)
   - Windows-specific pen application bugs

7. **Save Functionality Failures:**
   - `_last_baseline_result` is None when save clicked
   - Missing channel_id or data_source in result data
   - MainWindow `add_saved_result` method not found

---

## 2. Intrinsic Properties Analysis

### 2.1 Input Resistance (Rin) / Conductance

**Core Function:** `calculate_rin()` in `src/Synaptipy/core/analysis/intrinsic_properties.py`
- **Location:** Lines 13-65
- **Function Signature:** `calculate_rin(voltage_trace, time_vector, current_amplitude, baseline_window, response_window) -> Optional[float]`

**UI Tab:** `RinAnalysisTab` in `src/Synaptipy/application/gui/analysis_tabs/rin_tab.py`

**UI Elements:**
- `analysis_item_combo` - Selects analysis item
- `signal_channel_combobox` - Selects signal channel (voltage or current)
- `data_source_combobox` - Selects trial or average
- `mode_combobox` - Interactive (Regions) or Manual (Time Windows)
- `baseline_region` / `response_region` (pg.LinearRegionItem) - Interactive region selectors
- `manual_baseline_start_spinbox` / `manual_baseline_end_spinbox` - Manual baseline window
- `manual_response_start_spinbox` / `manual_response_end_spinbox` - Manual response window
- `manual_delta_i_spinbox` - Manual ΔI input (for voltage clamp)
- `manual_delta_v_spinbox` - Manual ΔV input (for current clamp)
- `run_button` - Triggers calculation
- `rin_result_label` - Displays Rin/G result
- `delta_v_label` / `delta_i_label` - Displays delta values
- `baseline_line` / `response_line` (pg.InfiniteLine) - Visualization lines
- `tau_button` / `sag_button` - Other property calculations
- `tau_result_label` / `sag_result_label` - Other property results

**Local Function:** `calculate_rin()` in `rin_tab.py` (Lines 31-95)
- Wrapper that handles delta I/V input

**Failure Points:**

1. **Input Validation Failures:**
   - Zero or near-zero delta_i_pa (division by zero)
   - Invalid time/data arrays (None, wrong shape)
   - Invalid window tuples (None, wrong length, start >= end)
   - No data points in baseline or response windows

2. **Data Access Failures:**
   - Recording not loaded
   - Channel not found
   - Trial index out of range
   - Average data unavailable
   - Missing sampling rate

3. **Mode-Specific Failures:**
   - Interactive: Regions not available when accessed
   - Interactive: Region bounds not set before use
   - Manual: Spinboxes not initialized
   - Manual: Invalid time window values (start >= end)

4. **Channel Type Detection Failures:**
   - Units string parsing fails (can't determine voltage vs current)
   - Wrong delta input field shown/hidden
   - Delta input not provided when required

5. **Calculation Failures:**
   - IndexError during window masking
   - Empty arrays after filtering
   - Mean calculation on empty arrays
   - Division by zero (delta_i = 0)

6. **Visualization Failures:**
   - Regions removed from plot but still referenced
   - Lines not added to plot before setting value
   - Plot cleared but regions not re-added
   - Windows-specific rendering issues

7. **UI State Management Failures:**
   - Mode changed before plot data loaded
   - Delta input visibility not updated on channel change
   - Run button state not updated on input change
   - Plot item reference lost after clear

### 2.2 Membrane Time Constant (Tau)

**Core Function:** `calculate_tau()` in `src/Synaptipy/core/analysis/intrinsic_properties.py`
- **Location:** Lines 72-113
- **Function Signature:** `calculate_tau(voltage_trace, time_vector, stim_start_time, fit_duration) -> Optional[float]`

**UI Elements:**
- `tau_button` - Triggers calculation
- `tau_result_label` - Displays result

**Failure Points:**

1. **Input Validation Failures:**
   - Invalid time/data arrays
   - Fit window outside data range
   - Insufficient data points for fitting (< 3 points)

2. **Fitting Failures:**
   - `curve_fit` RuntimeError (optimal parameters not found)
   - Initial guess values invalid
   - Bounds too restrictive
   - Data too noisy for reliable fit

3. **Data Access Failures:**
   - Response region not set
   - Stim start time invalid
   - Fit duration too short

### 2.3 Sag Ratio

**Core Function:** `calculate_sag_ratio()` in `src/Synaptipy/core/analysis/intrinsic_properties.py`
- **Location:** Lines 117-156
- **Function Signature:** `calculate_sag_ratio(voltage_trace, time_vector, baseline_window, response_peak_window, response_steady_state_window) -> Optional[float]`

**UI Elements:**
- `sag_button` - Triggers calculation
- `sag_result_label` - Displays result

**Failure Points:**

1. **Input Validation Failures:**
   - Invalid windows (no data points)
   - Division by zero (delta_v_ss = 0)

2. **Data Access Failures:**
   - Baseline/peak/steady-state windows not set
   - Windows outside data range

3. **Calculation Failures:**
   - Peak not found (all values same)
   - Steady-state calculation fails

---

## 3. Spike Analysis

### 3.1 Threshold-Based Spike Detection

**Core Function:** `detect_spikes_threshold()` in `src/Synaptipy/core/analysis/spike_analysis.py`
- **Location:** Lines 12-99
- **Function Signature:** `detect_spikes_threshold(data, time, threshold, refractory_samples) -> Tuple[np.ndarray, np.ndarray]`

**UI Tab:** `SpikeAnalysisTab` in `src/Synaptipy/application/gui/analysis_tabs/spike_tab.py`

**UI Elements:**
- `analysis_item_combo` - Selects analysis item
- `channel_combobox` - Selects signal channel
- `data_source_combobox` - Selects trial or average
- `threshold_edit` - Threshold value input
- `refractory_edit` - Refractory period input (ms)
- `detect_button` - Triggers detection
- `results_textedit` - Displays spike statistics
- `plot_widget` - Displays trace with spike markers
- `voltage_plot_item` - Main trace plot
- `spike_markers_item` (pg.ScatterPlotItem) - Spike markers
- `threshold_line` (pg.InfiniteLine) - Threshold visualization

**Helper Function:** `calculate_spike_features()` in `spike_analysis.py` (Lines 102-180)
- Calculates detailed spike features (amplitude, half-width, AHP depth, dV/dt)

**Helper Function:** `calculate_isi()` in `spike_analysis.py` (Lines 183-187)
- Calculates inter-spike intervals

**Failure Points:**

1. **Input Validation Failures:**
   - Invalid data array (not 1D, empty, < 2 samples)
   - Time/data shape mismatch
   - Invalid threshold (not numeric)
   - Invalid refractory_samples (not int, negative)

2. **Data Access Failures:**
   - Recording not loaded
   - Channel not found
   - Trial index out of range
   - Missing sampling rate
   - Missing time or voltage vectors

3. **Detection Failures:**
   - No threshold crossings found
   - Peak search window exceeds data bounds
   - IndexError during peak finding
   - ValueError if slice empty during peak search

4. **Feature Calculation Failures:**
   - Spike indices out of bounds
   - AP threshold not found (dvdt too low)
   - Half-width calculation fails (no crossings)
   - AHP depth calculation fails (no minimum found)
   - dV/dt calculation fails (gradient issues)

5. **UI State Failures:**
   - Parameters not validated before detection
   - Plot cleared but markers not re-added
   - Threshold line not visible
   - Results text not cleared on new detection

6. **Visualization Failures:**
   - Spike markers not added to plot
   - Marker brush not applied (Windows bug)
   - Threshold line position incorrect
   - Plot auto-range fails

7. **Save Functionality Failures:**
   - No spike data in `_current_plot_data`
   - Invalid spike_times array
   - Missing parameters for saving
   - Channel/data_source not selected

---

## 4. Event Detection Analysis

### 4.1 Threshold-Based Event Detection

**Core Function:** `detect_events_threshold_crossing()` in `src/Synaptipy/core/analysis/event_detection.py`
- **Location:** Lines 139-180
- **Function Signature:** `detect_events_threshold_crossing(data, threshold, direction) -> Tuple[np.ndarray, Dict[str, Any]]`

**UI Tab:** `EventDetectionTab` in `src/Synaptipy/application/gui/analysis_tabs/event_detection_tab.py`

**UI Elements:**
- `analysis_item_combo` - Selects analysis item
- `channel_combobox` - Selects signal channel
- `data_source_combobox` - Selects trial or average
- `sub_tab_widget` - Miniature/Evoked sub-tabs
- `mini_method_combobox` - Selects detection method
- `mini_direction_combo` - Event direction (negative/positive)
- `mini_threshold_edit` - Threshold value
- `mini_params_stack` - Stacked widget for method-specific parameters
- `mini_detect_button` - Triggers detection
- `mini_results_textedit` - Displays results
- `plot_widget` - Displays trace with event markers
- `data_plot_item` - Main trace plot
- `event_markers_item` (pg.ScatterPlotItem) - Event markers

**Failure Points:**

1. **Input Validation Failures:**
   - Invalid data array (not 1D, empty, < 2 samples)
   - Invalid threshold (not numeric)
   - Invalid direction (not 'positive' or 'negative')
   - Threshold sign contradicts direction

2. **Data Access Failures:**
   - Recording not loaded
   - Channel not found
   - Missing sampling rate
   - Missing time or data vectors

3. **Detection Failures:**
   - No threshold crossings found
   - Event start indices calculation fails
   - Empty crossings array handling

### 4.2 Deconvolution-Based Event Detection

**Core Function:** `detect_events_deconvolution_custom()` in `src/Synaptipy/core/analysis/event_detection.py`
- **Location:** Lines 191-334
- **Function Signature:** `detect_events_deconvolution_custom(data, sample_rate, tau_rise_ms, tau_decay_ms, threshold_sd, filter_freq_hz, min_event_separation_ms, regularization_factor) -> Tuple[np.ndarray, Dict[str, Any]]`

**UI Elements:**
- `mini_deconv_tau_rise_spinbox` - Tau rise parameter
- `mini_deconv_tau_decay_spinbox` - Tau decay parameter
- `mini_deconv_filter_spinbox` - Filter cutoff frequency
- `mini_deconv_threshold_sd_spinbox` - Detection threshold (SD multiples)

**Failure Points:**

1. **Parameter Validation Failures:**
   - tau_decay <= tau_rise (raises ValueError)
   - Filter frequency >= Nyquist frequency
   - Invalid sample rate (<= 0)
   - Negative time constants

2. **Filtering Failures:**
   - Butterworth filter design fails
   - Filter application fails (sosfiltfilt error)
   - Filter frequency too high for data

3. **Kernel Generation Failures:**
   - Kernel length calculation fails
   - Kernel peak near zero (division issues)
   - Kernel too long for data length

4. **Deconvolution Failures:**
   - FFT computation fails
   - Regularization epsilon too small (numerical instability)
   - Kernel power spectrum issues
   - IFFT fails or produces invalid results

5. **Noise Estimation Failures:**
   - Deconvolved trace too short for MAD
   - MAD calculation fails
   - Fallback noise estimate fails
   - Zero SD causes division issues

6. **Peak Finding Failures:**
   - `scipy.signal.find_peaks` fails
   - Detection level too high/low
   - Min distance too large for data
   - No peaks found

### 4.3 Baseline + Peak + Kinetics Detection

**Core Function:** `detect_events_baseline_peak_kinetics()` in `src/Synaptipy/core/analysis/event_detection.py`
- **Location:** Lines 452-571
- **Function Signature:** `detect_events_baseline_peak_kinetics(data, sample_rate, direction, baseline_window_s, baseline_step_s, threshold_sd_factor, filter_freq_hz, min_event_separation_ms, peak_prominence_factor) -> Tuple[np.ndarray, Dict[str, Any], Optional[List[Dict[str, Any]]]]`

**Helper Functions:**
- `_find_stable_baseline_segment()` (Lines 337-389) - Finds stable baseline
- `_calculate_simplified_kinetics()` (Lines 392-449) - Calculates rise/decay times

**UI Elements:**
- `mini_baseline_filter_spinbox` - Filter cutoff frequency
- `mini_baseline_prominence_spinbox` - Peak prominence factor

**Failure Points:**

1. **Baseline Finding Failures:**
   - Window duration too large for data
   - Step duration invalid
   - No stable segment found (all variance high)
   - Baseline SD near zero (division issues)

2. **Filtering Failures:**
   - Filter frequency >= Nyquist
   - Filter application fails
   - Filtered signal invalid

3. **Peak Detection Failures:**
   - `scipy.signal.find_peaks` fails
   - Prominence calculation fails
   - Height threshold too high/low
   - Min distance issues

4. **Kinetics Calculation Failures:**
   - Peak index out of bounds
   - Rise time calculation fails (no 10%/90% crossings)
   - Decay time calculation fails (no 50% crossing)
   - Relative amplitude near zero (division issues)
   - Search windows exceed data bounds

5. **Data Access Failures:**
   - Baseline mean/SD calculation fails
   - Peak indices invalid
   - Time vector missing

---

## 5. Common Failure Points Across All Analysis Functions

### 5.1 Data Loading Failures
- File not found
- File format not supported
- Corrupted file data
- Neo adapter read failures
- Lazy loading failures

### 5.2 UI State Management Failures
- Widgets not initialized when accessed
- Signals connected before widgets created
- Blocked signals not unblocked
- Plot cleared but items not re-added
- Mode changes before data loaded

### 5.3 Plotting Failures
- Plot widget not initialized
- Data vectors None or empty
- Time/data length mismatch
- PyQtGraph rendering issues (Windows-specific)
- Pen/brush not applied (Windows bug workaround)
- Grid configuration failures
- Auto-range failures

### 5.4 Save Functionality Failures
- `_get_specific_result_data()` returns None
- Missing required fields in result data
- MainWindow `add_saved_result` not found
- Invalid file path
- Save dialog cancelled

### 5.5 Threading/Concurrency Issues
- UI updates from non-main thread
- Cursor override not restored
- Long-running calculations blocking UI

### 5.6 Memory Issues
- Large data arrays causing memory errors
- Plot items not cleaned up
- References not cleared (memory leaks)

### 5.7 Error Handling Gaps
- Exceptions not caught in signal handlers
- Error messages not user-friendly
- Logging not comprehensive
- Error recovery not implemented

---

## 6. Recommendations for Improvement

1. **Input Validation:**
   - Add comprehensive validation at function entry
   - Provide clear error messages
   - Validate UI inputs before passing to core functions

2. **Error Handling:**
   - Catch all exceptions in UI handlers
   - Provide user-friendly error messages
   - Log errors with full context
   - Implement graceful degradation

3. **State Management:**
   - Initialize all widgets before use
   - Check widget existence before access
   - Use guard clauses extensively
   - Clear state on errors

4. **Testing:**
   - Unit tests for all analysis functions
   - Integration tests for UI workflows
   - Edge case testing (empty data, invalid inputs)
   - Performance testing for large datasets

5. **Documentation:**
   - Document all failure modes
   - Add examples of valid inputs
   - Document expected behavior on errors

6. **Code Quality:**
   - Reduce code duplication
   - Extract common validation logic
   - Improve type hints
   - Add docstrings with failure conditions

---

## 7. Summary Statistics

- **Total Analysis Functions:** 8 core functions + 3 helper functions
- **Total UI Tabs:** 4 analysis tabs
- **Total UI Elements:** ~50+ widgets across all tabs
- **Identified Failure Points:** 100+ distinct failure scenarios

---

*Document generated: 2024*
*Last updated: Based on current codebase analysis*
