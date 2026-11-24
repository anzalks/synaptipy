# -*- coding: utf-8 -*-
"""
Interactive draggable text badge for PyQtGraph plots.

Allows users to left-drag plot annotation badges (such as ``tau = ... ms``,
``Events: N``, popup fit statistics, and cursor measurement readouts) away from
underlying electrophysiological traces so waveforms remain unobstructed, with
an automatic dashed leader line pointing back to the referenced trace feature
and double-click reset to the default position.
"""

from __future__ import annotations

from typing import Any, Callable, Optional, Tuple

import pyqtgraph as pg
from PySide6 import QtCore, QtGui, QtWidgets


class DraggableTextItem(pg.TextItem):
    """A ``pyqtgraph.TextItem`` that can be repositioned by left-dragging.

    Features:
    - Left-click and drag moves the label in parent ViewBox data coordinates
      without panning the underlying plot.
    - Hovering displays an open-hand cursor and a subtle border highlight.
    - When bound to a plot and ``leader_target`` coordinate, dragging the badge
      reveals a thin dashed leader line connecting the badge to its target point
      on the trace/curve.
    - Double-clicking the badge resets it to its default position and hides the
      leader line.
    """

    def __init__(
        self,
        *args: Any,
        leader_target: Optional[Tuple[float, float]] = None,
        on_offset_changed: Optional[Callable[[Optional[float], Optional[float]], None]] = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.textItem.setAcceptedMouseButtons(QtCore.Qt.MouseButton.NoButton)
        self.textItem.setAcceptHoverEvents(False)

        self.setAcceptHoverEvents(True)
        self.setCursor(QtCore.Qt.CursorShape.OpenHandCursor)
        self.setToolTip("Drag to move label; double-click to reset position")

        self._base_border = pg.mkPen(self.border)
        self._hover_border = pg.mkPen(color=(255, 255, 255, 190), width=1.2)

        self.user_moved: bool = False
        self._default_pos: Optional[QtCore.QPointF] = None
        self._leader_plot: Optional[Any] = None
        self._leader_target: Optional[Tuple[float, float]] = (
            (float(leader_target[0]), float(leader_target[1])) if leader_target is not None else None
        )
        self._leader_line: Optional[pg.PlotCurveItem] = None
        self._drag_start_pos: Optional[QtCore.QPointF] = None
        self._drag_start_parent: Optional[QtCore.QPointF] = None
        self._drag_inv_transform: Optional[QtGui.QTransform] = None
        self.on_offset_changed = on_offset_changed

    def dataBounds(self, ax: int, frac: float = 1.0, orthoRange: Any = None) -> list:
        """Exclude draggable text badges from ViewBox auto-range calculations."""
        return [None, None]

    def bind_leader(self, plot_item: Any, leader_target: Tuple[float, float]) -> None:
        """Associate a host plot and target data coordinate ``(x, y)`` for the leader line."""
        self._leader_plot = plot_item
        self._leader_target = (float(leader_target[0]), float(leader_target[1]))
        self._sync_leader_line()

    def set_default_pos(
        self,
        x: float,
        y: float,
        leader_target: Optional[Tuple[float, float]] = None,
    ) -> None:
        """Record default ``(x, y)`` position and apply it unless already moved by the user."""
        self._default_pos = QtCore.QPointF(float(x), float(y))
        if leader_target is not None:
            self._leader_target = (float(leader_target[0]), float(leader_target[1]))
        elif self._leader_target is None:
            self._leader_target = (float(x), float(y))

        if not self.user_moved:
            self.setPos(float(x), float(y))
        self._sync_leader_line()

    def apply_offset(self, dx: float, dy: float) -> None:
        """Apply a saved ``(dx, dy)`` offset relative to ``_default_pos``."""
        if self._default_pos is None:
            cur = self.pos()
            self._default_pos = QtCore.QPointF(float(cur.x()), float(cur.y()))
        self.user_moved = True
        self.setPos(float(self._default_pos.x()) + float(dx), float(self._default_pos.y()) + float(dy))
        self._sync_leader_line()

    def reset_position(self) -> None:
        """Snap back to ``_default_pos``, clear ``user_moved``, and hide the leader line."""
        self.user_moved = False
        if self._default_pos is not None:
            self.setPos(self._default_pos)
        self._sync_leader_line()
        if callable(self.on_offset_changed):
            self.on_offset_changed(None, None)

    def _ensure_leader_line(self) -> Optional[pg.PlotCurveItem]:
        """Lazily create and attach the dashed leader curve on first user drag."""
        if self._leader_line is None and self._leader_plot is not None:
            pen = pg.mkPen(color=(90, 90, 90, 195), width=1.1, style=QtCore.Qt.PenStyle.DashLine)
            line = pg.PlotCurveItem(pen=pen)
            line._synaptipy_role = "annotation_leader"
            line.setZValue(max(0.0, float(self.zValue()) - 1.0))
            line.setVisible(False)
            try:
                self._leader_plot.addItem(line, ignoreBounds=True)
            except TypeError:
                self._leader_plot.addItem(line)
            self._leader_line = line
        return self._leader_line

    def _remove_leader_line(self) -> None:
        """Remove the leader curve from ``_leader_plot`` when this badge leaves the scene."""
        if self._leader_line is not None and self._leader_plot is not None:
            try:
                self._leader_plot.removeItem(self._leader_line)
            except Exception:
                pass
        self._leader_line = None

    def _sync_leader_line(self) -> None:
        """Update leader line endpoints or hide it when at default position."""
        if not self.user_moved or not self.isVisible() or self._leader_target is None:
            if self._leader_line is not None:
                self._leader_line.setData([], [])
                self._leader_line.setVisible(False)
            return

        line = self._ensure_leader_line()
        if line is not None:
            tx, ty = self._leader_target
            cur = self.pos()
            line.setData([tx, float(cur.x())], [ty, float(cur.y())])
            line.setVisible(True)

    def setVisible(self, visible: bool) -> None:
        """Keep leader line visibility synchronized with the text badge."""
        super().setVisible(visible)
        self._sync_leader_line()

    def itemChange(self, change: QtWidgets.QGraphicsItem.GraphicsItemChange, value: Any) -> Any:
        """Clean up any attached leader curve automatically when removed from a scene."""
        if change == QtWidgets.QGraphicsItem.GraphicsItemChange.ItemSceneChange and value is None:
            self._remove_leader_line()
        return super().itemChange(change, value)

    def hoverEvent(self, ev: Any) -> None:
        """Highlight badge border subtly while hovered."""
        self.border = self._base_border if ev.isExit() else self._hover_border
        self.update()

    def _begin_drag(self, ev: Any, parent: QtWidgets.QGraphicsItem) -> None:
        """Capture starting item position and frozen inverse scene transform."""
        if self._default_pos is None:
            p0 = self.pos()
            self._default_pos = QtCore.QPointF(float(p0.x()), float(p0.y()))
        if self._leader_target is None and self._default_pos is not None:
            self._leader_target = (float(self._default_pos.x()), float(self._default_pos.y()))
        self._drag_start_pos = QtCore.QPointF(self.pos())
        self._drag_inv_transform = pg.functions.invertQTransform(parent.sceneTransform())
        down_scene = ev.buttonDownScenePos(QtCore.Qt.MouseButton.LeftButton)
        self._drag_start_parent = self._drag_inv_transform.map(QtCore.QPointF(down_scene))
        self.setCursor(QtCore.Qt.CursorShape.ClosedHandCursor)

    def mouseDragEvent(self, ev: Any) -> None:
        """Reposition badge in ViewBox data coordinates on left-button drag."""
        if ev.button() != QtCore.Qt.MouseButton.LeftButton:
            ev.ignore()
            return

        parent = self.parentItem()
        if parent is None:
            ev.ignore()
            return

        ev.accept()
        if ev.isStart() or self._drag_inv_transform is None:
            self._begin_drag(ev, parent)

        if (
            self._drag_start_pos is not None
            and self._drag_start_parent is not None
            and self._drag_inv_transform is not None
        ):
            cur_parent = self._drag_inv_transform.map(QtCore.QPointF(ev.scenePos()))
            new_pos = self._drag_start_pos + (cur_parent - self._drag_start_parent)
            self.user_moved = True
            self.setPos(new_pos)
            self._sync_leader_line()
            if callable(self.on_offset_changed) and self._default_pos is not None:
                self.on_offset_changed(
                    float(new_pos.x() - self._default_pos.x()),
                    float(new_pos.y() - self._default_pos.y()),
                )

        if ev.isFinish():
            self._drag_inv_transform = None
            self.setCursor(QtCore.Qt.CursorShape.OpenHandCursor)

    def mouseClickEvent(self, ev: Any) -> None:
        """Reset badge to its default position on left double-click (PyQtGraph scene event)."""
        if ev.button() == QtCore.Qt.MouseButton.LeftButton and ev.double():
            ev.accept()
            self.reset_position()
            return
        ev.ignore()

    def mouseDoubleClickEvent(self, ev: Any) -> None:
        """Reset badge to its default position on standard Qt left double-click."""
        if ev.button() == QtCore.Qt.MouseButton.LeftButton:
            ev.accept()
            self.reset_position()
            return
        super().mouseDoubleClickEvent(ev)
