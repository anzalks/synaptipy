"""
Preprocessing widget for signal analysis.
Includes controls for Baseline Subtraction and Filtering (Notch, Bandpass, Lowpass, Highpass).
"""
import logging

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

        # --- Baseline Group ---
        baseline_group = QtWidgets.QGroupBox("Baseline Correction")
        baseline_layout = QtWidgets.QVBoxLayout(baseline_group)
        baseline_layout.setContentsMargins(5, 5, 5, 5)

        # Method Selection
        bl_type_layout = QtWidgets.QHBoxLayout()
        bl_type_layout.addWidget(QtWidgets.QLabel("Method:"))
        self.baseline_type_combo = QtWidgets.QComboBox()
        self.baseline_type_combo.addItems(["None", "Mode", "Mean", "Median", "Linear Detrend", "Time Window"])
        self.baseline_type_combo.currentIndexChanged.connect(self._on_baseline_type_changed)
        bl_type_layout.addWidget(self.baseline_type_combo, 1)
        baseline_layout.addLayout(bl_type_layout)

        # Baseline Param Stack
        self.bl_param_stack = QtWidgets.QStackedWidget()

        # Page 0: None
        self.bl_param_stack.addWidget(QtWidgets.QWidget())

        # Page 1: Mode (Decimals)
        self.page_bl_mode = self._create_param_page([
            ("Decimals:", "1", "decimals")
        ])
        # Force integer validator for decimals
        if "decimals" in self.page_bl_mode.inputs:
            self.page_bl_mode.inputs["decimals"].setValidator(QtGui.QIntValidator())
        self.bl_param_stack.addWidget(self.page_bl_mode)

        # Page 2: Mean (No params)
        self.bl_param_stack.addWidget(QtWidgets.QWidget())

        # Page 3: Median (No params)
        self.bl_param_stack.addWidget(QtWidgets.QWidget())

        # Page 4: Linear (No params)
        self.bl_param_stack.addWidget(QtWidgets.QWidget())

        # Page 5: Region (Start, End)
        self.page_bl_region = self._create_param_page([
            ("Start (s):", "0.0", "start_t"),
            ("End (s):", "0.05", "end_t")
        ])
        self.bl_param_stack.addWidget(self.page_bl_region)

        baseline_layout.addWidget(self.bl_param_stack)

        # Apply Baseline Button
        self.apply_baseline_btn = QtWidgets.QPushButton("Apply Baseline")
        style_button(self.apply_baseline_btn, style="secondary")
        self.apply_baseline_btn.clicked.connect(self._on_baseline_apply_clicked)
        self.apply_baseline_btn.setEnabled(False)
        baseline_layout.addWidget(self.apply_baseline_btn)

        # Add baseline group first
        group_layout.addWidget(baseline_group)

        # --- Filter Controls ---
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

        # Page 3: Bandpass
        self.page_bandpass = self._create_param_page([
            ("Low Cut (Hz):", "1", "low_cut"),
            ("High Cut (Hz):", "300", "high_cut"),
            ("Order:", "5", "order")
        ])
        self.param_stack.addWidget(self.page_bandpass)

        # Page 4: Notch
        self.page_notch = self._create_param_page([
            ("Freq (Hz):", "50", "freq"),
            ("Q-Factor:", "30", "q_factor")
        ])
        self.param_stack.addWidget(self.page_notch)

        filter_layout.addWidget(self.param_stack)

        # Apply/Reset Buttons
        btns_layout = QtWidgets.QHBoxLayout()

        self.apply_filter_btn = QtWidgets.QPushButton("Apply Filter")
        style_button(self.apply_filter_btn, style="secondary")
        self.apply_filter_btn.clicked.connect(self._on_apply_filter_clicked)
        self.apply_filter_btn.setEnabled(False)
        btns_layout.addWidget(self.apply_filter_btn)

        self.reset_btn = QtWidgets.QPushButton("Reset Preprocessing")
        style_button(self.reset_btn, style="danger")
        self.reset_btn.setToolTip("Clear all filters/baseline corrections and revert to raw data.")
        self.reset_btn.clicked.connect(self._on_reset_clicked)
        btns_layout.addWidget(self.reset_btn)

        filter_layout.addLayout(btns_layout)

        group_layout.addWidget(filter_group)

        # ADDED BACK: Add group box to main layout
        main_layout.addWidget(self.group_box)

    def _create_param_page(self, inputs: list) -> QtWidgets.QWidget:
        """
        Helper to create a parameter page.
        inputs: list of tuples (label_text, default_value, internal_name)
        """
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        widget.inputs = {}  # Store references to input fields

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
                    from PySide6.QtWidgets import QMessageBox
                    QMessageBox.warning(
                        self, "Invalid Input",
                        f"'{line_edit.text()}' is not a valid number for {name}."
                    )
                    return

        log.debug(f"Filter requested: {settings}")
        self.preprocessing_requested.emit(settings)

    def _on_reset_clicked(self):
        log.debug("Reset preprocessing requested")
        self.preprocessing_reset_requested.emit()

    def reset_ui(self):
        """Reset all UI controls to their default ("None") state.

        Called after a preprocessing reset so the widget visually reflects
        that no preprocessing is active.
        """
        self.baseline_type_combo.setCurrentIndex(0)  # "None"
        self.filter_type_combo.setCurrentIndex(0)    # "None"

    def _on_baseline_type_changed(self, index):
        self.bl_param_stack.setCurrentIndex(index)
        self.apply_baseline_btn.setEnabled(index != 0)

    def _on_baseline_apply_clicked(self):
        method_map = {
            1: "mode", 2: "mean", 3: "median", 4: "linear", 5: "region"
        }
        idx = self.baseline_type_combo.currentIndex()
        if idx == 0:
            return

        settings = {"type": "baseline", "method": method_map.get(idx, "mean")}

        # Get params from current stack page
        current_page = self.bl_param_stack.currentWidget()
        if hasattr(current_page, "inputs"):
            for name, line_edit in current_page.inputs.items():
                try:
                    val = float(line_edit.text())
                    # Special check for decimals (int)
                    if name == "decimals":
                        val = int(val)
                    settings[name] = val
                except ValueError:
                    log.warning(f"Invalid input: {line_edit.text()}")
                    from PySide6.QtWidgets import QMessageBox
                    QMessageBox.warning(
                        self, "Invalid Input",
                        f"'{line_edit.text()}' is not a valid number."
                    )
                    return

        log.debug(f"Baseline requested: {settings}")
        self.preprocessing_requested.emit(settings)

    def set_processing_state(self, is_processing: bool):
        """Enable/Disable controls during processing."""
        self.baseline_type_combo.setEnabled(not is_processing)
        self.apply_baseline_btn.setEnabled(not is_processing and self.baseline_type_combo.currentIndex() != 0)

        self.apply_filter_btn.setEnabled(not is_processing and self.filter_type_combo.currentIndex() != 0)
        self.reset_btn.setEnabled(not is_processing)
        self.filter_type_combo.setEnabled(not is_processing)
        self.group_box.setTitle("Preprocessing (Running...)" if is_processing else "Preprocessing")
