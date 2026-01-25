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
                 plot_canvas_wrapper: Any = None,
                 config: Dict[str, Any] = None):
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
        """Save raster images using pyqtgraph (WYSIWYG)."""
        # Use the central layout item (.ci) if avail, else the widget itself
        # Wrapper might not be present, so rely on widget
        target_item = getattr(self.widget, 'ci', self.widget)
        
        # If it's a PlotWidget, target the PlotItem
        if hasattr(self.widget, "getPlotItem"):
             target_item = self.widget.getPlotItem()

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
                # Fallback for generic widgets?
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
        for i, (label, plot_item) in enumerate(plots_to_export):
            ax = axes[i]
            
            # Get current view range to match screen
            vb = plot_item.getViewBox()
            x_range = vb.viewRange()[0]
            y_range = vb.viewRange()[1]

            # Extract all PlotDataItems from this plot
            plotted_items = []
            if hasattr(plot_item, 'listDataItems'):
                plotted_items = plot_item.listDataItems()
            else:
                for item in plot_item.items:
                    if isinstance(item, pg.PlotDataItem):
                        plotted_items.append(item)
            
            # Also check for InfiniteLine and LinearRegionItem for Analysis plots?
            # Matplotlib support for these is tricky but valuable.
            # unique to PlotExporter: we mainly focus on traces. 
            # Subclassing usage in Analysis tabs might involve markers.
            # Ideally we extract data points.
            
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
                    
                    # Check pen color to decide style if name relies on defaults
                    # Simply use the item's pen if possible?
                    # For consistency with Explorer, we use the global pens.
                    # But for Analysis tabs, the pen might be custom (e.g. orange for fits).
                    # We should probably respect the item's pen if we can extract it.
                    
                    item_pen = item.opts.get('pen')
                    if item_pen:
                        # Convert QPen to MPL
                        import PySide6.QtGui
                        if isinstance(item_pen, PySide6.QtGui.QPen):
                             c, a = pen_to_mpl(item_pen)
                             mp_color, mp_alpha = c, a
                        else:
                             # Default fallback
                             mp_color, mp_alpha = trial_color, trial_alpha
                    else:
                         mp_color, mp_alpha = trial_color, trial_alpha

                    if is_average:
                        ax.plot(x_data, y_data, color=mp_color if self.wrapper else avg_color, 
                                alpha=mp_alpha if self.wrapper else avg_alpha, linewidth=1.5, zorder=10)
                    else:
                        ax.plot(x_data, y_data, color=mp_color, alpha=mp_alpha, linewidth=0.8)

                except Exception as e:
                    log.warning(f"Failed to extract data from plot item: {e}")
                    continue

            # Styling Axes
            ax.set_xlim(x_range)
            ax.set_ylim(y_range)
            
            # Label
            if self.wrapper and hasattr(self.recording, 'channels') and label in self.recording.channels:
                 chan = self.recording.channels[label]
                 ax.set_ylabel(f"{chan.get_primary_data_label()} ({chan.units})")
            else:
                 # Try to get label from plot item?
                 ax.set_ylabel(label)

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
