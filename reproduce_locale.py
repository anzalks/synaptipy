
import sys
from PySide6 import QtWidgets, QtCore
import unittest

class TestLocale(unittest.TestCase):
    def test_decimal_separator(self):
        """Test the decimal separator used by QDoubleSpinBox."""
        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
        
        # Check default locale
        locale = QtCore.QLocale()
        print(f"System Locale: {locale.name()}")
        print(f"Decimal Point: {locale.decimalPoint()}")
        
        widget = QtWidgets.QDoubleSpinBox()
        widget.setValue(1.23)
        text = widget.textFromValue(1.23)
        print(f"Widget Text for 1.23: {text}")
        
        # Force locale to English/US (simulating the fix in __main__.py)
        QtCore.QLocale.setDefault(QtCore.QLocale(QtCore.QLocale.English, QtCore.QLocale.UnitedStates))
        
        # Check new locale
        new_locale = QtCore.QLocale() # Get default locale
        print(f"New System Locale: {new_locale.name()}")
        print(f"New Decimal Point: {new_locale.decimalPoint()}")
        
        # Create a NEW widget to pick up the new default locale
        new_widget = QtWidgets.QDoubleSpinBox()
        new_widget.setValue(1.23)
        text = new_widget.textFromValue(1.23)
        print(f"New Widget Text for 1.23: {text}")
        
        self.assertEqual(new_locale.decimalPoint(), '.', "Decimal point should be '.'")
        self.assertEqual(text, "1.23", "Widget text should use dot separator")
        
if __name__ == '__main__':
    unittest.main()
