
import sys
import unittest
from unittest.mock import MagicMock, patch
import numpy as np
from PySide6 import QtWidgets, QtCore
import pyqtgraph as pg

# Mock Synaptipy imports
sys.modules['Synaptipy.core.data_model'] = MagicMock()
sys.modules['Synaptipy.infrastructure.file_readers'] = MagicMock()
sys.modules['Synaptipy.shared.error_handling'] = MagicMock()
sys.modules['Synaptipy.shared.styling'] = MagicMock()
sys.modules['Synaptipy.shared.plot_zoom_sync'] = MagicMock()
sys.modules['Synaptipy.application.gui.analysis_worker'] = MagicMock()
sys.modules['Synaptipy.core.analysis.registry'] = MagicMock()
sys.modules['Synaptipy.application.gui.ui_generator'] = MagicMock()
sys.modules['Synaptipy.core.results'] = MagicMock()
sys.modules['Synaptipy.core.analysis.event_detection'] = MagicMock()

# Now import the module under test
from Synaptipy.application.gui.analysis_tabs.event_detection_tab import EventDetectionTab

class TestEventDetectionTab(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not QtWidgets.QApplication.instance():
            cls.app = QtWidgets.QApplication([])
        else:
            cls.app = QtWidgets.QApplication.instance()

    def setUp(self):
        self.neo_adapter = MagicMock()
        self.settings = MagicMock()
        
        # Mock AnalysisRegistry.get_metadata
        self.mock_metadata = {'ui_params': []}
        sys.modules['Synaptipy.core.analysis.registry'].AnalysisRegistry.get_metadata.return_value = self.mock_metadata

    def test_event_overlays(self):
        """Test that EventDetectionTab overlays markers correctly."""
        tab = EventDetectionTab(self.neo_adapter)
        tab.plot_widget = MagicMock()
        tab.event_markers_item = MagicMock()
        tab.mini_results_textedit = MagicMock()
        
        # Mock current plot data
        time = np.linspace(0, 1, 1000)
        voltage = np.sin(2 * np.pi * 10 * time) # Dummy data
        tab._current_plot_data = {
            'time': time,
            'voltage': voltage,
            'sampling_rate': 1000
        }
        
        # Simulate result with event indices
        # Indices 10, 50, 100
        event_indices = np.array([10, 50, 100])
        result = {
            'result': {
                'event_indices': event_indices,
                'event_count': 3,
                'frequency_hz': 3.0
            }
        }
        
        # Call _on_analysis_result
        tab._on_analysis_result(result)
        
        # Verify setData called with correct values
        expected_times = time[event_indices]
        expected_voltages = voltage[event_indices]
        
        # Check if setData was called
        # Note: In the code it uses keyword args: setData(x=times, y=voltages)
        tab.event_markers_item.setData.assert_called()
        
        # Get arguments
        call_args = tab.event_markers_item.setData.call_args
        if call_args:
            kwargs = call_args.kwargs
            if 'x' in kwargs and 'y' in kwargs:
                np.testing.assert_array_almost_equal(kwargs['x'], expected_times)
                np.testing.assert_array_almost_equal(kwargs['y'], expected_voltages)
            else:
                # Maybe positional args?
                args = call_args.args
                if len(args) >= 2:
                    np.testing.assert_array_almost_equal(args[0], expected_times)
                    np.testing.assert_array_almost_equal(args[1], expected_voltages)
        
        # Verify visibility
        tab.event_markers_item.setVisible.assert_called_with(True)
        
        # Verify it checks if item is in plot
        tab.plot_widget.listDataItems.assert_called()

if __name__ == '__main__':
    unittest.main()
