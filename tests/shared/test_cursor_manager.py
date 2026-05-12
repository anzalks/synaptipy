# -*- coding: utf-8 -*-
"""
Tests for CursorToolManager in Synaptipy.shared.cursor_manager.

Covers:
- set_cursor_enabled / set_delta_mode_enabled
- add_cursor_box (single cursor placement and history)
- handle_delta_click (delta pair numbering, cross-plot guard)
- undo() stack logic (single and delta entries)
- clear() — removes all cursors and resets counter
- get_history() / get_cursor_history() aliases
- _find_nearest_point / _get_all_plots (private methods)
"""

from unittest.mock import MagicMock, patch

import numpy as np
import pytest


@pytest.fixture
def mock_plot_item():
    """Return a lightweight mock of pg.PlotItem."""
    plot = MagicMock()
    # getViewBox() must return a view-box mock with viewRange()
    vb = MagicMock()
    vb.viewRange.return_value = [[-1.0, 1.0], [-1.0, 1.0]]
    vb.mapSceneToView.return_value = MagicMock(x=lambda: 0.5, y=lambda: 0.25)
    plot.getViewBox.return_value = vb
    plot.sceneBoundingRect.return_value = MagicMock(contains=lambda pos: True)
    plot.listDataItems.return_value = []
    return plot


@pytest.fixture
def cursor_manager(mock_plot_item):
    """Return a CursorToolManager backed by mock widget/scene."""
    # Patch pyqtgraph constructors that would require a real display
    with (
        patch("Synaptipy.shared.cursor_manager.pg.ScatterPlotItem") as mock_scatter,
        patch("Synaptipy.shared.cursor_manager.pg.TextItem") as mock_text,
        patch("Synaptipy.shared.cursor_manager.pg.PlotDataItem") as mock_line,
    ):

        mock_scatter.return_value = MagicMock()
        mock_text.return_value = MagicMock()
        mock_line.return_value = MagicMock()

        from Synaptipy.shared.cursor_manager import CursorToolManager

        mock_widget = MagicMock()
        mock_scene = MagicMock()

        mgr = CursorToolManager(widget=mock_widget, scene=mock_scene)
        mgr.set_cursor_enabled(True)
        # Store patches so tests can introspect call counts
        mgr._mock_scatter = mock_scatter
        mgr._mock_text = mock_text
        mgr._mock_line = mock_line
        yield mgr


# ---------------------------------------------------------------------------
# set_cursor_enabled / set_delta_mode_enabled
# ---------------------------------------------------------------------------


class TestSetEnabled:
    def test_cursor_disabled_by_default(self):
        from Synaptipy.shared.cursor_manager import CursorToolManager

        mgr = CursorToolManager(widget=MagicMock(), scene=MagicMock())
        assert mgr._cursor_mode_enabled is False

    def test_set_cursor_enabled_true(self, cursor_manager):
        cursor_manager.set_cursor_enabled(True)
        assert cursor_manager._cursor_mode_enabled is True

    def test_set_cursor_enabled_false(self, cursor_manager):
        cursor_manager.set_cursor_enabled(False)
        assert cursor_manager._cursor_mode_enabled is False

    def test_set_delta_mode_enabled_true(self, cursor_manager):
        cursor_manager.set_delta_mode_enabled(True)
        assert cursor_manager._delta_mode_enabled is True

    def test_set_delta_mode_enabled_false_clears_anchor(self, cursor_manager, mock_plot_item):
        """Disabling delta mode while an anchor is pending must clean it up."""
        with (
            patch("Synaptipy.shared.cursor_manager.pg.ScatterPlotItem") as ms,
            patch("Synaptipy.shared.cursor_manager.pg.TextItem") as mt,
        ):
            ms.return_value = MagicMock()
            mt.return_value = MagicMock()
            cursor_manager._delta_mode_enabled = True
            cursor_manager.handle_delta_click(0.5, 0.25, mock_plot_item)
            assert cursor_manager._delta_anchor is not None
        cursor_manager.set_delta_mode_enabled(False)
        assert cursor_manager._delta_anchor is None
        assert cursor_manager._delta_mode_enabled is False


# ---------------------------------------------------------------------------
# add_cursor_box — single cursor placement
# ---------------------------------------------------------------------------


