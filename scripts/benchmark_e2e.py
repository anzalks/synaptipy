#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
End-to-end rendering benchmark for Synaptipy.

Opens the full Synaptipy MainWindow (identical to a production user session),
loads a real ABF recording via the Explorer tab, and measures
``_update_plot()`` latency in both OVERLAY_AVG and CYCLE_SINGLE modes under
software (QPainter) and OpenGL (Metal-translated on Apple M-series)
rasterisation.

This script follows the same strategy as ``capture_screenshots.py``: it boots
the complete application stack and drives it programmatically.  The entire
rendering pipeline is exercised -- MainWindow -> ExplorerTab ->
ExplorerPlotCanvas -> GraphicsLayoutWidget -> pyqtgraph -> Qt painter / GL.

Dataset: 2023_04_11_0021.abf  (20 trials x 20 000 samples @ 20 kHz)

Benchmarks
----------
OVERLAY_AVG
    N trials overlaid simultaneously (N in [5, 10, 15, 20]).  Each timing
    cycle rotates the visible window of N trials through the available 20 so
    that pyqtgraph receives a distinct set of data arrays per call,
    preventing the same-object VBO-skip optimisation from masking real GPU
    upload cost.

CYCLE_SINGLE
    Single trial displayed at a time; trial index is incremented on each
    cycle, exercising the trial-browsing hot path.

Measurement
-----------
Each cycle times ``explorer._update_plot()`` + ``app.processEvents()``
(the exact sequence fired on every pan, scroll, or trial-selection change).
The first ``_N_WARMUP`` cycles are discarded; statistics are reported over
the remaining ``_N_CYCLES`` cycles as median and 5th/95th percentile.

Results -> paper/results/e2e_rendering_results_{os}.csv
Figure  -> paper/results/e2e_rendering_benchmark_{os}.png

Usage::

    python scripts/benchmark_e2e.py [--output-dir PATH]

