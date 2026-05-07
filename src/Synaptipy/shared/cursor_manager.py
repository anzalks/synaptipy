import logging
from typing import Any, Dict, List, Optional

import numpy as np
import pyqtgraph as pg
from PySide6 import QtCore, QtWidgets

log = logging.getLogger(__name__)


class CursorToolManager(QtCore.QObject):
    """
    Decoupled manager for persistent interactive cursors and delta-mode measurements
    on any pyqtgraph widget (PlotWidget or GraphicsLayoutWidget).
    """

    cursor_added = QtCore.Signal(float, float)

    def __init__(self, widget: QtWidgets.QWidget, scene: pg.GraphicsScene, parent=None):
        super().__init__(parent)
        self.widget = widget
        self.scene = scene

        self._cursor_mode_enabled = False
        self._delta_mode_enabled = False

        self._cursor_history: List[Dict[str, Any]] = []
        self._delta_anchor: Optional[Dict[str, Any]] = None
        self._delta_pair_counter = 0

        # Bind event
        self.scene.sigMouseClicked.connect(self._on_mouse_clicked)

    def set_cursor_enabled(self, enabled: bool):
        self._cursor_mode_enabled = enabled

    def set_delta_mode_enabled(self, enabled: bool):
        self._delta_mode_enabled = enabled
        if not enabled and self._delta_anchor:
            plot = self._delta_anchor.get("plot")
            if plot:
                plot.removeItem(self._delta_anchor["marker"])
                plot.removeItem(self._delta_anchor["text"])
            self._delta_anchor = None

    def _get_all_plots(self) -> List[pg.PlotItem]:
        if isinstance(self.widget, pg.PlotWidget):
            return [self.widget.getPlotItem()]

        plots = []
        for item in self.scene.items():
            if isinstance(item, pg.PlotItem):
                plots.append(item)
        return plots

    def _find_nearest_point(
        self,
        click_x: float,
        click_y: float,
        x_range: float,
        y_range: float,
        items: List,
    ):
        """Return (best_x, best_y) nearest to the click in normalised 2-D space."""
        best_x = None
        best_y = None
        min_dist = float("inf")
        for item in items:
            xData = getattr(item, "xData", None)
            yData = getattr(item, "yData", None)
            if xData is None or yData is None or len(xData) == 0 or len(xData) != len(yData):
                continue
            idx = np.argmin(np.abs(xData - click_x))
            pt_x = float(xData[idx])
            pt_y = float(yData[idx])
            norm_dist = ((pt_x - click_x) / x_range) ** 2 + ((pt_y - click_y) / y_range) ** 2
            if norm_dist < min_dist:
                min_dist = norm_dist
                best_x = pt_x
                best_y = pt_y
        return best_x, best_y

    def _resolve_clicked_plot(self, pos) -> Optional[pg.PlotItem]:
        """Return the first PlotItem whose bounding rect contains *pos*."""
        for plot in self._get_all_plots():
            if plot.getViewBox() and plot.sceneBoundingRect().contains(pos):
                return plot
        return None

    def _on_mouse_clicked(self, event):
        if not self._cursor_mode_enabled:
            return
        if event.button() != QtCore.Qt.MouseButton.LeftButton:
            return

        pos = event.scenePos()
        clicked_plot = self._resolve_clicked_plot(pos)
        if not clicked_plot:
            return

        vb = clicked_plot.getViewBox()
        if not vb:
            return

        mouse_point = vb.mapSceneToView(pos)
        click_x = mouse_point.x()
        click_y = mouse_point.y()

        view_rect = vb.viewRange()
        x_range = view_rect[0][1] - view_rect[0][0]
        y_range = view_rect[1][1] - view_rect[1][0]
        if x_range == 0 or y_range == 0:
            return

        best_x, best_y = self._find_nearest_point(click_x, click_y, x_range, y_range, clicked_plot.listDataItems())
        if best_x is None:
            return

        if self._delta_mode_enabled:
            self.handle_delta_click(best_x, best_y, clicked_plot)
        else:
            self.add_cursor_box(best_x, best_y, clicked_plot)

    def handle_delta_click(self, x_val: float, y_val: float, target_plot: pg.PlotItem):
        try:
            from Synaptipy.shared.zoom_theme import get_system_accent_color

            bg_color_str = get_system_accent_color()
            bg_color = pg.mkColor(bg_color_str)
        except ImportError:
            bg_color = pg.mkColor(0, 120, 215)

        if bg_color.alpha() == 255:
            bg_color.setAlpha(180)

        pair_id = self._delta_pair_counter + 1

        if not self._delta_anchor:
            marker = pg.ScatterPlotItem(x=[x_val], y=[y_val], size=10, pen=pg.mkPen(None), brush=pg.mkBrush(bg_color))
            target_plot.addItem(marker)

            text_item = pg.TextItem(
                text=f"[Pair {pair_id} Start] X: {x_val:.4g}\\nY: {y_val:.4g}",
                color="white",
                fill=pg.mkBrush(bg_color),
                anchor=(0.5, 1.2),
            )
            target_plot.addItem(text_item)
            text_item.setPos(x_val, y_val)

            self._delta_anchor = {"x": x_val, "y": y_val, "marker": marker, "text": text_item, "plot": target_plot}
        else:
            x1 = self._delta_anchor["x"]
            y1 = self._delta_anchor["y"]
            marker1 = self._delta_anchor["marker"]
            text1 = self._delta_anchor["text"]
            plot1 = self._delta_anchor["plot"]

            if target_plot != plot1:
                plot1.removeItem(marker1)
                plot1.removeItem(text1)
                self._delta_anchor = None
                self.handle_delta_click(x_val, y_val, target_plot)
                return

            marker2 = pg.ScatterPlotItem(x=[x_val], y=[y_val], size=10, pen=pg.mkPen(None), brush=pg.mkBrush(bg_color))
            target_plot.addItem(marker2)

            text2 = pg.TextItem(
                text=f"[Pair {pair_id} End] X: {x_val:.4g}\\nY: {y_val:.4g}",
                color="white",
                fill=pg.mkBrush(bg_color),
                anchor=(0.5, 1.2),
            )
            target_plot.addItem(text2)
            text2.setPos(x_val, y_val)

            line = pg.PlotDataItem([x1, x_val], [y1, y_val], pen=pg.mkPen(bg_color, style=QtCore.Qt.DashLine))
            target_plot.addItem(line)

            dx = x_val - x1
            dy = y_val - y1

            mid_text = pg.TextItem(
                text=f"[Pair {pair_id}]\\nΔX: {dx:.4g}\\nΔY: {dy:.4g}",
                color="white",
                fill=pg.mkBrush(bg_color),
                anchor=(0.5, 1.2),
            )
            mid_x = (x1 + x_val) / 2
            mid_y = (y1 + y_val) / 2
            target_plot.addItem(mid_text)
            mid_text.setPos(mid_x, mid_y)

            self._cursor_history.append(
                {
                    "type": "delta",
                    "items": [marker1, text1, marker2, text2, line, mid_text],
                    "plot": target_plot,
                    "data": (x1, y1, x_val, y_val, dx, dy, pair_id),
                }
            )

            self._delta_pair_counter += 1
            self._delta_anchor = None
            self.cursor_added.emit(x_val, y_val)

    def add_cursor_box(self, x_val: float, y_val: float, target_plot: pg.PlotItem):
        try:
            from Synaptipy.shared.zoom_theme import get_system_accent_color

            bg_color_str = get_system_accent_color()
            bg_color = pg.mkColor(bg_color_str)
        except ImportError:
            bg_color = pg.mkColor(0, 120, 215)

        if bg_color.alpha() == 255:
            bg_color.setAlpha(180)

        marker = pg.ScatterPlotItem(x=[x_val], y=[y_val], size=10, pen=pg.mkPen(None), brush=pg.mkBrush(bg_color))
        target_plot.addItem(marker)

        text_item = pg.TextItem(
            text=f"X: {x_val:.4g}\\nY: {y_val:.4g}", color="white", fill=pg.mkBrush(bg_color), anchor=(0.5, 1.2)
        )
        target_plot.addItem(text_item)
        text_item.setPos(x_val, y_val)

        self._cursor_history.append(
            {"type": "single", "items": [marker, text_item], "plot": target_plot, "data": (x_val, y_val)}
        )
        self.cursor_added.emit(x_val, y_val)

    def undo_last_cursor(self):
        self.undo()

    def undo(self):
        if self._delta_anchor:
            plot = self._delta_anchor.get("plot")
            if plot:
                plot.removeItem(self._delta_anchor["marker"])
                plot.removeItem(self._delta_anchor["text"])
            self._delta_anchor = None
            return

        if self._cursor_history:
            last = self._cursor_history.pop()
            plot = last.get("plot")
            if plot:
                for item in last["items"]:
                    plot.removeItem(item)
            if last["type"] == "delta":
                self._delta_pair_counter = max(0, self._delta_pair_counter - 1)

    def clear_all_cursors(self):
        self.clear()

    def clear(self):
        if self._delta_anchor:
            plot = self._delta_anchor.get("plot")
            if plot:
                plot.removeItem(self._delta_anchor["marker"])
                plot.removeItem(self._delta_anchor["text"])
            self._delta_anchor = None

        for entry in self._cursor_history:
            plot = entry.get("plot")
            if plot:
                for item in entry["items"]:
                    plot.removeItem(item)
        self._cursor_history.clear()
        self._delta_pair_counter = 0

    def get_cursor_history(self):
        """Return a copy of the cursor history list."""
        return self._cursor_history.copy()

    def get_history(self):
        """Public alias for get_cursor_history()."""
        return self.get_cursor_history()