class TestAddCursorBox:
    def test_adds_entry_to_history(self, cursor_manager, mock_plot_item):
        with (
            patch("Synaptipy.shared.cursor_manager.pg.ScatterPlotItem") as ms,
            patch("Synaptipy.shared.cursor_manager.pg.TextItem") as mt,
        ):
            ms.return_value = MagicMock()
            mt.return_value = MagicMock()
            cursor_manager.add_cursor_box(1.0, 2.0, mock_plot_item)

        assert len(cursor_manager._cursor_history) == 1
        entry = cursor_manager._cursor_history[0]
        assert entry["type"] == "single"
        assert entry["data"] == (1.0, 2.0)

    def test_multiple_single_cursors(self, cursor_manager, mock_plot_item):
        with (
            patch("Synaptipy.shared.cursor_manager.pg.ScatterPlotItem") as ms,
            patch("Synaptipy.shared.cursor_manager.pg.TextItem") as mt,
        ):
            ms.return_value = MagicMock()
            mt.return_value = MagicMock()
            cursor_manager.add_cursor_box(0.0, 0.0, mock_plot_item)
            cursor_manager.add_cursor_box(1.0, 1.0, mock_plot_item)

        assert len(cursor_manager._cursor_history) == 2

    def test_items_added_to_plot(self, cursor_manager, mock_plot_item):
        with (
            patch("Synaptipy.shared.cursor_manager.pg.ScatterPlotItem") as ms,
            patch("Synaptipy.shared.cursor_manager.pg.TextItem") as mt,
        ):
            ms.return_value = MagicMock()
            mt.return_value = MagicMock()
            cursor_manager.add_cursor_box(0.5, 0.5, mock_plot_item)

        # addItem must have been called for marker and text
        assert mock_plot_item.addItem.call_count == 2

    def test_cursor_added_signal_emitted(self, cursor_manager, mock_plot_item):
        received = []
        cursor_manager.cursor_added.connect(lambda x, y: received.append((x, y)))
        with (
            patch("Synaptipy.shared.cursor_manager.pg.ScatterPlotItem") as ms,
            patch("Synaptipy.shared.cursor_manager.pg.TextItem") as mt,
        ):
            ms.return_value = MagicMock()
            mt.return_value = MagicMock()
            cursor_manager.add_cursor_box(3.0, 4.0, mock_plot_item)

        assert received == [(3.0, 4.0)]


# ---------------------------------------------------------------------------
# handle_delta_click — pair numbering and anchor state machine
# ---------------------------------------------------------------------------


class TestHandleDeltaClick:
    def _click_pair(self, cursor_manager, plot_item, x1=0.0, y1=0.0, x2=1.0, y2=1.0):
        with (
            patch("Synaptipy.shared.cursor_manager.pg.ScatterPlotItem") as ms,
            patch("Synaptipy.shared.cursor_manager.pg.TextItem") as mt,
            patch("Synaptipy.shared.cursor_manager.pg.PlotDataItem") as ml,
        ):
            ms.return_value = MagicMock()
            mt.return_value = MagicMock()
            ml.return_value = MagicMock()
            cursor_manager.handle_delta_click(x1, y1, plot_item)
            cursor_manager.handle_delta_click(x2, y2, plot_item)

    def test_first_click_sets_anchor(self, cursor_manager, mock_plot_item):
        with (
            patch("Synaptipy.shared.cursor_manager.pg.ScatterPlotItem") as ms,
            patch("Synaptipy.shared.cursor_manager.pg.TextItem") as mt,
        ):
            ms.return_value = MagicMock()
            mt.return_value = MagicMock()
            cursor_manager.handle_delta_click(0.0, 0.0, mock_plot_item)

        assert cursor_manager._delta_anchor is not None
        assert cursor_manager._delta_anchor["x"] == 0.0
        assert cursor_manager._delta_anchor["y"] == 0.0

    def test_second_click_clears_anchor_and_records_delta(self, cursor_manager, mock_plot_item):
        self._click_pair(cursor_manager, mock_plot_item)

        assert cursor_manager._delta_anchor is None
        assert len(cursor_manager._cursor_history) == 1
        entry = cursor_manager._cursor_history[0]
        assert entry["type"] == "delta"

    def test_delta_pair_numbering_increments(self, cursor_manager, mock_plot_item):
        self._click_pair(cursor_manager, mock_plot_item)
        self._click_pair(cursor_manager, mock_plot_item, x1=2.0, y1=2.0, x2=3.0, y2=3.0)

        assert cursor_manager._delta_pair_counter == 2
        assert cursor_manager._cursor_history[0]["data"][6] == 1  # pair_id of first pair
        assert cursor_manager._cursor_history[1]["data"][6] == 2  # pair_id of second pair

    def test_cross_plot_click_resets_anchor(self, cursor_manager, mock_plot_item):
        """If second click is on a different plot, anchor is cancelled."""
        other_plot = MagicMock()
        with (
            patch("Synaptipy.shared.cursor_manager.pg.ScatterPlotItem") as ms,
            patch("Synaptipy.shared.cursor_manager.pg.TextItem") as mt,
        ):
            ms.return_value = MagicMock()
            mt.return_value = MagicMock()
            # First click sets anchor on mock_plot_item
            cursor_manager.handle_delta_click(0.0, 0.0, mock_plot_item)
            # Second click on a different plot should cancel and restart
            cursor_manager.handle_delta_click(1.0, 1.0, other_plot)

        # Anchor should now be on other_plot (restarted), not mock_plot_item
        assert cursor_manager._delta_anchor is not None
        assert cursor_manager._delta_anchor["plot"] is other_plot


