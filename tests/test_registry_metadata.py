import pytest
from Synaptipy.core.analysis.registry import AnalysisRegistry


# Clear registry before each test to ensure isolation
@pytest.fixture(autouse=True)
def clear_registry():
    AnalysisRegistry.clear()
    yield
    AnalysisRegistry.clear()


def test_register_with_metadata():
    """Test that metadata is correctly stored when registering a function."""

    @AnalysisRegistry.register(
        "test_analysis",
        ui_params=[
            {"name": "param1", "type": "float", "default": 1.0},
            {"name": "param2", "type": "choice", "choices": ["a", "b"]},
        ],
        description="A test analysis function",
    )
    def test_func(**kwargs):
        pass

    # Verify function is registered
    assert AnalysisRegistry.get_function("test_analysis") is not None

    # Verify metadata is stored
    metadata = AnalysisRegistry.get_metadata("test_analysis")
    assert metadata is not None
    assert "ui_params" in metadata
    assert len(metadata["ui_params"]) == 2
    assert metadata["ui_params"][0]["name"] == "param1"
    assert metadata["description"] == "A test analysis function"


def test_get_metadata_missing():
    """Test that get_metadata returns empty dict for unknown function."""
    metadata = AnalysisRegistry.get_metadata("non_existent_function")
    assert metadata == {}


def test_spike_detection_metadata():
    """Test that spike_detection has the correct metadata (integration test)."""
    # Re-import to ensure registration runs

    metadata = AnalysisRegistry.get_metadata("spike_detection")
    assert metadata is not None
    assert "ui_params" in metadata

    ui_params = metadata["ui_params"]
    param_names = [p["name"] for p in ui_params]
    assert "threshold" in param_names
    assert "refractory_period" in param_names

    # Check specific values for threshold
    threshold_param = next(p for p in ui_params if p["name"] == "threshold")
    assert threshold_param["type"] == "float"
    assert threshold_param["default"] == -20.0
