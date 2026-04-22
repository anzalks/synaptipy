# src/Synaptipy/application/gui/analysis_tabs/metadata_driven.py
# -*- coding: utf-8 -*-
"""
Generic Analysis Tab that generates its UI from metadata.

This module provides a generic implementation of BaseAnalysisTab that can
adapt to any registered analysis function by reading its metadata (ui_params)
from the AnalysisRegistry.  It also provides built-in support for:

* **method_selector**: switching between multiple registered analysis functions
  within a single tab (e.g. Event Detection methods).
* **Interactive event markers**: click-to-remove, Ctrl+click-to-add scatter
  points for manual curation of detected events.
* **Draggable threshold lines**: horizontal lines synced with a parameter widget.
* **Popup plots**: secondary plot windows for I-V curves, phase-plane loops, etc.
* **Result-aware h-lines**: horizontal lines positioned by result dict keys.
"""

import logging
from typing import Any, Dict, List, Optional

import numpy as np
import pyqtgraph as pg
from PySide6 import QtCore, QtWidgets

from Synaptipy.application.gui.analysis_tabs.base import BaseAnalysisTab
from Synaptipy.core.analysis.registry import AnalysisRegistry
from Synaptipy.shared.plot_customization import get_hv_line_pen, get_scatter_pen_and_brush

log = logging.getLogger(__name__)


