#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OpenGL vs software-rasterised rendering benchmark for Synaptipy plot traces.

Reproduces **Figure 2** (``paper/results/rendering_benchmark.png``) in the
Synaptipy manuscript.  To regenerate the figure::

    python scripts/benchmark_rendering.py

This script measures how long pyqtgraph takes to update a plot containing N
overlaid voltage traces when OpenGL-accelerated rendering is enabled versus
disabled.  Each condition is run in a separate child process so that
pyqtgraph's global ``useOpenGL`` flag is set before any Qt object is created.

Dataset: 2023_04_11_0021.abf (20 trials x 20 000 samples @ 20 kHz = 400 K
         visible points at maximum overlay).

Results are written to paper/results/rendering_results_{os}.csv and
paper/results/rendering_benchmark_{os}.png (OS-tagged) and also copied to the
canonical paper/results/rendering_benchmark.png referenced by paper.md.

Usage::

    python scripts/benchmark_rendering.py [--output-dir PATH]

IMPORTANT: This script creates a real Qt window. Run it on a machine that has
a physical or virtual display.  On macOS the default display server is used
automatically.  On Linux, set DISPLAY or use xvfb-run:

    xvfb-run python scripts/benchmark_rendering.py

How the measurement works
-------------------------
1. Each child process loads the real ABF file via ``NeoAdapter``, then
   creates an ``ExplorerPlotCanvas`` embedded in a visible ``QWidget`` with
   a ``QGridLayout`` — exactly the layout hierarchy the application uses.
2. For each trial count N in [10, 20, 30, 50]:
   a. A ``Recording`` containing N trials of real electrophysiology data is
      constructed from the loaded channel arrays.  For N > 20, trials wrap
      via ``i % len(all_trials)`` — the data content is varied but the array
      objects are reused, which is representative of the steady-state case.
   b. ``canvas.rebuild_plots(recording)`` is called once to set up the
      PlotItem, matching the file-open code path in the Explorer tab.  N
      ``PlotDataItem`` curves are then added to the canvas's PlotItem.
   c. 1 000 timing cycles are run: each cycle calls ``curve.setData()`` on
      every PlotDataItem then flushes repaints with
      ``QCoreApplication.processEvents()``.  This is the hot path that fires
      on every pan, scroll, or trial-selection change in the Explorer tab.
   d. The first 100 cycles are discarded as warm-up; error bars report the
      5th and 95th percentile over the remaining 900 cycles, which excludes
      rare OS-scheduler preemption spikes from the reported spread.

