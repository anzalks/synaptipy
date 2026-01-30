# src/Synaptipy/application/gui/explorer/toolbar.py
# -*- coding: utf-8 -*-
"""
Explorer Toolbar.
Handles file navigation, trial cycling, and X-axis controls.
"""
import logging

from PySide6 import QtCore, QtWidgets

log = logging.getLogger(__name__)


class ExplorerToolbar(QtWidgets.QWidget):
    """
    Toolbar containing file navigation and plot view controls.
    """

    prev_file_clicked = QtCore.Signal()
    next_file_clicked = QtCore.Signal()

    reset_view_clicked = QtCore.Signal()
    save_plot_clicked = QtCore.Signal()

    x_zoom_changed = QtCore.Signal(int)

    prev_trial_clicked = QtCore.Signal()
    next_trial_clicked = QtCore.Signal()

    SLIDER_RANGE_MIN = 0
    SLIDER_RANGE_MAX = 1000
    SLIDER_DEFAULT_VALUE = SLIDER_RANGE_MIN

    def __init__(self, parent=None):
        super().__init__(parent)

        self._x_zoom_timer = QtCore.QTimer()
        self._x_zoom_timer.setSingleShot(True)
        self._x_zoom_timer.setInterval(50)
        self._x_zoom_timer.timeout.connect(self._emit_x_zoom)

        self._setup_ui()

    def _setup_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)

        # 1. File Navigation Row
        nav_layout = QtWidgets.QHBoxLayout()
        self.prev_file_btn = QtWidgets.QPushButton("<< Prev File")
        self.prev_file_btn.clicked.connect(self.prev_file_clicked.emit)

        self.next_file_btn = QtWidgets.QPushButton("Next File >>")
        self.next_file_btn.clicked.connect(self.next_file_clicked.emit)

        self.file_index_lbl = QtWidgets.QLabel("")
        self.file_index_lbl.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

        nav_layout.addWidget(self.prev_file_btn)
        nav_layout.addStretch()
        nav_layout.addWidget(self.file_index_lbl)
        nav_layout.addStretch()
        nav_layout.addWidget(self.next_file_btn)

        layout.addLayout(nav_layout)

        # 2. Plot Controls Row
        plot_layout = QtWidgets.QHBoxLayout()

        # View Group
        self.view_group = QtWidgets.QGroupBox("View")
        view_layout = QtWidgets.QHBoxLayout(self.view_group)
        self.reset_btn = QtWidgets.QPushButton("Reset View")
        self.reset_btn.clicked.connect(self.reset_view_clicked.emit)
        self.save_btn = QtWidgets.QPushButton("Save Plot")
        self.save_btn.clicked.connect(self.save_plot_clicked.emit)
        view_layout.addWidget(self.reset_btn)
        view_layout.addWidget(self.save_btn)
        plot_layout.addWidget(self.view_group)

        # X Zoom Group
        self.x_zoom_group = QtWidgets.QGroupBox("Time Zoom (X-Axis)")
        x_zoom_layout = QtWidgets.QHBoxLayout(self.x_zoom_group)
        self.x_zoom_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.x_zoom_slider.setRange(self.SLIDER_RANGE_MIN, self.SLIDER_RANGE_MAX)
        self.x_zoom_slider.setValue(self.SLIDER_DEFAULT_VALUE)
        self.x_zoom_slider.valueChanged.connect(self._on_x_zoom_changed)
        x_zoom_layout.addWidget(self.x_zoom_slider)
        plot_layout.addWidget(self.x_zoom_group, 1)

        # Trial Group
        self.trial_group = QtWidgets.QGroupBox("Trial (Cycle)")
        trial_layout = QtWidgets.QHBoxLayout(self.trial_group)
        self.prev_trial_btn = QtWidgets.QPushButton("< Prev")
        self.prev_trial_btn.clicked.connect(self.prev_trial_clicked.emit)

        self.next_trial_btn = QtWidgets.QPushButton("Next >")
        self.next_trial_btn.clicked.connect(self.next_trial_clicked.emit)

        self.trial_idx_lbl = QtWidgets.QLabel("N/A")
        self.trial_idx_lbl.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

        trial_layout.addWidget(self.prev_trial_btn)
        trial_layout.addWidget(self.trial_idx_lbl)
        trial_layout.addWidget(self.next_trial_btn)
        plot_layout.addWidget(self.trial_group)

        layout.addLayout(plot_layout)

    def _on_x_zoom_changed(self, value):
        self._x_zoom_timer.start()

    def _emit_x_zoom(self):
        self.x_zoom_changed.emit(self.x_zoom_slider.value())

    def update_file_nav(self, current, total):
        if total > 0:
            self.file_index_lbl.setText(f"{current + 1} / {total}")
        else:
            self.file_index_lbl.setText("")

    def update_trial_nav(self, current, total):
        self.trial_idx_lbl.setText(f"{current + 1} / {total}" if total > 0 else "N/A")

    def set_trial_nav_enabled(self, enabled):
        self.trial_group.setEnabled(enabled)
