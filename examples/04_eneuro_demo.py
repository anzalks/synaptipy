#!/usr/bin/env python3
"""
SynaptiPy eNeuro Demo Script
============================
Demonstrates SynaptiPy's public BatchAnalysisEngine API on real patch-clamp
recordings from examples/data/.

Analysis is performed exclusively through the engine's registered pipeline —
no direct calls to internal analysis functions.

Outputs:
  paper/results/demo_results.csv — per-file/trial results table from the engine

This file is part of Synaptipy, licensed under the GNU Affero General Public
License v3.0. See the LICENSE file in the root of the repository for details.
"""

import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

DATA_DIR = REPO_ROOT / "examples" / "data"
OUT_DIR = REPO_ROOT / "paper" / "results"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ── Public API imports only ──────────────────────────────────────────────────
from synaptipy.core.analysis.batch_engine import BatchAnalysisEngine

# ── Files to analyse ─────────────────────────────────────────────────────────
FILES = [
    DATA_DIR / "2023_04_11_0018.abf",
    DATA_DIR / "2023_04_11_0019.abf",
    DATA_DIR / "2023_04_11_0021.abf",
]

# ── Pipeline: registered analysis names + their documented params ─────────────
#   Params match the ui_params defaults declared in each @AnalysisRegistry.register
#   block. Change values here to re-run with different settings.
PIPELINE = [
    {
        "analysis": "rmp_analysis",
        "scope": "all_trials",
        "params": {
            "baseline_start": 0.0,
            "baseline_end": 0.2,  # first 200 ms
        },
    },
    {
        "analysis": "rin_analysis",
        "scope": "all_trials",
        "params": {
            "baseline_start": 0.0,
            "baseline_end": 0.15,
            "response_start": 0.6,
            "response_end": 0.75,
        },
    },
    {
        "analysis": "spike_detection",
        "scope": "all_trials",
        "params": {
            "threshold": -20.0,  # mV  — peak voltage threshold
            "refractory_period": 0.002,  # s   — 2 ms refractory
            "dvdt_threshold": 20.0,  # V/s — dV/dt onset criterion (Bean 2007)
        },
    },
]


def progress(current: int, total: int, msg: str) -> None:
    print(f"  [{current}/{total}] {msg}")


def main() -> None:
    print("=" * 55)
    print("SynaptiPy — eNeuro real-data demonstration")
    print("=" * 55)

    # Print available registered analyses so readers can see what the API offers
    available = BatchAnalysisEngine.list_available_analyses()
    print(f"\nRegistered analyses ({len(available)}): {available}\n")

    existing = [p for p in FILES if p.exists()]
    missing = [p for p in FILES if not p.exists()]
    if missing:
        for m in missing:
            print(f"WARNING: file not found — skipping: {m.name}")
    if not existing:
        print("ERROR: no input files found.")
        sys.exit(1)

    engine = BatchAnalysisEngine(max_workers=1)

    t0 = time.time()
    df = engine.run_batch(
        files=existing,
        pipeline_config=PIPELINE,
        progress_callback=progress,
    )
    elapsed_ms = (time.time() - t0) * 1000

    if df.empty:
        print("Engine returned an empty DataFrame. Check file compatibility.")
        sys.exit(1)

    # ── Save ─────────────────────────────────────────────────────────────────
    csv_path = OUT_DIR / "demo_results.csv"
    df.to_csv(csv_path, index=False)
    print(f"\nResults saved → {csv_path}")
    print(f"Completed in {elapsed_ms:.1f} ms  |  {len(df)} rows  |  {len(df.columns)} columns\n")

    # ── Summary statistics ────────────────────────────────────────────────────
    print("--- Per-file summary ---")
    summary_cols = [
        c
        for c in df.columns
        if any(tag in c for tag in ["rmp", "rin", "spike_count", "ap_threshold", "amplitude", "half_width"])
    ]
    if summary_cols:
        print(
            df[["file_name"] + summary_cols].to_string(index=False)
            if "file_name" in df.columns
            else df[summary_cols].to_string(index=False)
        )
    else:
        print(df.to_string(index=False))

    print("\n--- Grand mean ± SD ---")
    import numpy as np

    for col in summary_cols:
        if col not in df.columns:
            continue
        numeric = df[col].apply(lambda x: x if isinstance(x, (int, float)) else None)
        vals = numeric.dropna()
        if len(vals):
            print(f"  {col}: {float(vals.mean()):.3f} ± {float(vals.std()):.3f}  (n={len(vals)})")


if __name__ == "__main__":
    main()