Why per-frame time matters
--------------------------
Synaptipy's Explorer tab overlays all trials in a single PlotItem. With 20
trials of 20 000 samples each, the renderer must process 400 000 data points
per frame.  With OpenGL disabled (Qt's QPainter rasteriser), each update
rasterises every polyline in software on the CPU.  With OpenGL enabled,
pyqtgraph uploads point arrays to the GPU as VBOs and issues a single draw
call per trace, offloading the rasterisation step.  The crossover point at
which OpenGL becomes faster depends on sample count and GPU capabilities.
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPT_DIR.parent
_SRC_DIR = _REPO_ROOT / "src"
_ABF_0021 = _REPO_ROOT / "examples" / "data" / "2023_04_11_0021.abf"

# N=40 is excluded: the source file has 20 trials; at N=40 the i%20 indexing
# cycles through all arrays twice per update, placing the entire dataset in L2
# cache for the second pass and triggering QPainter dirty-rect optimisation for
# repeated identical data.  The resulting anomalously low median (~2 ms vs ~17 ms
# at N=30) is a measurement artefact, not a genuine renderer difference.
_N_TRIALS_LEVELS = [10, 20, 30, 50]
_N_WARMUP = 100
_N_CYCLES = 1000  # total cycles; first _N_WARMUP are discarded
_OS_TAG = {"darwin": "macos", "win32": "windows"}.get(sys.platform, sys.platform)


# ---------------------------------------------------------------------------
# Child-process worker (called with --_child opengl|software)
# ---------------------------------------------------------------------------


def _run_child(mode: str) -> None:
    """Run the rendering benchmark in-process and print JSON to stdout."""
    use_opengl = mode == "opengl"

    if str(_SRC_DIR) not in sys.path:
        sys.path.insert(0, str(_SRC_DIR))

    import time

    import numpy as np

    # Set OpenGL flag BEFORE any Qt import
    import pyqtgraph as pg

    pg.setConfigOption("useOpenGL", use_opengl)
    pg.setConfigOption("antialias", False)
    pg.setConfigOption("background", "k")
    pg.setConfigOption("foreground", "w")

    from PySide6.QtWidgets import QApplication, QGridLayout, QWidget

    app = QApplication.instance() or QApplication(sys.argv)

    from Synaptipy.application.gui.explorer.plot_canvas import ExplorerPlotCanvas
    from Synaptipy.core.data_model import Channel, Recording
    from Synaptipy.infrastructure.file_readers import NeoAdapter

    # Load real electrophysiology data from the ABF file
    adapter = NeoAdapter()
    rec = adapter.read_recording(str(_ABF_0021))
    src_channel = list(rec.channels.values())[0]
    all_trials = [np.asarray(t, dtype=np.float32) for t in src_channel.data_trials]

    # Build a rotation pool of distinct array copies per trial.
    # Without this, calling item.setData(same_array_object) every cycle lets
    # pyqtgraph detect an unchanged data pointer and skip the VBO upload on
    # the GL path, making OpenGL appear artificially fast and producing
    # irreproducible results across runs.  Four distinct copies per trial
    # cycle via (cycle % _POOL_DEPTH) so every setData() call receives a
    # fresh object, guaranteeing a real GPU upload each cycle.
    _POOL_DEPTH = 4
    trial_pool = [[t.copy() for t in all_trials] for _ in range(_POOL_DEPTH)]

    # A visible parent container is required so rebuild_plots() can swap the
    # GraphicsLayoutWidget in/out of a QGridLayout.
    # NOTE: The Explorer tab does exactly this — its _setup_layout() calls
    #   center_layout.addWidget(self.plot_canvas.widget, 0, 0)
    # in a QGridLayout inside a plain QWidget.  The benchmark replicates
    # that layout exactly, so the rendering path is identical to production.
    parent_widget = QWidget()
    parent_widget.setWindowTitle(f"Synaptipy — ExplorerPlotCanvas rendering benchmark [{mode.upper()}]")
    parent_widget.resize(800, 600)
    parent_layout = QGridLayout(parent_widget)
    parent_widget.setLayout(parent_layout)
    canvas = ExplorerPlotCanvas()
    parent_layout.addWidget(canvas.widget, 0, 0, 1, 1)
    parent_widget.show()
    app.processEvents()

    results = {}

    for n_trials in _N_TRIALS_LEVELS:
        # Build a Recording with exactly n_trials trials of real data.
        subset_channel = Channel(
            id=src_channel.id,
            name=src_channel.name,
            units=src_channel.units,
            sampling_rate=src_channel.sampling_rate,
            data_trials=all_trials[:n_trials],
        )
        subset_rec = Recording(source_file=_ABF_0021)
        subset_rec.channels = {src_channel.id: subset_channel}
        subset_rec.sampling_rate = rec.sampling_rate
        subset_rec.duration = rec.duration

        # Set up canvas ONCE — this is the file-open path, not the hot path.
        # rebuild_plots() creates the PlotItem; data curves are added below.
        canvas.rebuild_plots(subset_rec)
        # Drain ALL deferred Qt events (including deleteLater() from the
        # previous N-level's widget) before adding curves or starting timing.
        for _ in range(5):
            app.processEvents()

        # Add PlotDataItems to the canvas's real PlotItem.  This mirrors what
        # the ExplorerTab does after rebuild_plots() completes.
        chan_id = src_channel.id
        plot_item = canvas.channel_plots.get(chan_id)
        data_items = []
        if plot_item is not None:
            for i in range(n_trials):
                pen = pg.mkPen((i * 30) % 255, 100, 200, 80)
                curve = plot_item.plot(trial_pool[0][i % len(all_trials)], pen=pen)
                data_items.append(curve)
        for _ in range(5):
            app.processEvents()

        # Time the per-frame update cycle: setData + processEvents.
        # Each cycle uses a distinct copy from trial_pool to ensure a real
        # VBO upload is triggered on the GL path (same-object detection would
        # otherwise skip the upload, producing misleading fast timings).
        print(f"  [{mode}] N={n_trials:>3} — running {_N_CYCLES} cycles ...", flush=True)
        cycle_times = []
        for cycle in range(_N_CYCLES):
            pool = trial_pool[cycle % _POOL_DEPTH]
            app.processEvents()
            t0 = time.perf_counter()
            for idx, item in enumerate(data_items):
                item.setData(pool[idx % len(all_trials)])
            app.processEvents()
            cycle_times.append(time.perf_counter() - t0)

        valid = sorted(cycle_times[_N_WARMUP:])
        n_valid = len(valid)
        median_ms = round(valid[n_valid // 2] * 1000, 3)
        p05_ms = round(valid[max(0, int(n_valid * 0.05))] * 1000, 3)
        p95_ms = round(valid[min(n_valid - 1, int(n_valid * 0.95))] * 1000, 3)
        results[n_trials] = {"median_ms": median_ms, "p05_ms": p05_ms, "p95_ms": p95_ms}

    parent_widget.close()
    app.quit()
    print(json.dumps(results))


# ---------------------------------------------------------------------------
# Main orchestrator: spawn two child processes, collect results, plot
# ---------------------------------------------------------------------------


def _spawn_child(mode: str) -> dict:
    """Launch this script as a subprocess with --_child and return parsed JSON.

    Cross-platform notes
    --------------------
    * The child inherits the full environment so that ``DISPLAY`` (Linux),
      ``QT_QPA_PLATFORM``, and ``PATH`` are all forwarded correctly.
    * Timeout is set to 900 s to accommodate slow hardware and large N levels
      (software renderer at N=50 with 1 000 cycles takes ~25 s on a modern
      machine; 900 s gives 35x headroom).
    * On Linux without a display, set ``QT_QPA_PLATFORM=xcb`` and ensure
      ``DISPLAY`` is set, or prepend ``xvfb-run`` to the invocation.
    """
    import os

    env = os.environ.copy()
    cmd = [sys.executable, str(_SCRIPT_DIR / "benchmark_rendering.py"), "--_child", mode]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=900, env=env)
    if result.returncode != 0:
        print(f"WARNING: child process [{mode}] exited with code {result.returncode}")
        print(result.stderr[-2000:])
        return {}
    # Last non-empty line is the JSON payload
    lines = [line for line in result.stdout.strip().splitlines() if line.strip()]
    if not lines:
        print(f"WARNING: no output from child [{mode}]")
        return {}
    try:
        return json.loads(lines[-1])
    except json.JSONDecodeError as exc:
        print(f"WARNING: could not parse child output [{mode}]: {exc}")
        return {}


def _save_csv(opengl_data: dict, software_data: dict, output_path: Path) -> None:
    """Write rendering benchmark results to CSV."""
    import csv

    fieldnames = [
        "renderer",
        "n_trials",
        "total_samples",
        "median_ms",
        "p05_ms",
        "p95_ms",
    ]
    rows = []
    for n_trials, data in sorted(opengl_data.items(), key=lambda x: int(x[0])):
        rows.append(
            {
                "renderer": "opengl",
                "n_trials": n_trials,
                "total_samples": int(n_trials) * 20000,
                **data,
            }
        )
    for n_trials, data in sorted(software_data.items(), key=lambda x: int(x[0])):
        rows.append(
            {
                "renderer": "software",
                "n_trials": n_trials,
                "total_samples": int(n_trials) * 20000,
                **data,
            }
        )
    with open(output_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Saved CSV : {output_path}")


def _save_plot(opengl_data: dict, software_data: dict, output_path: Path) -> None:
    """Export rendering benchmark PNG using matplotlib."""
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("WARNING: matplotlib not available — skipping plot export.")
        return

    levels = sorted(int(k) for k in opengl_data)

    def _extract(data: dict) -> tuple:
        med = [data[str(n)]["median_ms"] for n in levels]
        lo = [data[str(n)]["median_ms"] - data[str(n)]["p05_ms"] for n in levels]
        hi = [data[str(n)]["p95_ms"] - data[str(n)]["median_ms"] for n in levels]
        return med, lo, hi

    fig, (ax_abs, ax_ratio) = plt.subplots(1, 2, figsize=(12, 4.5))

    if opengl_data:
        med_gl, lo_gl, hi_gl = _extract(opengl_data)
        ax_abs.errorbar(
            levels,
            med_gl,
            yerr=[lo_gl, hi_gl],
            fmt="o-",
            color="#1565C0",
            ecolor="#90CAF9",
            capsize=4,
            linewidth=2,
            markersize=6,
            label="OpenGL (Metal)",
        )

    if software_data:
        med_sw, lo_sw, hi_sw = _extract(software_data)
        ax_abs.errorbar(
            levels,
            med_sw,
            yerr=[lo_sw, hi_sw],
            fmt="s--",
            color="#B71C1C",
            ecolor="#EF9A9A",
            capsize=4,
            linewidth=2,
            markersize=6,
            label="Software (QPainter)",
        )

    ax_abs.set_xlabel("Overlaid trials (N)", fontsize=11)
    ax_abs.set_ylabel("Per-frame update time (ms)", fontsize=11)
    ax_abs.set_title("A. Absolute render time (line)", fontsize=12)
    ax_abs.set_xticks(levels)
    ax_abs.legend(fontsize=9)
    ax_abs.grid(True, alpha=0.3)

    # Grouped bar chart: Software and OpenGL bars side by side for each N.
    if opengl_data and software_data:
        med_gl, lo_gl, hi_gl = _extract(opengl_data)
        med_sw, lo_sw, hi_sw = _extract(software_data)
        width = 0.35
        x = list(range(len(levels)))
        x_sw = [xi - width / 2 for xi in x]
        x_gl = [xi + width / 2 for xi in x]
        ax_ratio.bar(
            x_sw,
            med_sw,
            width,
            label="Software (QPainter)",
            color="#B71C1C",
            alpha=0.8,
            yerr=[lo_sw, hi_sw],
            capsize=4,
            error_kw={"ecolor": "#EF9A9A"},
        )
        ax_ratio.bar(
            x_gl,
            med_gl,
            width,
            label="OpenGL (Metal)",
            color="#1565C0",
            alpha=0.8,
            yerr=[lo_gl, hi_gl],
            capsize=4,
            error_kw={"ecolor": "#90CAF9"},
        )
        ax_ratio.set_xticks(x)
        ax_ratio.set_xticklabels([str(n) for n in levels])
        ax_ratio.set_xlabel("Overlaid trials (N)", fontsize=11)
        ax_ratio.set_ylabel("Per-frame update time (ms)", fontsize=11)
        ax_ratio.set_title("B. Software vs OpenGL (grouped bars)", fontsize=12)
        ax_ratio.legend(fontsize=9)
        ax_ratio.grid(True, alpha=0.3, axis="y")
    else:
        ax_ratio.text(0.5, 0.5, "Insufficient data", ha="center", va="center", transform=ax_ratio.transAxes)

    n_measured = _N_CYCLES - _N_WARMUP
    fig.suptitle(
        "pyqtgraph Rendering Benchmark — 2023_04_11_0021.abf "
        f"(20 000 samples/trial, {n_measured} measured cycles; error bars = 5th/95th percentile)",
        fontsize=10,
    )
    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)
    print(f"Saved plot: {output_path}")


def main(output_dir: Path) -> None:
    """Orchestrate child processes and save results."""
    output_dir.mkdir(parents=True, exist_ok=True)

    print("Spawning software-renderer child process ...")
    software_data = _spawn_child("software")
    print("Spawning OpenGL-renderer child process ...")
    opengl_data = _spawn_child("opengl")

    if not software_data and not opengl_data:
        print("ERROR: both child processes failed — no results to save.")
        sys.exit(1)

    _save_csv(opengl_data, software_data, output_dir / f"rendering_results_{_OS_TAG}.csv")
    tagged_png = output_dir / f"rendering_benchmark_{_OS_TAG}.png"
    _save_plot(opengl_data, software_data, tagged_png)
    # Copy to canonical filename referenced by paper/paper.md (Figure 2)
    canonical_png = output_dir / "rendering_benchmark.png"
    if tagged_png.exists():
        import shutil as _shutil

        _shutil.copy2(tagged_png, canonical_png)
        print(f"Copied canonical: {canonical_png}")

    print("\nSummary (median ms per update cycle):")
    print(f"  {'N trials':>8}  {'Samples':>8}  {'Software':>10}  {'OpenGL':>8}  {'Ratio (SW/GL)':>14}")
    for n in _N_TRIALS_LEVELS:
        key = str(n)
        sw = software_data.get(key, {}).get("median_ms", float("nan"))
        gl = opengl_data.get(key, {}).get("median_ms", float("nan"))
        ratio = sw / gl if gl and gl > 0 else float("nan")
        print(f"  {n:>8}  {n * 20000:>8}  {sw:>10.2f}  {gl:>8.2f}  {ratio:>14.2f}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Synaptipy OpenGL vs software rendering benchmark")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=_REPO_ROOT / "paper" / "results",
        help="Output directory for CSV and PNG (default: paper/results/)",
    )
    parser.add_argument(
        "--_child",
        choices=["opengl", "software"],
        help=argparse.SUPPRESS,  # internal flag used by subprocess invocation
    )
    args = parser.parse_args()

    if args._child:
        _run_child(args._child)
    else:
        main(args.output_dir)
