# -*- coding: utf-8 -*-
"""
Main Window for the Synaptipy GUI application.
Uses PySide6 for the GUI framework and pyqtgraph for plotting.
Features multi-panel plots per channel, channel selection,
and different trial plotting modes (overlay+avg, single trial cycling) via ComboBox.
Includes a single UI button for opening files (scans folder for same extension).
Uses NeoAdapter to dynamically generate file filters.
Plot view resets strategically when channel visibility or plot options change.

## MOD: Added X/Y zoom sliders with Y-axis lock functionality.
## MOD: Inverted zoom slider behavior (min=out, max=in).
## MOD: Added X/Y scrollbars for panning.
## MOD: Rearranged Right Panel: Y Scrollbars are now immediately right of plots, Y Zoom sliders are further right.
## MOD: Ensured individual Y controls stretch vertically.
## MOD: Ensured global Y controls AND group boxes stretch vertically.
## MOD: Added feature to select multiple trials during cycle mode and plot their average as an overlay.
## MOD: Added Manual X/Y Limit controls.
"""

# --- Standard Library Imports ---
import logging
import sys
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple, Set
import uuid
from datetime import datetime, timezone
from functools import partial # Needed for connecting individual sliders/scrollbars

# --- Third-Party Imports ---
import numpy as np
import pyqtgraph as pg
from PySide6 import QtCore, QtGui, QtWidgets
try:
    import tzlocal # Optional, for local timezone handling
except ImportError:
    tzlocal = None

# --- Synaptipy Imports ---
# Try importing the real classes. If it fails, we'll use dummies defined below.
try:
    # Attempt to import actual Synaptipy components
    from Synaptipy.core.data_model import Recording, Channel
    from Synaptipy.infrastructure.file_readers import NeoAdapter
    from Synaptipy.infrastructure.exporters import NWBExporter
    from Synaptipy.shared import constants as VisConstants # Use alias
    from Synaptipy.shared.error_handling import (
        FileReadError, UnsupportedFormatError, ExportError, SynaptipyError)
    SYNAPTIPY_AVAILABLE = True
    log = logging.getLogger(__name__) # Get logger after potential Synaptipy setup
except ImportError:
    # Synaptipy not found, set up dummy environment
    print("Warning: Synaptipy modules not found. Using dummy implementations.")
    logging.basicConfig(level=logging.DEBUG) # Basic config if Synaptipy didn't set it up
    log = logging.getLogger(__name__)
    log.warning("Synaptipy modules not found. Using dummy implementations.")

    SYNAPTIPY_AVAILABLE = False
    # Define placeholders so the rest of the script doesn't immediately crash
    NeoAdapter, NWBExporter, Recording, Channel = None, None, None, None
    VisConstants, SynaptipyError, FileReadError = None, None, None
    UnsupportedFormatError, ExportError = None, None

# --- Configure Logging (Fallback if Synaptipy didn't configure it) ---
if not logging.getLogger().hasHandlers():
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    logging.basicConfig(level=logging.DEBUG, format=log_format)
    log.info("Basic logging configured.")


# --- PyQtGraph Configuration ---
pg.setConfigOption('imageAxisOrder', 'row-major')
pg.setConfigOption('background', 'w')
pg.setConfigOption('foreground', 'k')


# --- Dummy Classes (Defined *before* MainWindow if Synaptipy not available) ---
if not SYNAPTIPY_AVAILABLE:
    class DummyChannel:
        def __init__(self, id, name, units='mV', num_trials=5, duration=1.0, rate=10000.0):
            self.id = id; self.name = name; self.units = units; self.num_trials = num_trials
            self._duration = duration; self._rate = rate; self._num_samples = int(duration * rate)
            self.tvecs = [np.linspace(0, duration, self._num_samples, endpoint=False) for _ in range(num_trials)]
            self.data = []
            for i in range(num_trials):
                noise = np.random.randn(self._num_samples) * 0.1 * (i + 1)
                sine_wave = np.sin(self.tvecs[i] * (i + 1) * 2 * np.pi / duration) * 0.5 * (i + 1)
                baseline_shift = i * 0.2
                self.data.append(noise + sine_wave + baseline_shift)
        def get_data(self, trial_idx): return self.data[trial_idx] if 0 <= trial_idx < self.num_trials else None
        def get_relative_time_vector(self, trial_idx): return self.tvecs[trial_idx] if 0 <= trial_idx < self.num_trials else None
        def get_averaged_data(self):
            if self.num_trials > 0 and self.data:
                try:
                    min_len = min(len(d) for d in self.data); data_to_avg = [d[:min_len] for d in self.data]
                    return np.mean(np.array(data_to_avg), axis=0)
                except Exception as e: log.error(f"Error averaging dummy data for channel {self.id}: {e}"); return None
            else: return None
        def get_relative_averaged_time_vector(self):
            if self.num_trials > 0 and self.tvecs:
                 # Ensure consistent length based on shortest data trace if possible
                 min_len = min(len(d) for d in self.data) if self.data else self._num_samples
                 # Use the first time vector, truncated to the minimum length
                 return self.tvecs[0][:min_len]
            else: return None

    class DummyRecording:
        def __init__(self, filepath, num_channels=3):
            self.source_file = Path(filepath); self.sampling_rate = 10000.0; self.duration = 2.0
            self.num_channels = num_channels; self.max_trials = 10
            ch_ids = [f'Ch{i+1:02d}' for i in range(num_channels)]
            self.channels = { ch_ids[i]: DummyChannel(id=ch_ids[i], name=f'Channel {i+1}', units='pA' if i % 2 == 0 else 'mV', num_trials=self.max_trials, duration=self.duration, rate=self.sampling_rate) for i in range(num_channels)}
            # Ensure dummy time is timezone-aware (UTC for simplicity)
            self.session_start_time_dt = datetime.now(timezone.utc)

    class DummyNeoAdapter:
        def get_supported_file_filter(self): return "Dummy Files (*.dummy);;All Files (*)"
        def read_recording(self, filepath):
            log.info(f"DummyNeoAdapter: Simulating read for {filepath}")
            if not Path(filepath).exists():
                try: Path(filepath).touch()
                except Exception as e: log.warning(f"Could not create dummy file {filepath}: {e}")
            # Simple logic to vary channel count based on filename
            if '5ch' in filepath.name.lower(): num_chan = 5
            elif '1ch' in filepath.name.lower(): num_chan = 1
            else: num_chan = 3
            log.debug(f"DummyNeoAdapter: Creating recording with {num_chan} channels.")
            return DummyRecording(filepath, num_channels=num_chan)

    class DummyNWBExporter:
        def export(self, recording, output_path, metadata):
            log.info(f"DummyNWBExporter: Simulating export of '{recording.source_file.name}' to {output_path} with metadata {metadata}")
            # Simulate success by touching the file
            try:
                output_path.touch()
                log.info(f"DummyNWBExporter: Touched output file {output_path}")
            except Exception as e:
                log.error(f"DummyNWBExporter: Failed to touch output file {output_path}: {e}")
                raise ExportError(f"Dummy export failed: {e}") # Simulate an export error

    class DummyVisConstants:
        TRIAL_COLOR = '#888888'; TRIAL_ALPHA = 70; AVERAGE_COLOR = '#EE4B2B'
        DEFAULT_PLOT_PEN_WIDTH = 1; DOWNSAMPLING_THRESHOLD = 5000

    def DummyErrors():
        class SynaptipyError(Exception): pass
        class FileReadError(SynaptipyError): pass
        class UnsupportedFormatError(SynaptipyError): pass
        class ExportError(SynaptipyError): pass
        return SynaptipyError, FileReadError, UnsupportedFormatError, ExportError

    # Assign dummy classes to the names expected by MainWindow
    Recording, Channel = DummyRecording, DummyChannel
    NeoAdapter, NWBExporter = DummyNeoAdapter, DummyNWBExporter
    VisConstants = DummyVisConstants() # Instantiate the dummy class
    SynaptipyError, FileReadError, UnsupportedFormatError, ExportError = DummyErrors()
# --- End Dummy Class Definitions ---


