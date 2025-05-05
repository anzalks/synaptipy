import sys
print("sys imported")
from PySide6 import QtWidgets
print("PySide6.QtWidgets imported")
app = QtWidgets.QApplication(sys.argv)
print("QtWidgets.QApplication instantiated")
