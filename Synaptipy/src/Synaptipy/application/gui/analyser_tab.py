# -*- coding: utf-8 -*-
"""
Placeholder tab for future analysis features.
"""
import logging
from PySide6 import QtWidgets, QtCore

log = logging.getLogger(__name__)

class AnalyserTab(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        log.debug("Initializing AnalyserTab")
        self._setup_ui()

    def _setup_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

        label = QtWidgets.QLabel("Analysis Features Placeholder")
        font = label.font()
        font.setPointSize(16)
        label.setFont(font)

        layout.addWidget(label)
        self.setLayout(layout)