# --- NWB Metadata Dialog ---
class NwbMetadataDialog(QtWidgets.QDialog):
    def __init__(self, default_identifier: str, default_start_time: datetime, parent: Optional[QtWidgets.QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("NWB Session Metadata")
        self.setModal(True)
        self.layout = QtWidgets.QFormLayout(self)

        self.session_description = QtWidgets.QLineEdit("Session description...")
        self.identifier = QtWidgets.QLineEdit(default_identifier)
        # Ensure the default time passed is timezone-aware before setting
        if default_start_time.tzinfo is None:
            log.warning("NwbMetadataDialog received naive datetime, assuming UTC.")
            default_start_time = default_start_time.replace(tzinfo=timezone.utc)
        self.session_start_time_edit = QtWidgets.QDateTimeEdit(default_start_time)
        self.session_start_time_edit.setCalendarPopup(True)
        self.session_start_time_edit.setDisplayFormat("yyyy-MM-dd HH:mm:ss")

        self.experimenter = QtWidgets.QLineEdit("")
        self.lab = QtWidgets.QLineEdit("")
        self.institution = QtWidgets.QLineEdit("")
        self.session_id = QtWidgets.QLineEdit("") # Optional NWB session_id

        self.layout.addRow("Description*:", self.session_description)
        self.layout.addRow("Identifier*:", self.identifier)
        self.layout.addRow("Start Time*:", self.session_start_time_edit)
        self.layout.addRow("Experimenter:", self.experimenter)
        self.layout.addRow("Lab:", self.lab)
        self.layout.addRow("Institution:", self.institution)
        self.layout.addRow("Session ID:", self.session_id)
        self.layout.addRow(QtWidgets.QLabel("* Required fields"))

        self.button_box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.StandardButton.Ok | QtWidgets.QDialogButtonBox.StandardButton.Cancel)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        self.layout.addRow(self.button_box)

    def get_metadata(self) -> Optional[Dict[str, Any]]:
        """Validates input and returns metadata dictionary or None if invalid."""
        desc = self.session_description.text().strip()
        ident = self.identifier.text().strip()
        start_time_dt = self.session_start_time_edit.dateTime().toPython() # Gets datetime

        if not desc or not ident:
            QtWidgets.QMessageBox.warning(self, "Input Error", "Session Description and Identifier are required fields.")
            return None

        # Ensure start time from QDateTimeEdit is timezone-aware (it should be based on input)
        # If it somehow becomes naive, default to UTC.
        if start_time_dt.tzinfo is None:
             log.warning("QDateTimeEdit returned naive datetime, forcing UTC.")
             try:
                 # Attempt to use tzlocal if available and reasonable
                 local_tz = tzlocal.get_localzone() if tzlocal else timezone.utc
                 start_time_dt = self.session_start_time_edit.dateTime().toTimeZone(local_tz.key).toPython() # Try converting using zone key
             except Exception:
                 start_time_dt = start_time_dt.replace(tzinfo=timezone.utc) # Fallback

        metadata = {
            "session_description": desc,
            "identifier": ident,
            "session_start_time": start_time_dt,
            "experimenter": self.experimenter.text().strip() or None,
            "lab": self.lab.text().strip() or None,
            "institution": self.institution.text().strip() or None,
            "session_id": self.session_id.text().strip() or None,
        }
        return metadata
# --- NwbMetadataDialog End ---


# --- MainWindow Class ---
class MainWindow(QtWidgets.QMainWindow):
    """Main application window with multi-panel plotting and trial modes."""
    class PlotMode: OVERLAY_AVG = 0; CYCLE_SINGLE = 1
    SLIDER_RANGE_MIN = 1; SLIDER_RANGE_MAX = 100
    SLIDER_DEFAULT_VALUE = SLIDER_RANGE_MIN # Start zoomed out
    MIN_ZOOM_FACTOR = 0.01; SCROLLBAR_MAX_RANGE = 10000
    SELECTED_AVG_PEN = pg.mkPen('#00FF00', width=(VisConstants.DEFAULT_PLOT_PEN_WIDTH + 1) if VisConstants else 2) if VisConstants else pg.mkPen('g', width=2)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Synaptipy Viewer")
        self.setGeometry(50, 50, 1700, 950) # x, y, width, height

        # --- Instantiate Adapters/Exporters ---
        try:
             self.neo_adapter = NeoAdapter()
             self.nwb_exporter = NWBExporter()
        except Exception as e:
             log.critical(f"Failed to instantiate NeoAdapter or NWBExporter: {e}", exc_info=True)
             # Show critical error message *before* trying to use QtWidgets which might fail if Qt init failed
             print(f"CRITICAL ERROR: Failed to instantiate adapters: {e}")
             # Attempt to show a message box, but be prepared for it to fail
             try:
                 QtWidgets.QMessageBox.critical(None, "Initialization Error", f"Failed to initialize core components:\n{e}\nPlease check installation and dependencies.")
             except Exception as mb_error:
                 print(f"Failed to show message box: {mb_error}")
             sys.exit(1) # Exit immediately

        # --- Initialize State Variables ---
        self.current_recording: Optional[Recording] = None
        self.file_list: List[Path] = []
        self.current_file_index: int = -1

        self.channel_checkboxes: Dict[str, QtWidgets.QCheckBox] = {}
        self.channel_plots: Dict[str, pg.PlotItem] = {}
        self.channel_plot_data_items: Dict[str, List[pg.PlotDataItem]] = {} # Stores non-average data items

        self.current_plot_mode: int = self.PlotMode.OVERLAY_AVG
        self.current_trial_index: int = 0
        self.max_trials_current_recording: int = 0

        # Zoom/Pan State
        self.y_axes_locked: bool = True
        self.base_x_range: Optional[Tuple[float, float]] = None # Full data range for X
        self.base_y_ranges: Dict[str, Optional[Tuple[float, float]]] = {} # Full data range for Y per channel

        # Individual Controls (dynamically created)
        self.individual_y_sliders: Dict[str, QtWidgets.QSlider] = {}
        self.individual_y_slider_labels: Dict[str, QtWidgets.QLabel] = {}
        self.individual_y_scrollbars: Dict[str, QtWidgets.QScrollBar] = {}

        # Control Flags
        self._updating_scrollbars: bool = False # Prevent feedback loops: scrollbar update -> view update -> scrollbar update
        self._updating_viewranges: bool = False # Prevent feedback loops: view update -> scrollbar/slider update -> view update
        self._updating_limit_fields: bool = False # Prevent feedback loop: view update -> field update -> view update? (less likely)

        # Multi-Trial Selection State
        self.selected_trial_indices: Set[int] = set() # Stores 0-based indices
        self.selected_average_plot_items: Dict[str, pg.PlotDataItem] = {} # Stores the plotted average item per channel

        # Manual Limits State
        self.manual_limits_enabled: bool = False
        self.manual_x_limits: Optional[Tuple[float, float]] = None
        self.manual_y_limits: Optional[Tuple[float, float]] = None

        # References to Manual Limit Widgets (set in _setup_ui)
        self.manual_limit_x_min_edit: Optional[QtWidgets.QLineEdit] = None
        self.manual_limit_x_max_edit: Optional[QtWidgets.QLineEdit] = None
        self.manual_limit_y_min_edit: Optional[QtWidgets.QLineEdit] = None
        self.manual_limit_y_max_edit: Optional[QtWidgets.QLineEdit] = None
        self.set_manual_limits_button: Optional[QtWidgets.QPushButton] = None
        self.enable_manual_limits_checkbox: Optional[QtWidgets.QCheckBox] = None

        # --- Setup UI and Signals ---
        self._setup_ui()
        self._connect_signals()
        self._update_ui_state() # Initial UI state based on no data
        self._update_limit_fields() # Initial state for limit fields

    # =========================================================================
    # UI Setup (_setup_ui)
    # =========================================================================
    def _setup_ui(self):
        """Create and arrange widgets ONCE during initialization."""
        log.debug("Setting up UI...")
        # --- Menu Bar ---
        menu_bar = self.menuBar()
        file_menu = menu_bar.addMenu("&File")
        self.open_file_action = file_menu.addAction("&Open...")
        self.export_nwb_action = file_menu.addAction("Export to &NWB...")
        self.quit_action = file_menu.addAction("&Quit")
        file_menu.insertSeparator(self.export_nwb_action)
        file_menu.insertSeparator(self.quit_action)

        # --- Main Layout ---
        main_widget = QtWidgets.QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QtWidgets.QHBoxLayout(main_widget) # Horizontal: Left | Center | Right

        # --- Left Panel (Controls) ---
        left_panel_widget = QtWidgets.QWidget()
        left_panel_layout = QtWidgets.QVBoxLayout(left_panel_widget)
        left_panel_layout.setSpacing(10)
        left_panel_widget.setFixedWidth(250) # Give controls some space

        # File Operations Group
        file_op_group = QtWidgets.QGroupBox("Load Data")
        file_op_layout = QtWidgets.QHBoxLayout(file_op_group)
        self.open_button_ui = QtWidgets.QPushButton("Open File...") # More descriptive
        file_op_layout.addWidget(self.open_button_ui)
        left_panel_layout.addWidget(file_op_group)

        # Display Options Group
        display_group = QtWidgets.QGroupBox("Display Options")
        display_layout = QtWidgets.QVBoxLayout(display_group)
        # Plot Mode
        plot_mode_layout = QtWidgets.QHBoxLayout()
        plot_mode_layout.addWidget(QtWidgets.QLabel("Plot Mode:"))
        self.plot_mode_combobox = QtWidgets.QComboBox()
        self.plot_mode_combobox.addItems(["Overlay All + Avg", "Cycle Single Trial"])
        self.plot_mode_combobox.setCurrentIndex(self.current_plot_mode)
        plot_mode_layout.addWidget(self.plot_mode_combobox)
        display_layout.addLayout(plot_mode_layout)
        # Downsampling
        self.downsample_checkbox = QtWidgets.QCheckBox("Auto Downsample Plot")
        self.downsample_checkbox.setChecked(True)
        self.downsample_checkbox.setToolTip("Enable automatic downsampling for performance on large datasets.")
        display_layout.addWidget(self.downsample_checkbox)
        # Separator
        sep1 = QtWidgets.QFrame()
        sep1.setFrameShape(QtWidgets.QFrame.Shape.HLine)
        sep1.setFrameShadow(QtWidgets.QFrame.Shadow.Sunken)
        display_layout.addWidget(sep1)
        # Multi-Trial Averaging Section
        display_layout.addWidget(QtWidgets.QLabel("Manual Trial Averaging (Cycle Mode):"))
        self.select_trial_button = QtWidgets.QPushButton("Add Current Trial to Avg Set")
        self.select_trial_button.setToolTip("Add/Remove the currently viewed trial (in Cycle Mode) to the set for averaging.")
        display_layout.addWidget(self.select_trial_button)
        self.selected_trials_display = QtWidgets.QLabel("Selected: None")
        self.selected_trials_display.setWordWrap(True) # Allow wrapping if many trials selected
        display_layout.addWidget(self.selected_trials_display)
        clear_avg_layout = QtWidgets.QHBoxLayout()
        self.clear_selection_button = QtWidgets.QPushButton("Clear Avg Set")
        self.clear_selection_button.setToolTip("Clear the set of selected trials.")
        clear_avg_layout.addWidget(self.clear_selection_button)
        self.show_selected_average_button = QtWidgets.QPushButton("Plot Selected Avg")
        self.show_selected_average_button.setToolTip("Toggle the display of the average of selected trials as an overlay.")
        self.show_selected_average_button.setCheckable(True)
        clear_avg_layout.addWidget(self.show_selected_average_button)
        display_layout.addLayout(clear_avg_layout)
        left_panel_layout.addWidget(display_group)

        # Manual Plot Limits Group
        manual_limits_group = QtWidgets.QGroupBox("Manual Plot Limits")
        manual_limits_layout = QtWidgets.QVBoxLayout(manual_limits_group)
        manual_limits_layout.setSpacing(5)
        self.enable_manual_limits_checkbox = QtWidgets.QCheckBox("Enable Manual Limits")
        self.enable_manual_limits_checkbox.setToolTip("Lock plot axes to the manually set limits below. Disables zoom/pan.")
        manual_limits_layout.addWidget(self.enable_manual_limits_checkbox)
        limits_grid_layout = QtWidgets.QGridLayout()
        limits_grid_layout.setSpacing(3)
        # Create QLineEdit widgets and store references
        self.manual_limit_x_min_edit = QtWidgets.QLineEdit()
        self.manual_limit_x_max_edit = QtWidgets.QLineEdit()
        self.manual_limit_y_min_edit = QtWidgets.QLineEdit()
        self.manual_limit_y_max_edit = QtWidgets.QLineEdit()
        # Set placeholders and tooltips
        self.manual_limit_x_min_edit.setPlaceholderText("Auto")
        self.manual_limit_x_max_edit.setPlaceholderText("Auto")
        self.manual_limit_y_min_edit.setPlaceholderText("Auto")
        self.manual_limit_y_max_edit.setPlaceholderText("Auto")
        self.manual_limit_x_min_edit.setToolTip("Current X Min / Manual X Min")
        self.manual_limit_x_max_edit.setToolTip("Current X Max / Manual X Max")
        self.manual_limit_y_min_edit.setToolTip("Current Y Min (Reference Plot) / Manual Y Min")
        self.manual_limit_y_max_edit.setToolTip("Current Y Max (Reference Plot) / Manual Y Max")
        # Add widgets to grid layout
        limits_grid_layout.addWidget(QtWidgets.QLabel("X Min:"), 0, 0)
        limits_grid_layout.addWidget(self.manual_limit_x_min_edit, 0, 1)
        limits_grid_layout.addWidget(QtWidgets.QLabel("X Max:"), 1, 0)
        limits_grid_layout.addWidget(self.manual_limit_x_max_edit, 1, 1)
        limits_grid_layout.addWidget(QtWidgets.QLabel("Y Min:"), 2, 0)
        limits_grid_layout.addWidget(self.manual_limit_y_min_edit, 2, 1)
        limits_grid_layout.addWidget(QtWidgets.QLabel("Y Max:"), 3, 0)
        limits_grid_layout.addWidget(self.manual_limit_y_max_edit, 3, 1)
        manual_limits_layout.addLayout(limits_grid_layout)
        self.set_manual_limits_button = QtWidgets.QPushButton("Set Manual Limits from Fields")
        self.set_manual_limits_button.setToolTip("Store the values from the fields above as the manual limits.")
        manual_limits_layout.addWidget(self.set_manual_limits_button)
        left_panel_layout.addWidget(manual_limits_group)


        # Channel Selection Group
        self.channel_select_group = QtWidgets.QGroupBox("Channels")
        self.channel_scroll_area = QtWidgets.QScrollArea()
        self.channel_scroll_area.setWidgetResizable(True)
        # Widget inside scroll area to hold the checkbox layout
        self.channel_select_widget = QtWidgets.QWidget()
        self.channel_checkbox_layout = QtWidgets.QVBoxLayout(self.channel_select_widget)
        self.channel_checkbox_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop) # Checkboxes start at the top
        # Set the widget for the scroll area
        self.channel_scroll_area.setWidget(self.channel_select_widget)
        # Layout for the group box containing the scroll area
        channel_group_layout = QtWidgets.QVBoxLayout(self.channel_select_group)
        channel_group_layout.addWidget(self.channel_scroll_area)
        left_panel_layout.addWidget(self.channel_select_group)

        # File Info Group
        meta_group = QtWidgets.QGroupBox("File Information")
        meta_layout = QtWidgets.QFormLayout(meta_group)
        self.filename_label = QtWidgets.QLabel("N/A")
        self.sampling_rate_label = QtWidgets.QLabel("N/A")
        self.channels_label = QtWidgets.QLabel("N/A") # Combines channel count and trials
        self.duration_label = QtWidgets.QLabel("N/A")
        meta_layout.addRow("File:", self.filename_label)
        meta_layout.addRow("Sampling Rate:", self.sampling_rate_label)
        meta_layout.addRow("Duration:", self.duration_label)
        meta_layout.addRow("Channels / Trials:", self.channels_label)
        left_panel_layout.addWidget(meta_group)

        left_panel_layout.addStretch() # Push controls to the top
        main_layout.addWidget(left_panel_widget, stretch=0) # Left panel doesn't stretch

        # --- Center Panel (Plots + X Controls) ---
        center_panel_widget = QtWidgets.QWidget()
        center_panel_layout = QtWidgets.QVBoxLayout(center_panel_widget)

        # File Navigation
        nav_layout = QtWidgets.QHBoxLayout()
        self.prev_file_button = QtWidgets.QPushButton("<< Prev File")
        self.next_file_button = QtWidgets.QPushButton("Next File >>")
        self.folder_file_index_label = QtWidgets.QLabel("") # Shows "File X/Y: filename.ext"
        self.folder_file_index_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        nav_layout.addWidget(self.prev_file_button)
        nav_layout.addStretch()
        nav_layout.addWidget(self.folder_file_index_label)
        nav_layout.addStretch()
        nav_layout.addWidget(self.next_file_button)
        center_panel_layout.addLayout(nav_layout)

        # Plot Area
        self.graphics_layout_widget = pg.GraphicsLayoutWidget()
        center_panel_layout.addWidget(self.graphics_layout_widget, stretch=1) # Plot area stretches vertically

        # X Scrollbar (below plot area)
        self.x_scrollbar = QtWidgets.QScrollBar(QtCore.Qt.Orientation.Horizontal)
        self.x_scrollbar.setFixedHeight(20)
        self.x_scrollbar.setRange(0, self.SCROLLBAR_MAX_RANGE) # Initial dummy range
        center_panel_layout.addWidget(self.x_scrollbar)

        # Bottom Control Row (Reset, X Zoom, Trial Nav)
        plot_controls_layout = QtWidgets.QHBoxLayout()
        # View Reset Group
        view_group = QtWidgets.QGroupBox("View")
        view_layout = QtWidgets.QHBoxLayout(view_group)
        self.reset_view_button = QtWidgets.QPushButton("Reset View")
        self.reset_view_button.setToolTip("Reset zoom and pan to show all data (or apply manual limits if enabled).")
        view_layout.addWidget(self.reset_view_button)
        plot_controls_layout.addWidget(view_group)

        # X Zoom Group
        x_zoom_group = QtWidgets.QGroupBox("X Zoom (Min=Out, Max=In)")
        x_zoom_layout = QtWidgets.QHBoxLayout(x_zoom_group)
        self.x_zoom_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.x_zoom_slider.setRange(self.SLIDER_RANGE_MIN, self.SLIDER_RANGE_MAX)
        self.x_zoom_slider.setValue(self.SLIDER_DEFAULT_VALUE)
        self.x_zoom_slider.setToolTip("Adjust X-axis zoom (shared across all plots)")
        x_zoom_layout.addWidget(self.x_zoom_slider)
        plot_controls_layout.addWidget(x_zoom_group, stretch=1) # X Zoom takes available space

        # Trial Navigation Group
        trial_group = QtWidgets.QGroupBox("Trial (Cycle Mode)")
        trial_layout = QtWidgets.QHBoxLayout(trial_group)
        self.prev_trial_button = QtWidgets.QPushButton("< Prev")
        self.next_trial_button = QtWidgets.QPushButton("Next >")
        self.trial_index_label = QtWidgets.QLabel("N/A") # Shows "Trial X / Y"
        self.trial_index_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        trial_layout.addWidget(self.prev_trial_button)
        trial_layout.addWidget(self.trial_index_label)
        trial_layout.addWidget(self.next_trial_button)
        plot_controls_layout.addWidget(trial_group)

        center_panel_layout.addLayout(plot_controls_layout)
        main_layout.addWidget(center_panel_widget, stretch=1) # Center panel stretches horizontally

        # --- Right Panel (Y Controls) ---
        y_controls_panel_widget = QtWidgets.QWidget()
        y_controls_panel_layout = QtWidgets.QHBoxLayout(y_controls_panel_widget)
        y_controls_panel_widget.setFixedWidth(220) # Fixed width for Y controls
        y_controls_panel_layout.setContentsMargins(0, 0, 0, 0)
        y_controls_panel_layout.setSpacing(5)

        # Y Scroll Column (Immediately right of plots)
        y_scroll_widget = QtWidgets.QWidget()
        y_scroll_layout = QtWidgets.QVBoxLayout(y_scroll_widget)
        y_scroll_layout.setContentsMargins(0,0,0,0)
        y_scroll_layout.setSpacing(5)
        y_scroll_group = QtWidgets.QGroupBox("Y Scroll")
        y_scroll_group_layout = QtWidgets.QVBoxLayout(y_scroll_group)
        y_scroll_layout.addWidget(y_scroll_group, stretch=1) # Group stretches vertically

        # Global Y Scrollbar (visible when locked)
        self.global_y_scrollbar_widget = QtWidgets.QWidget() # Container for label + scroll
        global_y_scrollbar_layout = QtWidgets.QVBoxLayout(self.global_y_scrollbar_widget)
        global_y_scrollbar_layout.setContentsMargins(0,0,0,0); global_y_scrollbar_layout.setSpacing(2)
        global_y_scrollbar_label = QtWidgets.QLabel("Global")
        global_y_scrollbar_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.global_y_scrollbar = QtWidgets.QScrollBar(QtCore.Qt.Orientation.Vertical)
        self.global_y_scrollbar.setRange(0, self.SCROLLBAR_MAX_RANGE)
        self.global_y_scrollbar.setToolTip("Scroll Y-axis (All visible channels simultaneously)")
        global_y_scrollbar_layout.addWidget(global_y_scrollbar_label)
        global_y_scrollbar_layout.addWidget(self.global_y_scrollbar, stretch=1) # Scrollbar stretches
        y_scroll_group_layout.addWidget(self.global_y_scrollbar_widget, stretch=1) # Widget stretches

        # Individual Y Scrollbars Container (visible when unlocked)
        self.individual_y_scrollbars_container = QtWidgets.QWidget()
        self.individual_y_scrollbars_layout = QtWidgets.QVBoxLayout(self.individual_y_scrollbars_container)
        self.individual_y_scrollbars_layout.setContentsMargins(0, 5, 0, 0)
        self.individual_y_scrollbars_layout.setSpacing(10)
        self.individual_y_scrollbars_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop) # Controls added start at top
        y_scroll_group_layout.addWidget(self.individual_y_scrollbars_container, stretch=1) # Container stretches

        y_controls_panel_layout.addWidget(y_scroll_widget, stretch=1) # Y Scroll column

        # Y Zoom Column (Furthest right)
        y_zoom_widget = QtWidgets.QWidget()
        y_zoom_layout = QtWidgets.QVBoxLayout(y_zoom_widget)
        y_zoom_layout.setContentsMargins(0,0,0,0)
        y_zoom_layout.setSpacing(5)
        y_zoom_group = QtWidgets.QGroupBox("Y Zoom")
        y_zoom_group_layout = QtWidgets.QVBoxLayout(y_zoom_group)
        y_zoom_layout.addWidget(y_zoom_group, stretch=1) # Group stretches vertically

        # Y Lock Checkbox (at the top of Y Zoom)
        self.y_lock_checkbox = QtWidgets.QCheckBox("Lock Y Axes")
        self.y_lock_checkbox.setChecked(self.y_axes_locked)
        self.y_lock_checkbox.setToolTip("Lock Y-axis zoom & scroll controls to affect all visible channels together.")
        y_zoom_group_layout.addWidget(self.y_lock_checkbox)

        # Global Y Zoom Slider (visible when locked)
        self.global_y_slider_widget = QtWidgets.QWidget() # Container for label + slider
        global_y_slider_layout = QtWidgets.QVBoxLayout(self.global_y_slider_widget)
        global_y_slider_layout.setContentsMargins(0,0,0,0); global_y_slider_layout.setSpacing(2)
        global_y_slider_label = QtWidgets.QLabel("Global")
        global_y_slider_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.global_y_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Vertical)
        self.global_y_slider.setRange(self.SLIDER_RANGE_MIN, self.SLIDER_RANGE_MAX)
        self.global_y_slider.setValue(self.SLIDER_DEFAULT_VALUE)
        self.global_y_slider.setToolTip("Adjust Y-axis zoom (All visible channels simultaneously)")
        global_y_slider_layout.addWidget(global_y_slider_label)
        global_y_slider_layout.addWidget(self.global_y_slider, stretch=1) # Slider stretches
        y_zoom_group_layout.addWidget(self.global_y_slider_widget, stretch=1) # Widget stretches

        # Individual Y Zoom Sliders Container (visible when unlocked)
        self.individual_y_sliders_container = QtWidgets.QWidget()
        self.individual_y_sliders_layout = QtWidgets.QVBoxLayout(self.individual_y_sliders_container)
        self.individual_y_sliders_layout.setContentsMargins(0, 5, 0, 0)
        self.individual_y_sliders_layout.setSpacing(10)
        self.individual_y_sliders_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop) # Controls added start at top
        y_zoom_group_layout.addWidget(self.individual_y_sliders_container, stretch=1) # Container stretches

        y_controls_panel_layout.addWidget(y_zoom_widget, stretch=1) # Y Zoom column

        main_layout.addWidget(y_controls_panel_widget, stretch=0) # Right panel doesn't stretch

        # --- Status Bar ---
        self.statusBar = QtWidgets.QStatusBar()
        self.setStatusBar(self.statusBar)
        self.statusBar.showMessage("Ready. Open a file to begin.")

        # Initial state updates after UI is built
        self._update_y_controls_visibility()
        self._update_selected_trials_display()
        self._update_zoom_scroll_enable_state()
        log.debug("UI Setup complete.")

    # =========================================================================
    # Signal Connections (_connect_signals)
    # =========================================================================
    def _connect_signals(self):
        """Connect widget signals to handler slots."""
        log.debug("Connecting signals...")
        # File Menu / Basic Controls
        self.open_file_action.triggered.connect(self._open_file_or_folder)
        self.export_nwb_action.triggered.connect(self._export_to_nwb)
        self.quit_action.triggered.connect(self.close) # QMainWindow's close method

        # Left Panel Buttons/Widgets
        self.open_button_ui.clicked.connect(self._open_file_or_folder)
        self.downsample_checkbox.stateChanged.connect(self._trigger_plot_update) # Replot needed
        self.plot_mode_combobox.currentIndexChanged.connect(self._on_plot_mode_changed)

        # Center Panel Buttons/Widgets
        self.reset_view_button.clicked.connect(self._reset_view)
        self.prev_trial_button.clicked.connect(self._prev_trial)
        self.next_trial_button.clicked.connect(self._next_trial)
        self.prev_file_button.clicked.connect(self._prev_file_folder)
        self.next_file_button.clicked.connect(self._next_file_folder)

        # Zoom / Scroll Controls
        self.x_zoom_slider.valueChanged.connect(self._on_x_zoom_changed)
        self.y_lock_checkbox.stateChanged.connect(self._on_y_lock_changed)
        self.global_y_slider.valueChanged.connect(self._on_global_y_zoom_changed)
        self.x_scrollbar.valueChanged.connect(self._on_x_scrollbar_changed)
        self.global_y_scrollbar.valueChanged.connect(self._on_global_y_scrollbar_changed)
        # Individual Y controls are connected dynamically in _create_channel_ui

        # Multi-Trial Selection Buttons
        self.select_trial_button.clicked.connect(self._toggle_select_current_trial)
        self.clear_selection_button.clicked.connect(self._clear_avg_selection)
        self.show_selected_average_button.toggled.connect(self._toggle_plot_selected_average)

        # Manual Limits Connections (Check widgets exist first)
        if self.enable_manual_limits_checkbox:
            self.enable_manual_limits_checkbox.toggled.connect(self._on_manual_limits_toggled)
        else: log.warning("enable_manual_limits_checkbox not found during signal connection.")
        if self.set_manual_limits_button:
            self.set_manual_limits_button.clicked.connect(self._on_set_limits_clicked)
        else: log.warning("set_manual_limits_button not found during signal connection.")
        # Connections for ViewBox range changes triggering limit field updates are in _create_channel_ui

        log.debug("Signal connections complete.")

    # =========================================================================
    # Reset & UI Creation
    # =========================================================================
    def _reset_ui_and_state_for_new_file(self):
        """Fully resets UI elements and state related to channels and plots when a new file is loaded."""
        log.info("Resetting UI and state for new file...")
        # Clear Plot/Selection State first
        self._remove_selected_average_plots() # Remove any existing average plots
        self.selected_trial_indices.clear()
        self._update_selected_trials_display()
        # Reset avg plot button state without triggering signal
        self.show_selected_average_button.blockSignals(True)
        self.show_selected_average_button.setChecked(False)
        self.show_selected_average_button.blockSignals(False)

        # Clear Channel UI (Checkboxes, Plots, Individual Controls)
        # Disconnect signals before removing checkboxes
        for checkbox in self.channel_checkboxes.values():
            try: checkbox.stateChanged.disconnect(self._trigger_plot_update)
            except (TypeError, RuntimeError) as e: log.warning(f"Error disconnecting checkbox signal: {e}")
        # Remove checkbox widgets from layout
        while self.channel_checkbox_layout.count():
            item = self.channel_checkbox_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        self.channel_checkboxes.clear()
        self.channel_select_group.setEnabled(False) # Disable group until channels are added

        # Clear Plots from GraphicsLayoutWidget and disconnect signals
        for plot in self.channel_plots.values():
            if plot and plot.getViewBox():
                vb = plot.getViewBox()
                try: vb.sigXRangeChanged.disconnect() # Disconnect all handlers for safety
                except (TypeError, RuntimeError): pass # Ignore if no connections
                try: vb.sigYRangeChanged.disconnect()
                except (TypeError, RuntimeError): pass
        self.graphics_layout_widget.clear() # Remove all plots
        self.channel_plots.clear()
        self.channel_plot_data_items.clear() # Clear references to plotted data

        # Clear Individual Y Controls
        for slider in self.individual_y_sliders.values():
             try: slider.valueChanged.disconnect()
             except (TypeError, RuntimeError): pass
        while self.individual_y_sliders_layout.count():
             item = self.individual_y_sliders_layout.takeAt(0)
             widget = item.widget(); widget.deleteLater() if widget else None
        self.individual_y_sliders.clear()
        self.individual_y_slider_labels.clear()

        for scrollbar in self.individual_y_scrollbars.values():
            try: scrollbar.valueChanged.disconnect()
            except (TypeError, RuntimeError): pass
        while self.individual_y_scrollbars_layout.count():
            item = self.individual_y_scrollbars_layout.takeAt(0)
            widget = item.widget(); widget.deleteLater() if widget else None
        self.individual_y_scrollbars.clear()

        # Reset Data State
        self.current_recording = None
        self.max_trials_current_recording = 0
        self.current_trial_index = 0

        # Reset Zoom/Scroll State
        self.base_x_range = None
        self.base_y_ranges.clear()
        # Reset sliders to default without triggering signals
        self.x_zoom_slider.blockSignals(True); self.x_zoom_slider.setValue(self.SLIDER_DEFAULT_VALUE); self.x_zoom_slider.blockSignals(False)
        self.global_y_slider.blockSignals(True); self.global_y_slider.setValue(self.SLIDER_DEFAULT_VALUE); self.global_y_slider.blockSignals(False)
        # Reset Y lock state (keep it consistent or reset to default?) Default seems safer.
        self.y_axes_locked = True
        self.y_lock_checkbox.blockSignals(True); self.y_lock_checkbox.setChecked(self.y_axes_locked); self.y_lock_checkbox.blockSignals(False)
        # Reset scrollbars to default state (0 range, 0 value, disabled)
        self._reset_scrollbar(self.x_scrollbar)
        self._reset_scrollbar(self.global_y_scrollbar)

        # Reset Displays & Update UI component states
        self._update_y_controls_visibility() # Hide/show global/individual controls
        self._clear_metadata_display()
        self._update_trial_label()
        self._update_limit_fields() # Clear limit fields
        self._update_zoom_scroll_enable_state() # Enable/disable zoom/scroll based on state
        self._update_ui_state() # Update general button enables etc.
        log.info("UI and state reset complete.")

    def _reset_scrollbar(self, scrollbar: Optional[QtWidgets.QScrollBar]):
        """Helper to reset a scrollbar to its default inactive state."""
        if not scrollbar: return
        scrollbar.blockSignals(True)
        try:
            scrollbar.setRange(0, 0) # No scroll range
            scrollbar.setPageStep(self.SCROLLBAR_MAX_RANGE) # Full page step
            scrollbar.setValue(0) # Set value to min
            scrollbar.setEnabled(False) # Disable the scrollbar
        finally:
            scrollbar.blockSignals(False)

    def _create_channel_ui(self):
        """Creates checkboxes, PlotItems, Y-sliders, AND Y-scrollbars for loaded channels. Called ONCE per file load."""
        if not self.current_recording or not self.current_recording.channels:
            log.warning("Cannot create channel UI: No current recording or channels found.")
            self.channel_select_group.setEnabled(False)
            return

        self.channel_select_group.setEnabled(True)
        # Sort channels by ID for consistent order
        sorted_items = sorted(self.current_recording.channels.items(), key=lambda item: str(item[0]))
        log.info(f"Creating UI for {len(sorted_items)} channels.")
        last_plot_item: Optional[pg.PlotItem] = None

        for i, (chan_id, channel) in enumerate(sorted_items):
            # Defensive check: Ensure we don't accidentally recreate UI elements
            if chan_id in self.channel_checkboxes or chan_id in self.channel_plots:
                log.error(f"State Error: UI elements for channel {chan_id} already exist! Skipping recreation.")
                continue

            # 1. Channel Checkbox
            checkbox_text = f"{channel.name or f'Channel {chan_id}'}" # Use name if available
            checkbox = QtWidgets.QCheckBox(checkbox_text)
            checkbox.setChecked(True) # Default to visible
            checkbox.stateChanged.connect(self._trigger_plot_update) # Connect signal
            self.channel_checkbox_layout.addWidget(checkbox)
            self.channel_checkboxes[chan_id] = checkbox

            # 2. Plot Item
            plot_item = self.graphics_layout_widget.addPlot(row=i, col=0)
            plot_item.setLabel('left', channel.name or f'Ch {chan_id}', units=channel.units or 'units')
            plot_item.showGrid(x=True, y=True, alpha=0.3)
            self.channel_plots[chan_id] = plot_item

            # Configure ViewBox
            vb = plot_item.getViewBox()
            vb.setMouseMode(pg.ViewBox.RectMode) # Enable rect zoom
            vb._synaptipy_chan_id = chan_id # Store channel ID for later reference

            # Connect ViewBox signals
            vb.sigXRangeChanged.connect(self._handle_vb_xrange_changed)
            vb.sigYRangeChanged.connect(self._handle_vb_yrange_changed)
            # Connect range changes to update the manual limit fields (with a delay)
            vb.sigXRangeChanged.connect(lambda *args: self._trigger_limit_field_update())
            vb.sigYRangeChanged.connect(lambda *args: self._trigger_limit_field_update())

            # Link X axes and hide bottom axis for all but the last plot
            if last_plot_item:
                plot_item.setXLink(last_plot_item)
                plot_item.hideAxis('bottom')
            last_plot_item = plot_item

            # 3. Individual Y Zoom Slider (initially hidden)
            slider_widget = QtWidgets.QWidget() # Container for label + slider
            slider_layout = QtWidgets.QVBoxLayout(slider_widget)
            slider_layout.setContentsMargins(0,0,0,0); slider_layout.setSpacing(2)
            lbl_text = f"{channel.name or chan_id[:4]}" # Short label
            lbl = QtWidgets.QLabel(lbl_text); lbl.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            lbl.setToolTip(f"Y Zoom for {channel.name or chan_id}")
            self.individual_y_slider_labels[chan_id] = lbl # Store label if needed later
            slider_layout.addWidget(lbl)

            slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Vertical)
            slider.setRange(self.SLIDER_RANGE_MIN, self.SLIDER_RANGE_MAX)
            slider.setValue(self.SLIDER_DEFAULT_VALUE)
            slider.setToolTip(f"Adjust Y-axis zoom for channel {channel.name or chan_id}")
            # Use partial to pass chan_id to the slot
            slider.valueChanged.connect(partial(self._on_individual_y_zoom_changed, chan_id))
            slider_layout.addWidget(slider, stretch=1) # Slider stretches vertically

            self.individual_y_sliders[chan_id] = slider
            self.individual_y_sliders_layout.addWidget(slider_widget, stretch=1) # Add container to layout
            slider_widget.setVisible(False) # Initially hidden (until Y axes unlocked)

            # 4. Individual Y Scrollbar (initially hidden)
            scrollbar = QtWidgets.QScrollBar(QtCore.Qt.Orientation.Vertical)
            scrollbar.setRange(0, self.SCROLLBAR_MAX_RANGE) # Dummy range
            scrollbar.setToolTip(f"Scroll Y-axis for channel {channel.name or chan_id}")
            scrollbar.valueChanged.connect(partial(self._on_individual_y_scrollbar_changed, chan_id))
            self._reset_scrollbar(scrollbar) # Initialize to inactive state

            self.individual_y_scrollbars[chan_id] = scrollbar
            self.individual_y_scrollbars_layout.addWidget(scrollbar, stretch=1) # Add scrollbar directly
            scrollbar.setVisible(False) # Initially hidden

        # Configure the last plot item to show the bottom axis (Time)
        if last_plot_item:
            last_plot_item.setLabel('bottom', "Time", units='s')
            last_plot_item.showAxis('bottom')

        log.info("Channel UI creation complete.")

    # =========================================================================
    # File Loading & Display Options
    # =========================================================================
    def _open_file_or_folder(self):
        """Opens a file dialog, loads the selected file, finds siblings, and loads the first one."""
        try:
            file_filter = self.neo_adapter.get_supported_file_filter()
            log.debug(f"Using file filter: {file_filter}")
        except Exception as e:
            log.error(f"Failed to get file filter from NeoAdapter: {e}", exc_info=True)
            QtWidgets.QMessageBox.critical(self, "Adapter Error", f"Could not get file types from adapter:\n{e}")
            file_filter = "All Files (*)" # Fallback

        # Get last opened directory (more user-friendly)
        settings = QtCore.QSettings("Synaptipy", "Viewer")
        last_dir = settings.value("lastDirectory", "", type=str)

        filepath_str, selected_filter = QtWidgets.QFileDialog.getOpenFileName(
            self, "Open Recording File", dir=last_dir, filter=file_filter
        )

        if not filepath_str:
            log.info("File open dialog cancelled.")
            self.statusBar.showMessage("File open cancelled.", 3000)
            return

        selected_filepath = Path(filepath_str)
        folder_path = selected_filepath.parent

        # Save the directory for next time
        settings.setValue("lastDirectory", str(folder_path))

        selected_extension = selected_filepath.suffix.lower()
        log.info(f"File selected: {selected_filepath.name}. Scanning folder '{folder_path}' for files with extension '{selected_extension}'.")

        # Find all files with the same extension in the folder
        try:
            # Use glob to find matching files, case-insensitive on the extension might be needed depending on OS/FS
            # For simplicity, sticking to lower() comparison after glob
            sibling_files_all = list(folder_path.glob(f"*{selected_filepath.suffix}")) # Match exact suffix first
            # Filter list to ensure case-insensitivity robustly if needed, though glob might handle it
            sibling_files = sorted([p for p in sibling_files_all if p.suffix.lower() == selected_extension])

        except Exception as e:
            log.error(f"Error scanning folder {folder_path} for sibling files: {e}", exc_info=True)
            QtWidgets.QMessageBox.warning(self, "Folder Scan Error", f"Could not scan folder for similar files:\n{e}\nLoading selected file only.")
            self.file_list = [selected_filepath]
            self.current_file_index = 0
            self._load_and_display_file(selected_filepath)
            return

        if not sibling_files:
            log.warning(f"No other files with extension '{selected_extension}' found in the folder. Loading selected file only.")
            self.file_list = [selected_filepath]
            self.current_file_index = 0
        else:
            self.file_list = sibling_files
            try:
                # Find the index of the *actually selected* file in the sorted list
                self.current_file_index = self.file_list.index(selected_filepath)
                log.info(f"Found {len(self.file_list)} file(s) with extension '{selected_extension}'. Selected file is at index {self.current_file_index}.")
            except ValueError:
                log.error(f"Selected file '{selected_filepath.name}' not found in the scanned list? This shouldn't happen. Defaulting to index 0.")
                self.current_file_index = 0 # Fallback to the first file if index fails

        # Load the file at the determined index
        if self.file_list:
            self._load_and_display_file(self.file_list[self.current_file_index])
        else:
            # This case should ideally not be reached if a file was selected, but handle defensively
            log.error("File list is unexpectedly empty after selection.")
            self._reset_ui_and_state_for_new_file() # Reset to empty state
            self._update_ui_state()
            QtWidgets.QMessageBox.critical(self, "Loading Error", "Failed to identify the file to load.")


    def _load_and_display_file(self, filepath: Path):
        """Loads a single recording file, updates UI, and plots data."""
        if not filepath or not filepath.exists():
            log.error(f"Attempted to load invalid or non-existent file: {filepath}")
            QtWidgets.QMessageBox.critical(self, "File Error", f"File not found:\n{filepath}")
            # Clear relevant state if a file fails to load after being in the list
            self._reset_ui_and_state_for_new_file()
            self._update_ui_state()
            return

        self.statusBar.showMessage(f"Loading '{filepath.name}'...")
        QtWidgets.QApplication.processEvents() # Allow UI to update

        # --- Reset everything related to the previous file ---
        self._reset_ui_and_state_for_new_file()
        self.current_recording = None # Ensure it's None before trying to load

        # --- Load the new file ---
        try:
            log.info(f"Reading recording from: {filepath}")
            self.current_recording = self.neo_adapter.read_recording(filepath)
            log.info(f"Successfully loaded recording: {filepath.name}")

            # Store essential info from the recording
            self.max_trials_current_recording = self.current_recording.max_trials if self.current_recording and hasattr(self.current_recording, 'max_trials') else 0

            # --- Update UI based on loaded data ---
            self._create_channel_ui() # Create checkboxes, plots, controls
            self._update_metadata_display() # Update file info labels
            self._update_plot() # Initial plot drawing
            self._reset_view() # Auto-range the initial view (or apply manual limits if enabled)

            self.statusBar.showMessage(f"Loaded '{filepath.name}'. Ready.", 5000) # Timed message

        except (FileNotFoundError, UnsupportedFormatError, FileReadError, SynaptipyError) as e:
            log.error(f"Failed to load recording '{filepath.name}': {e}", exc_info=False) # No need for full traceback for known errors
            QtWidgets.QMessageBox.critical(self, "Loading Error", f"Could not load file:\n{filepath.name}\n\nError: {e}")
            self._clear_metadata_display() # Clear info display on error
            self.statusBar.showMessage(f"Error loading {filepath.name}.", 5000)
        except Exception as e:
            log.error(f"An unexpected error occurred while loading '{filepath.name}': {e}", exc_info=True) # Full traceback for unexpected errors
            QtWidgets.QMessageBox.critical(self, "Unexpected Loading Error", f"An unexpected error occurred while loading:\n{filepath.name}\n\n{e}")
            self._clear_metadata_display()
            self.statusBar.showMessage(f"Unexpected error loading {filepath.name}.", 5000)
        finally:
            # --- Final UI State Update ---
            # Ensure zoom/scroll controls are enabled/disabled correctly after loading attempt
            self._update_zoom_scroll_enable_state()
            # Update all other UI element states (buttons etc.)
            self._update_ui_state()
            # Re-apply manual limits if they were enabled before loading
            if self.manual_limits_enabled:
                 log.debug("Re-applying manual limits after file load.")
                 self._apply_manual_limits()

    def _on_plot_mode_changed(self, index: int):
        """Handles changes in the plot mode ComboBox."""
        new_mode = index
        if new_mode == self.current_plot_mode:
            return # No change

        new_mode_name = 'Overlay All + Avg' if new_mode == self.PlotMode.OVERLAY_AVG else 'Cycle Single Trial'
        log.info(f"Plot mode changed to: {new_mode_name}")

        # If switching mode, remove any manually plotted average (it's confusing otherwise)
        if self.selected_average_plot_items:
            log.debug("Plot mode changed, removing selected average plot.")
            self._remove_selected_average_plots()
            # Reset button state without triggering signal
            self.show_selected_average_button.blockSignals(True)
            self.show_selected_average_button.setChecked(False)
            self.show_selected_average_button.blockSignals(False)

        self.current_plot_mode = new_mode
        self.current_trial_index = 0 # Reset trial index when switching mode

        self._update_plot() # Redraw plots with the new mode
        self._reset_view() # Reset view after changing plot content
        self._update_ui_state() # Update button enables etc.

    def _trigger_plot_update(self):
        """Slot called when channel visibility or downsampling changes, triggers replot."""
        if not self.current_recording:
            return

        sender = self.sender()
        # Check if the sender was a channel checkbox (and not other checkboxes)
        is_channel_checkbox = isinstance(sender, QtWidgets.QCheckBox) and sender in self.channel_checkboxes.values()

        # If a channel checkbox changed visibility AND we have a selected average plot visible, remove the average plot
        if is_channel_checkbox and self.selected_average_plot_items:
            log.debug("Channel visibility changed, removing selected average plot.")
            self._remove_selected_average_plots()
            # Reset button state without triggering signal
            self.show_selected_average_button.blockSignals(True)
            self.show_selected_average_button.setChecked(False)
            self.show_selected_average_button.blockSignals(False)

        # --- Update the main plot data ---
        self._update_plot()

        # If a channel checkbox changed, update the visibility of individual Y controls
        if is_channel_checkbox:
            self._update_y_controls_visibility()
            # If a channel was just made visible, reset its Y view individually
            if sender.isChecked():
                # Find the channel ID associated with the sender checkbox
                chan_id = next((k for k, v in self.channel_checkboxes.items() if v == sender), None)
                if chan_id:
                    log.debug(f"Channel {chan_id} made visible, resetting its Y view.")
                    self._reset_single_plot_view(chan_id) # Reset this specific channel's Y axis


    # =========================================================================
    # Plotting Core & Metadata
    # =========================================================================
    def _clear_plot_data_only(self):
        """Removes only the data traces (trials, averages) from plots, preserving axes and selected avg overlay."""
        log.debug("Clearing existing plot data items (excluding selected averages)...")
        cleared_count = 0
        for chan_id, plot_item in self.channel_plots.items():
            if not plot_item or plot_item.scene() is None: continue # Skip if plot not valid

            # Get the currently plotted selected average item for this channel, if any
            selected_avg_item = self.selected_average_plot_items.get(chan_id)

            # Find items to remove: PlotDataItems or TextItems, but NOT the selected_avg_item
            items_to_remove = [
                item for item in plot_item.items
                if isinstance(item, (pg.PlotDataItem, pg.TextItem)) and item != selected_avg_item
            ]

            if items_to_remove:
                # log.debug(f"Removing {len(items_to_remove)} items from plot {chan_id}")
                for item in items_to_remove:
                    try:
                        plot_item.removeItem(item)
                        cleared_count += 1
                    except Exception as e:
                        # This might happen if item is already removed or invalid
                        log.warning(f"Could not remove item {item} from plot {chan_id}: {e}")

        # Clear the dictionary tracking these items
        self.channel_plot_data_items.clear()
        if cleared_count > 0:
            log.debug(f"Cleared {cleared_count} plot data items.")

    def _update_plot(self):
        """Updates all visible plots based on current mode, trial index, and channel visibility."""
        self._clear_plot_data_only() # Remove previous traces first

        if not self.current_recording or not self.channel_plots:
            log.warning("Update plot called but no recording or plots available.")
            self._update_ui_state() # Ensure UI reflects lack of data
            return

        is_cycle_mode = self.current_plot_mode == self.PlotMode.CYCLE_SINGLE
        log.debug(f"Updating plots. Mode: {'Cycle Single' if is_cycle_mode else 'Overlay All + Avg'}. Current Trial (0-based): {self.current_trial_index}")

        # --- Define Pens ---
        # Use VisConstants if available, otherwise provide fallbacks
        vis_const_available = VisConstants is not None
        trial_pen = pg.mkPen(
            VisConstants.TRIAL_COLOR + (VisConstants.TRIAL_ALPHA,) if vis_const_available else (128, 128, 128, 80),
            width=VisConstants.DEFAULT_PLOT_PEN_WIDTH if vis_const_available else 1
        )
        average_pen = pg.mkPen(
            VisConstants.AVERAGE_COLOR if vis_const_available else 'r',
            width=(VisConstants.DEFAULT_PLOT_PEN_WIDTH + 1) if vis_const_available else 2
        )
        single_trial_pen = pg.mkPen(
             VisConstants.TRIAL_COLOR if vis_const_available else (100, 100, 200), # Make single trial distinct
             width=VisConstants.DEFAULT_PLOT_PEN_WIDTH if vis_const_available else 1
        )
        # Downsampling threshold
        ds_threshold = VisConstants.DOWNSAMPLING_THRESHOLD if vis_const_available else 5000
        enable_downsampling = self.downsample_checkbox.isChecked()

        any_data_plotted = False
        visible_plots: List[pg.PlotItem] = [] # Keep track of plots actually shown

        # --- Iterate through channels and plot data ---
        for chan_id, plot_item in self.channel_plots.items():
            checkbox = self.channel_checkboxes.get(chan_id)
            channel = self.current_recording.channels.get(chan_id)

            # Check if channel should be plotted
            if checkbox and checkbox.isChecked() and channel and plot_item:
                plot_item.setVisible(True)
                visible_plots.append(plot_item)
                channel_plotted = False # Track if *any* data was plotted for this channel

                if not is_cycle_mode: # Overlay All + Avg mode
                    # Plot individual trials
                    for trial_idx in range(channel.num_trials):
                        data = channel.get_data(trial_idx)
                        time_vec = channel.get_relative_time_vector(trial_idx)
                        if data is not None and time_vec is not None:
                             data_item = plot_item.plot(time_vec, data, pen=trial_pen)
                             data_item.opts['autoDownsample'] = enable_downsampling
                             data_item.opts['autoDownsampleThreshold'] = ds_threshold if enable_downsampling else 0
                             self.channel_plot_data_items.setdefault(chan_id, []).append(data_item)
                             channel_plotted = True
                        else: log.warning(f"Missing data or time for trial {trial_idx+1} in channel {chan_id}")

                    # Plot overall average
                    avg_data = channel.get_averaged_data()
                    avg_time_vec = channel.get_relative_averaged_time_vector()
                    if avg_data is not None and avg_time_vec is not None:
                        avg_item = plot_item.plot(avg_time_vec, avg_data, pen=average_pen)
                        avg_item.opts['autoDownsample'] = enable_downsampling
                        avg_item.opts['autoDownsampleThreshold'] = ds_threshold if enable_downsampling else 0
                        self.channel_plot_data_items.setdefault(chan_id, []).append(avg_item)
                        channel_plotted = True
                    else: log.debug(f"No average data/time for channel {chan_id}")

                else: # Cycle Single Trial mode
                    # Determine which trial index to plot (handle edge case of no trials)
                    trial_idx_to_plot = -1
                    if channel.num_trials > 0:
                        trial_idx_to_plot = min(self.current_trial_index, channel.num_trials - 1)

                    if trial_idx_to_plot >= 0:
                        data = channel.get_data(trial_idx_to_plot)
                        time_vec = channel.get_relative_time_vector(trial_idx_to_plot)
                        if data is not None and time_vec is not None:
                            data_item = plot_item.plot(time_vec, data, pen=single_trial_pen)
                            data_item.opts['autoDownsample'] = enable_downsampling
                            data_item.opts['autoDownsampleThreshold'] = ds_threshold if enable_downsampling else 0
                            self.channel_plot_data_items.setdefault(chan_id, []).append(data_item)
                            channel_plotted = True
                        else:
                            # Data missing for the selected trial, show error message
                            log.warning(f"Missing data or time for cycle trial {trial_idx_to_plot+1} in channel {chan_id}")
                            error_text = pg.TextItem(f"Data Error\nTrial {trial_idx_to_plot+1}", color='r', anchor=(0.5, 0.5))
                            plot_item.addItem(error_text) # Add text item directly to plot
                            # Position it centrally (approximate) - requires view range which might not be set yet
                            # error_text.setPos(plot_item.vb.viewRange()[0][0] * 0.5, plot_item.vb.viewRange()[1][0] * 0.5)

                    else: # No trials exist for this channel
                         no_trial_text = pg.TextItem("No Trials", color='orange', anchor=(0.5, 0.5))
                         plot_item.addItem(no_trial_text)


                # If nothing was plotted for this visible channel (e.g., 0 trials in overlay mode)
                if not channel_plotted and channel.num_trials == 0:
                    no_data_text = pg.TextItem("No Trials", color='orange', anchor=(0.5, 0.5))
                    plot_item.addItem(no_data_text)
                elif not channel_plotted: # Should only happen if errors occurred getting data
                    no_data_text = pg.TextItem("Plotting Error", color='red', anchor=(0.5, 0.5))
                    plot_item.addItem(no_data_text)


                if channel_plotted:
                    any_data_plotted = True

            elif plot_item: # Channel is not checked or doesn't exist, hide the plot item
                plot_item.hide()

        # --- Configure X-axis linking and visibility ---
        # The last *visible* plot should show the bottom X-axis (Time)
        last_visible_plot = visible_plots[-1] if visible_plots else None

        for i, plot_item in enumerate(self.channel_plots.values()):
            is_visible = plot_item in visible_plots
            is_last_visible = plot_item == last_visible_plot

            # Show/hide bottom axis
            plot_item.showAxis('bottom', show=is_last_visible)
            # Set bottom label only for the last visible plot
            if is_last_visible:
                plot_item.setLabel('bottom', "Time", units='s')
            else:
                # Clear label if not the last visible plot (or not visible at all)
                 if plot_item.getAxis('bottom').labelText is not None:
                    plot_item.setLabel('bottom', None) # Remove text

            # Update X-axis linking (only link visible plots sequentially)
            if is_visible:
                try:
                    visible_index = visible_plots.index(plot_item)
                    link_target = visible_plots[visible_index - 1] if visible_index > 0 else None
                    if plot_item.getViewBox().linkedView(0) != link_target: # Avoid redundant linking
                        plot_item.setXLink(link_target)
                except ValueError: # Should not happen if is_visible is true
                    log.error(f"Plot item {plot_item} marked visible but not found in visible_plots list.")
                    plot_item.setXLink(None) # Unlink if error occurs
            else:
                # Unlink hidden plots
                if plot_item.getViewBox().linkedView(0) is not None:
                    plot_item.setXLink(None)


        # --- Final Updates ---
        self._update_trial_label() # Update trial X/Y display
        self._update_ui_state() # Update general UI enables/disables
        log.debug(f"Plot update complete. Data plotted: {any_data_plotted}")


    def _update_metadata_display(self):
        """Updates the 'File Information' group box."""
        if self.current_recording:
            rec = self.current_recording
            self.filename_label.setText(rec.source_file.name)
            self.filename_label.setToolTip(str(rec.source_file)) # Show full path on hover

            sr_text = f"{rec.sampling_rate:.2f} Hz" if rec.sampling_rate else "N/A"
            self.sampling_rate_label.setText(sr_text)

            dur_text = f"{rec.duration:.3f} s" if rec.duration else "N/A"
            self.duration_label.setText(dur_text)

            # Combine channel count and trial count
            ch_text = f"{rec.num_channels} ch / {self.max_trials_current_recording} trial(s)"
            self.channels_label.setText(ch_text)
        else:
            self._clear_metadata_display()

    def _clear_metadata_display(self):
        """Clears the 'File Information' labels."""
        self.filename_label.setText("N/A"); self.filename_label.setToolTip("")
        self.sampling_rate_label.setText("N/A")
        self.duration_label.setText("N/A")
        self.channels_label.setText("N/A")

    # =========================================================================
    # UI State Update
    # =========================================================================
    def _update_ui_state(self):
        """Updates the enabled/disabled/visible state of various UI elements based on current application state."""
        # --- Determine current state ---
        has_data = self.current_recording is not None
        has_visible_plots = any(p.isVisible() for p in self.channel_plots.values())
        is_folder_mode = len(self.file_list) > 1
        is_cycle_mode = has_data and self.current_plot_mode == self.PlotMode.CYCLE_SINGLE
        has_trials = has_data and self.max_trials_current_recording > 0
        has_selection = bool(self.selected_trial_indices)
        is_selected_average_plotted = bool(self.selected_average_plot_items)

        # --- Update Menu Items ---
        self.export_nwb_action.setEnabled(has_data)

        # --- Update Left Panel Widgets ---
        self.plot_mode_combobox.setEnabled(has_data)
        self.downsample_checkbox.setEnabled(has_data)
        # Manual Trial Averaging section (only relevant in cycle mode with trials)
        can_select_trials = is_cycle_mode and has_trials
        self.select_trial_button.setEnabled(can_select_trials)
        if can_select_trials:
            is_current_trial_selected = self.current_trial_index in self.selected_trial_indices
            self.select_trial_button.setText("Deselect Current Trial" if is_current_trial_selected else "Add Current Trial")
            self.select_trial_button.setToolTip("Remove current trial from averaging set." if is_current_trial_selected else "Add current trial to averaging set.")
        else:
            self.select_trial_button.setText("Add Current Trial") # Default text when disabled
            self.select_trial_button.setToolTip("Add/Remove the currently viewed trial (in Cycle Mode) to the set for averaging.") # Default tooltip
        self.clear_selection_button.setEnabled(has_selection)
        self.show_selected_average_button.setEnabled(has_selection)
        if has_selection:
            self.show_selected_average_button.setText("Hide Selected Avg" if is_selected_average_plotted else "Plot Selected Avg")
            self.show_selected_average_button.setToolTip("Hide the average of selected trials." if is_selected_average_plotted else "Show the average of selected trials as an overlay.")
        else:
             self.show_selected_average_button.setText("Plot Selected Avg")
             self.show_selected_average_button.setToolTip("Toggle the display of the average of selected trials as an overlay.")

        # Manual Limits Group
        manual_limits_controls_enabled = has_data # Can only set/enable limits if data is loaded
        parent_groupbox = self.enable_manual_limits_checkbox.parentWidget() if self.enable_manual_limits_checkbox else None
        if isinstance(parent_groupbox, QtWidgets.QGroupBox):
            parent_groupbox.setEnabled(manual_limits_controls_enabled)
        else: # Enable individual controls if groupbox logic fails
            if self.enable_manual_limits_checkbox: self.enable_manual_limits_checkbox.setEnabled(manual_limits_controls_enabled)
            if self.set_manual_limits_button: self.set_manual_limits_button.setEnabled(manual_limits_controls_enabled and not self.manual_limits_enabled) # Can only set when not enabled? Or always? Always seems better.
            if self.set_manual_limits_button: self.set_manual_limits_button.setEnabled(manual_limits_controls_enabled)
            if self.manual_limit_x_min_edit: self.manual_limit_x_min_edit.setEnabled(manual_limits_controls_enabled)
            # ... enable other limit edits similarly ...

        # Channel Selection Group
        self.channel_select_group.setEnabled(has_data)

        # --- Update Center Panel Widgets ---
        # File Navigation
        self.prev_file_button.setVisible(is_folder_mode)
        self.next_file_button.setVisible(is_folder_mode)
        self.folder_file_index_label.setVisible(is_folder_mode)
        if is_folder_mode:
            self.prev_file_button.setEnabled(self.current_file_index > 0)
            self.next_file_button.setEnabled(self.current_file_index < len(self.file_list) - 1)
            # Update label text
            fname = self.file_list[self.current_file_index].name if 0 <= self.current_file_index < len(self.file_list) else "N/A"
            self.folder_file_index_label.setText(f"File {self.current_file_index + 1}/{len(self.file_list)}: {fname}")
        else:
            self.folder_file_index_label.setText("") # Clear label if not in folder mode

        # Plot Controls Row
        self.reset_view_button.setEnabled(has_visible_plots) # Can always reset if plots are visible
        # Trial Navigation (only relevant in cycle mode with multiple trials)
        enable_trial_navigation = is_cycle_mode and self.max_trials_current_recording > 1
        self.prev_trial_button.setEnabled(enable_trial_navigation and self.current_trial_index > 0)
        self.next_trial_button.setEnabled(enable_trial_navigation and self.current_trial_index < self.max_trials_current_recording - 1)
        self.trial_index_label.setVisible(is_cycle_mode and has_trials) # Show label if in cycle mode with any trials

        # --- Update Right Panel (Y Controls) ---
        # Visibility is handled by _update_y_controls_visibility
        # Enable/disable based on manual limits is handled by _update_zoom_scroll_enable_state

    def _update_trial_label(self):
        """Updates the trial index label (e.g., "Trial 3 / 10")."""
        if (self.current_recording and self.current_plot_mode == self.PlotMode.CYCLE_SINGLE and self.max_trials_current_recording > 0):
            self.trial_index_label.setText(f"{self.current_trial_index + 1} / {self.max_trials_current_recording}")
        else:
            self.trial_index_label.setText("N/A")

    # =========================================================================
    # Zoom & Scroll Controls (Interaction Logic)
    # =========================================================================
    def _calculate_new_range(self, base_range: Optional[Tuple[float, float]], slider_value: int) -> Optional[Tuple[float, float]]:
        """Calculates a new view range based on a base range and a slider value."""
        if base_range is None or base_range[0] is None or base_range[1] is None:
            log.warning("Cannot calculate new range: base_range is invalid.")
            return None
        try:
            min_val, max_val = base_range
            center = (min_val + max_val) / 2.0
            full_span = max(abs(max_val - min_val), 1e-12) # Avoid division by zero, use max absolute span

            min_slider, max_slider = float(self.SLIDER_RANGE_MIN), float(self.SLIDER_RANGE_MAX)
            # Normalize slider value (0=min zoom -> 1=max zoom)
            normalized_zoom = (float(slider_value) - min_slider) / (max_slider - min_slider) if max_slider > min_slider else 0.0

            # Invert behavior: min slider = max span (zoomed out), max slider = min span (zoomed in)
            # Map normalized_zoom (0..1) to a zoom factor (1.0 .. MIN_ZOOM_FACTOR)
            zoom_factor = 1.0 - normalized_zoom * (1.0 - self.MIN_ZOOM_FACTOR)
            zoom_factor = max(self.MIN_ZOOM_FACTOR, min(1.0, zoom_factor)) # Clamp factor

            new_span = full_span * zoom_factor
            new_min = center - new_span / 2.0
            new_max = center + new_span / 2.0
            return (new_min, new_max)
        except Exception as e:
            log.error(f"Error calculating new range: {e}", exc_info=True)
            return None

    def _on_x_zoom_changed(self, value: int):
        """Handles changes from the X-axis zoom slider."""
        if self.manual_limits_enabled or self.base_x_range is None or self._updating_viewranges:
            return # Ignore if manual limits on, no base range, or already updating

        new_x_range = self._calculate_new_range(self.base_x_range, value)
        if new_x_range is None: return

        # Apply to the first visible plot (others are linked)
        first_visible_plot = next((p for p in self.channel_plots.values() if p.isVisible()), None)
        if first_visible_plot and first_visible_plot.getViewBox():
            vb = first_visible_plot.getViewBox()
            try:
                self._updating_viewranges = True # Prevent feedback loop
                vb.setXRange(new_x_range[0], new_x_range[1], padding=0)
            except Exception as e:
                log.error(f"Error setting X range from slider: {e}", exc_info=True)
            finally:
                self._updating_viewranges = False
                # Update scrollbar after view changes
                self._update_scrollbar_from_view(self.x_scrollbar, self.base_x_range, new_x_range)
        else:
             log.debug("X zoom changed but no visible plot found to apply it to.")


    def _on_x_scrollbar_changed(self, value: int):
        """Handles changes from the X-axis scrollbar."""
        if self.manual_limits_enabled or self.base_x_range is None or self._updating_scrollbars:
             return # Ignore if manual limits on, no base range, or already updating

        first_visible_plot = next((p for p in self.channel_plots.values() if p.isVisible()), None)
        if not first_visible_plot or not first_visible_plot.getViewBox():
             log.debug("X scrollbar changed but no visible plot found.")
             return

        vb = first_visible_plot.getViewBox()
        try:
            current_x_range = vb.viewRange()[0]
            current_span = max(abs(current_x_range[1] - current_x_range[0]), 1e-12)
            base_span = max(abs(self.base_x_range[1] - self.base_x_range[0]), 1e-12)

            # Total scrollable distance in data units
            scrollable_data_range = max(0, base_span - current_span)

            # Calculate fraction scrolled (0.0 to 1.0)
            scroll_fraction = float(value) / max(1, self.x_scrollbar.maximum()) # Avoid division by zero if max is 0

            # Calculate new minimum position
            new_min = self.base_x_range[0] + scroll_fraction * scrollable_data_range
            new_max = new_min + current_span

            self._updating_viewranges = True # Prevent feedback from sigXRangeChanged
            vb.setXRange(new_min, new_max, padding=0)
        except Exception as e:
            log.error(f"Error handling X scrollbar change: {e}", exc_info=True)
        finally:
            self._updating_viewranges = False # Release lock

    def _handle_vb_xrange_changed(self, vb: pg.ViewBox, new_range: Tuple[float, float]):
        """Handles manual panning/zooming on the X-axis of a ViewBox."""
        # If manual limits are enabled, force the view back (unless we are programmatically setting it)
        if self.manual_limits_enabled and self.manual_x_limits and not self._updating_viewranges:
            log.debug("Manual X Limits: View changed externally, re-applying limits.")
            self._updating_viewranges = True # Prevent infinite loop
            try:
                vb.setXRange(self.manual_x_limits[0], self.manual_x_limits[1], padding=0)
            finally:
                self._updating_viewranges = False
            return # Don't update scrollbar in this case

        # Ignore changes triggered by our own updates or if base range isn't set
        if self._updating_viewranges or self.base_x_range is None:
            return

        # Update the scrollbar position based on the new view range
        # log.debug(f"VB XRange Changed: {new_range}. Updating scrollbar.") # Can be verbose
        self._update_scrollbar_from_view(self.x_scrollbar, self.base_x_range, new_range)
        # Update slider position? Less critical, could be complex due to non-linear mapping


    def _on_y_lock_changed(self, state: int):
        """Handles changes to the Y-axis lock checkbox."""
        self.y_axes_locked = bool(state == QtCore.Qt.CheckState.Checked.value) # Get boolean value
        log.info(f"Y-axes lock {'ENABLED' if self.y_axes_locked else 'DISABLED'}.")
        self._update_y_controls_visibility() # Show/hide global vs individual controls
        # No need to replot, just update UI state
        self._update_ui_state()
        self._update_zoom_scroll_enable_state() # Enable/disable controls based on lock state


    def _update_y_controls_visibility(self):
        """Shows/hides Global vs Individual Y zoom/scroll controls based on lock state and plot visibility."""
        is_locked = self.y_axes_locked
        any_plots_visible = any(p.isVisible() for p in self.channel_plots.values())

        # Set visibility of the container widgets for global controls
        self.global_y_slider_widget.setVisible(is_locked and any_plots_visible)
        self.global_y_scrollbar_widget.setVisible(is_locked and any_plots_visible)

        # Set visibility of the containers for individual controls
        self.individual_y_sliders_container.setVisible(not is_locked and any_plots_visible)
        self.individual_y_scrollbars_container.setVisible(not is_locked and any_plots_visible)

        if not any_plots_visible:
            log.debug("No plots visible, hiding all Y controls.")
            return # Skip individual updates if nothing is visible

        # Get IDs of currently visible channels
        visible_channel_ids = {
            p.getViewBox()._synaptipy_chan_id
            for p in self.channel_plots.values()
            if p.isVisible() and hasattr(p.getViewBox(), '_synaptipy_chan_id')
        }

        # Master enable/disable based on manual limits
        controls_enabled = not self.manual_limits_enabled

        if not is_locked:
            # Update visibility and enabled state of individual controls
            for cid, slider_widget in self.individual_y_sliders.items(): # Iterate through sliders dict keys
                 slider_container = slider_widget.parentWidget() # Get the container (QWidget holding label+slider)
                 is_channel_visible = cid in visible_channel_ids
                 slider_container.setVisible(is_channel_visible)
                 has_base_range = self.base_y_ranges.get(cid) is not None
                 slider_widget.setEnabled(is_channel_visible and has_base_range and controls_enabled)

            for cid, scrollbar in self.individual_y_scrollbars.items():
                 is_channel_visible = cid in visible_channel_ids
                 scrollbar.setVisible(is_channel_visible)
                 has_base_range = self.base_y_ranges.get(cid) is not None
                 # Only enable if visible, has base, not manual limited, AND if it *can* be scrolled (range > 0)
                 can_scroll = scrollbar.maximum() > scrollbar.minimum()
                 scrollbar.setEnabled(is_channel_visible and has_base_range and controls_enabled and can_scroll)
        else:
             # Update enabled state of global controls
             # Enable global slider if any visible plot has a base range
             can_enable_global_slider = any(self.base_y_ranges.get(cid) is not None for cid in visible_channel_ids)
             self.global_y_slider.setEnabled(can_enable_global_slider and controls_enabled)
             # Enable global scrollbar similarly, also checking if it *can* be scrolled
             can_scroll_global = self.global_y_scrollbar.maximum() > self.global_y_scrollbar.minimum()
             self.global_y_scrollbar.setEnabled(can_enable_global_slider and controls_enabled and can_scroll_global)


    def _on_global_y_zoom_changed(self, value: int):
        """Handles changes from the Global Y-axis zoom slider."""
        if self.manual_limits_enabled or not self.y_axes_locked or self._updating_viewranges:
            return # Ignore if limits on, not locked, or already updating
        self._apply_global_y_zoom(value)

    def _apply_global_y_zoom(self, value: int):
        """Applies the global Y zoom value to all visible plots."""
        if self.manual_limits_enabled: return # Double check manual limits

        log.debug(f"Applying global Y zoom value: {value}")
        base_range_ref, new_range_ref = None, None # For updating scrollbar later
        self._updating_viewranges = True # Prevent feedback loop
        try:
            for cid, plot_item in self.channel_plots.items():
                if plot_item.isVisible() and plot_item.getViewBox():
                    base_y = self.base_y_ranges.get(cid)
                    if base_y is None:
                        log.warning(f"Cannot apply global Y zoom to {cid}: No base Y range found.")
                        continue

                    new_y_range = self._calculate_new_range(base_y, value)
                    if new_y_range:
                        plot_item.getViewBox().setYRange(new_y_range[0], new_y_range[1], padding=0)
                        # Use the first valid range found as reference for the scrollbar
                        if base_range_ref is None:
                            base_range_ref = base_y
                            new_range_ref = new_y_range
                    else:
                         log.warning(f"Failed to calculate new Y range for {cid} with zoom value {value}")
        except Exception as e:
             log.error(f"Error applying global Y zoom: {e}", exc_info=True)
        finally:
            self._updating_viewranges = False # Release lock

        # Update the global scrollbar based on the reference ranges
        if base_range_ref and new_range_ref:
            self._update_scrollbar_from_view(self.global_y_scrollbar, base_range_ref, new_range_ref)
        else:
            # If no valid reference was found (e.g., no visible plots with base range), reset scrollbar
            self._reset_scrollbar(self.global_y_scrollbar)


    def _on_global_y_scrollbar_changed(self, value: int):
        """Handles changes from the Global Y-axis scrollbar."""
        if self.manual_limits_enabled or not self.y_axes_locked or self._updating_scrollbars:
            return # Ignore if limits on, not locked, or already updating scrollbars
        self._apply_global_y_scroll(value)


    def _apply_global_y_scroll(self, value: int):
        """Applies the global Y scroll value to all visible plots."""
        if self.manual_limits_enabled: return # Double check manual limits

        # Find the first visible plot to use as a reference for current span
        first_visible_plot = next((p for p in self.channel_plots.values() if p.isVisible() and p.getViewBox()), None)
        if not first_visible_plot:
            log.debug("Global Y scroll changed but no visible plot found.")
            return

        self._updating_viewranges = True # Prevent feedback from sigYRangeChanged
        try:
            vb_ref = first_visible_plot.getViewBox()
            ref_cid = getattr(vb_ref, '_synaptipy_chan_id', None)
            ref_base_y = self.base_y_ranges.get(ref_cid)

            if ref_base_y is None or ref_base_y[0] is None or ref_base_y[1] is None:
                log.warning(f"Global Y Scroll: Reference plot {ref_cid} has no valid base Y range.")
                return # Flag reset in finally

            current_y_range_ref = vb_ref.viewRange()[1]
            current_span_ref = max(abs(current_y_range_ref[1] - current_y_range_ref[0]), 1e-12)
            ref_base_span = max(abs(ref_base_y[1] - ref_base_y[0]), 1e-12)

            # Calculate scroll fraction
            scroll_fraction = float(value) / max(1, self.global_y_scrollbar.maximum())

            # Apply scroll to all visible plots
            for cid, plot_item in self.channel_plots.items():
                if plot_item.isVisible() and plot_item.getViewBox():
                    base_y = self.base_y_ranges.get(cid)
                    if base_y is None or base_y[0] is None or base_y[1] is None:
                        log.warning(f"Skipping global Y scroll for {cid}: No base Y range.")
                        continue

                    base_span = max(abs(base_y[1] - base_y[0]), 1e-12)
                    # Total scrollable distance for this channel (based on reference span)
                    scrollable_data_range = max(0, base_span - current_span_ref)

                    # Calculate new minimum based on scroll fraction and this channel's base
                    new_min = base_y[0] + scroll_fraction * scrollable_data_range
                    new_max = new_min + current_span_ref # Maintain the span from the reference plot

                    plot_item.getViewBox().setYRange(new_min, new_max, padding=0)

        except Exception as e:
            log.error(f"Error applying global Y scroll: {e}", exc_info=True)
        finally:
            self._updating_viewranges = False # Always release lock

    def _on_individual_y_zoom_changed(self, chan_id: str, value: int):
        """Handles changes from an individual channel's Y-axis zoom slider."""
        if self.manual_limits_enabled or self.y_axes_locked or self._updating_viewranges:
            return # Ignore if limits on, locked, or already updating

        plot_item = self.channel_plots.get(chan_id)
        base_y = self.base_y_ranges.get(chan_id)
        scrollbar = self.individual_y_scrollbars.get(chan_id)

        if not plot_item or not plot_item.isVisible() or not plot_item.getViewBox() or base_y is None or scrollbar is None:
            log.debug(f"Individual Y zoom for {chan_id} ignored: Plot/base/scrollbar not valid or visible.")
            return

        new_y_range = self._calculate_new_range(base_y, value)

        if new_y_range:
            self._updating_viewranges = True # Set flag before potential errors
            try:
                plot_item.getViewBox().setYRange(new_y_range[0], new_y_range[1], padding=0)
            except Exception as e:
                 log.error(f"Error setting individual Y range for {chan_id} from slider: {e}", exc_info=True)
            finally:
                self._updating_viewranges = False # Always release lock
                # Update the corresponding scrollbar
                self._update_scrollbar_from_view(scrollbar, base_y, new_y_range)
        else:
            log.warning(f"Failed to calculate new Y range for individual zoom on {chan_id}")


    def _on_individual_y_scrollbar_changed(self, chan_id: str, value: int):
        """Handles changes from an individual channel's Y-axis scrollbar."""
        if self.manual_limits_enabled or self.y_axes_locked or self._updating_scrollbars:
            return # Ignore if limits on, locked, or already updating

        plot_item = self.channel_plots.get(chan_id)
        base_y = self.base_y_ranges.get(chan_id)
        scrollbar = self.individual_y_scrollbars.get(chan_id)

        if not plot_item or not plot_item.isVisible() or not plot_item.getViewBox() or base_y is None or scrollbar is None:
            log.debug(f"Individual Y scroll for {chan_id} ignored: Plot/base/scrollbar not valid or visible.")
            return

        vb = plot_item.getViewBox()
        try:
            current_y_range = vb.viewRange()[1]
            current_span = max(abs(current_y_range[1] - current_y_range[0]), 1e-12)
            base_span = max(abs(base_y[1] - base_y[0]), 1e-12)

            # Total scrollable distance in data units for this channel
            scrollable_data_range = max(0, base_span - current_span)

            # Calculate fraction scrolled (0.0 to 1.0)
            scroll_fraction = float(value) / max(1, scrollbar.maximum())

            # Calculate new minimum position
            new_min = base_y[0] + scroll_fraction * scrollable_data_range
            new_max = new_min + current_span

            self._updating_viewranges = True # Prevent feedback from sigYRangeChanged
            vb.setYRange(new_min, new_max, padding=0)
        except Exception as e:
            log.error(f"Error handling individual Y scrollbar change for {chan_id}: {e}", exc_info=True)
        finally:
            self._updating_viewranges = False # Release lock


    def _handle_vb_yrange_changed(self, vb: pg.ViewBox, new_range: Tuple[float, float]):
        """Handles manual panning/zooming on the Y-axis of a ViewBox."""
        chan_id = getattr(vb, '_synaptipy_chan_id', None)
        if chan_id is None: return # Should have channel ID

        # If manual limits are enabled, force the view back (unless we are programmatically setting it)
        if self.manual_limits_enabled and self.manual_y_limits and not self._updating_viewranges:
            log.debug(f"Manual Y Limits ({chan_id}): View changed externally, re-applying limits.")
            self._updating_viewranges = True # Prevent infinite loop
            try:
                vb.setYRange(self.manual_y_limits[0], self.manual_y_limits[1], padding=0)
            finally:
                self._updating_viewranges = False
            return # Don't update scrollbar

        # Ignore changes triggered by our own updates or if base range isn't set for this channel
        base_y = self.base_y_ranges.get(chan_id)
        if self._updating_viewranges or base_y is None:
            return

        # Update the appropriate scrollbar(s)
        if self.y_axes_locked:
            # In locked mode, changes to *any* plot should potentially update the global scrollbar.
            # Use the *first visible* plot as the reference for the global scrollbar update.
            first_visible_vb = next((p.getViewBox() for p in self.channel_plots.values() if p.isVisible() and p.getViewBox()), None)
            if vb == first_visible_vb: # Only update global scrollbar based on changes to the first plot
                # log.debug(f"VB YRange Changed (Locked, Ref Plot {chan_id}): {new_range}. Updating global scrollbar.")
                self._update_scrollbar_from_view(self.global_y_scrollbar, base_y, new_range)
            # else: Changes to other plots in locked mode don't affect the global scrollbar directly (they follow the linked Y range)

        else: # Unlocked mode
            # Update the specific scrollbar for this channel
            scrollbar = self.individual_y_scrollbars.get(chan_id)
            if scrollbar:
                # log.debug(f"VB YRange Changed (Unlocked {chan_id}): {new_range}. Updating individual scrollbar.")
                self._update_scrollbar_from_view(scrollbar, base_y, new_range)


    def _update_scrollbar_from_view(self, scrollbar: QtWidgets.QScrollBar,
                                     base_range: Optional[Tuple[float,float]],
                                     view_range: Optional[Tuple[float, float]]):
        """Updates a scrollbar's range, page step, and value based on the view range relative to the base range."""
        if self._updating_scrollbars or scrollbar is None: return # Prevent recursion or errors
        if self.manual_limits_enabled or base_range is None or view_range is None:
            # If limits are on, or ranges invalid, disable and reset the scrollbar
            self._reset_scrollbar(scrollbar)
            return

        self._updating_scrollbars = True # Set lock
        try:
            b_min, b_max = base_range
            v_min, v_max = view_range
            base_span = max(abs(b_max - b_min), 1e-12)
            view_span = max(abs(v_max - v_min), 1e-12)

            # Ensure view span isn't larger than base span (can happen with padding)
            view_span = min(view_span, base_span)

            # Page step represents the proportion of the total range visible
            page_step = max(1, min(int((view_span / base_span) * self.SCROLLBAR_MAX_RANGE), self.SCROLLBAR_MAX_RANGE))

            # The maximum value the scrollbar can reach
            # (Total range - visible part = scrollable part)
            range_max = max(0, self.SCROLLBAR_MAX_RANGE - page_step)

            # Calculate the scrollbar value (position)
            # Relative position of the view minimum within the scrollable part of the base range
            relative_pos = v_min - b_min
            scrollable_data_range = max(abs(base_span - view_span), 1e-12) # Data range that can be scrolled over

            value = 0
            if scrollable_data_range > 1e-10: # Avoid division by near-zero
                 value = int((relative_pos / scrollable_data_range) * range_max)
                 value = max(0, min(value, range_max)) # Clamp value within [0, range_max]

            # Apply updates to the scrollbar
            scrollbar.blockSignals(True) # Block signals during update
            scrollbar.setRange(0, range_max)
            scrollbar.setPageStep(page_step)
            scrollbar.setValue(value)
            scrollbar.setEnabled(range_max > 0) # Enable only if there's something to scroll
            scrollbar.blockSignals(False)

        except Exception as e:
            log.error(f"Error updating scrollbar: {e}", exc_info=True)
            self._reset_scrollbar(scrollbar) # Reset on error
        finally:
            self._updating_scrollbars = False # Release lock

    # =========================================================================
    # View Reset (Handles manual limits)
    # =========================================================================
    def _reset_view(self):
        """Resets view: Applies manual limits if enabled, otherwise auto-ranges all visible plots."""
        log.info("Reset View requested.")
        if not self.current_recording:
             log.warning("Reset View: No recording loaded.")
             # Ensure UI is cleared if reset is pressed with no data
             self._reset_ui_and_state_for_new_file()
             self._update_ui_state()
             return

        if self.manual_limits_enabled:
            log.info("Manual limits enabled. Applying stored limits instead of auto-ranging.")
            self._apply_manual_limits()
            # Ensure UI state is consistent after applying limits (e.g., button enables)
            self._update_ui_state()
            return

        # --- Auto-ranging ---
        log.debug("Manual limits OFF. Performing auto-range on visible plots.")
        visible_plots_map = {
            p.getViewBox()._synaptipy_chan_id: p
            for p in self.channel_plots.values()
            if p.isVisible() and hasattr(p.getViewBox(), '_synaptipy_chan_id')
        }

        if not visible_plots_map:
            log.debug("Reset View: No visible plots to auto-range.")
            self.base_x_range = None
            self.base_y_ranges.clear()
            self._reset_scrollbar(self.x_scrollbar)
            self._reset_scrollbar(self.global_y_scrollbar)
            for scrollbar in self.individual_y_scrollbars.values(): self._reset_scrollbar(scrollbar)
            self._reset_all_sliders()
            self._update_y_controls_visibility()
            self._update_limit_fields()
            self._update_zoom_scroll_enable_state()
            self._update_ui_state()
            return

        # Enable auto-range on the first visible plot for X, and all visible plots for Y
        first_cid, first_plot = next(iter(visible_plots_map.items()))
        log.debug(f"Auto-ranging X based on plot {first_cid}")
        first_plot.getViewBox().enableAutoRange(axis=pg.ViewBox.XAxis)

        for plot in visible_plots_map.values():
            plot.getViewBox().enableAutoRange(axis=pg.ViewBox.YAxis)

        # --- Store the new base ranges obtained from auto-ranging ---
        # X Range (from the first visible plot, as they are linked)
        try:
            # Get range *after* auto-range has been processed (might need slight delay?)
            # Qt event loop might need to process; however, enableAutoRange often triggers immediate update.
            # Let's assume it's immediate for now.
            QtCore.QTimer.singleShot(0, self._capture_base_ranges_after_reset) # Capture after event loop tick

        except Exception as e:
             log.error(f"Reset View: Unexpected error during auto-range setup: {e}", exc_info=True)
             self.base_x_range = None
             self.base_y_ranges.clear()

        # Reset sliders to default zoom level
        self._reset_all_sliders()

        # Update scrollbars based on the *new* base ranges (this will happen in _capture_base_ranges_after_reset)
        # Update UI states
        log.debug("Auto-range triggered. Base ranges will be captured shortly.")
        self._update_limit_fields() # Update fields to show 'Auto' or new ranges
        self._update_y_controls_visibility()
        self._update_zoom_scroll_enable_state()
        self._update_ui_state()

    def _capture_base_ranges_after_reset(self):
        """Captures the view ranges after auto-ranging and updates scrollbars."""
        log.debug("Capturing base ranges after auto-range reset...")
        visible_plots_map = {
            p.getViewBox()._synaptipy_chan_id: p
            for p in self.channel_plots.values()
            if p.isVisible() and hasattr(p.getViewBox(), '_synaptipy_chan_id')
        }
        if not visible_plots_map:
            log.debug("Capture Base Ranges: No visible plots found.")
            return

        first_cid, first_plot = next(iter(visible_plots_map.items()))

        # Capture Base X Range
        try:
            self.base_x_range = first_plot.getViewBox().viewRange()[0]
            log.debug(f"Reset Capture: Base X Range: {self.base_x_range}")
            # Update X scrollbar now that base range is known
            if self.base_x_range:
                 self._update_scrollbar_from_view(self.x_scrollbar, self.base_x_range, self.base_x_range)
            else: self._reset_scrollbar(self.x_scrollbar)
        except Exception as e:
            log.error(f"Reset Capture: Error getting Base X Range: {e}", exc_info=True)
            self.base_x_range = None
            self._reset_scrollbar(self.x_scrollbar)

        # Capture Base Y Ranges for all visible plots
        self.base_y_ranges.clear()
        for cid, plot in visible_plots_map.items():
             try:
                 base_y = plot.getViewBox().viewRange()[1]
                 self.base_y_ranges[cid] = base_y
                 log.debug(f"Reset Capture: Base Y Range {cid}: {base_y}")
                 # Update individual scrollbar if axes are unlocked
                 if not self.y_axes_locked:
                      scrollbar = self.individual_y_scrollbars.get(cid)
                      if scrollbar: self._update_scrollbar_from_view(scrollbar, base_y, base_y)
             except Exception as e:
                 log.error(f"Reset Capture: Error getting Base Y Range for {cid}: {e}", exc_info=True)
                 # Ensure base range is None or removed if error occurs
                 if cid in self.base_y_ranges: del self.base_y_ranges[cid]
                 scrollbar = self.individual_y_scrollbars.get(cid)
                 if scrollbar: self._reset_scrollbar(scrollbar)


        # Update Global Y scrollbar if axes are locked
        if self.y_axes_locked:
             base_y_ref = self.base_y_ranges.get(first_cid)
             if base_y_ref:
                 self._update_scrollbar_from_view(self.global_y_scrollbar, base_y_ref, base_y_ref)
             else:
                 self._reset_scrollbar(self.global_y_scrollbar)
             # Reset individual scrollbars when locked
             for scrollbar in self.individual_y_scrollbars.values(): self._reset_scrollbar(scrollbar)
        else:
            # Reset global scrollbar when unlocked
            self._reset_scrollbar(self.global_y_scrollbar)


        log.debug("Base ranges captured and scrollbars updated after reset.")
        self._update_limit_fields() # Update fields with new auto ranges
        self._update_y_controls_visibility() # Re-evaluate enables based on new base ranges


    def _reset_all_sliders(self):
        """Resets X, Global Y, and all Individual Y sliders to the default (zoomed out) value."""
        log.debug("Resetting all zoom sliders to default.")
        all_sliders = [self.x_zoom_slider, self.global_y_slider] + list(self.individual_y_sliders.values())
        for slider in all_sliders:
            if slider: # Check if slider widget exists
                slider.blockSignals(True)
                slider.setValue(self.SLIDER_DEFAULT_VALUE)
                slider.blockSignals(False)

    def _reset_single_plot_view(self, chan_id: str):
        """Resets Y-axis zoom/pan for only one specific channel plot by auto-ranging it, respecting manual limits."""
        if self.manual_limits_enabled:
            log.debug(f"Ignoring reset single plot view for {chan_id} (Manual limits enabled).")
            return

        plot_item = self.channel_plots.get(chan_id)
        if not plot_item or not plot_item.isVisible() or not plot_item.getViewBox():
            log.debug(f"Ignoring reset single plot view for {chan_id}: Plot not found or not visible.")
            return

        log.debug(f"Resetting single plot Y-axis view for {chan_id} via auto-range.")
        vb = plot_item.getViewBox()
        vb.enableAutoRange(axis=pg.ViewBox.YAxis)

        # --- Update base range, slider, and scrollbar for this channel ---
        # Use a short timer to capture the range after auto-ranging completes
        QtCore.QTimer.singleShot(0, lambda: self._capture_single_base_range_after_reset(chan_id))


    def _capture_single_base_range_after_reset(self, chan_id: str):
        """Captures the Y range for a single plot after its view was reset."""
        plot_item = self.channel_plots.get(chan_id)
        if not plot_item or not plot_item.getViewBox() or not plot_item.isVisible():
             log.warning(f"Capture Single Base Range: Plot {chan_id} no longer valid/visible.")
             return

        log.debug(f"Capturing base Y range for single plot {chan_id} after reset.")
        vb = plot_item.getViewBox()
        new_y_range = None
        try:
            new_y_range = vb.viewRange()[1]
            self.base_y_ranges[chan_id] = new_y_range # Update the base range for this channel
            log.debug(f"Reset Single Capture: New base Y {chan_id}: {new_y_range}")
        except Exception as e:
            log.error(f"Reset Single Capture: Error getting Base Y Range for {chan_id}: {e}", exc_info=True)
            new_y_range = None # Ensure new_y_range is None if getting range failed
            if chan_id in self.base_y_ranges:
                del self.base_y_ranges[chan_id] # Remove base range if we couldn't update it

        # Reset the corresponding individual slider
        slider = self.individual_y_sliders.get(chan_id)
        if slider:
            slider.blockSignals(True); slider.setValue(self.SLIDER_DEFAULT_VALUE); slider.blockSignals(False)
            log.debug(f"Reset Single Capture: Slider for {chan_id} reset.")

        # Update the corresponding individual scrollbar
        scrollbar = self.individual_y_scrollbars.get(chan_id)
        if scrollbar:
            if new_y_range:
                self._update_scrollbar_from_view(scrollbar, new_y_range, new_y_range)
                log.debug(f"Reset Single Capture: Scrollbar for {chan_id} updated.")
            else:
                self._reset_scrollbar(scrollbar)
                log.debug(f"Reset Single Capture: Scrollbar for {chan_id} reset due to range error.")

        # If axes are locked, resetting one plot's Y affects all via auto-range linking?
        # No, Y axes are not linked. BUT resetting one might imply the user wants a general reset?
        # For now, let's assume resetting one only resets that one's base/slider/scroll.
        # If Y axes were locked, the global controls should reflect the state of the *first* visible plot.
        # We might need to update the global scrollbar if the reset channel *was* the first visible one.
        if self.y_axes_locked:
            first_visible_plot = next((p for p in self.channel_plots.values() if p.isVisible() and p.getViewBox()), None)
            if first_visible_plot and plot_item == first_visible_plot:
                # If the reset plot is the reference for the global scrollbar, update it
                first_cid = getattr(first_visible_plot.getViewBox(), '_synaptipy_chan_id', None)
                base_y_ref = self.base_y_ranges.get(first_cid)
                if base_y_ref:
                    self._update_scrollbar_from_view(self.global_y_scrollbar, base_y_ref, base_y_ref)
                    log.debug("Reset Single Capture: Global Y scrollbar updated as reset plot was reference.")
                else:
                    self._reset_scrollbar(self.global_y_scrollbar)
            # Resetting global slider too, as the relative zoom might be off now? Seems safest.
            self.global_y_slider.blockSignals(True)
            self.global_y_slider.setValue(self.SLIDER_DEFAULT_VALUE)
            self.global_y_slider.blockSignals(False)


        self._update_limit_fields() # Update text fields
        self._update_y_controls_visibility() # Update enables/visibility of controls

    # =========================================================================
    # Navigation & Export
    # =========================================================================
    def _next_trial(self):
        """Moves to the next trial in Cycle Single Trial mode."""
        if self.current_plot_mode == self.PlotMode.CYCLE_SINGLE and self.max_trials_current_recording > 0:
            if self.current_trial_index < self.max_trials_current_recording - 1:
                self.current_trial_index += 1
                log.debug(f"Navigated to next trial: {self.current_trial_index + 1}")
                self._update_plot()
                # Re-apply manual limits if they are enabled, as plot content changed
                if self.manual_limits_enabled:
                     self._apply_manual_limits()
                self._update_ui_state() # Update button enables
            else:
                log.debug("Already at the last trial.")
                self.statusBar.showMessage("Already at the last trial.", 2000)
        else:
            log.debug("Next trial ignored (not in cycle mode or no trials).")

    def _prev_trial(self):
        """Moves to the previous trial in Cycle Single Trial mode."""
        if self.current_plot_mode == self.PlotMode.CYCLE_SINGLE and self.max_trials_current_recording > 0:
            if self.current_trial_index > 0:
                self.current_trial_index -= 1
                log.debug(f"Navigated to previous trial: {self.current_trial_index + 1}")
                self._update_plot()
                 # Re-apply manual limits if they are enabled
                if self.manual_limits_enabled:
                     self._apply_manual_limits()
                self._update_ui_state() # Update button enables
            else:
                log.debug("Already at the first trial.")
                self.statusBar.showMessage("Already at the first trial.", 2000)
        else:
            log.debug("Previous trial ignored (not in cycle mode or no trials).")


    def _next_file_folder(self):
        """Loads the next file in the folder list."""
        if self.file_list and self.current_file_index < len(self.file_list) - 1:
            self.current_file_index += 1
            log.info(f"Navigating to next file (index {self.current_file_index}): {self.file_list[self.current_file_index].name}")
            self._load_and_display_file(self.file_list[self.current_file_index])
        else:
            log.debug("Next file ignored: Already at the last file in the folder list.")
            self.statusBar.showMessage("Already at the last file.", 2000)

    def _prev_file_folder(self):
        """Loads the previous file in the folder list."""
        if self.file_list and self.current_file_index > 0:
            self.current_file_index -= 1
            log.info(f"Navigating to previous file (index {self.current_file_index}): {self.file_list[self.current_file_index].name}")
            self._load_and_display_file(self.file_list[self.current_file_index])
        else:
            log.debug("Previous file ignored: Already at the first file in the folder list.")
            self.statusBar.showMessage("Already at the first file.", 2000)

    # =========================================================================
    # Export NWB (METHOD WITH SYNTAX FIX APPLIED AND REFINED)
    # =========================================================================
    def _export_to_nwb(self):
        """Handles exporting the current recording to an NWB file."""
        if not self.current_recording:
            QtWidgets.QMessageBox.warning(self, "Export Error", "No recording data loaded to export.")
            return

        # --- Suggest Filename ---
        # Default based on source file, replacing extension with .nwb
        default_filename = self.current_recording.source_file.with_suffix(".nwb").name

        # --- Get Save Location ---
        settings = QtCore.QSettings("Synaptipy", "Viewer")
        last_export_dir = settings.value("lastExportDirectory", str(self.current_recording.source_file.parent), type=str)

        output_filepath_str, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Save NWB File", dir=os.path.join(last_export_dir, default_filename), filter="NWB Files (*.nwb)"
        )

        if not output_filepath_str:
            log.info("NWB export cancelled by user.")
            self.statusBar.showMessage("NWB export cancelled.", 3000)
            return

        output_filepath = Path(output_filepath_str)
        # Save the chosen directory for next time
        settings.setValue("lastExportDirectory", str(output_filepath.parent))


        # --- Prepare Metadata for Dialog ---
        # Generate a default identifier
        default_identifier = str(uuid.uuid4())
        # Get start time from recording, default to now if unavailable
        default_start_time_naive = self.current_recording.session_start_time_dt or datetime.now()

        # Ensure start time is timezone-aware for the dialog
        if default_start_time_naive.tzinfo is None:
            log.warning("Recording start time is timezone-naive. Attempting to determine local timezone for NWB export dialog.")
            aware_start_time = timezone.utc # Default fallback
            if tzlocal:
                try:
                    local_tz = tzlocal.get_localzone()
                    # Make the naive time aware using the determined local timezone
                    aware_start_time = default_start_time_naive.replace(tzinfo=local_tz)
                    log.debug(f"Using local timezone from tzlocal: {local_tz}")
                except Exception as e:
                    log.warning(f"Failed to get local timezone using tzlocal: {e}. Defaulting NWB start time to UTC.", exc_info=True)
                    # Fallback: make naive time aware using UTC
                    aware_start_time = default_start_time_naive.replace(tzinfo=timezone.utc)
            else:
                 log.debug("tzlocal not found. Defaulting NWB start time to UTC.")
                 aware_start_time = default_start_time_naive.replace(tzinfo=timezone.utc)
        else:
             # Time from recording is already aware
             aware_start_time = default_start_time_naive


        # --- Show Metadata Dialog ---
        dialog = NwbMetadataDialog(default_identifier, aware_start_time, self)
        if dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            nwb_metadata = dialog.get_metadata()
            if nwb_metadata is None: # Should be caught by dialog validation, but check again
                log.error("Metadata dialog accepted but returned None.")
                self.statusBar.showMessage("Metadata validation failed.", 3000)
                return
            log.debug(f"NWB metadata collected: {nwb_metadata}")
        else:
            log.info("NWB export cancelled during metadata input.")
            self.statusBar.showMessage("NWB export cancelled.", 3000)
            return

        # --- Perform Export ---
        self.statusBar.showMessage(f"Exporting NWB to '{output_filepath.name}'...")
        QtWidgets.QApplication.processEvents() # Keep UI responsive

        try:
            self.nwb_exporter.export(self.current_recording, output_filepath, nwb_metadata)
            log.info(f"Successfully exported NWB file: {output_filepath}")
            self.statusBar.showMessage(f"Export successful: {output_filepath.name}", 5000)
            QtWidgets.QMessageBox.information(self, "Export Successful", f"Data successfully saved to:\n{output_filepath}")
        except (ValueError, ExportError, SynaptipyError) as e:
            # Handle known Synaptipy/export errors
            log.error(f"NWB Export failed: {e}", exc_info=False)
            self.statusBar.showMessage(f"NWB Export failed: {e}", 5000)
            QtWidgets.QMessageBox.critical(self, "NWB Export Error", f"Failed to export NWB file:\n{e}")
        except Exception as e:
            # Handle unexpected errors during export
            log.error(f"An unexpected error occurred during NWB Export: {e}", exc_info=True)
            self.statusBar.showMessage("Unexpected NWB Export error occurred.", 5000)
            QtWidgets.QMessageBox.critical(self, "NWB Export Error", f"An unexpected error occurred during export:\n{e}")


    # =========================================================================
    # Multi-Trial Selection & Averaging
    # =========================================================================
    def _update_selected_trials_display(self):
        """Updates the label showing which trials are selected for averaging."""
        if not self.selected_trial_indices:
            self.selected_trials_display.setText("Selected: None")
        else:
            # Sort indices and convert to 1-based for display
            sorted_indices_1_based = sorted([i + 1 for i in self.selected_trial_indices])
            # Create a concise representation (e.g., "1, 2, 5-7, 10") - Optional enhancement
            # For now, just list them
            text = "Selected: " + ", ".join(map(str, sorted_indices_1_based))
            self.selected_trials_display.setText(text)
            self.selected_trials_display.setToolTip(text) # Show full list on hover if long

    def _toggle_select_current_trial(self):
        """Adds or removes the currently viewed trial (in Cycle mode) from the averaging set."""
        if not self.current_recording or self.current_plot_mode != self.PlotMode.CYCLE_SINGLE:
            log.debug("Toggle select trial ignored: Not in cycle mode or no data.")
            return
        if not (0 <= self.current_trial_index < self.max_trials_current_recording):
            log.warning(f"Toggle select trial ignored: Invalid current trial index {self.current_trial_index}.")
            return

        current_idx_0_based = self.current_trial_index

        action_message = ""
        if current_idx_0_based in self.selected_trial_indices:
            self.selected_trial_indices.remove(current_idx_0_based)
            action_message = f"Trial {current_idx_0_based + 1} removed from averaging set."
            log.debug(action_message)
        else:
            self.selected_trial_indices.add(current_idx_0_based)
            action_message = f"Trial {current_idx_0_based + 1} added to averaging set."
            log.debug(action_message)

        self.statusBar.showMessage(action_message, 2000)

        # If the average plot was visible, remove it as the selection has changed
        if self.selected_average_plot_items:
            log.debug("Selection changed, removing previously plotted average.")
            self._remove_selected_average_plots()
            # Reset button state without triggering signal
            self.show_selected_average_button.blockSignals(True)
            self.show_selected_average_button.setChecked(False)
            self.show_selected_average_button.blockSignals(False)

        # Update UI
        self._update_selected_trials_display()
        self._update_ui_state() # Update button text/enables

    def _clear_avg_selection(self):
        """Clears the set of selected trials."""
        if not self.selected_trial_indices:
            log.debug("Clear selection called, but no trials were selected.")
            return

        log.debug("Clearing trial selection for averaging.")
        # Remove the average plot if it's currently shown
        if self.selected_average_plot_items:
            self._remove_selected_average_plots()
            # Reset button state without triggering signal
            self.show_selected_average_button.blockSignals(True)
            self.show_selected_average_button.setChecked(False)
            self.show_selected_average_button.blockSignals(False)

        self.selected_trial_indices.clear()
        self.statusBar.showMessage("Trial selection cleared.", 2000)

        # Update UI
        self._update_selected_trials_display()
        self._update_ui_state()

    def _toggle_plot_selected_average(self, checked: bool):
        """Slot connected to the 'Plot Selected Avg' button's toggled signal."""
        log.debug(f"Toggle plot selected average called. Checked state: {checked}")
        if checked:
            # Button is checked -> try to plot
            self._plot_selected_average()
        else:
            # Button is unchecked -> remove plot
            self._remove_selected_average_plots()
        # Update button text/tooltips
        self._update_ui_state()

    def _plot_selected_average(self):
        """Calculates and plots the average of the selected trials as an overlay."""
        if not self.selected_trial_indices or not self.current_recording:
            log.warning("Plot selected average called, but no trials selected or no data loaded.")
            # Ensure button state is correct if called erroneously
            self.show_selected_average_button.blockSignals(True)
            self.show_selected_average_button.setChecked(False)
            self.show_selected_average_button.blockSignals(False)
            self._update_ui_state()
            return

        if self.selected_average_plot_items:
            log.debug("Selected average plot already exists. Not replotting.")
            # Ensure button stays checked
            self.show_selected_average_button.blockSignals(True)
            self.show_selected_average_button.setChecked(True)
            self.show_selected_average_button.blockSignals(False)
            return

        sorted_indices = sorted(list(self.selected_trial_indices))
        log.info(f"Plotting average of selected trials (0-based indices): {sorted_indices}")

        plotted_anything = False
        reference_time_vector = None
        reference_channel_id = None

        # --- Find a reliable reference time vector from the first selected trial ---
        # Iterate through visible channels first to find one with valid data for the first selected trial
        first_selected_idx = sorted_indices[0]
        for cid, plot_item in self.channel_plots.items():
             if plot_item.isVisible():
                 channel = self.current_recording.channels.get(cid)
                 if channel and 0 <= first_selected_idx < channel.num_trials:
                     try:
                         tvec_candidate = channel.get_relative_time_vector(first_selected_idx)
                         if tvec_candidate is not None and len(tvec_candidate) > 0:
                             reference_time_vector = tvec_candidate
                             reference_channel_id = cid
                             log.debug(f"Using time vector from channel {cid}, trial {first_selected_idx+1} as reference (length {len(reference_time_vector)}).")
                             break # Found a valid reference vector
                     except Exception as e:
                         log.warning(f"Error getting time vector for reference: Channel {cid}, Trial {first_selected_idx+1}. Error: {e}")
        # Check if we found a reference time vector
        if reference_time_vector is None:
             log.error("Could not find a valid reference time vector from selected trials and visible channels.")
             QtWidgets.QMessageBox.warning(self, "Averaging Error", "Could not obtain a valid time vector to calculate the average.")
             self.show_selected_average_button.blockSignals(True); self.show_selected_average_button.setChecked(False); self.show_selected_average_button.blockSignals(False)
             self._update_ui_state()
             return

        # --- Calculate and plot average for each visible channel ---
        ds_threshold = VisConstants.DOWNSAMPLING_THRESHOLD if VisConstants else 5000
        enable_downsampling = self.downsample_checkbox.isChecked()
        ref_len = len(reference_time_vector)

        for cid, plot_item in self.channel_plots.items():
            if plot_item.isVisible():
                channel = self.current_recording.channels.get(cid)
                if not channel: continue

                valid_data_for_avg = []
                # Collect data from selected trials for this channel, ensuring matching length
                for trial_idx in sorted_indices:
                    if 0 <= trial_idx < channel.num_trials:
                        try:
                            data = channel.get_data(trial_idx)
                            # Check data validity and length against reference
                            if data is not None and len(data) == ref_len:
                                valid_data_for_avg.append(data)
                            elif data is not None:
                                log.warning(f"Length mismatch for avg: Ch {cid}, Trial {trial_idx+1} (len {len(data)}) vs Ref (len {ref_len}). Skipping trial.")
                            # else: data is None, implicitly skipped
                        except Exception as e:
                            log.error(f"Error getting data for avg: Ch {cid}, Trial {trial_idx+1}. Error: {e}")
                    else:
                         log.warning(f"Selected trial index {trial_idx+1} out of range for Ch {cid} (Num trials: {channel.num_trials}).")


                # Calculate and plot average if we have valid data
                if valid_data_for_avg:
                    try:
                        # Convert list of arrays to a 2D numpy array for averaging
                        data_array = np.array(valid_data_for_avg)
                        averaged_data = np.mean(data_array, axis=0)

                        # Plot the average using the special pen
                        avg_data_item = plot_item.plot(reference_time_vector, averaged_data, pen=self.SELECTED_AVG_PEN)
                        avg_data_item.opts['autoDownsample'] = enable_downsampling
                        avg_data_item.opts['autoDownsampleThreshold'] = ds_threshold if enable_downsampling else 0

                        # Store the plotted item
                        self.selected_average_plot_items[cid] = avg_data_item
                        plotted_anything = True
                        log.debug(f"Plotted selected average for channel {cid} using {len(valid_data_for_avg)} trials.")

                    except Exception as e:
                        log.error(f"Error calculating or plotting average for channel {cid}: {e}", exc_info=True)
                        # Clean up if plot failed mid-way for this channel? Maybe not necessary.
                else:
                    log.warning(f"No valid data found to average for channel {cid} among selected trials.")

        # --- Final checks and updates ---
        if not plotted_anything:
             log.warning("Failed to plot selected average for any visible channel.")
             QtWidgets.QMessageBox.warning(self, "Averaging Warning", "Could not plot average for any visible channel. Check data validity and selection.")
             # Ensure button state is correct
             self.show_selected_average_button.blockSignals(True); self.show_selected_average_button.setChecked(False); self.show_selected_average_button.blockSignals(False)
        else:
             self.statusBar.showMessage(f"Plotted average of {len(self.selected_trial_indices)} selected trials.", 2500)

        self._update_ui_state() # Update button text etc.


    def _remove_selected_average_plots(self):
        """Removes any plotted selected average traces from all plots."""
        if not self.selected_average_plot_items:
            return # Nothing to remove

        log.debug(f"Removing {len(self.selected_average_plot_items)} selected average plot item(s).")
        removed_count = 0
        for cid, avg_data_item in list(self.selected_average_plot_items.items()): # Iterate over copy
            plot_item = self.channel_plots.get(cid)
            if plot_item and avg_data_item in plot_item.items:
                try:
                    plot_item.removeItem(avg_data_item)
                    removed_count += 1
                except Exception as e:
                    # Might happen if item already removed elsewhere, log warning
                    log.warning(f"Could not remove selected average item from plot {cid}: {e}")
            # Remove from our tracking dictionary regardless of successful removal from plot
            del self.selected_average_plot_items[cid]

        if removed_count > 0:
            log.debug(f"Successfully removed {removed_count} average plot items.")
            self.statusBar.showMessage("Selected average overlay hidden.", 2000)
        # Update UI state after removal (e.g., button text)
        self._update_ui_state()

    # =========================================================================
    # Manual Limits
    # =========================================================================
    def _parse_limit_value(self, text: str) -> Optional[float]:
        """Safely parses text from a QLineEdit into a float, returns None if invalid or 'Auto'."""
        if not text or text.strip().lower() == "auto":
            return None
        try:
            return float(text.strip())
        except ValueError:
            log.warning(f"Could not parse '{text}' as a valid float limit.")
            return None

    def _on_set_limits_clicked(self):
        """Reads values from the limit QLineEdits and stores them if valid."""
        log.debug("Set Manual Limits button clicked. Parsing values from fields.")
        if not all([self.manual_limit_x_min_edit, self.manual_limit_x_max_edit,
                    self.manual_limit_y_min_edit, self.manual_limit_y_max_edit]):
             log.error("Manual limit LineEdit widgets not found.")
             return

        # Parse values
        x_min = self._parse_limit_value(self.manual_limit_x_min_edit.text())
        x_max = self._parse_limit_value(self.manual_limit_x_max_edit.text())
        y_min = self._parse_limit_value(self.manual_limit_y_min_edit.text())
        y_max = self._parse_limit_value(self.manual_limit_y_max_edit.text())

        valid_x_set = False
        valid_y_set = False

        # Validate and store X limits (require both min and max)
        if x_min is not None and x_max is not None:
            if x_min < x_max:
                self.manual_x_limits = (x_min, x_max)
                valid_x_set = True
                log.info(f"Manual X limits stored: {self.manual_x_limits}")
            else:
                QtWidgets.QMessageBox.warning(self, "Input Error", "X Min must be less than X Max.")
                self.manual_x_limits = None # Invalidate if order is wrong
        elif x_min is not None or x_max is not None:
             QtWidgets.QMessageBox.warning(self, "Input Error", "Both X Min and X Max must be provided to set manual X limits.")
             self.manual_x_limits = None # Invalidate if only one is provided
        else:
             self.manual_x_limits = None # Store None if both were empty/Auto
             log.info("Manual X limits cleared (set to Auto).")

        # Validate and store Y limits (require both min and max)
        if y_min is not None and y_max is not None:
            if y_min < y_max:
                self.manual_y_limits = (y_min, y_max)
                valid_y_set = True
                log.info(f"Manual Y limits stored: {self.manual_y_limits}")
            else:
                QtWidgets.QMessageBox.warning(self, "Input Error", "Y Min must be less than Y Max.")
                self.manual_y_limits = None # Invalidate if order is wrong
        elif y_min is not None or y_max is not None:
             QtWidgets.QMessageBox.warning(self, "Input Error", "Both Y Min and Y Max must be provided to set manual Y limits.")
             self.manual_y_limits = None # Invalidate if only one is provided
        else:
             self.manual_y_limits = None # Store None if both were empty/Auto
             log.info("Manual Y limits cleared (set to Auto).")


        # Provide feedback and apply if enabled
        if valid_x_set or valid_y_set:
            self.statusBar.showMessage("Manual limits stored successfully.", 3000)
            # If manual limits are already enabled, apply the newly set ones immediately
            if self.manual_limits_enabled:
                log.debug("Manual limits were enabled, applying newly set limits now.")
                self._apply_manual_limits()
        elif self.manual_x_limits is None and self.manual_y_limits is None and (x_min is None and x_max is None and y_min is None and y_max is None) :
             # Case where user explicitly set all fields to Auto/empty
             self.statusBar.showMessage("Manual limits set to Auto.", 3000)
             if self.manual_limits_enabled:
                  log.debug("Manual limits were enabled but set to Auto. Disabling and resetting view.")
                  # Uncheck the box, which will trigger _on_manual_limits_toggled(False) -> reset view
                  self.enable_manual_limits_checkbox.setChecked(False)

        else:
             # Handles cases where validation failed (min >= max or only one provided)
             self.statusBar.showMessage("Invalid or incomplete limits entered.", 3000)
             # Do not apply if invalid

    def _on_manual_limits_toggled(self, checked: bool):
        """Handles the 'Enable Manual Limits' checkbox state change."""
        self.manual_limits_enabled = checked
        state_text = "ENABLED" if checked else "DISABLED"
        log.info(f"Manual plot limits toggled: {state_text}")
        self.statusBar.showMessage(f"Manual plot limits {state_text}.", 2000)

        if checked: # Enabling manual limits
            # Check if limits have actually been set
            if self.manual_x_limits is None and self.manual_y_limits is None:
                log.debug("Attempting to enable manual limits, but no limits are stored. Trying to set from fields.")
                # Try to populate limits from fields first
                self._on_set_limits_clicked()
                # Check again if limits were successfully stored
                if self.manual_x_limits is None and self.manual_y_limits is None:
                    log.warning("Failed to enable manual limits: No valid limits set or stored.")
                    QtWidgets.QMessageBox.warning(self, "Enable Failed", "Cannot enable manual limits because no valid limits have been set using the fields below.")
                    # Uncheck the box programmatically without triggering signal again
                    self.enable_manual_limits_checkbox.blockSignals(True)
                    self.enable_manual_limits_checkbox.setChecked(False)
                    self.enable_manual_limits_checkbox.blockSignals(False)
                    self.manual_limits_enabled = False # Ensure state reflects failure
                    return # Abort enabling process

            # If we have limits (either pre-stored or just set), apply them
            self._apply_manual_limits()

        else: # Disabling manual limits
            # Enable zoom/scroll controls BEFORE resetting the view
            self._update_zoom_scroll_enable_state()
            log.debug("Manual limits disabled. Resetting view to auto-range.")
            self._reset_view() # Go back to auto-ranging

        self._update_ui_state() # Update button enables etc.


    def _apply_manual_limits(self):
        """Applies the stored manual X and Y limits to all visible plots."""
        if not self.manual_limits_enabled:
             log.warning("Apply manual limits called but feature is not enabled.")
             return

        if self.manual_x_limits is None and self.manual_y_limits is None:
             log.warning("Apply manual limits called but no limits are stored.")
             # Maybe disable the feature? Or just do nothing. Doing nothing seems safer.
             return

        log.debug(f"Applying manual limits - X: {self.manual_x_limits}, Y: {self.manual_y_limits}")
        applied_x = False
        applied_y = False
        self._updating_viewranges = True # Prevent range change signals from interfering
        try:
            for plot_item in self.channel_plots.values():
                if plot_item.isVisible() and plot_item.getViewBox():
                    vb = plot_item.getViewBox()
                    # Disable auto-ranging explicitly when setting manual limits
                    vb.disableAutoRange()

                    if self.manual_x_limits:
                        vb.setXRange(self.manual_x_limits[0], self.manual_x_limits[1], padding=0)
                        applied_x = True
                    # Apply Y limits if they exist (could apply X only or Y only)
                    if self.manual_y_limits:
                        vb.setYRange(self.manual_y_limits[0], self.manual_y_limits[1], padding=0)
                        applied_y = True
        except Exception as e:
             log.error(f"Error applying manual limits: {e}", exc_info=True)
        finally:
            self._updating_viewranges = False # Release lock

        if applied_x or applied_y:
            log.debug("Manual limits applied successfully.")
            # Update the display fields to reflect the applied limits
            self._update_limit_fields()
            # Update scrollbars to reflect the fixed view (effectively disabling them)
            # If X limits applied, update X scrollbar (will likely set range=0)
            if applied_x and self.manual_x_limits:
                 self._update_scrollbar_from_view(self.x_scrollbar, self.manual_x_limits, self.manual_x_limits)
            # If Y limits applied, update all Y scrollbars
            if applied_y and self.manual_y_limits:
                 self._update_scrollbar_from_view(self.global_y_scrollbar, self.manual_y_limits, self.manual_y_limits)
                 for scrollbar in self.individual_y_scrollbars.values():
                      self._update_scrollbar_from_view(scrollbar, self.manual_y_limits, self.manual_y_limits)
        else:
             log.warning("Attempted to apply manual limits, but no valid limits were applied.")


        # Disable zoom/scroll controls after applying limits
        self._update_zoom_scroll_enable_state()


    def _update_zoom_scroll_enable_state(self):
        """Enables or disables zoom/scroll widgets and mouse interaction based on manual_limits_enabled."""
        enable_controls = not self.manual_limits_enabled
        log.debug(f"Updating zoom/scroll control enabled state: {'ENABLED' if enable_controls else 'DISABLED'}")

        # Sliders
        self.x_zoom_slider.setEnabled(enable_controls)
        # Y sliders depend on lock state as well
        self.global_y_slider.setEnabled(enable_controls and self.y_axes_locked)
        for slider in self.individual_y_sliders.values():
            slider.setEnabled(enable_controls and not self.y_axes_locked)

        # Scrollbars are enabled/disabled by _update_scrollbar_from_view or _reset_scrollbar
        # If controls are disabled (manual limits ON), ensure scrollbars are reset/disabled
        if not enable_controls:
             self._reset_scrollbar(self.x_scrollbar)
             self._reset_scrollbar(self.global_y_scrollbar)
             for sb in self.individual_y_scrollbars.values():
                  self._reset_scrollbar(sb)
        # If controls are enabled (manual limits OFF), scrollbar state will be updated by view changes/resets.

        # Plot Mouse Interaction
        for plot_item in self.channel_plots.values():
             if plot_item and plot_item.getViewBox():
                 # Disable both X and Y mouse interaction if limits are manual
                 plot_item.getViewBox().setMouseEnabled(x=enable_controls, y=enable_controls)

        # Reset View Button (always enabled if plots visible, unless manual limits ON?)
        # Let's make ResetView disabled when manual limits are ON, as it applies limits instead.
        has_visible_plots = any(p.isVisible() for p in self.channel_plots.values())
        self.reset_view_button.setEnabled(has_visible_plots and enable_controls)


    def _update_limit_fields(self):
        """Updates the QLineEdit fields showing current or manual limits."""
        if self._updating_limit_fields: return # Prevent recursive updates
        if not all([self.manual_limit_x_min_edit, self.manual_limit_x_max_edit,
                    self.manual_limit_y_min_edit, self.manual_limit_y_max_edit]):
             # Widgets might not be ready during initial setup
             # log.debug("Limit fields not yet available for update.")
             return

        x_min_txt, x_max_txt = "Auto", "Auto"
        y_min_txt, y_max_txt = "Auto", "Auto"

        if self.manual_limits_enabled:
             # If enabled, show the stored manual limits (or "Auto" if not set)
             if self.manual_x_limits:
                 x_min_txt = f"{self.manual_x_limits[0]:.4g}"
                 x_max_txt = f"{self.manual_x_limits[1]:.4g}"
             if self.manual_y_limits:
                 y_min_txt = f"{self.manual_y_limits[0]:.4g}"
                 y_max_txt = f"{self.manual_y_limits[1]:.4g}"
        else:
             # If disabled, show the current view range of the first visible plot
             first_visible_plot = next((p for p in self.channel_plots.values() if p.isVisible() and p.getViewBox()), None)
             if first_visible_plot:
                 try:
                     vb = first_visible_plot.getViewBox()
                     x_range = vb.viewRange()[0]
                     y_range = vb.viewRange()[1]
                     x_min_txt = f"{x_range[0]:.4g}"
                     x_max_txt = f"{x_range[1]:.4g}"
                     y_min_txt = f"{y_range[0]:.4g}"
                     y_max_txt = f"{y_range[1]:.4g}"
                 except Exception as e:
                     log.warning(f"Error getting view range for limit fields update: {e}")
                     x_min_txt, x_max_txt = "Error", "Error"
                     y_min_txt, y_max_txt = "Error", "Error"
             # else: No visible plot, keep "Auto"

        # Update the QLineEdit text, preventing feedback loops
        self._updating_limit_fields = True
        try:
            self.manual_limit_x_min_edit.setText(x_min_txt)
            self.manual_limit_x_max_edit.setText(x_max_txt)
            self.manual_limit_y_min_edit.setText(y_min_txt)
            self.manual_limit_y_max_edit.setText(y_max_txt)
        finally:
            self._updating_limit_fields = False

    def _trigger_limit_field_update(self):
        """Intermediate slot connected to ViewBox range changes to trigger a delayed update of limit fields."""
        # Only update fields if manual limits are OFF and we're not already in the process
        if not self.manual_limits_enabled and not self._updating_limit_fields:
            # Use a short delay (e.g., 50ms) to avoid excessive updates during mouse drag/zoom
            QtCore.QTimer.singleShot(50, self._update_limit_fields)

    # =========================================================================
    # Close Event
    # =========================================================================
    def closeEvent(self, event: QtGui.QCloseEvent):
        """Handles the main window close event."""
        log.info("Close event received. Cleaning up...")
        # Perform any necessary cleanup here, e.g., stopping threads, saving state

        # Clear graphics layout (helps release resources)
        try:
             if hasattr(self, 'graphics_layout_widget') and self.graphics_layout_widget:
                 self.graphics_layout_widget.clear()
                 log.debug("Cleared graphics layout widget.")
        except Exception as e:
             log.warning(f"Error clearing graphics layout during close: {e}")

        # Save settings (like last directory)
        try:
             settings = QtCore.QSettings("Synaptipy", "Viewer")
             # Example: Save window geometry
             settings.setValue("geometry", self.saveGeometry())
             settings.setValue("windowState", self.saveState())
             log.debug("Saved window geometry and state.")
        except Exception as e:
            log.warning(f"Could not save settings on close: {e}")


        log.info("Accepting close event.")
        event.accept() # Allow the window to close