# ---------------------------------------------------------------------------
# undo()
# ---------------------------------------------------------------------------


class TestUndo:
    def test_undo_removes_last_single_cursor(self, cursor_manager, mock_plot_item):
        with (
            patch("Synaptipy.shared.cursor_manager.pg.ScatterPlotItem") as ms,
            patch("Synaptipy.shared.cursor_manager.pg.TextItem") as mt,
        ):
            ms.return_value = MagicMock()
            mt.return_value = MagicMock()
            cursor_manager.add_cursor_box(1.0, 1.0, mock_plot_item)
            cursor_manager.add_cursor_box(2.0, 2.0, mock_plot_item)

        cursor_manager.undo()
        assert len(cursor_manager._cursor_history) == 1
        assert cursor_manager._cursor_history[0]["data"] == (1.0, 1.0)

    def test_undo_removes_last_delta_pair_and_decrements_counter(self, cursor_manager, mock_plot_item):
        with (
            patch("Synaptipy.shared.cursor_manager.pg.ScatterPlotItem") as ms,
            patch("Synaptipy.shared.cursor_manager.pg.TextItem") as mt,
            patch("Synaptipy.shared.cursor_manager.pg.PlotDataItem") as ml,
        ):
            ms.return_value = MagicMock()
            mt.return_value = MagicMock()
            ml.return_value = MagicMock()
            cursor_manager.handle_delta_click(0.0, 0.0, mock_plot_item)
            cursor_manager.handle_delta_click(1.0, 1.0, mock_plot_item)

        assert cursor_manager._delta_pair_counter == 1
        cursor_manager.undo()
        assert cursor_manager._delta_pair_counter == 0
        assert len(cursor_manager._cursor_history) == 0

    def test_undo_pending_anchor_cancels_it(self, cursor_manager, mock_plot_item):
        """Calling undo with a pending (unconfirmed) anchor should cancel it."""
        with (
            patch("Synaptipy.shared.cursor_manager.pg.ScatterPlotItem") as ms,
            patch("Synaptipy.shared.cursor_manager.pg.TextItem") as mt,
        ):
            ms.return_value = MagicMock()
            mt.return_value = MagicMock()
            cursor_manager.handle_delta_click(0.0, 0.0, mock_plot_item)

        assert cursor_manager._delta_anchor is not None
        cursor_manager.undo()
        assert cursor_manager._delta_anchor is None

    def test_undo_on_empty_history_is_safe(self, cursor_manager):
        """undo() with nothing in history must not raise."""
        cursor_manager.undo()  # should not raise
        assert len(cursor_manager._cursor_history) == 0

    def test_undo_last_cursor_alias(self, cursor_manager, mock_plot_item):
        """undo_last_cursor() is an alias for undo()."""
        with (
            patch("Synaptipy.shared.cursor_manager.pg.ScatterPlotItem") as ms,
            patch("Synaptipy.shared.cursor_manager.pg.TextItem") as mt,
        ):
            ms.return_value = MagicMock()
            mt.return_value = MagicMock()
            cursor_manager.add_cursor_box(1.0, 1.0, mock_plot_item)

        cursor_manager.undo_last_cursor()
        assert len(cursor_manager._cursor_history) == 0


# ---------------------------------------------------------------------------
# clear()
# ---------------------------------------------------------------------------


