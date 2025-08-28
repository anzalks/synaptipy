#!/usr/bin/env python3
"""
Plot Save Dialog for Synaptipy

This module provides a dialog for saving plots as PNG or PDF files.
Users can select the file path, name, and format.

This file is part of Synaptipy, licensed under the GNU Affero General Public License v3.0.
See the LICENSE file in the root of the repository for full license details.
"""

from PySide6 import QtWidgets, QtCore, QtGui
import pyqtgraph as pg
import logging
import os
from typing import Optional, Tuple

log = logging.getLogger(__name__)


class PlotSaveDialog(QtWidgets.QDialog):
    """Dialog for saving plots as PNG or PDF files."""
    
    def __init__(self, parent=None, default_filename: str = "plot"):
        super().__init__(parent)
        self.setWindowTitle("Save Plot")
        self.setModal(True)
        self.setMinimumWidth(500)
        
        self.default_filename = default_filename
        self.selected_path = ""
        self.selected_format = "png"
        
        self._setup_ui()
        self._connect_signals()
        
    def _setup_ui(self):
        """Setup the user interface."""
        layout = QtWidgets.QVBoxLayout(self)
        
        # File path selection
        path_group = QtWidgets.QGroupBox("File Path")
        path_layout = QtWidgets.QHBoxLayout(path_group)
        
        self.path_edit = QtWidgets.QLineEdit()
        self.path_edit.setPlaceholderText("Select file path...")
        self.path_edit.setText(os.path.expanduser("~/Desktop"))
        
        self.browse_button = QtWidgets.QPushButton("Browse...")
        self.browse_button.setToolTip("Browse for save location")
        
        path_layout.addWidget(self.path_edit)
        path_layout.addWidget(self.browse_button)
        
        layout.addWidget(path_group)
        
        # File name and format
        file_group = QtWidgets.QGroupBox("File Details")
        file_layout = QtWidgets.QGridLayout(file_group)
        
        # File name
        file_layout.addWidget(QtWidgets.QLabel("File Name:"), 0, 0)
        self.filename_edit = QtWidgets.QLineEdit()
        self.filename_edit.setText(self.default_filename)
        file_layout.addWidget(self.filename_edit, 0, 1)
        
        # File format
        file_layout.addWidget(QtWidgets.QLabel("Format:"), 1, 0)
        self.format_combo = QtWidgets.QComboBox()
        self.format_combo.addItems(["PNG", "PDF"])
        self.format_combo.setCurrentText("PNG")
        file_layout.addWidget(self.format_combo, 1, 1)
        
        # File extension (read-only)
        file_layout.addWidget(QtWidgets.QLabel("Extension:"), 2, 0)
        self.extension_label = QtWidgets.QLabel(".png")
        self.extension_label.setStyleSheet("color: gray;")
        file_layout.addWidget(self.extension_label, 2, 1)
        
        layout.addWidget(file_group)
        
        # Preview of full path
        preview_group = QtWidgets.QGroupBox("Full Path Preview")
        preview_layout = QtWidgets.QVBoxLayout(preview_group)
        
        self.preview_label = QtWidgets.QLabel()
        self.preview_label.setStyleSheet("color: blue; font-family: monospace; padding: 5px; border: 1px solid #ccc; background-color: #f9f9f9;")
        self.preview_label.setWordWrap(True)
        self._update_preview()
        
        preview_layout.addWidget(self.preview_label)
        layout.addWidget(preview_group)
        
        # Buttons
        button_layout = QtWidgets.QHBoxLayout()
        button_layout.addStretch()
        
        self.cancel_button = QtWidgets.QPushButton("Cancel")
        self.save_button = QtWidgets.QPushButton("Save Plot")
        self.save_button.setDefault(True)
        
        button_layout.addWidget(self.cancel_button)
        button_layout.addWidget(self.save_button)
        
        layout.addLayout(button_layout)
        
    def _connect_signals(self):
        """Connect UI signals."""
        self.browse_button.clicked.connect(self._browse_path)
        self.path_edit.textChanged.connect(self._update_preview)
        self.filename_edit.textChanged.connect(self._update_preview)
        self.format_combo.currentTextChanged.connect(self._update_preview)
        
        self.cancel_button.clicked.connect(self.reject)
        self.save_button.clicked.connect(self._save_plot)
        
    def _browse_path(self):
        """Browse for save directory."""
        current_path = self.path_edit.text()
        if not current_path or not os.path.exists(current_path):
            current_path = os.path.expanduser("~/Desktop")
            
        directory = QtWidgets.QFileDialog.getExistingDirectory(
            self, "Select Save Directory", current_path
        )
        
        if directory:
            self.path_edit.setText(directory)
            
    def _update_preview(self):
        """Update the full path preview."""
        path = self.path_edit.text()
        filename = self.filename_edit.text()
        format_text = self.format_combo.currentText().lower()
        
        if path and filename:
            full_path = os.path.join(path, f"{filename}.{format_text}")
            self.preview_label.setText(full_path)
        else:
            self.preview_label.setText("")
            
    def _save_plot(self):
        """Save the plot and close dialog."""
        path = self.path_edit.text()
        filename = self.filename_edit.text()
        format_text = self.format_combo.currentText().lower()
        
        if not path or not filename:
            QtWidgets.QMessageBox.warning(
                self, "Invalid Input", 
                "Please provide both a path and filename."
            )
            return
            
        if not os.path.exists(path):
            QtWidgets.QMessageBox.warning(
                self, "Invalid Path", 
                f"The selected path does not exist:\n{path}"
            )
            return
            
        # Store the selected values
        self.selected_path = path
        self.selected_format = format_text
        
        # Close dialog with accept
        self.accept()
        
    def get_save_info(self) -> Tuple[str, str]:
        """Get the selected save path and format.
        
        Returns:
            Tuple[str, str]: (full_file_path, format)
        """
        path = self.path_edit.text()
        filename = self.filename_edit.text()
        format_text = self.format_combo.currentText().lower()
        
        full_path = os.path.join(path, f"{filename}.{format_text}")
        return full_path, format_text


