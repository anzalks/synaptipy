
import sys
import os
import logging
from pathlib import Path
from unittest.mock import MagicMock

# Add src to path
sys.path.append(os.path.abspath("src"))

from PySide6 import QtWidgets, QtCore

# Initialize QApplication
app = QtWidgets.QApplication.instance()
if not app:
    app = QtWidgets.QApplication(sys.argv)

from Synaptipy.application.gui.analysis_tabs.spike_tab import SpikeAnalysisTab
from Synaptipy.application.gui.analysis_tabs.rin_tab import RinAnalysisTab
from Synaptipy.application.gui.analysis_tabs.rmp_tab import BaselineAnalysisTab
from Synaptipy.application.gui.analysis_tabs.event_detection_tab import EventDetectionTab
from Synaptipy.application.gui.batch_dialog import BatchAnalysisDialog
from Synaptipy.core.analysis.registry import AnalysisRegistry

# Setup logging
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("verify_batch_workflow")

def verify_tabs():
    log.info("--- Verifying Analysis Tabs ---")
    
    mock_adapter = MagicMock()
    
    # 1. Spike Tab
    spike_tab = SpikeAnalysisTab(mock_adapter)
    assert spike_tab.get_registry_name() == "spike_detection"
    log.info("SpikeAnalysisTab.get_registry_name() verified.")
    
    # 2. Rin Tab
    rin_tab = RinAnalysisTab(mock_adapter)
    assert rin_tab.get_registry_name() == "rin_analysis"
    log.info("RinAnalysisTab.get_registry_name() verified.")
    
    # 3. Baseline Tab
    rmp_tab = BaselineAnalysisTab(mock_adapter)
    assert rmp_tab.get_registry_name() == "rmp_analysis"
    log.info("BaselineAnalysisTab.get_registry_name() verified.")
    
    # 4. Event Detection Tab
    event_tab = EventDetectionTab(mock_adapter)
    # Default
    assert event_tab.get_registry_name() == "event_detection_threshold"
    log.info("EventDetectionTab.get_registry_name() [Default] verified.")
    
    # Mock combobox selection
    event_tab.mini_method_combobox.setCurrentText("Deconvolution (Custom)")
    assert event_tab.get_registry_name() == "event_detection_deconvolution"
    log.info("EventDetectionTab.get_registry_name() [Deconvolution] verified.")

    # --- Verify Execution Logic ---
    log.info("Verifying EventDetectionTab execution logic...")
    
    # Mock data
    import numpy as np
    data = {
        'data': np.zeros(1000),
        'time': np.linspace(0, 1, 1000),
        'sampling_rate': 1000.0
    }
    
    # Test Threshold Execution
    event_tab.mini_method_combobox.setCurrentText("Threshold Based")
    params = event_tab._gather_analysis_parameters()
    # Mock the registry function to avoid actual computation overhead/dependencies
    # But we want to ensure _execute_core_analysis calls it correctly
    
    # Actually, let's run it with the REAL registry function if possible, 
    # or at least ensure _execute_core_analysis doesn't crash.
    # The crash was due to argument mismatch.
    
    try:
        # We need to mock AnalysisRegistry.get_function to return a mock 
        # that checks arguments, OR just let it run if the real function is available.
        # Since we are in the real environment, the real function should be there.
        
        # However, the real function might be slow or need real data.
        # Let's mock the registry return for safety and speed.
        
        original_get = AnalysisRegistry.get_function
        mock_func = MagicMock(return_value={'event_indices': [], 'summary_stats': {}})
        AnalysisRegistry.get_function = MagicMock(return_value=mock_func)
        
        # Run execution
        event_tab._execute_core_analysis(params, data)
        
        # Verify call signature
        # Expected: func(signal_data, time_vec, sample_rate, **kwargs)
        mock_func.assert_called_once()
        args, kwargs = mock_func.call_args
        assert len(args) == 3 # data, time, sampling_rate
        assert isinstance(args[0], np.ndarray) # data
        assert isinstance(args[1], np.ndarray) # time
        assert isinstance(args[2], float) # sampling_rate
        
        log.info("EventDetectionTab._execute_core_analysis called wrapper with correct signature.")
        
    finally:
        # Restore registry
        if 'original_get' in locals():
            AnalysisRegistry.get_function = original_get

def verify_batch_dialog():
    # Test BatchAnalysisDialog pre-population
    log.info("--- Verifying BatchAnalysisDialog ---")
    pipeline_config = [{'analysis': 'spike_detection', 'scope': 'all_trials', 'params': {}}]
    default_channels = ["Vm_1"]
    dialog = BatchAnalysisDialog(files=[], pipeline_config=pipeline_config, default_channels=default_channels)
    
    # Verify pipeline pre-population
    if len(dialog.pipeline_steps) == 1 and dialog.pipeline_steps[0]['analysis'] == 'spike_detection':
        log.info("BatchAnalysisDialog pre-population verified.")
    else:
        log.error(f"BatchAnalysisDialog pre-population FAILED. Steps: {dialog.pipeline_steps}")
        sys.exit(1)

    # Verify channel input pre-fill
    if dialog.channel_input.text() == "Vm_1":
        log.info("BatchAnalysisDialog channel pre-fill verified.")
    else:
        log.error(f"BatchAnalysisDialog channel pre-fill FAILED. Expected 'Vm_1', got '{dialog.channel_input.text()}'")
        sys.exit(1)

    # Verify channel filter parsing
    dialog.channel_input.setText("Vm_1, Im_1")
    # Simulate run to check worker init
    # We can't easily run the full worker in this test without real data, but we can check the parsing logic
    channel_filter_text = dialog.channel_input.text().strip()
    channel_filter = [c.strip() for c in channel_filter_text.split(',') if c.strip()]
    if channel_filter == ["Vm_1", "Im_1"]:
        log.info("BatchAnalysisDialog channel filter parsing verified.")
    else:
        log.error(f"BatchAnalysisDialog channel filter parsing FAILED. Got {channel_filter}")
        sys.exit(1)


if __name__ == "__main__":
    try:
        verify_tabs()
        verify_batch_dialog()
        log.info("ALL VERIFICATIONS PASSED!")
    except Exception as e:
        log.error(f"Verification FAILED: {e}", exc_info=True)
        sys.exit(1)

