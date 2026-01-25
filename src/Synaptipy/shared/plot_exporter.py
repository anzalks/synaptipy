# src/Synaptipy/shared/plot_exporter.py
# -*- coding: utf-8 -*-
"""
Plot Exporter Utility.
Handles export of plots to various formats (SVG, PDF, PNG, JPG) using
Matplotlib (for vector quality) or PyQtGraph (for raster WYSIWYG).
"""
import logging
from typing import Dict, Any

import pyqtgraph as pg
import pyqtgraph.exporters

from Synaptipy.core.data_model import Recording
from Synaptipy.shared.plot_customization import (
    get_average_pen, get_single_trial_pen, get_force_opaque_trials
)

log = logging.getLogger(__name__)


class PlotExporter:
    """
    Handles logic for exporting plots from the ExplorerTab (or similar).
    """

    def __init__(self,
                 recording: Recording,
                 plot_canvas_widget: Any,
                 plot_canvas_wrapper: Any,
                 config: Dict[str, Any]):
        """
        Args:
            recording: Current Recording object.
            plot_canvas_widget: The actual pg.GraphicsLayoutWidget (raster).
            plot_canvas_wrapper: The wrapper (ExplorerPlotCanvas) for get_plot().
            config: Configuration dict containing:
                - plot_mode: int (CYCLE_SINGLE or OVERLAY_AVG)
                - current_trial_index: int
                - selected_trial_indices: Set[int]
        """
        self.recording = recording
        self.widget = plot_canvas_widget
        self.wrapper = plot_canvas_wrapper
        self.config = config

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
        """Save raster images using pyqtgraph (WYSIWYG)."""
        # Use the central layout item (.ci) if avail, else the widget itself
        target_item = getattr(self.widget, 'ci', self.widget)

        exporter = pg.exporters.ImageExporter(target_item)

        # Scale for DPI (Screen DPI is usually ~96)
        scale_factor = dpi / 96.0
        exporter.parameters()['width'] = int(target_item.width() * scale_factor)

        exporter.export(filename)
        log.info(f"Exported raster plot to {filename}")
        return True

    def _save_via_matplotlib(self, filename: str, fmt: str, dpi: int) -> bool:
        """
        Save vector plots using Matplotlib for publication quality.
        Extracts data directly from pyqtgraph PlotDataItems to match screen.
        """
        import matplotlib.pyplot as plt

        # 1. Setup Figure - Get visible channels from wrapper
        visible_channels = []
        for cid in self.recording.channels.keys():
            plot_item = self.wrapper.get_plot(cid)
            if plot_item and plot_item.isVisible():
                visible_channels.append(cid)

        if not visible_channels:
            log.warning("No visible channels to export.")
            return False

        n_plots = len(visible_channels)
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

        fig, axes = plt.subplots(
            n_plots, 1, sharex=True, figsize=(fig_width, fig_height), dpi=dpi
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

        # 2. Iterate and extract data DIRECTLY from pyqtgraph PlotDataItems
        for i, cid in enumerate(visible_channels):
            ax = axes[i]
            channel = self.recording.channels[cid]
            plot_item = self.wrapper.get_plot(cid)

            if not plot_item:
                continue

            # Get current view range to match screen
            vb = plot_item.getViewBox()
            x_range = vb.viewRange()[0]
            y_range = vb.viewRange()[1]

            # Extract all PlotDataItems from this plot
            # This captures exactly what's displayed, including preprocessed data
            plotted_items = []

            # Method 1: Use listDataItems() if available
            if hasattr(plot_item, 'listDataItems'):
                plotted_items = plot_item.listDataItems()
            else:
                # Fallback: iterate items and filter PlotDataItems
                for item in plot_item.items:
                    if isinstance(item, pg.PlotDataItem):
                        plotted_items.append(item)

            if not plotted_items:
                log.warning(f"No plot data items found for channel {cid}")
                continue

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

                    if is_average:
                        # Average line: thicker, on top
                        exp_alpha = max(avg_alpha, 0.8)
                        ax.plot(
                            x_data, y_data, color=avg_color,
                            alpha=exp_alpha, linewidth=1.5, zorder=10
                        )
                    else:
                        # Trial line: thinner
                        exp_alpha = max(trial_alpha, 0.5)
                        ax.plot(
                            x_data, y_data, color=trial_color,
                            alpha=exp_alpha, linewidth=0.8
                        )

                except Exception as e:
                    log.warning(f"Failed to extract data from plot item: {e}")
                    continue

            # Styling Axes
            ax.set_xlim(x_range)
            ax.set_ylim(y_range)
            ax.set_ylabel(f"{channel.get_primary_data_label()} ({channel.units})")

            # Remove top/right spines
            ax.spines['right'].set_visible(False)
            ax.spines['top'].set_visible(False)
            ax.grid(True, alpha=0.3)

        # Bottom Label
        axes[-1].set_xlabel("Time (s)")

        plt.tight_layout()
        fig.savefig(filename, format=fmt, dpi=dpi)
        plt.close(fig)
        log.info(f"Exported vector plot to {filename}")
        return True
