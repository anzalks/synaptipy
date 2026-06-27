# src/synaptipy/application/gui/explorer/plot_canvas.py
# -*- coding: utf-8 -*-
"""
Explorer Plot Canvas widget.
Handles the pyqtgraph GraphicsLayoutWidget and plot item management.
"""

import logging
import sys
from typing import Callable, Dict, List, Optional

import pyqtgraph as pg
from PySide6 import QtCore, QtWidgets

from synaptipy.application.gui.widgets.plot_canvas import SynaptipyPlotCanvas
from synaptipy.core.data_model import Recording
from synaptipy.shared.cursor_manager import CursorToolManager
from synaptipy.shared.plot_factory import SynaptipyPlotFactory

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
        self.plot_widgets: List[pg.PlotItem] = []  # Ordered PlotItems (stack order)
        self.channel_plot_data_items: Dict[str, List[pg.PlotDataItem]] = {}
        self.selected_average_plot_items: Dict[str, pg.PlotDataItem] = {}
        # Maps channel key -> row index in the GraphicsLayoutWidget grid.
        # Updated when the stacked layout is rebuilt after visibility toggles.
        self._channel_row: Dict[str, int] = {}
        # Authoritative visibility preference from ExplorerTab / config panel
        # (do not rely on PlotItem.isVisible() alone — graphics items can lag).
        self._channel_visible_pref: Dict[str, bool] = {}

        # Cursor manager (created/replaced whenever the widget is rebuilt)
        self.cursor_manager: Optional[CursorToolManager] = None

        # Extra sigXRangeChanged slots so Y auto-range follows the visible X window.
        self._explorer_y_autoscale_slots: Dict[str, Callable[..., None]] = {}

        # Constants
        self.Y_AXIS_FIXED_WIDTH = 65

    @staticmethod
    def apply_explorer_y_follow_visible_x(vb: pg.ViewBox) -> None:
        """Let Y track data visible at the current X span (per-channel; X stays manual/linked)."""
        vb.enableAutoRange(x=False, y=True)
        vb.setAutoVisible(y=True)

    def _teardown_explorer_y_autoscale_handlers(self) -> None:
        for cid, slot in list(self._explorer_y_autoscale_slots.items()):
            plot = self.plot_items.get(cid)
            if plot is None:
                continue
            vb = plot.getViewBox()
            if vb is None:
                continue
            try:
                vb.sigXRangeChanged.disconnect(slot)
            except (TypeError, RuntimeError):
                pass
        self._explorer_y_autoscale_slots.clear()

    def _install_explorer_y_autoscale_handlers(self) -> None:
        self._teardown_explorer_y_autoscale_handlers()
        for cid in self._ordered_channel_ids():
            plot = self.plot_items.get(cid)
            if plot is None:
                continue
            vb = plot.getViewBox()
            if vb is None:
                continue

            def _slot(v_emit: pg.ViewBox, xr: object, chan: str = cid) -> None:
                self._on_explorer_viewbox_x_changed_refresh_y(chan, v_emit, xr)

            vb.sigXRangeChanged.connect(_slot)
            self._explorer_y_autoscale_slots[cid] = _slot

    def _on_explorer_viewbox_x_changed_refresh_y(self, chan_id: str, vb: pg.ViewBox, _xr: object) -> None:
        if not self._channel_visible_pref.get(chan_id, True):
            return
        plot = self.plot_items.get(chan_id)
        if plot is None or not plot.isVisible():
            return
        try:
            self.apply_explorer_y_follow_visible_x(vb)
            vb.updateAutoRange()
        except Exception as exc:
            log.debug("Explorer Y autoscale on X change failed (%s): %s", chan_id, exc)

    def _refresh_explorer_visible_y_after_layout(self, visible_plots: List[pg.PlotItem]) -> None:
        for pl in visible_plots:
            vb = pl.getViewBox()
            if vb is None:
                continue
            self.apply_explorer_y_follow_visible_x(vb)
            try:
                vb.updateAutoRange()
            except Exception as exc:
                log.debug("Explorer Y refresh after layout rebuild: %s", exc)

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
        self._channel_visible_pref.clear()

    def _ordered_channel_ids(self) -> List[str]:
        """Channel ids parallel to ``plot_widgets`` (same stacking order)."""
        plot_to_id = {plot: pid for pid, plot in self.plot_items.items()}
        return [plot_to_id[p] for p in self.plot_widgets if p in plot_to_id]

    def set_channel_visible(self, chan_id: str, visible: bool) -> None:
        """Show or hide a channel plot and rebuild the stacked layout.

        Collapsing rows via ``setRowMaximumHeight`` alone can shrink or corrupt
        the multi-row ``GraphicsLayout`` on Windows when channels are toggled.
        After updating visibility, we perform a hard reset: clear the layout,
        re-add only visible plot rows in channel order, restore X-links,
        refresh stretch factors, and run ``enableAutoRange`` + ``autoRange``
        so stacked views recover sane scaling before the next draw pass.

        Args:
            chan_id: Channel identifier matching a key in ``channel_plots``.
            visible: ``True`` to show; ``False`` to hide.
        """
        plot = self.plot_items.get(chan_id)
        if plot is None:
            return
        self._channel_visible_pref[chan_id] = visible
        if visible:
            plot.show()
        else:
            plot.hide()
        self._rebuild_visible_channels_grid()

    def _detach_stacked_plots_from_grid(self, ci: pg.GraphicsLayout, stack_order: List[str]) -> None:
        """Remove every stacked PlotItem from *ci* (prefer over ``GraphicsLayout.clear()``).

        ``clear()`` can abort halfway through disconnecting border helpers and leave
        the layout mapping stale; ``removeItem`` per plot matches pyqtgraph's path
        but stays tolerant via ``ValueError``.
        """
        plots_ordered = [self.plot_items[cid] for cid in stack_order if self.plot_items.get(cid)]
        for pl in plots_ordered:
            try:
                ci.removeItem(pl)
            except ValueError:
                pass
            except Exception as e:
                log.debug("GraphicsLayout removeItem failed: %s", e)

    def _reset_graphics_layout_counters(self, ci: pg.GraphicsLayout) -> None:
        try:
            ci.currentRow = 0
            ci.currentCol = 0
        except Exception:
            pass

    def _stack_pref_visible_channels_into_grid(
        self,
        ci: pg.GraphicsLayout,
        stack_order: List[str],
    ) -> tuple[int, List[pg.PlotItem]]:
        """Place plots preferred visible back onto *ci*; returns ``(row_count, visible_stack)``."""
        row = 0
        visible_plots: List[pg.PlotItem] = []
        for chan_key in stack_order:
            pl = self.plot_items.get(chan_key)
            if pl is None:
                continue
            if self._channel_visible_pref.get(chan_key, True):
                try:
                    ci.addItem(pl, row, 0)
                except Exception as e:
                    log.warning("Could not re-add plot for channel %s: %s", chan_key, e)
                    continue
                pl.show()
                self._channel_row[chan_key] = row
                visible_plots.append(pl)
                row += 1
            else:
                self._channel_row[chan_key] = None
        return row, visible_plots

    @staticmethod
    def _xlink_visible_stack(visible_plots: List[pg.PlotItem]) -> None:
        if len(visible_plots) < 2:
            return
        master = visible_plots[0]
        for pl in visible_plots[1:]:
            pl.setXLink(master)

    @staticmethod
    def _sync_bottom_time_axis_labels(visible_plots: List[pg.PlotItem]) -> None:
        for i, pl in enumerate(visible_plots):
            if i == len(visible_plots) - 1:
                pl.setLabel("bottom", "Time", units="s")
            else:
                pl.getAxis("bottom").showLabel(False)

    def _stretch_multichannel_grid_rows(self, row_count: int) -> None:
        try:
            internal_layout = self.widget.ci.layout
            for row_idx in range(row_count):
                internal_layout.setRowStretchFactor(row_idx, 1)
            internal_layout.setColumnStretchFactor(0, 1)
            internal_layout.invalidate()
            if sys.platform == "win32":
                internal_layout.activate()
        except Exception as e:
            log.debug("Could not refresh grid stretch factors: %s", e)

    def _rebuild_visible_channels_grid(self) -> None:
        """Detach stacked PlotItems, then re-insert only those marked visible in prefs."""
        if self.widget is None:
            return
        ci = self.widget.ci
        self._teardown_explorer_y_autoscale_handlers()
        self._unlink_all_plots()
        stack_order = self._ordered_channel_ids()
        self._detach_stacked_plots_from_grid(ci, stack_order)
        self._reset_graphics_layout_counters(ci)
        try:
            ci.setSpacing(10)
        except Exception:
            pass
        row_count, visible_plots = self._stack_pref_visible_channels_into_grid(ci, stack_order)
        self._xlink_visible_stack(visible_plots)
        self._sync_bottom_time_axis_labels(visible_plots)
        self._stretch_multichannel_grid_rows(row_count)
        self._refresh_explorer_visible_y_after_layout(visible_plots)
        self._install_explorer_y_autoscale_handlers()

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
        # through the canvas's x_range_changed -> _on_vb_x_range_changed and
        # corrupt the slider/scrollbar values for the NEW recording.  This is
        # the root cause of the "X-axis shifted right" bug when cycling files.
        #
        # Also disconnect sigStateChanged so that PlotItem.close() (below) can
        # safely set autoBtn=None without a pending viewStateChanged callback
        # later trying to call autoBtn.hide() on a None object -> AttributeError.
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
                    try:
                        vb.sigStateChanged.disconnect()
                    except (TypeError, RuntimeError):
                        pass
            except Exception:
                pass

        # macOS: remove all ViewBoxes from the old widget's scene before calling
        # old_widget.hide() / setParent(None).  On macOS + PySide6 6.7.x, those
        # operations trigger Qt geometry recalculations that queue deferred
        # ViewBox range callbacks (QTimer.singleShot(0, ...)).  If the ViewBoxes
        # are already removed from the scene they cannot generate new callbacks.
        #
        # _close_all_plots() disconnects ctrl signals and calls PlotItem.close()
        # which calls scene().removeItem(vb) and sets vb=None + autoBtn=None.
        # sigStateChanged was disconnected above so the autoBtn=None path is safe.
        #
        # After _close_all_plots(), processEvents() drains any callbacks queued
        # by PlotItem.close() itself while the C++ objects are still alive.
        # This is safe because sigStateChanged is already disconnected.
        #
        # Win/Linux are excluded: add_plot()'s processEvents guard handles it.
        if sys.platform == "darwin":
            self._close_all_plots()
            try:
                QtCore.QCoreApplication.processEvents()
            except Exception:
                pass

        self._explorer_y_autoscale_slots.clear()

        # Drop Python refs to old plot items BEFORE deleting old widget
        self.plot_items.clear()
        self._main_plot_id = None
        self.plot_widgets.clear()
        self.channel_plot_data_items.clear()
        self.selected_average_plot_items.clear()
        self._channel_row.clear()
        self._channel_visible_pref.clear()

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

        # Re-create cursor manager for the fresh widget so scene connections
        # always point to the live C++ object.
        self._init_cursor_manager()

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
            self._channel_row[chan_key] = i
            self._channel_visible_pref[chan_key] = True

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
                    # Y scales to data visible in the current X window; X stays under
                    # slider / pan / X-link control (_reset_view seeds explicit ranges).
                    self.apply_explorer_y_follow_visible_x(vb)
            except Exception as e:
                log.warning(f"Error styling ViewBox: {e}")

            # Labels — prefer the native channel name from the acquisition file;
            # fall back to the signal-type label only when name equals the id.
            chan_display_name = getattr(channel, "name", None)
            if not chan_display_name or chan_display_name == chan_key:
                chan_display_name = channel.get_primary_data_label()
            plot_item.setLabel("left", text=chan_display_name, units=channel.units)
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

        self._install_explorer_y_autoscale_handlers()

        return channel_keys

    # ------------------------------------------------------------------
    # Cursor tool delegation
    # ------------------------------------------------------------------

    def _init_cursor_manager(self) -> None:
        """Create (or replace) the CursorToolManager for the current widget."""
        if self.widget is None:
            return
        # Disconnect the old manager's scene connection first to avoid leaks.
        if self.cursor_manager is not None:
            try:
                self.cursor_manager.scene.sigMouseClicked.disconnect(self.cursor_manager._on_mouse_clicked)
            except (TypeError, RuntimeError):
                pass
        # Preserve enabled state across rebuilds.
        was_cursor_enabled = self.cursor_manager._cursor_mode_enabled if self.cursor_manager else False
        was_delta_enabled = self.cursor_manager._delta_mode_enabled if self.cursor_manager else False
        self.cursor_manager = CursorToolManager(widget=self.widget, scene=self.widget.scene())
        self.cursor_manager.set_cursor_enabled(was_cursor_enabled)
        self.cursor_manager.set_delta_mode_enabled(was_delta_enabled)

    def set_cursor_enabled(self, enabled: bool) -> None:
        """Enable or disable interactive cursor mode."""
        if self.cursor_manager is None:
            self._init_cursor_manager()
        if self.cursor_manager is not None:
            self.cursor_manager.set_cursor_enabled(enabled)

    def set_delta_mode_enabled(self, enabled: bool) -> None:
        """Enable or disable delta (pair) measurement mode."""
        if self.cursor_manager is None:
            self._init_cursor_manager()
        if self.cursor_manager is not None:
            self.cursor_manager.set_delta_mode_enabled(enabled)

    def undo_last_cursor(self) -> None:
        """Remove the most recently placed cursor from the plot."""
        if self.cursor_manager is not None:
            self.cursor_manager.undo()

    def clear_all_cursors(self) -> None:
        """Remove all cursors from the plot."""
        if self.cursor_manager is not None:
            self.cursor_manager.clear()
