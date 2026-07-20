# -*- coding: utf-8 -*-
"""Headless command-line entry point for reproducible Synaptipy batch runs."""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from synaptipy import __version__
from synaptipy.application.plugin_manager import PluginManager
from synaptipy.core.analysis.batch_engine import BatchAnalysisEngine


def _load_pipeline(path: Path) -> list:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        payload = payload.get("pipeline")
    if not isinstance(payload, list) or not payload:
        raise ValueError("Pipeline JSON must be a non-empty list or an object with a non-empty 'pipeline' list.")
    for index, task in enumerate(payload):
        if not isinstance(task, dict) or "analysis" not in task:
            raise ValueError(f"Pipeline task {index} must be an object containing an 'analysis' key.")
    return payload


def _write_provenance(output_path: Path, args: argparse.Namespace, pipeline: list) -> None:
    provenance = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "synaptipy_version": __version__,
        "command": "synaptipy-batch run",
        "input_files": [str(Path(p)) for p in args.files],
        "pipeline_file": str(args.pipeline),
        "pipeline": pipeline,
        "channel_filter": args.channel,
        "max_workers": args.max_workers,
        "cross_file_average": args.cross_file_average,
    }
    path = output_path.with_name(output_path.stem + "_provenance.json")
    path.write_text(json.dumps(provenance, indent=2), encoding="utf-8")


def _run_batch(args: argparse.Namespace) -> int:
    pipeline = _load_pipeline(args.pipeline)
    files = [Path(p) for p in args.files]
    missing = [path for path in files if not path.exists()]
    if missing:
        for path in missing:
            print(f"Input file not found: {path}", file=sys.stderr)
        return 2

    engine = BatchAnalysisEngine(max_workers=args.max_workers)
    df = engine.run_batch(
        files,
        pipeline,
        channel_filter=args.channel,
        cross_file_average=args.cross_file_average,
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.output, index=False)
    _write_provenance(args.output, args, pipeline)
    print(f"Wrote {len(df)} rows to {args.output}")
    return 0


def _list_analyses() -> int:
    for name in sorted(BatchAnalysisEngine.list_available_analyses()):
        print(name)
    return 0


def _bootstrap_plugins_for_cli() -> None:
    """Load the same approved optional plugins used by the GUI.

    Plugin failures are diagnostic only: core analyses and every successfully
    imported plugin remain usable.  The GUI presents failures in a dialog;
    the headless CLI reports them to stderr instead.
    """
    for failure in PluginManager.load_plugins():
        print(f"Plugin not loaded: {failure.path.name}: {failure.reason}", file=sys.stderr)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Headless Synaptipy batch analysis CLI.")
    parser.add_argument("--version", action="version", version=f"synaptipy {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run a JSON analysis pipeline on one or more recordings.")
    run_parser.add_argument("files", nargs="+", help="Recording files to analyse.")
    run_parser.add_argument("--pipeline", required=True, type=Path, help="JSON file containing a pipeline list.")
    run_parser.add_argument("--output", required=True, type=Path, help="Destination CSV path.")
    run_parser.add_argument("--channel", action="append", help="Channel name or ID to include. Repeatable.")
    run_parser.add_argument("--max-workers", type=int, default=1, help="File-level worker processes.")
    run_parser.add_argument(
        "--cross-file-average", action="store_true", help="Pool trials across files before analysis."
    )
    run_parser.set_defaults(func=_run_batch)

    list_parser = subparsers.add_parser("list-analyses", help="Print registered analysis names.")
    list_parser.set_defaults(func=lambda _args: _list_analyses())
    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    _bootstrap_plugins_for_cli()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
