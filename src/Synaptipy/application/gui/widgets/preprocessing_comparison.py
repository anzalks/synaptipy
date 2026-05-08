"""
Preprocessing comparison widget (MEDIUM-13).
Shows before/after preprocessing in a simple dialog.
"""

import logging
from typing import Optional, Tuple  # noqa: F401

import numpy as np
import pyqtgraph as pg
from PySide6 import QtWidgets

log = logging.getLogger(__name__)


class PreprocessingComparisonDialog(QtWidgets.QDialog):
    """Dialog to compare raw vs preprocessed data side-by-side."""

    def __init__(
        self,
        raw_data: np.ndarray,
        raw_time: np.ndarray,
        processed_data: np.ndarray,
        processed_time: np.ndarray,
        title: str = "Preprocessing Comparison",
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(1000, 600)

        self.raw_data = raw_data
        self.raw_time = raw_time
        self.processed_data = processed_data
        self.processed_time = processed_time

        self._setup_ui()

    def _setup_ui(self):
        """Setup the comparison UI with two plots."""
        layout = QtWidgets.QVBoxLayout(self)

        # Info label
        info = QtWidgets.QLabel("Compare raw data (left) with preprocessed data (right)")
        info.setStyleSheet("color: gray; font-style: italic;")
        layout.addWidget(info)

        # Horizontal layout for side-by-side plots
        plot_layout = QtWidgets.QHBoxLayout()

        # Left plot: Raw data
        self.raw_plot = pg.PlotWidget(title="Raw Data")
        self.raw_plot.setLabel("left", "Amplitude")
        self.raw_plot.setLabel("bottom", "Time", units="s")
        self.raw_plot.plot(self.raw_time, self.raw_data, pen=pg.mkPen(color="blue", width=1))
        plot_layout.addWidget(self.raw_plot)

        # Right plot: Processed data
        self.processed_plot = pg.PlotWidget(title="Preprocessed Data")
        self.processed_plot.setLabel("left", "Amplitude")
        self.processed_plot.setLabel("bottom", "Time", units="s")
        self.processed_plot.plot(self.processed_time, self.processed_data, pen=pg.mkPen(color="green", width=1))
        plot_layout.addWidget(self.processed_plot)

        layout.addLayout(plot_layout)

        # Link the X axes for synchronized zooming
        self.processed_plot.setXLink(self.raw_plot)

        # Stats comparison
        stats_group = QtWidgets.QGroupBox("Statistics Comparison")
        stats_layout = QtWidgets.QGridLayout(stats_group)

        # Raw stats
        raw_mean = np.mean(self.raw_data) if len(self.raw_data) > 0 else 0
        raw_std = np.std(self.raw_data) if len(self.raw_data) > 0 else 0
        raw_min = np.min(self.raw_data) if len(self.raw_data) > 0 else 0
        raw_max = np.max(self.raw_data) if len(self.raw_data) > 0 else 0

        # Processed stats
        proc_mean = np.mean(self.processed_data) if len(self.processed_data) > 0 else 0
        proc_std = np.std(self.processed_data) if len(self.processed_data) > 0 else 0
        proc_min = np.min(self.processed_data) if len(self.processed_data) > 0 else 0
        proc_max = np.max(self.processed_data) if len(self.processed_data) > 0 else 0

        # Headers
        stats_layout.addWidget(QtWidgets.QLabel("<b>Metric</b>"), 0, 0)
        stats_layout.addWidget(QtWidgets.QLabel("<b>Raw</b>"), 0, 1)
        stats_layout.addWidget(QtWidgets.QLabel("<b>Preprocessed</b>"), 0, 2)

        # Values
        metrics = [
            ("Mean", raw_mean, proc_mean),
            ("Std Dev", raw_std, proc_std),
            ("Min", raw_min, proc_min),
            ("Max", raw_max, proc_max),
        ]

        for row, (name, raw_val, proc_val) in enumerate(metrics, start=1):
            stats_layout.addWidget(QtWidgets.QLabel(name), row, 0)
            stats_layout.addWidget(QtWidgets.QLabel(f"{raw_val:.4f}"), row, 1)
            stats_layout.addWidget(QtWidgets.QLabel(f"{proc_val:.4f}"), row, 2)

        layout.addWidget(stats_group)

        # Close button
        close_btn = QtWidgets.QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)
