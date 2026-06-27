# src/synaptipy/application/gui/session_summary_dialog.py
# -*- coding: utf-8 -*-
"""
Dialog to display accumulated session results and statistics.
"""

import logging
from typing import Any, Dict, List

import numpy as np
from PySide6 import QtWidgets

log = logging.getLogger(__name__)


class SessionSummaryDialog(QtWidgets.QDialog):
    """
    Dialog showing a table of accumulated results and a summary of statistics (Mean/SD).
    """

    def __init__(self, results: List[Dict[str, Any]], parent=None):
        super().__init__(parent)
        self.results = results
        self.setWindowTitle("Session Summary")
        self.resize(600, 400)
        self._setup_ui()

    def _setup_ui(self):
        layout = QtWidgets.QVBoxLayout(self)

        # 1. Table of individual results
        self.table = QtWidgets.QTableWidget()
        layout.addWidget(self.table)

        # 2. Statistics Summary
        stats_group = QtWidgets.QGroupBox("Session Statistics")
        self.stats_layout = QtWidgets.QFormLayout(stats_group)
        layout.addWidget(stats_group)

        # Populate
        self._populate_table()
        self._calculate_stats()

        # 3. Methods Paragraph
        methods_group = QtWidgets.QGroupBox("Methods Paragraph")
        methods_layout = QtWidgets.QVBoxLayout(methods_group)
        self.methods_text = QtWidgets.QTextEdit()
        self.methods_text.setReadOnly(True)
        self.methods_text.setText(self._generate_methods_paragraph())
        methods_layout.addWidget(self.methods_text)

        copy_btn = QtWidgets.QPushButton("Copy Methods")
        copy_btn.clicked.connect(lambda: QtWidgets.QApplication.clipboard().setText(self.methods_text.toPlainText()))
        methods_layout.addWidget(copy_btn)
        layout.addWidget(methods_group)

        # Close button
        close_btn = QtWidgets.QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)

    def _populate_table(self):
        if not self.results:
            return

        # Determine columns dynamically from keys
        # Filter out complex objects, keep numbers/strings
        keys = []
        sample = self.results[0]
        for k, v in sample.items():
            if isinstance(v, (int, float, str)):
                keys.append(k)

        # Ensure source_label is first
        if "source_label" in keys:
            keys.remove("source_label")
            keys.insert(0, "source_label")

        self.table.setColumnCount(len(keys))
        self.table.setHorizontalHeaderLabels([k.replace("_", " ").title() for k in keys])
        self.table.setRowCount(len(self.results))

        for row, entry in enumerate(self.results):
            for col, key in enumerate(keys):
                val = entry.get(key)
                if isinstance(val, float):
                    item = QtWidgets.QTableWidgetItem(f"{val:.4g}")
                else:
                    item = QtWidgets.QTableWidgetItem(str(val))
                self.table.setItem(row, col, item)

    def _calculate_stats(self):
        if not self.results:
            return

        # Identify numeric columns
        numeric_keys = []
        sample = self.results[0]
        for k, v in sample.items():
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                numeric_keys.append(k)

        for key in numeric_keys:
            values = [r.get(key) for r in self.results if r.get(key) is not None]
            if values:
                mean_val = np.mean(values)
                std_val = np.std(values)

                label = key.replace("_", " ").title()
                self.stats_layout.addRow(f"{label}:", QtWidgets.QLabel(f"{mean_val:.4g} ± {std_val:.4g}"))

    def _generate_methods_paragraph(self) -> str:
        try:
            from synaptipy import __version__

            version = __version__
        except ImportError:
            version = "unknown"

        if not self.results:
            return f"Data was analyzed using Synaptipy {version}."

        sample = self.results[0]
        freq = sample.get("matched_filter_freq", "X")
        prominence = sample.get("prominence_factor", "Y")

        # You can expand this logic to extract more actual parameters
        return (
            f"Data was analyzed using Synaptipy {version}. "
            f"Event detection utilized a matched filter (freq: {freq} Hz) "
            f"with a prominence factor of {prominence}."
        )
