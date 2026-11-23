# src/synaptipy/application/gui/analysis_tabs/metadata_driven.py
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

from synaptipy.application.gui.analysis_tabs.base import AnalysisNotConfigured, BaseAnalysisTab
from synaptipy.core.analysis.registry import AnalysisRegistry
from synaptipy.shared.plot_customization import get_hv_line_pen, get_scatter_pen_and_brush
from synaptipy.shared.styling import style_button

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
        self._custom_interactive_region: Optional[pg.LinearRegionItem] = None
        self._custom_interactive_regions: List[pg.LinearRegionItem] = []
        self._interactive_region_created: bool = False

        # --- Interactive event-marker state ---
        self._current_event_indices: List[int] = []
        self._event_markers_item: Optional[pg.ScatterPlotItem] = None
        self._event_count_text_item: Optional[pg.TextItem] = None
        self._detected_event_amplitudes: Dict[int, float] = {}
        self._detector_uses_signed_amplitudes: bool = False
        self._artifact_curve_item: Optional[pg.PlotCurveItem] = None

        # --- Draggable threshold line ---
        self._threshold_line: Optional[pg.InfiniteLine] = None

        # --- Result h-lines & dynamic overlays ---
        self._result_hlines: Dict[str, pg.InfiniteLine] = {}
        self._dynamic_plot_items: List[Any] = []

        # --- Popup plot handles (keyed per sub-method + plot title) ---
        self._popup_plot: Optional[pg.PlotItem] = None
        self._popup_curves: Dict[str, Any] = {}
        self._popup_plots_by_method: Dict[str, Any] = {}
        self._method_param_cache: Dict[str, Dict[str, Any]] = {}
        self._active_method_label: Optional[str] = None
        self._ctrl_click_connected: bool = False
        self._last_message_state: tuple = ([], [])

        super().__init__(neo_adapter, settings_ref, parent)
        from synaptipy.shared.theme_manager import get_theme_signals

        get_theme_signals().theme_changed.connect(self._on_theme_changed)
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
        if getattr(self, "_custom_interactive_region", None) is not None:
            return self._custom_interactive_region
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
        self._left_scroll_area = QtWidgets.QScrollArea()
        scroll_area = self._left_scroll_area
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

        self.protocol_readiness_label = QtWidgets.QLabel("Protocol: signal-only / not reviewed")
        self.protocol_readiness_label.setWordWrap(True)
        self.protocol_readiness_label.setToolTip(
            "Protocol readiness is resolved from the Protocol Map in Explorer. "
            "Signal-only analyses can run without recorded protocol data."
        )
        control_layout.addWidget(self.protocol_readiness_label)

        # --- Preprocessing Widget ---
        # Explicitly place it here (after Data Source, before Params)
        if self.preprocessing_widget:
            control_layout.addWidget(self.preprocessing_widget)
            self.preprocessing_widget.setVisible(True)

        # Parameters Group
        params_group = QtWidgets.QGroupBox("Parameters")
        self._params_group = params_group
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
        from synaptipy.application.gui.ui_generator import ParameterWidgetGenerator

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

        # Errors and warnings the analysis reported about its own inputs.  These
        # must be visible next to the numbers: an evoked analysis that fell back
        # to a different stimulus source still produces a full results table, and
        # nothing in the numbers themselves says so.
        self.analysis_message_label = QtWidgets.QLabel("")
        self.analysis_message_label.setWordWrap(True)
        self.analysis_message_label.setVisible(False)
        self.results_layout.addRow(self.analysis_message_label)

        # We don't know the result keys ahead of time, so we'll add them dynamically
        # or we could add a text area for generic output
        # self.results_text = QtWidgets.QTextEdit()
        # self.results_text.setReadOnly(True)
        # self.results_text.setMaximumHeight(150)
        # self.results_layout.addRow(self.results_text)

        self.results_table = QtWidgets.QTableWidget()
        self.results_table.setColumnCount(2)
        self.results_table.setHorizontalHeaderLabels(["Metric", "Value"])
        self.results_table.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.Stretch)
        self.results_table.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
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

        # Set Splitter Sizes (1/3 Left, 2/3 Right) and prevent collapsing panels to 0 px
        splitter.setCollapsible(0, False)
        splitter.setCollapsible(1, False)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)

        # Basic plot setup
        if self.plot_widget:
            self._setup_custom_plot_items()

    def reset_parameters(self):
        """Reset generated parameters to defaults defined in metadata."""
        self._method_param_cache.pop(self.analysis_name, None)
        if self.plot_widget:
            for reg in list(self._custom_interactive_regions):
                try:
                    if reg in self.plot_widget.items:
                        self.plot_widget.removeItem(reg)
                except RuntimeError:
                    pass
        self._custom_interactive_regions.clear()
        self._custom_interactive_region = None
        self._interactive_region_created = False
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
            style_button(analyze_btn, "primary")
            layout.addRow("", analyze_btn)

        elif self.metadata.get("run_button"):
            # Explicit opt-in: add a standalone Run Analysis button without a
            # method selector (used by slow/heavy analyses like deep-learning
            # event detectors where auto-run on every parameter change would be
            # unacceptably slow).
            analyze_btn = QtWidgets.QPushButton("Run Analysis")
            analyze_btn.setToolTip("Run the analysis with current parameters")
            analyze_btn.clicked.connect(self._trigger_analysis)
            style_button(analyze_btn, "primary")
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
        # Always construct the combo so method_selector tabs can reveal/hide it dynamically
        # when switching between sub-analyses with and without paired start/end windows.
        region_param_names = [
            ("baseline_start", "baseline_end"),
            ("baseline_start_s", "baseline_end_s"),
            ("response_start", "response_end"),
            ("response_start_s", "response_end_s"),
            ("response_peak_start_s", "response_peak_end_s"),
            ("response_steady_start_s", "response_steady_end_s"),
            ("peak_window_start", "peak_window_end"),
            ("ss_window_start", "ss_window_end"),
        ]
        ui_param_names = {p.get("name") for p in self.metadata.get("ui_params", [])}
        has_regions = any(s in ui_param_names and e in ui_param_names for s, e in region_param_names)
        self._region_mode_combo = QtWidgets.QComboBox()
        self._region_mode_combo.addItems(["Interactive", "Manual"])
        self._region_mode_combo.setToolTip(
            "Interactive: drag regions on the plot to set windows.\n"
            "Manual: type start/end values in the spinboxes directly."
        )
        self._region_mode_combo.currentIndexChanged.connect(self._on_region_mode_changed)
        layout.addRow("Region Mode:", self._region_mode_combo)
        try:
            layout.setRowVisible(self._region_mode_combo, has_regions)
        except RuntimeError:
            pass

    def _on_method_selector_changed(self):  # noqa: C901
        """Handle switching between analysis methods via the method combo box."""
        if not self.method_combobox:
            return
        display_label = self.method_combobox.currentText()
        registry_key = self._method_map.get(display_label)
        if not registry_key:
            return

        # Cache outgoing sub-method's parameter edits before rebuilding widgets
        if hasattr(self, "param_generator") and self.param_generator.widgets and self.analysis_name:
            try:
                self._method_param_cache[self.analysis_name] = dict(self.param_generator.gather_params())
            except Exception:
                pass

        log.debug(f"Switching analysis method to: {registry_key}")
        self.analysis_name = registry_key
        self._active_method_label = display_label
        self.metadata = AnalysisRegistry.get_metadata(registry_key)

        # Hide popup windows belonging to other sub-methods so stale I-V / RMP / F-I
        # popups never stay behind or receive incompatible curve updates.
        for p_key, p_entry in list(self._popup_plots_by_method.items()):
            if not p_key.startswith(f"{registry_key}:"):
                try:
                    p_entry[0].hide()
                except Exception:
                    pass
        self._popup_plot = None
        self._popup_curves = {}

        # Rebuild generated parameter widgets and restore cached values if available
        if hasattr(self, "param_generator"):
            ui_params = self.metadata.get("ui_params", [])
            self.param_generator.generate_widgets(ui_params, self._on_param_changed)
            cached = self._method_param_cache.get(registry_key, {})
            for k, val in cached.items():
                w = self.param_generator.widgets.get(k)
                if w is None or val is None:
                    continue
                blocked = w.blockSignals(True)
                try:
                    if isinstance(w, (QtWidgets.QDoubleSpinBox, QtWidgets.QSpinBox)):
                        w.setValue(val)
                    elif isinstance(w, QtWidgets.QCheckBox):
                        w.setChecked(bool(val))
                    elif isinstance(w, QtWidgets.QComboBox):
                        idx = w.findText(str(val))
                        if idx >= 0:
                            w.setCurrentIndex(idx)
                    elif isinstance(w, QtWidgets.QLineEdit):
                        w.setText(str(val))
                except Exception:
                    pass
                finally:
                    w.blockSignals(blocked)

        # Remove previous method's persistent plot items & result h-lines, then set up new ones
        self._teardown_custom_plot_items()
        self._interactive_region_created = False
        self._setup_custom_plot_items()
        self._setup_interactive_regions()

        # Show/hide the secondary channel row based on the new sub-analysis metadata.
        if hasattr(self, "_secondary_channel_combobox") and self._secondary_channel_combobox is not None:
            sec_cfg = self.metadata.get("requires_secondary_channel")
            show_sec = bool(sec_cfg and isinstance(sec_cfg, dict))
            if show_sec:
                self._secondary_channel_param_name = sec_cfg.get("param_name", "secondary_data")
            try:
                if hasattr(self, "permanent_params_layout"):
                    self.permanent_params_layout.setRowVisible(self._secondary_channel_combobox, show_sec)
            except RuntimeError:
                pass

        # Clear previous results and disable Save until new analysis finishes
        self._last_analysis_result = None
        self._set_save_button_enabled(False)
        self._update_accumulation_ui_state()
        if self.results_table:
            self.results_table.setRowCount(0)
        self._show_analysis_messages({})
        self._current_event_indices = []

        # Drop the previous method's dynamic overlays.
        self._clear_dynamic_plot_items()

        # Apply channel-aware defaults for the newly generated widgets, then
        # re-run so the tab shows results for the method that is now selected.
        self._update_parameter_visibility()
        if self._current_plot_data and self._analysis_debounce_timer:
            self._analysis_debounce_timer.start(self._debounce_delay_ms)

        # Scroll the left panel so the Parameters group is visible.
        QtCore.QTimer.singleShot(50, self._scroll_to_params)

    def _clear_dynamic_plot_items(self):
        """Remove the per-run overlay items from the main plot."""
        if not self.plot_widget:
            return
        for item in getattr(self, "_dynamic_plot_items", []):
            try:
                if item in self.plot_widget.items:
                    self.plot_widget.removeItem(item)
            except RuntimeError:
                continue
        if hasattr(self, "_dynamic_plot_items"):
            self._dynamic_plot_items.clear()

    def _scroll_to_params(self) -> None:
        """Scroll the left control panel to bring the Parameters group into view."""
        if hasattr(self, "_left_scroll_area") and hasattr(self, "_params_group"):
            self._left_scroll_area.ensureWidgetVisible(self._params_group)

    def _teardown_custom_plot_items(self):
        """Remove persistent plot items and result h-lines when switching methods."""
        if self.plot_widget:
            for item in (
                self._event_markers_item,
                self._event_count_text_item,
                self._threshold_line,
                self._artifact_curve_item,
                self._custom_interactive_region,
            ):
                if item is not None:
                    try:
                        if item in self.plot_widget.items:
                            self.plot_widget.removeItem(item)
                    except RuntimeError:
                        pass
            for reg in list(self._custom_interactive_regions):
                try:
                    if reg in self.plot_widget.items:
                        self.plot_widget.removeItem(reg)
                except RuntimeError:
                    pass
            for line in list(self._result_hlines.values()):
                try:
                    if line in self.plot_widget.items:
                        self.plot_widget.removeItem(line)
                except RuntimeError:
                    pass
        self._event_markers_item = None
        self._event_count_text_item = None
        self._detected_event_amplitudes.clear()
        self._detector_uses_signed_amplitudes = False
        self._threshold_line = None
        self._artifact_curve_item = None
        self._custom_interactive_region = None
        self._custom_interactive_regions.clear()
        self._interactive_region_created = False
        self._result_hlines.clear()

    def _setup_custom_plot_items(self):
        """
        Create persistent plot items based on metadata ``plots`` list.

        Recognised persistent types (created once, updated per-analysis):
        * ``event_markers`` - interactive scatter (click remove / ctrl-click add)
        * ``threshold_line`` - draggable horizontal line synced w/ a param widget
        * ``artifact_overlay`` - curve item for artifact mask visualisation
        """
        if not self.plot_widget:
            return

        plots_meta = self.metadata.get("plots", [])

        for pcfg in plots_meta:
            ptype = pcfg.get("type")

            if ptype == "event_markers":
                s_pen, s_brush = get_scatter_pen_and_brush()
                self._event_markers_item = pg.ScatterPlotItem(size=10, pen=s_pen, brush=s_brush)
                self._event_markers_item._synaptipy_role = "scatter_markers"
                self.plot_widget.addItem(self._event_markers_item)
                self._event_markers_item.setVisible(False)
                self._event_markers_item.setZValue(100)
                self._event_markers_item.sigClicked.connect(self._on_event_marker_clicked)
                if not self._ctrl_click_connected and self.plot_widget.scene() is not None:
                    self.plot_widget.scene().sigMouseClicked.connect(self._on_plot_ctrl_clicked)
                    self._ctrl_click_connected = True

            elif ptype == "threshold_line":
                param_key = pcfg.get("param", "threshold")
                self._threshold_line = pg.InfiniteLine(angle=0, movable=True, pen=get_hv_line_pen())
                self._threshold_line._synaptipy_role = "hv_line"
                self._threshold_line.setVisible(False)
                self.plot_widget.addItem(self._threshold_line)
                self._threshold_line.setZValue(90)

                def _on_threshold_dragged(pk=param_key):
                    if self._threshold_line is None:
                        return
                    val = float(self._threshold_line.value())
                    base_med = getattr(self._threshold_line, "_synaptipy_baseline_median", None)
                    if base_med is not None and np.isfinite(float(base_med)):
                        val = abs(val - float(base_med))
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
                    try:
                        # If auto_detect_pulse is active, uncheck it when user manually drags a region
                        auto_w = widgets.get("auto_detect_pulse")
                        if isinstance(auto_w, QtWidgets.QCheckBox) and auto_w.isChecked():
                            b_auto = auto_w.blockSignals(True)
                            auto_w.setChecked(False)
                            auto_w.blockSignals(b_auto)
                        minX, maxX = region.getRegion()
                        start_w.setValue(minX)
                        end_w.setValue(maxX)
                    finally:
                        self._syncing_regions = False
                    self._on_param_changed()

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

        # Also bind Rin-style param names (without _s suffix) and Sag Ratio windows
        bind_region_tracked("baseline_start", "baseline_end", (0, 0, 255))
        bind_region_tracked("response_start", "response_end", (255, 0, 0))
        bind_region_tracked("peak_window_start", "peak_window_end", (255, 165, 0))
        bind_region_tracked("ss_window_start", "ss_window_end", (0, 200, 80))

        if self._region_mode_combo is not None and hasattr(self, "permanent_params_layout"):
            try:
                self.permanent_params_layout.setRowVisible(self._region_mode_combo, bool(self._region_spinbox_keys))
            except RuntimeError:
                pass

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
        if self.analysis_region and self.restrict_analysis_checkbox and self.restrict_analysis_checkbox.isChecked():
            if self.analysis_region not in self.plot_widget.items:
                self.plot_widget.addItem(self.analysis_region)
            self.analysis_region.setVisible(True)
        if self._event_markers_item and self._event_markers_item not in self.plot_widget.items:
            self.plot_widget.addItem(self._event_markers_item)
            self._event_markers_item.setZValue(100)
        if self._event_count_text_item and self._event_count_text_item not in self.plot_widget.items:
            self.plot_widget.addItem(self._event_count_text_item)
            self._event_count_text_item.setZValue(105)
        if self._threshold_line and self._threshold_line not in self.plot_widget.items:
            self.plot_widget.addItem(self._threshold_line)
            self._threshold_line.setZValue(90)
        if self._artifact_curve_item and self._artifact_curve_item not in self.plot_widget.items:
            self.plot_widget.addItem(self._artifact_curve_item)
            self._artifact_curve_item.setZValue(80)
        if self._custom_interactive_region and self._custom_interactive_region not in self.plot_widget.items:
            self.plot_widget.addItem(self._custom_interactive_region)
        for reg in self._custom_interactive_regions:
            if reg not in self.plot_widget.items:
                self.plot_widget.addItem(reg)
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
        if not self._current_plot_data or self._event_markers_item is None or not self.plot_widget:
            return

        vb = (
            self.plot_widget.getViewBox()
            if hasattr(self.plot_widget, "getViewBox")
            else getattr(self.plot_widget, "vb", None)
        )
        if vb is None:
            return
        pos = vb.mapSceneToView(ev.scenePos())
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
        """Redraw markers and count label based on ``_current_event_indices``."""
        if not self._current_plot_data:
            return
        data_arr = np.asarray(self._current_plot_data["data"], dtype=float)
        time_arr = np.asarray(self._current_plot_data["time"], dtype=float)
        valid_indices = [int(i) for i in self._current_event_indices if 0 <= int(i) < len(data_arr)]
        self._current_event_indices = valid_indices
        indices = np.array(valid_indices, dtype=int)
        count = len(indices)

        if self._event_markers_item is not None:
            if count > 0:
                times = time_arr[indices]
                volts = data_arr[indices]
                self._event_markers_item.setData(x=times, y=volts)
                self._event_markers_item.setVisible(True)
            else:
                self._event_markers_item.setData(x=[], y=[])
                self._event_markers_item.setVisible(False)

        if self._event_count_text_item is not None:
            self._event_count_text_item.setText(f"Events: {count}")
            if len(time_arr) > 0 and len(data_arr) > 0:
                self._event_count_text_item.setPos(float(np.nanmax(time_arr)), float(np.nanmax(data_arr)))
            self._event_count_text_item.setVisible(count > 0)

        # Update results table and _last_analysis_result with curated stats
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

        # CRITICAL: Add data_source key and concrete sub-analysis label for saving
        if self.data_source_combobox and self.data_source_combobox.isEnabled():
            data_source = self.data_source_combobox.currentData()
            result["data_source"] = data_source
        specific_label = (
            self._active_method_label
            or (self.metadata.get("label") if isinstance(self.metadata, dict) else None)
            or self.get_display_name()
        )
        result["_analysis_type_override"] = specific_label

        return result

    def _update_ui_for_selected_item(self):
        """Update UI when a new item is selected."""
        # Base class handles population of channel/source combos now
        # We just need to ensure plot is cleared if nothing selected
        self._current_event_indices = []
        self._detected_event_amplitudes.clear()
        self._detector_uses_signed_amplitudes = False
        if self._event_markers_item:
            self._event_markers_item.setVisible(False)
        if self._event_count_text_item:
            self._event_count_text_item.setVisible(False)
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
            self._preselect_named_stimulus_channel()
        else:
            self._secondary_channel_combobox.setEnabled(False)

        self._secondary_channel_combobox.blockSignals(False)

    # Channel names a recording system gives its stimulus/trigger output.  Matching
    # is on the recorded name only — never on the shape of the signal — so the
    # choice stays visible in the dropdown and the user can override it.
    _STIMULUS_CHANNEL_HINTS = ("ttl", "trig", "stim", "digital", "sync", "opto", "laser", "led")

    def _preselect_named_stimulus_channel(self):
        """Preselect a channel whose recorded name identifies it as the stimulus.

        Without this the evoked analyses open blocked on a dropdown the user has
        to find first.  Only an unambiguous name match is used: no match, or more
        than one, leaves the selection on "(None)".
        """
        combo = self._secondary_channel_combobox
        if combo is None or combo.currentData() is not None:
            return  # already chosen — never override the user

        primary_id = self.signal_channel_combobox.currentData() if self.signal_channel_combobox else None
        matches = []
        for index in range(combo.count()):
            chan_id = combo.itemData(index)
            if chan_id is None or chan_id == primary_id:
                continue
            channel = self._selected_item_recording.channels.get(chan_id)
            name = str(getattr(channel, "name", "") or chan_id).lower()
            if any(hint in name for hint in self._STIMULUS_CHANNEL_HINTS):
                matches.append(index)

        if len(matches) == 1:
            combo.setCurrentIndex(matches[0])
            log.debug("Preselected stimulus channel %r from its name.", combo.currentData())

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
                # Use average of the secondary channel (respecting filtered trial selection)
                sel_trials = sorted(self._filtered_indices) if getattr(self, "_filtered_indices", None) else None
                avg = channel.get_averaged_data(trial_indices=sel_trials)
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
                units_lower = units.lower()
                if units_lower in ("pa", "na", "ua", "ma", "a") or "amp" in units_lower:
                    is_voltage_clamp = True

        context["clamp_mode"] = "voltage_clamp" if is_voltage_clamp else "current_clamp"

        # Update generator
        try:
            self.param_generator.apply_context_defaults(context)
            self.param_generator.update_visibility(context)
        except RuntimeError:
            pass  # UI is being torn down or rebuilt — safe to ignore

    def _on_data_plotted(self):
        """Hook called after data is plotted - re-add persistent items then trigger analysis.

        Uses the debounce timer so the visibility gate in ``_trigger_analysis``
        recognises this as an automatic trigger and defers when the tab is hidden.
        """
        super()._on_data_plotted()
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

    def _compute_curated_event_amplitudes(self, indices: np.ndarray) -> np.ndarray:
        """Compute baseline-relative event amplitudes for curated indices."""
        if len(indices) == 0 or not self._current_plot_data:
            return np.array([], dtype=float)

        data_arr = np.asarray(self._current_plot_data["data"], dtype=float)
        fs = float(self._current_plot_data.get("sampling_rate", 10000.0) or 10000.0)
        pre_win_samples = max(2, int(0.01 * fs))
        guard_samples = int(0.001 * fs)

        amps: List[float] = []
        for idx in indices:
            idx_i = int(idx)
            if idx_i in self._detected_event_amplitudes:
                amps.append(float(self._detected_event_amplitudes[idx_i]))
                continue

            if idx_i > 0:
                pre_start = max(0, idx_i - pre_win_samples)
                pre_end = min(idx_i, max(pre_start + 1, idx_i - guard_samples))
                seg = data_arr[pre_start:pre_end]
            else:
                seg = data_arr[: min(len(data_arr), pre_win_samples)]

            local_bl = float(np.median(seg)) if seg.size > 0 else 0.0
            diff = float(data_arr[idx_i]) - local_bl
            amps.append(diff if self._detector_uses_signed_amplitudes else abs(diff))

        return np.asarray(amps, dtype=float)

    def _sync_curated_events_to_result(
        self,
        indices: np.ndarray,
        event_times: np.ndarray,
        amplitudes: np.ndarray,
        freq: float,
        mean_amp: float,
        amp_sd: float,
    ) -> None:
        """Write curated event metrics and arrays back into ``_last_analysis_result``."""
        if self._last_analysis_result is None:
            return

        count = int(len(indices))

        def _update_dict(target: Dict[str, Any], is_top: bool = False) -> None:
            target["event_count"] = count
            target["frequency_hz"] = float(freq)
            target["mean_amplitude"] = float(mean_amp)
            target["amplitude_sd"] = float(amp_sd)
            target["event_indices"] = (
                indices.tolist() if isinstance(target.get("event_indices"), list) else indices.copy()
            )
            target["event_times"] = (
                event_times.tolist() if isinstance(target.get("event_times"), list) else event_times.copy()
            )
            target["event_amplitudes"] = (
                amplitudes.tolist() if isinstance(target.get("event_amplitudes"), list) else amplitudes.copy()
            )
            if "mean_amplitude_pa" in target:
                target["mean_amplitude_pa"] = float(mean_amp)
            if "mean_amplitude_mv" in target:
                target["mean_amplitude_mv"] = float(mean_amp)
            if "mean_local_amplitude" in target:
                target["mean_local_amplitude"] = float(np.mean(np.abs(amplitudes))) if count > 0 else float("nan")
            if "_event_times" in target:
                target["_event_times"] = event_times.tolist()
            if "_event_peaks" in target and self._current_plot_data is not None:
                data_arr = np.asarray(self._current_plot_data["data"], dtype=float)
                target["_event_peaks"] = data_arr[indices].tolist() if count > 0 else []
            if is_top and "value" in target:
                if target.get("unit") == "Hz":
                    target["value"] = float(freq)
                elif target.get("unit") == "counts":
                    target["value"] = count

        def _update_obj(obj: Any) -> None:
            for attr, val in (
                ("event_count", count),
                ("frequency_hz", float(freq)),
                ("mean_amplitude", float(mean_amp)),
                ("amplitude_sd", float(amp_sd)),
                ("event_indices", indices.copy()),
                ("event_times", event_times.copy()),
                ("event_amplitudes", amplitudes.copy()),
            ):
                if hasattr(obj, attr):
                    setattr(obj, attr, val)
            if hasattr(obj, "value") and hasattr(obj, "unit"):
                if getattr(obj, "unit", None) == "Hz":
                    obj.value = float(freq)
                elif getattr(obj, "unit", None) == "counts":
                    obj.value = count

        if isinstance(self._last_analysis_result, dict):
            _update_dict(self._last_analysis_result, is_top=True)
            metrics = self._last_analysis_result.get("metrics")
            if isinstance(metrics, dict):
                _update_dict(metrics, is_top=False)
                if metrics.get("_result_obj") is not None:
                    _update_obj(metrics["_result_obj"])
        elif hasattr(self._last_analysis_result, "event_count"):
            _update_obj(self._last_analysis_result)

    def _update_curated_event_table(self):
        """Update the results table and result payload with curated event stats."""
        if not self._current_plot_data:
            if self.results_table and len(self._current_event_indices) == 0:
                self.results_table.setRowCount(1)
                self.results_table.setItem(0, 0, QtWidgets.QTableWidgetItem("Status"))
                self.results_table.setItem(0, 1, QtWidgets.QTableWidgetItem("No Events"))
            return

        data_arr = np.asarray(self._current_plot_data["data"], dtype=float)
        time_arr = np.asarray(self._current_plot_data["time"], dtype=float)
        valid_indices = [int(i) for i in self._current_event_indices if 0 <= int(i) < len(data_arr)]
        indices = np.array(valid_indices, dtype=int)
        count = len(indices)

        duration = float(time_arr[-1] - time_arr[0]) if len(time_arr) > 1 else 0.0
        if (
            getattr(self, "restrict_analysis_checkbox", None)
            and self.restrict_analysis_checkbox.isChecked()
            and getattr(self, "analysis_region", None)
            and len(time_arr) > 1
        ):
            r0, r1 = self.analysis_region.getRegion()
            c0 = max(float(time_arr[0]), float(r0))
            c1 = min(float(time_arr[-1]), float(r1))
            if c1 > c0:
                duration = c1 - c0

        if count == 0:
            empty_f = np.array([], dtype=float)
            self._sync_curated_events_to_result(
                indices=indices,
                event_times=empty_f,
                amplitudes=empty_f,
                freq=0.0,
                mean_amp=float("nan"),
                amp_sd=float("nan"),
            )
            if self.results_table:
                self.results_table.setRowCount(1)
                self.results_table.setItem(0, 0, QtWidgets.QTableWidgetItem("Status"))
                self.results_table.setItem(0, 1, QtWidgets.QTableWidgetItem("No Events"))
            return

        event_times = time_arr[indices]
        amplitudes = self._compute_curated_event_amplitudes(indices)
        freq = count / duration if duration > 0 else 0.0
        mean_amp = float(np.mean(amplitudes))
        amp_sd = float(np.std(amplitudes))

        self._sync_curated_events_to_result(
            indices=indices,
            event_times=event_times,
            amplitudes=amplitudes,
            freq=freq,
            mean_amp=mean_amp,
            amp_sd=amp_sd,
        )

        if not self.results_table:
            return

        method_label = ""
        if self.method_combobox:
            method_label = self.method_combobox.currentText() + " (Curated)"

        display_items = []
        if method_label:
            display_items.append(("Method", method_label))
        display_items += [
            ("Count", str(count)),
            ("Frequency", f"{freq:.2f} Hz"),
            ("Mean Amplitude", f"{mean_amp:.2f} +/- {amp_sd:.2f}"),
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
        supported_units = tuple(metadata.get("supported_channel_units", ()))
        if supported_units and self._selected_item_recording and self.signal_channel_combobox:
            channel = self._selected_item_recording.channels.get(self.signal_channel_combobox.currentData())
            channel_units = str(getattr(channel, "units", "")) if channel is not None else ""
            if channel_units not in supported_units:
                supported = ", ".join(supported_units)
                analysis_label = metadata.get("label", self.analysis_name)
                actual_units = channel_units or "unknown units"
                raise ValueError(f"{analysis_label} requires a channel in {supported}, not {actual_units}.")

        protocol_contexts = self._update_protocol_readiness(data)
        incompatible = [context for context in protocol_contexts if context.status == "incompatible"]
        if incompatible:
            missing = incompatible[0].missing
            detail = "; ".join(missing)
            # The usual way to hit a timing gap is an unselected stimulus channel,
            # which the user can fix here and now.  Naming the Protocol Map instead
            # sends them to a dialog they do not need.
            sec_cfg = metadata.get("requires_secondary_channel")
            if (
                isinstance(sec_cfg, dict)
                and any("stimulus timing" in item for item in missing)
                and not self._has_supplied_stimulus_timing()
            ):
                sec_label = str(sec_cfg.get("label", "secondary channel")).rstrip(":")
                routes = [f"Select the {sec_label} above"]
                # Offer the manual route only when this analysis actually has one;
                # Evoked Sync, for instance, can only read timing from a channel.
                manual_cfg = metadata.get("manual_stimulus_timing")
                if isinstance(manual_cfg, dict):
                    toggle = self.param_generator.widgets.get(manual_cfg.get("param"))
                    toggle_label = manual_cfg.get("label", "Detect Stim from TTL")
                    if toggle is not None:
                        routes.append(f"untick '{toggle_label}' to enter the stimulus onsets yourself")
                routes.append("or mark the stimulus timings as verified in the Protocol Map")
                raise AnalysisNotConfigured(
                    f"{metadata.get('label', self.analysis_name)} needs stimulus timing. " + ", ".join(routes) + "."
                )
            raise ValueError(f"Protocol Map is incompatible with this analysis: {detail}")
        fingerprints = {context.protocol_fingerprint for context in protocol_contexts}
        if requires_multi_trial and len(fingerprints) > 1:
            raise ValueError("Selected trials contain multiple protocol groups. Analyse one group at a time.")

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
                sec_data_list = []
                sec_channel = None
                if self._secondary_channel_combobox and self._secondary_channel_param_name:
                    sec_chan_id = self._secondary_channel_combobox.currentData()
                    if sec_chan_id is not None:
                        sec_channel = self._selected_item_recording.channels.get(sec_chan_id)

                fs = data.get("sampling_rate", 10000.0)
                trial_iter = (
                    sorted(i for i in self._filtered_indices if 0 <= i < num_trials)
                    if getattr(self, "_filtered_indices", None)
                    else list(range(num_trials))
                )
                win_start = params.get("t_start")
                win_end = params.get("t_end")
                has_win = win_start is not None and win_end is not None and float(win_end) > float(win_start)

                for i in trial_iter:
                    trial_data = channel.get_data(i)
                    trial_time = channel.get_relative_time_vector(i)

                    if trial_data is not None and trial_time is not None:
                        # Apply any global preprocessing if active
                        if hasattr(self, "_active_preprocessing_settings") and self._active_preprocessing_settings:
                            if hasattr(self, "pipeline"):
                                processed = self.pipeline.process(trial_data, fs, trial_time)
                                if processed is not None:
                                    trial_data = processed
                        applied_mask = None
                        if has_win:
                            w_mask = (trial_time >= float(win_start)) & (trial_time <= float(win_end))
                            if np.sum(w_mask) >= 2:
                                applied_mask = w_mask
                                trial_data = trial_data[w_mask]
                                trial_time = trial_time[w_mask]

                        data_list.append(trial_data)
                        time_list.append(trial_time)

                        if sec_channel is not None:
                            sec_trial = sec_channel.get_data(i)
                            if sec_trial is not None:
                                if applied_mask is not None and len(sec_trial) == len(applied_mask):
                                    sec_trial = sec_trial[applied_mask]
                                sec_data_list.append(sec_trial)

                if not data_list:
                    raise ValueError("Failed to load trial data.")

                if (
                    sec_channel is not None
                    and self._secondary_channel_param_name
                    and len(sec_data_list) == len(data_list)
                ):
                    params[self._secondary_channel_param_name] = sec_data_list

                # Call the function with lists
                results = AnalysisRegistry.execute(self.analysis_name, data_list, time_list, fs, **params)
            else:
                # Standard single-trial execution
                voltage = data["data"]
                time = data["time"]
                fs = data["sampling_rate"]
                win_offset = int(data.get("_window_offset_idx", 0) or 0)

                # Guard secondary channel array slicing when primary trace was restricted
                sec_key = self._secondary_channel_param_name
                if (
                    win_offset >= 0
                    and sec_key
                    and sec_key in params
                    and isinstance(params[sec_key], np.ndarray)
                    and self._current_plot_data
                    and len(params[sec_key]) == len(self._current_plot_data.get("time", []))
                    and len(time) < len(params[sec_key])
                ):
                    params[sec_key] = params[sec_key][win_offset : win_offset + len(time)]

                # Call the function with single arrays
                results = AnalysisRegistry.execute(self.analysis_name, voltage, time, fs, **params)
                res_dict = results.as_dict()
                if win_offset > 0 and isinstance(res_dict.get("metrics"), dict):
                    m = res_dict["metrics"]
                    for idx_k in ("spike_indices", "event_indices", "threshold_indices"):
                        if idx_k in m and m[idx_k] is not None:
                            try:
                                m[idx_k] = np.asarray(m[idx_k], dtype=int) + win_offset
                            except Exception:
                                pass
                    if "_result_obj" in m and hasattr(m["_result_obj"], "event_indices"):
                        try:
                            if m["_result_obj"].event_indices is not None:
                                m["_result_obj"].event_indices = (
                                    np.asarray(m["_result_obj"].event_indices, dtype=int) + win_offset
                                )
                        except Exception:
                            pass
                return res_dict

            return results.as_dict()

        except Exception as e:
            log.error(f"Analysis execution failed: {e}")
            raise

    def _has_selected_secondary_channel(self) -> bool:
        """True when the user has picked a real channel in the secondary dropdown.

        For the evoked analyses that channel is the recorded TTL / stimulus
        trace, so selecting it is the user supplying recorded stimulus timing for
        this run.  ``(None)`` carries userData None and does not count.
        """
        combo = self._secondary_channel_combobox
        if combo is None or not self._secondary_channel_param_name:
            return False
        try:
            return combo.currentData() is not None
        except RuntimeError:
            return False

    def _uses_manual_stimulus_timing(self) -> bool:
        """True when the user has switched this analysis to manual stimulus onsets.

        An analysis declares the toggle via ``manual_stimulus_timing`` metadata.
        Turning TTL detection off and typing the onsets is the user stating the
        stimulus timing explicitly — it is visible in the panel, drawn on the
        plot, and saved with the result — so it counts as supplied timing.
        """
        config = self.metadata.get("manual_stimulus_timing")
        if not isinstance(config, dict) or not hasattr(self, "param_generator"):
            return False
        widget = self.param_generator.widgets.get(config.get("param"))
        if widget is None:
            return False
        try:
            return self.param_generator._widget_value(widget) == config.get("manual_value", False)
        except RuntimeError:
            return False

    def _has_supplied_stimulus_timing(self) -> bool:
        """True when the user has given this run a stimulus-timing source."""
        return self._has_selected_secondary_channel() or self._uses_manual_stimulus_timing()

    def _update_protocol_readiness(self, data: Dict[str, Any]):
        """Show an auditable readiness state before a core analysis is called."""
        if not self._selected_item_recording:
            return []
        from synaptipy.core.protocols import resolve_protocols

        source = self.data_source_combobox.currentData() if self.data_source_combobox else 0
        trial_index = source if isinstance(source, int) else 0
        time = data.get("time") if isinstance(data, dict) else None
        duration = float(time[-1]) if time is not None and len(time) else None
        contexts = resolve_protocols(
            self._selected_item_recording,
            trial_index,
            duration,
            self.analysis_name,
            stimulus_timing_supplied=self._has_supplied_stimulus_timing(),
        )
        if not contexts:
            self.protocol_readiness_label.setText("Protocol: unavailable")
            return []
        statuses = {context.status for context in contexts}
        families = ", ".join(sorted({context.assignment.protocol_family for context in contexts}))
        if "incompatible" in statuses:
            state = "incompatible — edit Protocol Map"
        elif "ready" in statuses:
            state = "ready"
        else:
            state = "needs review"
        self.protocol_readiness_label.setText(f"Protocol: {families} ({state})")
        return contexts

    @QtCore.Slot(str)
    def _on_theme_changed(self, _mode: str = "") -> None:
        """Re-render status/warning messages with WCAG-compliant palette colors on theme switch."""
        try:
            errors, warnings = getattr(self, "_last_message_state", ([], []))
            if errors or warnings:
                self._render_message_banner(errors, warnings)
        except RuntimeError:
            pass

    def _render_message_banner(self, errors: List[str], warnings: List[str]) -> None:
        import html as _html

        from synaptipy.shared.theme_manager import status_html_colors

        label = getattr(self, "analysis_message_label", None)
        if label is None:
            return
        self._last_message_state = (list(errors), list(warnings))
        colors = status_html_colors()
        try:
            if errors:
                body = "<br>".join(f"[!] {_html.escape(text, quote=False)}" for text in errors + warnings)
                label.setText(f"<span style='color:{colors['error']};'>{body}</span>")
                label.setVisible(True)
            elif warnings:
                body = "<br>".join(f"[!] {_html.escape(text, quote=False)}" for text in warnings)
                label.setText(f"<span style='color:{colors['warning']};'>{body}</span>")
                label.setVisible(True)
            else:
                label.clear()
                label.setVisible(False)
        except RuntimeError:
            pass

    def _report_analysis_blocked(self, message: str) -> None:
        """Render a blocked/unconfigured run in the tab's message area."""
        if self.results_table:
            try:
                self.results_table.setRowCount(0)
            except RuntimeError:
                pass
        self._clear_dynamic_plot_items()
        label = getattr(self, "analysis_message_label", None)
        if label is None:
            super()._report_analysis_blocked(message)
            return
        self._render_message_banner([], [message])

    def _show_analysis_messages(self, results: Dict[str, Any]):
        """Surface the analysis's own errors and warnings above the results table."""
        label = getattr(self, "analysis_message_label", None)
        if label is None:
            return

        errors: List[str] = []
        warnings: List[str] = []

        if isinstance(results, dict):
            warnings.extend(str(w) for w in results.get("warnings", []) or [])
            metrics = results.get("metrics", {})
            if isinstance(metrics, dict):
                for key, value in metrics.items():
                    key_str = str(key)
                    if (key_str == "error" or key_str.endswith("_error")) and value:
                        errors.append(str(value))

        self._render_message_banner(errors, warnings)

    _METRIC_UNIT_TOKENS = {
        "rmp": "RMP",
        "rin": "Rin",
        "mohm": "(MOhm)",
        "kohm": "(kOhm)",
        "mv": "(mV)",
        "pa": "(pA)",
        "na": "(nA)",
        "pf": "(pF)",
        "us": "(uS)",
        "ms": "(ms)",
        "hz": "(Hz)",
        "pct": "(%)",
        "dvdt": "dV/dt",
        "ppr": "PPR",
        "stp": "STP",
        "cv": "CV",
        "cv2": "CV2",
        "lv": "LV",
        "iei": "IEI",
        "isi": "ISI",
        "fwhm": "FWHM",
        "fahp": "fAHP",
        "mahp": "mAHP",
        "ahp": "AHP",
        "adp": "ADP",
        "ap": "AP",
        "auc": "AUC",
        "snr": "SNR",
        "sd": "SD",
        "std": "SD",
        "se": "SE",
        "ci": "CI",
        "iv": "I-V",
        "fi": "F-I",
        "cc": "(CC)",
        "vc": "(VC)",
        "ss": "Steady-State",
    }

    @classmethod
    def _format_metric_label(cls, raw_key: str) -> str:
        if " " in raw_key:
            return raw_key
        tokens = str(raw_key).split("_")
        out = []
        for idx, tok in enumerate(tokens):
            low = tok.lower()
            if idx == len(tokens) - 1 and low == "s" and len(tokens) > 1:
                out.append("(s)")
            elif low in cls._METRIC_UNIT_TOKENS:
                out.append(cls._METRIC_UNIT_TOKENS[low])
            else:
                out.append(tok.capitalize())
        return " ".join(out)

    def _display_analysis_results(self, results: Dict[str, Any]):  # noqa: C901
        """
        Display analysis results in table widget.
        Implements abstract method from BaseAnalysisTab.
        """
        if not self.results_table:
            return

        self._show_analysis_messages(results)

        try:
            display_source = results.get("metrics", {})

            # robust extraction of items
            items = []
            if isinstance(display_source, dict):
                items = list(display_source.items())
            elif hasattr(display_source, "__dict__"):
                items = [(k, v) for k, v in display_source.__dict__.items() if not k.startswith("_")]
            else:
                items = [("Result", str(display_source))]

            display_items = []
            for k, v in items:
                try:
                    k_raw = str(k)
                    if k_raw.startswith("_") or k_raw == "error" or k_raw.endswith("_error"):
                        continue

                    if isinstance(v, (list, np.ndarray, dict)) or v is None:
                        continue

                    key_str = self._format_metric_label(k_raw)

                    if isinstance(v, bool):
                        val_str = "Yes" if v else "No"
                    elif isinstance(v, (int, np.integer)):
                        val_str = str(int(v))
                    elif isinstance(v, (float, np.floating)):
                        vf = float(v)
                        if np.isnan(vf) or np.isinf(vf):
                            val_str = "N/A"
                        elif 0.0 < abs(vf) < 0.01 or abs(vf) >= 1e5:
                            val_str = f"{vf:.4g}"
                        else:
                            val_str = f"{vf:.3f}"
                    elif isinstance(v, str):
                        val_str = v
                    else:
                        val_str = str(v)

                    display_items.append((key_str, val_str))
                except Exception as e:
                    log.warning(f"Skipping result item {k}: {e}")
                    continue

            self.results_table.setRowCount(len(display_items))
            self.results_table.setColumnCount(2)

            for row, (k, v) in enumerate(display_items):
                key_item = QtWidgets.QTableWidgetItem(k)
                key_item.setToolTip(k)
                val_item = QtWidgets.QTableWidgetItem(v)

                self.results_table.setItem(row, 0, key_item)
                self.results_table.setItem(row, 1, val_item)

        except Exception as e:
            log.error(f"Error displaying results: {e}")
            self.results_table.setRowCount(1)

        # --- Sync Rin spinboxes AND interactive plot regions when auto-detect runs ---
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
            # Sync interactive LinearRegionItems so shaded regions match auto-detected windows
            self._syncing_regions = True
            try:
                for s_key, e_key in (("baseline_start", "baseline_end"), ("response_start", "response_end")):
                    reg = self._interactive_regions.get(s_key)
                    if reg is not None and s_key in widgets and e_key in widgets:
                        reg.setRegion([widgets[s_key].value(), widgets[e_key].value()])
            finally:
                self._syncing_regions = False

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
        self._clear_dynamic_plot_items()

        result_item = results.get("metrics", {}) if isinstance(results, dict) else {}

        plots_meta = self.metadata.get("plots", [])

        for plot_cfg in plots_meta:
            plot_type = plot_cfg.get("type")

            # --- simple markers ---
            # Pass full results so top-level private array keys (_spike_times etc.) are found
            if plot_type == "markers":
                self._viz_markers(plot_cfg, results)

            # --- brackets (bursts) ---
            elif plot_type == "brackets":
                self._viz_brackets(plot_cfg, result_item)

            # --- vertical lines ---
            # Pass full results so top-level private array keys (_spike_times etc.) are found
            elif plot_type == "vlines":
                self._viz_vlines(plot_cfg, results)

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

            # trace - optional spike/event markers overlay
            elif plot_type == "trace":
                from synaptipy.shared.plot_customization import get_scatter_size, get_scatter_symbol

                if plot_cfg.get("show_spikes") and self._current_plot_data:
                    spike_idx = self._val(result_item, "spike_indices")
                    if spike_idx is not None and len(spike_idx) > 0:
                        time_arr = self._current_plot_data["time"]
                        data_arr = self._current_plot_data["data"]
                        valid = np.array(spike_idx, dtype=int)
                        valid = valid[(valid >= 0) & (valid < len(data_arr))]
                        if len(valid) > 0:
                            s_pen, s_brush = get_scatter_pen_and_brush()
                            scatter = pg.ScatterPlotItem(
                                x=time_arr[valid],
                                y=data_arr[valid],
                                size=get_scatter_size(),
                                symbol=get_scatter_symbol(),
                                pen=s_pen,
                                brush=s_brush,
                            )
                            scatter._synaptipy_role = "scatter_markers"
                            scatter.setZValue(50)
                            self.plot_widget.addItem(scatter)
                            self._dynamic_plot_items.append(scatter)

                if plot_cfg.get("show_events") and self._current_plot_data:
                    ev_times = self._val(result_item, "event_times")
                    if ev_times is not None and len(ev_times) > 0:
                        time_arr = self._current_plot_data["time"]
                        data_arr = self._current_plot_data["data"]
                        ev_arr = np.asarray(ev_times)
                        idx = np.searchsorted(time_arr, ev_arr, side="left")
                        idx = np.clip(idx, 0, len(time_arr) - 1)
                        prev = np.clip(idx - 1, 0, len(time_arr) - 1)
                        idx = np.where(
                            np.abs(time_arr[prev] - ev_arr) < np.abs(time_arr[idx] - ev_arr),
                            prev,
                            idx,
                        )
                        scatter = pg.ScatterPlotItem(
                            x=time_arr[idx],
                            y=data_arr[idx],
                            size=get_scatter_size(),
                            pen=pg.mkPen("#222222", width=0.8),
                            brush=pg.mkBrush(255, 165, 0, 210),
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
        if isinstance(x_data, (int, float, np.number)) and not isinstance(x_data, bool):
            x_data = [float(x_data)]
        elif isinstance(x_data, np.ndarray) and x_data.ndim == 0:
            x_data = [float(x_data)]
        if isinstance(y_data, (int, float, np.number)) and not isinstance(y_data, bool):
            y_data = [float(y_data)]
        elif isinstance(y_data, np.ndarray) and y_data.ndim == 0:
            y_data = [float(y_data)]
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
            from synaptipy.shared.plot_customization import get_scatter_size, get_scatter_symbol

            color = cfg.get("color")
            use_custom_primary = color is None or cfg.get("role") == "primary"
            scatter_size = get_scatter_size()
            if use_custom_primary:
                scatter_pen, scatter_brush = get_scatter_pen_and_brush()
                symbol = cfg.get("symbol") or get_scatter_symbol()
            else:
                scatter_pen = pg.mkPen("#222222", width=0.8)
                scatter_brush = pg.mkBrush(color)
                symbol = cfg.get("symbol", "o")
            scatter = pg.ScatterPlotItem(
                x=x_arr, y=y_arr, size=scatter_size, symbol=symbol, pen=scatter_pen, brush=scatter_brush
            )
            if use_custom_primary:
                scatter._synaptipy_role = "scatter_markers"
                scatter._synaptipy_fixed_symbol = "symbol" in cfg
            scatter.setZValue(75)
            self.plot_widget.addItem(scatter)
            self._dynamic_plot_items.append(scatter)

    def _viz_brackets(self, cfg, result):
        data_key = cfg.get("data")
        bursts = self._val(result, data_key, [])
        if not bursts:
            return
        y_offset = 0.0
        if self._current_plot_data:
            try:
                d_arr = np.asarray(self._current_plot_data["data"], dtype=float)
                y_max = float(np.nanmax(d_arr))
                y_span = float(np.nanmax(d_arr) - np.nanmin(d_arr))
                if not np.isfinite(y_span) or y_span <= 0:
                    y_span = max(abs(y_max) * 0.1, 1.0)
                y_offset = y_max + 0.08 * y_span
            except Exception:
                y_offset = 0.0
        color = cfg.get("color", "r")
        for burst_spikes in bursts:
            if len(burst_spikes) >= 2:
                item = pg.PlotCurveItem(
                    [burst_spikes[0], burst_spikes[-1]], [y_offset, y_offset], pen=pg.mkPen(color, width=3)
                )
                item._synaptipy_role = "bracket"
                self.plot_widget.addItem(item)
                self._dynamic_plot_items.append(item)
                if self._current_plot_data:
                    tv = np.asarray(self._current_plot_data["time"], dtype=float)
                    vv = np.asarray(self._current_plot_data["data"], dtype=float)
                    if len(tv) > 0 and len(vv) == len(tv):
                        bs_arr = np.asarray(burst_spikes, dtype=float)
                        si = np.clip(np.searchsorted(tv, bs_arr, side="left"), 0, len(tv) - 1)
                        prev = np.clip(si - 1, 0, len(tv) - 1)
                        si = np.where(np.abs(tv[prev] - bs_arr) < np.abs(tv[si] - bs_arr), prev, si)
                        s_pen, s_brush = get_scatter_pen_and_brush()
                        scatter = pg.ScatterPlotItem(x=tv[si], y=vv[si], size=8, pen=s_pen, brush=s_brush)
                        scatter._synaptipy_role = "scatter_markers"
                        self.plot_widget.addItem(scatter)
                        self._dynamic_plot_items.append(scatter)

    def _viz_vlines(self, cfg, result):
        data_key = cfg.get("data")
        vals = self._val(result, data_key, [])
        if vals is None and isinstance(result, dict) and "metrics" in result:
            vals = result["metrics"].get(data_key, [])
        color = cfg.get("color")
        if isinstance(vals, (int, float)):
            vals = [vals]
        for x in vals or []:
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
            if color is None:
                line._synaptipy_role = "hv_line"
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
        param_keys = cfg.get("data", ["baseline_start", "baseline_end"])
        start_val = 0.0
        end_val = 0.1
        widgets = self.param_generator.widgets if hasattr(self, "param_generator") else {}
        if len(param_keys) >= 2:
            if param_keys[0] in widgets:
                start_val = float(widgets[param_keys[0]].value())
            if param_keys[1] in widgets:
                end_val = float(widgets[param_keys[1]].value())

        if getattr(self, "_interactive_region_created", False) and self._custom_interactive_region is not None:
            if self.plot_widget and self._custom_interactive_region not in self.plot_widget.items:
                self.plot_widget.addItem(self._custom_interactive_region)
            if not self._syncing_regions:
                self._syncing_regions = True
                try:
                    self._custom_interactive_region.setRegion([start_val, end_val])
                finally:
                    self._syncing_regions = False
            return

        color_spec = cfg.get("color")
        if color_spec is not None:
            c_obj = pg.mkColor(color_spec)
            brush = pg.mkBrush(c_obj.red(), c_obj.green(), c_obj.blue(), 50)
            pen = pg.mkPen(c_obj.red(), c_obj.green(), c_obj.blue(), 150)
        else:
            brush = pg.mkBrush(50, 50, 200, 50)
            pen = pg.mkPen(50, 50, 200, 150)

        region = pg.LinearRegionItem(
            values=[start_val, end_val],
            orientation="vertical",
            brush=brush,
            pen=pen,
            movable=True,
        )
        if self.plot_widget:
            self.plot_widget.addItem(region)
        self._custom_interactive_region = region
        self._custom_interactive_regions.append(region)
        self._interactive_region_created = True

        def on_region_changed():
            if self._syncing_regions:
                return
            self._syncing_regions = True
            try:
                mn, mx = region.getRegion()
                if hasattr(self, "param_generator") and len(param_keys) >= 2:
                    w_map = self.param_generator.widgets
                    if param_keys[0] in w_map:
                        b0 = w_map[param_keys[0]].blockSignals(True)
                        w_map[param_keys[0]].setValue(mn)
                        w_map[param_keys[0]].blockSignals(b0)
                    if param_keys[1] in w_map:
                        b1 = w_map[param_keys[1]].blockSignals(True)
                        w_map[param_keys[1]].setValue(mx)
                        w_map[param_keys[1]].blockSignals(b1)
            finally:
                self._syncing_regions = False
            self._on_param_changed()

        region.sigRegionChangeFinished.connect(on_region_changed)

        if len(param_keys) >= 2:
            s_w = widgets.get(param_keys[0])
            e_w = widgets.get(param_keys[1])
            if s_w is not None and e_w is not None:

                def on_spinboxes_changed():
                    if self._syncing_regions:
                        return
                    self._syncing_regions = True
                    try:
                        region.setRegion([float(s_w.value()), float(e_w.value())])
                    finally:
                        self._syncing_regions = False

                if hasattr(s_w, "valueChanged"):
                    s_w.valueChanged.connect(on_spinboxes_changed)
                if hasattr(e_w, "valueChanged"):
                    e_w.valueChanged.connect(on_spinboxes_changed)

    def _viz_event_markers(self, cfg, result):
        """Update interactive event markers from result."""
        if (
            isinstance(result, dict)
            and "metrics" in result
            and "event_indices" not in result
            and "_result_obj" not in result
        ):
            result = result["metrics"]
        raw_metrics = result if isinstance(result, dict) else {}
        # Unwrap _result_obj stored inside a metrics dict
        if isinstance(result, dict) and "_result_obj" in result:
            result = result["_result_obj"]
        is_obj = hasattr(result, "event_indices")
        event_indices = (
            result.event_indices if is_obj else (result.get("event_indices") if isinstance(result, dict) else None)
        )
        orig_amps = (
            getattr(result, "event_amplitudes", None)
            if is_obj
            else (
                result.get("event_amplitudes")
                if isinstance(result, dict) and result.get("event_amplitudes") is not None
                else raw_metrics.get("event_amplitudes")
            )
        )

        self._detected_event_amplitudes.clear()
        self._detector_uses_signed_amplitudes = False

        if event_indices is not None:
            idx_arr = np.asarray(event_indices, dtype=int)
            if orig_amps is not None and len(orig_amps) == len(idx_arr):
                amp_arr = np.asarray(orig_amps, dtype=float)
                for e_idx, e_amp in zip(idx_arr, amp_arr):
                    if np.isfinite(e_amp):
                        self._detected_event_amplitudes[int(e_idx)] = float(e_amp)
                if any(v < 0 for v in self._detected_event_amplitudes.values()):
                    self._detector_uses_signed_amplitudes = True

            if self._event_count_text_item is None and self.plot_widget is not None:
                self._event_count_text_item = pg.TextItem(
                    text=f"Events: {len(idx_arr)}",
                    anchor=(1, 1),
                    color=(255, 255, 255),
                    fill=(0, 0, 0, 170),
                )
                self._event_count_text_item.setZValue(105)
                self.plot_widget.addItem(self._event_count_text_item)

            self._current_event_indices = list(idx_arr)
            self._refresh_event_markers()
        else:
            self._current_event_indices = []
            if self._event_markers_item:
                self._event_markers_item.setVisible(False)
            if self._event_count_text_item:
                self._event_count_text_item.setVisible(False)

    def _viz_threshold_line(self, cfg, result):
        """Update threshold line position from result."""
        plot_level = self._val(result, "_plot_threshold_level")
        base_med = self._val(result, "_baseline_median")
        if plot_level is not None and np.isfinite(float(plot_level)) and self._threshold_line:
            self._threshold_line._synaptipy_baseline_median = float(base_med) if base_med is not None else None
            self._threshold_line.setValue(float(plot_level))
            self._threshold_line.setVisible(True)
            return

        threshold_val = self._val(result, "threshold")
        if threshold_val is None:
            threshold_val = self._val(result, "threshold_value")
        if threshold_val is not None and np.isfinite(float(threshold_val)) and self._threshold_line:
            self._threshold_line._synaptipy_baseline_median = None
            self._threshold_line.setValue(float(threshold_val))
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
        from synaptipy.shared.plot_customization import get_overlay_fit_pen

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
        if cfg.get("role") == "secondary_fit":
            color = cfg.get("color", "#ff8c00")
            width = float(cfg.get("width", 2.0))
            pen = pg.mkPen(color, width=width, style=QtCore.Qt.PenStyle.DashLine)
            curve = pg.PlotCurveItem(x=x_arr, y=y_arr, pen=pen, connect="finite")
        else:
            pen = get_overlay_fit_pen()
            curve = pg.PlotCurveItem(x=x_arr, y=y_arr, pen=pen, connect="finite")
            curve._synaptipy_role = "overlay_fit"
        curve.setZValue(70)
        self.plot_widget.addItem(curve)
        self._dynamic_plot_items.append(curve)

        # Statistical annotation positioned cleanly within the fitted span (safe for negative mV)
        tau_key = cfg.get("tau_key")
        tau = self._val(result, tau_key) if tau_key else None
        if tau is None and cfg.get("role") != "secondary_fit":
            tau = self._val(result, "tau_ms")
            if tau is None:
                tau = self._val(result, "tau_fast_ms")
            if tau is None:
                tau = self._val(result, "tau")
        if tau is not None and np.isfinite(float(tau)):
            text_item = pg.TextItem(
                text=f"tau = {float(tau):.2f} ms",
                anchor=(0, 1),
                color=(255, 255, 255),
                fill=(0, 0, 0, 175),
            )
            x_min, x_max = float(np.nanmin(x_arr)), float(np.nanmax(x_arr))
            y_min, y_max = float(np.nanmin(y_arr)), float(np.nanmax(y_arr))
            text_item.setPos(x_min + 0.55 * (x_max - x_min), y_min + 0.85 * (y_max - y_min))
            text_item.setZValue(95)
            self.plot_widget.addItem(text_item)
            self._dynamic_plot_items.append(text_item)

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
        """Return a QBrush from ``brush``/``color`` in cfg or user AUC customization."""
        brush_spec = cfg.get("brush")
        color_spec = cfg.get("color")
        if brush_spec is not None:
            return pg.mkBrush(*brush_spec)
        if color_spec is not None:
            if isinstance(color_spec, (list, tuple)):
                return pg.mkBrush(*color_spec)
            return pg.mkBrush(color_spec)
        from synaptipy.shared.plot_customization import get_auc_brush

        return get_auc_brush()

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
        """Extract *key* from canonical analysis metrics."""
        if key is None:
            return None
        metrics = result.get("metrics", {}) if isinstance(result, dict) else {}
        return self._val(metrics, key)

    def _viz_fill_between(self, cfg, result):
        """Draw a shaded region between two curves (y1 and y2) along a shared x axis.

        Values are read from the canonical ``result['metrics']`` mapping.

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
        if cfg.get("brush") is None and cfg.get("color") is None:
            fill._synaptipy_role = "auc_fill"

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

        from synaptipy.shared.plot_customization import get_trace_overlay_pen

        pen = get_trace_overlay_pen()
        curve = pg.PlotCurveItem(x=time_arr[mask], y=data_arr[mask], pen=pen)
        curve._synaptipy_role = "trace_overlay"
        curve.setZValue(60)
        self.plot_widget.addItem(curve)
        self._dynamic_plot_items.append(curve)

    def _viz_event_fit_overlay(self, cfg, result):
        """Overlay fitted event curves (e.g. bi-exponential EPSP fits) on the raw trace."""
        if not self.plot_widget:
            return

        times_key = cfg.get("times_key", "_event_fit_times")
        values_key = cfg.get("values_key", "_event_fit_values")

        fit_times = self._val(result, times_key)
        fit_values = self._val(result, values_key)

        if fit_times is None or fit_values is None:
            return

        from synaptipy.shared.plot_customization import get_event_fit_overlay_pen

        pen = get_event_fit_overlay_pen()

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
            curve._synaptipy_role = "event_fit_overlay"
            curve.setZValue(65)
            self.plot_widget.addItem(curve)
            self._dynamic_plot_items.append(curve)

    def _get_or_create_method_popup(self, popup_key: str, title: str, x_label: str, y_label: str):
        """Return (popup_win, plot_widget, curves_dict) keyed per sub-analysis so popups never collide."""
        entry = self._popup_plots_by_method.get(popup_key)
        if entry is not None:
            popup_win, plot_widget, curves = entry
            plot_widget.setLabel("bottom", x_label)
            plot_widget.setLabel("left", y_label)
            popup_win.setWindowTitle(title)
            if not popup_win.isVisible():
                popup_win.show()
            return popup_win, plot_widget, curves

        popup_win, plot_widget = self.export_manager.create_popup_plot(title, x_label, y_label, self)
        self._popup_windows.append(popup_win)
        curves: Dict[str, Any] = {}
        self._popup_plots_by_method[popup_key] = (popup_win, plot_widget, curves)
        return popup_win, plot_widget, curves

    def _viz_popup_xy(self, cfg, result):  # noqa: C901
        """Show scatter + optional regression line in a dedicated per-method popup."""
        x_key = cfg.get("x")
        y_key = cfg.get("y")
        title = cfg.get("title", "Popup Plot")
        popup_key = f"{self.analysis_name}:{title}"

        x_data = self._val(result, x_key)
        y_data = self._val(result, y_key)
        valid = []
        if x_data is not None and y_data is not None:
            min_n = min(len(x_data), len(y_data))
            valid = [
                i
                for i in range(min_n)
                if x_data[i] is not None
                and y_data[i] is not None
                and np.isfinite(float(x_data[i]))
                and np.isfinite(float(y_data[i]))
            ]

        if not valid:
            # Clear stale data if popup already exists for this method
            existing = self._popup_plots_by_method.get(popup_key)
            if existing is not None:
                _, _, curves = existing
                if "scatter" in curves:
                    curves["scatter"].setData([], [])
                if "fit" in curves:
                    curves["fit"].setData([], [])
                if "stat_text" in curves:
                    curves["stat_text"].setText("")
            return

        px = [float(x_data[i]) for i in valid]
        py = [float(y_data[i]) for i in valid]

        unit = "mV"
        quantity = "Voltage"
        if self._current_plot_data:
            unit = self._current_plot_data.get("units", "mV")
            if unit.lower() in ["pa", "na", "ua", "a"]:
                quantity = "Current"
            elif unit.lower() in ["mv", "v"]:
                quantity = "Voltage"
            else:
                quantity = self._current_plot_data.get("channel_name", "Signal")

        x_label = cfg.get("x_label", f"{quantity} ({unit})")
        y_label = cfg.get("y_label", "Y")

        if "(mV)" in x_label and unit != "mV":
            x_label = x_label.replace("(mV)", f"({unit})").replace("Voltage", quantity).replace("RMP", "Baseline")
        if "(mV)" in y_label and unit != "mV":
            y_label = y_label.replace("(mV)", f"({unit})").replace("Voltage", quantity).replace("RMP", "Baseline")

        _, popup_plot, curves = self._get_or_create_method_popup(popup_key, title, x_label, y_label)
        self._popup_plot = popup_plot
        self._popup_curves = curves

        if "scatter" not in curves:
            curves["scatter"] = popup_plot.plot(
                pen=pg.mkPen((31, 119, 180, 140), width=1.2),
                symbol="o",
                symbolSize=9,
                symbolPen=pg.mkPen("#1a1a1a", width=0.8),
                symbolBrush=pg.mkBrush("#1f77b4"),
                name="Measured",
            )
            curves["fit"] = popup_plot.plot(
                pen=pg.mkPen("#d62728", width=2.2, style=QtCore.Qt.PenStyle.DashLine),
                name="Linear Fit",
            )

        curves["scatter"].setData(px, py)

        slope_key = cfg.get("slope_key")
        intercept_key = cfg.get("intercept_key")
        slope = self._val(result, slope_key)
        intercept = self._val(result, intercept_key)

        if (
            slope is not None
            and intercept is not None
            and np.isfinite(float(slope))
            and np.isfinite(float(intercept))
            and px
        ):
            scale = float(cfg.get("x_scale", 1.0))
            y_min = float(slope) * (min(px) * scale) + float(intercept)
            y_max = float(slope) * (max(px) * scale) + float(intercept)
            curves["fit"].setData([min(px), max(px)], [y_min, y_max])

            r2 = None
            for rk in (cfg.get("r2_key"), "r_squared", "iv_r_squared", "fi_r_squared"):
                if rk:
                    cand = self._val(result, rk)
                    if cand is not None and np.isfinite(float(cand)):
                        r2 = float(cand)
                        break

            if "stat_text" not in curves:
                text_item = pg.TextItem(anchor=(0, 1), color=(255, 255, 255), fill=(0, 0, 0, 175))
                popup_plot.addItem(text_item)
                curves["stat_text"] = text_item
            stats_lines = [f"Slope = {float(slope):.3g}"]
            if r2 is not None:
                stats_lines.insert(0, f"R^2 = {r2:.3f}")
            curves["stat_text"].setText("\n".join(stats_lines))
            x_span = max(px) - min(px) or 1.0
            y_span = max(py) - min(py) or 1.0
            curves["stat_text"].setPos(min(px) + 0.04 * x_span, max(py) - 0.04 * y_span)
        else:
            curves["fit"].setData([], [])
            if "stat_text" in curves:
                curves["stat_text"].setText("")
        popup_plot.autoRange()

    @staticmethod
    def _derivative_unit_str(unit: str) -> str:
        """Map trace amplitude unit to calculate_dvdt's 1000x-scaled derivative unit (e.g. mV -> V/s)."""
        mapping = {
            "mv": "V/s",
            "v": "kV/s",
            "uv": "mV/s",
            "pa": "nA/s",
            "na": "uA/s",
            "ua": "mA/s",
            "ma": "A/s",
        }
        return mapping.get((unit or "").strip().lower(), f"{unit}/ms" if unit else "V/s")

    def _viz_popup_phase(self, cfg, result):  # noqa: C901
        """Show dV/dt vs V phase-plane in a dedicated popup with threshold + max markers."""
        title = cfg.get("title", "Phase Plane")
        popup_key = f"{self.analysis_name}:{title}"
        voltage = self._val(result, "voltage")
        dvdt = self._val(result, "dvdt")
        valid_arrays = True
        if voltage is None or dvdt is None:
            valid_arrays = False
        else:
            try:
                voltage = np.asarray(voltage, dtype=float)
                dvdt = np.asarray(dvdt, dtype=float)
                if len(voltage) == 0 or len(dvdt) == 0 or np.all(np.isnan(voltage)) or np.all(np.isnan(dvdt)):
                    valid_arrays = False
            except (ValueError, TypeError):
                valid_arrays = False

        if not valid_arrays:
            existing = self._popup_plots_by_method.get(popup_key)
            if existing is not None:
                _, _, curves = existing
                for k in ("phase", "thresh_marker", "max_marker"):
                    if k in curves:
                        curves[k].setData([], [])
                if "phase_stats" in curves:
                    curves["phase_stats"].setText("")
            return

        unit = "mV"
        quantity = "Voltage"
        if self._current_plot_data:
            unit = self._current_plot_data.get("units", "mV")
            if unit.lower() in ["pa", "na", "ua", "a"]:
                quantity = "Current"
            elif unit.lower() in ["mv", "v"]:
                quantity = "Voltage"
            else:
                quantity = self._current_plot_data.get("channel_name", "Signal")

        x_label = f"{quantity} ({unit})"
        unit_s = self._derivative_unit_str(unit)
        if quantity == "Voltage":
            y_label = f"dV/dt ({unit_s})"
        elif quantity == "Current":
            y_label = f"dI/dt ({unit_s})"
        else:
            y_label = f"d({quantity})/dt ({unit_s})"

        _, popup_plot, curves = self._get_or_create_method_popup(popup_key, title, x_label, y_label)
        self._popup_plot = popup_plot
        self._popup_curves = curves

        if "phase" not in curves:
            popup_plot.addLegend(offset=(-10, 10))
            curves["phase"] = popup_plot.plot(pen=pg.mkPen("#1f77b4", width=1.6), name="Phase Loop")
            curves["thresh_marker"] = popup_plot.plot(
                pen=None,
                symbol="o",
                symbolPen=pg.mkPen("#1a1a1a", width=0.8),
                symbolBrush=pg.mkBrush("#d62728"),
                symbolSize=10,
                name="Threshold",
            )
            curves["max_marker"] = popup_plot.plot(
                pen=None,
                symbol="d",
                symbolPen=pg.mkPen("#1a1a1a", width=0.8),
                symbolBrush=pg.mkBrush("#2ca02c"),
                symbolSize=11,
                name="Max dV/dt",
            )

        min_len = min(len(voltage), len(dvdt))
        curves["phase"].setData(np.array(voltage)[:min_len], np.array(dvdt)[:min_len])

        threshold_v = self._val(result, "threshold_v")
        threshold_dvdt = self._val(result, "threshold_dvdt")
        tm_v = self._val(result, "_thresh_marker_v")
        tm_dvdt = self._val(result, "_thresh_marker_dvdt")
        if tm_v is not None and tm_dvdt is not None and len(tm_v) > 0 and len(tm_v) == len(tm_dvdt):
            curves["thresh_marker"].setData(np.asarray(tm_v, dtype=float), np.asarray(tm_dvdt, dtype=float))
        elif (
            threshold_v is not None
            and threshold_dvdt is not None
            and np.isfinite(float(threshold_v))
            and np.isfinite(float(threshold_dvdt))
        ):
            curves["thresh_marker"].setData([float(threshold_v)], [float(threshold_dvdt)])
        else:
            curves["thresh_marker"].setData([], [])

        max_dvdt = self._val(result, "max_dvdt")
        mm_v = self._val(result, "_max_dvdt_marker_v")
        mm_dvdt = self._val(result, "_max_dvdt_marker_dvdt")
        if mm_v is not None and mm_dvdt is not None and len(mm_v) > 0 and len(mm_v) == len(mm_dvdt):
            curves["max_marker"].setData(np.asarray(mm_v, dtype=float), np.asarray(mm_dvdt, dtype=float))
        elif max_dvdt is not None and np.isfinite(float(max_dvdt)) and len(dvdt) > 0:
            idx = int(np.nanargmax(dvdt))
            if idx < len(voltage):
                curves["max_marker"].setData([float(voltage[idx])], [float(dvdt[idx])])
        else:
            curves["max_marker"].setData([], [])

        if threshold_v is not None and max_dvdt is not None and np.isfinite(float(threshold_v)):
            if "phase_stats" not in curves:
                text_item = pg.TextItem(anchor=(0, 1), color=(255, 255, 255), fill=(0, 0, 0, 175))
                popup_plot.addItem(text_item)
                curves["phase_stats"] = text_item
            stats_text = f"Threshold: {float(threshold_v):.1f} {unit}\nMax dV/dt: {float(max_dvdt):.1f} {unit_s}"
            curves["phase_stats"].setText(stats_text)
            v_range = float(np.nanmax(voltage) - np.nanmin(voltage)) or 1.0
            dvdt_range = float(np.nanmax(dvdt) - np.nanmin(dvdt)) or 1.0
            curves["phase_stats"].setPos(
                float(np.nanmin(voltage)) + 0.04 * v_range, float(np.nanmax(dvdt)) - 0.04 * dvdt_range
            )
        elif "phase_stats" in curves:
            curves["phase_stats"].setText("")
        popup_plot.autoRange()

        # Draw threshold line on main plot using raw-trace coordinate (_plot_threshold_v when LJP != 0)
        plot_thresh_v = self._val(result, "_plot_threshold_v")
        if plot_thresh_v is None:
            plot_thresh_v = threshold_v
        if plot_thresh_v is not None and np.isfinite(float(plot_thresh_v)):
            if "main_thresh" not in self._result_hlines:
                line = pg.InfiniteLine(angle=0, pen=pg.mkPen("#d62728", width=1.5, style=QtCore.Qt.PenStyle.DashLine))
                self.plot_widget.addItem(line)
                self._result_hlines["main_thresh"] = line
            self._result_hlines["main_thresh"].setValue(float(plot_thresh_v))
            self._result_hlines["main_thresh"].setVisible(True)
        elif "main_thresh" in self._result_hlines:
            self._result_hlines["main_thresh"].setVisible(False)

    def cleanup(self) -> None:
        """Disconnect theme listeners and clean up popup windows/workers."""
        try:
            from synaptipy.shared.theme_manager import get_theme_signals

            get_theme_signals().theme_changed.disconnect(self._on_theme_changed)
        except (TypeError, RuntimeError):
            pass
        super().cleanup()
