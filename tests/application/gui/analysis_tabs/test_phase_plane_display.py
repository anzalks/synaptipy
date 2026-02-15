
import pytest
from unittest.mock import MagicMock
from PySide6 import QtWidgets
from Synaptipy.application.gui.analysis_tabs.phase_plane_tab import PhasePlaneTab

@pytest.fixture
def app():
    if not QtWidgets.QApplication.instance():
        return QtWidgets.QApplication([])
    return QtWidgets.QApplication.instance()

def test_phase_plane_result_display(app):
    """Verify PhasePlaneTab result display operates without NameError."""
    mock_neo = MagicMock()
    tab = PhasePlaneTab(mock_neo)
    
    # Mock results
    results = {
        "result": {
            "threshold_v": -45.0,
            "max_dvdt": 120.0,
            "voltage": [1, 2, 3],
            "dvdt": [1, 2, 3],
            "threshold_dvdt": 10.0
        }
    }
    
    # This should not raise NameError
    tab._display_analysis_results(results)
    
    # Verify table population
    assert tab.results_table.rowCount() == 2
    assert tab.results_table.item(0, 0).text() == "Threshold"
    assert tab.results_table.item(0, 1).text() == "-45.00 mV"

if __name__ == "__main__":
    pytest.main([__file__])
