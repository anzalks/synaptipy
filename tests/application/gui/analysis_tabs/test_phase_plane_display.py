"""
Tests for Phase Plane analysis via MetadataDrivenAnalysisTab.

Validates that the generic metadata-driven tab correctly handles
popup phase-plane plots and result display for phase plane analysis.
"""
import pytest
from unittest.mock import MagicMock
from PySide6 import QtWidgets
from Synaptipy.application.gui.analysis_tabs.metadata_driven import MetadataDrivenAnalysisTab

# Ensure the analysis modules are imported so registrations are active
import Synaptipy.core.analysis  # noqa: F401


@pytest.fixture
def app():
    if not QtWidgets.QApplication.instance():
        return QtWidgets.QApplication([])
    return QtWidgets.QApplication.instance()


def test_phase_plane_result_display(app):
    """Verify MetadataDrivenAnalysisTab result display for phase plane operates correctly."""
    mock_neo = MagicMock()
    tab = MetadataDrivenAnalysisTab(
        analysis_name="phase_plane_analysis",
        neo_adapter=mock_neo,
    )

    # Mock results
    results = {
        "result": {
            "threshold_v": -45.0,
            "max_dvdt": 120.0,
            "voltage": [1, 2, 3],
            "dvdt": [1, 2, 3],
            "threshold_dvdt": 10.0,
        }
    }

    # This should not raise errors
    tab._display_analysis_results(results)

    # Verify table was populated (generic display shows all keys)
    assert tab.results_table.rowCount() > 0


if __name__ == "__main__":
    pytest.main([__file__])
