"""Regression test for the shipped protocol-aware batch example."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = ROOT / "examples" / "05_protocol_aware_batch.py"


def test_protocol_aware_batch_example_exports_provenance(tmp_path: Path) -> None:
    """The documented selected-trial workflow runs against bundled recordings."""
    spec = importlib.util.spec_from_file_location("protocol_aware_batch_example", EXAMPLE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.OUTPUT = tmp_path / "protocol_aware_batch_results.csv"

    module.main()

    assert module.OUTPUT.exists()
    result = pd.read_csv(module.OUTPUT)
    assert result.iloc[0]["protocol_family"] == "signal_only"
    assert result.iloc[0]["protocol_source"] == "manual"
    assert result.iloc[0]["protocol_status"] == "ready"