IMPORTANT: Requires a real display.  On Linux without X11 use xvfb-run.
"""

import argparse
import csv
import json
import os
import subprocess
import sys
import time
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPT_DIR.parent
_SRC_DIR = _REPO_ROOT / "src"
_ABF_0021 = _REPO_ROOT / "examples" / "data" / "2023_04_11_0021.abf"

# N of trials overlaid in OVERLAY_AVG benchmark.
# 0021.abf has 20 trials; levels are clamped to min(N, n_all).
_N_OVERLAY_LEVELS = [5, 10, 15, 20]

_N_WARMUP = 50  # discarded warm-up cycles
_N_CYCLES = 500  # measured cycles after warm-up
_OS_TAG = {"darwin": "macos", "win32": "windows"}.get(sys.platform, sys.platform)


# ---------------------------------------------------------------------------
# Child-process worker
# ---------------------------------------------------------------------------


def _run_child(mode: str) -> None:  # noqa: C901
    """Boot the full MainWindow, load ABF, time _update_plot(). Print JSON."""
    use_opengl = mode == "opengl"

    if str(_SRC_DIR) not in sys.path:
        sys.path.insert(0, str(_SRC_DIR))

    import warnings

    warnings.filterwarnings("ignore")

    # useOpenGL MUST be set before the first Qt object is created.
    import pyqtgraph as pg

    pg.setConfigOption("useOpenGL", use_opengl)
    pg.setConfigOption("antialias", False)

    import logging

    logging.disable(logging.ERROR)

    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(sys.argv)

    # Apply the same light theme the app uses in a normal session.
    from Synaptipy.shared.theme_manager import ThemeMode, apply_theme

    apply_theme(ThemeMode.LIGHT)

    # Register all built-in analyses and any user plugins.
    # Required so AnalyserTab (created inside MainWindow) does not raise on init.
    import Synaptipy.core.analysis  # noqa: F401 -- triggers registry decorators
    from Synaptipy.application.plugin_manager import PluginManager

    PluginManager.load_plugins()

    from Synaptipy.application.gui.main_window import MainWindow

    window = MainWindow()
    window.setWindowTitle(f"Synaptipy -- E2E Rendering Benchmark [{mode.upper()}]")
    window.resize(1280, 800)
    window.show()

    for _ in range(5):
        app.processEvents()

    explorer = window.explorer_tab

    # Load the ABF file via the same code path as File > Open.
    # ExplorerTab.load_recording_data() kicks off an AnalysisWorker in a
    # QThreadPool; _is_loading is set True until _finalize_loading_state()
    # fires after the background thread completes.
    explorer.load_recording_data(_ABF_0021, [_ABF_0021], 0)

    deadline = time.time() + 30.0
    while getattr(explorer, "_is_loading", False) and time.time() < deadline:
        app.processEvents()
        time.sleep(0.005)

    for _ in range(10):
        app.processEvents()

    if not explorer.current_recording:
        print(json.dumps({"error": "file load failed or timed out"}))
        return

    ch0 = next(iter(explorer.current_recording.channels.values()))
    n_all = getattr(ch0, "num_trials", 1)
    raw0 = ch0.get_data(0)
    n_samples = len(raw0) if raw0 is not None else 0

    results = {
        "mode": mode,
        "n_all_trials": n_all,
        "n_samples_per_trial": n_samples,
        "overlay": [],
        "cycle_single": None,
    }

    # ------------------------------------------------------------------
    # OVERLAY_AVG: vary the number of simultaneously overlaid trials.
    # ------------------------------------------------------------------
    explorer.current_plot_mode = explorer.PlotMode.OVERLAY_AVG

    for n_req in _N_OVERLAY_LEVELS:
        n = min(n_req, n_all)

        # Warm-up: set initial selection and let Qt settle.
        explorer.selected_trial_indices = set(range(n))
        explorer._update_plot()
        for _ in range(3):
            app.processEvents()

        # Window size for rotation: how many distinct starting offsets fit.
        n_offsets = max(1, n_all - n + 1)

        times_ms = []
        for cycle in range(_N_WARMUP + _N_CYCLES):
            # Rotate the visible window by 1 each cycle so each setData()
            # call operates on a distinct set of arrays.  For n == n_all
            # only one offset exists (0), so the selection stays fixed --
            # reflecting the steady-state "all trials shown" user scenario.
            start = cycle % n_offsets
            explorer.selected_trial_indices = set(range(start, start + n))
            t0 = time.perf_counter()
            explorer._update_plot()
            app.processEvents()
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            if cycle >= _N_WARMUP:
                times_ms.append(elapsed_ms)

        times_ms.sort()
        k = len(times_ms)
        entry = {
            "n_trials": n,
            "total_samples": n * n_samples,
            "median_ms": round(times_ms[k // 2], 3),
            "p05_ms": round(times_ms[max(0, int(0.05 * k))], 3),
            "p95_ms": round(times_ms[min(k - 1, int(0.95 * k))], 3),
        }
        results["overlay"].append(entry)
        print(
            f"  [{mode}] overlay N={n:>2}: median={entry['median_ms']:.2f} ms",
            file=sys.stderr,
            flush=True,
        )

    # ------------------------------------------------------------------
    # CYCLE_SINGLE: single trial displayed, browse through all trials.
    # ------------------------------------------------------------------
    explorer.current_plot_mode = explorer.PlotMode.CYCLE_SINGLE
    explorer.selected_trial_indices.clear()
    explorer.current_trial_index = 0
    explorer._update_plot()
    for _ in range(3):
        app.processEvents()

    times_ms = []
    for cycle in range(_N_WARMUP + _N_CYCLES):
        explorer.current_trial_index = (explorer.current_trial_index + 1) % n_all
        t0 = time.perf_counter()
        explorer._update_plot()
        app.processEvents()
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        if cycle >= _N_WARMUP:
            times_ms.append(elapsed_ms)

    times_ms.sort()
    k = len(times_ms)
    results["cycle_single"] = {
        "n_trials": 1,
        "total_samples": n_samples,
        "median_ms": round(times_ms[k // 2], 3),
        "p05_ms": round(times_ms[max(0, int(0.05 * k))], 3),
        "p95_ms": round(times_ms[min(k - 1, int(0.95 * k))], 3),
    }
    print(
        f"  [{mode}] cycle_single: median={results['cycle_single']['median_ms']:.2f} ms",
        file=sys.stderr,
        flush=True,
    )

    print(json.dumps(results))

    window.close()
    for _ in range(3):
        app.processEvents()


# ---------------------------------------------------------------------------
# Spawn helpers
# ---------------------------------------------------------------------------


def _spawn_child(mode: str) -> dict:
    """Run _run_child in a subprocess; return the parsed JSON result dict."""
    env = os.environ.copy()
    # Ensure a real display is used, not an offscreen platform.
    env.pop("QT_QPA_PLATFORM", None)

    cmd = [sys.executable, str(Path(__file__).resolve()), "--_child", mode]
    print(f"\n[spawn] {mode.upper()} child process starting ...", flush=True)
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        env=env,
        timeout=600,
    )
    if result.stderr:
        for line in result.stderr.splitlines():
            stripped = line.strip()
            if stripped:
                print(f"  {stripped}", file=sys.stderr)

    # Extract the last JSON line from stdout.
    json_line = ""
    for line in reversed(result.stdout.splitlines()):
        stripped = line.strip()
        if stripped.startswith("{"):
            json_line = stripped
            break

    if not json_line:
        raise RuntimeError(
            f"{mode} child produced no JSON.\n" f"stdout: {result.stdout[:800]}\n" f"stderr: {result.stderr[:800]}"
        )
    return json.loads(json_line)


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------


def _save_csv(sw: dict, gl: dict, output_path: Path) -> None:
    """Write per-row CSV with one row per (renderer, benchmark_mode, n_trials)."""
    fieldnames = [
        "renderer",
        "benchmark_mode",
        "n_trials",
        "total_samples",
        "median_ms",
        "p05_ms",
        "p95_ms",
    ]
    rows = []
    for label, data in [("software", sw), ("opengl", gl)]:
        for entry in data.get("overlay", []):
            rows.append(
                {
                    "renderer": label,
                    "benchmark_mode": "overlay_avg",
                    "n_trials": entry["n_trials"],
                    "total_samples": entry["total_samples"],
                    "median_ms": entry["median_ms"],
                    "p05_ms": entry["p05_ms"],
                    "p95_ms": entry["p95_ms"],
                }
            )
        cs = data.get("cycle_single")
        if cs:
            rows.append(
                {
                    "renderer": label,
                    "benchmark_mode": "cycle_single",
                    "n_trials": cs["n_trials"],
                    "total_samples": cs["total_samples"],
                    "median_ms": cs["median_ms"],
                    "p05_ms": cs["p05_ms"],
                    "p95_ms": cs["p95_ms"],
                }
            )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Saved CSV : {output_path}")


def _save_plot(sw: dict, gl: dict, output_path: Path) -> None:
    """Export a two-panel benchmark figure."""
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np
    except ImportError:
        print("WARNING: matplotlib not available -- skipping plot export.")
        return

    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    fig.suptitle(
        "Synaptipy End-to-End Rendering Benchmark -- full MainWindow, real ABF\n"
        f"2023_04_11_0021.abf  (20 trials x 20 000 samples, {_N_CYCLES} measured cycles,"
        " error bars = 5th/95th percentile)",
        fontsize=10,
    )

    # --- Panel A: OVERLAY_AVG latency vs N ---
    ax0 = axes[0]

    def _ov_series(data: dict) -> tuple:
        entries = data.get("overlay", [])
        ns = [e["n_trials"] for e in entries]
        med = [e["median_ms"] for e in entries]
        lo = [e["median_ms"] - e["p05_ms"] for e in entries]
        hi = [e["p95_ms"] - e["median_ms"] for e in entries]
        return ns, med, lo, hi

    if sw.get("overlay"):
        ns, med, lo, hi = _ov_series(sw)
        ax0.errorbar(
            ns,
            med,
            yerr=[lo, hi],
            fmt="s--",
            color="#B71C1C",
            ecolor="#EF9A9A",
            capsize=4,
            linewidth=2,
            markersize=6,
            label="Software (QPainter)",
        )
    if gl.get("overlay"):
        ns, med, lo, hi = _ov_series(gl)
        ax0.errorbar(
            ns,
            med,
            yerr=[lo, hi],
            fmt="o-",
            color="#1565C0",
            ecolor="#90CAF9",
            capsize=4,
            linewidth=2,
            markersize=6,
            label="OpenGL (Metal)",
        )
    ax0.set_xlabel("Overlaid trials (N)", fontsize=11)
    ax0.set_ylabel("_update_plot() + processEvents() (ms)", fontsize=10)
    ax0.set_title("(A) OVERLAY_AVG mode", fontsize=12)
    if sw.get("overlay"):
        ax0.set_xticks([e["n_trials"] for e in sw["overlay"]])
    ax0.legend(fontsize=9)
    ax0.grid(True, alpha=0.3)

    # --- Panel B: grouped bars OVERLAY_AVG + CYCLE_SINGLE ---
    ax1 = axes[1]
    sw_ov = sw.get("overlay", [])
    gl_ov = gl.get("overlay", [])

    all_ns = sorted({e["n_trials"] for e in sw_ov} | {e["n_trials"] for e in gl_ov})
    sw_dict = {e["n_trials"]: e for e in sw_ov}
    gl_dict = {e["n_trials"]: e for e in gl_ov}

    width = 0.35
    x = np.arange(len(all_ns))
    sw_med = [sw_dict.get(n, {}).get("median_ms", 0) for n in all_ns]
    sw_lo = [sw_dict.get(n, {}).get("median_ms", 0) - sw_dict.get(n, {}).get("p05_ms", 0) for n in all_ns]
    sw_hi = [sw_dict.get(n, {}).get("p95_ms", 0) - sw_dict.get(n, {}).get("median_ms", 0) for n in all_ns]
    gl_med = [gl_dict.get(n, {}).get("median_ms", 0) for n in all_ns]
    gl_lo = [gl_dict.get(n, {}).get("median_ms", 0) - gl_dict.get(n, {}).get("p05_ms", 0) for n in all_ns]
    gl_hi = [gl_dict.get(n, {}).get("p95_ms", 0) - gl_dict.get(n, {}).get("median_ms", 0) for n in all_ns]

    ax1.bar(
        x - width / 2,
        sw_med,
        width,
        label="Software",
        color="#B71C1C",
        alpha=0.8,
        yerr=[sw_lo, sw_hi],
        capsize=4,
        error_kw={"ecolor": "#EF9A9A"},
    )
    ax1.bar(
        x + width / 2,
        gl_med,
        width,
        label="OpenGL (Metal)",
        color="#1565C0",
        alpha=0.8,
        yerr=[gl_lo, gl_hi],
        capsize=4,
        error_kw={"ecolor": "#90CAF9"},
    )
    ax1.set_xticks(x)
    ax1.set_xticklabels([str(n) for n in all_ns])
    ax1.set_xlabel("Overlaid trials (N)", fontsize=11)
    ax1.set_ylabel("Frame time (ms)", fontsize=11)
    ax1.set_title("(B) Software vs OpenGL per N (grouped bars)", fontsize=12)
    ax1.legend(fontsize=9)
    ax1.grid(True, alpha=0.3, axis="y")

    # Annotate CYCLE_SINGLE results below the x-axis label.
    sw_cs = sw.get("cycle_single")
    gl_cs = gl.get("cycle_single")
    if sw_cs and gl_cs:
        note = f"CYCLE_SINGLE (1 trial):  SW={sw_cs['median_ms']:.2f} ms," f"  GL={gl_cs['median_ms']:.2f} ms"
        ax1.text(
            0.5,
            -0.14,
            note,
            transform=ax1.transAxes,
            ha="center",
            fontsize=8,
            style="italic",
        )

    plt.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(str(output_path), dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved plot: {output_path}")


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


def run(output_dir: Path) -> bool:
    """Spawn both renderer modes and save results. Return True on success."""
    try:
        print("Spawning SOFTWARE renderer child process ...")
        sw = _spawn_child("software")
        print("Spawning OPENGL renderer child process ...")
        gl = _spawn_child("opengl")
    except Exception as exc:
        print(f"[ERROR] Child process failed: {exc}", file=sys.stderr)
        return False

    csv_path = output_dir / f"e2e_rendering_results_{_OS_TAG}.csv"
    png_path = output_dir / f"e2e_rendering_benchmark_{_OS_TAG}.png"
    _save_csv(sw, gl, csv_path)
    _save_plot(sw, gl, png_path)
    # Copy to canonical filename referenced by paper/paper.md (Figure 3)
    canonical_png = output_dir / f"e2e_rendering_benchmark_{_OS_TAG.lower()}.png"
    if png_path.exists() and canonical_png != png_path:
        import shutil as _shutil

        _shutil.copy2(png_path, canonical_png)
        print(f"Copied canonical: {canonical_png}")

    _print_summary(sw, gl)
    return True


def _print_summary(sw: dict, gl: dict) -> None:
    """Print a compact text summary to stdout."""
    print("\n--- E2E Rendering Benchmark Summary ---")
    print(f"{'Mode':<20} {'N':>4}  {'Software':>12}  {'OpenGL':>12}  {'SW/GL ratio':>12}")
    for sw_e, gl_e in zip(sw.get("overlay", []), gl.get("overlay", [])):
        n = sw_e["n_trials"]
        s = sw_e["median_ms"]
        g = gl_e["median_ms"]
        ratio = s / g if g else float("nan")
        print(f"  OVERLAY_AVG     {n:>4}  {s:>10.2f}ms  {g:>10.2f}ms  {ratio:>12.2f}x")
    sw_cs = sw.get("cycle_single")
    gl_cs = gl.get("cycle_single")
    if sw_cs and gl_cs:
        s = sw_cs["median_ms"]
        g = gl_cs["median_ms"]
        ratio = s / g if g else float("nan")
        print(f"  CYCLE_SINGLE    {'1':>4}  {s:>10.2f}ms  {g:>10.2f}ms  {ratio:>12.2f}x")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Synaptipy end-to-end rendering benchmark.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=_REPO_ROOT / "paper" / "results",
        metavar="PATH",
        help="Destination for CSV and PNG (default: paper/results/).",
    )
    parser.add_argument(
        "--_child",
        choices=["opengl", "software"],
        help=argparse.SUPPRESS,
    )
    args = parser.parse_args()

    if args._child:
        _run_child(args._child)
        return 0

    return 0 if run(args.output_dir) else 1


if __name__ == "__main__":
    sys.exit(main())
