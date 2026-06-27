# tests/infrastructure/test_prism_export.py
# -*- coding: utf-8 -*-
"""
Tests for CSVExporter.export_to_prism_format.

Covers:
- Basic happy path: two groups with equal N
- Unequal-N groups are padded with empty strings
- Metric not found in any row returns False
- Empty results list returns False
- group_by_key fallback chain (group -> source_file_name)
- Nested metrics dict is flattened correctly
- Provenance JSON is written alongside the CSV
- Output CSV columns match group names
"""

from __future__ import annotations

import csv
import json

import pytest

from synaptipy.infrastructure.exporters.csv_exporter import CSVExporter

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def exporter() -> CSVExporter:
    return CSVExporter()


def _make_results(groups_and_vals: dict[str, list[float]], metric: str = "rin_mohm") -> list[dict]:
    """Build minimal result rows for export testing."""
    rows = []
    for grp, vals in groups_and_vals.items():
        for v in vals:
            rows.append({"Condition": grp, metric: v, "source_file_name": f"{grp}_cell.abf"})
    return rows


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


class TestPrismExportHappyPath:
    def test_equal_groups_written(self, exporter, tmp_path):
        results = _make_results({"WT": [100.0, 110.0, 105.0], "KO": [80.0, 85.0, 90.0]})
        base = tmp_path / "out.csv"
        ok = exporter.export_to_prism_format(results, base, metric="rin_mohm")
        assert ok is True

    def test_output_file_exists(self, exporter, tmp_path):
        results = _make_results({"WT": [1.0, 2.0], "KO": [3.0, 4.0]})
        base = tmp_path / "out.csv"
        exporter.export_to_prism_format(results, base, metric="rin_mohm")
        prism_file = tmp_path / "out_prism_rin_mohm.csv"
        assert prism_file.exists()

    def test_columns_are_group_names(self, exporter, tmp_path):
        results = _make_results({"WT": [1.0], "KO": [2.0]})
        base = tmp_path / "out.csv"
        exporter.export_to_prism_format(results, base, metric="rin_mohm")
        prism_file = tmp_path / "out_prism_rin_mohm.csv"
        with open(prism_file, newline="") as fh:
            reader = csv.reader(fh)
            header = next(reader)
        assert "WT" in header
        assert "KO" in header

    def test_values_are_correct(self, exporter, tmp_path):
        results = _make_results({"A": [10.0, 20.0], "B": [30.0, 40.0]})
        base = tmp_path / "out.csv"
        exporter.export_to_prism_format(results, base, metric="rin_mohm")
        prism_file = tmp_path / "out_prism_rin_mohm.csv"
        with open(prism_file, newline="") as fh:
            reader = csv.DictReader(fh)
            rows = list(reader)
        a_vals = [float(r["A"]) for r in rows if r["A"] != ""]
        assert sorted(a_vals) == pytest.approx([10.0, 20.0], rel=1e-3)


# ---------------------------------------------------------------------------
# Unequal N padding
# ---------------------------------------------------------------------------