class TestClear:
    def test_clear_empties_history(self, cursor_manager, mock_plot_item):
        with (
            patch("Synaptipy.shared.cursor_manager.pg.ScatterPlotItem") as ms,
            patch("Synaptipy.shared.cursor_manager.pg.TextItem") as mt,
        ):
            ms.return_value = MagicMock()
            mt.return_value = MagicMock()
            cursor_manager.add_cursor_box(1.0, 1.0, mock_plot_item)
            cursor_manager.add_cursor_box(2.0, 2.0, mock_plot_item)

        cursor_manager.clear()
        assert len(cursor_manager._cursor_history) == 0

    def test_clear_resets_pair_counter(self, cursor_manager, mock_plot_item):
        with (
            patch("Synaptipy.shared.cursor_manager.pg.ScatterPlotItem") as ms,
            patch("Synaptipy.shared.cursor_manager.pg.TextItem") as mt,
            patch("Synaptipy.shared.cursor_manager.pg.PlotDataItem") as ml,
        ):
            ms.return_value = MagicMock()
            mt.return_value = MagicMock()
            ml.return_value = MagicMock()
            cursor_manager.handle_delta_click(0.0, 0.0, mock_plot_item)
            cursor_manager.handle_delta_click(1.0, 1.0, mock_plot_item)

        cursor_manager.clear()
        assert cursor_manager._delta_pair_counter == 0

    def test_clear_removes_pending_anchor(self, cursor_manager, mock_plot_item):
        with (
            patch("Synaptipy.shared.cursor_manager.pg.ScatterPlotItem") as ms,
            patch("Synaptipy.shared.cursor_manager.pg.TextItem") as mt,
        ):
            ms.return_value = MagicMock()
            mt.return_value = MagicMock()
            cursor_manager.handle_delta_click(0.0, 0.0, mock_plot_item)

        cursor_manager.clear()
        assert cursor_manager._delta_anchor is None

    def test_clear_all_cursors_alias(self, cursor_manager, mock_plot_item):
        """clear_all_cursors() is an alias for clear()."""
        with (
            patch("Synaptipy.shared.cursor_manager.pg.ScatterPlotItem") as ms,
            patch("Synaptipy.shared.cursor_manager.pg.TextItem") as mt,
        ):
            ms.return_value = MagicMock()
            mt.return_value = MagicMock()
            cursor_manager.add_cursor_box(5.0, 5.0, mock_plot_item)

        cursor_manager.clear_all_cursors()
        assert len(cursor_manager._cursor_history) == 0


# ---------------------------------------------------------------------------
# get_history() / get_cursor_history()
# ---------------------------------------------------------------------------


class TestGetHistory:
    def test_get_history_returns_copy(self, cursor_manager, mock_plot_item):
        with (
            patch("Synaptipy.shared.cursor_manager.pg.ScatterPlotItem") as ms,
            patch("Synaptipy.shared.cursor_manager.pg.TextItem") as mt,
        ):
            ms.return_value = MagicMock()
            mt.return_value = MagicMock()
            cursor_manager.add_cursor_box(1.0, 1.0, mock_plot_item)

        history = cursor_manager.get_history()
        assert len(history) == 1
        # Modifying the copy must not affect the internal list
        history.clear()
        assert len(cursor_manager._cursor_history) == 1

    def test_get_cursor_history_alias(self, cursor_manager, mock_plot_item):
        with (
            patch("Synaptipy.shared.cursor_manager.pg.ScatterPlotItem") as ms,
            patch("Synaptipy.shared.cursor_manager.pg.TextItem") as mt,
        ):
            ms.return_value = MagicMock()
            mt.return_value = MagicMock()
            cursor_manager.add_cursor_box(2.0, 2.0, mock_plot_item)

        h1 = cursor_manager.get_history()
        h2 = cursor_manager.get_cursor_history()
        assert len(h1) == len(h2) == 1

    def test_empty_history_returns_empty_list(self, cursor_manager):
        assert cursor_manager.get_history() == []


# ---------------------------------------------------------------------------
# _find_nearest_point — pure numpy computation (lines 65-81)
# ---------------------------------------------------------------------------


