# -*- coding: utf-8 -*-
"""
Unit and offscreen GUI tests for ``DraggableTextItem`` and draggable plot overlay badges
across ``MetadataDrivenAnalysisTab`` and ``CursorToolManager``.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np
import pyqtgraph as pg
import pytest
from PySide6 import QtCore

from synaptipy.application.gui.analysis_tabs.metadata_driven import MetadataDrivenAnalysisTab
from synaptipy.infrastructure.file_readers import NeoAdapter
from synaptipy.shared.cursor_manager import CursorToolManager
from synaptipy.shared.draggable_text_item import DraggableTextItem


def _make_drag_event(
    button: QtCore.Qt.MouseButton,
    start_scene: QtCore.QPointF,
    cur_scene: QtCore.QPointF,
    *,
    is_start: bool = False,
    is_finish: bool = False,
) -> MagicMock:
    """Build a mock PyQtGraph MouseDragEvent."""
    ev = MagicMock()
    ev.button.return_value = button
    ev.buttonDownScenePos.return_value = start_scene
    ev.scenePos.return_value = cur_scene
    ev.isStart.return_value = is_start
    ev.isFinish.return_value = is_finish
    return ev


@pytest.mark.timeout(30)
def test_draggable_text_item_drag_leader_line_visibility_and_reset(qapp, qtbot):
    """Left-dragging moves the badge in data space, shows a leader line, and double-click resets it."""
    pw = pg.PlotWidget()
    qtbot.addWidget(pw)
    pw.resize(500, 350)
    pw.setXRange(0.0, 1.0, padding=0)
    pw.setYRange(-80.0, -40.0, padding=0)
    qapp.processEvents()

    offsets = []
    badge = DraggableTextItem(
        text="tau = 303.52 ms",
        anchor=(0, 1),
        color=(255, 255, 255),
        fill=(0, 0, 0, 175),
        on_offset_changed=lambda dx, dy: offsets.append((dx, dy)),
    )
    assert isinstance(badge, pg.TextItem)
    assert badge.textItem.acceptedMouseButtons() == QtCore.Qt.MouseButton.NoButton

    plot_item = pw.getPlotItem()
    badge.bind_leader(plot_item, (0.20, -72.0))
    badge.set_default_pos(0.25, -70.0, leader_target=(0.20, -72.0))
    plot_item.addItem(badge)
    qapp.processEvents()

    # Before dragging, no leader curve is added or visible
    assert not badge.user_moved
    assert badge._leader_line is None

    # Hover highlight and exit restore
    hover_enter = MagicMock()
    hover_enter.isExit.return_value = False
    badge.hoverEvent(hover_enter)
    assert badge.border == badge._hover_border

    hover_exit = MagicMock()
    hover_exit.isExit.return_value = True
    badge.hoverEvent(hover_exit)
    assert badge.border == badge._base_border

    # Right-button drag is ignored so rectangle-zoom still works
    right_ev = _make_drag_event(
        QtCore.Qt.MouseButton.RightButton,
        QtCore.QPointF(100.0, 100.0),
        QtCore.QPointF(150.0, 80.0),
        is_start=True,
    )
    badge.mouseDragEvent(right_ev)
    right_ev.ignore.assert_called_once()
    assert not badge.user_moved

    # Left-button drag moves badge accurately in ViewBox data coordinates
    vb = plot_item.getViewBox()
    s0 = vb.mapViewToScene(QtCore.QPointF(0.25, -70.0))
    s1 = vb.mapViewToScene(QtCore.QPointF(0.45, -55.0))

    badge.mouseDragEvent(_make_drag_event(QtCore.Qt.MouseButton.LeftButton, s0, s0, is_start=True))
    assert badge.cursor().shape() == QtCore.Qt.CursorShape.ClosedHandCursor

    badge.mouseDragEvent(_make_drag_event(QtCore.Qt.MouseButton.LeftButton, s0, s1, is_finish=True))
    assert badge.cursor().shape() == QtCore.Qt.CursorShape.OpenHandCursor
    assert badge.user_moved is True
    assert badge.pos().x() == pytest.approx(0.45, abs=1e-3)
    assert badge.pos().y() == pytest.approx(-55.0, abs=1e-2)
    assert offsets[-1][0] == pytest.approx(0.20, abs=1e-3)
    assert offsets[-1][1] == pytest.approx(15.0, abs=1e-2)

    # Leader line is now visible and connects (0.20, -72.0) -> (0.45, -55.0)
    assert badge._leader_line is not None
    assert badge._leader_line.isVisible()
    lx, ly = badge._leader_line.getData()
    assert list(np.round(lx, 2)) == [0.20, 0.45]
    assert list(np.round(ly, 1)) == [-72.0, -55.0]

    # Hiding the badge hides its leader line; showing restores it
    badge.setVisible(False)
    assert not badge._leader_line.isVisible()
    badge.setVisible(True)
    assert badge._leader_line.isVisible()

    # Double-clicking resets position and hides the leader line
    dbl_click = MagicMock()
    dbl_click.button.return_value = QtCore.Qt.MouseButton.LeftButton
    dbl_click.double.return_value = True
    badge.mouseClickEvent(dbl_click)
    dbl_click.accept.assert_called_once()
    assert not badge.user_moved
    assert badge.pos().x() == pytest.approx(0.25, abs=1e-6)
    assert badge.pos().y() == pytest.approx(-70.0, abs=1e-6)
    assert not badge._leader_line.isVisible()
    assert offsets[-1] == (None, None)

    # Re-apply offset and verify removing badge from scene cleans up leader line automatically
    badge.apply_offset(0.15, 10.0)
    leader_ref = badge._leader_line
    assert leader_ref in plot_item.items
    plot_item.removeItem(badge)
    qapp.processEvents()
    assert leader_ref not in plot_item.items


@pytest.mark.timeout(30)
def test_tau_overlay_fit_badges_persist_user_drag_across_reruns_and_reset(qapp, qtbot):
    """Tau onset and offset badges are draggable, persist user offsets across reruns, and reset on double-click."""
    tab = MetadataDrivenAnalysisTab("tau_analysis", MagicMock(spec=NeoAdapter))
    qtbot.addWidget(tab)
    tab.resize(900, 600)
    tab.show()
    tab.plot_widget.plot([0.0, 1.0], [-80.0, -65.0])
    qapp.processEvents()

    t_on = np.linspace(0.10, 0.30, 50)
    y_on = -65.0 - 15.0 * (1.0 - np.exp(-(t_on - 0.10) / 0.020))
    t_off = np.linspace(0.60, 0.80, 50)
    y_off = -65.0 - 15.0 * np.exp(-(t_off - 0.60) / 0.025)
    result = {
        "metrics": {
            "tau_ms": 20.0,
            "tau_decay_after_stimulus_ms": 25.0,
            "_fit_time": t_on.tolist(),
            "_fit_values": y_on.tolist(),
            "_post_fit_time": t_off.tolist(),
            "_post_fit_values": y_off.tolist(),
        }
    }

    tab._plot_analysis_visualizations(result)
    badges = [item for item in tab._dynamic_plot_items if isinstance(item, DraggableTextItem)]
    assert len(badges) == 2

    onset_badge = next(b for b in badges if "20.00 ms" in b.toPlainText())
    orig_x, orig_y = float(onset_badge.pos().x()), float(onset_badge.pos().y())

    # Simulate user dragging the onset badge up by +12 mV and right by +0.08 s
    vb = tab.plot_widget.getViewBox()
    s0 = vb.mapViewToScene(QtCore.QPointF(orig_x, orig_y))
    s1 = vb.mapViewToScene(QtCore.QPointF(orig_x + 0.08, orig_y + 12.0))
    onset_badge.mouseDragEvent(_make_drag_event(QtCore.Qt.MouseButton.LeftButton, s0, s0, is_start=True))
    onset_badge.mouseDragEvent(_make_drag_event(QtCore.Qt.MouseButton.LeftButton, s0, s1, is_finish=True))

    # Re-run visualizations (simulating live parameter tweak): dragged offset must persist!
    tab._plot_analysis_visualizations(result)
    badges_after = [item for item in tab._dynamic_plot_items if isinstance(item, DraggableTextItem)]
    onset_after = next(b for b in badges_after if "20.00 ms" in b.toPlainText())
    assert onset_after.user_moved is True
    assert onset_after.pos().x() == pytest.approx(orig_x + 0.08, abs=1e-3)
    assert onset_after.pos().y() == pytest.approx(orig_y + 12.0, abs=1e-2)
    assert onset_after._leader_line is not None and onset_after._leader_line.isVisible()

    # Double-clicking resets stored offset as well
    qt_dbl = MagicMock()
    qt_dbl.button.return_value = QtCore.Qt.MouseButton.LeftButton
    onset_after.mouseDoubleClickEvent(qt_dbl)
    assert not tab._overlay_label_offsets
    assert onset_after.pos().x() == pytest.approx(orig_x, abs=1e-4)
    tab.cleanup()


@pytest.mark.timeout(30)
def test_cursor_manager_real_plot_creates_draggable_badges_and_cleans_leaders(qapp, qtbot):
    """Real PlotWidget cursors use DraggableTextItem and clean up leader curves on undo/clear."""
    pw = pg.PlotWidget()
    qtbot.addWidget(pw)
    plot_item = pw.getPlotItem()
    plot_item.plot([0.0, 0.5, 1.0], [-65.0, -75.0, -65.0])

    mgr = CursorToolManager(pw, pw.scene())
    mgr.set_cursor_enabled(True)
    mgr.add_cursor_box(0.5, -75.0, plot_item)

    entry = mgr.get_history()[0]
    text_badge = entry["items"][1]
    assert isinstance(text_badge, DraggableTextItem)
    text_badge.apply_offset(0.1, 5.0)
    leader = text_badge._leader_line
    assert leader is not None and leader in plot_item.items

    mgr.undo()
    qapp.processEvents()
    assert text_badge not in plot_item.items
    assert leader not in plot_item.items
