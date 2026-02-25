# src/Synaptipy/application/gui/widgets/plot_canvas.py
# -*- coding: utf-8 -*-
"""
Unified Plot Canvas Base Class.
Wraps PyQtGraph's GraphicsLayoutWidget with standard Synaptipy configuration.
"""
import logging
from typing import Dict, Optional
import pyqtgraph as pg
from PySide6 import QtCore

from Synaptipy.shared.plot_factory import SynaptipyPlotFactory

log = logging.getLogger(__name__)


class SynaptipyPlotCanvas(QtCore.QObject):
    """
    Base class for plot canvases in Synaptipy.
    Wraps a GraphicsLayoutWidget and manages plot items.
    """

    # Signals for range changes
    x_range_changed = QtCore.Signal(str, object)  # (plot_id, range_tuple)
    y_range_changed = QtCore.Signal(str, object)  # (plot_id, range_tuple)

    def __init__(self, parent=None):
        super().__init__(parent)

        # Create the widget using factory for Windows safety
        self.widget = SynaptipyPlotFactory.create_graphics_layout(parent)
        self.widget.setBackground("white")

        # State storage
        self.plot_items: Dict[str, pg.PlotItem] = {}
        # Provide a main plot property for simple single-plot tabs
        self._main_plot_id: Optional[str] = None

    @property
    def main_plot(self) -> Optional[pg.PlotItem]:
        """Convenience accessor for the 'main' plot (usually the first one added)."""
        if self._main_plot_id and self._main_plot_id in self.plot_items:
            return self.plot_items[self._main_plot_id]
        # Fallback to first item
        if self.plot_items:
            return next(iter(self.plot_items.values()))
        return None

    def add_plot(self, plot_id: str, row: int = None, col: int = None, **kwargs) -> pg.PlotItem:
        """
        Add a plot item to the layout.

        Args:
            plot_id: Unique identifier for the plot
            row: Row index in layout
            col: Column index in layout
            **kwargs: Arguments passed to addPlot (e.g. title)

        Returns:
            The created PlotItem
        """
        if plot_id in self.plot_items:
            log.warning(f"Plot ID '{plot_id}' already exists. Returning existing.")
            return self.plot_items[plot_id]

        # Add to layout
        plot_item = self.widget.addPlot(row=row, col=col, **kwargs)

        # Apply standard configuration
        self._configure_plot_item(plot_item, plot_id)

        # Store
        self.plot_items[plot_id] = plot_item
        if self._main_plot_id is None:
            self._main_plot_id = plot_id

        return plot_item

    def _configure_plot_item(self, plot_item: pg.PlotItem, plot_id: str):
        """Apply standard configuration to a plot item."""
        # Grid
        plot_item.showGrid(x=True, y=True, alpha=0.3)

        # White background for ViewBox
        if plot_item.getViewBox():
            plot_item.getViewBox().setBackgroundColor("white")
            plot_item.getViewBox().setMouseMode(pg.ViewBox.RectMode)

            # Connect range signals
            plot_item.getViewBox().sigXRangeChanged.connect(
                lambda _, range: self.x_range_changed.emit(plot_id, range)
            )
            plot_item.getViewBox().sigYRangeChanged.connect(
                lambda _, range: self.y_range_changed.emit(plot_id, range)
            )

        # Apply consistent theme to axis colors, labels, etc.
        try:
            from Synaptipy.shared.plot_customization import apply_plot_theme
            apply_plot_theme(plot_item, background_color="white", axis_color="black")
        except ImportError:
            log.debug("plot_customization module not available for theming")

    def get_plot(self, plot_id: str) -> Optional[pg.PlotItem]:
        return self.plot_items.get(plot_id)

    def clear_plots(self):
        """Remove all plots from the layout."""
        # Force Python's cycle GC to collect any PlotItem objects (from THIS
        # tab or any other) that have cyclic references and whose __del__
        # hasn't run yet.  Without this, Python 3.10's less-aggressive GC
        # leaves PlotItem.__del__ uncalled until a later collection pass;
        # the deferred deleteLater events for their ctrl QWidgets are not yet
        # queued, so processEvents() below can't flush them, and the next
        # add_plot() call finds stale C++ pointers in pyqtgraph's global
        # registry -> segfault.
        import gc
        gc.collect()

        self.widget.clear()
        self.plot_items.clear()
        self._main_plot_id = None

        # Flush Qt's event queue so that any deferred C++ destructor calls
        # (deleteLater) for removed PlotItem ctrl widgets complete *before* the
        # caller creates new PlotItems.  Without this, pyqtgraph's global
        # PlotItem registry retains stale C++ pointers that crash the very next
        # PlotItem.__init__ on macOS/Windows in offscreen (CI) mode.
        try:
            from PySide6.QtWidgets import QApplication
            _app = QApplication.instance()
            if _app:
                for _ in range(3):
                    _app.processEvents()
        except Exception:
            pass

    def clear_items(self, plot_id: str):
        """Clear data items from a specific plot (keeping axis/labels)."""
        plot = self.get_plot(plot_id)
        if not plot:
            return

        # Robust clearing
        for item in plot.listDataItems():
            try:
                plot.removeItem(item)
            except Exception as e:
                log.debug(f"Could not remove plot item during clearing: {e}")

        # Also remove any InfiniteLines or other items if needed?
        # Typically we just want to remove data.
        # CAUTION: plot.clear() removes everything including labels sometimes?
        # PG's plot.clear() usually removes all items.
        # Let's try to be specific if we want to keep grid/labels,
        # or just rely on re-adding them if we used plot.clear().
        # Actually plot.clear() is usually fine for PlotItem.
        plot.clear()

    def set_main_plot(self, plot_id: str):
        if plot_id in self.plot_items:
            self._main_plot_id = plot_id
