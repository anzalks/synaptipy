# src/synaptipy/shared/viewbox.py
# -*- coding: utf-8 -*-
"""
Custom ViewBox for synaptipy.

Reassigns mouse button actions so that:
- Left-drag  : pan the view
- Right-drag : draw a zoom rectangle (release to zoom in)
- Axis-constrained right-drag: continuous scale (wheel-zoom feel on axis ticks)

All existing signals (sigRangeChangedManually, sigXRangeChanged,
sigYRangeChanged, etc.) are preserved so scrollbar synchronisation and
zoom-lock connections continue to work without modification.
"""

import logging

import numpy as np
import pyqtgraph as pg
from pyqtgraph import functions as fn
from pyqtgraph.Point import Point
from PySide6 import QtCore

log = logging.getLogger(__name__)


class SynaptipyViewBox(pg.ViewBox):
    """ViewBox with natural mouse bindings for electrophysiology navigation.

    Left-drag  -> pan the view
    Right-drag -> draw a zoom rectangle; release to zoom in
    Axis-constrained right-drag (e.g. dragging on Y-axis ticks) ->
        continuous scale (unchanged pyqtgraph default)

    All signals emitted by the stock ViewBox are preserved so that scrollbar
    synchronisation, range locks, and zoom-sync connections continue to work.
    """

    def mouseDragEvent(self, ev, axis=None):  # noqa: C901
        """Override to remap left=pan and right=rectangle-zoom."""
        ev.accept()

        mouse_enabled = np.array(self.state["mouseEnabled"], dtype=np.float64)
        mask = mouse_enabled.copy()
        if axis is not None:
            mask[1 - axis] = 0.0

        btn = ev.button()

        if btn in (QtCore.Qt.MouseButton.LeftButton, QtCore.Qt.MouseButton.MiddleButton):
            # ------------------------------------------------------------------
            # Left / Middle drag -> pan (translate)
            # ------------------------------------------------------------------
            tr = self.childGroup.transform()
            tr = fn.invertQTransform(tr)
            dif = (ev.pos() - ev.lastPos()) * -1
            dif_mapped = tr.map(dif * mask) - tr.map(Point(0, 0))

            x = dif_mapped.x() if mask[0] == 1 else None
            y = dif_mapped.y() if mask[1] == 1 else None

            self._resetTarget()
            if x is not None or y is not None:
                self.translateBy(x=x, y=y)
            self.sigRangeChangedManually.emit(self.state["mouseEnabled"])

        elif btn & QtCore.Qt.MouseButton.RightButton:
            if axis is None:
                # --------------------------------------------------------------
                # Right drag (unconstrained) -> rectangle zoom
                # Mirrors the stock RectMode left-drag behavior, remapped here
                # to the right mouse button.
                # --------------------------------------------------------------
                down_pos = ev.buttonDownPos(QtCore.Qt.MouseButton.RightButton)
                if ev.isFinish():
                    # Finalise: hide rubber band, zoom to selected rect
                    self.rbScaleBox.hide()
                    ax = QtCore.QRectF(Point(down_pos), Point(ev.pos()))
                    ax = self.childGroup.mapRectFromParent(ax)
                    # Lock manual Y before showAxRect / sigXRangeChanged so Explorer's
                    # visible-X Y-autoscale handler preserves the 2D box zoom's Y span.
                    self._synaptipy_manual_y = True
                    self.enableAutoRange(x=False, y=False)
                    self.showAxRect(ax)  # calls setRange -> emits sigRangeChanged
                    self.axHistoryPointer += 1
                    self.axHistory = self.axHistory[: self.axHistoryPointer] + [ax]
                    # Forcefully re-emit range-change signals so that
                    # multi-channel sync handlers connected to sigXRangeChanged /
                    # sigYRangeChanged are guaranteed to fire even when
                    # pyqtgraph's floating-point threshold gate in
                    # updateViewRange would otherwise skip emission.
                    self.sigXRangeChanged.emit(self, tuple(self.state["viewRange"][0]))
                    self.sigYRangeChanged.emit(self, tuple(self.state["viewRange"][1]))
                    self.sigRangeChanged.emit(self, self.state["viewRange"], [True, True])
                else:
                    # In-progress: draw the rubber-band rectangle
                    self.updateScaleBox(down_pos, ev.pos())
            else:
                # --------------------------------------------------------------
                # Axis-constrained right-drag -> continuous scale
                # Preserves the default pyqtgraph wheel-zoom-on-axis behavior.
                # --------------------------------------------------------------
                if self.state["aspectLocked"] is not False:
                    mask[0] = 0

                dif = ev.screenPos() - ev.lastScreenPos()
                dif_arr = np.array([dif.x(), dif.y()])
                dif_arr[0] *= -1
                s = ((mask * 0.02) + 1) ** dif_arr

                tr = self.childGroup.transform()
                tr = fn.invertQTransform(tr)

                x = s[0] if mouse_enabled[0] == 1 else None
                y = s[1] if mouse_enabled[1] == 1 else None

                if axis == 1 and y is not None:
                    self._synaptipy_manual_y = True
                    self.enableAutoRange(y=False)

                center = Point(tr.map(ev.buttonDownPos(QtCore.Qt.MouseButton.RightButton)))
                self._resetTarget()
                self.scaleBy(x=x, y=y, center=center)
                self.sigRangeChangedManually.emit(self.state["mouseEnabled"])

    def wheelEvent(self, ev, axis=None):
        """Apply user Scroll Behavior preference (Natural vs Inverted) to wheel/trackpad zoom."""
        if (axis is None or axis == 1) and self.state["mouseEnabled"][1]:
            self._synaptipy_manual_y = True
            self.enableAutoRange(y=False)

        try:
            from synaptipy.shared.scroll_settings import get_scroll_multiplier

            mult = get_scroll_multiplier()
        except Exception:
            mult = 1

        if mult < 0:
            mask = np.array(self.state["mouseEnabled"], dtype=np.float64)
            if axis is not None and 0 <= axis < 2:
                mask[1 - axis] = 0.0
            s = (mask * 0.02) + 1
            s = [val ** (ev.delta() * (1.0 / 8.0) * 0.1) if m == 1.0 else None for val, m in zip(s, mask)]
            center = Point(fn.invertQTransform(self.childGroup.transform()).map(ev.pos()))
            self._resetTarget()
            self.scaleBy(x=s[0], y=s[1], center=center)
            ev.accept()
            self.sigRangeChangedManually.emit(self.state["mouseEnabled"])
            return

        super().wheelEvent(ev, axis=axis)
