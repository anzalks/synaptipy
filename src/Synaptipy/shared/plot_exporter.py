# src/Synaptipy/shared/plot_exporter.py
# -*- coding: utf-8 -*-
"""
Plot Exporter Utility.
Handles export of plots to various formats (SVG, PDF, PNG, JPG) using
Matplotlib (for vector quality) or PyQtGraph (for raster WYSIWYG).
"""

import logging
from typing import Any, Dict

import pyqtgraph as pg
import pyqtgraph.exporters

from Synaptipy.core.data_model import Recording
from Synaptipy.shared.plot_customization import get_average_pen, get_force_opaque_trials, get_single_trial_pen

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Hybrid-rendering DPI for PDF/SVG exports.
# Rasterized layers (dense traces, filled regions) are embedded at this DPI
# so they remain sharp in print while keeping axes/text as true vectors.
# ---------------------------------------------------------------------------
_RASTER_DPI = 300


class PlotExporter:
    """
    Handles logic for exporting plots from the ExplorerTab (or similar).
    """

    def __init__(
        self,
        recording: Recording,
        plot_canvas_widget: Any,
        plot_canvas_wrapper: Any = None,
        config: Dict[str, Any] = None,
    ):
        """
        Args:
            recording: Current Recording object.
            plot_canvas_widget: The actual pg.GraphicsLayoutWidget (raster) or pg.PlotWidget.
            plot_canvas_wrapper: The wrapper (ExplorerPlotCanvas) for get_plot(). Optional.
            config: Configuration dict.
        """
        self.recording = recording
        self.widget = plot_canvas_widget
        self.wrapper = plot_canvas_wrapper
        self.config = config or {}

    def export(self, filename: str, fmt: str, dpi: int) -> bool:
        """
        Export the plot to the specified file.
        Returns True if successful, False otherwise.
        """
        try:
            if fmt in ["svg", "pdf"]:
                return self._save_via_matplotlib(filename, fmt, dpi)
            else:
                return self._save_via_pyqtgraph(filename, fmt, dpi)
        except Exception as e:
            log.error(f"Export failed: {e}")
            raise e

    def _save_via_pyqtgraph(self, filename: str, fmt: str, dpi: int) -> bool:
        """Save raster images using pyqtgraph (WYSIWYG).

        Explicitly sets an opaque white background before grabbing the widget so
        that macOS Dark Mode or transparent Qt themes do not bleed a dark canvas
        colour through semi-transparent shaded regions in the exported PNG.
        The original background is restored immediately after the capture.
        """
        # Use the central layout item (.ci) if avail, else the widget itself
        target_item = getattr(self.widget, "ci", self.widget)

        # If it's a PlotWidget, target the PlotItem
        if hasattr(self.widget, "getPlotItem"):
            target_item = self.widget.getPlotItem()

        # --- Force opaque white background for PNG export ---
        # Issue 2 fix: prevents OS dark-mode from compositing a dark canvas
        # through transparent Qt backgrounds, which makes alpha shading appear
        # muddy / over-dark in image viewers (Preview, Finder Quick Look, etc.)
        original_bg = None
        try:
            if hasattr(self.widget, "backgroundBrush"):
                original_bg = self.widget.backgroundBrush()
            if hasattr(self.widget, "setBackground"):
                self.widget.setBackground("w")  # solid white
        except Exception:
            pass  # non-fatal — proceed with whatever background exists

        try:
            exporter = pg.exporters.ImageExporter(target_item)

            # Scale for DPI (Screen DPI is usually ~96)
            scale_factor = dpi / 96.0
            exporter.parameters()["width"] = int(target_item.width() * scale_factor)

            exporter.export(filename)
            log.info(f"Exported raster plot to {filename}")
            return True
        finally:
            # Restore original background
            try:
                if original_bg is not None and hasattr(self.widget, "setBackground"):
                    self.widget.setBackground(original_bg)
            except Exception:
                pass

    def _save_via_matplotlib(self, filename: str, fmt: str, dpi: int) -> bool:  # noqa: C901
        """
        Save vector plots using Matplotlib for publication quality.

        Hybrid rendering strategy (Issue 1b + Issue 2):
        - Axes, tick labels, and text are rendered as **true vectors** (crisp at any zoom).
        - Dense raw-data lines and filled/shaded regions use ``rasterized=True`` so they
          are embedded as a single high-DPI bitmap layer inside the PDF/SVG.  This prevents:
            * PDF file bloat (one vector path per sample point),
            * Alpha-compositing stitching artefacts in Acrobat / Preview,
            * Viewer crashes on high-density recordings (>100 k points per line).
        - The raster DPI used for embedded bitmaps is ``_RASTER_DPI`` (300 dpi) regardless
          of the ``dpi`` argument so that the embedded layer is always print-quality.

        PNG alpha-stacking / Dark Mode fix (Issue 2):
        - Each call creates a *fresh* Figure + Axes (no state bleed between exports).
        - ``fig.savefig`` always uses ``facecolor='white', transparent=False`` so that
          macOS Dark Mode or any OS-level theme cannot composite a dark canvas colour
          through the transparent PNG background.
        - Every Axes face is also explicitly set to white (``ax.set_facecolor('white')``).

        Extracts data directly from pyqtgraph PlotDataItems to match screen appearance.
        """
        import matplotlib
        import matplotlib.pyplot as plt

        # Use the non-interactive Agg backend for off-screen rendering.
        # This avoids "matplotlib not found" errors that occur when the Qt backend
        # tries to create a display window in a headless / embedded context.
        matplotlib.use("Agg")

        # 1. Setup Figure
        plots_to_export = []

        if self.wrapper:
            # Explorer Mode: Multiple channels via wrapper
            for cid in self.recording.channels.keys():
                plot_item = self.wrapper.get_plot(cid)
                if plot_item and plot_item.isVisible():
                    plots_to_export.append((cid, plot_item))
        else:
            # Analysis Mode: Single PlotWidget
            if hasattr(self.widget, "getPlotItem"):
                plot_item = self.widget.getPlotItem()
                plots_to_export.append(("Analysis", plot_item))
            else:
                # Fallback for generic widgets
                log.warning("Widget does not have getPlotItem(). Cannot export vector.")
                return False

        if not plots_to_export:
            log.warning("No visible plots to export.")
            return False

        n_plots = len(plots_to_export)
        # Figure size: Match screen aspect ratio
        screen_width = self.widget.width()
        screen_height = self.widget.height()

        if screen_width > 0 and screen_height > 0:
            aspect_ratio = screen_width / screen_height
            fig_width = 12
            fig_height = fig_width / aspect_ratio
        else:
            fig_width = 10
            fig_height = 3 * n_plots

        # Always create a FRESH figure — never reuse a previous one.
        # This is the core guard against alpha-stacking (Issue 2): if the same
        # Figure object were reused, previously drawn semi-transparent regions
        # would accumulate on top of the new draw.
        fig, axes = plt.subplots(
            n_plots,
            1,
            sharex=True,
            figsize=(fig_width, fig_height),
            dpi=_RASTER_DPI,  # Use high DPI so rasterized layers are sharp in print
            facecolor="white",  # Solid white canvas — blocks OS dark-mode bleed
        )
        if n_plots == 1:
            axes = [axes]

        # Get styling from customization manager
        avg_pen = get_average_pen()
        trial_pen = get_single_trial_pen()

        # Helper to extract color/alpha from QPen
        def pen_to_mpl(pen):
            c = pen.color()
            return (c.redF(), c.greenF(), c.blueF()), c.alphaF()

        avg_color, avg_alpha = pen_to_mpl(avg_pen)
        trial_color, trial_alpha = pen_to_mpl(trial_pen)

        if get_force_opaque_trials():
            trial_alpha = 1.0

        # Determine whether to rasterize data layers (always True for PDF/SVG).
        # For PNG output coming through this path (unusual but possible), rasterizing
        # is still harmless since the whole file is a bitmap anyway.
        use_rasterized = fmt in ("pdf", "svg")

        # 2. Iterate and extract data DIRECTLY from pyqtgraph PlotDataItems
        for i, (label, plot_item) in enumerate(plots_to_export):
            ax = axes[i]

            # Issue 2 fix: always set a white axes face so that OS themes cannot
            # composite a dark colour through transparent Matplotlib patch regions.
            ax.set_facecolor("white")

            # Get current view range to match screen
            vb = plot_item.getViewBox()
            x_range = vb.viewRange()[0]
            y_range = vb.viewRange()[1]

            # Extract all PlotDataItems from this plot
            plotted_items = []
            if hasattr(plot_item, "listDataItems"):
                plotted_items = plot_item.listDataItems()
            else:
                for item in plot_item.items:
                    if isinstance(item, pg.PlotDataItem):
                        plotted_items.append(item)

            # Plot each data item
            for item in plotted_items:
                try:
                    # Get the actual data from the PlotDataItem
                    x_data, y_data = item.getData()

                    if x_data is None or y_data is None:
                        continue
                    if len(x_data) == 0 or len(y_data) == 0:
                        continue

                    # Ensure arrays have same length
                    min_len = min(len(x_data), len(y_data))
                    x_data = x_data[:min_len]
                    y_data = y_data[:min_len]

                    # Determine if this is an average or trial line
                    item_name = item.name() if item.name() else ""
                    is_average = "Average" in item_name or "average" in item_name

                    # Respect the item's own pen if possible; fall back to global pens
                    item_pen = item.opts.get("pen")
                    if item_pen:
                        import PySide6.QtGui

                        if isinstance(item_pen, PySide6.QtGui.QPen):
                            c, a = pen_to_mpl(item_pen)
                            mp_color, mp_alpha = c, a
                        else:
                            mp_color, mp_alpha = trial_color, trial_alpha
                    else:
                        mp_color, mp_alpha = trial_color, trial_alpha

                    if is_average:
                        ax.plot(
                            x_data,
                            y_data,
                            color=mp_color if self.wrapper else avg_color,
                            alpha=mp_alpha if self.wrapper else avg_alpha,
                            linewidth=1.5,
                            zorder=10,
                            # Averages are thinner datasets — keep as vectors for crispness.
                            rasterized=False,
                        )
                    else:
                        # Issue 1b — Hybrid rendering:
                        # Raw trial traces can have tens of thousands of points. Rasterizing
                        # them prevents PDF/SVG bloat and compositing artefacts while the axes
                        # frame, labels, and average line stay as clean vectors.
                        ax.plot(
                            x_data,
                            y_data,
                            color=mp_color,
                            alpha=mp_alpha,
                            linewidth=0.8,
                            rasterized=use_rasterized,
                        )

                except Exception as e:
                    log.warning(f"Failed to extract data from plot item: {e}")
                    continue

            # Styling Axes
            ax.set_xlim(x_range)
            ax.set_ylim(y_range)

            # Label
            if self.wrapper and hasattr(self.recording, "channels") and label in self.recording.channels:
                chan = self.recording.channels[label]
                ax.set_ylabel(f"{chan.get_primary_data_label()} ({chan.units})")
            else:
                ax.set_ylabel(label)

            # Remove top/right spines (publication style)
            ax.spines["right"].set_visible(False)
            ax.spines["top"].set_visible(False)
            ax.grid(True, alpha=0.3)

        # Bottom Label
        axes[-1].set_xlabel("Time (s)")

        plt.tight_layout()

        # Issue 2 fix: always save with a solid white background.
        # ``transparent=False`` + ``facecolor='white'`` ensures that macOS Dark Mode
        # and any other OS theme cannot composite a dark canvas colour through the
        # transparent alpha channel of PNG files opened in Preview / Finder / browsers.
        fig.savefig(
            filename,
            format=fmt,
            dpi=_RASTER_DPI,
            facecolor="white",
            transparent=False,
        )
        plt.close(fig)
        log.info(f"Exported vector plot to {filename} (hybrid rendering, dpi={_RASTER_DPI})")
        return True