class TestFindNearestPoint:
    def test_finds_correct_nearest_point(self, cursor_manager):
        """Lines 65-81: nearest-point search returns the closest data point."""
        item = MagicMock()
        item.xData = np.array([0.0, 1.0, 2.0, 3.0])
        item.yData = np.array([0.0, 1.0, 2.0, 3.0])
        x, y = cursor_manager._find_nearest_point(1.3, 1.3, 3.0, 3.0, [item])
        assert x == pytest.approx(1.0)
        assert y == pytest.approx(1.0)

    def test_returns_none_when_no_items(self, cursor_manager):
        """Empty items list → (None, None)."""
        x, y = cursor_manager._find_nearest_point(0.5, 0.5, 2.0, 2.0, [])
        assert x is None
        assert y is None

    def test_skips_item_with_none_data(self, cursor_manager):
        """Item with xData=None is skipped."""
        item = MagicMock()
        item.xData = None
        item.yData = np.array([1.0, 2.0])
        x, y = cursor_manager._find_nearest_point(0.5, 0.5, 2.0, 2.0, [item])
        assert x is None and y is None

    def test_skips_item_with_empty_xdata(self, cursor_manager):
        """Item with empty xData is skipped."""
        item = MagicMock()
        item.xData = np.array([])
        item.yData = np.array([])
        x, y = cursor_manager._find_nearest_point(0.5, 0.5, 2.0, 2.0, [item])
        assert x is None and y is None

    def test_skips_item_with_mismatched_lengths(self, cursor_manager):
        """Item where len(xData) != len(yData) is skipped."""
        item = MagicMock()
        item.xData = np.array([0.0, 1.0, 2.0])
        item.yData = np.array([0.0, 1.0])
        x, y = cursor_manager._find_nearest_point(0.5, 0.5, 2.0, 2.0, [item])
        assert x is None and y is None

    def test_picks_closest_of_multiple_items(self, cursor_manager):
        """When two items overlap, the truly nearest point wins."""
        item1 = MagicMock()
        item1.xData = np.array([0.0, 5.0])
        item1.yData = np.array([0.0, 5.0])
        item2 = MagicMock()
        item2.xData = np.array([1.0, 4.0])
        item2.yData = np.array([1.0, 4.0])
        # Click near (1.0, 1.0) — item2's first point should win
        x, y = cursor_manager._find_nearest_point(1.0, 1.0, 5.0, 5.0, [item1, item2])
        assert x == pytest.approx(1.0)
        assert y == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# _get_all_plots — PlotWidget branch (lines 47-54)
# ---------------------------------------------------------------------------


class TestGetAllPlots:
    def test_get_all_plots_with_plot_widget(self, cursor_manager):
        """Lines 47-48: when widget is a pg.PlotWidget return [getPlotItem()]."""
        import pyqtgraph as pg

        fake_plot_item = MagicMock()
        mock_pw = MagicMock(spec=pg.PlotWidget)
        mock_pw.getPlotItem.return_value = fake_plot_item
        cursor_manager.widget = mock_pw
        plots = cursor_manager._get_all_plots()
        assert len(plots) == 1
        assert plots[0] is fake_plot_item

    def test_get_all_plots_from_scene_items(self, cursor_manager):
        """Lines 50-54: when widget is not PlotWidget, fall back to scene.items()."""
        import pyqtgraph as pg

        fake_plot = MagicMock(spec=pg.PlotItem)
        not_plot = MagicMock()  # not a PlotItem
        cursor_manager.widget = MagicMock()  # not a pg.PlotWidget
        cursor_manager.scene = MagicMock()
        cursor_manager.scene.items.return_value = [fake_plot, not_plot]
        plots = cursor_manager._get_all_plots()
        assert fake_plot in plots
        assert not_plot not in plots


# ---------------------------------------------------------------------------
# zoom_theme ImportError branches (lines 130-131, 214-215)
# ---------------------------------------------------------------------------


class TestZoomThemeImportFallback:
    def test_handle_delta_click_zoom_theme_import_error(self, cursor_manager, mock_plot_item):
        """Lines 130-131: if zoom_theme ImportError, fall back to default colour."""
        import sys

        with (
            patch("Synaptipy.shared.cursor_manager.pg.ScatterPlotItem") as ms,
            patch("Synaptipy.shared.cursor_manager.pg.TextItem") as mt,
            patch.dict(sys.modules, {"Synaptipy.shared.zoom_theme": None}),
        ):
            ms.return_value = MagicMock()
            mt.return_value = MagicMock()
            # Should not raise — falls back to default colour
            cursor_manager.handle_delta_click(0.5, 0.5, mock_plot_item)
        # Only first click sets anchor
        assert cursor_manager._delta_anchor is not None

    def test_add_cursor_box_zoom_theme_import_error(self, cursor_manager, mock_plot_item):
        """Lines 214-215: if zoom_theme ImportError in add_cursor_box, fall back."""
        import sys

        with (
            patch("Synaptipy.shared.cursor_manager.pg.ScatterPlotItem") as ms,
            patch("Synaptipy.shared.cursor_manager.pg.TextItem") as mt,
            patch.dict(sys.modules, {"Synaptipy.shared.zoom_theme": None}),
        ):
            ms.return_value = MagicMock()
            mt.return_value = MagicMock()
            cursor_manager.add_cursor_box(1.0, 2.0, mock_plot_item)
        assert len(cursor_manager._cursor_history) == 1
