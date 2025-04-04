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
    from Synaptipy.core.data_model import Recording, Channel
    from Synaptipy.infrastructure.file_readers import NeoAdapter
    from Synaptipy.infrastructure.exporters import NWBExporter
    from Synaptipy.shared import constants as VisConstants # Use alias
    from Synaptipy.shared.error_handling import (
        FileReadError, UnsupportedFormatError, ExportError, SynaptipyError)
    SYNAPTIPY_AVAILABLE = True
except ImportError:
    print("Warning: Synaptipy modules not found. Using dummy implementations.")
    SYNAPTIPY_AVAILABLE = False
    # Define placeholders so the rest of the script doesn't immediately crash
    # The actual dummy definitions are below, BEFORE MainWindow
    NeoAdapter, NWBExporter, Recording, Channel = None, None, None, None
    VisConstants, SynaptipyError, FileReadError = None, None, None
    UnsupportedFormatError, ExportError = None, None

# --- Configure Logging ---
log = logging.getLogger(__name__)

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
                 min_len = min(len(d) for d in self.data) if self.data else self._num_samples
                 return self.tvecs[0][:min_len]
            else: return None

    class DummyRecording:
        def __init__(self, filepath, num_channels=3):
            self.source_file = Path(filepath); self.sampling_rate = 10000.0; self.duration = 2.0
            self.num_channels = num_channels; self.max_trials = 10
            ch_ids = [f'Ch{i+1:02d}' for i in range(num_channels)]
            self.channels = { ch_ids[i]: DummyChannel(id=ch_ids[i], name=f'Channel {i+1}', units='pA' if i % 2 == 0 else 'mV', num_trials=self.max_trials, duration=self.duration, rate=self.sampling_rate) for i in range(num_channels)}
            self.session_start_time_dt = datetime.now()

    class DummyNeoAdapter:
        def get_supported_file_filter(self): return "Dummy Files (*.dummy);;All Files (*)"
        def read_recording(self, filepath):
            log.info(f"DummyNeoAdapter: Simulating read for {filepath}")
            if not Path(filepath).exists():
                try: Path(filepath).touch()
                except Exception as e: log.warning(f"Could not create dummy file {filepath}: {e}")
            if '5ch' in filepath.name.lower(): num_chan = 5
            elif '1ch' in filepath.name.lower(): num_chan = 1
            else: num_chan = 3
            log.debug(f"DummyNeoAdapter: Creating recording with {num_chan} channels.")
            return DummyRecording(filepath, num_channels=num_chan)

    class DummyNWBExporter:
        def export(self, recording, output_path, metadata):
            log.info(f"DummyNWBExporter: Simulating export of '{recording.source_file.name}' to {output_path} with metadata {metadata}")

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
    VisConstants = DummyVisConstants
    SynaptipyError, FileReadError, UnsupportedFormatError, ExportError = DummyErrors()
# --- End Dummy Class Definitions ---


# --- NWB Metadata Dialog ---
class NwbMetadataDialog(QtWidgets.QDialog):
    def __init__(self, default_identifier, default_start_time, parent=None):
        super().__init__(parent); self.setWindowTitle("NWB Session Metadata"); self.setModal(True)
        self.layout = QtWidgets.QFormLayout(self)
        self.session_description = QtWidgets.QLineEdit("Session description..."); self.identifier = QtWidgets.QLineEdit(default_identifier)
        self.session_start_time_edit = QtWidgets.QDateTimeEdit(default_start_time); self.session_start_time_edit.setCalendarPopup(True); self.session_start_time_edit.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        self.experimenter = QtWidgets.QLineEdit(""); self.lab = QtWidgets.QLineEdit(""); self.institution = QtWidgets.QLineEdit(""); self.session_id = QtWidgets.QLineEdit("")
        self.layout.addRow("Description*:", self.session_description); self.layout.addRow("Identifier*:", self.identifier); self.layout.addRow("Start Time*:", self.session_start_time_edit)
        self.layout.addRow("Experimenter:", self.experimenter); self.layout.addRow("Lab:", self.lab); self.layout.addRow("Institution:", self.institution); self.layout.addRow("Session ID:", self.session_id)
        self.layout.addRow(QtWidgets.QLabel("* Required fields"))
        self.button_box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel); self.button_box.accepted.connect(self.accept); self.button_box.rejected.connect(self.reject)
        self.layout.addRow(self.button_box)
    def get_metadata(self) -> Optional[Dict]:
        desc = self.session_description.text().strip(); ident = self.identifier.text().strip(); start_time = self.session_start_time_edit.dateTime().toPython();
        if not desc or not ident:
            QtWidgets.QMessageBox.warning(self, "Input Error", "Session Description and Identifier are required.")
            return None
        # Ensure timezone info for start_time if missing
        if start_time.tzinfo is None:
             try: local_tz = tzlocal.get_localzone() if tzlocal else timezone.utc
             except Exception: local_tz = timezone.utc
             start_time = start_time.replace(tzinfo=local_tz)
        return {"session_description": desc, "identifier": ident, "session_start_time": start_time, "experimenter": self.experimenter.text().strip() or None, "lab": self.lab.text().strip() or None, "institution": self.institution.text().strip() or None, "session_id": self.session_id.text().strip() or None}
# --- NwbMetadataDialog End ---


