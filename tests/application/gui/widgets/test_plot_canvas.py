
import sys
import pytest
from PySide6 import QtCore, QtWidgets  # noqa: F401
from Synaptipy.application.gui.widgets.plot_canvas import SynaptipyPlotCanvas


@pytest.fixture(scope="session")
def plot_canvas(qapp):
    canvas = SynaptipyPlotCanvas()
    return canvas


@pytest.fixture(autouse=True)
def reset_canvas(plot_canvas):
    """Clear all plots before and drain events after every test (Win/Linux).

    Runs clear_plots() BEFORE each test so each starts with a clean canvas.
    After the test, drains the Qt posted-event queue so pyqtgraph deferred
    callbacks from the just-run test (range/layout events queued during plot
    operations) do not fire during the C++ teardown in the next test's
    clear_plots() call, which would cause SIGBUS / access-violations.
    removePostedEvents discards events without executing callbacks -- safe
    for this single-canvas fixture; clear_plots() has already handled all
    live canvas teardown via _unlink_all_plots + _close_all_plots.

    macOS excluded: see conftest._drain_qt_events_after_test for rationale.
    """
    plot_canvas.clear_plots()
    yield
    if sys.platform == 'darwin':
        return
    try:
        from PySide6.QtCore import QCoreApplication
        QCoreApplication.removePostedEvents(None, 0)
    except Exception:
        pass


def test_add_plot(plot_canvas):
    p1 = plot_canvas.add_plot("plot1", row=0, col=0)
    assert p1 is not None
    assert "plot1" in plot_canvas.plot_items
    assert plot_canvas.main_plot == p1

    plot_canvas.add_plot("plot2", row=1, col=0)
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
