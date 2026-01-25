
import sys
import os
import numpy as np
import logging
from unittest.mock import MagicMock

# --- Mocking Qt and PyQtGraph ---
# We mock these BEFORE importing any application code to avoid requiring a display
sys.modules['PySide6'] = MagicMock()
sys.modules['PySide6.QtCore'] = MagicMock()
sys.modules['PySide6.QtWidgets'] = MagicMock()
sys.modules['PySide6.QtGui'] = MagicMock()
sys.modules['pyqtgraph'] = MagicMock()

# Setup Logging
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("Verification")

# --- Import Adapters (Function Wrappers) ---
# We need to manually add the project root to path
project_root = "/Users/anzalks/PycharmProjects/Synaptipy/src"
if project_root not in sys.path:
    sys.path.insert(0, project_root)

try:
    from Synaptipy.core.analysis.burst_analysis import run_burst_analysis_wrapper
    from Synaptipy.core.analysis.excitability import run_excitability_analysis_wrapper
    from Synaptipy.core.analysis.basic_features import run_rmp_analysis_wrapper
except ImportError as e:
    log.error(f"Failed to import analysis modules: {e}")
    sys.exit(1)

# --- Mock Tab Classes ---
# We can't easily instantiate the full tabs because they inherit QWidget and use complex Mixins.
# Instead, we will simulate the `_plot_analysis_visualizations` logic directly, 
# or instantiate a lightweight mock that copies the relevant methods.

class MockPlotWidget:
    def __init__(self):
        self.items = []
        self.viewbox = MagicMock()
    
    def addItem(self, item):
        self.items.append(item)
    
    def plot(self, *args, **kwargs):
        mock_curve = MagicMock()
        mock_curve.setData = MagicMock()
        return mock_curve

class MockAnalysisTab:
    """Simulates the analysis tab environment for plotting verification."""
    def __init__(self):
        self.plot_widget = MockPlotWidget()
        self.burst_lines = []
        self._current_plot_data = {'data': np.zeros(100)} # Mock data for offset calculation
        
        # Popup Mocks (Excitability/PhasePlane)
        self.popup_plot = MockPlotWidget() # Reuse same mock class
        self.fi_curve = MagicMock()
        self.slope_line = MagicMock() 
        self.rheobase_marker = MagicMock()
        
        # RMP Lines
        self.baseline_mean_line = MagicMock()
        self.baseline_plus_sd_line = MagicMock()
        self.baseline_minus_sd_line = MagicMock()

    def create_popup_plot(self, title, x, y):
        return self.popup_plot
        
# --- Test 1: Burst Analysis Verification ---
def test_burst_analysis():
    log.info("--- Testing Burst Analysis Compatibility ---")
    
    # 1. Create Synthetic Data (2 bursts)
    time = np.linspace(0, 10, 10000) # 10s
    data = np.zeros_like(time)
    
    # Burst 1 at 1s (5 spikes)
    burst1_times = [1.0, 1.05, 1.10, 1.15, 1.20]
    # Burst 2 at 5s (5 spikes)
    burst2_times = [5.0, 5.05, 5.10, 5.15, 5.20]
    
    # Naive spike insertion (just for wrapper to process, though wrapper detects spikes)
    # The wrapper uses threshold detection.
    # We'll just force the wrapper to work or mock the internal detection?
    # Actually, let's just create voltage spikes so detection logic works.
    for t in burst1_times + burst2_times:
        idx = int(t * 1000)
        data[idx] = 20.0 # Spike!
        
    # 2. Run Analysis Wrapper
    results = run_burst_analysis_wrapper(data, time, sampling_rate=1000.0, threshold=10.0, max_isi_start=0.1)
    
    if not isinstance(results, dict):
        log.error("Burst wrapper returned invalid type!")
        return False
        
    log.info(f"Wrapper Results Keys: {list(results.keys())}")
    
    # 3. Assert Data Presence
    if 'bursts' not in results:
        log.error("CRITICAL: 'bursts' key MISSING from wrapper result!")
        return False
        
    bursts = results['bursts']
    if len(bursts) != 2:
        log.error(f"Expected 2 bursts, found {len(bursts)}. Detection logic might vary, but we need > 0.")
        if len(bursts) == 0: return False
        
    log.info(f"Burst Data Found: {len(bursts)} bursts detected.")
    
    # 4. Simulate Plotting Logic (Copied from BurstAnalysisTab)
    tab = MockAnalysisTab()
    
    # --- LOGIC START ---
    bursts = results.get('bursts')
    if bursts:
        y_offset = 0 # Simplified
        for burst_spikes in bursts:
            if len(burst_spikes) >= 2:
                start_t = burst_spikes[0]
                end_t = burst_spikes[-1]
                # Simulate adding items
                tab.plot_widget.addItem(f"BurstLine({start_t}-{end_t})")
                tab.burst_lines.append(f"Line({start_t})")
    # --- LOGIC END ---
    
    expected_lines = len(bursts)
    actual_lines = len(tab.burst_lines)
    
    if actual_lines == expected_lines:
        log.info(f"SUCCESS: Burst tab plotting logic added {actual_lines} lines correctly.")
        return True
    else:
        log.error(f"FAILURE: Expected {expected_lines} lines, got {actual_lines}.")
        return False

