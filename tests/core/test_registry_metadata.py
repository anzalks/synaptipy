import pytest
from Synaptipy.core.analysis.registry import AnalysisRegistry


# Save and restore registry around each test to ensure isolation
# without losing module-level @register decorations for other tests
@pytest.fixture(autouse=True)
def clear_registry():
    saved_registry = dict(AnalysisRegistry._registry)
    saved_metadata = dict(AnalysisRegistry._metadata)
    AnalysisRegistry._registry.clear()
    AnalysisRegistry._metadata.clear()
    yield
    AnalysisRegistry._registry.clear()
    AnalysisRegistry._metadata.clear()
    AnalysisRegistry._registry.update(saved_registry)
    AnalysisRegistry._metadata.update(saved_metadata)


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
    # Re-import to ensure registration runs after clear()
    import importlib
    import Synaptipy.core.analysis.spike_analysis as sa
    importlib.reload(sa)

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


# ---------------------------------------------------------------------------
# Regression test for Windows analysis-tab population bug
# ---------------------------------------------------------------------------
# Root cause: analyser_tab._load_analysis_tabs() called
#   ``from Synaptipy.core.analysis.registry import AnalysisRegistry``
# which only imports the registry *class* — it does NOT import the package
# __init__.py, so the ``from . import basic_features`` (etc.) lines in
# core/analysis/__init__.py were never executed and the registry remained
# empty.  On macOS the batch engine happened to be imported earlier via a
# different path, masking the bug.
# The fix imports ``Synaptipy.core.analysis`` (the full package) immediately
# before calling list_registered().
# ---------------------------------------------------------------------------

EXPECTED_BUILTIN_ANALYSES = {
    "rmp_analysis",
    "spike_detection",
    "rin_analysis",
    "tau_analysis",
    "iv_curve_analysis",
    "sag_ratio_analysis",
    "event_detection_threshold",
    "event_detection_deconvolution",
    "event_detection_baseline_peak",
    "phase_plane_analysis",
    "burst_analysis",
    "excitability_analysis",
    "capacitance_analysis",
    "optogenetic_sync",
    "train_dynamics",
}


def test_full_package_import_populates_registry():
    """Regression test: importing only registry.py leaves the registry empty;
    the full Synaptipy.core.analysis package must be imported to trigger all
    @AnalysisRegistry.register decorators.

    The autouse clear_registry fixture has already cleared the registry before
    this test runs.  We reload every built-in analysis submodule explicitly to
    re-execute their decorators (the modules are already in sys.modules so a
    plain import is a no-op), then verify all 15 expected analyses are present.
    This matches the mechanism in startup_manager._begin_loading() and in
    analyser_tab._load_analysis_tabs() added to fix the Windows bug.
    """
    import importlib
    import Synaptipy.core.analysis.basic_features as m0
    import Synaptipy.core.analysis.spike_analysis as m1
    import Synaptipy.core.analysis.intrinsic_properties as m2
    import Synaptipy.core.analysis.event_detection as m3
    import Synaptipy.core.analysis.phase_plane as m4
    import Synaptipy.core.analysis.burst_analysis as m5
    import Synaptipy.core.analysis.excitability as m6
    import Synaptipy.core.analysis.capacitance as m7
    import Synaptipy.core.analysis.optogenetics as m8
    import Synaptipy.core.analysis.train_dynamics as m9

    for module in (m0, m1, m2, m3, m4, m5, m6, m7, m8, m9):
        importlib.reload(module)

    registered = set(AnalysisRegistry.list_registered())
    missing = EXPECTED_BUILTIN_ANALYSES - registered
    assert not missing, (
        f"Registry is missing built-in analyses after reloading all analysis modules.\n"
        f"Missing: {sorted(missing)}\n"
        f"Present: {sorted(registered)}\n"
        "This is the Windows regression: importing only registry.py is not enough."
    )


def test_registry_only_import_does_not_populate():
    """Verify that importing only the registry module (as the old analyser_tab code did)
    does NOT register any built-in analyses.  The autouse fixture already cleared the
    registry, so we just check it is still empty after a registry-only re-import."""
    import importlib
    import Synaptipy.core.analysis.registry as reg_mod
    importlib.reload(reg_mod)

    registered = AnalysisRegistry.list_registered()
    # Registry class itself never registers anything; only analysis modules do.
    # Any entries here were added by other tests that run before this fixture
    # clears — but the autouse fixture guarantees a clean slate.
    builtin_overlap = set(registered) & EXPECTED_BUILTIN_ANALYSES
    assert not builtin_overlap, (
        f"Expected empty registry after registry-only import, "
        f"but found built-in analyses: {sorted(builtin_overlap)}"
    )
