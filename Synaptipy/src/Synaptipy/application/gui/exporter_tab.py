# -*- coding: utf-8 -*-
"""
Placeholder tab for future data exporting features (beyond NWB).
"""
import logging
from PySide6 import QtWidgets, QtCore

log = logging.getLogger(__name__)

class ExporterTab(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        log.debug("Initializing ExporterTab")
        self._setup_ui()

    def _setup_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

        label = QtWidgets.QLabel("Exporter Features Placeholder")
        font = label.font()
        font.setPointSize(16)
        label.setFont(font)

        layout.addWidget(label)
        self.setLayout(layout)