
import sys
from PySide6 import QtWidgets
import unittest

# Mock imports if needed, but we can import ui_generator directly if we mock parent layout
from Synaptipy.application.gui.ui_generator import ParameterWidgetGenerator

class TestDecimalPrecision(unittest.TestCase):
    def setUp(self):
        self.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
        self.layout = QtWidgets.QFormLayout()
        self.generator = ParameterWidgetGenerator(self.layout)

    def test_default_decimals(self):
        """Test that default decimals is now 4."""
        params = [{'name': 'test_param', 'type': 'float'}]
        self.generator.generate_widgets(params)
        widget = self.generator.widgets['test_param']
        
        self.assertIsInstance(widget, QtWidgets.QDoubleSpinBox)
        self.assertEqual(widget.decimals(), 4, "Default decimals should be 4")
        self.assertAlmostEqual(widget.singleStep(), 0.0001, places=5, msg="Single step should be 0.0001")

    def test_override_decimals(self):
        """Test that decimals can be overridden."""
        params = [{'name': 'test_param_2', 'type': 'float', 'decimals': 2}]
        self.generator.generate_widgets(params)
        widget = self.generator.widgets['test_param_2']
        
        self.assertEqual(widget.decimals(), 2, "Decimals should be overridden to 2")
        self.assertAlmostEqual(widget.singleStep(), 0.01, places=3, msg="Single step should be 0.01")

if __name__ == '__main__':
    unittest.main()
