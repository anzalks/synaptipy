
import sys
import logging
import pandas as pd
from unittest.mock import MagicMock
from PySide6 import QtWidgets
from Synaptipy.application.gui.batch_dialog import BatchAnalysisDialog

# Configure logging
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("verify_batch_integration")

def verify_batch_integration():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    
    # Mock MainWindow using a real QMainWindow to satisfy type checks
    mock_main_window = QtWidgets.QMainWindow()
    mock_main_window.saved_analysis_results = []
    
    def add_saved_result(result):
        mock_main_window.saved_analysis_results.append(result)
        log.info(f"Result added to MainWindow: {result}")
        
    # Monkey patch the method onto the instance
    mock_main_window.add_saved_result = add_saved_result
    
    # Mock dependencies for BatchAnalysisDialog
    mock_analysis_items = []
    mock_registry = MagicMock()
    
    try:
        log.info("Initializing BatchAnalysisDialog...")
        dialog = BatchAnalysisDialog(mock_analysis_items, mock_registry, parent=mock_main_window)
        
        # Mock pipeline steps
        dialog.pipeline_steps = [{'analysis': 'Test Analysis'}]
        # dialog.analysis_type_combo = MagicMock() # Removed
        # dialog.analysis_type_combo.currentText.return_value = "Test Analysis" # Removed
        
        # Create a dummy result DataFrame
        df = pd.DataFrame({
            'file': ['/path/to/file1.abf', '/path/to/file2.abf'],
            'value': [10, 20],
            'timestamp_saved': ['2023-01-01', '2023-01-02']
        })
        
        log.info("Simulating batch completion...")
        # Manually trigger the save method (simulating _on_finished)
        dialog._save_results_to_main_window(df)
        
        # Verify results were added to MainWindow
        count = len(mock_main_window.saved_analysis_results)
        log.info(f"Saved results count: {count}")
        
        if count != 2:
            log.error(f"Expected 2 saved results, got {count}")
            sys.exit(1)
            
        # Verify content
        first_result = mock_main_window.saved_analysis_results[0]
        if first_result['source_file_name'] != 'file1.abf':
            log.error(f"Expected source_file_name 'file1.abf', got {first_result.get('source_file_name')}")
            sys.exit(1)
            
        if first_result['analysis_type'] != 'Test Analysis':
            log.error(f"Expected analysis_type 'Test Analysis', got {first_result.get('analysis_type')}")
            sys.exit(1)
            
        log.info("Batch Integration Verification PASSED")
        
    except Exception as e:
        log.error(f"Verification FAILED: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    verify_batch_integration()
