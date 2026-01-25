"""
Preprocessing widget for signal analysis.
Includes controls for Baseline Subtraction and Filtering (Notch, Bandpass, Lowpass, Highpass).
"""
import logging
from typing import Dict, Any, Optional

from PySide6 import QtWidgets, QtCore, QtGui
from Synaptipy.shared.styling import style_button

log = logging.getLogger(__name__)


class PreprocessingWidget(QtWidgets.QWidget):
    """
    Widget containing preprocessing controls.
    Emits 'preprocessing_requested' signal when actions are triggered.
    """
    
    # Signal: emitted with a dictionary of settings
    # e.g. {'type': 'baseline', 'decimals': 1}
    # e.g. {'type': 'filter', 'method': 'lowpass', 'cutoff': 100, 'order': 5}
    preprocessing_requested = QtCore.Signal(dict)
    preprocessing_reset_requested = QtCore.Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        # Group Box
        self.group_box = QtWidgets.QGroupBox("Preprocessing")
        group_layout = QtWidgets.QVBoxLayout(self.group_box)
        group_layout.setSpacing(10)
        
        # --- Row 1: Baseline Subtraction ---
        baseline_layout = QtWidgets.QHBoxLayout()
        self.baseline_btn = QtWidgets.QPushButton("Subtract Baseline")
        style_button(self.baseline_btn, style="secondary")
        self.baseline_btn.setToolTip("Align traces to zero using mode-based baseline subtraction.")
        self.baseline_btn.clicked.connect(self._on_baseline_clicked)
        baseline_layout.addWidget(self.baseline_btn)
        group_layout.addLayout(baseline_layout)
        
        # --- Row 2: Filter Controls ---
        filter_group = QtWidgets.QWidget()
        filter_layout = QtWidgets.QVBoxLayout(filter_group)
        filter_layout.setContentsMargins(0, 0, 0, 0)
        
        # Filter Type Selection
        type_layout = QtWidgets.QHBoxLayout()
        type_layout.addWidget(QtWidgets.QLabel("Filter:"))
        self.filter_type_combo = QtWidgets.QComboBox()
        self.filter_type_combo.addItems(["None", "Lowpass", "Highpass", "Bandpass", "Notch"])
        self.filter_type_combo.currentIndexChanged.connect(self._on_filter_type_changed)
        type_layout.addWidget(self.filter_type_combo, 1)
        filter_layout.addLayout(type_layout)
        
        # Stacked Widget for specific parameters
        self.param_stack = QtWidgets.QStackedWidget()
        
        # Page 0: None (Empty)
        self.param_stack.addWidget(QtWidgets.QWidget())
        
        # Page 1: Lowpass (Cutoff, Order)
        self.page_lowpass = self._create_param_page([
            ("Cutoff (Hz):", "1000", "cutoff"),
            ("Order:", "5", "order")
        ])
        self.param_stack.addWidget(self.page_lowpass)
        
        # Page 2: Highpass (Cutoff, Order)
        self.page_highpass = self._create_param_page([
            ("Cutoff (Hz):", "1", "cutoff"),
            ("Order:", "5", "order")
        ])
        self.param_stack.addWidget(self.page_highpass)
        
        # Page 3: Bandpass (Low Cut, High Cut, Order)
        self.page_bandpass = self._create_param_page([
            ("Low Cut (Hz):", "1", "low_cut"),
            ("High Cut (Hz):", "300", "high_cut"),
            ("Order:", "5", "order")
        ])
        self.param_stack.addWidget(self.page_bandpass)
        
        # Page 4: Notch (Freq, Q)
        self.page_notch = self._create_param_page([
            ("Freq (Hz):", "50", "freq"),
            ("Q-Factor:", "30", "q_factor")
        ])
        self.param_stack.addWidget(self.page_notch)
        
        filter_layout.addWidget(self.param_stack)
        
        # --- Row 3: Apply Filter Button ---
        self.apply_filter_btn = QtWidgets.QPushButton("Apply Filter")
        style_button(self.apply_filter_btn, style="secondary")
        self.apply_filter_btn.clicked.connect(self._on_apply_filter_clicked)
        self.apply_filter_btn.setEnabled(False) # Disabled initially as "None" is selected
        
        # Reset Button
        self.reset_btn = QtWidgets.QPushButton("Reset Preprocessing")
        style_button(self.reset_btn, style="danger") # Use danger style for reset
        self.reset_btn.setToolTip("Clear all filters/baseline corrections and revert to raw data.")
        self.reset_btn.clicked.connect(self._on_reset_clicked)
        
        # Layout for buttons
        btns_layout = QtWidgets.QHBoxLayout()
        btns_layout.addWidget(self.apply_filter_btn)
        btns_layout.addWidget(self.reset_btn)
        
        filter_layout.addLayout(btns_layout)
        
        group_layout.addWidget(filter_group)
        
        main_layout.addWidget(self.group_box)
        
    def _create_param_page(self, inputs: list) -> QtWidgets.QWidget:
        """
        Helper to create a parameter page.
        inputs: list of tuples (label_text, default_value, internal_name)
        """
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        
        widget.inputs = {} # Store references to input fields
        
        for label_text, default_val, name in inputs:
            layout.addWidget(QtWidgets.QLabel(label_text))
            
            line_edit = QtWidgets.QLineEdit(default_val)
            # Add validator for numbers
            line_edit.setValidator(QtGui.QDoubleValidator())
            line_edit.setMaximumWidth(60)
            
            layout.addWidget(line_edit)
            widget.inputs[name] = line_edit
            
        layout.addStretch()
        return widget

    def _on_filter_type_changed(self, index):
        self.param_stack.setCurrentIndex(index)
        # Enable apply button only if not "None" (index 0)
        self.apply_filter_btn.setEnabled(index != 0)

    def _on_baseline_clicked(self):
        log.debug("Baseline subtraction requested")
        self.preprocessing_requested.emit({"type": "baseline", "decimals": 1})

    def _on_apply_filter_clicked(self):
        filter_type = self.filter_type_combo.currentText().lower()
        if filter_type == "none":
            return
            
        settings = {"type": "filter", "method": filter_type}
        
        # Get current page widget
        current_page = self.param_stack.currentWidget()
        if hasattr(current_page, "inputs"):
            for name, line_edit in current_page.inputs.items():
                try:
                    val = float(line_edit.text())
                    settings[name] = val
                except ValueError:
                    log.warning(f"Invalid input for {name}: {line_edit.text()}")
                    # Optionally show error, but for now just maybe default or fail gracefully?
                    # Ideally we should validate before emitting
                    return
        
        log.debug(f"Filter requested: {settings}")
        self.preprocessing_requested.emit(settings)

    def _on_reset_clicked(self):
        log.debug("Reset preprocessing requested")
        self.preprocessing_reset_requested.emit()
        
    def set_processing_state(self, is_processing: bool):
        """Enable/Disable controls during processing."""
        self.baseline_btn.setEnabled(not is_processing)
        self.apply_filter_btn.setEnabled(not is_processing and self.filter_type_combo.currentIndex() != 0)
        self.reset_btn.setEnabled(not is_processing)
        self.filter_type_combo.setEnabled(not is_processing)
        self.group_box.setTitle("Preprocessing (Running...)" if is_processing else "Preprocessing")
