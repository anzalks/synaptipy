"""File-level checks for batch-result exports."""

import json
import zipfile
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest
from PySide6 import QtWidgets

from synaptipy.application.gui.batch_dialog import BatchAnalysisDialog


@pytest.fixture
def batch_dialog_stub():
    """Supply only the dialog state consumed by the export routines."""
    return SimpleNamespace(
        result_df=pd.DataFrame(
            {
                "file_name": ["recording.abf"],
                "amplitude": [42.0],
                "trace": [np.array([1.0, 2.0])],
                "_raw_trace": [np.array([1.0, 2.0])],
            }
        ),
        files=["recording.abf"],
        pipeline_steps=[{"analysis": "Amplitude"}],
        _write_csv_with_header=MagicMock(),
    )


@pytest.mark.parametrize("suffix", [".csv", ".xlsx", ".json"])
def test_batch_results_export_to_selected_format(batch_dialog_stub, tmp_path, suffix):
    """Batch exports create usable CSV, Excel, and JSON outputs."""
    output_path = tmp_path / f"batch_results{suffix}"
    with (
        patch.object(QtWidgets.QFileDialog, "getSaveFileName", return_value=(str(output_path), "")),
        patch.object(QtWidgets.QMessageBox, "information"),
        patch.object(QtWidgets.QMessageBox, "critical") as critical,
    ):
        BatchAnalysisDialog._on_export(batch_dialog_stub)

    critical.assert_not_called()
    if suffix == ".csv":
        batch_dialog_stub._write_csv_with_header.assert_called_once()
        exported_df = batch_dialog_stub._write_csv_with_header.call_args.args[0]
        assert "_raw_trace" not in exported_df.columns
    elif suffix == ".xlsx":
        assert output_path.is_file()
        with zipfile.ZipFile(output_path) as archive:
            worksheet = archive.read("xl/worksheets/sheet1.xml").decode("utf-8")
        assert "file_name" in worksheet
        assert "amplitude" in worksheet
        assert "_raw_trace" not in worksheet
    else:
        assert output_path.is_file()
        assert json.loads(output_path.read_text(encoding="utf-8"))[0]["trace"] == [1.0, 2.0]


def test_batch_csv_export_writes_reproducibility_header(tmp_path):
    """CSV results retain the batch metadata required for reproducibility."""
    output_path = tmp_path / "batch_results.csv"
    dialog_stub = SimpleNamespace(files=["one.abf", "two.abf"], pipeline_steps=[{"analysis": "Amplitude"}])

    BatchAnalysisDialog._write_csv_with_header(
        dialog_stub,
        pd.DataFrame({"selected_trial_indices": ["0,2"], "amplitude": [42.0]}),
        str(output_path),
    )

    content = output_path.read_text(encoding="utf-8")
    assert "# Files processed: 2" in content
    assert "# Pipeline: Amplitude" in content
    assert "selected_trial_indices,amplitude" in content