# --- MainWindow Class ---
class MainWindow(QtWidgets.QMainWindow):
    """Main application window with multi-panel plotting and trial modes."""
    class PlotMode: OVERLAY_AVG = 0; CYCLE_SINGLE = 1
    SLIDER_RANGE_MIN = 1; SLIDER_RANGE_MAX = 100
    SLIDER_DEFAULT_VALUE = SLIDER_RANGE_MIN
    MIN_ZOOM_FACTOR = 0.01; SCROLLBAR_MAX_RANGE = 10000
    # Use VisConstants only if it was successfully defined (real or dummy)
    SELECTED_AVG_PEN = pg.mkPen('#00FF00', width=(VisConstants.DEFAULT_PLOT_PEN_WIDTH + 1) if VisConstants else 2) if VisConstants else pg.mkPen('g', width=2)

    def __init__(self):
        super().__init__(); self.setWindowTitle("Synaptipy"); self.setGeometry(50, 50, 1700, 950)

        # --- Instantiate Adapters/Exporters ---
        try:
             self.neo_adapter = NeoAdapter()
             self.nwb_exporter = NWBExporter()
        except Exception as e:
             log.critical(f"Failed to instantiate NeoAdapter or NWBExporter: {e}", exc_info=True)
             QtWidgets.QMessageBox.critical(self, "Initialization Error", f"Failed to initialize core components:\n{e}")
             sys.exit(1)

        # --- Initialize State Variables ---
        self.current_recording: Optional[Recording] = None; self.file_list: List[Path] = []; self.current_file_index: int = -1
        self.channel_checkboxes: Dict[str, QtWidgets.QCheckBox] = {}; self.channel_plots: Dict[str, pg.PlotItem] = {}
        self.channel_plot_data_items: Dict[str, List[pg.PlotDataItem]] = {}
        self.current_plot_mode: int = self.PlotMode.OVERLAY_AVG; self.current_trial_index: int = 0; self.max_trials_current_recording: int = 0

        # Zoom/Scroll State
        self.y_axes_locked: bool = True
        self.base_x_range: Optional[Tuple[float, float]] = None
        self.base_y_ranges: Dict[str, Optional[Tuple[float, float]]] = {}
        self.individual_y_sliders: Dict[str, QtWidgets.QSlider] = {}
        self.individual_y_slider_labels: Dict[str, QtWidgets.QLabel] = {}
        self.individual_y_scrollbars: Dict[str, QtWidgets.QScrollBar] = {}
        self._updating_scrollbars: bool = False
        self._updating_viewranges: bool = False
        self._updating_limit_fields: bool = False

        # Multi-Trial Selection State
        self.selected_trial_indices: Set[int] = set()
        self.selected_average_plot_items: Dict[str, pg.PlotDataItem] = {}

        # Manual Limits State
        self.manual_limits_enabled: bool = False
        self.manual_x_limits: Optional[Tuple[float, float]] = None
        self.manual_y_limits: Optional[Tuple[float, float]] = None
        self.manual_limit_x_min_edit: Optional[QtWidgets.QLineEdit] = None
        self.manual_limit_x_max_edit: Optional[QtWidgets.QLineEdit] = None
        self.manual_limit_y_min_edit: Optional[QtWidgets.QLineEdit] = None
        self.manual_limit_y_max_edit: Optional[QtWidgets.QLineEdit] = None
        self.set_manual_limits_button: Optional[QtWidgets.QPushButton] = None
        self.enable_manual_limits_checkbox: Optional[QtWidgets.QCheckBox] = None

        # --- Setup UI and Signals ---
        self._setup_ui(); self._connect_signals(); self._update_ui_state()
        self._update_limit_fields() # Initialize field text

    # =========================================================================
    # UI Setup (_setup_ui)
    # =========================================================================
    def _setup_ui(self):
        """Create and arrange widgets ONCE during initialization."""
        # --- Menu Bar ---
        menu_bar = self.menuBar(); file_menu = menu_bar.addMenu("&File")
        self.open_file_action = file_menu.addAction("&Open..."); self.open_folder_action = None
        file_menu.addSeparator(); self.export_nwb_action = file_menu.addAction("Export to &NWB...")
        file_menu.addSeparator(); self.quit_action = file_menu.addAction("&Quit")

        main_widget = QtWidgets.QWidget(); self.setCentralWidget(main_widget)
        main_layout = QtWidgets.QHBoxLayout(main_widget)

        # --- Left Panel ---
        left_panel_widget = QtWidgets.QWidget(); left_panel_layout = QtWidgets.QVBoxLayout(left_panel_widget); left_panel_layout.setSpacing(10)

        # File Ops
        file_op_group = QtWidgets.QGroupBox("Load Data"); file_op_layout = QtWidgets.QHBoxLayout(file_op_group)
        self.open_button_ui = QtWidgets.QPushButton("Open..."); file_op_layout.addWidget(self.open_button_ui); left_panel_layout.addWidget(file_op_group)

        # Display Options
        display_group = QtWidgets.QGroupBox("Display Options"); display_layout = QtWidgets.QVBoxLayout(display_group)
        plot_mode_layout = QtWidgets.QHBoxLayout(); plot_mode_layout.addWidget(QtWidgets.QLabel("Plot Mode:"))
        self.plot_mode_combobox = QtWidgets.QComboBox(); self.plot_mode_combobox.addItems(["Overlay All + Avg", "Cycle Single Trial"])
        self.plot_mode_combobox.setCurrentIndex(self.current_plot_mode); plot_mode_layout.addWidget(self.plot_mode_combobox); display_layout.addLayout(plot_mode_layout)
        self.downsample_checkbox = QtWidgets.QCheckBox("Auto Downsample Plot"); self.downsample_checkbox.setChecked(True); display_layout.addWidget(self.downsample_checkbox)
        sep1 = QtWidgets.QFrame(); sep1.setFrameShape(QtWidgets.QFrame.Shape.HLine); sep1.setFrameShadow(QtWidgets.QFrame.Shadow.Sunken); display_layout.addWidget(sep1)
        display_layout.addWidget(QtWidgets.QLabel("Manual Trial Averaging:"))
        self.select_trial_button = QtWidgets.QPushButton("Add Current Trial to Avg Set"); self.select_trial_button.setToolTip("Add/Remove the currently viewed trial (in Cycle Mode) to the set for averaging."); display_layout.addWidget(self.select_trial_button)
        self.selected_trials_display = QtWidgets.QLabel("Selected: None"); self.selected_trials_display.setWordWrap(True); display_layout.addWidget(self.selected_trials_display)
        clear_avg_layout = QtWidgets.QHBoxLayout(); self.clear_selection_button = QtWidgets.QPushButton("Clear Avg Set"); self.clear_selection_button.setToolTip("Clear the set of selected trials."); clear_avg_layout.addWidget(self.clear_selection_button)
        self.show_selected_average_button = QtWidgets.QPushButton("Plot Selected Avg"); self.show_selected_average_button.setToolTip("Toggle the display of the average of selected trials as an overlay."); self.show_selected_average_button.setCheckable(True); clear_avg_layout.addWidget(self.show_selected_average_button); display_layout.addLayout(clear_avg_layout)
        left_panel_layout.addWidget(display_group)

        # Manual Limits
        manual_limits_group = QtWidgets.QGroupBox("Manual Plot Limits"); manual_limits_layout = QtWidgets.QVBoxLayout(manual_limits_group); manual_limits_layout.setSpacing(5)
        self.enable_manual_limits_checkbox = QtWidgets.QCheckBox("Enable Manual Limits"); self.enable_manual_limits_checkbox.setToolTip("Lock plot axes to the manually set limits below."); manual_limits_layout.addWidget(self.enable_manual_limits_checkbox)
        limits_grid_layout = QtWidgets.QGridLayout(); limits_grid_layout.setSpacing(3)
        self.manual_limit_x_min_edit = QtWidgets.QLineEdit(); self.manual_limit_x_max_edit = QtWidgets.QLineEdit(); self.manual_limit_y_min_edit = QtWidgets.QLineEdit(); self.manual_limit_y_max_edit = QtWidgets.QLineEdit()
        self.manual_limit_x_min_edit.setPlaceholderText("Auto"); self.manual_limit_x_max_edit.setPlaceholderText("Auto"); self.manual_limit_y_min_edit.setPlaceholderText("Auto"); self.manual_limit_y_max_edit.setPlaceholderText("Auto")
        self.manual_limit_x_min_edit.setToolTip("Current/Manual X Min"); self.manual_limit_x_max_edit.setToolTip("Current/Manual X Max"); self.manual_limit_y_min_edit.setToolTip("Current/Manual Y Min (Ref Plot)"); self.manual_limit_y_max_edit.setToolTip("Current/Manual Y Max (Ref Plot)")
        limits_grid_layout.addWidget(QtWidgets.QLabel("X Min:"), 0, 0); limits_grid_layout.addWidget(self.manual_limit_x_min_edit, 0, 1); limits_grid_layout.addWidget(QtWidgets.QLabel("X Max:"), 1, 0); limits_grid_layout.addWidget(self.manual_limit_x_max_edit, 1, 1)
        limits_grid_layout.addWidget(QtWidgets.QLabel("Y Min:"), 2, 0); limits_grid_layout.addWidget(self.manual_limit_y_min_edit, 2, 1); limits_grid_layout.addWidget(QtWidgets.QLabel("Y Max:"), 3, 0); limits_grid_layout.addWidget(self.manual_limit_y_max_edit, 3, 1)
        manual_limits_layout.addLayout(limits_grid_layout)
        self.set_manual_limits_button = QtWidgets.QPushButton("Set Manual Limits"); self.set_manual_limits_button.setToolTip("Store the values from the fields above as the manual limits."); manual_limits_layout.addWidget(self.set_manual_limits_button)
        left_panel_layout.addWidget(manual_limits_group)

        # Channel Select
        self.channel_select_group = QtWidgets.QGroupBox("Channels"); self.channel_scroll_area = QtWidgets.QScrollArea(); self.channel_scroll_area.setWidgetResizable(True)
        self.channel_select_widget = QtWidgets.QWidget(); self.channel_checkbox_layout = QtWidgets.QVBoxLayout(self.channel_select_widget); self.channel_checkbox_layout.setAlignment(QtCore.Qt.AlignTop)
        self.channel_scroll_area.setWidget(self.channel_select_widget); channel_group_layout = QtWidgets.QVBoxLayout(self.channel_select_group); channel_group_layout.addWidget(self.channel_scroll_area); left_panel_layout.addWidget(self.channel_select_group)

        # Metadata
        meta_group = QtWidgets.QGroupBox("File Information"); meta_layout = QtWidgets.QFormLayout(meta_group)
        self.filename_label = QtWidgets.QLabel("N/A"); self.sampling_rate_label = QtWidgets.QLabel("N/A"); self.channels_label = QtWidgets.QLabel("N/A"); self.duration_label = QtWidgets.QLabel("N/A")
        meta_layout.addRow("File:", self.filename_label); meta_layout.addRow("Sampling Rate:", self.sampling_rate_label); meta_layout.addRow("Duration:", self.duration_label); meta_layout.addRow("Channels:", self.channels_label)
        left_panel_layout.addWidget(meta_group); left_panel_layout.addStretch();
        main_layout.addWidget(left_panel_widget, stretch=0)

        # --- Center Panel ---
        center_panel_widget = QtWidgets.QWidget(); center_panel_layout = QtWidgets.QVBoxLayout(center_panel_widget)
        nav_layout = QtWidgets.QHBoxLayout(); self.prev_file_button = QtWidgets.QPushButton("<< Prev File"); self.next_file_button = QtWidgets.QPushButton("Next File >>"); self.folder_file_index_label = QtWidgets.QLabel("")
        nav_layout.addWidget(self.prev_file_button); nav_layout.addStretch(); nav_layout.addWidget(self.folder_file_index_label); nav_layout.addStretch(); nav_layout.addWidget(self.next_file_button); center_panel_layout.addLayout(nav_layout)
        self.graphics_layout_widget = pg.GraphicsLayoutWidget(); center_panel_layout.addWidget(self.graphics_layout_widget, stretch=1)
        self.x_scrollbar = QtWidgets.QScrollBar(QtCore.Qt.Horizontal); self.x_scrollbar.setFixedHeight(20); self.x_scrollbar.setRange(0, self.SCROLLBAR_MAX_RANGE); center_panel_layout.addWidget(self.x_scrollbar)
        plot_controls_layout = QtWidgets.QHBoxLayout()
        view_group = QtWidgets.QGroupBox("View"); view_layout = QtWidgets.QHBoxLayout(view_group); self.reset_view_button = QtWidgets.QPushButton("Reset View"); view_layout.addWidget(self.reset_view_button); plot_controls_layout.addWidget(view_group)
        x_zoom_group = QtWidgets.QGroupBox("X Zoom (Min=Out, Max=In)"); x_zoom_layout = QtWidgets.QHBoxLayout(x_zoom_group); self.x_zoom_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal); self.x_zoom_slider.setRange(self.SLIDER_RANGE_MIN, self.SLIDER_RANGE_MAX); self.x_zoom_slider.setValue(self.SLIDER_DEFAULT_VALUE); self.x_zoom_slider.setToolTip("Adjust X-axis zoom (Shared)"); x_zoom_layout.addWidget(self.x_zoom_slider); plot_controls_layout.addWidget(x_zoom_group, stretch=1)
        trial_group = QtWidgets.QGroupBox("Trial"); trial_layout = QtWidgets.QHBoxLayout(trial_group); self.prev_trial_button = QtWidgets.QPushButton("<"); self.next_trial_button = QtWidgets.QPushButton(">"); self.trial_index_label = QtWidgets.QLabel("N/A"); trial_layout.addWidget(self.prev_trial_button); trial_layout.addWidget(self.trial_index_label); trial_layout.addWidget(self.next_trial_button); plot_controls_layout.addWidget(trial_group)
        center_panel_layout.addLayout(plot_controls_layout)
        main_layout.addWidget(center_panel_widget, stretch=1)

        # --- Right Panel ---
        y_controls_panel_widget = QtWidgets.QWidget(); y_controls_panel_layout = QtWidgets.QHBoxLayout(y_controls_panel_widget); y_controls_panel_widget.setFixedWidth(220); y_controls_panel_layout.setContentsMargins(0, 0, 0, 0); y_controls_panel_layout.setSpacing(5)
        # Y Scroll Column
        y_scroll_widget = QtWidgets.QWidget(); y_scroll_layout = QtWidgets.QVBoxLayout(y_scroll_widget); y_scroll_layout.setContentsMargins(0,0,0,0); y_scroll_layout.setSpacing(5)
        y_scroll_group = QtWidgets.QGroupBox("Y Scroll"); y_scroll_group_layout = QtWidgets.QVBoxLayout(y_scroll_group); y_scroll_layout.addWidget(y_scroll_group, stretch=1)
        self.global_y_scrollbar_widget = QtWidgets.QWidget(); global_y_scrollbar_layout = QtWidgets.QVBoxLayout(self.global_y_scrollbar_widget); global_y_scrollbar_layout.setContentsMargins(0,0,0,0); global_y_scrollbar_layout.setSpacing(2)
        global_y_scrollbar_label = QtWidgets.QLabel("Global Scroll"); global_y_scrollbar_label.setAlignment(QtCore.Qt.AlignCenter); self.global_y_scrollbar = QtWidgets.QScrollBar(QtCore.Qt.Vertical); self.global_y_scrollbar.setRange(0, self.SCROLLBAR_MAX_RANGE); self.global_y_scrollbar.setToolTip("Scroll Y-axis (All visible)")
        global_y_scrollbar_layout.addWidget(global_y_scrollbar_label); global_y_scrollbar_layout.addWidget(self.global_y_scrollbar, stretch=1); y_scroll_group_layout.addWidget(self.global_y_scrollbar_widget, stretch=1)
        self.individual_y_scrollbars_container = QtWidgets.QWidget(); self.individual_y_scrollbars_layout = QtWidgets.QVBoxLayout(self.individual_y_scrollbars_container); self.individual_y_scrollbars_layout.setContentsMargins(0, 5, 0, 0); self.individual_y_scrollbars_layout.setSpacing(10); self.individual_y_scrollbars_layout.setAlignment(QtCore.Qt.AlignTop)
        y_scroll_group_layout.addWidget(self.individual_y_scrollbars_container, stretch=1); y_controls_panel_layout.addWidget(y_scroll_widget, stretch=1)
        # Y Zoom Column
        y_zoom_widget = QtWidgets.QWidget(); y_zoom_layout = QtWidgets.QVBoxLayout(y_zoom_widget); y_zoom_layout.setContentsMargins(0,0,0,0); y_zoom_layout.setSpacing(5)
        y_zoom_group = QtWidgets.QGroupBox("Y Zoom"); y_zoom_group_layout = QtWidgets.QVBoxLayout(y_zoom_group); y_zoom_layout.addWidget(y_zoom_group, stretch=1)
        self.y_lock_checkbox = QtWidgets.QCheckBox("Lock Axes"); self.y_lock_checkbox.setChecked(self.y_axes_locked); self.y_lock_checkbox.setToolTip("Lock/Unlock Y-axis zoom & scroll"); y_zoom_group_layout.addWidget(self.y_lock_checkbox)
        self.global_y_slider_widget = QtWidgets.QWidget(); global_y_slider_layout = QtWidgets.QVBoxLayout(self.global_y_slider_widget); global_y_slider_layout.setContentsMargins(0,0,0,0); global_y_slider_layout.setSpacing(2)
        global_y_slider_label = QtWidgets.QLabel("Global Zoom"); global_y_slider_label.setAlignment(QtCore.Qt.AlignCenter); self.global_y_slider = QtWidgets.QSlider(QtCore.Qt.Vertical); self.global_y_slider.setRange(self.SLIDER_RANGE_MIN, self.SLIDER_RANGE_MAX); self.global_y_slider.setValue(self.SLIDER_DEFAULT_VALUE); self.global_y_slider.setToolTip("Adjust Y-axis zoom (All visible)")
        global_y_slider_layout.addWidget(global_y_slider_label); global_y_slider_layout.addWidget(self.global_y_slider, stretch=1); y_zoom_group_layout.addWidget(self.global_y_slider_widget, stretch=1)
        self.individual_y_sliders_container = QtWidgets.QWidget(); self.individual_y_sliders_layout = QtWidgets.QVBoxLayout(self.individual_y_sliders_container); self.individual_y_sliders_layout.setContentsMargins(0, 5, 0, 0); self.individual_y_sliders_layout.setSpacing(10); self.individual_y_sliders_layout.setAlignment(QtCore.Qt.AlignTop)
        y_zoom_group_layout.addWidget(self.individual_y_sliders_container, stretch=1); y_controls_panel_layout.addWidget(y_zoom_widget, stretch=1)
        main_layout.addWidget(y_controls_panel_widget, stretch=0)

        # --- Status Bar ---
        self.statusBar = QtWidgets.QStatusBar(); self.setStatusBar(self.statusBar); self.statusBar.showMessage("Ready.")

        # Initial state updates
        self._update_y_controls_visibility(); self._update_selected_trials_display(); self._update_zoom_scroll_enable_state()

    # =========================================================================
    # Signal Connections (_connect_signals)
    # =========================================================================
    def _connect_signals(self):
        """Connect widget signals to handler slots."""
        # File Menu / Basic Controls
        self.open_file_action.triggered.connect(self._open_file_or_folder)
        self.export_nwb_action.triggered.connect(self._export_to_nwb); self.quit_action.triggered.connect(self.close)
        self.open_button_ui.clicked.connect(self._open_file_or_folder)
        self.downsample_checkbox.stateChanged.connect(self._trigger_plot_update); self.plot_mode_combobox.currentIndexChanged.connect(self._on_plot_mode_changed)
        self.reset_view_button.clicked.connect(self._reset_view)
        self.prev_trial_button.clicked.connect(self._prev_trial); self.next_trial_button.clicked.connect(self._next_trial)
        self.prev_file_button.clicked.connect(self._prev_file_folder); self.next_file_button.clicked.connect(self._next_file_folder)

        # Zoom / Scroll Controls
        self.x_zoom_slider.valueChanged.connect(self._on_x_zoom_changed)
        self.y_lock_checkbox.stateChanged.connect(self._on_y_lock_changed)
        self.global_y_slider.valueChanged.connect(self._on_global_y_zoom_changed)
        self.x_scrollbar.valueChanged.connect(self._on_x_scrollbar_changed)
        self.global_y_scrollbar.valueChanged.connect(self._on_global_y_scrollbar_changed)
        # Individual Y & ViewBox signals connected in _create_channel_ui

        # Multi-Trial Selection
        self.select_trial_button.clicked.connect(self._toggle_select_current_trial)
        self.clear_selection_button.clicked.connect(self._clear_avg_selection)
        self.show_selected_average_button.toggled.connect(self._toggle_plot_selected_average)

        # Manual Limits Connections
        if self.enable_manual_limits_checkbox: self.enable_manual_limits_checkbox.toggled.connect(self._on_manual_limits_toggled)
        if self.set_manual_limits_button: self.set_manual_limits_button.clicked.connect(self._on_set_limits_clicked)

    # =========================================================================
    # Reset & UI Creation
    # =========================================================================
    def _reset_ui_and_state_for_new_file(self):
        """Fully resets UI elements and state related to channels and plots."""
        log.info("Resetting UI and state for new file...")
        # Clear Plot/Selection State
        self._remove_selected_average_plots(); self.selected_trial_indices.clear(); self._update_selected_trials_display()
        self.show_selected_average_button.blockSignals(True); self.show_selected_average_button.setChecked(False); self.show_selected_average_button.blockSignals(False)

        # Clear Channel UI (Checkboxes, Plots, Individual Controls)
        for checkbox in self.channel_checkboxes.values():
            try: checkbox.stateChanged.disconnect(self._trigger_plot_update)
            except (TypeError, RuntimeError): pass
        while self.channel_checkbox_layout.count(): item = self.channel_checkbox_layout.takeAt(0); widget = item.widget(); widget.deleteLater() if widget else None
        self.channel_checkboxes.clear(); self.channel_select_group.setEnabled(False)

        for plot in self.channel_plots.values():
            if plot and plot.getViewBox(): vb = plot.getViewBox()
            try: vb.sigXRangeChanged.disconnect()
            except (TypeError, RuntimeError): pass
            try: vb.sigYRangeChanged.disconnect()
            except (TypeError, RuntimeError): pass
        self.graphics_layout_widget.clear(); self.channel_plots.clear(); self.channel_plot_data_items.clear()

        for slider in self.individual_y_sliders.values():
            try: slider.valueChanged.disconnect()
            except (TypeError, RuntimeError): pass
        while self.individual_y_sliders_layout.count(): item = self.individual_y_sliders_layout.takeAt(0); widget = item.widget(); widget.deleteLater() if widget else None
        self.individual_y_sliders.clear(); self.individual_y_slider_labels.clear()

        for scrollbar in self.individual_y_scrollbars.values():
            try: scrollbar.valueChanged.disconnect()
            except (TypeError, RuntimeError): pass
        while self.individual_y_scrollbars_layout.count(): item = self.individual_y_scrollbars_layout.takeAt(0); widget = item.widget(); widget.deleteLater() if widget else None
        self.individual_y_scrollbars.clear()

        # Reset Data State
        self.current_recording = None; self.max_trials_current_recording = 0; self.current_trial_index = 0

        # Reset Zoom/Scroll State
        self.base_x_range = None; self.base_y_ranges.clear()
        self.x_zoom_slider.blockSignals(True); self.x_zoom_slider.setValue(self.SLIDER_DEFAULT_VALUE); self.x_zoom_slider.blockSignals(False)
        self.global_y_slider.blockSignals(True); self.global_y_slider.setValue(self.SLIDER_DEFAULT_VALUE); self.global_y_slider.blockSignals(False)
        self.y_axes_locked = True; self.y_lock_checkbox.blockSignals(True); self.y_lock_checkbox.setChecked(self.y_axes_locked); self.y_lock_checkbox.blockSignals(False)
        self._reset_scrollbar(self.x_scrollbar); self._reset_scrollbar(self.global_y_scrollbar)

        # Reset Displays & Update State
        self._update_y_controls_visibility(); self._clear_metadata_display(); self._update_trial_label()
        self._update_limit_fields(); self._update_zoom_scroll_enable_state(); self._update_ui_state()

    def _reset_scrollbar(self, scrollbar: QtWidgets.QScrollBar):
        """Helper to reset a scrollbar to its default state (full range visible, disabled)."""
        scrollbar.blockSignals(True)
        try: scrollbar.setRange(0, 0); scrollbar.setPageStep(self.SCROLLBAR_MAX_RANGE); scrollbar.setValue(0)
        finally: scrollbar.blockSignals(False)
        scrollbar.setEnabled(False)

    def _create_channel_ui(self):
        """Creates checkboxes, PlotItems, Y-sliders, AND Y-scrollbars. Called ONCE per file load."""
        if not self.current_recording or not self.current_recording.channels:
            log.warning("No data to create channel UI."); self.channel_select_group.setEnabled(False); return
        self.channel_select_group.setEnabled(True)
        sorted_channel_items = sorted(self.current_recording.channels.items(), key=lambda item: str(item[0]))
        log.info(f"Creating UI for {len(sorted_channel_items)} channels.")
        last_plot_item = None

        for i, (chan_id, channel) in enumerate(sorted_channel_items):
            if chan_id in self.channel_checkboxes or chan_id in self.channel_plots: log.error(f"State Error: UI element {chan_id} exists!"); continue

            # Checkbox
            checkbox = QtWidgets.QCheckBox(f"{channel.name or f'Ch {chan_id}'}"); checkbox.setChecked(True); checkbox.stateChanged.connect(self._trigger_plot_update)
            self.channel_checkbox_layout.addWidget(checkbox); self.channel_checkboxes[chan_id] = checkbox

            # PlotItem
            plot_item = self.graphics_layout_widget.addPlot(row=i, col=0); plot_item.setLabel('left', channel.name or f'Ch {chan_id}', units=channel.units or 'units'); plot_item.showGrid(x=True, y=True, alpha=0.3)
            self.channel_plots[chan_id] = plot_item

            # ViewBox Setup & Signal Connection
            vb = plot_item.getViewBox(); vb.setMouseMode(pg.ViewBox.RectMode); vb._synaptipy_chan_id = chan_id
            # Standard handlers
            vb.sigXRangeChanged.connect(self._handle_vb_xrange_changed)
            vb.sigYRangeChanged.connect(self._handle_vb_yrange_changed)
            # Update limit fields (via delayed intermediate slot)
            vb.sigXRangeChanged.connect(partial(self._update_limit_fields_from_vb, axis='x'))
            vb.sigYRangeChanged.connect(partial(self._update_limit_fields_from_vb, axis='y'))

            # Link Axes & Hide Bottom
            if last_plot_item: plot_item.setXLink(last_plot_item); plot_item.hideAxis('bottom')
            last_plot_item = plot_item

            # Individual Y Zoom Slider
            ind_y_slider_widget = QtWidgets.QWidget(); ind_y_slider_layout = QtWidgets.QVBoxLayout(ind_y_slider_widget); ind_y_slider_layout.setContentsMargins(0,0,0,0); ind_y_slider_layout.setSpacing(2)
            slider_label_text = f"{channel.name or chan_id[:4]} Zoom"; slider_label = QtWidgets.QLabel(slider_label_text); slider_label.setAlignment(QtCore.Qt.AlignCenter); slider_label.setToolTip(f"Y Zoom for {channel.name or chan_id}")
            self.individual_y_slider_labels[chan_id] = slider_label; ind_y_slider_layout.addWidget(slider_label)
            y_slider = QtWidgets.QSlider(QtCore.Qt.Vertical); y_slider.setRange(self.SLIDER_RANGE_MIN, self.SLIDER_RANGE_MAX); y_slider.setValue(self.SLIDER_DEFAULT_VALUE); y_slider.setToolTip(f"Adjust Y zoom for {channel.name or chan_id} (Min=Out, Max=In)")
            y_slider.valueChanged.connect(partial(self._on_individual_y_zoom_changed, chan_id)); ind_y_slider_layout.addWidget(y_slider, stretch=1)
            self.individual_y_sliders[chan_id] = y_slider; self.individual_y_sliders_layout.addWidget(ind_y_slider_widget, stretch=1); ind_y_slider_widget.setVisible(False)

            # Individual Y Scrollbar
            y_scrollbar = QtWidgets.QScrollBar(QtCore.Qt.Vertical); y_scrollbar.setRange(0, self.SCROLLBAR_MAX_RANGE); y_scrollbar.setToolTip(f"Scroll Y-axis for {channel.name or chan_id}")
            y_scrollbar.valueChanged.connect(partial(self._on_individual_y_scrollbar_changed, chan_id))
            self.individual_y_scrollbars[chan_id] = y_scrollbar; self.individual_y_scrollbars_layout.addWidget(y_scrollbar, stretch=1); y_scrollbar.setVisible(False)
            self._reset_scrollbar(y_scrollbar)

        # Final Plot Setup
        if last_plot_item: last_plot_item.setLabel('bottom', "Time", units='s'); last_plot_item.showAxis('bottom')

    # =========================================================================
    # File Loading & Display Options
    # =========================================================================
    def _open_file_or_folder(self):
        """Opens a file dialog, finds sibling files, and loads the selected one."""
        file_filter = self.neo_adapter.get_supported_file_filter()
        log.debug(f"Using dynamic file filter: {file_filter}")
        filepath_str, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Open Recording File", "", file_filter)
        if not filepath_str: log.info("File open cancelled."); return
        selected_filepath = Path(filepath_str); folder_path = selected_filepath.parent; selected_extension = selected_filepath.suffix.lower()
        log.info(f"User selected: {selected_filepath.name}. Scanning folder '{folder_path}' for '{selected_extension}'.")
        try: sibling_files = sorted(list(folder_path.glob(f"*{selected_extension}")))
        except Exception as e:
             log.error(f"Error scanning folder {folder_path}: {e}"); QtWidgets.QMessageBox.warning(self, "Folder Scan Error", f"Could not scan folder:\n{e}")
             self.file_list = [selected_filepath]; self.current_file_index = 0; self._load_and_display_file(selected_filepath); return
        if not sibling_files: log.warning(f"No other files with '{selected_extension}' found. Loading selected only."); self.file_list = [selected_filepath]; self.current_file_index = 0
        else:
            self.file_list = sibling_files
            try: self.current_file_index = self.file_list.index(selected_filepath); log.info(f"Found {len(self.file_list)} file(s). Selected index: {self.current_file_index}.")
            except ValueError: log.error(f"Selected file {selected_filepath} not in scanned list? Loading first."); self.current_file_index = 0
        if self.file_list: self._load_and_display_file(self.file_list[self.current_file_index])
        else: self._reset_ui_and_state_for_new_file(); self._update_ui_state()

    def _load_and_display_file(self, filepath: Path):
        """Loads data, resets UI, creates plots, updates metadata, respects manual limits."""
        self.statusBar.showMessage(f"Loading '{filepath.name}'..."); QtWidgets.QApplication.processEvents()
        self._reset_ui_and_state_for_new_file(); self.current_recording = None
        try:
            self.current_recording = self.neo_adapter.read_recording(filepath)
            log.info(f"Successfully loaded recording from {filepath.name}")
            self.max_trials_current_recording = self.current_recording.max_trials if self.current_recording else 0
            self._create_channel_ui(); self._update_metadata_display(); self._update_plot()
            self._reset_view() # Applies manual limits if enabled, otherwise auto-ranges
            self.statusBar.showMessage(f"Loaded '{filepath.name}'. Ready.", 5000)
        except (FileNotFoundError, UnsupportedFormatError, FileReadError, SynaptipyError) as e:
            log.error(f"Load failed {filepath}: {e}", exc_info=False); QtWidgets.QMessageBox.critical(self, "Loading Error", f"Could not load file:\n{filepath.name}\n\nError: {e}"); self._clear_metadata_display(); self.statusBar.showMessage(f"Error loading {filepath.name}.", 5000)
        except Exception as e:
            log.error(f"Unexpected error loading {filepath}: {e}", exc_info=True); QtWidgets.QMessageBox.critical(self, "Unexpected Error", f"Error loading:\n{filepath.name}\n\n{e}"); self._clear_metadata_display(); self.statusBar.showMessage(f"Error loading {filepath.name}.", 5000)
        finally:
            self._update_zoom_scroll_enable_state(); self._update_ui_state()
            if self.manual_limits_enabled: self._apply_manual_limits() # Re-apply if needed after potential reset

    def _on_plot_mode_changed(self, index):
        """Handles change in plot mode (Overlay vs Cycle)."""
        new_mode_name = 'Overlay+Avg' if index == self.PlotMode.OVERLAY_AVG else 'Cycle Single'
        log.info(f"Plot mode changed to: {new_mode_name} (Index: {index})")
        if self.current_plot_mode != index:
            self._remove_selected_average_plots()
            self.show_selected_average_button.blockSignals(True); self.show_selected_average_button.setChecked(False); self.show_selected_average_button.blockSignals(False)
        self.current_plot_mode = index; self.current_trial_index = 0
        self._update_plot(); self._reset_view(); self._update_ui_state()

    def _trigger_plot_update(self):
        """Connected to channel checkboxes and downsample option. Updates plot and related UI."""
        if not self.current_recording: return
        sender_widget = self.sender()
        is_channel_checkbox = isinstance(sender_widget, QtWidgets.QCheckBox) and sender_widget not in [self.downsample_checkbox, self.y_lock_checkbox, self.enable_manual_limits_checkbox]
        if is_channel_checkbox and self.selected_average_plot_items:
            log.debug("Channel visibility changed, removing selected average plot.")
            self._remove_selected_average_plots()
            self.show_selected_average_button.blockSignals(True); self.show_selected_average_button.setChecked(False); self.show_selected_average_button.blockSignals(False)
        self._update_plot()
        if is_channel_checkbox: self._update_y_controls_visibility()
        if is_channel_checkbox and sender_widget.isChecked():
            channel_id_to_reset = next((ch_id for ch_id, cb in self.channel_checkboxes.items() if cb == sender_widget), None)
            if channel_id_to_reset: self._reset_single_plot_view(channel_id_to_reset) # Will respect manual limits

    # =========================================================================
    # Plotting Core & Metadata
    # =========================================================================
    def _clear_plot_data_only(self):
        """Clears data items from plots, *excluding* the selected average overlays."""
        log.debug("Clearing plot data items (excluding selected averages).")
        for chan_id, plot_item in self.channel_plots.items():
            if plot_item is None or plot_item.scene() is None: continue
            selected_avg_item = self.selected_average_plot_items.get(chan_id)
            items_to_remove = [item for item in plot_item.items if isinstance(item, (pg.PlotDataItem, pg.TextItem)) and item != selected_avg_item]
            for item in items_to_remove:
                 if item in plot_item.items: plot_item.removeItem(item)
                 else: log.warning(f"Attempted to remove item {item} from plot {chan_id}, but it was not found.")
        self.channel_plot_data_items.clear()

    def _update_plot(self):
        """Core function to draw data onto the visible plot items based on current mode."""
        self._clear_plot_data_only()
        if not self.current_recording or not self.channel_plots:
            log.warning("Update plot: No recording or plot items exist."); items = self.graphics_layout_widget.items()
            if not any(isinstance(item, pg.PlotItem) for item in items): self.graphics_layout_widget.clear(); self.graphics_layout_widget.addLabel("Load data", row=0, col=0)
            self._update_ui_state(); return

        is_cycle_mode = self.current_plot_mode == self.PlotMode.CYCLE_SINGLE
        log.debug(f"Updating plot data. Mode: {'Cycle Single' if is_cycle_mode else 'Overlay+Avg'}, Trial: {self.current_trial_index+1}/{self.max_trials_current_recording}")

        vis_constants_available = 'VisConstants' in globals() and VisConstants is not None
        trial_pen = pg.mkPen(VisConstants.TRIAL_COLOR + (VisConstants.TRIAL_ALPHA,), width=VisConstants.DEFAULT_PLOT_PEN_WIDTH) if vis_constants_available else pg.mkPen(color=(128, 128, 128, 80), width=1)
        avg_pen = pg.mkPen(VisConstants.AVERAGE_COLOR, width=(VisConstants.DEFAULT_PLOT_PEN_WIDTH + 1) if vis_constants_available else 2) if vis_constants_available else pg.mkPen('r', width=2)
        single_trial_pen = pg.mkPen(VisConstants.TRIAL_COLOR, width=VisConstants.DEFAULT_PLOT_PEN_WIDTH) if vis_constants_available else pg.mkPen(color=(128, 128, 128), width=1)
        ds_threshold = VisConstants.DOWNSAMPLING_THRESHOLD if vis_constants_available else 1000

        any_data_plotted_overall = False; visible_plots_this_update: List[pg.PlotItem] = []

        for chan_id, plot_item in self.channel_plots.items():
            checkbox = self.channel_checkboxes.get(chan_id); channel = self.current_recording.channels.get(chan_id)
            if checkbox and checkbox.isChecked() and channel and plot_item:
                plot_item.setVisible(True); visible_plots_this_update.append(plot_item)
                plotted_something_for_channel = False; enable_ds = self.downsample_checkbox.isChecked()

                if not is_cycle_mode: # Overlay+Avg Mode
                    for trial_idx in range(channel.num_trials):
                        data = channel.get_data(trial_idx); tvec = channel.get_relative_time_vector(trial_idx)
                        if data is not None and tvec is not None:
                             di = plot_item.plot(tvec, data, pen=trial_pen); di.opts['autoDownsample'] = enable_ds
                             if enable_ds: di.opts['autoDownsampleThreshold'] = ds_threshold
                             self.channel_plot_data_items.setdefault(chan_id, []).append(di); plotted_something_for_channel = True
                    avg_data = channel.get_averaged_data(); avg_tvec = channel.get_relative_averaged_time_vector()
                    if avg_data is not None and avg_tvec is not None:
                        di_avg = plot_item.plot(avg_tvec, avg_data, pen=avg_pen); di_avg.opts['autoDownsample'] = enable_ds;
                        if enable_ds: di_avg.opts['autoDownsampleThreshold'] = ds_threshold
                        self.channel_plot_data_items.setdefault(chan_id, []).append(di_avg); plotted_something_for_channel = True
                    elif channel.num_trials > 0: log.warning(f"Avg failed ch {chan_id}")

                else: # Cycle Single Mode
                    idx_to_plot = -1;
                    if channel.num_trials > 0: idx_to_plot = min(self.current_trial_index, channel.num_trials - 1)
                    if idx_to_plot >= 0:
                        data = channel.get_data(idx_to_plot); tvec = channel.get_relative_time_vector(idx_to_plot)
                        if data is not None and tvec is not None:
                            di = plot_item.plot(tvec, data, pen=single_trial_pen); di.opts['autoDownsample'] = enable_ds
                            if enable_ds: di.opts['autoDownsampleThreshold'] = ds_threshold
                            self.channel_plot_data_items.setdefault(chan_id, []).append(di); plotted_something_for_channel = True
                        else: plot_item.addItem(pg.TextItem(f"Trial {idx_to_plot+1} data error", color='r')); log.warning(f"Missing data/tvec for trial {idx_to_plot+1}, channel {chan_id}")

                if not plotted_something_for_channel and channel.num_trials == 0: plot_item.addItem(pg.TextItem(f"No trials", color='orange'))
                elif not plotted_something_for_channel: plot_item.addItem(pg.TextItem(f"No data display", color='orange'))
                if plotted_something_for_channel: any_data_plotted_overall = True

            elif plot_item: plot_item.hide()

        # Configure X axis linking and bottom label
        last_visible_plot_this_update = visible_plots_this_update[-1] if visible_plots_this_update else None
        for i, item in enumerate(self.channel_plots.values()):
             if item in visible_plots_this_update:
                 is_last = (item == last_visible_plot_this_update); item.showAxis('bottom', show=is_last)
                 item.setLabel('bottom', "Time" if is_last else None, units='s' if is_last else None)
                 try:
                    current_vis_idx = visible_plots_this_update.index(item)
                    if current_vis_idx > 0: item.setXLink(visible_plots_this_update[current_vis_idx - 1])
                    else: item.setXLink(None)
                 except ValueError: item.setXLink(None); log.error(f"PlotItem {item} visible but not in list.")
             else: item.hideAxis('bottom'); item.setLabel('bottom', None); item.setXLink(None)

        self._update_trial_label()
        if not any_data_plotted_overall and self.current_recording and self.channel_plots: log.info("No channels selected or no data plotted.")
        self._update_ui_state() # Refresh button enables etc.

    def _update_metadata_display(self):
        """Updates labels in the 'File Information' group box."""
        if self.current_recording: rec = self.current_recording
        else: self._clear_metadata_display(); return
        self.filename_label.setText(rec.source_file.name)
        sr_text = f"{rec.sampling_rate:.2f} Hz" if rec.sampling_rate else "N/A"; self.sampling_rate_label.setText(sr_text)
        dur_text = f"{rec.duration:.3f} s" if rec.duration else "N/A"; self.duration_label.setText(dur_text)
        num_ch = rec.num_channels; max_tr = self.max_trials_current_recording
        self.channels_label.setText(f"{num_ch} ch, {max_tr} trial(s)")

    def _clear_metadata_display(self):
        """Resets metadata labels to 'N/A'."""
        self.filename_label.setText("N/A"); self.sampling_rate_label.setText("N/A"); self.duration_label.setText("N/A"); self.channels_label.setText("N/A")

    # =========================================================================
    # UI State Update
    # =========================================================================
    def _update_ui_state(self):
        """Updates enable/disable state and text of various UI elements."""
        has_data = self.current_recording is not None
        has_visible_plots = any(p.isVisible() for p in self.channel_plots.values())
        is_folder = len(self.file_list) > 1
        is_cycling_mode = has_data and self.current_plot_mode == self.PlotMode.CYCLE_SINGLE
        has_multiple_trials = has_data and self.max_trials_current_recording > 0
        has_selection = bool(self.selected_trial_indices)
        is_selected_average_plotted = bool(self.selected_average_plot_items)
        enable_any_data_controls = has_data

        # Reset View Button
        self.reset_view_button.setEnabled(has_visible_plots and not self.manual_limits_enabled)

        # Zoom/Scroll Controls - Handled by _update_zoom_scroll_enable_state()

        # General display options
        self.plot_mode_combobox.setEnabled(enable_any_data_controls); self.downsample_checkbox.setEnabled(enable_any_data_controls)
        self.export_nwb_action.setEnabled(enable_any_data_controls); self.channel_select_group.setEnabled(has_data)

        # Trial Navigation
        enable_trial_cycle_nav = enable_any_data_controls and is_cycling_mode and self.max_trials_current_recording > 1
        self.prev_trial_button.setEnabled(enable_trial_cycle_nav and self.current_trial_index > 0)
        self.next_trial_button.setEnabled(enable_trial_cycle_nav and self.current_trial_index < self.max_trials_current_recording - 1)
        self.trial_index_label.setVisible(enable_any_data_controls and is_cycling_mode)
        # self._update_trial_label() called elsewhere

        # File Navigation
        self.prev_file_button.setVisible(is_folder); self.next_file_button.setVisible(is_folder); self.folder_file_index_label.setVisible(is_folder)
        if is_folder:
             self.prev_file_button.setEnabled(self.current_file_index > 0); self.next_file_button.setEnabled(self.current_file_index < len(self.file_list) - 1)
             current_filename = self.file_list[self.current_file_index].name if 0 <= self.current_file_index < len(self.file_list) else "N/A"
             self.folder_file_index_label.setText(f"File {self.current_file_index + 1}/{len(self.file_list)}: {current_filename}")
        else: self.folder_file_index_label.setText("")

        # Multi-Trial Selection Buttons & Text
        can_select_current = is_cycling_mode and has_multiple_trials
        self.select_trial_button.setEnabled(can_select_current)
        is_current_selected = can_select_current and self.current_trial_index in self.selected_trial_indices
        self.select_trial_button.setText("Deselect Current Trial" if is_current_selected else "Add Current Trial to Avg Set")
        self.select_trial_button.setToolTip("Remove..." if is_current_selected else "Add...")
        self.clear_selection_button.setEnabled(has_selection); self.show_selected_average_button.setEnabled(has_selection)
        self.show_selected_average_button.setText("Hide Selected Avg" if is_selected_average_plotted else "Plot Selected Avg")
        self.show_selected_average_button.setToolTip("Hide..." if is_selected_average_plotted else "Show...")

        # Manual Limits UI State
        manual_limits_group_box = self.enable_manual_limits_checkbox.parentWidget() if self.enable_manual_limits_checkbox else None
        if isinstance(manual_limits_group_box, QtWidgets.QGroupBox): manual_limits_group_box.setEnabled(has_data)

    def _update_trial_label(self):
        """Updates the text of the trial index label."""
        if (self.current_recording and self.current_plot_mode == self.PlotMode.CYCLE_SINGLE and self.max_trials_current_recording > 0):
            self.trial_index_label.setText(f"{self.current_trial_index + 1} / {self.max_trials_current_recording}")
        else: self.trial_index_label.setText("N/A")

    # =========================================================================
    # Zoom & Scroll Controls (Check manual_limits_enabled)
    # =========================================================================
    def _calculate_new_range(self, base_range: Optional[Tuple[float, float]], slider_value: int) -> Optional[Tuple[float, float]]:
        """Calculates a new zoomed range based on a base range and slider value."""
        if base_range is None or base_range[0] is None or base_range[1] is None: log.warning("_calculate_new_range: Invalid base_range."); return None
        try:
            min_val, max_val = base_range; center = (min_val + max_val) / 2.0; full_span = max(1e-12, max_val - min_val)
            min_slider=float(self.SLIDER_RANGE_MIN); max_slider=float(self.SLIDER_RANGE_MAX); slider_pos_norm = (float(slider_value)-min_slider)/(max_slider-min_slider) if max_slider > min_slider else 0
            zoom_factor = max(self.MIN_ZOOM_FACTOR, min(1.0, 1.0 - slider_pos_norm * (1.0 - self.MIN_ZOOM_FACTOR)))
            new_span = full_span * zoom_factor; new_min = center - new_span / 2.0; new_max = center + new_span / 2.0
            return (new_min, new_max)
        except Exception as e: log.error(f"Error calculating new range: {e}", exc_info=True); return None

    def _on_x_zoom_changed(self, value):
        if self.manual_limits_enabled or self.base_x_range is None or self._updating_viewranges: return
        new_x_range = self._calculate_new_range(self.base_x_range, value)
        if new_x_range is None: return
        first_visible_plot = next((p for p in self.channel_plots.values() if p.isVisible()), None)
        if first_visible_plot:
            vb = first_visible_plot.getViewBox()
            try: self._updating_viewranges = True; vb.setXRange(new_x_range[0], new_x_range[1], padding=0)
            finally: self._updating_viewranges = False
            self._update_scrollbar_from_view(self.x_scrollbar, self.base_x_range, new_x_range)

    def _on_x_scrollbar_changed(self, value):
        if self.manual_limits_enabled or self.base_x_range is None or self._updating_scrollbars: return
        first_visible_plot = next((p for p in self.channel_plots.values() if p.isVisible()), None)
        if not first_visible_plot: return
        try:
            vb = first_visible_plot.getViewBox(); current_x_range = vb.viewRange()[0]; current_span = max(1e-12, current_x_range[1] - current_x_range[0])
            base_span = max(1e-12, self.base_x_range[1] - self.base_x_range[0])
            scrollable_data_range = max(0, base_span - current_span); scroll_fraction = float(value) / max(1, self.x_scrollbar.maximum())
            new_min = self.base_x_range[0] + scroll_fraction * scrollable_data_range; new_max = new_min + current_span
            self._updating_viewranges = True; vb.setXRange(new_min, new_max, padding=0)
        except Exception as e: log.error(f"Error handling X scrollbar change: {e}", exc_info=True)
        finally: self._updating_viewranges = False

    def _handle_vb_xrange_changed(self, vb, new_range):
        if self.manual_limits_enabled and self.manual_x_limits and not self._updating_viewranges:
            log.debug("Manual limits ON: Re-applying X limits after ViewBox change.")
            self._updating_viewranges = True; vb.setXRange(self.manual_x_limits[0], self.manual_x_limits[1], padding=0); self._updating_viewranges = False; return
        if self._updating_viewranges or self.base_x_range is None: return
        self._update_scrollbar_from_view(self.x_scrollbar, self.base_x_range, new_range)

    def _on_y_lock_changed(self, state):
        self.y_axes_locked = bool(state == QtCore.Qt.Checked.value); log.info(f"Y-axes {'locked' if self.y_axes_locked else 'unlocked'}.")
        self._update_y_controls_visibility(); self._update_ui_state(); self._update_zoom_scroll_enable_state() # Update enables

    def _update_y_controls_visibility(self):
        locked = self.y_axes_locked; has_visible_plots = any(p.isVisible() for p in self.channel_plots.values())
        self.global_y_slider_widget.setVisible(locked and has_visible_plots); self.individual_y_sliders_container.setVisible(not locked and has_visible_plots)
        self.global_y_scrollbar_widget.setVisible(locked and has_visible_plots); self.individual_y_scrollbars_container.setVisible(not locked and has_visible_plots)
        if not has_visible_plots: return
        visible_chan_ids = {p.getViewBox()._synaptipy_chan_id for p in self.channel_plots.values() if p.isVisible() and hasattr(p.getViewBox(), '_synaptipy_chan_id')}
        if not locked:
            for chan_id, slider in self.individual_y_sliders.items(): is_visible = chan_id in visible_chan_ids; slider.parentWidget().setVisible(is_visible); has_base = self.base_y_ranges.get(chan_id) is not None; slider.setEnabled(is_visible and has_base and not self.manual_limits_enabled) # Check manual limits
            for chan_id, scrollbar in self.individual_y_scrollbars.items(): is_visible = chan_id in visible_chan_ids; scrollbar.setVisible(is_visible); has_base = self.base_y_ranges.get(chan_id) is not None; current_enabled_state = scrollbar.isEnabled(); scrollbar.setEnabled(is_visible and has_base and current_enabled_state and not self.manual_limits_enabled) # Check manual limits
        else:
             can_enable_global = any(self.base_y_ranges.get(ch_id) is not None for ch_id in visible_chan_ids)
             self.global_y_slider.setEnabled(can_enable_global and not self.manual_limits_enabled) # Check manual limits
             current_enabled_state = self.global_y_scrollbar.isEnabled(); self.global_y_scrollbar.setEnabled(can_enable_global and current_enabled_state and not self.manual_limits_enabled) # Check manual limits

    def _on_global_y_zoom_changed(self, value):
        if self.manual_limits_enabled or not self.y_axes_locked or self._updating_viewranges: return; self._apply_global_y_zoom(value)

    def _apply_global_y_zoom(self, value):
        if self.manual_limits_enabled: return
        log.debug(f"Applying global Y zoom value: {value}"); first_visible_base_y = None; first_visible_new_y = None
        try:
            self._updating_viewranges = True
            for chan_id, plot in self.channel_plots.items():
                if plot.isVisible(): base_y = self.base_y_ranges.get(chan_id)
                if base_y is None: log.warning(f"Global Y Zoom: No base Y range for {chan_id}"); continue
                new_y_range = self._calculate_new_range(base_y, value)
                if new_y_range: plot.getViewBox().setYRange(new_y_range[0], new_y_range[1], padding=0)
                if first_visible_base_y is None and new_y_range: first_visible_base_y = base_y; first_visible_new_y = new_y_range
        finally: self._updating_viewranges = False
        if first_visible_base_y and first_visible_new_y: self._update_scrollbar_from_view(self.global_y_scrollbar, first_visible_base_y, first_visible_new_y)
        else: self._reset_scrollbar(self.global_y_scrollbar)

    def _on_global_y_scrollbar_changed(self, value):
        if self.manual_limits_enabled or not self.y_axes_locked or self._updating_scrollbars: return; self._apply_global_y_scroll(value)

    def _apply_global_y_scroll(self, value):
        if self.manual_limits_enabled: return
        first_visible_plot = next((p for p in self.channel_plots.values() if p.isVisible()), None);
        if not first_visible_plot: return
        try:
            vb_ref = first_visible_plot.getViewBox(); ref_chan_id = getattr(vb_ref, '_synaptipy_chan_id', None); ref_base_y = self.base_y_ranges.get(ref_chan_id)
            if ref_base_y is None: return
            current_y_range_ref = vb_ref.viewRange()[1]; current_span = max(1e-12, current_y_range_ref[1] - current_y_range_ref[0])
            ref_base_span = max(1e-12, ref_base_y[1] - ref_base_y[0])
            scroll_fraction = float(value) / max(1, self.global_y_scrollbar.maximum())
            self._updating_viewranges = True
            for chan_id, plot in self.channel_plots.items():
                if plot.isVisible():
                    base_y = self.base_y_ranges.get(chan_id);
                    if base_y is None: continue; base_span = max(1e-12, base_y[1] - base_y[0])
                    scrollable_data_range = max(0, base_span - current_span)
                    new_min = base_y[0] + scroll_fraction * scrollable_data_range; new_max = new_min + current_span
                    plot.getViewBox().setYRange(new_min, new_max, padding=0)
        except Exception as e: log.error(f"Error handling global Y scrollbar change: {e}", exc_info=True)
        finally: self._updating_viewranges = False

    def _on_individual_y_zoom_changed(self, chan_id, value):
        if self.manual_limits_enabled or self.y_axes_locked or self._updating_viewranges: return
        plot = self.channel_plots.get(chan_id); base_y = self.base_y_ranges.get(chan_id); scrollbar = self.individual_y_scrollbars.get(chan_id)
        if plot is None or not plot.isVisible() or base_y is None or scrollbar is None: return
        new_y_range = self._calculate_new_range(base_y, value)
        if new_y_range:
            try: self._updating_viewranges = True; plot.getViewBox().setYRange(new_y_range[0], new_y_range[1], padding=0)
            finally: self._updating_viewranges = False
            self._update_scrollbar_from_view(scrollbar, base_y, new_y_range)

    def _on_individual_y_scrollbar_changed(self, chan_id, value):
        if self.manual_limits_enabled or self.y_axes_locked or self._updating_scrollbars: return
        plot = self.channel_plots.get(chan_id); base_y = self.base_y_ranges.get(chan_id); scrollbar = self.individual_y_scrollbars.get(chan_id)
        if plot is None or not plot.isVisible() or base_y is None or scrollbar is None: return
        try:
            vb = plot.getViewBox(); current_y_range = vb.viewRange()[1]; current_span = max(1e-12, current_y_range[1] - current_y_range[0])
            base_span = max(1e-12, base_y[1] - base_y[0])
            scrollable_data_range = max(0, base_span - current_span); scroll_fraction = float(value) / max(1, scrollbar.maximum())
            new_min = base_y[0] + scroll_fraction * scrollable_data_range; new_max = new_min + current_span
            self._updating_viewranges = True; vb.setYRange(new_min, new_max, padding=0)
        except Exception as e: log.error(f"Error handling individual Y scrollbar {chan_id}: {e}", exc_info=True)
        finally: self._updating_viewranges = False

    def _handle_vb_yrange_changed(self, vb, new_range):
        if self.manual_limits_enabled and self.manual_y_limits and not self._updating_viewranges:
            chan_id = getattr(vb, '_synaptipy_chan_id', None); log.debug(f"Manual limits ON: Re-applying Y limits for {chan_id} after ViewBox change.")
            self._updating_viewranges = True; vb.setYRange(self.manual_y_limits[0], self.manual_y_limits[1], padding=0); self._updating_viewranges = False; return
        if self._updating_viewranges: return
        chan_id = getattr(vb, '_synaptipy_chan_id', None);
        if chan_id is None: return; base_y = self.base_y_ranges.get(chan_id);
        if base_y is None: return
        if self.y_axes_locked:
            first_visible_vb=next((p.getViewBox() for p in self.channel_plots.values() if p.isVisible()), None)
            if vb == first_visible_vb: self._update_scrollbar_from_view(self.global_y_scrollbar, base_y, new_range)
        else: scrollbar = self.individual_y_scrollbars.get(chan_id);
        if scrollbar: self._update_scrollbar_from_view(scrollbar, base_y, new_range)

    def _update_scrollbar_from_view(self, scrollbar: QtWidgets.QScrollBar, base_range: Optional[Tuple[float,float]], view_range: Optional[Tuple[float, float]]):
        """Updates a scrollbar's range, page step, and value based on base and current view ranges."""
        if self._updating_scrollbars: return
        # Disable scrollbar if ranges invalid OR if manual limits are ON
        if (base_range is None or view_range is None or self.manual_limits_enabled):
            self._reset_scrollbar(scrollbar); return
        try:
            base_min, base_max = base_range; view_min, view_max = view_range
            base_span = max(1e-12, base_max - base_min); view_span = max(1e-12, min(view_max - view_min, base_span))
            page_step = max(1, min(int((view_span / base_span) * self.SCROLLBAR_MAX_RANGE), self.SCROLLBAR_MAX_RANGE))
            scroll_range_max = max(0, self.SCROLLBAR_MAX_RANGE - page_step)
            relative_pos = view_min - base_min; scrollable_data_range = max(1e-12, base_span - view_span)
            value = max(0, min(int((relative_pos / scrollable_data_range) * scroll_range_max), scroll_range_max)) if scrollable_data_range > 0 else 0
            self._updating_scrollbars = True; scrollbar.blockSignals(True); scrollbar.setRange(0, scroll_range_max); scrollbar.setPageStep(page_step); scrollbar.setValue(value); scrollbar.setEnabled(scroll_range_max > 0); scrollbar.blockSignals(False)
        except Exception as e: log.error(f"Error updating scrollbar: {e}", exc_info=True); self._reset_scrollbar(scrollbar)
        finally: self._updating_scrollbars = False

    # =========================================================================
    # View Reset (Handles manual limits)
    # =========================================================================
    def _reset_view(self):
        """Resets view: Applies manual limits if enabled, otherwise auto-ranges."""
        log.info("Reset View triggered.")
        if self.manual_limits_enabled:
            log.info("Manual limits are enabled. Applying stored limits instead of auto-ranging.")
            self._apply_manual_limits(); self._update_ui_state(); return

        log.debug("Manual limits OFF. Performing auto-range.")
        visible_plots_dict = {p.getViewBox()._synaptipy_chan_id: p for p in self.channel_plots.values() if p.isVisible() and hasattr(p.getViewBox(), '_synaptipy_chan_id')}
        if not visible_plots_dict:
            log.debug("Reset View: No visible plots."); self.base_x_range = None; self.base_y_ranges.clear(); self._reset_scrollbar(self.x_scrollbar); self._reset_scrollbar(self.global_y_scrollbar); [self._reset_scrollbar(sb) for sb in self.individual_y_scrollbars.values()]; self._reset_all_sliders(); self._update_y_controls_visibility(); self._update_limit_fields(); self._update_zoom_scroll_enable_state(); self._update_ui_state(); return

        first_chan_id, first_plot = next(iter(visible_plots_dict.items()))
        first_plot.getViewBox().enableAutoRange(axis=pg.ViewBox.XAxis)
        for plot in visible_plots_dict.values(): plot.getViewBox().enableAutoRange(axis=pg.ViewBox.YAxis)

        try: self.base_x_range = first_plot.getViewBox().viewRange()[0]; log.debug(f"Reset View: New base X: {self.base_x_range}")
        except Exception as e: log.error(f"Reset View: Error getting base X: {e}"); self.base_x_range = None
        self.base_y_ranges.clear()
        for chan_id, plot in visible_plots_dict.items():
             try: self.base_y_ranges[chan_id] = plot.getViewBox().viewRange()[1]; log.debug(f"Reset View: New base Y for {chan_id}: {self.base_y_ranges[chan_id]}")
             except Exception as e: log.error(f"Reset View: Error getting base Y for {chan_id}: {e}")

        self._reset_all_sliders()
        if self.base_x_range: self._update_scrollbar_from_view(self.x_scrollbar, self.base_x_range, self.base_x_range)
        else: self._reset_scrollbar(self.x_scrollbar)
        if self.y_axes_locked:
             first_visible_base_y = self.base_y_ranges.get(first_chan_id)
             if first_visible_base_y: self._update_scrollbar_from_view(self.global_y_scrollbar, first_visible_base_y, first_visible_base_y)
             else: self._reset_scrollbar(self.global_y_scrollbar)
             for scrollbar in self.individual_y_scrollbars.values(): self._reset_scrollbar(scrollbar)
        else:
             for chan_id, scrollbar in self.individual_y_scrollbars.items():
                 base_y = self.base_y_ranges.get(chan_id)
                 if chan_id in visible_plots_dict and base_y: self._update_scrollbar_from_view(scrollbar, base_y, base_y)
                 else: self._reset_scrollbar(scrollbar)
             self._reset_scrollbar(self.global_y_scrollbar)

        log.debug("Reset View: Sliders reset, scrollbars updated."); self._update_limit_fields(); self._update_y_controls_visibility(); self._update_zoom_scroll_enable_state(); self._update_ui_state()

    def _reset_all_sliders(self):
        """Resets X, Global Y, and all Individual Y sliders to the default value."""
        sliders = [self.x_zoom_slider, self.global_y_slider] + list(self.individual_y_sliders.values());
        for slider in sliders: slider.blockSignals(True); slider.setValue(self.SLIDER_DEFAULT_VALUE); slider.blockSignals(False)

    def _reset_single_plot_view(self, chan_id: str):
        """Resets Y-axis zoom/pan for only one specific channel plot, respecting manual limits."""
        if self.manual_limits_enabled: log.debug(f"Ignoring reset single plot view for {chan_id} (manual limits ON)."); return
        plot_item = self.channel_plots.get(chan_id);
        if not plot_item or not plot_item.isVisible(): return
        log.debug(f"Resetting single plot view (Y-axis) for {chan_id}"); vb = plot_item.getViewBox(); vb.enableAutoRange(axis=pg.ViewBox.YAxis); new_y_range = None
        try: new_y_range = vb.viewRange()[1]; self.base_y_ranges[chan_id] = new_y_range; log.debug(f"Reset Single View: New base Y for {chan_id}: {new_y_range}")
        except Exception as e: log.error(f"Reset Single View: Error getting base Y for {chan_id}: {e}");
        if chan_id in self.base_y_ranges: del self.base_y_ranges[chan_id]
        slider = self.individual_y_sliders.get(chan_id);
        if slider: slider.blockSignals(True); slider.setValue(self.SLIDER_DEFAULT_VALUE); slider.blockSignals(False); log.debug(f"Reset Single View: Slider for {chan_id} reset.")
        scrollbar = self.individual_y_scrollbars.get(chan_id);
        if scrollbar:
            if new_y_range: self._update_scrollbar_from_view(scrollbar, new_y_range, new_y_range); log.debug(f"Reset Single View: Scrollbar for {chan_id} updated.")
            else: self._reset_scrollbar(scrollbar)
        if self.y_axes_locked:
            self.global_y_slider.blockSignals(True); self.global_y_slider.setValue(self.SLIDER_DEFAULT_VALUE); self.global_y_slider.blockSignals(False)
            first_visible_plot = next((p for p in self.channel_plots.values() if p.isVisible()), None)
            if first_visible_plot: first_vb = first_visible_plot.getViewBox(); first_chan_id = getattr(first_vb, '_synaptipy_chan_id', None); first_base_y = self.base_y_ranges.get(first_chan_id)
            if first_base_y: self._update_scrollbar_from_view(self.global_y_scrollbar, first_base_y, first_base_y)
            else: self._reset_scrollbar(self.global_y_scrollbar)
            log.debug("Reset Single View: Global Y controls reset/updated.")
        self._update_limit_fields(); self._update_y_controls_visibility()

    # =========================================================================
    # Navigation & Export
    # =========================================================================
    def _next_trial(self):
        if self.current_plot_mode == self.PlotMode.CYCLE_SINGLE and self.max_trials_current_recording > 0 and self.current_trial_index < self.max_trials_current_recording - 1:
            self.current_trial_index += 1; log.debug(f"Next trial: {self.current_trial_index + 1}")
            self._update_plot();
            if self.manual_limits_enabled: self._apply_manual_limits() # Re-apply limits
            self._update_ui_state()
        else: log.debug("Already at last trial.")

    def _prev_trial(self):
        if self.current_plot_mode == self.PlotMode.CYCLE_SINGLE and self.current_trial_index > 0:
            self.current_trial_index -= 1; log.debug(f"Previous trial: {self.current_trial_index + 1}")
            self._update_plot();
            if self.manual_limits_enabled: self._apply_manual_limits() # Re-apply limits
            self._update_ui_state()
        else: log.debug("Already at first trial.")

    def _next_file_folder(self):
        if self.file_list and self.current_file_index < len(self.file_list) - 1:
            self.current_file_index += 1; self._load_and_display_file(self.file_list[self.current_file_index])
        else: log.debug("Next file: Already at last file.")

    def _prev_file_folder(self):
        if self.file_list and self.current_file_index > 0:
            self.current_file_index -= 1; self._load_and_display_file(self.file_list[self.current_file_index])
        else: log.debug("Previous file: Already at first file.")

    def _export_to_nwb(self):
        """Handles the NWB export process including metadata dialog."""
        if not self.current_recording: QtWidgets.QMessageBox.warning(self, "Export Error", "No data loaded."); return
        default_filename = self.current_recording.source_file.with_suffix(".nwb").name
        output_path_str, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Save NWB", default_filename, "NWB Files (*.nwb)")
        if not output_path_str: self.statusBar.showMessage("NWB export cancelled.", 3000); return
        output_path = Path(output_path_str); default_id = str(uuid.uuid4()); default_time = self.current_recording.session_start_time_dt or datetime.now()
        if default_time.tzinfo is None:
            try: local_tz = tzlocal.get_localzone() if tzlocal else timezone.utc
            except Exception: local_tz = timezone.utc
            default_time = default_time.replace(tzinfo=local_tz)
        dialog = NwbMetadataDialog(default_id, default_time, self);
        if dialog.exec() == QtWidgets.QDialog.Accepted: session_metadata = dialog.get_metadata();
        else: self.statusBar.showMessage("NWB export cancelled.", 3000); return
        if session_metadata is None: return
        self.statusBar.showMessage(f"Exporting NWB..."); QtWidgets.QApplication.processEvents()
        try: self.nwb_exporter.export(self.current_recording, output_path, session_metadata); log.info(f"Exported NWB to {output_path}"); self.statusBar.showMessage(f"Export successful: {output_path.name}", 5000); QtWidgets.QMessageBox.information(self, "Export Successful", f"Saved to:\n{output_path}")
        except (ValueError, ExportError, SynaptipyError) as e: log.error(f"NWB Export failed: {e}", exc_info=False); self.statusBar.showMessage(f"NWB Export failed: {e}", 5000); QtWidgets.QMessageBox.critical(self, "NWB Export Error", f"Failed to export:\n{e}")
        except Exception as e: log.error(f"Unexpected NWB Export error: {e}", exc_info=True); self.statusBar.showMessage("Unexpected NWB Export error.", 5000); QtWidgets.QMessageBox.critical(self, "NWB Export Error", f"Unexpected error:\n{e}")

    # =========================================================================
    # Multi-Trial Selection
    # =========================================================================
    def _update_selected_trials_display(self):
        """Updates the QLabel showing the selected trial indices."""
        if not self.selected_trial_indices: self.selected_trials_display.setText("Selected: None")
        else: sorted_indices = sorted(list(self.selected_trial_indices)); display_text = "Selected: " + ", ".join(str(i + 1) for i in sorted_indices); self.selected_trials_display.setText(display_text)

    def _toggle_select_current_trial(self):
        """Adds or removes the current trial index from the selection set."""
        if not self.current_recording or self.current_plot_mode != self.PlotMode.CYCLE_SINGLE: log.warning("Cannot select trial: Not in cycle mode or no data."); return
        if not (0 <= self.current_trial_index < self.max_trials_current_recording): log.error(f"Invalid current trial index ({self.current_trial_index}) for selection."); return
        idx = self.current_trial_index
        if idx in self.selected_trial_indices: self.selected_trial_indices.remove(idx); log.debug(f"Removed trial {idx+1}"); self.statusBar.showMessage(f"Trial {idx+1} removed.", 2000)
        else: self.selected_trial_indices.add(idx); log.debug(f"Added trial {idx+1}"); self.statusBar.showMessage(f"Trial {idx+1} added.", 2000)
        if self.selected_average_plot_items:
            log.debug("Selection changed, removing old average plot."); self._remove_selected_average_plots()
            self.show_selected_average_button.blockSignals(True); self.show_selected_average_button.setChecked(False); self.show_selected_average_button.blockSignals(False)
        self._update_selected_trials_display(); self._update_ui_state()

    def _clear_avg_selection(self):
        """Clears the selected trial set and removes the average plot if shown."""
        log.debug("Clearing trial selection.");
        if not self.selected_trial_indices: return
        if self.selected_average_plot_items: self._remove_selected_average_plots(); self.show_selected_average_button.blockSignals(True); self.show_selected_average_button.setChecked(False); self.show_selected_average_button.blockSignals(False)
        self.selected_trial_indices.clear(); self.statusBar.showMessage("Trial selection cleared.", 2000); self._update_selected_trials_display(); self._update_ui_state()

    def _toggle_plot_selected_average(self, checked):
        """Slot connected to the 'Plot/Hide Selected Avg' toggle button."""
        log.debug(f"Toggle plot selected average: {'Checked' if checked else 'Unchecked'}")
        if checked: self._plot_selected_average() # Might uncheck button if fails
        else: self._remove_selected_average_plots()
        self._update_ui_state() # Update button text

    def _plot_selected_average(self):
        """Calculates and plots the average of selected trials for visible channels."""
        # --- Pre-conditions ---
        if not self.selected_trial_indices or not self.current_recording:
            log.warning("Cannot plot selected average: No selection or data."); self.statusBar.showMessage("Select trials first.", 3000)
            self.show_selected_average_button.blockSignals(True); self.show_selected_average_button.setChecked(False); self.show_selected_average_button.blockSignals(False); return
        if self.selected_average_plot_items: log.debug("Avg already plotted."); self.show_selected_average_button.blockSignals(True); self.show_selected_average_button.setChecked(True); self.show_selected_average_button.blockSignals(False); return

        log.info(f"Plotting average of trials (0-based): {sorted(list(self.selected_trial_indices))}")
        plotted_any_avg = False
        first_selected_idx = next(iter(sorted(self.selected_trial_indices)))
        ref_tvec = None
        ref_chan_id_for_tvec = None

        # --- Determine Reference Time Vector --- ## CORRECTED TRY/EXCEPT STRUCTURE ##
        for chan_id, plot_item in self.channel_plots.items():
            if plot_item.isVisible():
                channel = self.current_recording.channels.get(chan_id)
                if channel and 0 <= first_selected_idx < channel.num_trials:
                    tvec_candidate = None # Initialize before try block
                    try:
                        # Only the potentially failing call goes in the try block
                        tvec_candidate = channel.get_relative_time_vector(first_selected_idx)
                    except Exception as e:
                        # Handle potential error during get_relative_time_vector
                        log.warning(f"Error getting tvec from ch {chan_id}, trial {first_selected_idx+1}: {e}")
                        continue # Skip to the next channel if error getting tvec

                    # Check the result *after* the try-except block
                    if tvec_candidate is not None:
                        ref_tvec = tvec_candidate
                        ref_chan_id_for_tvec = chan_id
                        log.debug(f"Using time vector from channel '{ref_chan_id_for_tvec}', trial {first_selected_idx+1}.")
                        break # Found a valid time vector, exit the loop
        # --- END CORRECTION ---

        # --- Check if ref_tvec was found ---
        if ref_tvec is None:
            log.error("Could not determine a reference time vector for the selected average. Cannot plot.")
            QtWidgets.QMessageBox.warning(self, "Plot Error", "Could not find a valid time vector for the selected trials among visible channels.")
            self.show_selected_average_button.blockSignals(True); self.show_selected_average_button.setChecked(False); self.show_selected_average_button.blockSignals(False)
            return

        # --- Calculate and Plot Average for Each Visible Channel ---
        ds_threshold = VisConstants.DOWNSAMPLING_THRESHOLD if VisConstants else 1000
        enable_ds = self.downsample_checkbox.isChecked()
        for chan_id, plot_item in self.channel_plots.items():
            if plot_item.isVisible():
                channel = self.current_recording.channels.get(chan_id)
                if not channel: continue
                valid_trial_data = []
                for trial_idx in self.selected_trial_indices:
                    if 0 <= trial_idx < channel.num_trials:
                        try:
                            data = channel.get_data(trial_idx)
                            if data is not None and len(data) == len(ref_tvec):
                                valid_trial_data.append(data)
                            elif data is not None:
                                log.warning(f"Trial {trial_idx+1} data length mismatch ch {chan_id}.")
                            else:
                                log.warning(f"No data trial {trial_idx+1} ch {chan_id}.")
                        except Exception as e:
                            log.error(f"Error getting data trial {trial_idx+1}, ch {chan_id}: {e}")
                    else:
                        log.warning(f"Selected trial {trial_idx+1} out of bounds ch {chan_id}.")

                if not valid_trial_data:
                    log.warning(f"No valid data for averaging ch {chan_id}.")
                    continue
                try:
                    selected_avg_data = np.mean(np.array(valid_trial_data), axis=0)
                    avg_di = plot_item.plot(ref_tvec, selected_avg_data, pen=self.SELECTED_AVG_PEN)
                    avg_di.opts['autoDownsample'] = enable_ds
                    if enable_ds: avg_di.opts['autoDownsampleThreshold'] = ds_threshold
                    self.selected_average_plot_items[chan_id] = avg_di
                    plotted_any_avg = True
                    log.debug(f"Plotted selected avg ch {chan_id}")
                except Exception as e:
                    log.error(f"Error plotting avg ch {chan_id}: {e}", exc_info=True)

        # --- Post-plotting ---
        if not plotted_any_avg:
             log.warning("Failed to plot selected average for any channel."); QtWidgets.QMessageBox.warning(self, "Plot Warning", "Could not plot average for any visible channel.")
             self.show_selected_average_button.blockSignals(True); self.show_selected_average_button.setChecked(False); self.show_selected_average_button.blockSignals(False)
        else:
             self.statusBar.showMessage("Selected average plotted.", 2500)


    def _remove_selected_average_plots(self):
        """Removes any currently displayed selected average plots from all channels."""
        if not self.selected_average_plot_items: return
        log.debug(f"Removing {len(self.selected_average_plot_items)} avg plot(s)."); removed_count = 0
        for chan_id, avg_di in self.selected_average_plot_items.items():
            plot_item = self.channel_plots.get(chan_id)
            if plot_item and avg_di in plot_item.items:
                try: plot_item.removeItem(avg_di); removed_count += 1
                except Exception as e: log.warning(f"Could not remove avg item {chan_id}: {e}")
        if removed_count > 0: log.debug(f"Removed {removed_count} avg items."); self.statusBar.showMessage("Selected average hidden.", 2000)
        self.selected_average_plot_items.clear()

    # =========================================================================
    # Manual Limits
    # =========================================================================
    def _parse_limit_value(self, text: str) -> Optional[float]:
        """Safely parses text from a QLineEdit into a float."""
        if not text or text.lower() == "auto": return None
        try: return float(text)
        except ValueError: return None

    def _on_set_limits_clicked(self):
        """Reads values from limit fields, validates, and stores them."""
        log.debug("Set Manual Limits button clicked.")
        if not all([self.manual_limit_x_min_edit, self.manual_limit_x_max_edit, self.manual_limit_y_min_edit, self.manual_limit_y_max_edit]): log.error("Manual limit QLineEdit elements not initialized."); return
        x_min = self._parse_limit_value(self.manual_limit_x_min_edit.text()); x_max = self._parse_limit_value(self.manual_limit_x_max_edit.text())
        y_min = self._parse_limit_value(self.manual_limit_y_min_edit.text()); y_max = self._parse_limit_value(self.manual_limit_y_max_edit.text())
        valid_x = False; valid_y = False
        if x_min is not None and x_max is not None:
            if x_min < x_max: self.manual_x_limits = (x_min, x_max); valid_x = True; log.info(f"Stored manual X limits: {self.manual_x_limits}")
            else: QtWidgets.QMessageBox.warning(self, "Input Error", "X Min must be less than X Max."); self.manual_x_limits = None
        else: self.manual_x_limits = None
        if y_min is not None and y_max is not None:
            if y_min < y_max: self.manual_y_limits = (y_min, y_max); valid_y = True; log.info(f"Stored manual Y limits: {self.manual_y_limits}")
            else: QtWidgets.QMessageBox.warning(self, "Input Error", "Y Min must be less than Y Max."); self.manual_y_limits = None
        else: self.manual_y_limits = None
        if valid_x or valid_y:
            self.statusBar.showMessage("Manual limits stored.", 3000)
            if self.manual_limits_enabled: log.debug("Applying newly set limits."); self._apply_manual_limits()
        else: self.statusBar.showMessage("Invalid or incomplete limits entered.", 3000)

    def _on_manual_limits_toggled(self, checked: bool):
        """Handles enabling/disabling the manual limit mode."""
        self.manual_limits_enabled = checked
        log.info(f"Manual plot limits {'ENABLED' if checked else 'DISABLED'}.")
        self.statusBar.showMessage(f"Manual plot limits {'ENABLED' if checked else 'DISABLED'}.", 2000)
        if checked:
            if self.manual_x_limits is None and self.manual_y_limits is None:
                 log.debug("Manual limits enabled, but none stored. Trying to set from fields.")
                 self._on_set_limits_clicked() # Try to parse/store from fields now
                 if self.manual_x_limits is None and self.manual_y_limits is None:
                      log.warning("No valid manual limits. Cannot enable."); QtWidgets.QMessageBox.warning(self, "Enable Failed", "No valid limits set. Enter limits and click 'Set' first.")
                      self.enable_manual_limits_checkbox.blockSignals(True); self.enable_manual_limits_checkbox.setChecked(False); self.enable_manual_limits_checkbox.blockSignals(False); self.manual_limits_enabled = False; return
            self._apply_manual_limits() # Apply stored/newly set limits
        else: # Disabling
            self._update_zoom_scroll_enable_state() # Re-enable controls *before* resetting
            log.debug("Manual limits disabled. Resetting view to auto-range.")
            self._reset_view() # This will now auto-range
        self._update_ui_state() # Update reset button enable state etc.

    def _apply_manual_limits(self):
        """Applies the stored manual X/Y limits to all visible plots."""
        if not self.manual_limits_enabled: log.warning("_apply_manual_limits called but disabled."); return
        log.debug(f"Applying manual limits: X={self.manual_x_limits}, Y={self.manual_y_limits}")
        applied_x = False; applied_y = False; self._updating_viewranges = True
        try:
            for plot in self.channel_plots.values():
                if plot.isVisible(): vb = plot.getViewBox()
                if self.manual_x_limits: vb.setXRange(self.manual_x_limits[0], self.manual_x_limits[1], padding=0); applied_x = True
                if self.manual_y_limits: vb.setYRange(self.manual_y_limits[0], self.manual_y_limits[1], padding=0); applied_y = True
        finally: self._updating_viewranges = False
        if applied_x or applied_y:
             log.debug("Manual limits applied."); self._update_limit_fields() # Update fields to show applied limits
             # Update scrollbars to reflect full manual range (should disable them)
             if applied_x and self.manual_x_limits: self._update_scrollbar_from_view(self.x_scrollbar, self.manual_x_limits, self.manual_x_limits)
             if applied_y and self.manual_y_limits:
                  self._update_scrollbar_from_view(self.global_y_scrollbar, self.manual_y_limits, self.manual_y_limits)
                  for sb in self.individual_y_scrollbars.values(): self._update_scrollbar_from_view(sb, self.manual_y_limits, self.manual_y_limits)
        self._update_zoom_scroll_enable_state() # Disable interactive controls

    def _update_zoom_scroll_enable_state(self):
        """Enables/disables zoom/scroll widgets based on manual_limits_enabled flag."""
        enable_controls = not self.manual_limits_enabled
        log.debug(f"Updating zoom/scroll enable state: {'Enabled' if enable_controls else 'Disabled'}")
        self.x_zoom_slider.setEnabled(enable_controls)
        self.global_y_slider.setEnabled(enable_controls and self.y_axes_locked)
        for slider in self.individual_y_sliders.values(): slider.setEnabled(enable_controls and not self.y_axes_locked)
        if not enable_controls:
             self.x_scrollbar.setEnabled(False); self.global_y_scrollbar.setEnabled(False)
             for sb in self.individual_y_scrollbars.values(): sb.setEnabled(False)
        # Mouse Interaction
        for plot in self.channel_plots.values():
             if plot and plot.getViewBox(): plot.getViewBox().setMouseEnabled(x=enable_controls, y=enable_controls)
        # Reset View Button
        has_visible_plots = any(p.isVisible() for p in self.channel_plots.values())
        self.reset_view_button.setEnabled(has_visible_plots and enable_controls)

    def _update_limit_fields(self):
        """Updates the QLineEdit fields with the current view range or manual limits."""
        if self._updating_limit_fields: return

        x_range_str = ("Auto", "Auto"); y_range_str = ("Auto", "Auto")
        if self.manual_limits_enabled:
             if self.manual_x_limits: x_range_str = (f"{self.manual_x_limits[0]:.4g}", f"{self.manual_x_limits[1]:.4g}")
             if self.manual_y_limits: y_range_str = (f"{self.manual_y_limits[0]:.4g}", f"{self.manual_y_limits[1]:.4g}")
        else:
             first_visible_plot = next((p for p in self.channel_plots.values() if p.isVisible()), None)
             if first_visible_plot:
                 try:
                     vb = first_visible_plot.getViewBox(); x_range = vb.viewRange()[0]; y_range = vb.viewRange()[1]
                     x_range_str = (f"{x_range[0]:.4g}", f"{x_range[1]:.4g}")
                     y_range_str = (f"{y_range[0]:.4g}", f"{y_range[1]:.4g}")
                 except Exception as e: log.warning(f"Could not get view range: {e}"); x_range_str = ("N/A", "N/A"); y_range_str = ("N/A", "N/A")

        self._updating_limit_fields = True
        try:
            if self.manual_limit_x_min_edit: self.manual_limit_x_min_edit.setText(x_range_str[0])
            if self.manual_limit_x_max_edit: self.manual_limit_x_max_edit.setText(x_range_str[1])
            if self.manual_limit_y_min_edit: self.manual_limit_y_min_edit.setText(y_range_str[0])
            if self.manual_limit_y_max_edit: self.manual_limit_y_max_edit.setText(y_range_str[1])
        finally: self._updating_limit_fields = False

    def _update_limit_fields_from_vb(self, axis: str):
        """Slot for ViewBox signals to trigger field update (with delay)."""
        if not self.manual_limits_enabled and not self._updating_limit_fields:
            QtCore.QTimer.singleShot(50, self._update_limit_fields)

    # =========================================================================
    # Close Event
    # =========================================================================
    def closeEvent(self, event: QtGui.QCloseEvent):
        """Clean up resources before closing."""
        log.info("Close event triggered. Shutting down GUI.")
        try:
             if self.graphics_layout_widget: self.graphics_layout_widget.clear()
        except Exception as e: log.warning(f"Error clearing graphics layout on close: {e}")
        log.info("Accepting close event.")
        event.accept()
