# -*- coding: utf-8 -*-
"""Tests for CSVExporter."""

import json

import numpy as np
import pytest

from Synaptipy.core.data_model import Channel, Recording
from Synaptipy.infrastructure.exporters.csv_exporter import (
    CSVExporter,
    _build_tidy_row,
    _get_dependency_versions,
    _sanitize_csv_value,
    _tidy_get_meta,
    _tidy_row_to_long,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def simple_recording(tmp_path):
    rec = Recording(source_file=tmp_path / "test.abf")
    rec.sampling_rate = 1000.0
    rec.t_start = 0.0
    rec.duration = 0.1
    n = 100
    data = np.linspace(-65.0, -60.0, n)
    ch = Channel(id="0", name="Vm", units="mV", sampling_rate=1000.0, data_trials=[data])
    ch.t_start = 0.0
    rec.channels = {"0": ch}
    return rec


@pytest.fixture
def exporter():
    return CSVExporter()


@pytest.fixture
def simple_results():
    return [
        {
            "analysis_type": "rmp",
            "source_file_name": "test.abf",
            "channel_id": "0",
            "channel_name": "Vm",
            "trial_index_used": 0,
            "rmp_mv": -65.3,
        }
    ]


# ---------------------------------------------------------------------------
# _get_dependency_versions
# ---------------------------------------------------------------------------


def test_get_dependency_versions_returns_dict():
    versions = _get_dependency_versions()
    assert isinstance(versions, dict)
    assert "numpy" in versions
    # numpy is always installed
    assert versions["numpy"] != "unknown"


# ---------------------------------------------------------------------------
# _build_tidy_row
# ---------------------------------------------------------------------------


def test_build_tidy_row_scalar_metrics():
    flat = {"rmp_mv": -65.0, "rin_mohm": 100.0}
    rows = _build_tidy_row(flat, "f.abf", "ctrl", 0, "Vm", "rmp", "mV")
    metrics = {r["Metric"] for r in rows}
    assert "rmp_mv" in metrics
    assert "rin_mohm" in metrics


def test_build_tidy_row_skips_metadata_keys():
    flat = {"file": "f.abf", "rmp_mv": -65.0}
    rows = _build_tidy_row(flat, "f.abf", "ctrl", 0, "Vm", "rmp", "mV")
    metrics = {r["Metric"] for r in rows}
    assert "file" not in metrics


def test_build_tidy_row_skips_private_keys():
    flat = {"_debug": "hidden", "rmp_mv": -65.0}
    rows = _build_tidy_row(flat, "f.abf", "ctrl", 0, "Vm", "rmp", "mV")
    metrics = {r["Metric"] for r in rows}
    assert "_debug" not in metrics


def test_build_tidy_row_skips_list_values():
    flat = {"spike_times": [0.1, 0.2, 0.3], "rmp_mv": -65.0}
    rows = _build_tidy_row(flat, "f.abf", "ctrl", 0, "Vm", "rmp", "mV")
    metrics = {r["Metric"] for r in rows}
    assert "spike_times" not in metrics
    assert "rmp_mv" in metrics


def test_build_tidy_row_unit_map_applied():
    flat = {"rmp_mv": -65.0}
    rows = _build_tidy_row(flat, "f.abf", "ctrl", 0, "Vm", "rmp", "mV")
    assert rows[0]["Unit"] == "mV"


# ---------------------------------------------------------------------------
# _tidy_get_meta
# ---------------------------------------------------------------------------


def test_tidy_get_meta_first_key():
    row = {"file": "a.abf", "source_file_name": "b.abf"}
    assert _tidy_get_meta(row, ["file", "source_file_name"]) == "a.abf"


def test_tidy_get_meta_fallback():
    row = {"source_file_name": "b.abf"}
    assert _tidy_get_meta(row, ["file", "source_file_name"]) == "b.abf"


def test_tidy_get_meta_missing():
    assert _tidy_get_meta({}, ["missing_key"]) == ""


# ---------------------------------------------------------------------------
# _tidy_row_to_long
# ---------------------------------------------------------------------------


def test_tidy_row_to_long_basic():
    row = {
        "file": "f.abf",
        "group": "ctrl",
        "channel_name": "Vm",
        "trial_index": 0,
        "analysis_type": "rmp",
        "channel_units": "mV",
        "rmp_mv": -65.0,
    }
    long_rows = _tidy_row_to_long(row, ["file"], ["group"])
    assert len(long_rows) > 0
    assert long_rows[0]["File"] == "f.abf"
    assert long_rows[0]["Group"] == "ctrl"


def test_tidy_row_to_long_nested_metrics():
    """metrics dict is flattened before pivoting."""
    row = {
        "file": "f.abf",
        "analysis_type": "rin",
        "metrics": {"rin_mohm": 100.0},
    }
    long_rows = _tidy_row_to_long(row, ["file"], ["group"])
    metrics = {r["Metric"] for r in long_rows}
    assert "rin_mohm" in metrics


# ---------------------------------------------------------------------------
# CSVExporter.export_recording
# ---------------------------------------------------------------------------


def test_export_recording_creates_files(exporter, simple_recording, tmp_path):
    out_dir = tmp_path / "output"
    success, errors = exporter.export_recording(simple_recording, out_dir)
    assert success >= 1
    assert errors == 0
    csv_files = list(out_dir.glob("*.csv"))
    assert len(csv_files) >= 1


def test_export_recording_csv_content(exporter, simple_recording, tmp_path):
    out_dir = tmp_path / "out2"
    exporter.export_recording(simple_recording, out_dir)
    csv_file = next(out_dir.glob("*.csv"))
    lines = csv_file.read_text().splitlines()
    assert lines[0].startswith("Time")
    assert len(lines) > 2  # header + data rows


def test_export_recording_empty_channel_skipped(exporter, tmp_path):
    rec = Recording(source_file=tmp_path / "empty.abf")
    rec.sampling_rate = 1000.0
    rec.t_start = 0.0
    rec.duration = 0.0
    ch = Channel(id="0", name="Vm", units="mV", sampling_rate=1000.0, data_trials=[])
    rec.channels = {"0": ch}
    out_dir = tmp_path / "out_empty"
    success, errors = exporter.export_recording(rec, out_dir)
    assert success == 0
    assert errors == 0


# ---------------------------------------------------------------------------
# CSVExporter.export_analysis_results
# ---------------------------------------------------------------------------


def test_export_analysis_results_creates_csv(exporter, simple_results, tmp_path):
    out = tmp_path / "results.csv"
    ok = exporter.export_analysis_results(simple_results, out)
    assert ok is True
    assert out.exists()


def test_export_analysis_results_provenance_json(exporter, simple_results, tmp_path):
    out = tmp_path / "results.csv"
    exporter.export_analysis_results(simple_results, out)
    prov = tmp_path / "results_provenance.json"
    assert prov.exists()
    data = json.loads(prov.read_text())
    assert "synaptipy_version" in data
    assert "timestamp_utc" in data
    assert "rmp" in data["analysis_types"]


def test_export_analysis_results_empty_returns_false(exporter, tmp_path):
    out = tmp_path / "empty.csv"
    ok = exporter.export_analysis_results([], out)
    assert ok is False


def test_export_analysis_results_nested_dicts(exporter, tmp_path):
    results = [
        {
            "analysis_type": "event",
            "source_file_name": "f.abf",
            "summary_stats": {"count": 10, "frequency_hz": 5.0},
            "parameters": {"direction": "negative"},
        }
    ]
    out = tmp_path / "nested.csv"
    ok = exporter.export_analysis_results(results, out)
    assert ok is True
    content = out.read_text()
    assert "summary_stats.count" in content or "count" in content


def test_export_analysis_results_with_config(exporter, simple_results, tmp_path):
    out = tmp_path / "with_config.csv"
    cfg = {"param1": "value1"}
    ok = exporter.export_analysis_results(simple_results, out, analysis_config=cfg)
    assert ok is True
    prov = tmp_path / "with_config_provenance.json"
    data = json.loads(prov.read_text())
    assert data["analysis_config"] == cfg


# ---------------------------------------------------------------------------
# CSVExporter.export_tidy
# ---------------------------------------------------------------------------


def test_export_tidy_creates_csv(exporter, simple_results, tmp_path):
    out = tmp_path / "tidy.csv"
    ok = exporter.export_tidy(simple_results, out)
    assert ok is True
    assert out.exists()


def test_export_tidy_has_correct_columns(exporter, simple_results, tmp_path):
    out = tmp_path / "tidy2.csv"
    exporter.export_tidy(simple_results, out)
    lines = out.read_text().splitlines()
    header = lines[0]
    assert "Metric" in header
    assert "Value" in header
    assert "Unit" in header


def test_export_tidy_empty_returns_false(exporter, tmp_path):
    out = tmp_path / "empty_tidy.csv"
    ok = exporter.export_tidy([], out)
    assert ok is False


def test_export_tidy_provenance_written(exporter, simple_results, tmp_path):
    out = tmp_path / "tidy_prov.csv"
    exporter.export_tidy(simple_results, out)
    prov = tmp_path / "tidy_prov_provenance.json"
    assert prov.exists()


# ---------------------------------------------------------------------------
# _sanitize_csv_value
# ---------------------------------------------------------------------------


def test_sanitize_csv_value_none_returns_nan():
    import math

    result = _sanitize_csv_value(None)
    assert math.isnan(result)


def test_sanitize_csv_value_numpy_float32_no_wrapper():
    val = np.float32(-65.303456)
    result = _sanitize_csv_value(val)
    assert isinstance(result, float)
    result_str = str(result)
    assert "np.float32" not in result_str
    assert "float32" not in result_str


def test_sanitize_csv_value_numpy_float64_rounded():
    val = np.float64(0.6666666666666666)
    result = _sanitize_csv_value(val)
    assert isinstance(result, float)
    # Should be rounded to ~6 sig figs
    assert abs(result - 0.666667) < 1e-5


def test_sanitize_csv_value_plain_float_rounded():
    result = _sanitize_csv_value(15.099999999999891)
    assert isinstance(result, float)
    assert abs(result - 15.1) < 1e-4


def test_sanitize_csv_value_numpy_int():
    val = np.int32(42)
    result = _sanitize_csv_value(val)
    assert result == 42
    assert isinstance(result, int)


def test_sanitize_csv_value_list_of_numpy_floats_no_wrapper():
    lst = [np.float32(-65.3), np.float32(-64.1), np.float32(-66.0)]
    result = _sanitize_csv_value(lst)
    assert isinstance(result, str)
    assert "np.float32" not in result
    assert "float32" not in result


def test_sanitize_csv_value_numpy_array_no_wrapper():
    arr = np.array([-65.3, -64.1, -66.0], dtype=np.float32)
    result = _sanitize_csv_value(arr)
    assert isinstance(result, str)
    assert "np.float32" not in result
    assert "float32" not in result


def test_sanitize_csv_value_large_array_truncated():
    from Synaptipy.infrastructure.exporters.csv_exporter import _MAX_ARRAY_PREVIEW

    arr = list(range(_MAX_ARRAY_PREVIEW + 5))
    result = _sanitize_csv_value(arr)
    assert "total" in result
    assert str(_MAX_ARRAY_PREVIEW + 5) in result


def test_sanitize_csv_value_empty_list_returns_nan():
    import math

    result = _sanitize_csv_value([])
    assert math.isnan(result)


def test_sanitize_csv_value_zero():
    assert _sanitize_csv_value(0.0) == 0.0
    assert _sanitize_csv_value(np.float64(0.0)) == 0.0


# ---------------------------------------------------------------------------
# export_analysis_results — private key exclusion
# ---------------------------------------------------------------------------


def test_export_analysis_results_skips_private_keys(exporter, tmp_path):
    results = [
        {
            "analysis_type": "burst",
            "source_file_name": "f.abf",
            "_result_obj": object(),
            "burst_count": 3,
        }
    ]
    out = tmp_path / "private_keys.csv"
    ok = exporter.export_analysis_results(results, out)
    assert ok is True
    content = out.read_text()
    assert "_result_obj" not in content
    assert "burst_count" in content


def test_export_analysis_results_numpy_array_no_wrapper(exporter, tmp_path):
    results = [
        {
            "analysis_type": "rmp",
            "source_file_name": "f.abf",
            "baseline_voltages": [np.float32(-65.3), np.float32(-64.1)],
        }
    ]
    out = tmp_path / "array_clean.csv"
    ok = exporter.export_analysis_results(results, out)
    assert ok is True
    content = out.read_text()
    assert "np.float32" not in content
    assert "float32" not in content


def test_export_analysis_results_response_probability_pct_column(exporter, tmp_path):
    """response_probability_pct (not 'Response Probability (%)') is the canonical column name."""
    results = [
        {
            "analysis_type": "evoked_responses",
            "source_file_name": "f.abf",
            "module_used": "evoked_responses",
            "metrics": {
                "response_probability": 0.75,
                "response_probability_pct": 75.0,
            },
        }
    ]
    out = tmp_path / "resp_prob.csv"
    ok = exporter.export_analysis_results(results, out)
    assert ok is True
    content = out.read_text()
    assert "Response Probability (%)" not in content
