# src/Synaptipy/application/gui/explorer/plot_canvas.py
# -*- coding: utf-8 -*-
"""
Explorer Plot Canvas widget.
Handles the pyqtgraph GraphicsLayoutWidget and plot item management.
"""
import logging
from typing import Dict, List, Optional

import pyqtgraph as pg
from PySide6 import QtCore

from Synaptipy.shared.plot_factory import SynaptipyPlotFactory
from Synaptipy.core.data_model import Recording

log = logging.getLogger(__name__)


class ExplorerPlotCanvas(QtCore.QObject):
    """
    Manages the plotting area (GraphicsLayoutWidget) and plot items.
    """

    # Signal emitted when a ViewBox range changes: (channel_id, new_range)
    x_range_changed = QtCore.Signal(str, object)
    y_range_changed = QtCore.Signal(str, object)

    def __init__(self, parent=None):
        super().__init__(parent)

        # Create the widget using factory
        self.widget = SynaptipyPlotFactory.create_graphics_layout()
        self.widget.setBackground("white")

        # State
        self.channel_plots: Dict[str, pg.PlotItem] = {}
        self.plot_widgets: List[pg.PlotItem] = []  # Ordered list
        self.channel_plot_data_items: Dict[str, List[pg.PlotDataItem]] = {}
        self.selected_average_plot_items: Dict[str, pg.PlotDataItem] = {}
        
        # Constants
        self.Y_AXIS_FIXED_WIDTH = 65

        # Constants

    def clear_plot_items(self, chan_id: str):
        """Robustly clear all data items from a channel plot."""
        plot = self.channel_plots.get(chan_id)
        if not plot:
            return

        # 1. Clear items tracked in our lists
        if chan_id in self.channel_plot_data_items:
            for item in self.channel_plot_data_items[chan_id]:
                try:
                    plot.removeItem(item)
                except Exception:
                    pass
            self.channel_plot_data_items[chan_id].clear()

        # 2. Clear items from plot's internal list if they seem to be data items
        # Be careful not to remove grid or axes, but usually clear() does too much (removes labels/axes sometimes depending on impl)
        # Instead, we can iterate over plot.listDataItems() if available
        if hasattr(plot, "listDataItems"):
            for item in plot.listDataItems():
                try:
                    plot.removeItem(item)
                except Exception:
                    pass
        elif hasattr(plot, "items"):
            # Fallback: remove all PlotDataItem
            for item in plot.items[:]:
                if isinstance(item, pg.PlotDataItem):
                    try:
                        plot.removeItem(item)
                    except Exception:
                        pass

    def clear(self):
        """Clear all plots."""
        self.channel_plots.clear()
        self.plot_widgets.clear()
        self.channel_plot_data_items.clear()
        self.selected_average_plot_items.clear()
        self.widget.clear()

    def rebuild_plots(self, recording: Recording) -> List[str]:
        """
        Rebuilds the plot layout based on the recording channels.
        Returns the list of channel keys in order.
        """
        self.clear()

        if not recording or not recording.channels:
            return []

        channel_keys = list(recording.channels.keys())
        first_plot_item = None

        self.widget.ci.setSpacing(10)

        for i, chan_key in enumerate(channel_keys):
            channel = recording.channels[chan_key]

            # Create plot item
            plot_item = self.widget.addPlot(row=i, col=0)

            # X-Link
            if first_plot_item is None:
                first_plot_item = plot_item
            else:
                plot_item.setXLink(first_plot_item)

            # Styling
            try:
                vb = plot_item.getViewBox()
                if vb:
                    vb.setBackgroundColor("white")
                    # Tag viewbox with ID for signal handling
                    vb._synaptipy_chan_id = chan_key
            except Exception as e:
                log.warning(f"Error styling ViewBox: {e}")

            # Grid
            plot_item.showGrid(x=True, y=True, alpha=0.3)

            # Labels
            plot_item.setLabel("left", text=channel.get_primary_data_label(), units=channel.units)
            plot_item.getAxis("left").setWidth(self.Y_AXIS_FIXED_WIDTH)

            # Bottom Axis
            if i == len(channel_keys) - 1:
                plot_item.setLabel("bottom", "Time", units="s")
            else:
                plot_item.getAxis("bottom").showLabel(False)

            # Interaction
            plot_item.getViewBox().setMouseMode(pg.ViewBox.RectMode)

            # Connect Signals
            self._connect_signals(plot_item, chan_key)

            # Store
            self.channel_plots[chan_key] = plot_item
            self.plot_widgets.append(plot_item)

        return channel_keys

    def _connect_signals(self, plot_item, chan_key):
        vb = plot_item.getViewBox()
        if vb:
            vb.sigXRangeChanged.connect(lambda _, range: self.x_range_changed.emit(chan_key, range))
            vb.sigYRangeChanged.connect(lambda _, range: self.y_range_changed.emit(chan_key, range))

    def get_plot(self, chan_key: str) -> Optional[pg.PlotItem]:
        return self.channel_plots.get(chan_key)
