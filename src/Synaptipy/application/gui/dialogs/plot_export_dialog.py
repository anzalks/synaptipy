# src/Synaptipy/application/gui/dialogs/plot_export_dialog.py
# -*- coding: utf-8 -*-
"""
Dialog for exporting plots with custom settings (Format, DPI).
"""
from PySide6 import QtWidgets, QtCore, QtGui

class PlotExportDialog(QtWidgets.QDialog):
    """
    Dialog to select export format and DPI.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Export Plot")
        self.resize(300, 150)
        self._setup_ui()

    def _setup_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(10)

        # 1. Format Selection
        fmt_layout = QtWidgets.QHBoxLayout()
        fmt_layout.addWidget(QtWidgets.QLabel("Format:"))
        self.format_combo = QtWidgets.QComboBox()
        # SVG and PDF first as they are vector formats (preferred for illustrations)
        self.format_combo.addItems(["PNG", "JPG", "SVG", "PDF"])
        fmt_layout.addWidget(self.format_combo, 1)
        layout.addLayout(fmt_layout)

        # 2. DPI Selection (Only relevant for Raster or some exporters)
        dpi_layout = QtWidgets.QHBoxLayout()
        dpi_layout.addWidget(QtWidgets.QLabel("DPI:"))
        self.dpi_spin = QtWidgets.QSpinBox()
        self.dpi_spin.setRange(72, 1200)
        self.dpi_spin.setValue(300)
        self.dpi_spin.setSuffix(" dpi")
        dpi_layout.addWidget(self.dpi_spin, 1)
        layout.addLayout(dpi_layout)
        
        # Info label
        self.info_label = QtWidgets.QLabel("Vector formats (SVG, PDF) support editable text.")
        self.info_label.setWordWrap(True)
        self.info_label.setStyleSheet("color: gray; font-size: 11px;")
        layout.addWidget(self.info_label)

        # Buttons
        btn_box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)
        
        # Connect format change to update DPI availability/Info
        self.format_combo.currentTextChanged.connect(self._on_format_changed)
        
    def _on_format_changed(self, text):
        # DPI is mostly for rasterization, but sometimes used for PDF sizing.
        # Check text compatibility
        if text in ["SVG", "PDF"]:
            self.info_label.setText("Vector format selected. Text will be editable in Illustrator/Inkscape.")
        else:
            self.info_label.setText("Raster format selected.")

    def get_settings(self):
        return {
            "format": self.format_combo.currentText().lower(),
            "dpi": self.dpi_spin.value()
        }
