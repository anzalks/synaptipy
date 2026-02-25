# src/Synaptipy/application/gui/widgets/plot_canvas.py
# -*- coding: utf-8 -*-
"""
Unified Plot Canvas Base Class.
Wraps PyQtGraph's GraphicsLayoutWidget with standard Synaptipy configuration.
"""
import logging
import gc
import os
import sys
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

        # In headless/offscreen mode (CI), ViewBoxMenu.__init__ calls
        # QWidgetAction which crashes PySide6 on Windows and macOS without a
        # real display.  PyQtGraph's own enableMenu=False flag tells ViewBox
        # to skip menu creation entirely -- no monkey-patching required.
        if os.environ.get("QT_QPA_PLATFORM") == "offscreen":
            kwargs.setdefault("enableMenu", False)

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

            # Connect range signals.
            # Use default-arg capture (pid=plot_id) so each lambda closes over
            # the correct plot_id value, not a shared late-binding reference.
            # Use 'r' not 'range' to avoid shadowing the Python builtin.
            plot_item.getViewBox().sigXRangeChanged.connect(
                lambda _, r, pid=plot_id: self.x_range_changed.emit(pid, r)
            )
            plot_item.getViewBox().sigYRangeChanged.connect(
                lambda _, r, pid=plot_id: self.y_range_changed.emit(pid, r)
            )

        # Apply consistent theme to axis colors, labels, etc.
        try:
            from Synaptipy.shared.plot_customization import apply_plot_theme
            apply_plot_theme(plot_item, background_color="white", axis_color="black")
        except ImportError:
            log.debug("plot_customization module not available for theming")

    def get_plot(self, plot_id: str) -> Optional[pg.PlotItem]:
        return self.plot_items.get(plot_id)

    @staticmethod
    def _remove_posted_events():
        """Discard all pending posted events — Win/Linux only.

        macOS is excluded: pyqtgraph on macOS queues internal layout/range
        update events that it must process to keep its internal state
        (ViewBox geometry, AllViews registry) consistent.  Discarding them
        on macOS corrupts that state and causes later widget.clear() calls
        to segfault.  On macOS, _unlink_all_plots() is the sole pre-clear
        safety measure needed.
        """
        if sys.platform == 'darwin':
            return
        try:
            from PySide6.QtCore import QCoreApplication
            QCoreApplication.removePostedEvents(None, 0)
        except Exception:
            pass

    def _unlink_all_plots(self):
        """Break all X/Y axis links between plots before C++ teardown.

        When multiple plots are X-linked (via PlotItem.setXLink / ViewBox
        linkView), pyqtgraph connects sigXRangeChanged and sigResized between
        the corresponding ViewBoxes.  During widget.clear(), Qt removes each
        PlotItem from the scene one by one.  Each removal triggers itemChange
        which can cascade range-change signals through the still-alive linked
        ViewBoxes.  On macOS PySide6 ≥ 6.7 this cascade through partially-
        destroyed C++ objects causes a segfault inside widget.clear().

        ViewBox.linkView(axis, None) disconnects only the XLink-specific
        slots (linkedXChanged, linkedYChanged, and sigResized).  It does NOT
        touch pyqtgraph's own internal connections or our signal lambdas, so
        it is safe to call on every platform immediately before clearing.
        """
        for plot_item in list(self.plot_items.values()):
            try:
                vb = plot_item.getViewBox()
                if vb is not None:
                    vb.setXLink(None)
                    vb.setYLink(None)
            except Exception:
                pass

    def _cancel_pending_qt_events(self):
        """Discard stale posted events BEFORE C++ object teardown (Win/Linux).

        Also runs gc.collect() on Win/Linux to free reference-cycle-trapped
        PySide6 wrappers from prior rebuilds.  With gc.disable() active (set
        in pytest_configure for offscreen mode), cyclic garbage accumulates
        across tests.  Zombie wrappers appear in Qt's internal connection
        tables; when the next PlotItem.__init__ connects a signal it hits
        these stale entries and crashes.  gc.collect() frees the cycles while
        all current C++ objects are still alive (safe), then removePostedEvents
        discards any DeferredDelete events the finalizers posted.

        macOS is excluded: gc.collect() races with PySide6 tp_dealloc during
        Qt's C++ destructor chain on macOS PySide6 >= 6.7 -> SIGBUS.
        The _unlink_all_plots() step handles macOS crash prevention instead.
        """
        if sys.platform == 'darwin':
            return
        gc.collect()
        self._remove_posted_events()

    def _flush_qt_registry(self):
        """Finalize zombie wrappers and discard stale events (Win/Linux).

        Called after widget.clear() + plot_items.clear().  At this point the
        C++ backing of all removed plots is already destroyed and Python refs
        in plot_items are dropped.  Any remaining cyclic-garbage wrappers
        (PlotItem / ctrl widgets etc.) are unreachable but not yet finalised
        because gc.disable() suppresses automatic collection in offscreen mode.

        gc.collect() forces finalisation of those cycles now -- before the
        next add_plot() call -- so Qt's internal signal connection table is
        clean when PlotItem.__init__ tries to connect at line 235.  This is
        safe because the wrappers being collected have no live C++ backing
        (widget.clear() already destroyed it); PySide6 tp_dealloc skips C++
        interaction when isValid() is False.

        A second removePostedEvents then discards DeferredDelete events that
        PySide6 tp_dealloc may post during the GC pass.

        macOS is excluded: gc.collect() causes a SIGBUS on macOS PySide6
        >= 6.7 regardless of C++ validity (race in PySide6's type system).
        The _unlink_all_plots() + widget.clear()-first ordering handles macOS.
        """
        if sys.platform == 'darwin':
            return
        gc.collect()
        self._remove_posted_events()

    def clear_plots(self):
        """Remove all plots from the layout."""
        # Step 1: Break axis links between plots.
        # Prevents sigXRangeChanged/sigResized cascade through partially-
        # destroyed C++ ViewBox objects during widget.clear() on macOS.
        self._unlink_all_plots()
        # Step 2: Discard stale deferred events before teardown (Win/Linux).
        # macOS skip is inside _cancel_pending_qt_events / _remove_posted_events.
        self._cancel_pending_qt_events()
        # Step 3: Destroy C++ layout children FIRST.
        # widget.clear() runs Qt's destructor chain which automatically
        # disconnects all signals on the destroyed objects.  Python wrappers
        # in self.plot_items remain valid throughout so PySide6 can cleanly
        # resolve any C++ → Python back-references during destruction.
        # Calling plot_items.clear() BEFORE widget.clear() drops Python refs
        # while C++ objects are still live -- on macOS PySide6 ≥ 6.7 this
        # causes a segfault when the destructor tries to reach the Python side.
        self.widget.clear()
        # Step 4: Drop Python references after C++ teardown is complete.
        self.plot_items.clear()
        self._main_plot_id = None
        # Step 5: Discard any events posted BY widget.clear() (Win/Linux).
        self._flush_qt_registry()

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
