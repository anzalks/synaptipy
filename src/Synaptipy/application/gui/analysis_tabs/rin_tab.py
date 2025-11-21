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
from Synaptipy.core.results import RinResult
from Synaptipy.shared.styling import (
    style_button, 
    style_label, 
    style_info_label, 
    style_result_display,
    get_baseline_pen,
    get_response_pen,
)

log = logging.getLogger('Synaptipy.application.gui.analysis_tabs.rin_tab')



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
        # NOTE: signal_channel_combobox and data_source_combobox are now inherited from BaseAnalysisTab
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
        return "Resistance/Conductance"

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

        # Signal Channel & Data Source (now handled by base class)
        self._setup_data_selection_ui(data_selection_layout)

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

        # NOTE: Channel and Data Source signals are now connected by BaseAnalysisTab._setup_data_selection_ui
        # Plotting and analysis triggering will happen via _on_data_plotted() hook

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
            # PHASE 2: Connect to template method (direct call, no debouncing)
            self.run_button.clicked.connect(self._trigger_analysis)

        # Connect other properties buttons
        if self.tau_button: self.tau_button.clicked.connect(self._calculate_tau)
        if self.sag_button: self.sag_button.clicked.connect(self._calculate_sag_ratio)

        # Connect other properties buttons
        if self.tau_button: self.tau_button.clicked.connect(self._calculate_tau)
        if self.sag_button: self.sag_button.clicked.connect(self._calculate_sag_ratio)

        # Ensure plot regions update triggers analysis in interactive mode
        if self.baseline_region: self.baseline_region.sigRegionChanged.connect(self._trigger_analysis_if_interactive)
        if self.response_region: self.response_region.sigRegionChanged.connect(self._trigger_analysis_if_interactive)

    # --- NEW Slots for internal combobox changes ---
    @QtCore.Slot()
    # --- PHASE 1 REFACTORING: Hook for Rin-Specific Plot Items ---
    def _on_data_plotted(self):
        """
        Hook called by BaseAnalysisTab after plotting main data trace.
        Adds Rin-specific plot items: baseline/response regions, visualization lines.
        """
        log.debug(f"{self.get_display_name()}: _on_data_plotted hook called")
        
        # Clear results for new data
        self._clear_results_display()
        
        # Validate that base class plotted data successfully
        if not self._current_plot_data or 'time' not in self._current_plot_data:
            log.debug("No plot data available, skipping Rin-specific items")
            # Hide regions if no data
            if self.baseline_region: self.baseline_region.setVisible(False)
            if self.response_region: self.response_region.setVisible(False)
            return
        
        time_vec = self._current_plot_data['time']
        
        # Set region bounds based on plotted data
        min_t, max_t = time_vec[0], time_vec[-1]
        duration = max_t - min_t
        
        # Update region bounds
        self.baseline_region.setBounds([min_t, max_t])
        self.response_region.setBounds([min_t, max_t])
        
        # Set default regions if they're invalid or outside bounds
        bl_start, bl_end = self.baseline_region.getRegion()
        resp_start, resp_end = self.response_region.getRegion()
        
        # Reset baseline region if invalid
        if bl_start < min_t or bl_end > max_t or bl_start >= bl_end:
            default_bl_end = min(min_t + 0.1, min_t + duration * 0.2, max_t)
            self.baseline_region.setRegion([min_t, default_bl_end])
            log.debug(f"Reset baseline region to: [{min_t:.4f}, {default_bl_end:.4f}]")
        
        # Reset response region if invalid (place it after baseline)
        if resp_start < min_t or resp_end > max_t or resp_start >= resp_end:
            default_resp_start = min(min_t + 0.2, min_t + duration * 0.4, max_t - 0.05)
            default_resp_end = min(default_resp_start + 0.1, max_t)
            self.response_region.setRegion([default_resp_start, default_resp_end])
            log.debug(f"Reset response region to: [{default_resp_start:.4f}, {default_resp_end:.4f}]")
        
        # Add regions to plot (removed by base class clear())
        self.plot_widget.addItem(self.baseline_region)
        self.plot_widget.addItem(self.response_region)
        
        # Show regions if in interactive mode
        current_mode = self.mode_combobox.currentText() if self.mode_combobox else ""
        if current_mode == self._MODE_INTERACTIVE:
            self.baseline_region.setVisible(True)
            self.response_region.setVisible(True)
            # Don't trigger analysis automatically - wait for user to set regions or enter delta values
            # Analysis will trigger when regions are moved or delta values are changed
        else:
            self.baseline_region.setVisible(False)
            self.response_region.setVisible(False)
        
        log.debug(f"{self.get_display_name()}: Rin-specific plot items added successfully")
    # --- END PHASE 1 REFACTORING ---

    # --- Analysis Triggering ---

    def _trigger_analysis_if_interactive(self):
        """Trigger analysis only if the current mode is Interactive."""
        if self.mode_combobox and self.mode_combobox.currentText() == self._MODE_INTERACTIVE:
            log.debug("Interactive region changed, triggering analysis.")
            # PHASE 2 & 3: Use debounced template method
            self._on_parameter_changed()
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
        # NOTE: Base class stores as 'time' and 'data', support both formats
        t_vec = self._current_plot_data.get("time")
        time_vec = t_vec if t_vec is not None else self._current_plot_data.get("time_vec")
        d_vec = self._current_plot_data.get("data")
        data_vec = d_vec if d_vec is not None else self._current_plot_data.get("data_vec")
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
                result = ip.calculate_rin(
                    voltage_trace=data_vec,
                    time_vector=time_vec,
                    current_amplitude=delta_i_pa,
                    baseline_window=baseline_window,
                    response_window=response_window
                )
                
                if result is not None and result.is_valid:
                    # Ensure Rin is always positive (magnitude)
                    rin_megaohms = abs(result.value) if result.value is not None else None
                    delta_v = result.voltage_deflection
                    conductance_us = result.conductance if result.conductance is not None else (1000.0 / rin_megaohms if rin_megaohms and rin_megaohms != 0 else None)
                    
                    if rin_megaohms is not None:
                        # Display results
                        g_str = f"{conductance_us:.4f}" if conductance_us is not None else "--"
                        self.rin_result_label.setText(f"Input Resistance (Rin): {rin_megaohms:.2f} MΩ | Conductance: {g_str} μS")
                        if delta_v is not None:
                            self.delta_v_label.setText(f"Voltage Change (ΔV): {delta_v:.2f} mV")
                        self.delta_i_label.setText(f"Current Change (ΔI): {delta_i_pa:.2f} pA")
                        self.status_label.setText("Status: Rin calculation successful")
                        
                        # Store result for potential saving
                        self._last_rin_result = {
                            "Rin (MΩ)": rin_megaohms,
                            "Conductance (μS)": conductance_us,
                            "ΔV (mV)": delta_v,
                            "ΔI (pA)": delta_i_pa,
                            "Baseline Window (s)": baseline_window,
                            "Response Window (s)": response_window,
                            "analysis_type": "Input Resistance",  # Add analysis type for better reporting
                            "source_file_name": self._selected_item_recording.source_file.name if self._selected_item_recording else "Unknown"
                        }
                    else:
                        self.status_label.setText(f"Status: Rin calculation failed. {result.error_message if result else 'Unknown error'}")
                        log.warning("Rin calculation returned invalid result.")
                    
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
                
                # Calculate conductance: G = |ΔI|/|ΔV|
                # If ΔV is in mV and ΔI is in pA, G will be in μS (micro-Siemens)
                # Use absolute values to ensure positive conductance
                conductance_us = abs(delta_i) / abs(delta_v_mv) if delta_v_mv != 0 else 0.0
                
                # Calculate resistance (in MΩ) - always positive
                resistance_mohm = abs(1000 / conductance_us) if conductance_us != 0 else float('inf')  # 1000 is to convert from μS to nS
                
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
            log.debug("Mode switched to Interactive with data. Analysis will trigger when user adjusts regions or enters delta values.")
            # Don't auto-trigger - wait for user interaction

    # --- Mode and Plot Dependent UI Updates --- # NEW METHOD
    def _update_mode_dependent_ui(self):
        """Updates visibility of UI elements based on mode and plot state."""
        if not self.mode_combobox: return # Not ready yet
        
        mode_text = self.mode_combobox.currentText()
        is_interactive = (mode_text == self._MODE_INTERACTIVE)
        is_manual = (mode_text == self._MODE_MANUAL)
        
        log.debug(f"Updating mode dependent UI: Mode text='{mode_text}', _MODE_MANUAL='{self._MODE_MANUAL}', is_manual={is_manual}")

        # Determine if we have data plotted (check _current_plot_data)
        has_data_plotted = self._current_plot_data is not None and 'time' in self._current_plot_data

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
        Updates the UI elements specific to Rin/G analysis when a new analysis item is selected.
        NOTE: Channel/data source population and plotting are now handled by BaseAnalysisTab.
        This method only handles mode-specific UI updates.
        """
        log.debug(f"Rin/G: Updating UI for selected item index {self._selected_item_index}")
        
        # Clear previous analysis results
        self._last_rin_result = None
        self._clear_results_display()
        
        # Determine if analysis can be performed based on data availability
        # BaseAnalysisTab has already loaded the recording and will populate comboboxes
        is_data_valid = (self._selected_item_recording is not None and 
                        bool(self._selected_item_recording.channels))

        # Enable/disable analysis parameter controls
        self.analysis_params_group.setEnabled(is_data_valid)
        self.results_group.setEnabled(is_data_valid)
        self.mode_combobox.setEnabled(is_data_valid)
        
        # Update mode-specific controls and visualization
        self._on_mode_changed()
        
        # Hide regions/lines if no data
        if not is_data_valid:
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

    # --- REMOVED: _plot_selected_trace() ---
    # This method has been replaced by BaseAnalysisTab._plot_selected_data()
    # combined with the _on_data_plotted() hook above.
    # Base class handles generic plotting; hook adds Rin-specific items (regions, lines)

    # --- ADDED: Method to initialize spinbox values from time vector ---
    def _set_default_time_windows(self):
        """Set default time windows based on the current plot data."""
        if not self._current_plot_data:
            return
            
        # Get the time vector (support both base class and old format)
        t_vec = self._current_plot_data.get("time")
        time_vec = t_vec if t_vec is not None else self._current_plot_data.get("time_vec")
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
        if is_manual and self._current_plot_data:
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
        if not self._current_plot_data:
            return
        if not self.response_region:
            self.tau_result_label.setText("Tau: Regions not initialized")
            return
        # NOTE: Support both base class and old format
        t_vec = self._current_plot_data.get("time")
        time_vec = t_vec if t_vec is not None else self._current_plot_data.get("time_vec")
        d_vec = self._current_plot_data.get("data")
        data_vec = d_vec if d_vec is not None else self._current_plot_data.get("data_vec")
        
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
        if not self._current_plot_data:
            return
        if not self.baseline_region or not self.response_region:
            self.sag_result_label.setText("Sag Ratio: Regions not initialized")
            return
        # NOTE: Support both base class and old format
        t_vec = self._current_plot_data.get("time")
        time_vec = t_vec if t_vec is not None else self._current_plot_data.get("time_vec")
        d_vec = self._current_plot_data.get("data")
        data_vec = d_vec if d_vec is not None else self._current_plot_data.get("data_vec")

        baseline_window = self.baseline_region.getRegion()
        response_window = self.response_region.getRegion()
        # For sag, peak window is typically early in the response
        peak_window = (response_window[0], response_window[0] + 0.1 * (response_window[1] - response_window[0]))

        sag = ip.calculate_sag_ratio(data_vec, time_vec, baseline_window, peak_window, response_window)
        if sag is not None:
            self.sag_result_label.setText(f"Sag Ratio: {sag:.3f}")
        else:
            self.sag_result_label.setText("Sag Ratio: Failed")

    # --- PHASE 2: Template Method Pattern Implementation ---
    def _gather_analysis_parameters(self) -> Dict[str, Any]:
        """
        Gather analysis parameters from UI widgets.
        
        Returns:
            Dictionary with mode, windows, and delta values.
        """
        params = {}
        
        # Get mode
        is_interactive = (self.mode_combobox and self.mode_combobox.currentText() == self._MODE_INTERACTIVE)
        params['mode'] = 'interactive' if is_interactive else 'manual'
        
        # Get data units to determine signal type
        if self._current_plot_data:
            units = self._current_plot_data.get("units", "unknown")
            params['units'] = units
            params['is_voltage'] = 'mv' in units.lower() if units else False
            params['is_current'] = 'pa' in units.lower() or 'na' in units.lower() if units else False
        
        # Get windows based on mode
        if is_interactive:
            if self.baseline_region and self.response_region:
                params['baseline_window'] = self.baseline_region.getRegion()
                params['response_window'] = self.response_region.getRegion()
        else:  # Manual mode
            if all([self.manual_baseline_start_spinbox, self.manual_baseline_end_spinbox,
                    self.manual_response_start_spinbox, self.manual_response_end_spinbox]):
                params['baseline_window'] = (
                    self.manual_baseline_start_spinbox.value(),
                    self.manual_baseline_end_spinbox.value()
                )
                params['response_window'] = (
                    self.manual_response_start_spinbox.value(),
                    self.manual_response_end_spinbox.value()
                )
        
        # Get delta values
        if params.get('is_voltage'):
            if self.manual_delta_i_spinbox:
                params['delta_i_pa'] = self.manual_delta_i_spinbox.value()
        elif params.get('is_current'):
            if self.manual_delta_v_spinbox:
                params['delta_v_mv'] = self.manual_delta_v_spinbox.value()

        log.debug(f"Gathered Rin parameters: {params}")
        return params
    
    def _execute_core_analysis(self, params: Dict[str, Any], data: Dict[str, Any]) -> Optional[RinResult]:
        """
        Execute Rin/conductance analysis.
        
        Args:
            params: Analysis parameters from _gather_analysis_parameters
            data: Current plot data
        
        Returns:
            RinResult object or None on failure.
        """
        # Validate data
        if not data:
            log.warning("_execute_core_analysis: No data available")
            return None
        
        # Get data vectors (support both formats)
        time_vec = data.get("time") if data.get("time") is not None else data.get("time_vec")
        data_vec = data.get("data") if data.get("data") is not None else data.get("data_vec")   
        
        if time_vec is None or data_vec is None:
            log.warning("_execute_core_analysis: Missing time or data vectors")
            return None
        
        # Get parameters
        baseline_window = params.get('baseline_window')
        response_window = params.get('response_window')
        is_voltage = params.get('is_voltage', False)
        is_current = params.get('is_current', False)
        
        # Validate windows
        if not baseline_window or not response_window:
            log.warning("_execute_core_analysis: Missing baseline/response windows")
            return None
        
        try:
            if is_voltage:
                # Calculate Rin from voltage trace
                delta_i_pa = params.get('delta_i_pa')
                
                if not delta_i_pa or np.isclose(delta_i_pa, 0.0):
                    log.warning("_execute_core_analysis: Missing or zero delta_i_pa")
                    return RinResult(value=None, unit="MOhm", is_valid=False, error_message="Missing or zero delta I")
                
                result = ip.calculate_rin(
                    voltage_trace=data_vec,
                    time_vector=time_vec,
                    current_amplitude=delta_i_pa,
                    baseline_window=baseline_window,
                    response_window=response_window
                )
                # Add metadata about windows used
                result.metadata['baseline_window'] = baseline_window
                result.metadata['response_window'] = response_window
                result.metadata['analysis_type'] = 'Input Resistance'
                return result
            
            elif is_current:
                # Calculate conductance from current trace
                delta_v_mv = params.get('delta_v_mv')
                
                if not delta_v_mv or np.isclose(delta_v_mv, 0.0):
                    log.warning("_execute_core_analysis: Missing or zero delta_v_mv")
                    return RinResult(value=None, unit="MOhm", is_valid=False, error_message="Missing or zero delta V")
                
                result = ip.calculate_conductance(
                    current_trace=data_vec,
                    time_vector=time_vec,
                    voltage_step=delta_v_mv,
                    baseline_window=baseline_window,
                    response_window=response_window
                )
                # Add metadata about windows used
                result.metadata['baseline_window'] = baseline_window
                result.metadata['response_window'] = response_window
                result.metadata['analysis_type'] = 'Conductance'
                return result
            
            else:
                log.warning("_execute_core_analysis: Unknown signal type")
                return None
        
        except Exception as e:
            log.error(f"_execute_core_analysis: Analysis failed: {e}", exc_info=True)
            return None
    
    def _display_analysis_results(self, result: RinResult):
        """
        Display analysis results in UI labels.
        
        Args:
            result: RinResult object
        """
        if not result or not result.is_valid:
            msg = result.error_message if result else "Unknown error"
            self.status_label.setText(f"Status: Calculation failed. {msg}")
            self._last_rin_result = None
            return

        rin_megaohms = result.value
        conductance_us = result.conductance
        delta_v = result.voltage_deflection
        delta_i = result.current_injection
        
        if rin_megaohms is not None:
            # Ensure Rin is always positive (magnitude)
            rin_megaohms = abs(rin_megaohms)
            # Handle conductance if not explicitly set (fallback)
            if conductance_us is None and rin_megaohms != 0:
                conductance_us = 1000.0 / rin_megaohms
            
            g_str = f"{conductance_us:.4f}" if conductance_us is not None else "--"
            self.rin_result_label.setText(
                f"Input Resistance (Rin): {rin_megaohms:.2f} MΩ | Conductance: {g_str} μS"
            )
            
            if delta_v is not None:
                self.delta_v_label.setText(f"Voltage Change (ΔV): {delta_v:.2f} mV")
            
            if delta_i is not None:
                self.delta_i_label.setText(f"Current Change (ΔI): {delta_i:.2f} pA")
            
            analysis_type = result.metadata.get('analysis_type', 'Analysis')
            self.status_label.setText(f"Status: {analysis_type} calculation successful")
            
            # Store result for saving (convert dataclass to dict for now, or keep object)
            # For compatibility with existing save logic, we'll create a dict
            self._last_rin_result = {
                "Rin (MΩ)": rin_megaohms,
                "Conductance (μS)": conductance_us,
                "ΔV (mV)": delta_v,
                "ΔI (pA)": delta_i,
                "Baseline Window (s)": result.metadata.get('baseline_window'),
                "Response Window (s)": result.metadata.get('response_window'),
                "analysis_type": analysis_type,
                "source_file_name": self._selected_item_recording.source_file.name if self._selected_item_recording else "Unknown"
            }
            
            log.info(f"{analysis_type} result: Rin={rin_megaohms:.2f} MΩ")
        else:
            self.status_label.setText("Status: Calculation failed (No value).")
            self._last_rin_result = None
    
    def _plot_analysis_visualizations(self, result: RinResult):
        """
        Update plot visualizations with baseline and response lines.
        
        Args:
            result: RinResult object
        """
        if not result or not result.is_valid:
            return

        # Get data to calculate mean levels (or use values from result if available)
        # The result object has baseline_voltage and steady_state_voltage, but only for Rin calc
        # For conductance, we might need to recalculate or store them in result
        
        # Let's use the windows from metadata to update lines on the plot
        baseline_window = result.metadata.get('baseline_window')
        response_window = result.metadata.get('response_window')
        
        if not baseline_window or not response_window:
            return

        # We can use the values from the result if they exist, otherwise recalculate from data
        # RinResult has baseline_voltage and steady_state_voltage
        
        val_baseline = result.baseline_voltage
        val_response = result.steady_state_voltage
        
        # If values are missing (e.g. conductance calc might not set them yet, though we should), 
        # we can recalculate from plot data as fallback
        if val_baseline is None or val_response is None:
             if self._current_plot_data:
                t_vec = self._current_plot_data.get("time")
                time_vec = t_vec if t_vec is not None else self._current_plot_data.get("time_vec")
                data_vec = self._current_plot_data.get("data") or self._current_plot_data.get("data_vec")
                
                if time_vec is not None and data_vec is not None:
                    bl_indices = np.where((time_vec >= baseline_window[0]) & (time_vec <= baseline_window[1]))[0]
                    resp_indices = np.where((time_vec >= response_window[0]) & (time_vec <= response_window[1]))[0]
                    
                    if len(bl_indices) > 0: val_baseline = np.mean(data_vec[bl_indices])
                    if len(resp_indices) > 0: val_response = np.mean(data_vec[resp_indices])

        # Update lines
        if val_baseline is not None and self.baseline_line:
            self.baseline_line.setValue(val_baseline)
            self.baseline_line.setVisible(True)
        
        if val_response is not None and self.response_line:
            self.response_line.setValue(val_response)
            self.response_line.setVisible(True)
            
        log.debug(f"Updated visualization lines: baseline={val_baseline}, response={val_response}")
    # --- END PHASE 2 ---

# This constant is used by AnalyserTab to dynamically load the analysis tabs
ANALYSIS_TAB_CLASS = RinAnalysisTab 