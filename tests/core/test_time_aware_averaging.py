"""Scientific-safety tests for canonical trial averaging and QC provenance."""

from pathlib import Path
from unittest.mock import MagicMock

import numpy as np

from synaptipy.core.analysis.batch_engine import BatchAnalysisEngine
from synaptipy.core.analysis.registry import AnalysisRegistry
from synaptipy.core.averaging import compute_time_aligned_average
from synaptipy.core.data_model import Channel, Recording


def test_time_aware_average_interpolates_and_reports_contributor_counts():
    """Different valid sampling grids align on time rather than array index."""
    result = compute_time_aligned_average(
        [np.array([0.0, 1.0, 2.0]), np.array([0.0, 2.0])],
        [np.array([0.0, 0.5, 1.0]), np.array([0.0, 1.0])],
        trial_indices=[3, 7],
    )

    assert result.included_indices == [3, 7]
    assert np.allclose(result.time, [0.0, 0.5, 1.0])
    assert np.allclose(result.data, [0.0, 1.0, 2.0])
    assert np.array_equal(result.contributors_per_sample, [2, 2, 2])


def test_time_aware_average_excludes_invalid_and_manually_rejected_trials():
    """Invalid and manually rejected sweeps remain auditable exclusions."""
    result = compute_time_aligned_average(
        [np.array([1.0, 1.0]), np.array([np.nan, 2.0]), np.array([3.0, 3.0])],
        [np.array([0.0, 1.0]), np.array([0.0, 1.0]), np.array([0.0, 1.0])],
        trial_indices=[0, 1, 2],
        manually_excluded=[2],
    )

    assert result.included_indices == [0]
    assert [decision.reason for decision in result.decisions if not decision.included] == [
        "trace contains non-finite values",
        "manual exclusion",
    ]


def test_batch_average_exports_shared_qc_provenance():
    """Batch averages expose the canonical eligibility summary in result rows."""
    analysis_name = "_time_aware_average_qc_test"
    AnalysisRegistry.register(analysis_name, label="Time average QC", ui_params=[])(
        lambda data, time, sampling_rate, **kwargs: {"mean": float(np.mean(data))}
    )
    recording = Recording(Path("qc.abf"))
    recording.channels = {
        "Vm": Channel(
            "Vm",
            "Vm",
            "mV",
            1_000.0,
            [np.array([1.0, 1.0]), np.array([np.nan, 2.0])],
        )
    }
    engine = BatchAnalysisEngine()
    engine.neo_adapter.read_recording = MagicMock(return_value=recording)

    result = engine.run_batch([Path("qc.abf")], [{"analysis": analysis_name, "scope": "average", "params": {}}])

    assert result.iloc[0]["qc_included_trial_indices"] == "0"
    assert result.iloc[0]["qc_excluded_trial_indices"] == "1"
    assert result.iloc[0]["qc_excluded_trial_count"] == 1
    AnalysisRegistry._registry.pop(analysis_name, None)
    AnalysisRegistry._metadata.pop(analysis_name, None)
    AnalysisRegistry._original_metadata.pop(analysis_name, None)
