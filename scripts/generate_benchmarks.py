#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Empirical scaling benchmark for Synaptipy's BatchAnalysisEngine.

Reproduces **Figure 1** (``paper/results/benchmark_scaling.png``) in the
Synaptipy manuscript.  To regenerate the figure::

    python scripts/generate_benchmarks.py

Two recording types are benchmarked separately:

  Dataset A  2023_04_11_0021.abf  spike_detection, all_trials, threshold=-20 mV
             Single channel, 20 trials x 20 000 samples @ 20 kHz.
  Dataset B  2023_04_11_0022.abf  event_detection_threshold, all_trials,
             threshold=2.0 mV.  Four channels, 3 trials x 20 000 samples @ 20 kHz.

100 copies of each file are written to a temporary directory.
Wall-clock time is measured for max_workers in [1, 2, 4, 6, 8] with 3 timed
repeats per configuration; the median is reported.

Results are written to paper/results/benchmark_results.csv and
paper/results/benchmark_scaling.png by default.

Usage::

    python scripts/generate_benchmarks.py [--output-dir PATH]

Note on worker counts for Apple M-series (2 efficiency + 6 performance cores):
max_workers=6 typically gives the best throughput for CPU-bound tasks because
it saturates the six high-performance cores without spilling onto the slower
efficiency cores. max_workers=8 can be slower when the two efficiency cores
lag behind and become the straggler that sets the total completion time.

Note on "ideal linear speedup": if N independent workers each process exactly
1/N of the files with zero coordination overhead, the total wall-clock time
would be T1/N, where T1 is the single-worker time. This is plotted as a
dashed reference line. In practice, measured throughput falls below this line
for two reasons:
  1. Process-spawn import cost: each worker process must re-import numpy,
     scipy, and neo before doing any work. On macOS (spawn context) this takes
     roughly 1-2 s per worker and is paid once at startup, not per file.
  2. Shared resources: all workers read from the same SSD and share memory
     bandwidth. For analyses whose per-file compute time is short relative to
     the spawn cost (e.g. rmp_analysis at ~35 ms/file), the overhead dominates
     and adding workers increases total time. For heavier pipelines (spike
     detection at ~300-800 ms/file), the spawn cost amortises over many files
     and parallel throughput approaches the ideal line.
