
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
sys.modules['Synaptipy.core.analysis.spike_analysis'] = MagicMock()
sys.modules['Synaptipy.core.analysis.phase_plane'] = MagicMock()

# Now import the modules under test
from Synaptipy.application.gui.analysis_tabs.metadata_driven import MetadataDrivenAnalysisTab
from Synaptipy.application.gui.analysis_tabs.spike_tab import SpikeAnalysisTab
from Synaptipy.application.gui.analysis_tabs.phase_plane_tab import PhasePlaneTab

class TestAnalysisTabs(unittest.TestCase):
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

    def test_metadata_driven_calls_visualization_hook(self):
        """Test that MetadataDrivenAnalysisTab calls _plot_analysis_visualizations on result."""
        
        # Create a mock subclass to verify the hook call
        class MockTab(MetadataDrivenAnalysisTab):
            def __init__(self, *args, **kwargs):
                self.hook_called = False
                super().__init__("mock_analysis", *args, **kwargs)
                
            def _plot_analysis_visualizations(self, results):
                self.hook_called = True
                
            def get_registry_name(self): return "mock_analysis"
            def get_display_name(self): return "Mock Tab"
            def _gather_analysis_parameters(self): return {}
            def _execute_core_analysis(self, params, data): return {'result': 'success'}
            def _display_analysis_results(self, results): pass
            
        tab = MockTab(self.neo_adapter)
        tab.plot_widget = MagicMock() # Mock plot widget
        tab.results_text = MagicMock()
        tab.status_label = MagicMock()
        
        # Trigger result
        tab._on_analysis_result({'result': 'success'})
        
        self.assertTrue(tab.hook_called, "_plot_analysis_visualizations should be called")
        # Verify plot was NOT cleared (except for raw trace which happens earlier)
        # We can't easily check if it wasn't cleared here because we mock plot_widget, 
        # but we can check that it didn't crash.

    def test_spike_tab_visualization(self):
        """Test that SpikeAnalysisTab updates markers."""
        tab = SpikeAnalysisTab(self.neo_adapter)
        tab.plot_widget = MagicMock()
        tab.spike_markers_item = MagicMock()
        tab.threshold_line = MagicMock()
        tab.results_text = MagicMock()
        tab.status_label = MagicMock()
        
        # Mock current plot data
        tab._current_plot_data = {
            'time': np.array([0, 1, 2, 3]),
            'voltage': np.array([10, 20, 30, 40]),
            'sampling_rate': 1000
        }
        
        # Simulate result
        result = {'spike_indices': [1, 3], 'metadata': {'threshold': -20}}
        
        # Call _on_analysis_result (which calls _plot_analysis_visualizations)
        tab._on_analysis_result(result)
        
        # Verify markers updated
        tab.spike_markers_item.setData.assert_called()
        tab.spike_markers_item.setVisible.assert_called_with(True)
        
        # Verify threshold line updated
        tab.threshold_line.setValue.assert_called_with(-20)
        tab.threshold_line.setVisible.assert_called_with(True)

    def test_phase_plane_safety(self):
        """Test PhasePlaneTab safety check for missing curve."""
        tab = PhasePlaneTab(self.neo_adapter)
        tab.plot_widget = MagicMock()
        tab.results_text = MagicMock()
        tab.status_label = MagicMock()
        
        # Force phase_curve to None to simulate the crash condition
        tab.phase_curve = None
        tab.popup_plot = MagicMock() # Popup exists but curve is None
        
        # Simulate result
        result = {'voltage': [1, 2], 'dvdt': [3, 4]}
        
        # Should not raise AttributeError
        try:
            tab._on_analysis_result(result)
        except AttributeError as e:
            self.fail(f"PhasePlaneTab raised AttributeError: {e}")
            
        # Verify it tried to recreate the plot (since popup_plot was not None but curve was None, logic might differ)
        # In my fix: if self.popup_plot is None or self.phase_curve is None: recreate
        # So it should have recreated it.
        # Since create_popup_plot is a method on tab, we can mock it to verify call
        with patch.object(tab, 'create_popup_plot') as mock_create:
            mock_create.return_value = MagicMock()
            tab.phase_curve = None # Reset
            tab._on_analysis_result(result)
            mock_create.assert_called()

if __name__ == '__main__':
    unittest.main()
