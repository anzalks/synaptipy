# src/Synaptipy/application/gui/widgets/plot_canvas.py
# -*- coding: utf-8 -*-
"""
Unified Plot Canvas Base Class.
Wraps PyQtGraph's GraphicsLayoutWidget with standard Synaptipy configuration.
"""
import logging
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
            # Execute any pending deferred callbacks (ViewBox geometry /
            # layout recalculations) queued by previous clear() or widget
            # construction before entering PlotItem.__init__.  On Windows +
            # PySide6 >= 6.9 those callbacks dereference C++ pointers inside
            # __init__ causing an access violation when they fire there instead
            # of being processed first.  processEvents() *executes* them (safe
            # on Win/Linux) whereas removePostedEvents() would discard them.
            #
            # macOS is excluded: _unlink_all_plots() + _close_all_plots()
            # disconnect all signals before widget.clear(), so no stale
            # callbacks are queued by the time add_plot() is called.
            # Calling processEvents() on macOS can execute post-widget.clear()
            # callbacks that reference freed C++ ViewBox objects → SIGSEGV.
            if sys.platform != 'darwin':
                try:
                    QtCore.QCoreApplication.processEvents()
                except Exception:
                    pass

        # Add to layout
        plot_item = self.widget.addPlot(row=row, col=col, **kwargs)

        # Windows fix: pyqtgraph bug #3195 — after widget.clear() + re-addPlot(),
        # the internal QGraphicsGridLayout (widget.ci.layout) leaves each row at its
        # near-zero sizeHint height on Windows (DWM skips the implicit re-layout pass
        # that macOS/Linux Qt compositors perform).  Setting explicit stretch factors
        # on the internal graphics layout — completely separate from the outer Qt
        # widget SizePolicy — forces equal space distribution across all rows/cols.
        try:
            internal_layout = self.widget.ci.layout
            actual_row = row if row is not None else (internal_layout.rowCount() - 1)
            actual_col = col if col is not None else 0
            internal_layout.setRowStretchFactor(actual_row, 1)
            internal_layout.setColumnStretchFactor(actual_col, 1)
            
            def _deferred_invalidate():
                try:
                    internal_layout.invalidate()
                    internal_layout.activate()
                except Exception:
                    pass
            QtCore.QTimer.singleShot(0, _deferred_invalidate)
        except Exception:
            pass  # Non-fatal; fall back to default layout behaviour

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

    # Exact (ctrl_widget_attr, signal_name, plotitem_slot_name) triples
    # from PlotItem.__init__ (pyqtgraph 0.13.x lines 119, 213-239).
    # Used by _disconnect_ctrl_signals() to break the C++ signal-table ->
    # Python bound-method -> PlotItem reference cycles without warnings.
    _CTRL_CONNECTIONS = (
        ('alphaGroup', 'toggled', 'updateAlpha'),
        ('alphaSlider', 'valueChanged', 'updateAlpha'),
        ('autoAlphaCheck', 'toggled', 'updateAlpha'),
        ('xGridCheck', 'toggled', 'updateGrid'),
        ('yGridCheck', 'toggled', 'updateGrid'),
        ('gridAlphaSlider', 'valueChanged', 'updateGrid'),
        ('fftCheck', 'toggled', 'updateSpectrumMode'),
        ('logXCheck', 'toggled', 'updateLogMode'),
        ('logYCheck', 'toggled', 'updateLogMode'),
        ('derivativeCheck', 'toggled', 'updateDerivativeMode'),
        ('phasemapCheck', 'toggled', 'updatePhasemapMode'),
        ('downsampleSpin', 'valueChanged', 'updateDownsampling'),
        ('downsampleCheck', 'toggled', 'updateDownsampling'),
        ('autoDownsampleCheck', 'toggled', 'updateDownsampling'),
        ('subsampleRadio', 'toggled', 'updateDownsampling'),
        ('meanRadio', 'toggled', 'updateDownsampling'),
        ('clipToViewCheck', 'toggled', 'updateDownsampling'),
        ('avgParamList', 'itemClicked', 'avgParamListClicked'),
        ('averageGroup', 'toggled', 'avgToggled'),
        ('maxTracesCheck', 'toggled', '_handle_max_traces_toggle'),
        ('forgetTracesCheck', 'toggled', 'updateDecimation'),
        ('maxTracesSpin', 'valueChanged', 'updateDecimation'),
    )

    @staticmethod
    def _disconnect_ctrl_signals(plot_item):
        """Disconnect PlotItem ctrl-widget signals to break reference cycles.

        Each entry in _CTRL_CONNECTIONS is (widget_attr, signal_name,
        slot_method_name).  We call signal.disconnect(slot) with the specific
        bound method rather than signal.disconnect() (no args) so that Qt
        does NOT emit a qWarning when the connection does not exist — the
        specific-slot form raises RuntimeError silently instead.
        """
        ctrl = getattr(plot_item, 'ctrl', None)
        if ctrl is None:
            return
        for widget_attr, sig_name, method_name in \
                SynaptipyPlotCanvas._CTRL_CONNECTIONS:
            widget = getattr(ctrl, widget_attr, None)
            if widget is None:
                continue
            sig = getattr(widget, sig_name, None)
            slot = getattr(plot_item, method_name, None)
            if sig is not None and slot is not None:
                try:
                    sig.disconnect(slot)
                except (RuntimeError, TypeError):
                    pass
        # autoBtn.clicked → autoBtnClicked (line 119 of PlotItem.__init__)
        try:
            btn = getattr(plot_item, 'autoBtn', None)
            if btn is not None:
                btn.clicked.disconnect(plot_item.autoBtnClicked)
        except (RuntimeError, TypeError, AttributeError):
            pass

    def _close_all_plots(self):
        """Disconnect ctrl signals and call PlotItem.close() for every plot.

        Must be called while items still have a valid scene() because
        PlotItem.close() internally calls scene().removeItem(self.vb).
        """
        for plot_item in list(self.plot_items.values()):
            try:
                self._disconnect_ctrl_signals(plot_item)
                plot_item.close()
            except Exception:
                pass

    def _cancel_pending_qt_events(self):
        """Execute (not discard) stale posted events BEFORE C++ teardown (Win/Linux).

        pyqtgraph queues geometry/range-update callbacks in ViewBox deferred
        events.  On PySide6 ≥ 6.9 (Windows), these fire DURING subsequent
        Qt signal-connection calls (e.g. inside PlotItem.__init__ at the
        ctrl-widget connect() calls) if they are still pending when the next
        widget.addPlot() runs.  Simply discarding them with removePostedEvents()
        does NOT prevent the crash on 6.10.x because PySide6 internally
        re-queues some callbacks during the connect() sequence itself.

        Executing them with processEvents() while ALL current C++ objects are
        still alive (before widget.clear()) is the only reliable fix.  At this
        point _unlink_all_plots() + _close_all_plots() have NOT yet run, so
        all signals are still connected, and executing the callbacks against
        live objects is safe.

        macOS is excluded: see _flush_qt_registry() for the macOS drain path.
        _unlink_all_plots() on macOS prevents new callbacks from queuing during
        widget.clear(), so no pre-clear drain is needed.
        """
        if sys.platform == 'darwin':
            return
        try:
            QtCore.QCoreApplication.processEvents()
        except Exception:
            pass

    def _flush_qt_registry(self):
        """Drain events posted BY widget.clear().

        On Win/Linux: discards with removePostedEvents().  The processEvents()
        guard in add_plot() executes any stragglers in a controlled window
        before PlotItem.__init__ runs.

        On macOS: executes with processEvents().  At this point
        _unlink_all_plots() + _close_all_plots() have already disconnected all
        signals so widget.clear() cannot have queued any new callbacks that
        reference freed C++ objects.  Executing the queued events now keeps
        pyqtgraph's AllViews / geometry caches consistent across repeated
        rebuild loops, preventing cumulative segfaults.  (On macOS
        removePostedEvents is a no-op per _remove_posted_events() guard --
        this is the only safe drain path there.)
        """
        if sys.platform == 'darwin':
            try:
                QtCore.QCoreApplication.processEvents()
            except Exception:
                pass
        else:
            self._remove_posted_events()

    def clear_plots(self):
        """Remove all plots from the layout."""
        # Step 1: Break axis links between plots.
        # Prevents sigXRangeChanged/sigResized cascade through partially-
        # destroyed C++ ViewBox objects during widget.clear() on macOS.
        self._unlink_all_plots()
        # Step 2: Disconnect ctrl widget signals and call PlotItem.close().
        # Breaks the C++ signal-table → Python bound-method → PlotItem
        # reference cycles so Python refcounting can collect freed objects
        # without needing gc.collect() (which is unsafe on macOS PySide6 >= 6.7).
        # Must be called BEFORE widget.clear() because PlotItem.close()
        # internally calls scene().removeItem(self.vb).
        self._close_all_plots()
        # Step 3: Discard stale deferred events before teardown (Win/Linux).
        self._cancel_pending_qt_events()
        # Step 4: Destroy C++ layout children FIRST via Qt's scene graph.
        # Python wrappers in self.plot_items remain valid throughout so
        # PySide6 can cleanly resolve any C++ → Python back-references.
        # Calling plot_items.clear() BEFORE widget.clear() drops Python refs
        # while C++ objects are still live -- on macOS PySide6 ≥ 6.7 this
        # causes a segfault when the destructor tries to reach the Python side.
        self.widget.clear()
        # Step 5: Drop Python references after C++ teardown is complete.
        self.plot_items.clear()
        self._main_plot_id = None
        # Step 6: Discard any events posted BY widget.clear() (Win/Linux).
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
