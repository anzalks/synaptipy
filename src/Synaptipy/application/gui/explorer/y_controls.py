# src/Synaptipy/application/gui/explorer/y_controls.py
# -*- coding: utf-8 -*-
"""
Explorer Y-Axis Controls widget.
Handles global and individual Y-axis zoom/scroll controls.
"""

import logging
from typing import Dict, Optional

from PySide6 import QtCore, QtWidgets

from Synaptipy.core.data_model import Recording

log = logging.getLogger(__name__)


class ExplorerYControls(QtWidgets.QWidget):
    """
    Widget containing Y-axis sliders and scrollbars.
    """

    global_zoom_changed = QtCore.Signal(int)
    global_scroll_changed = QtCore.Signal(int)
    channel_zoom_changed = QtCore.Signal(str, int)
    channel_scroll_changed = QtCore.Signal(str, int)
    lock_toggled = QtCore.Signal(bool)

    SLIDER_RANGE_MIN = 0
    SLIDER_RANGE_MAX = 1000
    SLIDER_DEFAULT_VALUE = SLIDER_RANGE_MIN
    SCROLLBAR_MAX_RANGE = 10000

    def __init__(self, parent=None):
        super().__init__(parent)

        # State
        self.individual_y_sliders: Dict[str, QtWidgets.QSlider] = {}
        self.individual_y_scrollbars: Dict[str, QtWidgets.QScrollBar] = {}

        self.individual_y_zoom_timers: Dict[str, QtCore.QTimer] = {}
        self.individual_y_scroll_timers: Dict[str, QtCore.QTimer] = {}

        self._last_individual_y_zoom_values: Dict[str, int] = {}
        self._last_individual_y_scroll_values: Dict[str, int] = {}

        self._setup_ui()
        self._setup_timers()

    def _setup_timers(self):
        # Global timers
        self._y_global_zoom_apply_timer = QtCore.QTimer()
        self._y_global_zoom_apply_timer.setSingleShot(True)
        self._y_global_zoom_apply_timer.setInterval(50)
        self._y_global_zoom_apply_timer.timeout.connect(
            lambda: self.global_zoom_changed.emit(self.global_y_slider.value())
        )

        self._y_global_scroll_apply_timer = QtCore.QTimer()
        self._y_global_scroll_apply_timer.setSingleShot(True)
        self._y_global_scroll_apply_timer.setInterval(50)
        self._y_global_scroll_apply_timer.timeout.connect(
            lambda: self.global_scroll_changed.emit(self.global_y_scrollbar.value())
        )

    def _setup_ui(self):
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)

        # Scroll Group
        self.y_scroll_widget = QtWidgets.QWidget()
        y_scroll_layout = QtWidgets.QVBoxLayout(self.y_scroll_widget)
        y_scroll_layout.setContentsMargins(0, 0, 0, 0)
        y_scroll_group = QtWidgets.QGroupBox("Y Scroll")
        y_scroll_group_layout = QtWidgets.QVBoxLayout(y_scroll_group)
        y_scroll_layout.addWidget(y_scroll_group)

        # Global Scrollbar
        self.global_y_scrollbar = QtWidgets.QScrollBar(QtCore.Qt.Orientation.Vertical)
        self.global_y_scrollbar.setRange(0, self.SCROLLBAR_MAX_RANGE)
        self.global_y_scrollbar.setToolTip("Y scroll (All)")
        self.global_y_scrollbar.valueChanged.connect(self._on_global_scroll_changed)

        gs_layout = QtWidgets.QVBoxLayout()
        gs_layout.setSpacing(2)
        gs_layout.addWidget(QtWidgets.QLabel("Global", alignment=QtCore.Qt.AlignmentFlag.AlignCenter))
        gs_layout.addWidget(self.global_y_scrollbar, 1)
        y_scroll_group_layout.addLayout(gs_layout, 1)

        # Individual Scrollbars Container
        self.individual_y_scrollbars_container = QtWidgets.QWidget()
        self.individual_y_scrollbars_layout = QtWidgets.QVBoxLayout(self.individual_y_scrollbars_container)
        self.individual_y_scrollbars_layout.setContentsMargins(0, 5, 0, 0)
        self.individual_y_scrollbars_layout.setSpacing(10)
        self.individual_y_scrollbars_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)
        y_scroll_group_layout.addWidget(self.individual_y_scrollbars_container, 1)

        layout.addWidget(self.y_scroll_widget, 1)

        # Zoom Controls (Exposed for external grid layout)

        # Lock Checkbox
        self.y_lock_checkbox = QtWidgets.QCheckBox("Lock Y Views")
        self.y_lock_checkbox.setToolTip("Link Y axes across channels")
        self.y_lock_checkbox.setChecked(True)
        self.y_lock_checkbox.stateChanged.connect(self._on_lock_changed)

        # Global Slider
        self.global_y_lbl = QtWidgets.QLabel("Signal (Y):")

        self.global_y_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.global_y_slider.setRange(self.SLIDER_RANGE_MIN, self.SLIDER_RANGE_MAX)
        self.global_y_slider.setValue(self.SLIDER_DEFAULT_VALUE)
        self.global_y_slider.setToolTip("Y zoom (All)")
        self.global_y_slider.valueChanged.connect(self._on_global_zoom_changed)

        # We keep individual sliders container for later use
        self.individual_y_sliders_container = QtWidgets.QWidget()
        self.individual_y_sliders_layout = QtWidgets.QVBoxLayout(self.individual_y_sliders_container)
        self.individual_y_sliders_layout.setContentsMargins(0, 5, 0, 0)
        self.individual_y_sliders_layout.setSpacing(2)
        self.individual_y_sliders_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)

    def rebuild(self, recording: Optional[Recording]):
        """Rebuild individual controls for the recording channels."""
        # Clear existing
        self._clear_individual_controls()

        if not recording or not recording.channels:
            return

        for chan_id, channel in recording.channels.items():
            display_name = f"{channel.name}" if hasattr(channel, "name") and channel.name else f"Ch {chan_id}"

            # Slider
            slider_container = QtWidgets.QWidget()
            slider_layout = QtWidgets.QHBoxLayout(slider_container)
            slider_layout.setContentsMargins(0, 0, 0, 0)
            slider_layout.setSpacing(5)
            slider_layout.addWidget(
                QtWidgets.QLabel(
                    display_name, alignment=QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter
                )
            )

            y_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
            y_slider.setRange(self.SLIDER_RANGE_MIN, self.SLIDER_RANGE_MAX)
            y_slider.setValue(self.SLIDER_DEFAULT_VALUE)
            y_slider.setToolTip(f"Y zoom for {display_name}")
            y_slider.valueChanged.connect(lambda v, c=chan_id: self._on_individual_zoom_changed(c, v))

            slider_layout.addWidget(y_slider, 1)
            self.individual_y_sliders_layout.addWidget(slider_container)
            self.individual_y_sliders[chan_id] = y_slider

            # Scrollbar
            scroll_container = QtWidgets.QWidget()
            scroll_layout = QtWidgets.QVBoxLayout(scroll_container)
            scroll_layout.setContentsMargins(0, 0, 0, 0)
            scroll_layout.setSpacing(2)
            scroll_layout.addWidget(QtWidgets.QLabel(display_name, alignment=QtCore.Qt.AlignmentFlag.AlignCenter))

            y_scrollbar = QtWidgets.QScrollBar(QtCore.Qt.Orientation.Vertical)
            y_scrollbar.setRange(0, self.SCROLLBAR_MAX_RANGE)
            y_scrollbar.setValue(self.SCROLLBAR_MAX_RANGE // 2)
            y_scrollbar.setToolTip(f"Y pan for {display_name}")
            y_scrollbar.valueChanged.connect(lambda v, c=chan_id: self._on_individual_scroll_changed(c, v))

            scroll_layout.addWidget(y_scrollbar, 1)
            self.individual_y_scrollbars_layout.addWidget(scroll_container)
            self.individual_y_scrollbars[chan_id] = y_scrollbar

        self._update_visibility()

    def _clear_individual_controls(self):
        # Disconnect and remove widgets
        for i in reversed(range(self.individual_y_sliders_layout.count())):
            item = self.individual_y_sliders_layout.takeAt(i)
            if item.widget():
                item.widget().deleteLater()

        for i in reversed(range(self.individual_y_scrollbars_layout.count())):
            item = self.individual_y_scrollbars_layout.takeAt(i)
            if item.widget():
                item.widget().deleteLater()

        self.individual_y_sliders.clear()
        self.individual_y_scrollbars.clear()
        self.individual_y_zoom_timers.clear()
        self.individual_y_scroll_timers.clear()

    def _update_visibility(self):
        locked = self.y_lock_checkbox.isChecked()
        self.global_y_slider.setEnabled(locked)
        self.global_y_scrollbar.setEnabled(locked)
        self.individual_y_sliders_container.setVisible(not locked)
        self.individual_y_scrollbars_container.setVisible(not locked)

    # --- Event Handlers ---

    def _on_lock_changed(self, state):
        self._update_visibility()
        self.lock_toggled.emit(self.y_lock_checkbox.isChecked())

    def _on_global_zoom_changed(self, value):
        self._y_global_zoom_apply_timer.start()

    def _on_global_scroll_changed(self, value):
        self._y_global_scroll_apply_timer.start()

    def _on_individual_zoom_changed(self, chan_id, value):
        self._last_individual_y_zoom_values[chan_id] = value
        if chan_id not in self.individual_y_zoom_timers:
            timer = QtCore.QTimer()
            timer.setSingleShot(True)
            timer.setInterval(50)
            timer.timeout.connect(lambda: self._emit_individual_zoom(chan_id))
            self.individual_y_zoom_timers[chan_id] = timer
        self.individual_y_zoom_timers[chan_id].start()

    def _emit_individual_zoom(self, chan_id):
        val = self._last_individual_y_zoom_values.get(chan_id)
        if val is not None:
            self.channel_zoom_changed.emit(chan_id, val)

    def _on_individual_scroll_changed(self, chan_id, value):
        self._last_individual_y_scroll_values[chan_id] = value
        if chan_id not in self.individual_y_scroll_timers:
            timer = QtCore.QTimer()
            timer.setSingleShot(True)
            timer.setInterval(50)
            timer.timeout.connect(lambda: self._emit_individual_scroll(chan_id))
            self.individual_y_scroll_timers[chan_id] = timer
        self.individual_y_scroll_timers[chan_id].start()

    def _emit_individual_scroll(self, chan_id):
        val = self._last_individual_y_scroll_values.get(chan_id)
        if val is not None:
            self.channel_scroll_changed.emit(chan_id, val)

    # --- Public Accessors to update standard UI ---
    def set_global_scrollbar(self, value, block=True):
        sb = self.global_y_scrollbar
        if block:
            sb.blockSignals(True)
        sb.setValue(value)
        if block:
            sb.blockSignals(False)

    def set_individual_scrollbar(self, chan_id, value, block=True):
        sb = self.individual_y_scrollbars.get(chan_id)
        if sb:
            if block:
                sb.blockSignals(True)
            sb.setValue(value)
            if block:
                sb.blockSignals(False)