def save_plot_as_image(plot_widget: pg.PlotWidget, file_path: str, format_type: str = "png") -> bool:
    """Save a plot widget as an image file.
    
    Args:
        plot_widget: The PyQtGraph plot widget to save
        file_path: Full path where to save the file
        format_type: File format ("png" or "pdf")
        
    Returns:
        bool: True if save was successful, False otherwise
    """
    try:
        if format_type.lower() == "png":
            # Save as PNG
            plot_widget.grab().save(file_path, "PNG")
            log.info(f"Plot saved as PNG: {file_path}")
            return True
            
        elif format_type.lower() == "pdf":
            # Save as PDF using QPrinter
            from PySide6.QtPrintSupport import QPrinter
            from PySide6.QtGui import QPainter
            
            printer = QPrinter(QPrinter.PrinterMode.HighResolution)
            printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
            printer.setOutputFileName(file_path)
            
            # Get the plot item and render it
            plot_item = plot_widget.getPlotItem()
            if plot_item:
                painter = QPainter()
                if painter.begin(printer):
                    # Render the plot to the printer
                    plot_item.render(painter)
                    painter.end()
                    log.info(f"Plot saved as PDF: {file_path}")
                    return True
                else:
                    log.error(f"Failed to begin painting for PDF: {file_path}")
                    return False
            else:
                log.error(f"No plot item found for PDF export: {file_path}")
                return False
        else:
            log.error(f"Unsupported format: {format_type}")
            return False
            
    except Exception as e:
        log.error(f"Failed to save plot as {format_type}: {e}")
        return False


def save_plot_with_dialog(plot_widget: pg.PlotWidget, parent=None, default_filename: str = "plot") -> bool:
    """Show save plot dialog and save the plot if user confirms.
    
    Args:
        plot_widget: The PyQtGraph plot widget to save
        parent: Parent widget for the dialog
        default_filename: Default filename (without extension)
        
    Returns:
        bool: True if plot was saved successfully, False otherwise
    """
    try:
        dialog = PlotSaveDialog(parent, default_filename)
        if dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            file_path, format_type = dialog.get_save_info()
            return save_plot_as_image(plot_widget, file_path, format_type)
        return False
        
    except Exception as e:
        log.error(f"Failed to show save plot dialog: {e}")
        return False