class TestPrismExportPadding:
    def test_unequal_groups_padded(self, exporter, tmp_path):
        results = _make_results({"WT": [1.0, 2.0, 3.0], "KO": [4.0]})
        base = tmp_path / "out.csv"
        exporter.export_to_prism_format(results, base, metric="rin_mohm")
        prism_file = tmp_path / "out_prism_rin_mohm.csv"
        with open(prism_file, newline="") as fh:
            reader = csv.DictReader(fh)
            rows = list(reader)
        # All rows have both columns (even if padded with empty)
        assert all("WT" in r and "KO" in r for r in rows)
        assert len(rows) == 3  # max N is 3

    def test_padding_is_empty_string(self, exporter, tmp_path):
        results = _make_results({"WT": [1.0, 2.0], "KO": [9.0]})
        base = tmp_path / "out.csv"
        exporter.export_to_prism_format(results, base, metric="rin_mohm")
        prism_file = tmp_path / "out_prism_rin_mohm.csv"
        with open(prism_file, newline="") as fh:
            reader = csv.DictReader(fh)
            rows = list(reader)
        # Second row, KO column should be empty (padded)
        assert rows[1]["KO"] == ""


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestPrismExportEdgeCases:
    def test_empty_results_returns_false(self, exporter, tmp_path):
        base = tmp_path / "out.csv"
        ok = exporter.export_to_prism_format([], base, metric="rin_mohm")
        assert ok is False

    def test_metric_not_found_returns_false(self, exporter, tmp_path):
        results = [{"Condition": "WT", "rin_mohm": 100.0}]
        base = tmp_path / "out.csv"
        ok = exporter.export_to_prism_format(results, base, metric="nonexistent_metric")
        assert ok is False

    def test_nested_metrics_dict_flattened(self, exporter, tmp_path):
        """Rows with metrics nested under 'metrics' key should be handled."""
        results = [
            {"Condition": "WT", "metrics": {"event_count": 5}},
            {"Condition": "KO", "metrics": {"event_count": 3}},
        ]
        base = tmp_path / "out.csv"
        ok = exporter.export_to_prism_format(results, base, metric="event_count")
        assert ok is True

    def test_group_fallback_to_group_key(self, exporter, tmp_path):
        """When 'Condition' absent, falls back to 'group'."""
        results = [
            {"group": "WT", "rin_mohm": 100.0},
            {"group": "KO", "rin_mohm": 80.0},
        ]
        base = tmp_path / "out.csv"
        ok = exporter.export_to_prism_format(results, base, metric="rin_mohm", group_by_key="Condition")
        assert ok is True
        prism_file = tmp_path / "out_prism_rin_mohm.csv"
        with open(prism_file, newline="") as fh:
            reader = csv.reader(fh)
            header = next(reader)
        assert "WT" in header or "KO" in header

    def test_non_float_values_skipped(self, exporter, tmp_path):
        """Rows where metric cannot be cast to float are silently dropped."""
        results = [
            {"Condition": "WT", "rin_mohm": 100.0},
            {"Condition": "WT", "rin_mohm": "not_a_number"},
            {"Condition": "KO", "rin_mohm": 80.0},
        ]
        base = tmp_path / "out.csv"
        ok = exporter.export_to_prism_format(results, base, metric="rin_mohm")
        assert ok is True
        prism_file = tmp_path / "out_prism_rin_mohm.csv"
        with open(prism_file, newline="") as fh:
            reader = csv.DictReader(fh)
            rows = list(reader)
        wt_vals = [r["WT"] for r in rows if r["WT"] != ""]
        assert len(wt_vals) == 1  # only the numeric value survived

    def test_metric_with_slash_in_name_safe_filename(self, exporter, tmp_path):
        """Metrics with '/' in the name must produce a safe file name."""
        results = [{"Condition": "WT", "amp/pA": 5.0}]
        base = tmp_path / "out.csv"
        ok = exporter.export_to_prism_format(results, base, metric="amp/pA")
        assert ok is True
        # File name uses '-' instead of '/'
        safe = tmp_path / "out_prism_amp-pA.csv"
        assert safe.exists()


# ---------------------------------------------------------------------------
# Provenance
# ---------------------------------------------------------------------------


class TestPrismExportProvenance:
    def test_provenance_json_written(self, exporter, tmp_path):
        results = _make_results({"WT": [1.0], "KO": [2.0]})
        base = tmp_path / "out.csv"
        exporter.export_to_prism_format(results, base, metric="rin_mohm")
        prov = tmp_path / "out_prism_rin_mohm_provenance.json"
        assert prov.exists()

    def test_provenance_contains_metric(self, exporter, tmp_path):
        results = _make_results({"WT": [1.0]})
        base = tmp_path / "out.csv"
        exporter.export_to_prism_format(results, base, metric="rin_mohm")
        prov = tmp_path / "out_prism_rin_mohm_provenance.json"
        data = json.loads(prov.read_text())
        assert data["analysis_config"]["metric"] == "rin_mohm"
