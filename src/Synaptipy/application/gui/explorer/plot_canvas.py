# src/Synaptipy/application/gui/explorer/plot_canvas.py
# -*- coding: utf-8 -*-
"""
Explorer Plot Canvas widget.
Handles the pyqtgraph GraphicsLayoutWidget and plot item management.
"""
import logging
from typing import Dict, List
import pyqtgraph as pg

from Synaptipy.application.gui.widgets.plot_canvas import SynaptipyPlotCanvas
from Synaptipy.core.data_model import Recording

log = logging.getLogger(__name__)


class ExplorerPlotCanvas(SynaptipyPlotCanvas):
    """
    Manages the plotting area (GraphicsLayoutWidget) and plot items.
    Inherits from SynaptipyPlotCanvas for unified infrastructure.
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        # State unique to Explorer
        # channel_plots will alias to self.plot_items for backward compatibility
        self.plot_widgets: List[pg.PlotItem] = []  # Ordered list
        self.channel_plot_data_items: Dict[str, List[pg.PlotDataItem]] = {}
        self.selected_average_plot_items: Dict[str, pg.PlotDataItem] = {}

        # Constants
        self.Y_AXIS_FIXED_WIDTH = 65

    @property
    def channel_plots(self) -> Dict[str, pg.PlotItem]:
        """Alias for plot_items to maintain compatibility with ExplorerTab."""
        return self.plot_items

    def clear_plot_items(self, chan_id: str):
        """Robustly clear all data items from a channel plot."""
        plot = self.get_plot(chan_id)
        if not plot:
            return

        # 1. Clear items tracked in our lists
        if chan_id in self.channel_plot_data_items:
            for item in self.channel_plot_data_items[chan_id]:
                try:
                    plot.removeItem(item)
                except Exception as e:
                    log.debug(f"Could not remove plot item for channel {chan_id}: {e}")
            self.channel_plot_data_items[chan_id].clear()

        # 2. Use base class clear mechanism for robustness
        self.clear_items(chan_id)

    def clear(self):
        """Clear all plots."""
        super().clear_plots()
        self.plot_widgets.clear()
        self.channel_plot_data_items.clear()
        self.selected_average_plot_items.clear()

    def rebuild_plots(self, recording: Recording) -> List[str]:  # noqa: C901
        """
        Rebuilds the plot layout based on the recording channels.
        Returns the list of channel keys in order.
        """
        # Drain stale Qt events before and after clear() (Win/Linux only).
        # clear_plots() calls widget.clear() first so Qt's destructor chain
        # auto-disconnects signals while C++ objects are still valid.
        self._cancel_pending_qt_events()
        self.clear()
        self._flush_qt_registry()

        if not recording or not recording.channels:
            return []

        channel_keys = list(recording.channels.keys())
        first_plot_item = None

        self.widget.ci.setSpacing(10)

        for i, chan_key in enumerate(channel_keys):
            channel = recording.channels[chan_key]

            # Create plot item using base class method
            # Row i, Col 0
            plot_item = self.add_plot(chan_key, row=i, col=0)
            self.plot_widgets.append(plot_item)

            # X-Link
            if first_plot_item is None:
                first_plot_item = plot_item
            else:
                plot_item.setXLink(first_plot_item)

            # Custom Styling for Explorer
            try:
                vb = plot_item.getViewBox()
                if vb:
                    # Tag viewbox with ID for signal handling (legacy need?)
                    # Base class already connects signals using chan_key,
                    # but ExplorerTab might check this attribute manually?
                    # Let's keep it to be safe.
                    vb._synaptipy_chan_id = chan_key
            except Exception as e:
                log.warning(f"Error styling ViewBox: {e}")

            # Labels
            plot_item.setLabel("left", text=channel.get_primary_data_label(), units=channel.units)
            plot_item.getAxis("left").setWidth(self.Y_AXIS_FIXED_WIDTH)

            # Bottom Axis
            if i == len(channel_keys) - 1:
                plot_item.setLabel("bottom", "Time", units="s")
            else:
                plot_item.getAxis("bottom").showLabel(False)

        return channel_keys
