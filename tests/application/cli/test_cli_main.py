"""Tests for synaptipy.application.cli.main — headless batch CLI."""

import json
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# _load_pipeline
# ---------------------------------------------------------------------------


def test_load_pipeline_list_form(tmp_path):
    from synaptipy.application.cli.main import _load_pipeline

    pl = [{"analysis": "evoked_responses"}]
    p = tmp_path / "pl.json"
    p.write_text(json.dumps(pl))
    result = _load_pipeline(p)
    assert result == pl


def test_load_pipeline_dict_form(tmp_path):
    from synaptipy.application.cli.main import _load_pipeline

    pl = [{"analysis": "evoked_responses"}]
    p = tmp_path / "pl.json"
    p.write_text(json.dumps({"pipeline": pl, "extra": 1}))
    result = _load_pipeline(p)
    assert result == pl


def test_load_pipeline_empty_list_raises(tmp_path):
    from synaptipy.application.cli.main import _load_pipeline

    p = tmp_path / "pl.json"
    p.write_text(json.dumps([]))
    with pytest.raises(ValueError, match="non-empty list"):
        _load_pipeline(p)


def test_load_pipeline_not_list_raises(tmp_path):
    from synaptipy.application.cli.main import _load_pipeline

    p = tmp_path / "pl.json"
    p.write_text(json.dumps({"pipeline": None}))
    with pytest.raises(ValueError, match="non-empty list"):
        _load_pipeline(p)


def test_load_pipeline_missing_analysis_key_raises(tmp_path):
    from synaptipy.application.cli.main import _load_pipeline

    p = tmp_path / "pl.json"
    p.write_text(json.dumps([{"params": {}}]))
    with pytest.raises(ValueError, match="'analysis' key"):
        _load_pipeline(p)


# ---------------------------------------------------------------------------
# build_parser
# ---------------------------------------------------------------------------


def test_build_parser_returns_parser():
    from synaptipy.application.cli.main import build_parser

    parser = build_parser()
    assert parser is not None


def test_build_parser_version(capsys):
    from synaptipy.application.cli.main import build_parser

    parser = build_parser()
    with pytest.raises(SystemExit) as exc_info:
        parser.parse_args(["--version"])
    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert "synaptipy" in captured.out


def test_build_parser_list_analyses_subcommand():
    from synaptipy.application.cli.main import build_parser

    parser = build_parser()
    args = parser.parse_args(["list-analyses"])
    assert args.command == "list-analyses"


def test_build_parser_run_subcommand(tmp_path):
    from synaptipy.application.cli.main import build_parser

    p = tmp_path / "pl.json"
    p.write_text("[]")
    parser = build_parser()
    args = parser.parse_args(["run", "rec.abf", "--pipeline", str(p), "--output", "out.csv"])
    assert args.command == "run"
    assert args.files == ["rec.abf"]
    assert args.pipeline == p
    assert args.output == Path("out.csv")


def test_build_parser_run_with_channel_flag(tmp_path):
    from synaptipy.application.cli.main import build_parser

    p = tmp_path / "pl.json"
    p.write_text("[]")
    parser = build_parser()
    args = parser.parse_args(
        [
            "run",
            "rec.abf",
            "--pipeline",
            str(p),
            "--output",
            "out.csv",
            "--channel",
            "CH1",
        ]
    )
    assert args.channel == ["CH1"]


# ---------------------------------------------------------------------------
# _list_analyses
# ---------------------------------------------------------------------------


def test_list_analyses_runs_without_error(capsys):
    from synaptipy.application.cli.main import _list_analyses

    rc = _list_analyses()
    assert rc == 0
    captured = capsys.readouterr()
    # At least one analysis should be printed
    assert len(captured.out.strip()) > 0


# ---------------------------------------------------------------------------
# main — list-analyses subcommand
# ---------------------------------------------------------------------------


def test_main_list_analyses(capsys):
    from synaptipy.application.cli.main import main

    rc = main(["list-analyses"])
    assert rc == 0
    assert len(capsys.readouterr().out.strip()) > 0


# ---------------------------------------------------------------------------
# _write_provenance
# ---------------------------------------------------------------------------


def test_write_provenance_creates_file(tmp_path):
    import argparse

    from synaptipy.application.cli.main import _write_provenance

    output = tmp_path / "results.csv"
    args = argparse.Namespace(
        files=["a.abf"],
        pipeline=Path("pl.json"),
        channel=None,
        max_workers=1,
        cross_file_average=False,
    )
    pipeline = [{"analysis": "evoked_responses"}]
    _write_provenance(output, args, pipeline)
    prov = tmp_path / "results_provenance.json"
    assert prov.exists()
    data = json.loads(prov.read_text())
    assert data["command"] == "synaptipy-batch run"
    assert data["pipeline"] == pipeline


# ---------------------------------------------------------------------------
# _run_batch — missing input file path
# ---------------------------------------------------------------------------


def test_run_batch_missing_file(tmp_path, capsys):
    import argparse

    from synaptipy.application.cli.main import _run_batch

    pl_path = tmp_path / "pl.json"
    pl_path.write_text(json.dumps([{"analysis": "evoked_responses"}]))

    args = argparse.Namespace(
        files=[str(tmp_path / "nonexistent.abf")],
        pipeline=pl_path,
        output=tmp_path / "out.csv",
        channel=None,
        max_workers=1,
        cross_file_average=False,
    )
    rc = _run_batch(args)
    assert rc == 2
    captured = capsys.readouterr()
    assert "not found" in captured.err


def test_run_batch_success_path(tmp_path, capsys):
    """Lines 51-63: successful run_batch writes CSV and returns 0."""
    import argparse
    from unittest.mock import MagicMock, patch

    import pandas as pd

    from synaptipy.application.cli.main import _run_batch

    pl_path = tmp_path / "pl.json"
    pl_path.write_text(json.dumps([{"analysis": "rmp_analysis"}]))

    # Create a real (empty) file so the missing-file check passes
    rec_file = tmp_path / "rec.abf"
    rec_file.write_bytes(b"")

    out_path = tmp_path / "out.csv"
    args = argparse.Namespace(
        files=[str(rec_file)],
        pipeline=pl_path,
        output=out_path,
        channel=None,
        max_workers=1,
        cross_file_average=False,
    )

    fake_df = pd.DataFrame([{"analysis": "rmp_analysis", "value": -65.0}])
    with patch("synaptipy.application.cli.main.BatchAnalysisEngine") as mock_cls:
        mock_engine = MagicMock()
        mock_cls.return_value = mock_engine
        mock_engine.run_batch.return_value = fake_df
        rc = _run_batch(args)

    assert rc == 0
    assert out_path.exists()
    captured = capsys.readouterr()
    assert "rows" in captured.out
