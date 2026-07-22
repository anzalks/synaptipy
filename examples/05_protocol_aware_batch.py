#!/usr/bin/env python3
"""Run a provenance-preserving selected-trial batch analysis.

The bundled recordings do not expose Neo command or TTL protocol evidence, so
this example makes the required review step explicit instead of inventing
automatic provenance.  With a recording that contains Neo evidence, inspect
``recording.metadata['recorded_protocol_evidence']`` in the Protocol Map before
creating the reviewed analysis assignment.
"""

from __future__ import annotations

from pathlib import Path

from synaptipy.core.analysis.batch_engine import BatchAnalysisEngine
from synaptipy.core.protocols import ProtocolAssignment, ProtocolSource
from synaptipy.infrastructure.file_readers.neo_adapter import NeoAdapter

ROOT = Path(__file__).resolve().parent
DATA_FILES = sorted((ROOT / "data").glob("*.abf"))[:3]
OUTPUT = Path("protocol_aware_batch_results.csv")


def reviewed_recordings():
    """Load bundled traces and add the reviewed signal-only assignment used here."""
    adapter = NeoAdapter()
    recordings = []
    for path in DATA_FILES:
        recording = adapter.read_recording(path)
        evidence = recording.metadata.get("recorded_protocol_evidence")
        print(f"{path.name}: recorded protocol evidence = {bool(evidence)}")
        trial_count = max((channel.num_trials for channel in recording.channels.values()), default=0)
        for trial_index in range(trial_count):
            recording.protocol_map.add(
                ProtocolAssignment(
                    "signal_only",
                    (trial_index,),
                    source=ProtocolSource.MANUAL,
                    label="Reviewed baseline segment for example batch analysis",
                    verified=True,
                )
            )
        recordings.append(recording)
    return recordings


def main() -> None:
    """Run one selected sweep per file and export provenance with the metrics."""
    if not DATA_FILES:
        raise FileNotFoundError("No bundled ABF files were found in examples/data.")

    pipeline = [
        {
            "analysis": "rmp_analysis",
            "scope": "selected_trials_average",
            "params": {"trial_indices": "0", "baseline_start": 0.0, "baseline_end": 0.1},
        }
    ]
    results = BatchAnalysisEngine(max_workers=1).run_batch(reviewed_recordings(), pipeline, cross_file_average=True)
    columns = [
        column
        for column in ("file_name", "rmp_mv", "protocol_family", "protocol_source", "protocol_status")
        if column in results
    ]
    print(results[columns].to_string(index=False))
    results.to_csv(OUTPUT, index=False)
    print(f"Wrote {OUTPUT} with metrics and protocol provenance.")


if __name__ == "__main__":
    main()
