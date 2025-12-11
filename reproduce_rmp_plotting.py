
import sys
import unittest
import numpy as np
import pyqtgraph as pg
from PySide6 import QtWidgets, QtCore
from unittest.mock import MagicMock

# Mock NeoAdapter and Registry
sys.modules['Synaptipy.infrastructure.file_readers'] = MagicMock()
sys.modules['Synaptipy.core.analysis.registry'] = MagicMock()

# Mock AnalysisRegistry.get_metadata to return empty list
sys.modules['Synaptipy.core.analysis.registry'].AnalysisRegistry.get_metadata.return_value = {'ui_params': []}

# Import the tab
from Synaptipy.application.gui.analysis_tabs.rmp_tab import BaselineAnalysisTab

class TestRMPPlotting(unittest.TestCase):
    def setUp(self):
        self.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
        self.adapter = MagicMock()
        self.tab = BaselineAnalysisTab(self.adapter)
        
    def test_plotting_lines(self):
        """Test that baseline lines are visible after analysis."""
        # Setup plot widget (it's created in _setup_ui)
        self.assertIsNotNone(self.tab.plot_widget)
        
        # Mock result data
        results = {
            'result': {
                'rmp_mv': -65.0,
                'rmp_std': 2.0,
                'rmp_drift': 0.1
            }
        }
        
        # Trigger result handling
        self.tab._on_analysis_result(results)
        
        # Check lines
        self.assertTrue(self.tab.baseline_mean_line.isVisible(), "Mean line should be visible")
        self.assertEqual(self.tab.baseline_mean_line.value(), -65.0)
        
        self.assertTrue(self.tab.baseline_plus_sd_line.isVisible(), "Plus SD line should be visible")
        self.assertEqual(self.tab.baseline_plus_sd_line.value(), -63.0)
        
        self.assertTrue(self.tab.baseline_minus_sd_line.isVisible(), "Minus SD line should be visible")
        self.assertEqual(self.tab.baseline_minus_sd_line.value(), -67.0)

if __name__ == '__main__':
    unittest.main()
