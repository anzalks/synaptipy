"""
Headless visual regression tests for SynaptipyPlotCanvas.

These tests verify that the plot canvas correctly adds and retains pyqtgraph
data items after plotting operations.  They run entirely in offscreen mode with
synthetic numpy data so no real ABF files are required.

Purpose: assert that a future pyqtgraph or PySide6 update does not silently
break plot rendering (e.g., items added but never painted, clear() not
removing stale items, LinearRegionItem not attaching to the scene, etc.)

Run only these tests:
    pytest tests/gui/test_headless_visuals.py -v
"""

import sys

import numpy as np
import pyqtgraph as pg
import pytest
from PySide6 import QtCore

from Synaptipy.application.gui.widgets.plot_canvas import SynaptipyPlotCanvas

# ---------------------------------------------------------------------------
# Shared synthetic data
# ---------------------------------------------------------------------------

_SAMPLE_RATE = 20_000  # Hz
_DURATION = 0.5  # s
_N = int(_SAMPLE_RATE * _DURATION)
_T = np.linspace(0, _DURATION, _N, endpoint=False)
_V = np.sin(2 * np.pi * 50 * _T) + np.random.default_rng(42).normal(0, 0.05, _N)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def canvas(qapp, qtbot):
    """A fresh SynaptipyPlotCanvas with one plot, cleaned up after the test."""
    c = SynaptipyPlotCanvas(parent=None)
    qtbot.addWidget(c.widget)
    c.add_plot("test_plot", row=0, col=0)
    yield c
    # Tear down safely: let the event loop process deferred events on Win/Linux
    # before the canvas goes out of scope.
    if sys.platform != "darwin":
        QtCore.QCoreApplication.removePostedEvents(None, 0)


# ---------------------------------------------------------------------------
# Canvas construction
# ---------------------------------------------------------------------------


class TestCanvasConstruction:
    """Verify SynaptipyPlotCanvas sets up its widget and plot registry."""

    def test_widget_created(self, canvas):
        """The underlying GraphicsLayoutWidget must exist."""
        assert canvas.widget is not None

    def test_plot_registered(self, canvas):
        """add_plot() must register a PlotItem under the given key."""
        assert "test_plot" in canvas.plot_items
        assert isinstance(canvas.plot_items["test_plot"], pg.PlotItem)

    def test_main_plot_property(self, canvas):
        """main_plot property must return the first registered PlotItem."""
        assert canvas.main_plot is canvas.plot_items["test_plot"]


# ---------------------------------------------------------------------------
# Plotting data
# ---------------------------------------------------------------------------


class TestPlotDataItems:
    """Verify that plotting synthetic data produces the correct item count."""

    def test_single_curve_adds_one_item(self, canvas):
        """Plotting a single array must add exactly one PlotDataItem."""
        plot = canvas.plot_items["test_plot"]
        plot.plot(_T, _V, pen=pg.mkPen("b"))
        items = plot.listDataItems()
        assert len(items) == 1, f"Expected 1 PlotDataItem, got {len(items)}"
        assert isinstance(items[0], pg.PlotDataItem)

    def test_multiple_curves_add_multiple_items(self, canvas):
        """Plotting N arrays must add exactly N PlotDataItems."""
        plot = canvas.plot_items["test_plot"]
        n_curves = 5
        rng = np.random.default_rng(0)
        for i in range(n_curves):
            noise = rng.normal(0, 0.1, _N)
            plot.plot(_T, _V + noise)
        items = plot.listDataItems()
        assert len(items) == n_curves, f"Expected {n_curves} PlotDataItems, got {len(items)}"

    def test_clear_removes_all_items(self, canvas):
        """clear() must leave zero PlotDataItems."""
        plot = canvas.plot_items["test_plot"]
        plot.plot(_T, _V)
        plot.plot(_T, _V * 0.5)
        plot.clear()
        items = plot.listDataItems()
        assert len(items) == 0, f"Expected 0 items after clear(), got {len(items)}"


# ---------------------------------------------------------------------------
# LinearRegionItem
# ---------------------------------------------------------------------------


class TestLinearRegionItem:
    """Verify that LinearRegionItem can be added to and removed from a plot."""

    def test_region_added_to_plot(self, canvas):
        """A LinearRegionItem added via addItem() must appear in the ViewBox."""
        plot = canvas.plot_items["test_plot"]
        region = pg.LinearRegionItem(
            values=[0.1, 0.2],
            orientation=pg.LinearRegionItem.Vertical,
            brush=pg.mkBrush(0, 200, 0, 40),
        )
        plot.addItem(region)
        vb_items = plot.getViewBox().addedItems
        assert region in vb_items, "LinearRegionItem not found in ViewBox.addedItems after addItem()"

    def test_region_removed_from_plot(self, canvas):
        """removeItem() must remove the LinearRegionItem from the ViewBox."""
        plot = canvas.plot_items["test_plot"]
        region = pg.LinearRegionItem(values=[0.1, 0.2])
        plot.addItem(region)
        plot.removeItem(region)
        vb_items = plot.getViewBox().addedItems
        assert region not in vb_items, "LinearRegionItem still in ViewBox.addedItems after removeItem()"

    def test_region_bounds(self, canvas):
        """LinearRegionItem must report the bounds it was created with."""
        plot = canvas.plot_items["test_plot"]
        region = pg.LinearRegionItem(values=[0.05, 0.25])
        plot.addItem(region)
        lo, hi = region.getRegion()
        assert pytest.approx(lo) == 0.05
        assert pytest.approx(hi) == 0.25


# ---------------------------------------------------------------------------
# Multiple plots in one canvas
# ---------------------------------------------------------------------------


class TestMultiplePlots:
    """Verify that a canvas can manage multiple PlotItems independently."""

    def test_two_plots_independent(self, canvas):
        """Items added to plot A must not appear in plot B."""
        canvas.add_plot("plot_b", row=1, col=0)
        plot_a = canvas.plot_items["test_plot"]
        plot_b = canvas.plot_items["plot_b"]
        plot_a.plot(_T, _V)
        assert len(plot_a.listDataItems()) == 1
        assert len(plot_b.listDataItems()) == 0

    def test_get_plot_returns_correct_item(self, canvas):
        """get_plot() must return the PlotItem registered under the given key."""
        canvas.add_plot("plot_c", row=2, col=0)
        assert canvas.get_plot("test_plot") is canvas.plot_items["test_plot"]
        assert canvas.get_plot("plot_c") is canvas.plot_items["plot_c"]
        assert canvas.get_plot("nonexistent") is None