# --- MainWindow Class --- END ---


# --- Main Execution Block ---
if __name__ == '__main__':
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    logging.basicConfig(level=logging.DEBUG, format=log_format)
    log.info("Application starting...")

    if not SYNAPTIPY_AVAILABLE:
        log.warning("*"*30)
        log.warning(" Running with DUMMY Synaptipy classes! ")
        log.warning(" Functionality will be simulated. ")
        log.warning("*"*30)
        # Dummy classes already assigned above

    app = QtWidgets.QApplication(sys.argv)

    try:
        import qdarkstyle
        # Try different qdarkstyle loading methods for compatibility
        style = None
        if hasattr(qdarkstyle, 'load_stylesheet'): style = qdarkstyle.load_stylesheet(qt_api='pyside6')
        elif hasattr(qdarkstyle, 'load_stylesheet_pyside6'): style = qdarkstyle.load_stylesheet_pyside6()
        # Add more checks if needed for future versions
        if style: app.setStyleSheet(style); log.info("Applied qdarkstyle theme.")
        else: log.warning("qdarkstyle found but could not determine loading method.")
    except ImportError: log.info("qdarkstyle not found, using default style.")
    except Exception as e: log.warning(f"Could not apply qdarkstyle: {e}")

    try:
        window = MainWindow()
        window.show()
        log.info("Main window created and shown.")
    except Exception as e:
         log.critical(f"Failed to initialize or show MainWindow: {e}", exc_info=True)
         sys.exit(1)

    log.info("Starting Qt event loop...")
    sys.exit(app.exec())