"""

import argparse
import csv
import multiprocessing
import shutil
import sys
import tempfile
import time
from pathlib import Path

multiprocessing.freeze_support()

# ---------------------------------------------------------------------------
# Locate repository root; add src/ to import path for editable checkouts.
# ---------------------------------------------------------------------------
_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPT_DIR.parent
_SRC_DIR = _REPO_ROOT / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from Synaptipy.core.analysis.batch_engine import BatchAnalysisEngine  # noqa: E402

# ---------------------------------------------------------------------------
# Source recordings and analysis pipelines
# ---------------------------------------------------------------------------
_ABF_0021 = _REPO_ROOT / "examples" / "data" / "2023_04_11_0021.abf"
_ABF_0022 = _REPO_ROOT / "examples" / "data" / "2023_04_11_0022.abf"

# spike_detection on every individual trial (20 trials x 20 000 samples @ 20 kHz)
_PIPELINE_0021 = [
    {
        "analysis": "spike_detection",
        "scope": "all_trials",
        "params": {
            "threshold": -20.0,
            "refractory_period": 0.002,
        },
    }
]

# threshold-based event detection on the primary voltage channel (IN0, mV)
_PIPELINE_0022 = [
    {
        "analysis": "event_detection_threshold",
        "scope": "all_trials",
        "params": {
            "threshold": 2.0,
            "direction": "positive",
            "refractory_period": 0.005,
        },
    }
]

_N_FILES = 10
# [1, 2, 4, 6, 8] — 6 covers performance-core saturation on Apple M-series
_WORKER_COUNTS = [1, 2, 4, 6, 8]
_N_REPEATS = 3
_OS_TAG = {"darwin": "macos", "win32": "windows"}.get(sys.platform, sys.platform)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_file_list(source: Path, tmp_dir: Path) -> list:
    """Copy *source* _N_FILES times into *tmp_dir* and return their paths."""
    if not source.exists():
        raise FileNotFoundError(
            f"Source recording not found: {source}\n" "Ensure examples/data/ is present in the repository."
        )
    file_list = []
    stem = source.stem
    suffix = source.suffix
    for i in range(_N_FILES):
        dest = tmp_dir / f"{stem}_bench_{i:04d}{suffix}"
        shutil.copy2(source, dest)
        file_list.append(dest)
    return file_list


def _timed_run(file_list: list, pipeline: list, max_workers: int) -> float:
    """Run one batch pass and return elapsed wall-clock seconds."""
    engine = BatchAnalysisEngine(max_workers=max_workers)
    t0 = time.perf_counter()
    engine.run_batch(file_list, pipeline)
    return time.perf_counter() - t0


def _run_dataset(label: str, file_list: list, pipeline: list) -> list:
    """Benchmark one dataset across all worker counts; return result dicts."""
    results = []
    for workers in _WORKER_COUNTS:
        print(f"  [{label}] max_workers={workers} ...", end=" ", flush=True)
        times = []
        for rep in range(_N_REPEATS):
            elapsed = _timed_run(file_list, pipeline, max_workers=workers)
            times.append(elapsed)
            print(f"rep{rep + 1}={elapsed:.1f}s", end=" ", flush=True)
        median_time = sorted(times)[len(times) // 2]
        print(f"-> median={median_time:.2f}s")
        results.append(
            {
                "dataset": label,
                "max_workers": workers,
                "median_time_s": round(median_time, 3),
                "min_time_s": round(min(times), 3),
                "max_time_s": round(max(times), 3),
                "n_files": _N_FILES,
                "n_repeats": _N_REPEATS,
            }
        )
    return results


def _save_csv(results: list, output_path: Path) -> None:
    """Write combined results to a CSV file."""
    fieldnames = [
        "dataset",
        "max_workers",
        "median_time_s",
        "min_time_s",
        "max_time_s",
        "n_files",
        "n_repeats",
    ]
    with open(output_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)
    print(f"Saved CSV : {output_path}")


def _save_plot(results: list, output_path: Path) -> None:
    """Export a 2x2 benchmark figure: raw time and speedup S=T1/TW per dataset."""
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("WARNING: matplotlib not available — skipping plot export.")
        return

    datasets = list(dict.fromkeys(r["dataset"] for r in results))
    colors = {"0021 spike_detection": "#1565C0", "0022 event_detection": "#B71C1C"}
    markers = {"0021 spike_detection": "o", "0022 event_detection": "s"}
    panel_labels = ["A", "B", "C", "D"]

    fig, axes = plt.subplots(2, 2, figsize=(12, 9))

    for row_idx, label in enumerate(datasets):
        rows = [r for r in results if r["dataset"] == label]
        workers = [r["max_workers"] for r in rows]
        times = [r["median_time_s"] for r in rows]
        err_lo = [r["median_time_s"] - r["min_time_s"] for r in rows]
        err_hi = [r["max_time_s"] - r["median_time_s"] for r in rows]

        color = colors.get(label, "#424242")
        marker = markers.get(label, "o")

        # Left column: raw execution time
        ax_time = axes[row_idx, 0]
        ax_time.errorbar(
            workers,
            times,
            yerr=[err_lo, err_hi],
            fmt=marker + "-",
            color=color,
            ecolor="#BDBDBD",
            capsize=5,
            linewidth=2,
            markersize=7,
            label="Median wall-clock time",
        )
        baseline = times[0]
        ideal_time = [baseline / w for w in workers]
        ax_time.plot(workers, ideal_time, "--", color="#9E9E9E", linewidth=1, label="Ideal T\u2081/N")
        ax_time.set_xlabel("CPU Cores (max_workers)", fontsize=11)
        ax_time.set_ylabel("Elapsed Time (s)", fontsize=11)
        ax_time.set_title(f"({panel_labels[row_idx * 2]}) {label} — Execution Time", fontsize=12)
        ax_time.set_xticks(workers)
        ax_time.legend(fontsize=9)
        ax_time.grid(True, alpha=0.3)

        # Right column: speedup S = T1 / TW
        ax_speedup = axes[row_idx, 1]
        speedup = [baseline / t for t in times]
        ax_speedup.plot(
            workers,
            speedup,
            marker + "-",
            color=color,
            linewidth=2,
            markersize=7,
            label="Measured speedup",
        )
        ax_speedup.plot(
            workers,
            [float(w) for w in workers],
            "k--",
            linewidth=1,
            label="Ideal linear S = W",
        )
        ax_speedup.set_xlabel("CPU Cores (max_workers)", fontsize=11)
        ax_speedup.set_ylabel("Speedup (S = T\u2081 / T_W)", fontsize=11)
        ax_speedup.set_title(f"({panel_labels[row_idx * 2 + 1]}) {label} — Speedup", fontsize=12)
        ax_speedup.set_xticks(workers)
        ax_speedup.legend(fontsize=9)
        ax_speedup.grid(True, alpha=0.3)

    fig.suptitle(
        f"BatchAnalysisEngine Scaling — {_N_FILES} files, {_N_REPEATS} repeats "
        f"(Apple M-series, 6P+2E cores, 32 GB RAM)",
        fontsize=11,
    )
    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)
    print(f"Saved plot: {output_path}")


def main(output_dir: Path) -> None:
    """Run benchmarks for both datasets and write results."""
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Hardware: {multiprocessing.cpu_count()} logical CPUs visible to Python")
    print(f"n_files={_N_FILES}, n_repeats={_N_REPEATS}, workers={_WORKER_COUNTS}\n")

    all_results = []

    with tempfile.TemporaryDirectory(prefix="synaptipy_bench_") as tmp:
        tmp_path = Path(tmp)

        print(f"Building {_N_FILES}-file dataset from: {_ABF_0021.name}")
        files_0021 = _build_file_list(_ABF_0021, tmp_path)
        print(f"Building {_N_FILES}-file dataset from: {_ABF_0022.name}")
        files_0022 = _build_file_list(_ABF_0022, tmp_path)

        print("\n--- Dataset A: spike detection (0021) ---")
        all_results += _run_dataset("0021 spike_detection", files_0021, _PIPELINE_0021)

        print("\n--- Dataset B: event detection threshold (0022) ---")
        all_results += _run_dataset("0022 event_detection", files_0022, _PIPELINE_0022)

    _save_csv(all_results, output_dir / f"benchmark_results_{_OS_TAG}.csv")
    tagged_png = output_dir / f"benchmark_scaling_{_OS_TAG}.png"
    _save_plot(all_results, tagged_png)
    # Also write the canonical filename referenced by paper/paper.md (Figure 1)
    canonical_png = output_dir / "benchmark_scaling.png"
    if tagged_png.exists():
        import shutil as _shutil

        _shutil.copy2(tagged_png, canonical_png)
        print(f"Copied canonical: {canonical_png}")

    print("\nSummary:")
    print(f"  {'Dataset':<28}  {'Workers':>7}  {'Median (s)':>10}  {'Min':>7}  {'Max':>7}")
    for r in all_results:
        print(
            f"  {r['dataset']:<28}  {r['max_workers']:>7}  "
            f"{r['median_time_s']:>10.3f}  {r['min_time_s']:>7.3f}  {r['max_time_s']:>7.3f}"
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Synaptipy BatchAnalysisEngine scaling benchmark")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=_REPO_ROOT / "paper" / "results",
        help="Output directory for CSV and PNG (default: paper/results/)",
    )
    args = parser.parse_args()
    main(args.output_dir)
