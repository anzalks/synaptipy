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
"""

from unittest.mock import MagicMock, patch

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