class MetadataDrivenAnalysisTab(BaseAnalysisTab):
    """
    A generic analysis tab that builds its UI entirely from AnalysisRegistry
    metadata.  Supports single-analysis and multi-method-selector modes.
    """

    def __init__(self, analysis_name: str, neo_adapter, settings_ref=None, parent=None):
        """
        Initialize the metadata-driven tab.

        Args:
            analysis_name: The name of the registered analysis function.
            neo_adapter: NeoAdapter instance.
            settings_ref: QSettings reference.
            parent: Parent widget.
        """
        self.analysis_name = analysis_name
        self.metadata = AnalysisRegistry.get_metadata(analysis_name)
        # Stable module-level identity - never overwritten by method-selector switching.
        self._module_name: str = analysis_name
        self._module_metadata: Dict[str, Any] = AnalysisRegistry.get_metadata(analysis_name)
        self.param_widgets: Dict[str, QtWidgets.QWidget] = {}
        self._popup_windows = []
        self._interactive_regions = {}
        self._syncing_regions = False
        self._region_mode_combo: Optional[QtWidgets.QComboBox] = None

        # --- Method selector state (populated from metadata "method_selector") ---
        self._method_map: Dict[str, str] = {}  # display_label -> registry_name
        self.method_combobox: Optional[QtWidgets.QComboBox] = None

        # --- Secondary channel selector (for TTL/trigger channels) ---
        self._secondary_channel_combobox: Optional[QtWidgets.QComboBox] = None
        self._secondary_channel_param_name: Optional[str] = None

        # --- Interactive region spinbox tracking: start_key -> end_key ---
        self._region_spinbox_keys: Dict[str, str] = {}

        # --- Interactive event-marker state ---
        self._current_event_indices: List[int] = []
        self._event_markers_item: Optional[pg.ScatterPlotItem] = None
        self._artifact_curve_item: Optional[pg.PlotCurveItem] = None

        # --- Draggable threshold line ---
        self._threshold_line: Optional[pg.InfiniteLine] = None

        # --- Result h-lines ---
        self._result_hlines: Dict[str, pg.InfiniteLine] = {}

        # --- Popup plot handles ---
        self._popup_plot: Optional[pg.PlotItem] = None
        self._popup_curves: Dict[str, Any] = {}

        super().__init__(neo_adapter, settings_ref, parent)
        self._setup_ui()
        self._setup_interactive_regions()
        # Module-level aggregator entries have no ui_params of their own;
        # immediately prime the first sub-analysis so the tab is non-blank.
        if self._method_map and not self.metadata.get("ui_params"):
            self._on_method_selector_changed()

    @property
    def response_region(self):
        """
        Plot region used for response/baseline window analyses (interactive
        LinearRegionItems or the green restrict-analysis region from the base tab).
        """
        interactive = getattr(self, "_interactive_regions", None) or {}
        for key in ("response_start", "response_start_s", "baseline_start", "baseline_start_s"):
            region = interactive.get(key)
            if region is not None:
                return region
        if interactive:
            return next(iter(interactive.values()))
        return getattr(self, "analysis_region", None)

    def _trace_package_ready(self, data: Any) -> bool:
        """True if *data* is the plot trace dict (``data`` / ``time`` arrays) used by core analysis."""
        if not isinstance(data, dict):
            return False
        arr = data.get("data")
        tim = data.get("time")
        if arr is None or tim is None:
            return False
        try:
            if len(arr) == 0 or len(tim) == 0:
                return False
        except TypeError:
            return False
        return True

    def get_registry_name(self) -> str:
        # Always return the original module/aggregator name, not the active sub-method.
        return self._module_name

    def get_display_name(self) -> str:
        # Use the module-level label, which is stable across method-selector changes.
        return self._module_metadata.get("label", self._module_name.replace("_", " ").title())

    def get_covered_analysis_names(self) -> List[str]:
        """Return all registry names this tab covers (including method selector alternatives)."""
        names = [self._module_name]
        names.extend(self._method_map.values())
        return list(set(names))

    def _setup_ui(self):
        """Setup the UI components dynamically based on metadata."""
        main_layout = QtWidgets.QHBoxLayout(self)

        # --- Create Splitter ---
        splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        main_layout.addWidget(splitter)

        # --- Left Control Panel (wrapped in scroll area for small screens) ---
        scroll_area = QtWidgets.QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setMinimumWidth(250)

        control_panel = QtWidgets.QWidget()
        control_layout = QtWidgets.QVBoxLayout(control_panel)
        control_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)

        # Global controls container (will be populated by AnalyserTab)
        self.global_controls_layout = QtWidgets.QVBoxLayout()
        control_layout.addLayout(self.global_controls_layout)

        # Channel Selection & Data Source (Standard for all tabs)
        self._setup_data_selection_ui(control_layout)

        # --- Preprocessing Widget ---
        # Explicitly place it here (after Data Source, before Params)
        if self.preprocessing_widget:
            control_layout.addWidget(self.preprocessing_widget)
            self.preprocessing_widget.setVisible(True)

        # Parameters Group
        params_group = QtWidgets.QGroupBox("Parameters")
        # Use a VBoxLayout for the group to stack permanent and generated layouts
        params_group_layout = QtWidgets.QVBoxLayout(params_group)

        # 1. Permanent/Custom Controls Layout (Hook for subclasses)
        self.permanent_params_layout = QtWidgets.QFormLayout()
        params_group_layout.addLayout(self.permanent_params_layout)

        # Separator (Optional)
        line = QtWidgets.QFrame()
        line.setFrameShape(QtWidgets.QFrame.Shape.HLine)
        line.setFrameShadow(QtWidgets.QFrame.Shadow.Sunken)
        params_group_layout.addWidget(line)

        # 2. Generated Parameters Layout
        self.generated_params_layout = QtWidgets.QFormLayout()
        params_group_layout.addLayout(self.generated_params_layout)

        # Use ParameterWidgetGenerator on the GENERATED layout
        from Synaptipy.application.gui.ui_generator import ParameterWidgetGenerator

        self.param_generator = ParameterWidgetGenerator(self.generated_params_layout)

        ui_params = self.metadata.get("ui_params", [])
        self.param_generator.generate_widgets(ui_params, self._on_param_changed)

        # Hook for subclasses to add extra controls (e.g. Method Selector)
        # We pass the PERMANENT params layout so they are NOT deleted by generator updates
        self._setup_additional_controls(self.permanent_params_layout)

        # 3. Reset Button
        reset_btn = QtWidgets.QPushButton("Reset Parameters")
        reset_btn.setToolTip("Reset all parameters to default values")
        reset_btn.clicked.connect(self.reset_parameters)
        params_group_layout.addWidget(reset_btn)

        control_layout.addWidget(params_group)

        # Results Group
        results_group = QtWidgets.QGroupBox("Results")
        self.results_layout = QtWidgets.QFormLayout(results_group)
        self.results_labels: Dict[str, QtWidgets.QLabel] = {}

        # We don't know the result keys ahead of time, so we'll add them dynamically
        # or we could add a text area for generic output
        # self.results_text = QtWidgets.QTextEdit()
        # self.results_text.setReadOnly(True)
        # self.results_text.setMaximumHeight(150)
        # self.results_layout.addRow(self.results_text)

        self.results_table = QtWidgets.QTableWidget()
        self.results_table.setColumnCount(2)
        self.results_table.setHorizontalHeaderLabels(["Metric", "Value"])
        self.results_table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Stretch)
        self.results_table.verticalHeader().setVisible(False)
        self.results_table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.results_table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self.results_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.results_table.setAlternatingRowColors(True)
        self.results_table.setMinimumHeight(250)
        self.results_layout.addRow(self.results_table)

        control_layout.addWidget(results_group)

        # Status Label
        self.status_label = QtWidgets.QLabel("Ready")
        control_layout.addWidget(self.status_label)

        # Save Button
        self._setup_save_button(control_layout)

        # Accumulation UI
        self._setup_accumulation_ui(control_layout)

        control_layout.addStretch()

        # Set the control panel as the scroll area widget
        scroll_area.setWidget(control_panel)

        # Add scroll area to splitter (instead of control_panel directly)
        splitter.addWidget(scroll_area)

        # --- Right Plot Area ---
        plot_container = QtWidgets.QWidget()
        plot_layout = QtWidgets.QVBoxLayout(plot_container)
        self._setup_plot_area(plot_layout, stretch_factor=0)  # Stretch handled by splitter
        splitter.addWidget(plot_container)

        # Set Splitter Sizes (1/3 Left, 2/3 Right)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)

        # Basic plot setup
        if self.plot_widget:
            self.plot_widget.showGrid(x=True, y=True)
            self._setup_custom_plot_items()

    def reset_parameters(self):
        """Reset generated parameters to defaults defined in metadata."""
        if hasattr(self, "param_generator") and self.metadata:
            ui_params = self.metadata.get("ui_params", [])
            # Re-generating widgets will reset them to defaults
            self.param_generator.generate_widgets(ui_params, self._on_param_changed)
            self._setup_interactive_regions()
            # Also notify any changes
            self._on_param_changed()

        # If subclass has custom logic for reset (e.g. RinTab logic), trigger it
        if hasattr(self, "_on_channel_changed"):
            # Re-apply mode logic
            self._on_channel_changed()

    def _setup_additional_controls(self, layout: QtWidgets.QFormLayout):
        """
        Auto-generate extra controls from metadata.

        Supports:
        * ``method_selector``: dict mapping display labels to registry names.
          Renders a QComboBox that switches the active analysis function and
          rebuilds the generated parameter widgets on each change.
        * ``requires_secondary_channel``: dict with ``param_name``, ``label``,
          and optional ``tooltip``.  Renders a channel selector combo that
          provides a secondary data channel (e.g. TTL/trigger) to the
          analysis function.
        """
        method_selector = self.metadata.get("method_selector")
        if method_selector and isinstance(method_selector, dict):
            self._method_map = dict(method_selector)  # copy

            self.method_combobox = QtWidgets.QComboBox()
            self.method_combobox.addItems(list(self._method_map.keys()))
            self.method_combobox.setToolTip("Choose the analysis algorithm.")
            self.method_combobox.currentIndexChanged.connect(self._on_method_selector_changed)
            layout.addRow("Method:", self.method_combobox)

            # "Run" button (useful for event detection where auto-run may be slow)
            analyze_btn = QtWidgets.QPushButton("Run Analysis")
            analyze_btn.setToolTip("Run the analysis with current parameters")
            analyze_btn.clicked.connect(self._trigger_analysis)
            layout.addRow("", analyze_btn)

        # --- Secondary channel selector (e.g. TTL channel for optogenetics) ---
        sec_chan = self.metadata.get("requires_secondary_channel")
        if sec_chan and isinstance(sec_chan, dict):
            self._secondary_channel_param_name = sec_chan.get("param_name", "secondary_data")
            label = sec_chan.get("label", "Secondary Channel:")
            tooltip = sec_chan.get("tooltip", "Select a secondary data channel.")

            self._secondary_channel_combobox = QtWidgets.QComboBox()
            self._secondary_channel_combobox.setToolTip(tooltip)
            self._secondary_channel_combobox.setEnabled(False)
            self._secondary_channel_combobox.currentIndexChanged.connect(self._on_param_changed)
            layout.addRow(label, self._secondary_channel_combobox)

        # --- Region selection mode (Interactive / Manual) ---
        # Auto-detect: if this analysis has paired start/end region params,
        # offer a mode selector so the user can toggle draggable regions.
        region_param_names = [
            ("baseline_start", "baseline_end"),
            ("baseline_start_s", "baseline_end_s"),
            ("response_start", "response_end"),
            ("response_start_s", "response_end_s"),
            ("response_peak_start_s", "response_peak_end_s"),
            ("response_steady_start_s", "response_steady_end_s"),
        ]
        ui_param_names = {p.get("name") for p in self.metadata.get("ui_params", [])}
        has_regions = any(s in ui_param_names and e in ui_param_names for s, e in region_param_names)
        if has_regions:
            self._region_mode_combo = QtWidgets.QComboBox()
            self._region_mode_combo.addItems(["Interactive", "Manual"])
            self._region_mode_combo.setToolTip(
                "Interactive: drag regions on the plot to set windows.\n"
                "Manual: type start/end values in the spinboxes directly."
            )
            self._region_mode_combo.currentIndexChanged.connect(self._on_region_mode_changed)
            layout.addRow("Region Mode:", self._region_mode_combo)

    def _on_method_selector_changed(self):  # noqa: C901
        """Handle switching between analysis methods via the method combo box."""
        if not self.method_combobox:
            return
        display_label = self.method_combobox.currentText()
        registry_key = self._method_map.get(display_label)
        if not registry_key:
            return

        log.debug(f"Switching analysis method to: {registry_key}")
        self.analysis_name = registry_key
        self.metadata = AnalysisRegistry.get_metadata(registry_key)

        # Rebuild generated parameter widgets
        if hasattr(self, "param_generator"):
            ui_params = self.metadata.get("ui_params", [])
            self.param_generator.generate_widgets(ui_params, self._on_param_changed)

        # Re-setup interactive regions for the new parameter set
        self._setup_interactive_regions()

        # Show/hide the secondary channel row based on the new sub-analysis metadata
        if hasattr(self, "_secondary_channel_combobox") and self._secondary_channel_combobox is not None:
            sec_cfg = self.metadata.get("requires_secondary_channel")
            show_sec = bool(sec_cfg and isinstance(sec_cfg, dict))
            try:
                if hasattr(self, "permanent_params_layout"):
                    self.permanent_params_layout.setRowVisible(self._secondary_channel_combobox, show_sec)
            except RuntimeError:
                pass

        # Clear previous results
        if self.results_table:
            self.results_table.setRowCount(0)
        self._current_event_indices = []
        if self._event_markers_item:
            self._event_markers_item.setData(x=[], y=[])
            self._event_markers_item.setVisible(False)
        if self._artifact_curve_item:
            self._artifact_curve_item.setData([], [])
            self._artifact_curve_item.setVisible(False)

    def _setup_custom_plot_items(self):
        """
        Create persistent plot items based on metadata ``plots`` list.

        Recognised persistent types (created once, updated per-analysis):
        * ``event_markers`` — interactive scatter (click remove / ctrl-click add)
        * ``threshold_line`` — draggable horizontal line synced w/ a param widget
        * ``artifact_overlay`` — curve item for artifact mask visualisation
        """
        if not self.plot_widget:
            return

        plots_meta = self.metadata.get("plots", [])

        for pcfg in plots_meta:
            ptype = pcfg.get("type")

            if ptype == "event_markers":
                self._event_markers_item = pg.ScatterPlotItem(
                    size=10, pen=pg.mkPen(None), brush=pg.mkBrush(255, 0, 0, 150)
                )
                self.plot_widget.addItem(self._event_markers_item)
                self._event_markers_item.setVisible(False)
                self._event_markers_item.setZValue(100)
                self._event_markers_item.sigClicked.connect(self._on_event_marker_clicked)
                self.plot_widget.scene().sigMouseClicked.connect(self._on_plot_ctrl_clicked)

            elif ptype == "threshold_line":
                param_key = pcfg.get("param", "threshold")
                self._threshold_line = pg.InfiniteLine(
                    angle=0, movable=True, pen=pg.mkPen("b", style=QtCore.Qt.PenStyle.DashLine)
                )
                self.plot_widget.addItem(self._threshold_line)
                self._threshold_line.setZValue(90)

                def _on_threshold_dragged(pk=param_key):
                    val = self._threshold_line.value()
                    if hasattr(self, "param_generator") and pk in self.param_generator.widgets:
                        w = self.param_generator.widgets[pk]
                        blocked = w.blockSignals(True)
                        if isinstance(w, QtWidgets.QDoubleSpinBox):
                            w.setValue(val)
                        w.blockSignals(blocked)
                        self._on_param_changed()

                self._threshold_line.sigPositionChangeFinished.connect(_on_threshold_dragged)

            elif ptype == "artifact_overlay":
                self._artifact_curve_item = pg.PlotCurveItem(pen=pg.mkPen(color=(60, 179, 113, 200), width=3))
                self.plot_widget.addItem(self._artifact_curve_item)
                self._artifact_curve_item.setVisible(False)
                self._artifact_curve_item.setZValue(80)

    def _setup_interactive_regions(self):  # noqa: C901
        """Setup pg.LinearRegionItem for window parameters if they exist."""
        if not self.plot_widget:
            return

        # Clear old regions
        for region in self._interactive_regions.values():
            if region in self.plot_widget.items:
                self.plot_widget.removeItem(region)

        self._interactive_regions.clear()

        if not hasattr(self, "param_generator"):
            return

        widgets = self.param_generator.widgets

        # Helper to bind a region to start/end spinboxes
        def bind_region(start_key, end_key, color_tuple):
            if start_key in widgets and end_key in widgets:
                start_w = widgets[start_key]
                end_w = widgets[end_key]

                region = pg.LinearRegionItem(
                    values=[start_w.value(), end_w.value()],
                    brush=pg.mkBrush(*color_tuple, 50),
                    pen=pg.mkPen(*color_tuple, 200),
                )
                self.plot_widget.addItem(region)
                self._interactive_regions[start_key] = region

                def update_spinboxes():
                    if self._syncing_regions:
                        return
                    self._syncing_regions = True
                    minX, maxX = region.getRegion()
                    start_w.setValue(minX)
                    end_w.setValue(maxX)
                    # Manually trigger param change since setValue blocks signal if unchanged?
                    # valueChanged will fire, which triggers _on_param_changed via param_generator
                    self._syncing_regions = False

                region.sigRegionChangeFinished.connect(update_spinboxes)

                def update_region():
                    if self._syncing_regions:
                        return
                    self._syncing_regions = True
                    region.setRegion([start_w.value(), end_w.value()])
                    self._syncing_regions = False

                start_w.valueChanged.connect(update_region)
                end_w.valueChanged.connect(update_region)

        # Track pairs so _apply_region_mode can enable/disable them
        self._region_spinbox_keys.clear()

        def bind_region_tracked(start_key, end_key, color_tuple):
            bind_region(start_key, end_key, color_tuple)
            if start_key in widgets and end_key in widgets:
                self._region_spinbox_keys[start_key] = end_key

        bind_region_tracked("baseline_start_s", "baseline_end_s", (0, 0, 255))
        bind_region_tracked("response_start_s", "response_end_s", (255, 0, 0))
        bind_region_tracked("response_peak_start_s", "response_peak_end_s", (255, 165, 0))  # Orange
        bind_region_tracked("response_steady_start_s", "response_steady_end_s", (0, 255, 0))  # Green

        # Also bind Rin-style param names (without _s suffix)
        bind_region_tracked("baseline_start", "baseline_end", (0, 0, 255))
        bind_region_tracked("response_start", "response_end", (255, 0, 0))

        # Apply region mode visibility
        self._apply_region_mode()

    def _on_region_mode_changed(self, _index=None):
        """Toggle interactive region items visible/hidden."""
        self._apply_region_mode()
        self._on_param_changed()

    def _apply_region_mode(self):
        """Show/hide interactive region items and enable/disable paired spinboxes."""
        if not self._region_mode_combo:
            return
        interactive = self._region_mode_combo.currentText() == "Interactive"
        for region in self._interactive_regions.values():
            region.setVisible(interactive)
        # In Interactive mode the draggable regions control the spinboxes,
        # so disable direct editing of them to avoid confusion.
        widgets = self.param_generator.widgets if hasattr(self, "param_generator") else {}
        for start_key, end_key in self._region_spinbox_keys.items():
            for key in (start_key, end_key):
                w = widgets.get(key)
                if w is not None:
                    # QDoubleSpinBox: setReadOnly exists
                    if hasattr(w, "setReadOnly"):
                        w.setReadOnly(interactive)
                    else:
                        w.setEnabled(not interactive)

    # ------------------------------------------------------------------
    # Interactive event-marker helpers
    # ------------------------------------------------------------------

    def _ensure_custom_items_on_plot(self):
        """Re-add persistent plot items after ``plot_widget.clear()``."""
        if not self.plot_widget:
            return
        if self._event_markers_item and self._event_markers_item not in self.plot_widget.items:
            self.plot_widget.addItem(self._event_markers_item)
            self._event_markers_item.setZValue(100)
        if self._threshold_line and self._threshold_line not in self.plot_widget.items:
            self.plot_widget.addItem(self._threshold_line)
            self._threshold_line.setZValue(90)
        if self._artifact_curve_item and self._artifact_curve_item not in self.plot_widget.items:
            self.plot_widget.addItem(self._artifact_curve_item)
            self._artifact_curve_item.setZValue(80)
        # Re-add any result h-lines
        for line in self._result_hlines.values():
            if line not in self.plot_widget.items:
                self.plot_widget.addItem(line)
        # Re-add interactive regions
        for region in self._interactive_regions.values():
            if region not in self.plot_widget.items:
                self.plot_widget.addItem(region)
        # Re-apply region mode visibility
        self._apply_region_mode()

    def _on_event_marker_clicked(self, scatter, points, ev):
        """Remove event marker on click (curation)."""
        if len(points) == 0:
            return
        ev.accept()

        pos = points[0].pos()
        clicked_time = pos.x()
        if not self._current_plot_data:
            return
        times = self._current_plot_data["time"]
        dt = times[1] - times[0] if len(times) > 1 else 0.001
        tolerance = dt * 1.5

        for i, e_idx in enumerate(self._current_event_indices):
            if e_idx < len(times) and abs(times[e_idx] - clicked_time) <= tolerance:
                self._current_event_indices.pop(i)
                break

        self._refresh_event_markers()

    def _on_plot_ctrl_clicked(self, ev):
        """Add event marker on Ctrl+click."""
        if not ev.modifiers() & QtCore.Qt.KeyboardModifier.ControlModifier:
            return
        if not self._current_plot_data or self._event_markers_item is None:
            return

        pos = self.plot_widget.plotItem.vb.mapSceneToView(ev.scenePos())
        clicked_time = pos.x()
        times = self._current_plot_data["time"]
        if clicked_time < times[0] or clicked_time > times[-1]:
            return

        idx = int(np.argmin(np.abs(times - clicked_time)))
        if idx not in self._current_event_indices:
            self._current_event_indices.append(idx)
            self._current_event_indices.sort()
            self._refresh_event_markers()

    def _refresh_event_markers(self):
        """Redraw markers based on ``_current_event_indices``."""
        if not self._current_plot_data or self._event_markers_item is None:
            return
        indices = np.array(self._current_event_indices, dtype=int)
        if len(indices) > 0:
            times = self._current_plot_data["time"][indices]
            volts = self._current_plot_data["data"][indices]
            self._event_markers_item.setData(x=times, y=volts)
            self._event_markers_item.setVisible(True)
        else:
            self._event_markers_item.setData(x=[], y=[])
            self._event_markers_item.setVisible(False)

        # Update results table with curated stats
        self._update_curated_event_table()

    def _get_specific_result_data(self) -> Optional[Dict[str, Any]]:
        """Return the last analysis result for saving."""
        # For metadata-driven tabs, the result is usually a dictionary or object
        # If it's an object, we might need to convert it to a dict
        log.debug(
            f"{self.__class__.__name__}._get_specific_result_data: _last_analysis_result is None? "
            f"{self._last_analysis_result is None}"
        )
        if not self._last_analysis_result:
            log.warning(
                f"{self.__class__.__name__}._get_specific_result_data: returning None because "
                f"_last_analysis_result is falsy"
            )
            return None

        # Start with the result data
        if hasattr(self._last_analysis_result, "__dict__"):
            result = dict(self._last_analysis_result.__dict__)
        elif isinstance(self._last_analysis_result, dict):
            result = dict(self._last_analysis_result)  # Copy to avoid modifying original
        else:
            # Fallback for simple types
            result = {"result": self._last_analysis_result}

        # CRITICAL: Add data_source key which is required by _request_save_result
        if self.data_source_combobox and self.data_source_combobox.isEnabled():
            data_source = self.data_source_combobox.currentData()
            result["data_source"] = data_source

        return result

    def _update_ui_for_selected_item(self):
        """Update UI when a new item is selected."""
        # Base class handles population of channel/source combos now
        # We just need to ensure plot is cleared if nothing selected
        if not self._selected_item_recording:
            if self.plot_widget:
                self.plot_widget.clear()

        # Populate secondary channel combobox if configured
        self._populate_secondary_channel_combobox()

        # Update visibility based on new item context
        self._update_parameter_visibility()

    def _populate_secondary_channel_combobox(self):
        """Populate the secondary channel combobox from the current recording."""
        if not self._secondary_channel_combobox:
            return
        self._secondary_channel_combobox.blockSignals(True)
        self._secondary_channel_combobox.clear()

        # Add a "None" option for when no secondary channel is needed
        self._secondary_channel_combobox.addItem("(None)", userData=None)

        if self._selected_item_recording and self._selected_item_recording.channels:
            for chan_id, channel in sorted(self._selected_item_recording.channels.items()):
                units = getattr(channel, "units", "")
                display_name = f"{channel.name or f'Ch {chan_id}'} ({chan_id}) [{units}]"
                self._secondary_channel_combobox.addItem(display_name, userData=chan_id)
            self._secondary_channel_combobox.setEnabled(True)
        else:
            self._secondary_channel_combobox.setEnabled(False)

        self._secondary_channel_combobox.blockSignals(False)

    def _inject_secondary_channel_data(self, params: Dict[str, Any], data: Dict[str, Any]):
        """Load data from the secondary channel and inject it into params.

        When *requires_secondary_channel* metadata is configured and the
        user has selected a valid secondary channel, this method reads the
        raw data from that channel (same data-source / trial as the primary)
        and stores it in ``params[param_name]`` so the analysis wrapper
        receives it via **kwargs.
        """
        if (
            not self._secondary_channel_combobox
            or not self._secondary_channel_param_name
            or not self._selected_item_recording
        ):
            return

        sec_chan_id = self._secondary_channel_combobox.currentData()
        if sec_chan_id is None:
            return  # user chose "(None)"

        channel = self._selected_item_recording.channels.get(sec_chan_id)
        if channel is None:
            log.warning("Secondary channel '%s' not found in recording.", sec_chan_id)
            return

        # Determine which trial / data-source the primary channel is using
        trial_index = 0
        if self.data_source_combobox:
            ds = self.data_source_combobox.currentData()
            if isinstance(ds, int):
                trial_index = ds
            elif ds == "average":
                # Use average of the secondary channel if available
                avg = getattr(channel, "average_data", None)
                if avg is not None:
                    params[self._secondary_channel_param_name] = avg
                    return
                # Fall back to trial 0
                trial_index = 0

        sec_data = channel.get_data(trial_index)
        if sec_data is not None:
            params[self._secondary_channel_param_name] = sec_data
        else:
            log.warning(
                "Could not load data from secondary channel '%s' trial %d.",
                sec_chan_id,
                trial_index,
            )

    def _on_channel_changed(self, index=None):
        """Handle channel selection change."""
        # Trigger visibility update (channel units might have changed)
        self._update_parameter_visibility()

        # BaseAnalysisTab._plot_selected_data calls _on_data_plotted hook.
        # We can trigger analysis there.
        pass

    def _update_parameter_visibility(self):
        """Calculate context and update parameter visibility."""
        if not hasattr(self, "param_generator"):
            return

        context = {}

        # 1. Determine Clamp Mode
        # Logic: If channel units contain 'A' (Amps), it's Voltage Clamp (measuring Current)
        # If channel units contain 'V' (Volts), it's Current Clamp (measuring Voltage)
        # Default to Current Clamp if unknown

        is_voltage_clamp = False

        if self.signal_channel_combobox:
            # Get channel name string
            channel_name = self.signal_channel_combobox.currentData()

            # Fetch channel object
            channel = None
            if (
                channel_name
                and self._selected_item_recording
                and channel_name in self._selected_item_recording.channels
            ):
                channel = self._selected_item_recording.channels[channel_name]

            if channel:
                units = channel.units or "V"
                if "A" in units or "amp" in units.lower():
                    is_voltage_clamp = True

        context["clamp_mode"] = "voltage_clamp" if is_voltage_clamp else "current_clamp"

        # Update generator
        try:
            self.param_generator.update_visibility(context)
        except RuntimeError:
            pass  # UI is being torn down or rebuilt — safe to ignore

    def _on_data_plotted(self):
        """Hook called after data is plotted - re-add persistent items then trigger analysis.

        Uses the debounce timer so the visibility gate in ``_trigger_analysis``
        recognises this as an automatic trigger and defers when the tab is hidden.
        """
        self._ensure_custom_items_on_plot()
        if self._analysis_debounce_timer:
            self._analysis_debounce_timer.start(self._debounce_delay_ms)

    def _on_param_changed(self):
        """Handle parameter changes."""
        # Re-evaluate visibility in case a choice/bool param controls others
        if hasattr(self, "param_generator"):
            self._update_parameter_visibility()
        if self._analysis_debounce_timer:
            self._analysis_debounce_timer.start(self._debounce_delay_ms)

    def _gather_analysis_parameters(self) -> Dict[str, Any]:
        """Gather parameters from UI widgets, with clamp-mode-aware overrides."""
        params = self.param_generator.gather_params()

        # Rin-style clamp-mode exclusivity: zero out the irrelevant stimulus
        if self.analysis_name == "rin_analysis":
            is_voltage_clamp = False
            if self.signal_channel_combobox:
                channel_name = self.signal_channel_combobox.currentData()
                if (
                    channel_name
                    and self._selected_item_recording
                    and channel_name in self._selected_item_recording.channels
                ):
                    ch = self._selected_item_recording.channels[channel_name]
                    units = ch.units or "V"
                    if "A" in units or "amp" in units.lower():
                        is_voltage_clamp = True
            if is_voltage_clamp:
                params["current_amplitude"] = 0.0
            else:
                params["voltage_step"] = 0.0

        return params

    def _update_curated_event_table(self):
        """Update the results table with curated event stats (used by event markers)."""
        if not self.results_table:
            return
        count = len(self._current_event_indices)
        if count == 0:
            self.results_table.setRowCount(1)
            self.results_table.setItem(0, 0, QtWidgets.QTableWidgetItem("Status"))
            self.results_table.setItem(0, 1, QtWidgets.QTableWidgetItem("No Events"))
            return
        if not self._current_plot_data:
            return

        indices = np.array(self._current_event_indices, dtype=int)
        try:
            amplitudes = self._current_plot_data["data"][indices]
        except IndexError:
            return

        duration = self._current_plot_data["time"][-1] - self._current_plot_data["time"][0]
        freq = count / duration if duration > 0 else 0.0
        mean_amp = float(np.mean(amplitudes))
        amp_sd = float(np.std(amplitudes))

        method_label = ""
        if self.method_combobox:
            method_label = self.method_combobox.currentText() + " (Curated)"

        display_items = []
        if method_label:
            display_items.append(("Method", method_label))
        display_items += [
            ("Count", str(count)),
            ("Frequency", f"{freq:.2f} Hz"),
            ("Mean Amplitude", f"{mean_amp:.2f} ± {amp_sd:.2f}"),
        ]
        if self._threshold_line and self._threshold_line.isVisible():
            display_items.append(("Threshold", f"{self._threshold_line.value():.2f}"))

        self.results_table.setRowCount(len(display_items))
        for row, (k, v) in enumerate(display_items):
            self.results_table.setItem(row, 0, QtWidgets.QTableWidgetItem(k))
            self.results_table.setItem(row, 1, QtWidgets.QTableWidgetItem(v))

    def _execute_core_analysis(self, params: Dict[str, Any], data: Dict[str, Any]) -> Dict[str, Any]:  # noqa: C901
        """Run the registered analysis function."""
        func = AnalysisRegistry.get_function(self.analysis_name)
        if not func:
            # The analysis was unregistered (e.g. plugin hot-reload in progress).
            # Return None so the caller exits quietly without showing an error popup.
            log.debug(f"_execute_core_analysis: '{self.analysis_name}' not in registry — skipping silently.")
            return None

        # Check if the analysis requires all trials
        metadata = AnalysisRegistry.get_metadata(self.analysis_name)
        requires_multi_trial = metadata.get("requires_multi_trial", False)

        # --- Inject secondary channel data if configured ---
        self._inject_secondary_channel_data(params, data)

        try:
            if requires_multi_trial and self._selected_item_recording and self.signal_channel_combobox:
                # Fetch all trials systematically
                chan_id = self.signal_channel_combobox.currentData()
                channel = self._selected_item_recording.channels.get(chan_id)
                if not channel:
                    raise ValueError(f"Channel {chan_id} not found for multi-trial analysis.")

                num_trials = getattr(channel, "num_trials", 0)
                if num_trials == 0:
                    num_trials = len(getattr(channel, "data_trials", []))
                if num_trials == 0:
                    num_trials = getattr(channel, "trial_count", 0)

                if num_trials == 0:
                    raise ValueError("No trials found in the selected channel.")

                data_list = []
                time_list = []
                fs = data.get("sampling_rate", 10000.0)

                for i in range(num_trials):
                    trial_data = channel.get_data(i)
                    trial_time = channel.get_relative_time_vector(i)

                    if trial_data is not None and trial_time is not None:
                        # Apply any global preprocessing if active
                        if hasattr(self, "_active_preprocessing_settings") and self._active_preprocessing_settings:
                            if hasattr(self, "pipeline"):
                                processed = self.pipeline.process(trial_data, fs, trial_time)
                                if processed is not None:
                                    trial_data = processed

                        data_list.append(trial_data)
                        time_list.append(trial_time)

                if not data_list:
                    raise ValueError("Failed to load trial data.")

                # Call the function with lists
                results = func(data_list, time_list, fs, **params)
            else:
                # Standard single-trial execution
                voltage = data["data"]
                time = data["time"]
                fs = data["sampling_rate"]

                # Call the function with single arrays
                results = func(voltage, time, fs, **params)

            # Normalise: wrap non-dict returns; flatten metrics nesting from new 5-module format
            if isinstance(results, list):
                return {"module_used": self.analysis_name, "metrics": {"list_results": results}}
            elif isinstance(results, dict):
                # If returned dict already has module_used/metrics, pass through
                if "module_used" in results or "metrics" in results:
                    return results
                # Wrap legacy flat dict in standard payload
                return {"module_used": self.analysis_name, "metrics": results}
            else:
                return {"module_used": self.analysis_name, "metrics": {"result": results}}

        except Exception as e:
            log.error(f"Analysis execution failed: {e}")
            raise

    def _display_analysis_results(self, results: Dict[str, Any]):  # noqa: C901
        """
        Display analysis results in text area.
        Implements abstract method from BaseAnalysisTab.
        """
        if not self.results_table:
            return

        try:
            # Flatten nested {"module_used": ..., "metrics": {...}} schema for display
            display_source = results
            if isinstance(results, dict) and "metrics" in results:
                display_source = results["metrics"]

            # Also flatten legacy {"result": {...}} single-key wrappers
            if isinstance(display_source, dict) and list(display_source.keys()) == ["result"]:
                inner = display_source["result"]
                if isinstance(inner, dict):
                    display_source = inner
                elif hasattr(inner, "__dict__"):
                    display_source = inner.__dict__

            # robust extraction of items
            items = []
            if isinstance(display_source, dict):
                items = list(display_source.items())
            elif hasattr(display_source, "__dict__"):
                items = [(k, v) for k, v in display_source.__dict__.items() if not k.startswith("_")]
            else:
                # Fallback
                items = [("Result", str(display_source))]

            # Filter out complex objects like arrays for the simple table view
            display_items = []
            for k, v in items:
                try:
                    # Skip internal/private keys (prefixed with _)
                    if str(k).startswith("_"):
                        continue

                    # Skip complex iterables entirely
                    if isinstance(v, (list, np.ndarray, dict)):
                        continue

                    # Sanitize Key
                    key_str = str(k).replace("_", " ").title()

                    # Sanitize Value: format floats to 3 decimal places
                    if isinstance(v, float):
                        if np.isnan(v) or np.isinf(v):
                            val_str = str(v)
                        else:
                            val_str = f"{v:.3f}"
                    elif isinstance(v, bool):
                        val_str = str(v)
                    elif isinstance(v, int):
                        val_str = str(v)
                    elif isinstance(v, str):
                        val_str = v
                    else:
                        # Unknown scalar type — stringify
                        val_str = str(v)

                    display_items.append((key_str, val_str))
                except Exception as e:
                    log.warning(f"Skipping result item {k}: {e}")
                    continue

            self.results_table.setRowCount(len(display_items))
            self.results_table.setColumnCount(2)  # Ensure column count

            for row, (k, v) in enumerate(display_items):
                key_item = QtWidgets.QTableWidgetItem(k)
                val_item = QtWidgets.QTableWidgetItem(v)

                self.results_table.setItem(row, 0, key_item)
                self.results_table.setItem(row, 1, val_item)

        except Exception as e:
            log.error(f"Error displaying results: {e}")
            # Fallback to simple popup if table fails
            self.results_table.setRowCount(1)

        # --- Sync Rin spinboxes if auto-detect was used and returned window values ---
        # Check both flat and nested metrics format
        _results_flat = results.get("metrics", results) if isinstance(results, dict) else results
        if isinstance(_results_flat, dict) and _results_flat.get("auto_detected") and hasattr(self, "param_generator"):
            spinbox_map = {
                "_used_baseline_start": "baseline_start",
                "_used_baseline_end": "baseline_end",
                "_used_response_start": "response_start",
                "_used_response_end": "response_end",
            }
            widgets = self.param_generator.widgets
            for result_key, param_key in spinbox_map.items():
                val = _results_flat.get(result_key)
                if val is not None and param_key in widgets:
                    w = widgets[param_key]
                    was_read_only = getattr(w, "isReadOnly", lambda: False)()
                    if was_read_only and hasattr(w, "setReadOnly"):
                        w.setReadOnly(False)
                    blocked = w.blockSignals(True)
                    w.setValue(val)
                    w.blockSignals(blocked)
                    if was_read_only and hasattr(w, "setReadOnly"):
                        w.setReadOnly(True)

    def _plot_analysis_visualizations(self, results: Dict[str, Any]):  # noqa: C901
        """
        Dynamically plot visualizations based on registry metadata ``plots`` list.

        Supported plot types
        --------------------
        trace            — (default) nothing extra on the main plot
        markers          — scatter points at (x_key, y_key) from result
        brackets         — horizontal bracket lines for burst groups
        vlines / hlines  — infinite lines at result-derived positions
        interactive_region — draggable region bound to param widgets
        event_markers    — interactive scatter (curation, threshold line, artifact)
        threshold_line   — draggable h-line (handled in _setup_custom_plot_items)
        artifact_overlay — curve overlay (handled in _setup_custom_plot_items)
        result_hlines    — h-lines positioned by named result keys
        popup_xy         — scatter + optional fit line in a popup window
        popup_phase      — phase-plane (dV/dt vs V) popup with markers
        """
        if not self.plot_widget:
            return

        self._ensure_custom_items_on_plot()

        # Clear generic dynamic items
        if not hasattr(self, "_dynamic_plot_items"):
            self._dynamic_plot_items = []

        for item in self._dynamic_plot_items:
            if item in self.plot_widget.items:
                self.plot_widget.removeItem(item)
        self._dynamic_plot_items.clear()

        # Normalise result structure – support both new {"module_used", "metrics"} and legacy formats
        if isinstance(results, dict) and "metrics" in results:
            result_item = results["metrics"]
        elif isinstance(results, dict) and "result" in results:
            result_item = results["result"]
        else:
            result_item = results

        plots_meta = self.metadata.get("plots", [])

        for plot_cfg in plots_meta:
            plot_type = plot_cfg.get("type")

            # --- simple markers ---
            if plot_type == "markers":
                self._viz_markers(plot_cfg, result_item)

            # --- brackets (bursts) ---
            elif plot_type == "brackets":
                self._viz_brackets(plot_cfg, result_item)

            # --- vertical lines ---
            elif plot_type == "vlines":
                self._viz_vlines(plot_cfg, result_item)

            # --- horizontal lines ---
            elif plot_type == "hlines":
                self._viz_hlines(plot_cfg, result_item)

            # --- interactive region ---
            elif plot_type == "interactive_region":
                self._viz_interactive_region(plot_cfg)

            # --- event markers (interactive curation) ---
            elif plot_type == "event_markers":
                self._viz_event_markers(plot_cfg, result_item)

            # --- threshold line update ---
            elif plot_type == "threshold_line":
                self._viz_threshold_line(plot_cfg, result_item)

            # --- artifact overlay ---
            elif plot_type == "artifact_overlay":
                self._viz_artifact_overlay(plot_cfg, result_item)

            # --- result-driven h-lines (e.g. baseline/response voltage) ---
            elif plot_type == "result_hlines":
                self._viz_result_hlines(plot_cfg, result_item)

            # --- popup scatter / line (I-V curve) ---
            elif plot_type == "popup_xy":
                self._viz_popup_xy(plot_cfg, result_item)

            # --- popup phase-plane ---
            elif plot_type == "popup_phase":
                self._viz_popup_phase(plot_cfg, result_item)

            # --- overlay fit curve (e.g. tau exponential) ---
            elif plot_type == "overlay_fit":
                self._viz_overlay_fit(plot_cfg, result_item)

            # --- trace region highlight overlay ---
            elif plot_type == "trace_overlay":
                self._viz_trace_overlay(plot_cfg, result_item)

            # --- event bi-exponential fit curve ---
            elif plot_type == "event_fit_overlay":
                self._viz_event_fit_overlay(plot_cfg, result_item)

            # --- shaded fill-between two curves ---
            # Pass full results so top-level private array keys (_int_x etc.) are found
            elif plot_type == "fill_between":
                self._viz_fill_between(plot_cfg, results)

            # trace — optional spike markers overlay
            elif plot_type == "trace":
                if plot_cfg.get("show_spikes") and self._current_plot_data:
                    spike_idx = self._val(result_item, "spike_indices")
                    if spike_idx is not None and len(spike_idx) > 0:
                        time_arr = self._current_plot_data["time"]
                        data_arr = self._current_plot_data["data"]
                        valid = np.array(spike_idx, dtype=int)
                        valid = valid[(valid >= 0) & (valid < len(data_arr))]
                        if len(valid) > 0:
                            scatter = pg.ScatterPlotItem(
                                x=time_arr[valid],
                                y=data_arr[valid],
                                size=8,
                                pen=pg.mkPen(None),
                                brush=pg.mkBrush(255, 0, 0, 180),
                            )
                            scatter.setZValue(50)
                            self.plot_widget.addItem(scatter)
                            self._dynamic_plot_items.append(scatter)

                if plot_cfg.get("show_events") and self._current_plot_data:
                    ev_times = self._val(result_item, "event_times")
                    if ev_times is not None and len(ev_times) > 0:
                        time_arr = self._current_plot_data["time"]
                        data_arr = self._current_plot_data["data"]
                        # Map float times → nearest sample indices
                        ev_arr = np.asarray(ev_times)
                        idx = np.searchsorted(time_arr, ev_arr, side="left")
                        idx = np.clip(idx, 0, len(time_arr) - 1)
                        # For each insertion point, also check the element to
                        # the left and keep whichever is closer in time.
                        prev = np.clip(idx - 1, 0, len(time_arr) - 1)
                        idx = np.where(
                            np.abs(time_arr[prev] - ev_arr) < np.abs(time_arr[idx] - ev_arr),
                            prev,
                            idx,
                        )
                        scatter = pg.ScatterPlotItem(
                            x=time_arr[idx],
                            y=data_arr[idx],
                            size=10,
                            pen=pg.mkPen(None),
                            brush=pg.mkBrush(255, 165, 0, 200),
                            symbol="t",
                        )
                        scatter.setZValue(50)
                        self.plot_widget.addItem(scatter)
                        self._dynamic_plot_items.append(scatter)

    # ------------------------------------------------------------------
    # Visualisation helpers (called by _plot_analysis_visualizations)
    # ------------------------------------------------------------------

    def _val(self, obj, key, default=None):
        """Extract a value from either a dict or an object attribute."""
        if key is None:
            return default
        if isinstance(obj, dict):
            return obj.get(key, default)
        if isinstance(key, str) and hasattr(obj, key):
            return getattr(obj, key)
        return default

    def _viz_markers(self, cfg, result):
        x_key = cfg.get("x")
        y_key = cfg.get("y")
        x_data = self._val(result, x_key)
        if x_data is None and isinstance(result, dict) and "metrics" in result:
            x_data = result["metrics"].get(x_key)
        y_data = self._val(result, y_key)
        if y_data is None and isinstance(result, dict) and "metrics" in result:
            y_data = result["metrics"].get(y_key)
        if x_data is None:
            x_data = []
        if y_data is None:
            y_data = []
        if hasattr(x_data, "__len__") and hasattr(y_data, "__len__") and len(x_data) > 0 and len(y_data) > 0:
            try:
                x_arr = np.asarray(x_data, dtype=float)
                y_arr = np.asarray(y_data, dtype=float)
                valid = ~(np.isnan(x_arr) | np.isnan(y_arr))
                x_arr, y_arr = x_arr[valid], y_arr[valid]
                if len(x_arr) == 0:
                    return
            except (ValueError, TypeError):
                return
            color = cfg.get("color")
            symbol = cfg.get("symbol", "o")
            if color is None:
                scatter_pen, scatter_brush = get_scatter_pen_and_brush()
                scatter_size = 10
            else:
                scatter_pen = pg.mkPen(None)
                scatter_brush = pg.mkBrush(color)
                scatter_size = 10
            scatter = pg.ScatterPlotItem(
                x=x_arr, y=y_arr, size=scatter_size, symbol=symbol, pen=scatter_pen, brush=scatter_brush
            )
            self.plot_widget.addItem(scatter)
            self._dynamic_plot_items.append(scatter)

    def _viz_brackets(self, cfg, result):
        data_key = cfg.get("data")
        bursts = self._val(result, data_key, [])
        if not bursts:
            return
        y_offset = 0
        if self._current_plot_data:
            try:
                y_offset = float(np.max(self._current_plot_data["data"])) + 10
            except Exception:
                y_offset = 50
        color = cfg.get("color", "r")
        for burst_spikes in bursts:
            if len(burst_spikes) >= 2:
                item = pg.PlotCurveItem(
                    [burst_spikes[0], burst_spikes[-1]], [y_offset, y_offset], pen=pg.mkPen(color, width=3)
                )
                self.plot_widget.addItem(item)
                self._dynamic_plot_items.append(item)
                if self._current_plot_data:
                    tv = self._current_plot_data["time"]
                    vv = self._current_plot_data["data"]
                    si = np.clip(np.searchsorted(tv, burst_spikes), 0, len(vv) - 1)
                    scatter = pg.ScatterPlotItem(
                        x=burst_spikes, y=vv[si], size=8, pen=pg.mkPen(None), brush=pg.mkBrush(color)
                    )
                    self.plot_widget.addItem(scatter)
                    self._dynamic_plot_items.append(scatter)

    def _viz_vlines(self, cfg, result):
        data_key = cfg.get("data")
        vals = self._val(result, data_key, [])
        color = cfg.get("color")
        if isinstance(vals, (int, float)):
            vals = [vals]
        for x in vals:
            try:
                if x is None or not np.isfinite(float(x)):
                    continue
            except (TypeError, ValueError):
                continue
            if color is None:
                pen = get_hv_line_pen()
            else:
                pen = pg.mkPen(color, width=2, style=QtCore.Qt.DashLine)
            line = pg.InfiniteLine(pos=float(x), angle=90, pen=pen)
            self.plot_widget.addItem(line)
            self._dynamic_plot_items.append(line)

    def _viz_hlines(self, cfg, result):
        data_keys = cfg.get("data", [])
        if isinstance(data_keys, str):
            data_keys = [data_keys]
        color = cfg.get("color", "r")
        styles = cfg.get("styles", ["solid"] * len(data_keys))
        for idx, key in enumerate(data_keys):
            y = self._val(result, key)
            try:
                if y is None or not np.isfinite(float(y)):
                    continue
            except (TypeError, ValueError):
                continue
            s = styles[idx] if idx < len(styles) else "solid"
            ps = QtCore.Qt.DashLine if s == "dash" else QtCore.Qt.SolidLine
            line = pg.InfiniteLine(pos=float(y), angle=0, pen=pg.mkPen(color, width=2, style=ps))
            self.plot_widget.addItem(line)
            self._dynamic_plot_items.append(line)

    def _viz_interactive_region(self, cfg):
        if getattr(self, "_interactive_region_created", False):
            return
        param_keys = cfg.get("data", ["baseline_start", "baseline_end"])
        # Read initial values from param widgets if available
        start_val = 0.0
        end_val = 0.1
        if hasattr(self, "param_generator") and len(param_keys) >= 2:
            widgets = self.param_generator.widgets
            if param_keys[0] in widgets:
                start_val = float(widgets[param_keys[0]].value())
            if param_keys[1] in widgets:
                end_val = float(widgets[param_keys[1]].value())
        region = pg.LinearRegionItem(
            values=[start_val, end_val],
            orientation="vertical",
            brush=pg.mkBrush(50, 50, 200, 50),
            pen=pg.mkPen(50, 50, 200, 150),
            movable=True,
        )
        self.plot_widget.addItem(region)
        self._dynamic_plot_items.append(region)
        self._interactive_region_created = True

        def on_region_changed():
            mn, mx = region.getRegion()
            if hasattr(self, "param_generator") and len(param_keys) >= 2:
                widgets = self.param_generator.widgets
                if param_keys[0] in widgets:
                    widgets[param_keys[0]].setValue(mn)
                if param_keys[1] in widgets:
                    widgets[param_keys[1]].setValue(mx)
                self._on_param_changed()

        region.sigRegionChangeFinished.connect(on_region_changed)

    def _viz_event_markers(self, cfg, result):
        """Update interactive event markers from result."""
        # Unwrap _result_obj stored inside a metrics dict
        if isinstance(result, dict) and "_result_obj" in result:
            result = result["_result_obj"]
        is_obj = hasattr(result, "event_indices")
        event_indices = (
            result.event_indices if is_obj else (result.get("event_indices") if isinstance(result, dict) else None)
        )

        if event_indices is not None:
            self._current_event_indices = list(np.array(event_indices, dtype=int))
            self._refresh_event_markers()
        else:
            self._current_event_indices = []
            if self._event_markers_item:
                self._event_markers_item.setVisible(False)

    def _viz_threshold_line(self, cfg, result):
        """Update threshold line position from result."""
        threshold_val = self._val(result, "threshold") or self._val(result, "threshold_value")
        if threshold_val is not None and self._threshold_line:
            self._threshold_line.setValue(threshold_val)
            self._threshold_line.setVisible(True)
        elif self._threshold_line:
            self._threshold_line.setVisible(False)

    def _viz_artifact_overlay(self, cfg, result):
        """Draw artifact mask as a green overlay on the trace."""
        if not self._artifact_curve_item:
            return
        artifact_mask = self._val(result, "artifact_mask")
        if artifact_mask is not None and self._current_plot_data:
            full_data = self._current_plot_data["data"]
            full_time = self._current_plot_data["time"]
            if len(full_data) == len(artifact_mask):
                overlay = full_data.copy().astype(float)
                overlay[~artifact_mask] = np.nan
                self._artifact_curve_item.setData(full_time, overlay, connect="finite")
                self._artifact_curve_item.setVisible(True)
            else:
                self._artifact_curve_item.setVisible(False)
        else:
            self._artifact_curve_item.setVisible(False)

    def _viz_result_hlines(self, cfg, result):
        """Draw h-lines from named result keys (e.g. baseline_voltage_mv)."""
        keys = cfg.get("keys", [])
        colors = cfg.get("colors", {})  # mapping key -> color string
        for key in keys:
            y = self._val(result, key)
            if y is not None and not np.isnan(y):
                color = colors.get(key, "b")
                if key not in self._result_hlines:
                    line = pg.InfiniteLine(angle=0, pen=pg.mkPen(color, style=QtCore.Qt.PenStyle.DashLine))
                    self.plot_widget.addItem(line)
                    self._result_hlines[key] = line
                self._result_hlines[key].setValue(y)
                self._result_hlines[key].setVisible(True)
            elif key in self._result_hlines:
                self._result_hlines[key].setVisible(False)

    def _viz_overlay_fit(self, cfg, result):
        """Draw a fit curve overlay on the main plot (e.g. exponential fit for Tau)."""
        x_key = cfg.get("x")
        y_key = cfg.get("y")
        x_data = self._val(result, x_key)
        y_data = self._val(result, y_key)
        if x_data is None or y_data is None:
            return
        try:
            x_arr = np.asarray(x_data, dtype=float)
            y_arr = np.asarray(y_data, dtype=float)
        except (ValueError, TypeError):
            return
        if len(x_arr) < 2 or len(y_arr) < 2:
            return
        if np.all(np.isnan(x_arr)) or np.all(np.isnan(y_arr)):
            return
        color = cfg.get("color", "r")
        width = cfg.get("width", 2)
        pen = pg.mkPen(color, width=width, style=QtCore.Qt.PenStyle.SolidLine)
        curve = pg.PlotCurveItem(x=x_arr, y=y_arr, pen=pen, connect="finite")
        self.plot_widget.addItem(curve)
        self._dynamic_plot_items.append(curve)

    # ------------------------------------------------------------------
    # fill_between helpers
    # ------------------------------------------------------------------

    def _resolve_fill_y2(self, y2_data, y1_len: int) -> np.ndarray:
        """Convert the y2 config value (array, scalar, or None) to a NumPy array."""
        if y2_data is None:
            return np.zeros(y1_len)
        try:
            y2_scalar = float(y2_data)
            return np.full(y1_len, y2_scalar)
        except (TypeError, ValueError):
            pass
        try:
            return np.asarray(y2_data, dtype=float)
        except (ValueError, TypeError):
            return np.zeros(y1_len)

    def _resolve_fill_brush(self, cfg):
        """Return a QBrush from the ``brush`` (RGBA tuple) or ``color`` key in cfg."""
        brush_spec = cfg.get("brush")
        color_spec = cfg.get("color")
        if brush_spec is not None:
            return pg.mkBrush(*brush_spec)
        if color_spec is not None:
            if isinstance(color_spec, (list, tuple)):
                return pg.mkBrush(*color_spec)
            return pg.mkBrush(color_spec)
        return pg.mkBrush(0, 100, 255, 100)

    def _prepare_fill_arrays(self, x_data, y1_data, y2_data):
        """Validate, convert, and NaN-filter arrays for fill_between.

        Returns a ``(x_arr, y1_arr, y2_arr)`` triple or ``None`` when the
        arrays are invalid or entirely NaN.
        """
        try:
            x_arr = np.asarray(x_data, dtype=float)
            y1_arr = np.asarray(y1_data, dtype=float)
        except (ValueError, TypeError):
            return None
        if len(x_arr) < 2 or len(y1_arr) < 2 or len(x_arr) != len(y1_arr):
            return None
        y2_arr = self._resolve_fill_y2(y2_data, len(y1_arr))
        valid = ~(np.isnan(x_arr) | np.isnan(y1_arr) | np.isnan(y2_arr))
        if not np.any(valid):
            return None
        x_arr, y1_arr, y2_arr = x_arr[valid], y1_arr[valid], y2_arr[valid]
        if len(x_arr) < 2:
            return None
        return x_arr, y1_arr, y2_arr

    def _val_with_metrics(self, result, key):
        """Extract *key* from *result* directly, then fall back to result['metrics']."""
        if key is None:
            return None
        val = self._val(result, key)
        if val is None and isinstance(result, dict):
            val = result.get("metrics", {}).get(key)
        return val

    def _viz_fill_between(self, cfg, result):
        """Draw a shaded region between two curves (y1 and y2) along a shared x axis.

        The ``result`` dict is searched directly then inside ``result['metrics']``
        so both flat and nested ``{"module_used", "metrics"}`` schemas are supported.

        Config keys:
            x     -- key for the shared x-axis array (required)
            y1    -- key for the upper/primary curve array (required)
            y2    -- key for the lower/baseline curve, or a scalar (default 0.0)
            brush -- (r, g, b, a) tuple for the fill colour (takes precedence)
            color -- colour string or tuple (used when ``brush`` is not set)
        """
        if not self.plot_widget:
            return

        x_data = self._val_with_metrics(result, cfg.get("x"))
        y1_data = self._val_with_metrics(result, cfg.get("y1"))
        y2_data = self._val_with_metrics(result, cfg.get("y2"))

        if x_data is None or y1_data is None:
            log.debug("_viz_fill_between: missing x or y1 data, skipping.")
            return

        arrays = self._prepare_fill_arrays(x_data, y1_data, y2_data)
        if arrays is None:
            log.debug("_viz_fill_between: arrays invalid or all-NaN, skipping.")
            return

        x_arr, y1_arr, y2_arr = arrays
        brush = self._resolve_fill_brush(cfg)
        pen_none = pg.mkPen(None)

        curve1 = pg.PlotCurveItem(x=x_arr, y=y1_arr, pen=pen_none)
        curve2 = pg.PlotCurveItem(x=x_arr, y=y2_arr, pen=pen_none)
        fill = pg.FillBetweenItem(curve1, curve2, brush=brush)

        # Only add fill to the plot; curve1/curve2 are kept alive via
        # _dynamic_plot_items so FillBetweenItem can reference their data.
        self.plot_widget.addItem(fill)
        self._dynamic_plot_items.extend([curve1, curve2, fill])

    def _viz_trace_overlay(self, cfg, result):
        """Draw a semi-transparent line segment over the raw trace to highlight an analyzed region.

        The overlay spans from ``start_time`` to ``end_time`` on the x-axis.
        Both keys reference float values (seconds) stored in *result*.

        Config keys:
            start_time -- result key (or literal float) for the region start (s).
            end_time   -- result key (or literal float) for the region end (s).
            color      -- pen colour string or (r, g, b) tuple.  Defaults to
                          the ``trace_overlay`` theme colour.
            width      -- pen width in pixels (default 3).
            opacity    -- opacity 0-100 (default 60).
        """
        if not self.plot_widget or not self._current_plot_data:
            return

        start = self._val(result, cfg.get("start_time"))
        end = self._val(result, cfg.get("end_time"))

        # Allow literal scalar values in cfg
        if start is None:
            start = cfg.get("start_time")
        if end is None:
            end = cfg.get("end_time")

        if start is None or end is None:
            return

        try:
            start = float(start)
            end = float(end)
        except (TypeError, ValueError):
            return

        time_arr = self._current_plot_data["time"]
        data_arr = self._current_plot_data["data"]
        mask = (time_arr >= start) & (time_arr <= end)
        if not np.any(mask):
            return

        from Synaptipy.shared.plot_customization import get_plot_customization_manager

        mgr = get_plot_customization_manager()
        overlay_prefs = mgr.defaults.get("trace_overlay", {})

        color = cfg.get("color") or overlay_prefs.get("color", "#00cfff")
        width = int(cfg.get("width", overlay_prefs.get("width", 3)))
        opacity = int(cfg.get("opacity", overlay_prefs.get("opacity", 60)))
        alpha = max(0, min(255, int(opacity / 100.0 * 255)))

        pen = pg.mkPen(color=pg.mkColor(color), width=width)
        pen.setColor(pg.mkColor(color))
        # Apply alpha channel via QColor
        qcolor = pg.mkColor(color)
        qcolor.setAlpha(alpha)
        pen = pg.mkPen(color=qcolor, width=width)

        curve = pg.PlotCurveItem(x=time_arr[mask], y=data_arr[mask], pen=pen)
        curve.setZValue(60)
        self.plot_widget.addItem(curve)
        self._dynamic_plot_items.append(curve)

    def _viz_event_fit_overlay(self, cfg, result):
        """Overlay fitted event curves (e.g. bi-exponential EPSP fits) on the raw trace.

        The result dict must contain arrays of times and fitted values keyed by
        *times_key* and *values_key* respectively.  Multiple events are supported
        when both arrays are lists-of-arrays (one per event).

        Config keys:
            times_key  -- result key for fit time arrays (required).
            values_key -- result key for fit value arrays (required).
            color      -- pen colour.  Defaults to ``event_fit_overlay`` theme colour.
            width      -- pen width in pixels (default 2).
            opacity    -- opacity 0-100 (default 80).
        """
        if not self.plot_widget:
            return

        times_key = cfg.get("times_key", "_event_fit_times")
        values_key = cfg.get("values_key", "_event_fit_values")

        fit_times = self._val(result, times_key)
        fit_values = self._val(result, values_key)

        if fit_times is None or fit_values is None:
            return

        from Synaptipy.shared.plot_customization import get_plot_customization_manager

        mgr = get_plot_customization_manager()
        overlay_prefs = mgr.defaults.get("event_fit_overlay", {})

        color = cfg.get("color") or overlay_prefs.get("color", "#ff9900")
        width = int(cfg.get("width", overlay_prefs.get("width", 2)))
        opacity = int(cfg.get("opacity", overlay_prefs.get("opacity", 80)))
        alpha = max(0, min(255, int(opacity / 100.0 * 255)))

        qcolor = pg.mkColor(color)
        qcolor.setAlpha(alpha)
        pen = pg.mkPen(color=qcolor, width=width)

        # Normalise to list of arrays (handle both single and multi-event cases)
        if isinstance(fit_times, np.ndarray) and fit_times.ndim == 1:
            fit_times_list = [fit_times]
            fit_values_list = [fit_values]
        else:
            fit_times_list = list(fit_times)
            fit_values_list = list(fit_values)

        for t_arr, v_arr in zip(fit_times_list, fit_values_list):
            try:
                t_arr = np.asarray(t_arr, dtype=float)
                v_arr = np.asarray(v_arr, dtype=float)
            except (TypeError, ValueError):
                continue
            if t_arr.size < 2:
                continue
            curve = pg.PlotCurveItem(x=t_arr, y=v_arr, pen=pen)
            curve.setZValue(65)
            self.plot_widget.addItem(curve)
            self._dynamic_plot_items.append(curve)

    def _viz_popup_xy(self, cfg, result):
        """Show scatter + optional regression line in a popup."""
        x_key = cfg.get("x")
        y_key = cfg.get("y")
        x_data = self._val(result, x_key)
        y_data = self._val(result, y_key)
        if x_data is None or y_data is None:
            return
        # Filter NaNs
        valid = [i for i in range(len(y_data)) if not np.isnan(y_data[i])]
        if not valid:
            return
        px = [x_data[i] for i in valid]
        py = [y_data[i] for i in valid]

        title = cfg.get("title", "Popup Plot")
        x_label = cfg.get("x_label", "X")
        y_label = cfg.get("y_label", "Y")

        if self._popup_plot is None:
            self._popup_plot = self.create_popup_plot(title, x_label, y_label)
            self._popup_curves["scatter"] = self._popup_plot.plot(pen=None, symbol="o", symbolBrush="b")
            self._popup_curves["fit"] = self._popup_plot.plot(
                pen=pg.mkPen("r", width=2, style=QtCore.Qt.PenStyle.DashLine)
            )

        self._popup_curves["scatter"].setData(px, py)

        # Optional regression line
        slope_key = cfg.get("slope_key")
        intercept_key = cfg.get("intercept_key")
        slope = self._val(result, slope_key)
        intercept = self._val(result, intercept_key)

        if slope is not None and intercept is not None and px:
            # slope is in MOhm and currents in pA → convert
            scale = cfg.get("x_scale", 1.0)
            y_min = slope * (min(px) * scale) + intercept
            y_max = slope * (max(px) * scale) + intercept
            self._popup_curves["fit"].setData([min(px), max(px)], [y_min, y_max])
        else:
            self._popup_curves["fit"].setData([], [])

    def _viz_popup_phase(self, cfg, result):  # noqa: C901
        """Show dV/dt vs V phase-plane in a popup with threshold + max markers."""
        voltage = self._val(result, "voltage")
        dvdt = self._val(result, "dvdt")
        if voltage is None or dvdt is None:
            return
        try:
            voltage = np.asarray(voltage, dtype=float)
            dvdt = np.asarray(dvdt, dtype=float)
        except (ValueError, TypeError):
            return
        if len(voltage) == 0 or len(dvdt) == 0:
            return
        if np.all(np.isnan(voltage)) or np.all(np.isnan(dvdt)):
            return

        if self._popup_plot is None:
            title = cfg.get("title", "Phase Plane")
            self._popup_plot = self.create_popup_plot(title, "Voltage (mV)", "dV/dt (V/s)")
            self._popup_curves["phase"] = self._popup_plot.plot(pen="b", name="Phase Loop")
            self._popup_curves["thresh_marker"] = self._popup_plot.plot(
                pen=None, symbol="o", symbolBrush="r", symbolSize=10, name="Threshold"
            )
            self._popup_curves["max_marker"] = self._popup_plot.plot(
                pen=None, symbol="x", symbolBrush="g", symbolSize=10, name="Max dV/dt"
            )

        min_len = min(len(voltage), len(dvdt))
        self._popup_curves["phase"].setData(np.array(voltage)[:min_len], np.array(dvdt)[:min_len])

        threshold_v = self._val(result, "threshold_v")
        threshold_dvdt = self._val(result, "threshold_dvdt")
        if threshold_v is not None and threshold_dvdt is not None:
            self._popup_curves["thresh_marker"].setData([threshold_v], [threshold_dvdt])
        else:
            self._popup_curves["thresh_marker"].setData([], [])

        max_dvdt = self._val(result, "max_dvdt")
        if max_dvdt is not None and len(dvdt) > 0:
            idx = int(np.argmax(dvdt))
            if idx < len(voltage):
                self._popup_curves["max_marker"].setData([voltage[idx]], [dvdt[idx]])
        else:
            self._popup_curves["max_marker"].setData([], [])

        # Also draw threshold line on main plot
        if threshold_v is not None:
            if "main_thresh" not in self._result_hlines:
                line = pg.InfiniteLine(angle=0, pen=pg.mkPen("r", style=QtCore.Qt.PenStyle.DashLine))
                self.plot_widget.addItem(line)
                self._result_hlines["main_thresh"] = line
            self._result_hlines["main_thresh"].setValue(threshold_v)
            self._result_hlines["main_thresh"].setVisible(True)
        elif "main_thresh" in self._result_hlines:
            self._result_hlines["main_thresh"].setVisible(False)
