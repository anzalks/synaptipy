# src/Synaptipy/application/gui/dialogs/export_manager.py
# -*- coding: utf-8 -*-
"""
Export manager for analysis tabs.

Encapsulates popup-plot creation and plot-to-file saving so that
``BaseAnalysisTab`` can delegate all export logic here (Phase 4 of the
Composition-over-Inheritance refactor).
"""

import csv
import logging
from pathlib import Path
from typing import Optional, Tuple

import pyqtgraph as pg
from PySide6 import QtCore, QtWidgets

from Synaptipy.application.gui.dialogs.plot_export_dialog import PlotExportDialog
from Synaptipy.shared.plot_exporter import PlotExporter

log = logging.getLogger(__name__)


class ExportManager(QtCore.QObject):
    """Handles popup plot creation and saving plots to files.

    This object is intended to be owned by a ``BaseAnalysisTab`` instance.
    It has no knowledge of analysis data - it only manages Qt windows and
    file I/O.

    Args:
        parent: The owning widget (``BaseAnalysisTab``).
    """

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        """Initialise the ExportManager."""
        super().__init__(parent)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def create_popup_plot(
        self,
        title: str,
        x_label: Optional[str] = None,
        y_label: Optional[str] = None,
        parent_widget: Optional[QtWidgets.QWidget] = None,
    ) -> Tuple[QtWidgets.QMainWindow, pg.PlotWidget]:
        """Create a standalone popup window containing a PlotWidget.

        The caller is responsible for appending the returned QMainWindow
        to its own popup-window registry (e.g. ``self._popup_windows``).

        Args:
            title: Window title string.
            x_label: Optional X-axis label.
            y_label: Optional Y-axis label.
            parent_widget: Qt parent for the window.

        Returns:
            ``(popup_window, plot_widget)`` tuple.
        """
        from Synaptipy.shared.plot_factory import SynaptipyPlotFactory
        from Synaptipy.shared.styling import style_button

        popup = QtWidgets.QMainWindow(parent_widget)
        popup.setWindowTitle(title)
        popup.resize(600, 440)
        popup.setAttribute(QtCore.Qt.WidgetAttribute.WA_DeleteOnClose, False)

        central_widget = QtWidgets.QWidget()
        popup.setCentralWidget(central_widget)
        layout = QtWidgets.QVBoxLayout(central_widget)

        plot_widget = SynaptipyPlotFactory.create_plot_widget(parent=central_widget)
        if x_label:
            plot_widget.setLabel("bottom", x_label)
        if y_label:
            plot_widget.setLabel("left", y_label)
        layout.addWidget(plot_widget, stretch=1)

        btn_layout = QtWidgets.QHBoxLayout()
        btn_layout.addStretch()

        reset_btn = QtWidgets.QPushButton("Reset View")
        reset_btn.setToolTip("Reset zoom and pan to fit all data in this popup.")
        style_button(reset_btn)
        reset_btn.clicked.connect(lambda: plot_widget.autoRange())
        btn_layout.addWidget(reset_btn)

        save_plot_btn = QtWidgets.QPushButton("Save Plot")
        save_plot_btn.setToolTip("Save this plot as an image file (PNG, PDF, SVG).")
        style_button(save_plot_btn)
        save_plot_btn.clicked.connect(lambda: self._save_popup_plot(plot_widget, title, popup))
        btn_layout.addWidget(save_plot_btn)

        export_btn = QtWidgets.QPushButton("Export Data")
        export_btn.setToolTip("Export the plotted data values as a CSV file.")
        style_button(export_btn)
        export_btn.clicked.connect(lambda: self._export_popup_data(plot_widget, title, popup))
        btn_layout.addWidget(export_btn)

        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        popup.show()
        return popup, plot_widget

    def save_plot(
        self,
        plot_widget,
        tab_name: str,
        recording,
        parent_widget: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        """Open format/DPI dialogs then save *plot_widget* to a file.

        Args:
            plot_widget: pyqtgraph PlotItem or PlotWidget to export.
            tab_name: Used to generate the default filename suggestion.
            recording: Current recording object (may be None).
            parent_widget: Parent for dialogs.
        """
        try:
            default_name = tab_name.lower().replace("tab", "").replace(" ", "_") + "_plot"

            dialog = PlotExportDialog(parent_widget)
            if not dialog.exec():
                log.debug("[ExportManager] Save plot cancelled")
                return

            settings = dialog.get_settings()
            fmt = settings["format"]
            dpi = settings["dpi"]

            filename, _ = QtWidgets.QFileDialog.getSaveFileName(
                parent_widget,
                "Save Plot",
                str(Path.home() / f"{default_name}.{fmt}"),
                f"Images (*.{fmt})",
            )
            if not filename:
                return

            exporter = PlotExporter(recording=recording, plot_canvas_widget=plot_widget)
            success = exporter.export(filename, fmt, dpi)

            if success:
                log.debug("[ExportManager] Plot saved to %s", filename)
            else:
                log.warning("[ExportManager] PlotExporter.export() returned False")

        except Exception as exc:
            log.error("[ExportManager] Failed to save plot: %s", exc)
            QtWidgets.QMessageBox.critical(parent_widget, "Save Error", f"Failed to save plot:\n{exc}")

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _save_popup_plot(
        self,
        plot_widget: pg.PlotWidget,
        title: str,
        popup: QtWidgets.QMainWindow,
    ) -> None:
        """Save popup plot to file (invoked from popup Save Plot button)."""
        try:
            dialog = PlotExportDialog(popup)
            if not dialog.exec():
                return

            cfg = dialog.get_settings()
            fmt = cfg["format"]
            dpi = cfg["dpi"]

            safe_title = title.lower().replace(" ", "_")
            filename, _ = QtWidgets.QFileDialog.getSaveFileName(
                popup,
                "Save Plot",
                str(Path.home() / f"{safe_title}.{fmt}"),
                f"Images (*.{fmt})",
            )
            if filename:
                exporter = PlotExporter(recording=None, plot_canvas_widget=plot_widget)
                exporter.export(filename, fmt, dpi)

        except Exception as exc:
            log.error("[ExportManager] Popup plot save error: %s", exc)
            QtWidgets.QMessageBox.critical(popup, "Save Error", str(exc))

    def _export_popup_data(
        self,
        plot_widget: pg.PlotWidget,
        title: str,
        popup: QtWidgets.QMainWindow,
    ) -> None:
        """Export popup plot data to CSV (invoked from popup Export Data button)."""
        try:
            safe_title = title.lower().replace(" ", "_")
            filename, _ = QtWidgets.QFileDialog.getSaveFileName(
                popup,
                "Export Data",
                str(Path.home() / f"{safe_title}_data.csv"),
                "CSV Files (*.csv)",
            )
            if not filename:
                return

            with open(filename, "w", newline="", encoding="utf-8") as fh:
                writer = csv.writer(fh)
                writer.writerow(["x", "y"])
                for item in plot_widget.getPlotItem().items:
                    if hasattr(item, "getData"):
                        xs, ys = item.getData()
                        if xs is not None and ys is not None:
                            for x, y in zip(xs, ys):
                                writer.writerow([x, y])

        except Exception as exc:
            log.error("[ExportManager] Popup data export error: %s", exc)
            QtWidgets.QMessageBox.critical(popup, "Export Error", str(exc))
