
import sys
import numpy as np
from PySide6 import QtWidgets, QtCore
from Synaptipy.application.gui.analysis_tabs.spike_tab import SpikeAnalysisTab
from Synaptipy.core.data_model import Recording, Channel
from Synaptipy.infrastructure.file_readers import NeoAdapter
from unittest.mock import MagicMock

def verify_accumulation():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    
    # Mock NeoAdapter
    neo_adapter = MagicMock(spec=NeoAdapter)
    
    # Create Tab
    tab = SpikeAnalysisTab(neo_adapter)
    tab.show()
    
    # Mock Recording with 2 trials
    recording = Recording(source_file=QtCore.QFileInfo("test.abf").absoluteFilePath())
    
    # Trial 1 data (simple sine wave)
    t = np.linspace(0, 1, 1000)
    data1 = np.sin(2 * np.pi * 5 * t) # 5 Hz
    
    # Trial 2 data (faster sine wave)
    data2 = np.sin(2 * np.pi * 10 * t) # 10 Hz
    
    channel = Channel(id="0", name="Primary", units="mV", sampling_rate=1000.0, data_trials=[data1, data2])
    
    recording.channels = {"0": channel}
    
    # Manually inject recording into tab (simulating selection)
    tab._selected_item_recording = recording
    tab._analysis_items = [{'target_type': 'Recording', 'path': 'test.abf'}]
    tab._selected_item_index = 0
    
    # Trigger UI update to populate combos
    tab._populate_channel_and_source_comboboxes()
    
    print("Comboboxes populated.")
    print(f"Channel Combo Count: {tab.signal_channel_combobox.count()}")
    print(f"Source Combo Count: {tab.data_source_combobox.count()}")
    
    if tab.data_source_combobox.count() < 2:
        print("FAIL: Expected at least 2 items in data source combo (Trial 1, Trial 2)")
        return

    # --- Test Trial 1 ---
    print("\nTesting Trial 1...")
    tab.data_source_combobox.setCurrentIndex(0) # Trial 1
    # Mock analysis result
    result1 = {'spike_count': 5, 'freq_hz': 5.0}
    tab._last_analysis_result = result1
    tab._last_spike_result = result1 # SpikeTab specific
    tab._set_save_button_enabled(True)
    tab._update_accumulation_ui_state()
    
    # Click Add to Session
    tab.add_to_session_button.click()
    print(f"Accumulated Results: {len(tab._accumulated_results)}")
    
    # --- Test Trial 2 ---
    print("\nTesting Trial 2...")
    tab.data_source_combobox.setCurrentIndex(1) # Trial 2
    # Mock analysis result
    result2 = {'spike_count': 10, 'freq_hz': 10.0}
    tab._last_analysis_result = result2
    tab._last_spike_result = result2 # SpikeTab specific
    tab._set_save_button_enabled(True)
    tab._update_accumulation_ui_state()
    
    # Click Add to Session
    tab.add_to_session_button.click()
    print(f"Accumulated Results: {len(tab._accumulated_results)}")
    
    if len(tab._accumulated_results) != 2:
        print("FAIL: Expected 2 accumulated results")
        return
        
    # --- Test View Session ---
    print("\nTesting View Session Dialog...")
    # Just check if we can instantiate it without error
    from Synaptipy.application.gui.session_summary_dialog import SessionSummaryDialog
    dialog = SessionSummaryDialog(tab._accumulated_results)
    print("Dialog created successfully.")
    
    print("\nSUCCESS: Verification Complete")
    tab.close()

if __name__ == "__main__":
    verify_accumulation()
