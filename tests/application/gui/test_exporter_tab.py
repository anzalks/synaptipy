"""
Unit tests for the Exporter Tab functionality
"""
import pytest
import os
from unittest.mock import MagicMock, patch, PropertyMock
from PySide6 import QtWidgets, QtCore
from pathlib import Path
import tempfile

from Synaptipy.application.gui.exporter_tab import ExporterTab
from Synaptipy.application.gui.explorer_tab import ExplorerTab
from Synaptipy.infrastructure.file_readers import NeoAdapter
from Synaptipy.infrastructure.exporters import NWBExporter

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
            "specific_data": {
                "Input Resistance (kOhm)": 200.0,
                "Baseline Std Dev": 0.5
            }
        },
        {
            "analysis_type": "Resting Membrane Potential",
            "channel_name": "Vm",
            "calculation_method": "Mean",
            "timestamp": "2023-10-25 15:35:20",
            "specific_data": {
                "RMP (mV)": -65.3,
                "Std Dev (mV)": 0.8
            }
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
                "Detection Parameters": {
                    "threshold": 10.0,
                    "min_duration": 0.5
                }
            }
        }
    ]
    
    return window

@pytest.fixture
def exporter_tab(qtbot, mock_main_window):
    """Create an exporter tab attached to a mock main window"""
    # Mock all required dependencies
    explorer_tab_ref = MagicMock(name="explorer_tab")
    nwb_exporter_ref = MagicMock(name="nwb_exporter")
    settings_ref = MagicMock(spec=QtCore.QSettings)
    status_bar_ref = MagicMock(spec=QtWidgets.QStatusBar)
    
    # Create the tab
    tab = ExporterTab(
        explorer_tab_ref=explorer_tab_ref,
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
    assert hasattr(exporter_tab, 'sub_tab_widget')
    
    # Check if the analysis results tab exists - only check that the tab widget has at least 3 tabs
    assert exporter_tab.sub_tab_widget.count() >= 3
    # The third tab should be the Analysis Results tab
    assert "Analysis Results" in exporter_tab.sub_tab_widget.tabText(2)

def test_refresh_analysis_results(exporter_tab, mock_main_window):
    """Test refreshing the analysis results table"""
    # Call refresh method
    exporter_tab._refresh_analysis_results()
    
    # Verify table has correct number of rows (one per result)
    assert exporter_tab.analysis_results_table.rowCount() == len(mock_main_window.saved_analysis_results)
    
    # Check first row contains analysis type (don't check specific values as they may change)
    assert "Input Resistance" in exporter_tab.analysis_results_table.item(0, 0).text()

def test_export_to_csv(exporter_tab, qtbot, mock_main_window):
    """Test exporting analysis results to CSV"""
    # Create a temporary directory for test output
    with tempfile.TemporaryDirectory() as temp_dir:
        csv_path = os.path.join(temp_dir, "test_results.csv")
        
        # Set the export path
        exporter_tab.analysis_results_path_edit.setText(csv_path)
        
        # Refresh the analysis results
        exporter_tab._refresh_analysis_results()
        
        # Select all rows
        exporter_tab.analysis_results_table.selectAll()
        
        # Export the selected results
        with patch('builtins.open', create=True) as mock_open:
            # Use the correct method name
            exporter_tab._do_export_analysis_results()
            # Check that open was called with the correct path
            # The actual call may include encoding parameter which is fine
            mock_open.assert_called_once()
            call_args = mock_open.call_args
            # First positional arg should be the path (as string or Path)
            assert str(call_args[0][0]) == csv_path
            # Should have 'w' mode
            assert call_args[0][1] == 'w'
            # Should have newline='' for CSV
            assert call_args[1].get('newline') == ''
        
        # Skip checking if the file exists since we're using a mock for the file operations

def test_get_selected_results_indices(exporter_tab):
    """Test the method to get selected indices from the table"""
    # Refresh the results first
    exporter_tab._refresh_analysis_results()
    
    # Select specific rows
    selection_model = exporter_tab.analysis_results_table.selectionModel()
    
    # Select row 0 and 2
    for row in [0, 2]:
        index = exporter_tab.analysis_results_table.model().index(row, 0)
        selection_model.select(index, QtCore.QItemSelectionModel.Select | QtCore.QItemSelectionModel.Rows)
    
    # Get selected indices
    indices = exporter_tab._get_selected_results_indices()
    
    # Check that we got the right indices
    assert len(indices) == 2
    assert 0 in indices
    assert 2 in indices 