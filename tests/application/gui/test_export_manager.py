# tests/application/gui/test_export_manager.py
# -*- coding: utf-8 -*-
"""
Tests for ExportManager (Phase 4 of the CoI refactor).

All tests are structural / unit-level: they verify the public API exists
and that ``create_popup_plot`` returns the expected types without creating
real file dialogs or real pop-up windows.
"""

import pytest

from Synaptipy.application.gui.dialogs.export_manager import ExportManager

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def manager(qtbot):
    """A bare ExportManager with no parent widget."""
    em = ExportManager(parent=None)
    yield em


# ---------------------------------------------------------------------------
# Structure tests
# ---------------------------------------------------------------------------


class TestExportManagerStructure:
    """ExportManager exposes the expected public API."""

    def test_instantiates(self, manager):
        assert manager is not None

    def test_has_create_popup_plot(self, manager):
        assert callable(getattr(manager, "create_popup_plot", None))

    def test_has_save_plot(self, manager):
        assert callable(getattr(manager, "save_plot", None))


# ---------------------------------------------------------------------------
# create_popup_plot tests
# ---------------------------------------------------------------------------


class TestCreatePopupPlot:
    """create_popup_plot returns (QMainWindow, PlotWidget) and tracks the popup."""

    def test_returns_tuple_of_two(self, manager, qtbot):
        result = manager.create_popup_plot("Test Popup")
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_second_element_is_plot_widget(self, manager, qtbot):
        import pyqtgraph as pg

        popup, plot_widget = manager.create_popup_plot("Test")
        qtbot.addWidget(popup)
        assert isinstance(plot_widget, pg.PlotWidget)

    def test_popup_window_title(self, manager, qtbot):
        popup, _ = manager.create_popup_plot("My Title")
        qtbot.addWidget(popup)
        assert popup.windowTitle() == "My Title"

    def test_x_label_applied(self, manager, qtbot):
        popup, plot_widget = manager.create_popup_plot("T", x_label="Time (s)")
        qtbot.addWidget(popup)
        bottom_label = plot_widget.getPlotItem().getAxis("bottom").labelText
        assert "Time (s)" in bottom_label

    def test_y_label_applied(self, manager, qtbot):
        popup, plot_widget = manager.create_popup_plot("T", y_label="Voltage (mV)")
        qtbot.addWidget(popup)
        left_label = plot_widget.getPlotItem().getAxis("left").labelText
        assert "Voltage (mV)" in left_label

    def test_no_labels_does_not_crash(self, manager, qtbot):
        popup, plot_widget = manager.create_popup_plot("No Labels")
        qtbot.addWidget(popup)
        assert plot_widget is not None

    def test_popup_is_qmain_window(self, manager, qtbot):
        from PySide6 import QtWidgets

        popup, _ = manager.create_popup_plot("Win")
        qtbot.addWidget(popup)
        assert isinstance(popup, QtWidgets.QMainWindow)

    def test_popup_not_delete_on_close(self, manager, qtbot):
        from PySide6 import QtCore

        popup, _ = manager.create_popup_plot("Win")
        qtbot.addWidget(popup)
        assert not popup.testAttribute(QtCore.Qt.WidgetAttribute.WA_DeleteOnClose)


# ---------------------------------------------------------------------------
# save_plot tests
# ---------------------------------------------------------------------------


class TestSavePlot:
    """save_plot delegates to PlotExportDialog + QFileDialog + PlotExporter."""

    def test_save_plot_no_crash_when_dialog_rejected(self, manager, qtbot):
        """If the export dialog is rejected, save_plot must exit silently."""
        from unittest.mock import MagicMock, patch

        mock_plot = MagicMock()
        with patch("Synaptipy.application.gui.dialogs.export_manager.PlotExportDialog") as MockDialog:
            instance = MockDialog.return_value
            instance.exec.return_value = False  # user cancels
            # Should not raise
            manager.save_plot(mock_plot, "MyTab", None, None)
            instance.exec.assert_called_once()

    def test_save_plot_calls_exporter_on_accept(self, manager, qtbot, tmp_path):
        """If user accepts and chooses a file, PlotExporter.export is called."""
        from unittest.mock import MagicMock, patch

        save_path = str(tmp_path / "plot.png")
        mock_plot = MagicMock()

        with (
            patch("Synaptipy.application.gui.dialogs.export_manager.PlotExportDialog") as MockDialog,
            patch(
                "Synaptipy.application.gui.dialogs.export_manager.QtWidgets.QFileDialog.getSaveFileName",
                return_value=(save_path, "Images (*.png)"),
            ),
            patch("Synaptipy.application.gui.dialogs.export_manager.PlotExporter") as MockExporter,
        ):
            mock_dialog_inst = MockDialog.return_value
            mock_dialog_inst.exec.return_value = True
            mock_dialog_inst.get_settings.return_value = {"format": "png", "dpi": 150}
            mock_exporter_inst = MockExporter.return_value
            mock_exporter_inst.export.return_value = True

            manager.save_plot(mock_plot, "TestTab", None, None)

            MockExporter.assert_called_once()
            mock_exporter_inst.export.assert_called_once_with(save_path, "png", 150)