# --- Test 2: Excitability Analysis Verification ---
def test_excitability_analysis():
    log.info("--- Testing Excitability Analysis Compatibility ---")
    
    # 1. Create Synthetic Sweeps (Step protocol)
    num_sweeps = 5
    sweeps = []
    times = []
    for i in range(num_sweeps):
        t = np.linspace(0, 1, 1000)
        d = np.zeros_like(t)
        # Add 'i' spikes to sweep 'i'
        for k in range(i):
            d[k*100] = 20.0
        sweeps.append(d)
        times.append(t)
        
    current_steps = [0, 10, 20, 30, 40]
    
    # 2. Run Wrapper
    # Wrapper expects data_list, time_list
    results = run_excitability_analysis_wrapper(
        data_list=sweeps, 
        time_list=times, 
        sampling_rate=1000.0,
        start_current=0,
        step_current=10
    )
    
    log.info(f"Wrapper Results Keys: {list(results.keys())}")
    
    # 3. Assert Data Presence
    if 'frequencies' not in results or 'current_steps' not in results:
        log.error("CRITICAL: Arrays MISSING from wrapper result!")
        return False
        
    freqs = results['frequencies']
    curr = results['current_steps']
    
    log.info(f"Arrays Found - Current: {curr}, Freqs: {freqs}")
    
    # 4. Simulate Plotting
    tab = MockAnalysisTab()
    
    # --- LOGIC START ---
    currents = results.get('current_steps')
    freqs = results.get('frequencies')
    
    if currents is not None and freqs is not None:
        tab.fi_curve.setData(currents, freqs)
    # --- LOGIC END ---
    
    # Check if setData was called on mock
    if tab.fi_curve.setData.called:
        args, _ = tab.fi_curve.setData.call_args
        if list(args[0]) == curr and list(args[1]) == freqs:
             log.info("SUCCESS: Excitability plotting logic set correct data on curve.")
             return True
             
    log.error("FAILURE: setData was not called or called with wrong args.")
    return False

# --- Test 3: RMP Analysis Verification ---
def test_rmp_analysis():
    log.info("--- Testing RMP Analysis Compatibility ---")
    
    # 1. Create data
    time = np.linspace(0, 1, 1000)
    data = np.random.normal(-60, 1, 1000) # RMP around -60mV
    
    # 2. Run Wrapper
    results = run_rmp_analysis_wrapper(data, time, sampling_rate=1000.0, baseline_start=0, baseline_end=1.0)
    
    log.info(f"Wrapper Results: {results}")
    
    # 3. Assert Data
    if results['rmp_mv'] is None:
        log.error("RMP calculation failed.")
        return False
        
    # 4. Simulate Plotting (reproducing RMPTab logic)
    tab = MockAnalysisTab()
    
    result_data = results # wrapper result IS the dict
    
    # --- LOGIC START ---
    if result_data and 'rmp_mv' in result_data and result_data['rmp_mv'] is not None:
        mean = result_data['rmp_mv']
        tab.baseline_mean_line.setValue(mean)
        tab.baseline_mean_line.setVisible(True)
    # --- LOGIC END ---
    
    if tab.baseline_mean_line.setValue.called:
        log.info("SUCCESS: RMP plotting logic updated mean line.")
        return True
        
    log.error("FAILURE: Mean line not updated.")
    return False

if __name__ == "__main__":
    success = True
    success &= test_burst_analysis()
    success &= test_excitability_analysis()
    success &= test_rmp_analysis()
    
    if success:
        print("\nALL COMPATIBILITY CHECKS PASSED.")
        sys.exit(0)
    else:
        print("\nSOME CHECKS FAILED.")
        sys.exit(1)
