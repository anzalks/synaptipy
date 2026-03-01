"""
Unit tests for the Exporter Tab functionality
"""

import pathlib
import pytest
import tempfile
from unittest.mock import MagicMock, patch
from PySide6 import QtWidgets, QtCore

from Synaptipy.application.gui.exporter_tab import ExporterTab


@pytest.fixture
def mock_main_window():
    """Mock main window with saved analysis results"""
    window = MagicMock()

    # Create mock saved analysis results
    window.saved_analysis_results = [
        {
            "analysis_type": "Input Resistance",
            "channel_name": "Vm",
            "calculation_method": "Interactive Regions",
            "timestamp": "2023-10-25 15:30:45",
            "specific_data": {"Input Resistance (kOhm)": 200.0, "Baseline Std Dev": 0.5},
        },
        {
            "analysis_type": "Resting Membrane Potential",
            "channel_name": "Vm",
            "calculation_method": "Mean",
            "timestamp": "2023-10-25 15:35:20",
            "specific_data": {"RMP (mV)": -65.3, "Std Dev (mV)": 0.8},
        },
        {
            "analysis_type": "Event Detection",
            "channel_name": "Im",
            "calculation_method": "Threshold Crossing",
            "timestamp": "2023-10-25 15:40:00",
            "specific_data": {
                "Event Count": 45,
                "Mean Amplitude (pA)": 25.3,
                "Mean Rise Time (ms)": 2.4,
                "Detection Parameters": {"threshold": 10.0, "min_duration": 0.5},
            },
        },
    ]

    return window


@pytest.fixture
def exporter_tab(qtbot, mock_main_window):
    """Create an exporter tab attached to a mock main window"""
    # Mock all required dependencies
    nwb_exporter_ref = MagicMock(name="nwb_exporter")
    settings_ref = MagicMock(spec=QtCore.QSettings)
    status_bar_ref = MagicMock(spec=QtWidgets.QStatusBar)

    # Create the tab
    tab = ExporterTab(
        nwb_exporter_ref=nwb_exporter_ref,
        settings_ref=settings_ref,
        status_bar_ref=status_bar_ref
    )
    qtbot.addWidget(tab)

    # Attach to mock main window and set up parent relationship
    tab.window = MagicMock(return_value=mock_main_window)

    return tab


def test_exporter_tab_init(exporter_tab):
    """Test that the exporter tab initializes correctly"""
    assert exporter_tab is not None
    assert hasattr(exporter_tab, "sub_tab_widget")

    # Check if the analysis results tab exists
    assert exporter_tab.sub_tab_widget.count() >= 2
    # The second tab should be the Analysis Results tab
    assert "Analysis Results" in exporter_tab.sub_tab_widget.tabText(1)


def test_refresh_analysis_results(exporter_tab, mock_main_window):
    """Test refreshing the analysis results table"""
    # Call refresh method
    exporter_tab._refresh_analysis_results()

    # Verify table has correct number of rows (one per result)
    assert exporter_tab.analysis_results_table.rowCount() == \
        len(mock_main_window.saved_analysis_results)

    # Check first row contains analysis type
    assert "Input Resistance" in exporter_tab.analysis_results_table.item(0, 0).text()


def test_export_to_csv(exporter_tab, qtbot, mock_main_window):
    """Test exporting analysis results to CSV.

    The new exporter writes one tidy CSV per analysis_type into a directory
    (or a zip when the output path ends with .csv).  This test uses a real
    temp-directory path so the zip branch is skipped and we can verify the
    per-type to_csv calls directly.
    """
    # Create a temporary directory for test output; pass the directory path so
    # the exporter writes individual CSVs directly into it (no zip created).
    with tempfile.TemporaryDirectory() as temp_dir:
        # Set the export path to a directory — exporter uses the directory branch
        exporter_tab.analysis_results_path_edit.setText(temp_dir)

        # Refresh the analysis results
        exporter_tab._refresh_analysis_results()

        # Select all rows
        exporter_tab.analysis_results_table.selectAll()

        # Expect one to_csv call per unique analysis_type in the fixture (3 types):
        # "Input Resistance", "Resting Membrane Potential", "Event Detection"
        expected_call_count = len(
            {r["analysis_type"] for r in mock_main_window.saved_analysis_results}
        )

        # Mock the pandas DataFrame.to_csv to avoid actual file writes
        # and mock QMessageBox to avoid GUI blocking
        with patch("pandas.DataFrame.to_csv") as mock_to_csv, \
                patch.object(QtWidgets.QMessageBox, 'information'):
            # Export the selected results
            exporter_tab._do_export_analysis_results()

            # Verify to_csv was called once per analysis type
            assert mock_to_csv.call_count == expected_call_count, (
                f"Expected {expected_call_count} to_csv calls "
                f"(one per analysis type), got {mock_to_csv.call_count}"
            )

            # Every call should use index=False and na_rep=''
            for call in mock_to_csv.call_args_list:
                assert call[1].get("index") is False
                assert call[1].get("na_rep") == ""

            # Each call's first positional argument should be a path inside temp_dir
            for call in mock_to_csv.call_args_list:
                csv_filepath = call[0][0]
                assert pathlib.Path(temp_dir) == pathlib.Path(csv_filepath).parent


def test_get_selected_results_indices(exporter_tab):
    """Test the method to get selected indices from the table"""
    # Refresh the results first
    exporter_tab._refresh_analysis_results()

    # Select specific rows
    selection_model = exporter_tab.analysis_results_table.selectionModel()

    # Select row 0 and 2
    for row in [0, 2]:
        index = exporter_tab.analysis_results_table.model().index(row, 0)
        selection_model.select(
            index,
            QtCore.QItemSelectionModel.Select | QtCore.QItemSelectionModel.Rows
        )

    # Get selected indices
    indices = exporter_tab._get_selected_results_indices()

    # Check that we got the right indices
    assert len(indices) == 2
    assert 0 in indices
    assert 2 in indices
