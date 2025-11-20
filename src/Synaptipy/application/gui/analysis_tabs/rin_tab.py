# src/Synaptipy/application/gui/analysis_tabs/rin_tab.py
# -*- coding: utf-8 -*-
"""
Analysis tab for calculating Input Resistance (Rin) with interactive selection.
"""
import logging
from typing import Optional, List, Dict, Any, Tuple
import numpy as np

from PySide6 import QtCore, QtGui, QtWidgets
import pyqtgraph as pg

# Use relative imports within the same package
from .base import BaseAnalysisTab
# Use absolute paths for core components
from Synaptipy.core.data_model import Recording, Channel
from Synaptipy.infrastructure.file_readers import NeoAdapter
from Synaptipy.core.analysis import intrinsic_properties as ip
from Synaptipy.shared.styling import (
    style_button, 
    style_label, 
    style_info_label, 
    style_result_display,
    get_baseline_pen,
    get_response_pen,
)

log = logging.getLogger('Synaptipy.application.gui.analysis_tabs.rin_tab')

# --- Rin Calculation Function (REVERTED to use manual delta_i) ---
def calculate_rin(
    time_v: np.ndarray, voltage: np.ndarray,
    baseline_window: Tuple[float, float],
    response_window: Tuple[float, float],
    delta_i_pa: float # RE-ADDED manual delta I
) -> Optional[Tuple[float, float]]: # Return Rin, dV (dI is now input)
    """
    Calculates Input Resistance (Rin) based on voltage trace within defined windows
    and a provided current step amplitude (delta_i).

    Args:
        time_v: 1D numpy array of time values for voltage trace.
        voltage: 1D numpy array of voltage values.
        baseline_window: Tuple (start_time, end_time) for baseline measurement.
        response_window: Tuple (start_time, end_time) for response measurement.
        delta_i_pa: The change in current amplitude (I_response - I_baseline) in picoamps (pA).

    Returns:
        A tuple containing (rin_megaohms, delta_v_millivolts) 
        or None if calculation fails (e.g., invalid windows, no data, zero delta_i).
    """
    # Basic validations
    if time_v is None or voltage is None or \
       baseline_window is None or response_window is None or \
       baseline_window[0] >= baseline_window[1] or response_window[0] >= response_window[1]:
        log.error("Calculate Rin: Invalid input arrays or window times.")
        return None
    
    # Validate delta_i
    if np.isclose(delta_i_pa, 0.0):
        log.warning(f"Provided Delta I is zero or close to zero ({delta_i_pa:.4f} pA). Cannot calculate Rin.")
        return None

    try:
        # --- Calculate Mean Baseline Voltage ---
        bl_indices_v = np.where((time_v >= baseline_window[0]) & (time_v <= baseline_window[1]))[0]
        if len(bl_indices_v) == 0:
            log.warning(f"No voltage data points found in baseline window: {baseline_window}")
            return None
        mean_baseline_v = np.mean(voltage[bl_indices_v])

        # --- Calculate Mean Response Voltage ---
        resp_indices_v = np.where((time_v >= response_window[0]) & (time_v <= response_window[1]))[0]
        if len(resp_indices_v) == 0:
            log.warning(f"No voltage data points found in response window: {response_window}")
            return None
        mean_response_v = np.mean(voltage[resp_indices_v])

        # --- Calculate Delta V ---
        delta_v = mean_response_v - mean_baseline_v # mV (assuming input V is mV)

        log.debug(f"Rin Calc: Mean Baseline V={mean_baseline_v:.3f} mV, Mean Response V={mean_response_v:.3f} mV => dV={delta_v:.3f} mV")
        log.debug(f"Rin Calc: Using provided dI = {delta_i_pa:.3f} pA")

        # --- Calculate Rin using provided delta_i --- 
        # Rin (MΩ) = Delta V (mV) / Delta I (nA)
        # Convert delta_i from pA to nA by dividing by 1000
        rin_megaohms = delta_v / (delta_i_pa / 1000.0)

        log.info(f"Calculated Rin = {rin_megaohms:.2f} MΩ (dV={delta_v:.3f}mV, using provided dI={delta_i_pa:.3f}pA)")
        return rin_megaohms, delta_v # Return Rin and the calculated dV

    except Exception as e:
        log.error(f"Error calculating Rin: {e}", exc_info=True)
        return None

