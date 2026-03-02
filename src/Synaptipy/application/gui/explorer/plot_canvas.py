# src/Synaptipy/application/gui/explorer/plot_canvas.py
# -*- coding: utf-8 -*-
"""
Explorer Plot Canvas widget.
Handles the pyqtgraph GraphicsLayoutWidget and plot item management.
"""

import logging
import sys
from typing import Dict, List

import pyqtgraph as pg
from PySide6 import QtWidgets

from Synaptipy.application.gui.widgets.plot_canvas import SynaptipyPlotCanvas
from Synaptipy.core.data_model import Recording
from Synaptipy.shared.plot_factory import SynaptipyPlotFactory

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

        Instead of calling widget.clear() and reusing the same
        GraphicsLayoutWidget (which leaves the Qt scene in a broken state on
        Windows after the clear→addPlot cycle), we create a brand-new widget
        and swap it into the parent layout. This guarantees a pristine scene
        graph with no stale ViewBox callbacks or orphaned C++ pointers.

        Returns the list of channel keys in order.
        """
        # --- Replace the widget entirely ---
        old_widget = self.widget
        parent_layout = None
        layout_pos = None

        # Find the old widget's position in its parent layout
        if old_widget and old_widget.parentWidget():
            parent = old_widget.parentWidget()
            parent_layout = parent.layout()
            if parent_layout is not None:
                # Find position of old widget in the grid layout
                for i in range(parent_layout.count()):
                    item = parent_layout.itemAt(i)
                    if item and item.widget() is old_widget:
                        # For QGridLayout, get row/col/rowSpan/colSpan
                        if isinstance(parent_layout, QtWidgets.QGridLayout):
                            idx = parent_layout.indexOf(old_widget)
                            if idx >= 0:
                                row, col, rspan, cspan = parent_layout.getItemPosition(idx)
                                layout_pos = (row, col, rspan, cspan)
                        break

        # Disconnect old ViewBox signals BEFORE deleting old widget.
        # Without this, old ViewBoxes scheduled for deleteLater() can still
        # emit sigXRangeChanged / sigYRangeChanged / sigResized during the
        # event loop iteration that destroys them.  Those signals propagate
        # through the canvas's x_range_changed → _on_vb_x_range_changed and
        # corrupt the slider/scrollbar values for the NEW recording.  This is
        # the root cause of the "X-axis shifted right" bug when cycling files.
        for plot_item in self.plot_items.values():
            try:
                vb = plot_item.getViewBox()
                if vb:
                    try:
                        vb.sigXRangeChanged.disconnect()
                    except (TypeError, RuntimeError):
                        pass
                    try:
                        vb.sigYRangeChanged.disconnect()
                    except (TypeError, RuntimeError):
                        pass
                    try:
                        vb.sigResized.disconnect()
                    except (TypeError, RuntimeError):
                        pass
            except Exception:
                pass

        # Drop Python refs to old plot items BEFORE deleting old widget
        self.plot_items.clear()
        self._main_plot_id = None
        self.plot_widgets.clear()
        self.channel_plot_data_items.clear()
        self.selected_average_plot_items.clear()

        # Create a fresh GraphicsLayoutWidget
        new_widget = SynaptipyPlotFactory.create_graphics_layout(
            parent=old_widget.parentWidget() if old_widget else None
        )

        # Swap into the layout
        if parent_layout is not None and layout_pos is not None:
            parent_layout.removeWidget(old_widget)
            old_widget.hide()
            old_widget.setParent(None)
            old_widget.deleteLater()
            row, col, rspan, cspan = layout_pos
            parent_layout.addWidget(new_widget, row, col, rspan, cspan)
        elif parent_layout is not None:
            # Fallback: simple replace
            parent_layout.removeWidget(old_widget)
            old_widget.hide()
            old_widget.setParent(None)
            old_widget.deleteLater()
            parent_layout.addWidget(new_widget)
        else:
            # No parent layout — just swap the reference
            if old_widget:
                old_widget.hide()
                old_widget.deleteLater()

        self.widget = new_widget

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
                    vb._synaptipy_chan_id = chan_key
                    # Disable auto-range immediately so pyqtgraph does not
                    # queue deferred updateAutoRange callbacks when data items
                    # are added later.  The Explorer manages view ranges
                    # explicitly via _reset_view().
                    vb.disableAutoRange()
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

        # Windows fix: pyqtgraph bug #3195 — after a full rebuild issue a single
        # synchronous invalidate/activate so QGraphicsGridLayout recalculates
        # row heights immediately while all C++ objects are alive.
        # One call here replaces N per-plot deferred timers whose unpredictable
        # firing times caused races with rapid file cycling on Windows.
        # macOS and Linux compositors handle the re-layout pass implicitly.
        if sys.platform == "win32":
            try:
                internal_layout = self.widget.ci.layout
                for row_idx in range(len(channel_keys)):
                    internal_layout.setRowStretchFactor(row_idx, 1)
                internal_layout.setColumnStretchFactor(0, 1)
                internal_layout.invalidate()
                internal_layout.activate()
            except Exception:
                pass  # Non-fatal; gracefully fall back on unsupported platforms

        return channel_keys