# --- MainWindow Class --- END ---


# --- Main Execution Block ---
if __name__ == '__main__':
    # Configure logging (basic setup here, might be overridden by Synaptipy)
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s'
    logging.basicConfig(level=logging.DEBUG, format=log_format) # Set level to DEBUG for detailed output

    log.info(f"Application starting... Synaptipy Available: {SYNAPTIPY_AVAILABLE}")
    if not SYNAPTIPY_AVAILABLE:
        log.warning("*"*30 + "\n Running with DUMMY Synaptipy classes! \n" + "*"*30)

    # Create Qt Application
    # Set High DPI scaling attribute BEFORE creating QApplication
    # QtWidgets.QApplication.setAttribute(QtCore.Qt.ApplicationAttribute.AA_EnableHighDpiScaling, True)
    # QtWidgets.QApplication.setAttribute(QtCore.Qt.ApplicationAttribute.AA_UseHighDpiPixmaps, True)
    app = QtWidgets.QApplication(sys.argv)


    # Apply Dark Theme (Optional)
    style = None
    try:
        import qdarkstyle
        # Check for preferred API style functions
        if hasattr(qdarkstyle, 'load_stylesheet'): # Generic loader often works
            style = qdarkstyle.load_stylesheet(qt_api='pyside6')
        elif hasattr(qdarkstyle, 'load_stylesheet_pyside6'): # Specific loader
             style = qdarkstyle.load_stylesheet_pyside6()

        if style:
            app.setStyleSheet(style)
            log.info("Applied qdarkstyle theme.")
            # Optional: Set pyqtgraph foreground based on theme (if needed)
            # pg.setConfigOption('foreground', 'w') # Example for dark theme
        else:
             log.warning("qdarkstyle module found but no suitable load_stylesheet function detected.")
    except ImportError:
        log.info("qdarkstyle not found, using default system style.")
    except Exception as e:
        log.warning(f"Could not apply qdarkstyle theme: {e}")

    # Restore Window Geometry
    settings = QtCore.QSettings("Synaptipy", "Viewer")

    # Create and Show Main Window
    try:
        window = MainWindow()
        # Restore geometry if saved
        geom = settings.value("geometry", None, type=QtCore.QByteArray)
        if geom: window.restoreGeometry(geom)
        state = settings.value("windowState", None, type=QtCore.QByteArray)
        if state: window.restoreState(state)

        window.show()
        log.info("Main window created and shown.")
    except Exception as e:
        log.critical(f"Failed to initialize or show the MainWindow: {e}", exc_info=True)
        # Attempt to show message box even if main window failed
        try:
            QtWidgets.QMessageBox.critical(None, "Application Startup Error", f"Failed to create main window:\n{e}\n\nSee logs for details.")
        except Exception: pass # Ignore if even message box fails
        sys.exit(1) # Exit if main window fails

    # Start Qt Event Loop
    log.info("Starting Qt event loop...")
    sys.exit(app.exec())
