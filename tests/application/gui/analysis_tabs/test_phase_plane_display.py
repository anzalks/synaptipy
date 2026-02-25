"""
Tests for Phase Plane analysis via MetadataDrivenAnalysisTab.

Validates that the generic metadata-driven tab correctly handles
popup phase-plane plots and result display for phase plane analysis.
"""
import pytest
from unittest.mock import MagicMock
from Synaptipy.application.gui.analysis_tabs.metadata_driven import MetadataDrivenAnalysisTab

# Ensure the analysis modules are imported so registrations are active
import Synaptipy.core.analysis  # noqa: F401


@pytest.fixture(scope="session")
def phase_plane_tab(qapp):
    """Session-scoped to prevent PlotItem teardown/recreation crashes.

    Creating/destroying a MetadataDrivenAnalysisTab per-test (or even
    per-module) crashes with PySide6 6.8+ in offscreen mode because
    PlotItem.ctrl teardown corrupts a Qt global registry.  Pinning to
    session scope avoids all inter-module teardown.
    """
    mock_neo = MagicMock()
    return MetadataDrivenAnalysisTab(
        analysis_name="phase_plane_analysis",
        neo_adapter=mock_neo,
    )


def test_phase_plane_result_display(phase_plane_tab):
    """Verify MetadataDrivenAnalysisTab result display for phase plane operates correctly."""
    tab = phase_plane_tab

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
