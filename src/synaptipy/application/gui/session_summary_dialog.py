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

    @staticmethod
    def _flatten_entry(entry: Dict[str, Any]) -> Dict[str, Any]:
        """Unpack Schema v1 nested 'metrics' while filtering private/internal keys."""
        skip = {"schema_version", "module_used", "data_source", "xfa_sources", "_analysis_type_override"}
        flat: Dict[str, Any] = {}
        if "source_label" in entry:
            flat["source_label"] = entry["source_label"]
        metrics = entry.get("metrics")
        if isinstance(metrics, dict):
            for k, v in metrics.items():
                if not str(k).startswith("_") and k not in skip and not str(k).endswith("_error"):
                    flat[k] = v
        for k, v in entry.items():
            if (
                not str(k).startswith("_")
                and k not in skip
                and k != "metrics"
                and not str(k).endswith("_error")
                and k not in flat
            ):
                flat[k] = v
        return flat

    def _populate_table(self):
        if not self.results:
            return

        flat_rows = [self._flatten_entry(r) for r in self.results]

        # Collect union of scalar keys in deterministic order
        keys: List[str] = []
        for row_dict in flat_rows:
            for k, v in row_dict.items():
                if k not in keys and isinstance(v, (int, float, str, np.number)) and not isinstance(v, bool):
                    keys.append(k)

        if "source_label" in keys:
            keys.remove("source_label")
            keys.insert(0, "source_label")

        self.table.setColumnCount(len(keys))
        self.table.setHorizontalHeaderLabels([k.replace("_", " ").title() for k in keys])
        self.table.setRowCount(len(flat_rows))

        for row, entry in enumerate(flat_rows):
            for col, key in enumerate(keys):
                val = entry.get(key)
                if val is None:
                    item = QtWidgets.QTableWidgetItem("N/A")
                elif isinstance(val, (float, np.floating)):
                    vf = float(val)
                    item = QtWidgets.QTableWidgetItem("N/A" if (np.isnan(vf) or np.isinf(vf)) else f"{vf:.4g}")
                else:
                    item = QtWidgets.QTableWidgetItem(str(val))
                self.table.setItem(row, col, item)

    def _calculate_stats(self):
        if not self.results:
            return

        flat_rows = [self._flatten_entry(r) for r in self.results]
        numeric_keys: List[str] = []
        for row_dict in flat_rows:
            for k, v in row_dict.items():
                if k not in numeric_keys and isinstance(v, (int, float, np.number)) and not isinstance(v, bool):
                    numeric_keys.append(k)

        for key in numeric_keys:
            values = [
                float(r[key])
                for r in flat_rows
                if r.get(key) is not None
                and isinstance(r.get(key), (int, float, np.number))
                and not isinstance(r.get(key), bool)
                and np.isfinite(float(r[key]))
            ]
            if values:
                mean_val = float(np.nanmean(values))
                std_val = float(np.nanstd(values))

                label = key.replace("_", " ").title()
                self.stats_layout.addRow(
                    f"{label} (n={len(values)}):", QtWidgets.QLabel(f"{mean_val:.4g} +/- {std_val:.4g}")
                )

    def _generate_methods_paragraph(self) -> str:
        try:
            from synaptipy import __version__

            version = __version__
        except ImportError:
            version = "unknown"

        if not self.results:
            return f"Electrophysiology data were analyzed using Synaptipy {version}."

        from synaptipy.application.controllers.analysis_formatter import generate_methods_text

        sample = self.results[0]
        detail_text = generate_methods_text(sample)
        return (
            f"Electrophysiology data were analyzed using Synaptipy {version} "
            f"(n = {len(self.results)}). {detail_text}"
        )
