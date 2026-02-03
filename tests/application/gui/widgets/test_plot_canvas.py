
import pytest
from PySide6 import QtCore, QtWidgets
import pyqtgraph as pg
from Synaptipy.application.gui.widgets.plot_canvas import SynaptipyPlotCanvas

@pytest.fixture
def plot_canvas(qtbot):
    canvas = SynaptipyPlotCanvas()
    qtbot.addWidget(canvas.widget)
    return canvas

def test_add_plot(plot_canvas):
    p1 = plot_canvas.add_plot("plot1", row=0, col=0)
    assert p1 is not None
    assert "plot1" in plot_canvas.plot_items
    assert plot_canvas.main_plot == p1
    
    p2 = plot_canvas.add_plot("plot2", row=1, col=0)
    assert "plot2" in plot_canvas.plot_items
    # Main plot should still be p1 unless changed
    assert plot_canvas.main_plot == p1

def test_get_plot(plot_canvas):
    plot_canvas.add_plot("p1")
    assert plot_canvas.get_plot("p1") is not None
    assert plot_canvas.get_plot("non_existent") is None

def test_clear_plots(plot_canvas):
    plot_canvas.add_plot("p1")
    plot_canvas.add_plot("p2")
    assert len(plot_canvas.plot_items) == 2
    
    plot_canvas.clear_plots()
    assert len(plot_canvas.plot_items) == 0
    assert plot_canvas.main_plot is None

def test_signals(plot_canvas, qtbot):
    p1 = plot_canvas.add_plot("p1")
    vb = p1.getViewBox()
    
    with qtbot.waitSignal(plot_canvas.x_range_changed, timeout=1000) as blocker:
        vb.setXRange(0, 10, padding=0)
    
    assert blocker.args[0] == "p1"
    # Check range values (approximate)
    ranges = blocker.args[1]
    assert abs(ranges[0] - 0) < 0.1
    assert abs(ranges[1] - 10) < 0.1

def test_clear_items(plot_canvas):
    p1 = plot_canvas.add_plot("p1")
    p1.plot([1, 2, 3], [1, 2, 3])
    assert len(p1.listDataItems()) == 1
    
    plot_canvas.clear_items("p1")
    assert len(p1.listDataItems()) == 0