# --- Rin Analysis Tab Class ---
class RinAnalysisTab(BaseAnalysisTab):
    """Widget for Input Resistance/Conductance calculation with interactive plotting."""

    # Class constants for modes (Should match combobox text exactly)
    _MODE_INTERACTIVE = "Interactive (Regions)"
    _MODE_MANUAL = "Manual (Time Windows)"

    # Class constants for results keys
    _RESULT_RIN_KOHM = "Input Resistance (kOhm)"
    _RESULT_STD_DEV = "Baseline Std Dev"

    def __init__(self, neo_adapter: NeoAdapter, parent=None):
        # Initialize the base class FIRST
        super().__init__(neo_adapter=neo_adapter, parent=parent)
        # Explicitly initialize attributes needed before _on_mode_changed is called
        self._selected_item_recording = None # Initialize base class attribute

        # Initialize Rin/G specific attributes
        self.mode_combobox = None
        # --- UI References specific to Rin/Conductance ---
        self.signal_channel_combobox: Optional[QtWidgets.QComboBox] = None
        self.data_source_combobox: Optional[QtWidgets.QComboBox] = None
        # Mode Selection
        self.analysis_params_group: Optional[QtWidgets.QGroupBox] = None
        self.mode_combobox: Optional[QtWidgets.QComboBox] = None
        # Manual Inputs (Time)
        self.manual_time_group: Optional[QtWidgets.QGroupBox] = None
        self.manual_baseline_start_spinbox: Optional[QtWidgets.QDoubleSpinBox] = None
        self.manual_baseline_end_spinbox: Optional[QtWidgets.QDoubleSpinBox] = None
        self.manual_response_start_spinbox: Optional[QtWidgets.QDoubleSpinBox] = None
        self.manual_response_end_spinbox: Optional[QtWidgets.QDoubleSpinBox] = None
        # Manual Inputs (Delta I/V)
        self.manual_delta_i_spinbox: Optional[QtWidgets.QDoubleSpinBox] = None
        self.manual_delta_v_spinbox: Optional[QtWidgets.QDoubleSpinBox] = None # <<< ADDED for VC
        self.delta_i_input_row_widgets: Optional[Tuple[QtWidgets.QLabel, QtWidgets.QWidget]] = None # <<< ADDED to store row widgets
        self.delta_v_input_row_widgets: Optional[Tuple[QtWidgets.QLabel, QtWidgets.QWidget]] = None # <<< ADDED to store row widgets
        self.delta_i_form_layout: Optional[QtWidgets.QFormLayout] = None # <<< ADDED reference to layout holding delta inputs
        # Results Display
        self.rin_result_label: Optional[QtWidgets.QLabel] = None
        self.delta_v_label: Optional[QtWidgets.QLabel] = None
        self.delta_i_label: Optional[QtWidgets.QLabel] = None
        self.status_label: Optional[QtWidgets.QLabel] = None
        # Plotting Interaction
        self.plot_widget: Optional[pg.PlotWidget] = None
        self.baseline_region: Optional[pg.LinearRegionItem] = None
        self.response_region: Optional[pg.LinearRegionItem] = None
        # Visualization lines
        self.baseline_line: Optional[pg.InfiniteLine] = None
        self.response_line: Optional[pg.InfiniteLine] = None
        # Current Plotting (secondary axis)
        self.current_plot_item: Optional[pg.PlotDataItem] = None # Keep for now, might plot command voltage here later
        # Run Button (Manual Mode)
        self.run_button: Optional[QtWidgets.QPushButton] = None
        # Other properties
        self.tau_button: Optional[QtWidgets.QPushButton] = None
        self.sag_button: Optional[QtWidgets.QPushButton] = None
        self.tau_result_label: Optional[QtWidgets.QLabel] = None
        self.sag_result_label: Optional[QtWidgets.QLabel] = None

        # Store currently plotted data for analysis
        self._current_plot_data: Optional[Dict[str, Any]] = None # Generalized name
        # Store last calculated result
        self._last_rin_result: Optional[Dict[str, Any]] = None
        # --- ADDED: Plot Item Reference ---
        self.plot_item: Optional[pg.PlotDataItem] = None
        # --- END ADDED ---

        self._setup_ui()
        self._connect_signals()
        self._on_mode_changed() # Set initial UI state

    def get_display_name(self) -> str:
        return "Intrinsic Properties" # Updated name

    def _setup_ui(self):
        """Set up the UI elements for the Rin/G Analysis tab (Generalized)."""
        log.debug("Setting up Rin/G Analysis Tab UI (Generalized)...")
        main_layout = QtWidgets.QVBoxLayout()
        main_layout.setContentsMargins(5, 5, 5, 5)
        main_layout.setSpacing(5)

        # Create a scroll area for the controls to handle overflow
        controls_scroll_area = QtWidgets.QScrollArea()
        controls_scroll_area.setWidgetResizable(True)
        controls_scroll_area.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        controls_scroll_area.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        controls_scroll_area.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        
        # Create a widget to hold the controls
        controls_container = QtWidgets.QWidget()
        controls_scroll_area.setWidget(controls_container)
        
        # --- Top: Controls Area ---
        top_controls_layout = QtWidgets.QHBoxLayout(controls_container)
        top_controls_layout.setContentsMargins(5, 5, 5, 5)
        top_controls_layout.setSpacing(10)

        # --- Column 1: Data Selection --- 
        self.data_selection_group = QtWidgets.QGroupBox("Data Selection")
        self.data_selection_group.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Preferred,
            QtWidgets.QSizePolicy.Policy.Maximum
        )
        data_selection_layout = QtWidgets.QFormLayout(self.data_selection_group)
        data_selection_layout.setFieldGrowthPolicy(QtWidgets.QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        data_selection_layout.setContentsMargins(10, 10, 10, 10)
        data_selection_layout.setVerticalSpacing(8)

        # Use Base Class Item Combobox
        self._setup_analysis_item_selector(data_selection_layout)

        # Signal Channel Combobox (Renamed from voltage_channel_combobox)
        self.signal_channel_label = QtWidgets.QLabel("Signal Channel:") # RENAMED LABEL
        self.signal_channel_combobox = QtWidgets.QComboBox()
        self.signal_channel_combobox.setToolTip("Select the primary signal channel (Voltage or Current) to analyze.")
        data_selection_layout.addRow(self.signal_channel_label, self.signal_channel_combobox)

        # Data Source Combobox (Trial/Average)
        self.data_source_label = QtWidgets.QLabel("Data Source:")
        self.data_source_combobox = QtWidgets.QComboBox()
        self.data_source_combobox.setToolTip("Select the specific trial or average trace to analyze.")
        data_selection_layout.addRow(self.data_source_label, self.data_source_combobox)

        top_controls_layout.addWidget(self.data_selection_group)

        # --- Column 2: Analysis Parameters ---
        self.analysis_params_group = QtWidgets.QGroupBox("Analysis Parameters")
        self.analysis_params_group.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Preferred, 
            QtWidgets.QSizePolicy.Policy.Maximum
        )
        analysis_params_layout = QtWidgets.QVBoxLayout(self.analysis_params_group)
        analysis_params_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)
        analysis_params_layout.setContentsMargins(10, 10, 10, 10)
        analysis_params_layout.setSpacing(8)

        # Mode Selection (Interactive/Manual)
        mode_layout = QtWidgets.QHBoxLayout()
        mode_layout.setSpacing(10)
        mode_label = QtWidgets.QLabel("Analysis Mode:")
        mode_label.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Maximum,
            QtWidgets.QSizePolicy.Policy.Preferred
        )
        mode_layout.addWidget(mode_label)
        
        self.mode_combobox = QtWidgets.QComboBox()
        self.mode_combobox.addItem("Interactive (Regions)", userData=self._MODE_INTERACTIVE)
        self.mode_combobox.addItem("Manual (Time Windows)", userData=self._MODE_MANUAL)
        self.mode_combobox.setToolTip("Select how to define baseline/response windows.")
        mode_layout.addWidget(self.mode_combobox)
        analysis_params_layout.addLayout(mode_layout)

        # --- Interactive Regions Info ---
        self.interactive_info_label = QtWidgets.QLabel("Drag blue (baseline) and red (response) regions on the plot.")
        self.interactive_info_label.setWordWrap(True)
        self.interactive_info_label.setVisible(True) # Initially visible
        analysis_params_layout.addWidget(self.interactive_info_label)

        # --- Manual Time Windows Group ---
        self.manual_time_group = QtWidgets.QGroupBox("Manual Time Windows")
        self.manual_time_group.setVisible(False) # Initially hidden
        manual_time_layout = QtWidgets.QFormLayout(self.manual_time_group)
        manual_time_layout.setFieldGrowthPolicy(QtWidgets.QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        manual_time_layout.setContentsMargins(10, 10, 10, 10)
        manual_time_layout.setVerticalSpacing(8)

        self.manual_baseline_start_spinbox = QtWidgets.QDoubleSpinBox()
        self.manual_baseline_end_spinbox = QtWidgets.QDoubleSpinBox()
        self.manual_response_start_spinbox = QtWidgets.QDoubleSpinBox()
        self.manual_response_end_spinbox = QtWidgets.QDoubleSpinBox()
        for spinbox in [self.manual_baseline_start_spinbox, self.manual_baseline_end_spinbox,
                        self.manual_response_start_spinbox, self.manual_response_end_spinbox]:
            spinbox.setSuffix(" s")
            spinbox.setDecimals(3)
            spinbox.setSingleStep(0.01)
            spinbox.setRange(0, 9999.999) # Arbitrarily large range
            spinbox.setMinimumWidth(100)
        manual_time_layout.addRow("Baseline Start (s):", self.manual_baseline_start_spinbox)
        manual_time_layout.addRow("Baseline End (s):", self.manual_baseline_end_spinbox)
        manual_time_layout.addRow("Response Start (s):", self.manual_response_start_spinbox)
        manual_time_layout.addRow("Response End (s):", self.manual_response_end_spinbox)
        analysis_params_layout.addWidget(self.manual_time_group)

        # --- Manual Delta Input Group ---
        # Contains either Delta I or Delta V input depending on channel type
        self.delta_input_group = QtWidgets.QGroupBox("Step Amplitude Input")
        self.delta_input_group.setToolTip("Enter the amplitude of the current or voltage step")
        self.delta_i_form_layout = QtWidgets.QFormLayout(self.delta_input_group)
        self.delta_i_form_layout.setFieldGrowthPolicy(QtWidgets.QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        self.delta_i_form_layout.setContentsMargins(10, 10, 10, 10)
        self.delta_i_form_layout.setVerticalSpacing(8)

        # Manual Delta I (for Voltage Clamp primary signal)
        self.manual_delta_i_label = QtWidgets.QLabel("Manual ΔI (pA):")
        self.manual_delta_i_spinbox = QtWidgets.QDoubleSpinBox()
        self.manual_delta_i_spinbox.setToolTip("Enter the known current step amplitude (ΔI) in pA.")
        self.manual_delta_i_spinbox.setDecimals(1)
        self.manual_delta_i_spinbox.setRange(-1e6, 1e6) # Large range
        self.manual_delta_i_spinbox.setValue(0.0)
        self.manual_delta_i_spinbox.setMinimumWidth(100)
        self.delta_i_input_row_widgets = (self.manual_delta_i_label, self.manual_delta_i_spinbox) # Store widgets
        self.delta_i_form_layout.addRow(self.manual_delta_i_label, self.manual_delta_i_spinbox)
        self.manual_delta_i_label.setVisible(False) # Initially hidden
        self.manual_delta_i_spinbox.setVisible(False)

        # Manual Delta V (for Current Clamp primary signal) - ADDED
        self.manual_delta_v_label = QtWidgets.QLabel("Manual ΔV (mV):")
        self.manual_delta_v_spinbox = QtWidgets.QDoubleSpinBox()
        self.manual_delta_v_spinbox.setToolTip("Enter the known voltage step amplitude (ΔV) in mV.")
        self.manual_delta_v_spinbox.setDecimals(1)
        self.manual_delta_v_spinbox.setRange(-1000, 1000) # Large range
        self.manual_delta_v_spinbox.setValue(0.0)
        self.manual_delta_v_spinbox.setMinimumWidth(100)
        self.delta_v_input_row_widgets = (self.manual_delta_v_label, self.manual_delta_v_spinbox) # Store widgets
        self.delta_i_form_layout.addRow(self.manual_delta_v_label, self.manual_delta_v_spinbox)
        self.manual_delta_v_label.setVisible(False) # Initially hidden
        self.manual_delta_v_spinbox.setVisible(False)

        analysis_params_layout.addWidget(self.delta_input_group)

        # Run button to manually execute analysis
        self.run_button = QtWidgets.QPushButton("Calculate Rin")
        self.run_button.setToolTip("Use current window settings to calculate input resistance")
        style_button(self.run_button, 'primary')  # Apply consistent styling directly
        self.run_button.setVisible(False) # Initially hidden
        analysis_params_layout.addWidget(self.run_button)

        # Info label for guidance
        self.info_label = QtWidgets.QLabel("Info will appear here.")
        self.info_label.setWordWrap(True)
        # Use styling module instead of inline style
        style_info_label(self.info_label)
        analysis_params_layout.addWidget(self.info_label)

        # Other properties buttons
        other_props_group = QtWidgets.QGroupBox("Other Properties")
        other_props_layout = QtWidgets.QHBoxLayout(other_props_group)
        self.tau_button = QtWidgets.QPushButton("Calculate Tau")
        self.sag_button = QtWidgets.QPushButton("Calculate Sag Ratio")
        other_props_layout.addWidget(self.tau_button)
        other_props_layout.addWidget(self.sag_button)
        analysis_params_layout.addWidget(other_props_group)


        analysis_params_layout.addStretch(1)
        top_controls_layout.addWidget(self.analysis_params_group)

        # --- Column 3: Results (Add Conductance) ---
        self.results_group = QtWidgets.QGroupBox("Results")
        self.results_group.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding, 
            QtWidgets.QSizePolicy.Policy.Maximum
        )
        results_layout = QtWidgets.QVBoxLayout(self.results_group)
        results_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)
        results_layout.setContentsMargins(10, 10, 10, 10)
        results_layout.setSpacing(8)
        
        self.rin_result_label = QtWidgets.QLabel("Resistance (Rin) / Conductance (G): --")
        self.rin_result_label.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
        # Use styling module instead of inline style
        style_result_display(self.rin_result_label)
        results_layout.addWidget(self.rin_result_label)
        
        self.delta_v_label = QtWidgets.QLabel("Voltage Change (ΔV): --")
        self.delta_v_label.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
        results_layout.addWidget(self.delta_v_label)
        
        self.delta_i_label = QtWidgets.QLabel("Current Change (ΔI): --")
        self.delta_i_label.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
        results_layout.addWidget(self.delta_i_label)

        # Other properties
        self.tau_result_label = QtWidgets.QLabel("Tau: --")
        results_layout.addWidget(self.tau_result_label)
        self.sag_result_label = QtWidgets.QLabel("Sag Ratio: --")
        results_layout.addWidget(self.sag_result_label)

        self.status_label = QtWidgets.QLabel("Status: Idle")
        self.status_label.setWordWrap(True)
        results_layout.addWidget(self.status_label)
        
        # Add a horizontal separator line
        line = QtWidgets.QFrame()
        line.setFrameShape(QtWidgets.QFrame.Shape.HLine)
        line.setFrameShadow(QtWidgets.QFrame.Shadow.Sunken)
        results_layout.addWidget(line)
        
        # Call the base class method to set up the save button
        self._setup_save_button(results_layout)
        
        results_layout.addStretch(1)
        top_controls_layout.addWidget(self.results_group)

        # Add the scroll area to the main layout
        main_layout.addWidget(controls_scroll_area, 0)

        # --- Bottom: Plot Area (Unchanged) ---
        plot_container = QtWidgets.QWidget()
        plot_layout = QtWidgets.QVBoxLayout(plot_container)
        plot_layout.setContentsMargins(0,0,0,0)
        self._setup_plot_area(plot_layout)
        
        main_layout.addWidget(plot_container, 1)

        # Add RIN-specific plot items - simple approach
        if self.plot_widget:
            plot_item = self.plot_widget.getPlotItem()
            if plot_item:
                from PySide6 import QtGui
                from Synaptipy.shared.styling import get_baseline_pen, get_response_pen
                
                # Create regions and lines with consistent styling
                baseline_brush = QtGui.QBrush(QtGui.QColor(46, 204, 113, 50))  # Green with alpha
                response_brush = QtGui.QBrush(QtGui.QColor(243, 156, 18, 50))  # Orange with alpha
                
                self.baseline_region = pg.LinearRegionItem(values=[0.0, 0.1], brush=baseline_brush, movable=True, bounds=[0, 1])
                self.response_region = pg.LinearRegionItem(values=[0.2, 0.3], brush=response_brush, movable=True, bounds=[0, 1])
                self.baseline_line = pg.InfiniteLine(angle=0, movable=False, pen=get_baseline_pen())
                self.response_line = pg.InfiniteLine(angle=0, movable=False, pen=get_response_pen())
                
                # Plot items will be added when data is loaded to prevent Qt graphics errors

        self.setLayout(main_layout)
        log.debug("Rin/G Analysis Tab UI setup complete (Generalized).")
        
        # Set initial UI state
        self._on_mode_changed()  # Ensure proper initial UI setup

    def _connect_signals(self):
        # Connect signals for widgets common to all tabs
        super()._connect_signals()

        # Mode switching
        if self.mode_combobox: self.mode_combobox.currentTextChanged.connect(self._on_mode_changed)

        # Data selection - Use NEW specific slots
        if self.signal_channel_combobox: self.signal_channel_combobox.currentIndexChanged.connect(self._on_signal_channel_changed)
        if self.data_source_combobox: self.data_source_combobox.currentIndexChanged.connect(self._on_data_source_changed)

        # Manual time window inputs - Connect with valueChanged instead of editingFinished
        if self.manual_baseline_start_spinbox: 
            self.manual_baseline_start_spinbox.valueChanged.connect(self._trigger_analysis_if_manual)
        if self.manual_baseline_end_spinbox: 
            self.manual_baseline_end_spinbox.valueChanged.connect(self._trigger_analysis_if_manual)
        if self.manual_response_start_spinbox: 
            self.manual_response_start_spinbox.valueChanged.connect(self._trigger_analysis_if_manual)
        if self.manual_response_end_spinbox: 
            self.manual_response_end_spinbox.valueChanged.connect(self._trigger_analysis_if_manual)
        
        # Connect delta input spinboxes with valueChanged for immediate feedback
        if self.manual_delta_i_spinbox: 
            self.manual_delta_i_spinbox.valueChanged.connect(self._trigger_analysis_if_manual)
        if self.manual_delta_v_spinbox: 
            self.manual_delta_v_spinbox.valueChanged.connect(self._trigger_analysis_if_manual)
        
        # Connect Run button
        if self.run_button: 
            self.run_button.clicked.connect(self._run_analysis)

        # Connect other properties buttons
        if self.tau_button: self.tau_button.clicked.connect(self._calculate_tau)
        if self.sag_button: self.sag_button.clicked.connect(self._calculate_sag_ratio)

        # Ensure plot regions update triggers analysis in interactive mode
        if self.baseline_region: self.baseline_region.sigRegionChanged.connect(self._trigger_analysis_if_interactive)
        if self.response_region: self.response_region.sigRegionChanged.connect(self._trigger_analysis_if_interactive)

    # --- NEW Slots for internal combobox changes ---
    @QtCore.Slot()
    def _on_signal_channel_changed(self):
        """Called when the signal channel combobox selection changes."""
        log.debug("Signal channel selection changed, replotting.")
        self._plot_selected_trace()
        # Analysis might need re-triggering depending on mode
        if self.mode_combobox and self.mode_combobox.currentText() == self._MODE_INTERACTIVE:
             self._run_analysis()
        elif self.mode_combobox and self.mode_combobox.currentText() == self._MODE_MANUAL:
             self._clear_results_display() # Clear old results for manual mode
             # Consider if manual analysis should re-run automatically?

    @QtCore.Slot()
    def _on_data_source_changed(self):
        """Called when the data source combobox selection changes."""
        log.debug("Data source selection changed, replotting.")
        self._plot_selected_trace()
        # Analysis might need re-triggering depending on mode
        if self.mode_combobox and self.mode_combobox.currentText() == self._MODE_INTERACTIVE:
             self._run_analysis()
        elif self.mode_combobox and self.mode_combobox.currentText() == self._MODE_MANUAL:
             self._clear_results_display() # Clear old results for manual mode
             # Consider if manual analysis should re-run automatically?

    # --- Analysis Triggering ---

    def _trigger_analysis_if_interactive(self):
        """Trigger analysis only if the current mode is Interactive."""
        if self.mode_combobox and self.mode_combobox.currentText() == self._MODE_INTERACTIVE:
            log.debug("Interactive region changed, triggering analysis.")
            self._run_analysis()
        else:
            log.debug("Interactive region changed, but mode is not Interactive. Skipping analysis.")

    def _trigger_analysis_if_manual(self):
        """Update Run button state when manual inputs change."""
        if self.mode_combobox and self.mode_combobox.currentText() == self._MODE_MANUAL:
            log.debug("Manual input changed, updating run button state.")
            # Don't auto-run when inputs change, just update the button state
            self._update_run_button_state()
            
            # Force button to be visible if we're in manual mode with data
            if self.run_button and self._current_plot_data:
                self.run_button.setVisible(True)
        else:
            log.debug("Manual input changed, but mode is not Manual. Skipping update.")

    def _run_analysis(self):
        """Main method to perform Rin/G analysis based on current settings."""
        log.debug("Running Rin/G analysis...")
        
        # Check if we have valid data to operate on
        if not self._current_plot_data or "time_vec" not in self._current_plot_data or "data_vec" not in self._current_plot_data:
            log.warning("No valid data available for Rin/G analysis.")
            self.status_label.setText("Status: No valid data for analysis.")
            return
        
        # Get the current mode
        is_interactive = (self.mode_combobox and self.mode_combobox.currentText() == self._MODE_INTERACTIVE)
        is_manual = not is_interactive
        
        # Get data vectors from current data
        time_vec = self._current_plot_data["time_vec"]
        data_vec = self._current_plot_data["data_vec"]
        units = self._current_plot_data.get("units", "unknown")
        
        # Determine if we're dealing with voltage or current signal
        is_voltage = 'mv' in units.lower() if units else False
        is_current = 'pa' in units.lower() or 'na' in units.lower() if units else False
        
        # Get baseline and response windows based on mode
        baseline_window = None
        response_window = None
        delta_i_pa = None
        delta_v_mv = None
        
        # --- Get windows and delta values based on mode ---
        if is_interactive:
            # Get regions from interactive regions
            if not self.baseline_region or not self.response_region:
                log.warning("Interactive regions not available.")
                self.status_label.setText("Status: Interactive regions not available.")
                return
                
            # Get window boundaries from regions
            baseline_window = self.baseline_region.getRegion()
            response_window = self.response_region.getRegion()
            
            # For interactive mode, we need to calculate delta_v from the signal
            # and we might need a manual delta_i if we're analyzing a voltage trace
            if is_voltage:
                # We're analyzing voltage, so we need delta_i input
                delta_i_pa = self.manual_delta_i_spinbox.value() if self.manual_delta_i_spinbox else 0.0
                if np.isclose(delta_i_pa, 0.0):
                    log.warning("Cannot calculate Rin: Missing or zero delta I value.")
                    self.status_label.setText("Status: Please provide a non-zero ΔI value.")
                    return
            elif is_current:
                # We're analyzing current, so we need delta_v input
                delta_v_mv = self.manual_delta_v_spinbox.value() if self.manual_delta_v_spinbox else 0.0
                if np.isclose(delta_v_mv, 0.0):
                    log.warning("Cannot calculate conductance: Missing or zero delta V value.")
                    self.status_label.setText("Status: Please provide a non-zero ΔV value.")
                    return
            
        elif is_manual:
            # Get windows from manual spinboxes
            if not all([self.manual_baseline_start_spinbox, self.manual_baseline_end_spinbox,
                        self.manual_response_start_spinbox, self.manual_response_end_spinbox]):
                log.warning("Manual spinboxes not available.")
                self.status_label.setText("Status: Manual time input fields not available.")
                return
                
            baseline_window = (self.manual_baseline_start_spinbox.value(), self.manual_baseline_end_spinbox.value())
            response_window = (self.manual_response_start_spinbox.value(), self.manual_response_end_spinbox.value())
            
            # Get delta values from manual spinboxes
            if is_voltage:
                delta_i_pa = self.manual_delta_i_spinbox.value() if self.manual_delta_i_spinbox else 0.0
                if np.isclose(delta_i_pa, 0.0):
                    log.warning("Cannot calculate Rin: Missing or zero delta I value.")
                    self.status_label.setText("Status: Please provide a non-zero ΔI value.")
                    return
            elif is_current:
                delta_v_mv = self.manual_delta_v_spinbox.value() if self.manual_delta_v_spinbox else 0.0
                if np.isclose(delta_v_mv, 0.0):
                    log.warning("Cannot calculate conductance: Missing or zero delta V value.")
                    self.status_label.setText("Status: Please provide a non-zero ΔV value.")
                    return
        
        # Validate windows
        if not baseline_window or not response_window:
            log.warning("Invalid baseline/response windows for analysis.")
            self.status_label.setText("Status: Invalid baseline/response windows.")
            return
            
        # --- Perform the actual calculation ---
        try:
            if is_voltage:  # Voltage clamp mode - calculate Rin
                # Call the calculate_rin function with appropriate parameters
                result = calculate_rin(
                    time_v=time_vec,
                    voltage=data_vec,
                    baseline_window=baseline_window,
                    response_window=response_window,
                    delta_i_pa=delta_i_pa
                )
                
                if result is not None:
                    rin_megaohms, delta_v = result
                    
                    # Display results
                    self.rin_result_label.setText(f"Input Resistance (Rin): {rin_megaohms:.2f} MΩ | Conductance: {1000/rin_megaohms:.4f} μS")
                    self.delta_v_label.setText(f"Voltage Change (ΔV): {delta_v:.2f} mV")
                    self.delta_i_label.setText(f"Current Change (ΔI): {delta_i_pa:.2f} pA")
                    self.status_label.setText("Status: Rin calculation successful")
                    
                    # Store result for potential saving
                    self._last_rin_result = {
                        "Rin (MΩ)": rin_megaohms,
                        "Conductance (μS)": 1000/rin_megaohms,
                        "ΔV (mV)": delta_v,
                        "ΔI (pA)": delta_i_pa,
                        "Baseline Window (s)": baseline_window,
                        "Response Window (s)": response_window,
                        "analysis_type": "Input Resistance",  # Add analysis type for better reporting
                        "source_file_name": self._selected_item_recording.source_file.name if self._selected_item_recording else "Unknown"
                    }
                    
                    # Update lines showing the mean levels
                    bl_indices = np.where((time_vec >= baseline_window[0]) & (time_vec <= baseline_window[1]))[0]
                    resp_indices = np.where((time_vec >= response_window[0]) & (time_vec <= response_window[1]))[0]
                    
                    if len(bl_indices) > 0 and len(resp_indices) > 0:
                        mean_baseline = np.mean(data_vec[bl_indices])
                        mean_response = np.mean(data_vec[resp_indices])
                        
                        # Update lines
                        if self.baseline_line:
                            self.baseline_line.setValue(mean_baseline)
                            self.baseline_line.setVisible(True)
                        if self.response_line:
                            self.response_line.setValue(mean_response)
                            self.response_line.setVisible(True)
                    
                    # Enable save button - make sure this line is executed
                    if hasattr(self, '_set_save_button_enabled'):
                        self._set_save_button_enabled(True)
                        log.debug("Save button enabled after successful calculation")
                    
                else:
                    self.status_label.setText("Status: Rin calculation failed. Check input values.")
                    log.warning("Rin calculation returned None.")
                
            elif is_current:  # Current clamp mode - calculate conductance instead
                # Here we are analyzing a current trace, so we calculate conductance
                # from the current changes
                # Need to re-use similar calculations but swap V/I directions
                
                # Calculate mean baseline and response current
                bl_indices = np.where((time_vec >= baseline_window[0]) & (time_vec <= baseline_window[1]))[0]
                resp_indices = np.where((time_vec >= response_window[0]) & (time_vec <= response_window[1]))[0]
                
                if len(bl_indices) == 0 or len(resp_indices) == 0:
                    self.status_label.setText("Status: No data points found in baseline/response windows.")
                    return
                
                mean_baseline_i = np.mean(data_vec[bl_indices])
                mean_response_i = np.mean(data_vec[resp_indices])
                
                # Calculate delta I (in pA)
                delta_i = mean_response_i - mean_baseline_i
                
                # Calculate conductance: G = ΔI/ΔV
                # If ΔV is in mV and ΔI is in pA, G will be in μS (micro-Siemens)
                conductance_us = delta_i / delta_v_mv
                
                # Calculate resistance (in MΩ)
                resistance_mohm = 1000 / conductance_us  # 1000 is to convert from μS to nS
                
                # Display results
                self.rin_result_label.setText(f"Input Resistance (Rin): {resistance_mohm:.2f} MΩ | Conductance: {conductance_us:.4f} μS")
                self.delta_v_label.setText(f"Voltage Change (ΔV): {delta_v_mv:.2f} mV")
                self.delta_i_label.setText(f"Current Change (ΔI): {delta_i:.2f} pA")
                self.status_label.setText("Status: Conductance calculation successful")
                
                # Store result for potential saving
                self._last_rin_result = {
                    "Rin (MΩ)": resistance_mohm,
                    "Conductance (μS)": conductance_us,
                    "ΔV (mV)": delta_v_mv,
                    "ΔI (pA)": delta_i,
                    "Baseline Window (s)": baseline_window,
                    "Response Window (s)": response_window,
                    "analysis_type": "Conductance",  # Add analysis type for better reporting
                    "source_file_name": self._selected_item_recording.source_file.name if self._selected_item_recording else "Unknown"
                }
                
                # Update lines showing the mean levels
                if self.baseline_line:
                    self.baseline_line.setValue(mean_baseline_i)
                    self.baseline_line.setVisible(True)
                if self.response_line:
                    self.response_line.setValue(mean_response_i)
                    self.response_line.setVisible(True)
                
                # Enable save button - make sure this line is executed
                if hasattr(self, '_set_save_button_enabled'):
                    self._set_save_button_enabled(True)
                    log.debug("Save button enabled after successful calculation")
                
            else:
                self.status_label.setText(f"Status: Unknown units '{units}'. Cannot determine analysis type.")
                log.warning(f"Unknown units '{units}' - cannot determine if voltage or current clamp.")
        
        except Exception as e:
            self.status_label.setText(f"Status: Error during analysis: {str(e)}")
            log.error(f"Error running Rin/G analysis: {e}", exc_info=True)
            
        # Force layout update - IMPORTANT for visibility changes
        self.layout().activate()
        # Force repaint of plot widget and the tab itself
        self.plot_widget.update()
        self.update()

    def _clear_results_display(self):
        """Clears only the text results labels."""
        if self.rin_result_label: self.rin_result_label.setText("Resistance (Rin) / Conductance (G): --")
        if self.delta_v_label: self.delta_v_label.setText("Voltage Change (ΔV): --") 
        if self.delta_i_label: self.delta_i_label.setText("Current Change (ΔI): --")
        if self.tau_result_label: self.tau_result_label.setText("Tau: --")
        if self.sag_result_label: self.sag_result_label.setText("Sag Ratio: --")
        if self.status_label: self.status_label.setText("Status: Idle")
        # Hide lines
        if self.baseline_line: self.baseline_line.setVisible(False)
        if self.response_line: self.response_line.setVisible(False)
        # Use correct base class method for save button
        if hasattr(self, '_set_save_button_enabled'):
            self._set_save_button_enabled(False)
            log.debug("Save button disabled during results clear")

    def _on_mode_changed(self, mode_text=None):
        """Handles changes in the analysis mode combobox.
           ONLY updates UI visibility via _update_mode_dependent_ui and triggers analysis if needed.
        """
        if mode_text is None:
            if not self.mode_combobox: return
            mode_text = self.mode_combobox.currentText()
        log.debug(f"Rin/G mode changed to: {mode_text}")

        # Update UI visibility based on the new mode
        self._update_mode_dependent_ui()

        # Trigger analysis only if switching TO interactive and data is ready
        is_interactive = (mode_text == self._MODE_INTERACTIVE)
        has_data_plotted = self.plot_item is not None # Check if plot exists
        if is_interactive and has_data_plotted:
            log.debug("Mode switched to Interactive with data, triggering analysis.")
            self._run_analysis()

    # --- Mode and Plot Dependent UI Updates --- # NEW METHOD
    def _update_mode_dependent_ui(self):
        """Updates visibility of UI elements based on mode and plot state."""
        if not self.mode_combobox: return # Not ready yet
        
        mode_text = self.mode_combobox.currentText()
        is_interactive = (mode_text == self._MODE_INTERACTIVE)
        is_manual = (mode_text == self._MODE_MANUAL)
        
        log.debug(f"Updating mode dependent UI: Mode text='{mode_text}', _MODE_MANUAL='{self._MODE_MANUAL}', is_manual={is_manual}")

        # Determine if we have data plotted (use plot_item as indicator)
        has_data_plotted = self.plot_item is not None

        log.debug(f"Updating mode dependent UI: Mode='{mode_text}', HasDataPlotted={has_data_plotted}")

        # Visibility for interactive regions (Only if Interactive AND data plotted)
        visibility_interactive = is_interactive and has_data_plotted
        if self.baseline_region:
            self.baseline_region.setVisible(visibility_interactive)
        if self.response_region:
            self.response_region.setVisible(visibility_interactive)
        # Also hide/show associated lines
        if self.baseline_line: self.baseline_line.setVisible(visibility_interactive and self._last_rin_result is not None)
        if self.response_line: self.response_line.setVisible(visibility_interactive and self._last_rin_result is not None)
            
        # Visibility for interactive mode info label
        if self.interactive_info_label: 
            self.interactive_info_label.setVisible(is_interactive)

        # Visibility for manual time input group (Only if Manual)
        if self.manual_time_group: 
            self.manual_time_group.setVisible(is_manual)

        # Determine channel type based on units for ALL modes
        units_str = None
        if has_data_plotted and self._selected_item_recording and self.signal_channel_combobox and self.signal_channel_combobox.currentIndex() >= 0:
            ch_key = self.signal_channel_combobox.currentData()
            if ch_key:
                channel = self._selected_item_recording.channels.get(ch_key)
                if channel and channel.units:
                    units_str = channel.units.lower()
        
        # Determine which delta input field to show based on the channel units
        show_delta_i = has_data_plotted and units_str and 'mv' in units_str
        show_delta_v = has_data_plotted and units_str and ('pa' in units_str or 'na' in units_str)
        
        log.debug(f"Unit detection: units_str={units_str}, show_delta_i={show_delta_i}, show_delta_v={show_delta_v}")
        
        # Make delta inputs visible for BOTH interactive and manual modes
        if self.delta_i_input_row_widgets:
            label, spinbox = self.delta_i_input_row_widgets
            if label: label.setVisible(show_delta_i)
            if spinbox: spinbox.setVisible(show_delta_i)

        if self.delta_v_input_row_widgets:
            label, spinbox = self.delta_v_input_row_widgets
            if label: label.setVisible(show_delta_v)
            if spinbox: spinbox.setVisible(show_delta_v)
 
        # Always show the delta input group if any inputs are shown
        if self.delta_input_group:
            self.delta_input_group.setVisible(has_data_plotted and (show_delta_i or show_delta_v))

        # Enable/Disable Run button (only relevant for Manual mode)
        if self.run_button: 
            # Always show the run button in manual mode with data
            self.run_button.setVisible(is_manual and has_data_plotted)
            self._update_run_button_state()  # Update enabled state based on input values

        # Update info label based on mode
        if self.info_label:
            if is_interactive:
                info = "Interactive Mode: Drag the Baseline and Response regions on the plot."
                # Add info about entering delta values
                if show_delta_i:
                    info += " Enter the step current (ΔI) in the field above."
                elif show_delta_v:
                    info += " Enter the step voltage (ΔV) in the field above."
            elif is_manual:
                info = "Manual Mode: Set time windows and "
                if show_delta_i:
                    info += "ΔI manually, then press the Calculate button."
                elif show_delta_v:
                    info += "ΔV manually, then press the Calculate button."
                else:
                    info += "parameters manually, then press the Calculate button."
            else:
                info = "Select a mode."
            self.info_label.setText(info)

        # Force layout update after visibility changes
        self.layout().activate()
        # Force repaint might still be needed sometimes
        self.plot_widget.update()
        self.update()

    # --- UI Update Method --- 
    def _update_ui_for_selected_item(self):
        """
        Updates the UI elements specific to Rin/G analysis when a new 
        analysis item is selected.
        Populates channel list, data source list, and triggers plotting.
        """
        log.debug(f"Rin/G: Updating UI for selected item index {self._selected_item_index}")
        
        # Clear previous state and plot
        # Block signals during programmatic changes
        if self.signal_channel_combobox: self.signal_channel_combobox.blockSignals(True)
        if self.data_source_combobox: self.data_source_combobox.blockSignals(True)
        
        if self.signal_channel_combobox: self.signal_channel_combobox.clear()
        if self.data_source_combobox: self.data_source_combobox.clear()

        if self.plot_widget:
            self.plot_widget.clear()
        self._last_rin_result = None
        self._clear_results_display() # Clear result labels
        # Disable controls by default
        is_data_valid = False

        if self._selected_item_recording:
            # Populate Signal Channel Combobox
            if self._selected_item_recording.channels:
                # NEW: Iterate through channels to create descriptive names
                for key, channel in self._selected_item_recording.channels.items():
                    display_text = f"{channel.name} ({channel.units})" if channel.units else channel.name
                    self.signal_channel_combobox.addItem(display_text, userData=key)
                
                self.signal_channel_combobox.setCurrentIndex(0) # Select first channel by default
                is_data_valid = True # Enable further UI if channels exist
            else:
                self.signal_channel_combobox.addItem("No Channels Found")
            # self.signal_channel_combobox.blockSignals(False) # Unblock later

            # Populate Data Source Combobox based on the first channel (assume homogeneity)
            first_channel_key = self.signal_channel_combobox.currentData() if self.signal_channel_combobox.count() > 0 else None # NEW: Get key of first item
            if first_channel_key: # NEW
                # CORRECT ACCESS: Use dictionary lookup
                first_channel = self._selected_item_recording.channels.get(first_channel_key)
                # self.data_source_combobox.blockSignals(True) # Already blocked
                if first_channel:
                    num_trials = first_channel.num_trials
                    # Correct way to check if average data is available
                    has_average = first_channel.get_averaged_data() is not None
                    
                    log.debug(f"Determined from first channel: num_trials={num_trials}, has_average={has_average}")

                    available_sources = []
                    if has_average:
                        available_sources.append(("Average", "average"))
                    for i in range(num_trials):
                        available_sources.append((f"Trial {i + 1}", f"trial_{i}"))
                    
                    if available_sources:
                        for display_name, data_key in available_sources:
                            self.data_source_combobox.addItem(display_name, userData=data_key)
                        self.data_source_combobox.setCurrentIndex(0) # Select first available source
                    else:
                        self.data_source_combobox.addItem("No Traces Found")
                        is_data_valid = False # Cannot analyze if no traces
                else:
                     self.data_source_combobox.addItem("Error reading channel")
                     is_data_valid = False
                # self.data_source_combobox.blockSignals(False) # Unblock later
            else:
                 self.data_source_combobox.addItem("No channels")
                 is_data_valid = False
        else:
            # Handle case where recording didn't load or no item selected
            self.signal_channel_combobox.addItem("No Recording Selected")
            self.data_source_combobox.addItem("No Recording Selected")

        # --- Unblock Signals --- 
        if self.signal_channel_combobox: self.signal_channel_combobox.blockSignals(False)
        if self.data_source_combobox: self.data_source_combobox.blockSignals(False)

        # Enable/Disable controls based on data validity
        self.signal_channel_combobox.setEnabled(is_data_valid)
        self.data_source_combobox.setEnabled(is_data_valid)
        self.analysis_params_group.setEnabled(is_data_valid)
        self.results_group.setEnabled(is_data_valid)
        self.mode_combobox.setEnabled(is_data_valid)
        # Save button is handled separately by _update_save_button_state

        # Update mode-dependent UI elements (regions, manual inputs)
        # REMOVED: self._on_mode_changed() # This was likely causing loops/redundancy

        # Plot the selected trace if data is valid
        if is_data_valid:
            log.debug("Data is valid, attempting to plot initial trace.")
            self._plot_selected_trace()
        else:
            log.debug("Data is invalid or unavailable, clearing plot and disabling UI.")
            if self.plot_widget: self.plot_widget.clear()
            # Ensure regions/lines are hidden if no data
            if self.baseline_region: self.baseline_region.setVisible(False)
            if self.response_region: self.response_region.setVisible(False)
            if self.baseline_line: self.baseline_line.setVisible(False)
            if self.response_line: self.response_line.setVisible(False)

    # --- ADDED: Helper to get plot data (Adapted from Baseline Tab) ---
    def _get_data_for_plotting(self, channel_name: str, data_source_key: str) -> Optional[Dict[str, Any]]:
        """Fetches the appropriate data array and time vector based on source.
           Returns a dictionary with data, labels, pen, etc., or None on failure.
        """
        if not self._selected_item_recording or channel_name not in self._selected_item_recording.channels:
            log.error(f"_get_data_for_plotting: Invalid recording or channel name '{channel_name}'.")
            return None

        channel = self._selected_item_recording.channels[channel_name]
        time_vec, data_vec = None, None
        
        # Use original blue color (55, 126, 184) instead of styling module
        pen = pg.mkPen(color=(55, 126, 184)) # Original pen color (blueish)

        try:
            if data_source_key == "average":
                data_vec = channel.get_averaged_data()
                time_vec = channel.get_relative_averaged_time_vector() # Use relative time
                pen = pg.mkPen(color=(55, 126, 184)) # Original blue color
                if data_vec is None or time_vec is None:
                    log.warning(f"Could not get averaged data/time for channel {channel_name}.")
                    return None
            elif data_source_key.startswith("trial_"):
                trial_index = int(data_source_key.split("_")[1])
                data_vec = channel.get_data(trial_index)
                time_vec = channel.get_relative_time_vector(trial_index) # Use relative time
                if data_vec is None or time_vec is None:
                    log.warning(f"Could not get data/time for trial {trial_index} of channel {channel_name}.")
                    return None
            else:
                log.error(f"Unknown data source key: {data_source_key}")
                return None

            # Determine labels based on channel units
            y_axis_label = f"{channel.get_primary_data_label()} ({channel.units})" if channel.units else channel.get_primary_data_label()
            channel_label = channel.name # Use channel name for reference

            return {
                "time_vector": time_vec,
                "data_vector": data_vec,
                "channel_label": channel_label,
                "y_axis_label": y_axis_label,
                "units": channel.units,
                "sampling_rate": channel.sampling_rate,
                "pen": pen
            }

        except Exception as e:
            log.error(f"Error getting data for plotting {channel_name}, {data_source_key}: {e}", exc_info=True)
            return None

    # --- Plotting --- 
    def _plot_selected_trace(self):
        """Plots the data trace based on selected channel and data source."""
        if not self._selected_item_recording or \
           not self.signal_channel_combobox or \
           not self.data_source_combobox or \
           not self.plot_widget:
            log.debug("Plotting skipped: Missing recording, comboboxes, or plot widget.")
            if self.plot_widget: self.plot_widget.clear() # Clear if widgets exist but no data
            return

        # Clear previous plot items (including regions and lines)
        self.plot_widget.clear()
        self.plot_item = None # Reset plot item reference
        # Important: Re-add regions and lines after clearing, but keep them hidden initially
        if self.baseline_region: self.plot_widget.addItem(self.baseline_region)
        if self.response_region: self.plot_widget.addItem(self.response_region)
        if self.baseline_line: self.plot_widget.addItem(self.baseline_line)
        if self.response_line: self.plot_widget.addItem(self.response_line)
        self.baseline_region.setVisible(False)
        self.response_region.setVisible(False)
        self.baseline_line.setVisible(False)
        self.response_line.setVisible(False)


        # selected_channel_name = self.signal_channel_combobox.currentText() # OLD: Used display text
        selected_channel_key = self.signal_channel_combobox.currentData() # NEW: Use stored key
        selected_data_source_key = self.data_source_combobox.currentData()

        # if not selected_channel_name or not selected_data_source_key: # OLD
        if not selected_channel_key or not selected_data_source_key: # NEW
            log.warning("Plotting skipped: No channel key or data source selected.")
            return

        # log.debug(f"Plotting Rin/G trace for Ch: {selected_channel_name}, Source: {selected_data_source_key}") # OLD
        log.debug(f"Plotting Rin/G trace for Ch Key: {selected_channel_key}, Source: {selected_data_source_key}") # NEW

        # Get data using the helper method
        # plot_data = self._get_data_for_plotting(selected_channel_name, selected_data_source_key) # OLD
        plot_data = self._get_data_for_plotting(selected_channel_key, selected_data_source_key) # NEW
        if plot_data is None:
            # log.error(f"Failed to retrieve data for plotting {selected_channel_name}, {selected_data_source_key}") # OLD
            log.error(f"Failed to retrieve data for plotting key {selected_channel_key}, {selected_data_source_key}") # NEW
            return

        # <<< FIX: Assign retrieved data to local variables >>>
        time_vec = plot_data['time_vector']
        data_vec = plot_data['data_vector']
        ch_label = plot_data['channel_label']
        y_label = plot_data['y_axis_label']
        pen = plot_data['pen']
        sampling_rate = plot_data['sampling_rate']

        # Store for analysis
        self._current_plot_data = {
            "time_vec": time_vec,
            "data_vec": data_vec,
            "units": plot_data.get('units', 'unknown'), # Get units if available
            "sampling_rate": sampling_rate
        }

        # Update plot labels
        plot_item = self.plot_widget.getPlotItem()
        if plot_item:
            plot_item.setLabel('left', y_label)
            plot_item.setLabel('bottom', 'Time (s)')
            # Use the channel name in the title?
            plot_item.setTitle(f"{ch_label} ({self.data_source_combobox.currentText()})")
        
        # Set region bounds based on the time vector
        min_time, max_time = time_vec.min(), time_vec.max()
        if self.baseline_region: self.baseline_region.setBounds([min_time, max_time])
        if self.response_region: self.response_region.setBounds([min_time, max_time])
        
        # Set default regions
        time_range = max_time - min_time
        if self.baseline_region:
            baseline_start = min_time
            baseline_end = min_time + 0.2 * time_range
            self.baseline_region.setRegion([baseline_start, baseline_end])
            
        if self.response_region:
            response_start = baseline_end
            response_end = response_start + 0.2 * time_range
            self.response_region.setRegion([response_start, response_end])

        # Plot the main data trace - use customized average pen
        try:
            from Synaptipy.shared.plot_customization import get_average_pen
            pen = get_average_pen()
            log.debug(f"[RIN-DEBUG] Using customized average pen: {pen}")
        except ImportError:
            pen = pg.mkPen(color=(0, 0, 0), width=1)  # Fallback to original black pen
            log.debug(f"[RIN-DEBUG] Using fallback pen: {pen}")
        
        self.plot_item = self.plot_widget.plot(time_vec, data_vec, pen=pen)
        # CRITICAL: Force pen application (Windows PyQtGraph bug fix)
        if self.plot_item:
            self.plot_item.setPen(pen)
            log.info(f"[RIN-DEBUG] Data plot pen applied: {pen}")
        
        # Set data ranges for zoom synchronization
        x_range = (time_vec.min(), time_vec.max())
        y_range = (data_vec.min(), data_vec.max())
        self.set_data_ranges(x_range, y_range)
        
        log.debug(f"Successfully plotted {ch_label} trace for Rin/G analysis.")

        # --- Update UI based on new plot ---
        self._update_mode_dependent_ui() # Ensure regions/manual controls are visible/hidden correctly
        
        # Set default values for manual time windows
        self._set_default_time_windows()
        
        # Update button states
        self._update_run_button_state()

        # Auto-range view AFTER setting data and potentially adding regions
        if self.plot_widget:
            self.plot_widget.autoRange() # Adjust view
        # Force repaint of the plot widget
        self.plot_widget.update()

    # --- ADDED: Method to initialize spinbox values from time vector ---
    def _set_default_time_windows(self):
        """Set default time windows based on the current plot data."""
        if not self._current_plot_data or "time_vec" not in self._current_plot_data:
            return
            
        # Get the time vector
        time_vec = self._current_plot_data["time_vec"]
        if time_vec is None or len(time_vec) == 0:
            return
            
        # Calculate reasonable default time windows
        time_min = time_vec.min()
        time_max = time_vec.max()
        time_range = time_max - time_min
        
        # Set baseline to first 20% of the trace
        baseline_start = time_min
        baseline_end = time_min + 0.2 * time_range
        
        # Set response to next 20% after baseline
        response_start = baseline_end
        response_end = response_start + 0.2 * time_range
        
        # Update spinboxes with these values
        if self.manual_baseline_start_spinbox:
            self.manual_baseline_start_spinbox.setValue(baseline_start)
        if self.manual_baseline_end_spinbox:
            self.manual_baseline_end_spinbox.setValue(baseline_end)
        if self.manual_response_start_spinbox:
            self.manual_response_start_spinbox.setValue(response_start)
        if self.manual_response_end_spinbox:
            self.manual_response_end_spinbox.setValue(response_end)
            
        log.debug(f"Set default time windows: baseline=[{baseline_start:.3f}, {baseline_end:.3f}], response=[{response_start:.3f}, {response_end:.3f}]")
        
        # Update the run button state
        self._update_run_button_state()

    def _update_run_button_state(self):
        """Updates the enabled state of the Run button based on input validity."""
        if not self.run_button or not self.mode_combobox:
            return
            
        # Only enable Run button in Manual mode with valid inputs
        is_manual = (self.mode_combobox.currentText() == self._MODE_MANUAL)
        has_valid_inputs = False
        
        # Check if we have valid data to operate on
        if is_manual and self._current_plot_data and "time_vec" in self._current_plot_data and "data_vec" in self._current_plot_data:
            units = self._current_plot_data.get("units", "unknown")
            is_voltage = units and 'mv' in units.lower()
            is_current = units and ('pa' in units.lower() or 'na' in units.lower())
            
            # Check delta values
            delta_i_valid = False
            delta_v_valid = False
            
            if is_voltage and self.manual_delta_i_spinbox:
                delta_i_pa = self.manual_delta_i_spinbox.value()
                delta_i_valid = not np.isclose(delta_i_pa, 0.0)
                log.debug(f"Delta I validation: {delta_i_pa} pA, valid={delta_i_valid}")
                
            if is_current and self.manual_delta_v_spinbox:
                delta_v_mv = self.manual_delta_v_spinbox.value()
                delta_v_valid = not np.isclose(delta_v_mv, 0.0)
                log.debug(f"Delta V validation: {delta_v_mv} mV, valid={delta_v_valid}")
                
            # Check time windows
            time_windows_valid = (
                self.manual_baseline_start_spinbox and
                self.manual_baseline_end_spinbox and
                self.manual_response_start_spinbox and
                self.manual_response_end_spinbox and
                self.manual_baseline_start_spinbox.value() < self.manual_baseline_end_spinbox.value() and
                self.manual_response_start_spinbox.value() < self.manual_response_end_spinbox.value()
            )
            
            # Combine all conditions
            has_valid_inputs = time_windows_valid and ((is_voltage and delta_i_valid) or (is_current and delta_v_valid))
            
            log.debug(f"Run button validation: time_windows_valid={time_windows_valid}, is_voltage={is_voltage}, is_current={is_current}, delta_i_valid={delta_i_valid}, delta_v_valid={delta_v_valid}, has_valid_inputs={has_valid_inputs}")
        
        # Update button state
        # Ensure the button is visible and enabled when appropriate
        should_enable = is_manual and has_valid_inputs
        was_enabled = self.run_button.isEnabled()
        self.run_button.setEnabled(should_enable)
        
        # Log any state change
        if should_enable != was_enabled:
            log.debug(f"Run button enabled state changed: {was_enabled} -> {should_enable}")

    # Implement the required method to enable saving
    def _get_specific_result_data(self) -> Optional[Dict[str, Any]]:
        """
        Returns the current calculation results for saving.
        Required by the BaseAnalysisTab save mechanism.
        """
        if not self._last_rin_result:
            log.warning("_get_specific_result_data called but no results available")
            return None
            
        # Return a copy of the result data to avoid modifying the original
        # Note: This is now called by the base class save mechanism
        return self._last_rin_result.copy()

    # Override the base class save button method to customize behavior
    def _on_save_button_clicked(self):
        """Handles save button clicks by preparing data and passing to parent."""
        if not self._last_rin_result:
            log.warning("Save button clicked but no results available.")
            return
            
        # Make a copy of the result data to avoid modifying the original
        result_to_save = self._last_rin_result.copy()
        
        # Add additional context information
        result_to_save["analysis_type"] = "Input Resistance/Conductance Analysis"
        if self._selected_item_recording and hasattr(self._selected_item_recording, "source_file"):
            result_to_save["source_file"] = str(self._selected_item_recording.source_file)
        
        # Get a reference to the parent MainWindow through parent chain
        parent = self.parent()
        while parent and not hasattr(parent, "add_saved_result"):
            parent = parent.parent()
            
        if parent and hasattr(parent, "add_saved_result"):
            try:
                parent.add_saved_result(result_to_save)
                self.status_label.setText("Status: Results saved successfully")
                log.info("Input Resistance/Conductance results saved successfully")
            except Exception as e:
                log.error(f"Error saving results: {e}", exc_info=True)
                self.status_label.setText(f"Status: Error saving results: {e}")
        else:
            log.error("Could not find parent with add_saved_result method")
            self.status_label.setText("Status: Error - could not find save handler")

    @QtCore.Slot()
    def _calculate_tau(self):
        if not self._current_plot_data: return
        if not self.response_region:
            self.tau_result_label.setText("Tau: Regions not initialized")
            return
        time_vec = self._current_plot_data["time_vec"]
        data_vec = self._current_plot_data["data_vec"]
        
        # Use response window for stim start and duration
        response_window = self.response_region.getRegion()
        stim_start = response_window[0]
        fit_duration = response_window[1] - stim_start

        tau = ip.calculate_tau(data_vec, time_vec, stim_start, fit_duration)
        if tau is not None:
            self.tau_result_label.setText(f"Tau: {tau:.3f} ms")
        else:
            self.tau_result_label.setText("Tau: Failed")

    @QtCore.Slot()
    def _calculate_sag_ratio(self):
        if not self._current_plot_data: return
        if not self.baseline_region or not self.response_region:
            self.sag_result_label.setText("Sag Ratio: Regions not initialized")
            return
        time_vec = self._current_plot_data["time_vec"]
        data_vec = self._current_plot_data["data_vec"]

        baseline_window = self.baseline_region.getRegion()
        response_window = self.response_region.getRegion()
        # For sag, peak window is typically early in the response
        peak_window = (response_window[0], response_window[0] + 0.1 * (response_window[1] - response_window[0]))

        sag = ip.calculate_sag_ratio(data_vec, time_vec, baseline_window, peak_window, response_window)
        if sag is not None:
            self.sag_result_label.setText(f"Sag Ratio: {sag:.3f}")
        else:
            self.sag_result_label.setText("Sag Ratio: Failed")


# This constant is used by AnalyserTab to dynamically load the analysis tabs
ANALYSIS_TAB_CLASS = RinAnalysisTab 