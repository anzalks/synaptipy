"""Tests for the sole runtime boundary between analyses and their consumers."""

from synaptipy.core.analysis.contracts import ANALYSIS_RESULT_SCHEMA_VERSION, AnalysisResult
from synaptipy.core.analysis.registry import AnalysisRegistry


def test_analysis_result_coerces_flat_metrics_without_losing_provenance():
    result = AnalysisResult.from_raw("example", {"amplitude": 12.5})

    assert result.analysis_name == "example"
    assert result.metrics == {"amplitude": 12.5}
    assert result.schema_version == ANALYSIS_RESULT_SCHEMA_VERSION
    assert result.export_row(file_name="example.abf") == {
        "amplitude": 12.5,
        "file_name": "example.abf",
        "analysis_result_schema_version": ANALYSIS_RESULT_SCHEMA_VERSION,
        "analysis_result_warnings": "",
    }


def test_analysis_result_preserves_explicit_schema_fields():
    result = AnalysisResult.from_raw(
        "ignored",
        {
            "analysis_name": "declared",
            "metrics": {"latency_ms": 2.1},
            "warnings": ["manual epoch"],
            "plot_payload": {"x": [0.0, 1.0]},
            "provenance": {"protocol_fingerprint": "abc"},
        },
    )

    assert result.as_dict()["analysis_name"] == "declared"
    assert result.export_row()["protocol_fingerprint"] == "abc"
    assert result.export_row()["analysis_result_warnings"] == "manual epoch"


def test_registry_execute_is_the_canonical_consumer_boundary():
    name = "contract_test_flat_analysis"

    @AnalysisRegistry.register(name)
    def _analysis(data, time, sampling_rate):
        return {"sample_count": len(data), "sampling_rate": sampling_rate}

    result = AnalysisRegistry.execute(name, [1, 2, 3], [0.0, 0.1, 0.2], 10.0)

    assert isinstance(result, AnalysisResult)
    assert result.metrics == {"sample_count": 3, "sampling_rate": 10.0}
