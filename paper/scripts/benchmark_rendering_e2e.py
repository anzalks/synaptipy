#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Consolidated rendering benchmark for SynaptiPy — Figure 3, Panels C & D.

Runs TWO benchmark suites SERIALLY, each in its own subprocess:

  Suite 1 — Raw pyqtgraph layer (ExplorerPlotCanvas)
    Measures how long pyqtgraph takes to update a plot containing N overlaid
    voltage traces under software (QPainter) and OpenGL rendering.
    N in [5, 10, 20, 30, 50].  Results → rendering_results_{os}.csv

  Suite 2 — End-to-end full application (MainWindow)
    Drives the complete SynaptiPy application stack and measures
    _update_plot() latency for OVERLAY_AVG and CYCLE_SINGLE modes.
    N in [5, 10, 15, 20] (capped to actual trial count in file).
    Results → e2e_rendering_results_{os}.csv

After both suites finish, figure_03.py is regenerated automatically.

Usage::

    python paper/scripts/benchmark_rendering_e2e.py [--output-dir PATH]

IMPORTANT: Requires a visible display.  On headless Linux use xvfb-run.
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
_REPO_ROOT = _SCRIPT_DIR.parent.parent
_SRC_DIR = _REPO_ROOT / "src"

_OS_TAG = {"darwin": "macos", "win32": "windows"}.get(sys.platform, sys.platform)


def _get_abf_path() -> Path:
    target = _REPO_ROOT / "examples" / "data" / "2023_04_11_0021.abf"
    if target.exists():
        return target
    data_dir = _REPO_ROOT / "examples" / "data"
    if data_dir.exists():
        abfs = list(data_dir.glob("*.abf"))
        if abfs:
            return abfs[0]
    return target


_ABF_0021 = _get_abf_path()

# ---------------------------------------------------------------------------
# Trial level configuration
# ---------------------------------------------------------------------------
# Raw rendering: synthetic trials so N=50 is fine (wraps via i % 20)
_N_REND_LEVELS = [10, 20, 30, 40, 50]
_N_REND_WARMUP = 100
_N_REND_CYCLES = 1000  # discard first _N_REND_WARMUP

# E2E: file has 20 real trials; trials are replicated when N > n_all
_N_E2E_LEVELS = [10, 20, 30, 40, 50]
_N_E2E_WARMUP = 50
_N_E2E_CYCLES = 500


# ===========================================================================
# SUITE 1 — Raw rendering child worker
# ===========================================================================

def _child_raw_rendering(mode: str) -> None:
    """Run the raw pyqtgraph rendering benchmark in-process. Print JSON."""
    use_opengl = mode.startswith("opengl")
    force_opaque = "opaque" in mode

    if str(_SRC_DIR) not in sys.path:
        sys.path.insert(0, str(_SRC_DIR))

    import numpy as np
    import pyqtgraph as pg

    pg.setConfigOption("useOpenGL", use_opengl)
    pg.setConfigOption("antialias", False)
    pg.setConfigOption("background", "k")
    pg.setConfigOption("foreground", "w")

    from Synaptipy.shared.plot_customization import set_force_opaque_trials
    set_force_opaque_trials(force_opaque)

    from PySide6.QtWidgets import QApplication, QGridLayout, QWidget
    app = QApplication.instance() or QApplication(sys.argv)

    from Synaptipy.application.gui.explorer.plot_canvas import ExplorerPlotCanvas
    from Synaptipy.core.data_model import Channel, Recording
    from Synaptipy.infrastructure.file_readers import NeoAdapter

    adapter = NeoAdapter()
    rec = adapter.read_recording(str(_ABF_0021))
    src_channel = list(rec.channels.values())[0]
    all_trials = [np.asarray(t, dtype=np.float32) for t in src_channel.data_trials]

    # Pool of distinct array copies prevents VBO-skip optimisation on GL path
    _POOL_DEPTH = 4
    trial_pool = [[t.copy() for t in all_trials] for _ in range(_POOL_DEPTH)]

    parent_widget = QWidget()
    parent_widget.resize(800, 600)
    parent_layout = QGridLayout(parent_widget)
    canvas = ExplorerPlotCanvas()
    parent_layout.addWidget(canvas.widget, 0, 0, 1, 1)
    parent_widget.show()
    app.processEvents()

    results = {}

    for n_trials in _N_REND_LEVELS:
        subset_channel = Channel(
            id=src_channel.id,
            name=src_channel.name,
            units=src_channel.units,
            sampling_rate=src_channel.sampling_rate,
            data_trials=all_trials[:min(n_trials, len(all_trials))],
        )
        subset_rec = Recording(source_file=_ABF_0021)
        subset_rec.channels = {src_channel.id: subset_channel}
        subset_rec.sampling_rate = rec.sampling_rate
        subset_rec.duration = rec.duration

        canvas.rebuild_plots(subset_rec)
        for _ in range(5):
            app.processEvents()

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

        print(f"  [{mode}] N={n_trials:>3} — running {_N_REND_CYCLES} cycles ...", flush=True)
        cycle_times = []
        for cycle in range(_N_REND_CYCLES):
            pool = trial_pool[cycle % _POOL_DEPTH]
            app.processEvents()
            t0 = time.perf_counter()
            for idx, item in enumerate(data_items):
                item.setData(pool[idx % len(all_trials)])
            app.processEvents()
            cycle_times.append(time.perf_counter() - t0)

        valid_arr = np.array(cycle_times[_N_REND_WARMUP:]) * 1000.0
        mean_ms = round(float(np.mean(valid_arr)), 3)
        sem_ms = round(float(np.std(valid_arr, ddof=1) / np.sqrt(len(valid_arr))), 3) if len(valid_arr) > 1 else 0.0
        results[n_trials] = {"mean_ms": mean_ms, "sem_ms": sem_ms}

    parent_widget.close()
    app.quit()
    print(json.dumps(results))


# ===========================================================================
# SUITE 2 — E2E full application child worker
# ===========================================================================

def _child_e2e(mode: str) -> None:
    """Boot the full MainWindow, load ABF, time _update_plot(). Print JSON."""
    use_opengl = mode == "opengl"

    if str(_SRC_DIR) not in sys.path:
        sys.path.insert(0, str(_SRC_DIR))

    import warnings
    import logging
    warnings.filterwarnings("ignore")
    logging.disable(logging.ERROR)

    import numpy as np
    import pyqtgraph as pg
    pg.setConfigOption("useOpenGL", use_opengl)
    pg.setConfigOption("antialias", False)

    from PySide6.QtWidgets import QApplication, QMessageBox
    # Suppress all popups upfront
    QMessageBox.information = lambda *a, **kw: None
    QMessageBox.warning = lambda *a, **kw: None
    QMessageBox.critical = lambda *a, **kw: None
    QMessageBox.question = lambda *a, **kw: QMessageBox.StandardButton.No

    app = QApplication.instance() or QApplication(sys.argv)

    from Synaptipy.shared.theme_manager import ThemeMode, apply_theme
    apply_theme(ThemeMode.LIGHT)

    import Synaptipy.core.analysis  # noqa: F401 — triggers registry decorators
    from Synaptipy.application.plugin_manager import PluginManager
    PluginManager.load_plugins()

    from Synaptipy.application.gui.main_window import MainWindow
    window = MainWindow()

    # Suppress the "Restore Previous Session?" popup and all startup banners
    window._offer_session_restore = lambda: None
    window._show_demo_download_banner = lambda: None
    window._check_for_updates_manual = lambda: None

    window.setWindowTitle(f"SynaptiPy — E2E Rendering Benchmark [{mode.upper()}]")
    window.resize(1280, 800)
    window.show()

    for _ in range(5):
        app.processEvents()

    explorer = window.explorer_tab
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

    # Replicate trials so N can exceed the file's actual trial count.
    # This lets the benchmark test render performance for any N in _N_E2E_LEVELS
    # with consistent data content across all N values.
    max_n_needed = max(_N_E2E_LEVELS)
    if n_all < max_n_needed:
        for ch in explorer.current_recording.channels.values():
            base = list(ch.data_trials)
            while len(ch.data_trials) < max_n_needed:
                ch.data_trials = ch.data_trials + base
            ch.data_trials = ch.data_trials[:max_n_needed]
        n_all = max_n_needed

    results = {
        "mode": mode,
        "n_all_trials": n_all,
        "n_samples_per_trial": n_samples,
        "overlay": [],
        "cycle_single": None,
    }

    # OVERLAY_AVG
    explorer.current_plot_mode = explorer.PlotMode.OVERLAY_AVG

    # Extra warmup for OpenGL to amortize GPU driver initialisation cost.
    if use_opengl:
        for _ in range(30):
            explorer._update_plot()
            app.processEvents()

    for n_req in _N_E2E_LEVELS:
        n = n_req  # n_all was expanded above, so n_req is always <= n_all
        explorer.selected_trial_indices = set(range(n))
        explorer._update_plot()
        for _ in range(3):
            app.processEvents()

        n_offsets = max(1, n_all - n + 1)
        times_ms = []
        for cycle in range(_N_E2E_WARMUP + _N_E2E_CYCLES):
            start = cycle % n_offsets
            explorer.selected_trial_indices = set(range(start, start + n))
            t0 = time.perf_counter()
            explorer._update_plot()
            app.processEvents()
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            if cycle >= _N_E2E_WARMUP:
                times_ms.append(elapsed_ms)

        times_arr = np.array(times_ms)
        mean_val = float(np.mean(times_arr))
        sem_val = float(np.std(times_arr, ddof=1) / np.sqrt(len(times_arr))) if len(times_arr) > 1 else 0.0
        entry = {
            "n_trials": n,
            "total_samples": n * n_samples,
            "mean_ms": round(mean_val, 3),
            "sem_ms": round(sem_val, 3),
        }
        results["overlay"].append(entry)
        print(f"  [{mode}] overlay N={n:>2}: mean={entry['mean_ms']:.2f} ± {entry['sem_ms']:.2f} ms",
              file=sys.stderr, flush=True)

    # CYCLE_SINGLE
    explorer.current_plot_mode = explorer.PlotMode.CYCLE_SINGLE
    explorer.selected_trial_indices.clear()
    explorer.current_trial_index = 0
    explorer._update_plot()
    for _ in range(3):
        app.processEvents()

    times_ms = []
    for cycle in range(_N_E2E_WARMUP + _N_E2E_CYCLES):
        explorer.current_trial_index = (explorer.current_trial_index + 1) % n_all
        t0 = time.perf_counter()
        explorer._update_plot()
        app.processEvents()
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        if cycle >= _N_E2E_WARMUP:
            times_ms.append(elapsed_ms)

    times_arr = np.array(times_ms)
    results["cycle_single"] = {
        "n_trials": 1,
        "total_samples": n_samples,
        "mean_ms": round(float(np.mean(times_arr)), 3),
        "sem_ms": round(float(np.std(times_arr, ddof=1) / np.sqrt(len(times_arr))), 3) if len(times_arr) > 1 else 0.0,
    }
    print(f"  [{mode}] cycle_single: mean={results['cycle_single']['mean_ms']:.2f} ms",
          file=sys.stderr, flush=True)

    print(json.dumps(results))
    window.close()
    for _ in range(3):
        app.processEvents()


# ===========================================================================
# Subprocess helpers
# ===========================================================================

def _spawn_child(suite: str, mode: str, timeout: int = 900) -> dict:
    """Spawn this script as a subprocess with --_suite and --_mode flags."""
    env = os.environ.copy()
    # Ensure a real Qt display is used
    env.pop("QT_QPA_PLATFORM", None)

    cmd = [sys.executable, str(Path(__file__).resolve()), "--_suite", suite, "--_mode", mode]
    print(f"\n[RUNNING] Suite={suite} mode={mode} ...", flush=True)

    result = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=timeout)

    if result.stderr:
        for line in result.stderr.splitlines():
            stripped = line.strip()
            if stripped:
                print(f"  {stripped}", file=sys.stderr)

    # Find last JSON line in stdout
    json_line = ""
    for line in reversed(result.stdout.splitlines()):
        stripped = line.strip()
        if stripped.startswith("{"):
            json_line = stripped
            break

    if not json_line:
        print(f"WARNING: No JSON output from {suite}/{mode}. stdout: {result.stdout[:400]}", file=sys.stderr)
        return {}
    try:
        return json.loads(json_line)
    except json.JSONDecodeError as exc:
        print(f"WARNING: JSON parse error for {suite}/{mode}: {exc}", file=sys.stderr)
        return {}


# ===========================================================================
# CSV savers
# ===========================================================================

def _save_rendering_csv(results_dict: dict, output_path: Path) -> None:
    fieldnames = ["renderer_mode", "n_trials", "mean_ms", "sem_ms"]
    rows = []
    for mode_name, data in results_dict.items():
        if not data:
            continue
        for n_trials, vals in sorted(data.items(), key=lambda x: int(x[0]) if str(x[0]).isdigit() else 0):
            if n_trials == "_mode":
                continue
            rows.append({"renderer_mode": mode_name, "n_trials": n_trials, **vals})
    with open(output_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Saved: {output_path}")


def _save_e2e_csv(sw: dict, gl: dict, output_path: Path) -> None:
    fieldnames = ["renderer", "benchmark_mode", "n_trials", "total_samples", "mean_ms", "sem_ms"]
    rows = []
    for label, data in [("software", sw), ("opengl", gl)]:
        for entry in data.get("overlay", []):
            rows.append({
                "renderer": label,
                "benchmark_mode": "overlay_avg",
                "n_trials": entry["n_trials"],
                "total_samples": entry["total_samples"],
                "mean_ms": entry["mean_ms"],
                "sem_ms": entry["sem_ms"],
            })
        cs = data.get("cycle_single")
        if cs:
            rows.append({
                "renderer": label,
                "benchmark_mode": "cycle_single",
                "n_trials": cs["n_trials"],
                "total_samples": cs["total_samples"],
                "mean_ms": cs["mean_ms"],
                "sem_ms": cs["sem_ms"],
            })
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Saved: {output_path}")


# ===========================================================================
# Orchestrator
# ===========================================================================

def run(output_dir: Path) -> bool:
    output_dir.mkdir(parents=True, exist_ok=True)

    # -----------------------------------------------------------------------
    # Suite 1: Raw rendering (4 modes, serially)
    # -----------------------------------------------------------------------
    print("\n" + "=" * 60)
    print("SUITE 1: Raw pyqtgraph rendering benchmark")
    print(f"  N levels : {_N_REND_LEVELS}")
    print(f"  Modes    : software_transparent, software_opaque, opengl_transparent, opengl_opaque")
    print("=" * 60)

    rend_modes = ["software_transparent", "software_opaque", "opengl_transparent", "opengl_opaque"]
    rend_results = {}
    for m in rend_modes:
        rend_results[m] = _spawn_child("rendering", m)

    _save_rendering_csv(rend_results, output_dir / f"rendering_results_{_OS_TAG}.csv")

    print("\nRendering Summary (mean ms per update cycle):")
    print(f"  {'N':>5}  {'SW_Trans':>10}  {'SW_Opaque':>10}  {'GL_Trans':>10}  {'GL_Opaque':>10}")
    for n in _N_REND_LEVELS:
        key = str(n)
        st = rend_results["software_transparent"].get(key, {}).get("mean_ms", float("nan"))
        so = rend_results["software_opaque"].get(key, {}).get("mean_ms", float("nan"))
        gt = rend_results["opengl_transparent"].get(key, {}).get("mean_ms", float("nan"))
        go = rend_results["opengl_opaque"].get(key, {}).get("mean_ms", float("nan"))
        print(f"  {n:>5}  {st:>10.2f}  {so:>10.2f}  {gt:>10.2f}  {go:>10.2f}")

    # -----------------------------------------------------------------------
    # Suite 2: End-to-end full application (2 modes, serially)
    # -----------------------------------------------------------------------
    print("\n" + "=" * 60)
    print("SUITE 2: End-to-end full application benchmark")
    print(f"  N levels : {_N_E2E_LEVELS} (capped to actual trial count in file)")
    print(f"  Modes    : software, opengl")
    print("=" * 60)

    sw = _spawn_child("e2e", "software")
    gl = _spawn_child("e2e", "opengl")

    _save_e2e_csv(sw, gl, output_dir / f"e2e_rendering_results_{_OS_TAG}.csv")

    print("\nE2E Summary:")
    print(f"  {'Mode':<20} {'N':>4}  {'Software':>12}  {'OpenGL':>12}  {'SW/GL':>8}")
    for sw_e, gl_e in zip(sw.get("overlay", []), gl.get("overlay", [])):
        n = sw_e["n_trials"]
        s, g = sw_e["mean_ms"], gl_e["mean_ms"]
        ratio = s / g if g else float("nan")
        print(f"  {'OVERLAY_AVG':<20} {n:>4}  {s:>10.2f}ms  {g:>10.2f}ms  {ratio:>7.2f}x")
    sw_cs, gl_cs = sw.get("cycle_single"), gl.get("cycle_single")
    if sw_cs and gl_cs:
        s, g = sw_cs["mean_ms"], gl_cs["mean_ms"]
        ratio = s / g if g else float("nan")
        print(f"  {'CYCLE_SINGLE':<20} {'1':>4}  {s:>10.2f}ms  {g:>10.2f}ms  {ratio:>7.2f}x")

    # -----------------------------------------------------------------------
    # Regenerate Figure 3
    # -----------------------------------------------------------------------
    print("\n" + "=" * 60)
    print("Regenerating Figure 3 ...")
    print("=" * 60)
    fig3_script = _SCRIPT_DIR / "paper_figures" / "figure_03.py"
    if fig3_script.exists():
        import subprocess as sp
        sp.run([sys.executable, str(fig3_script)], check=False)
    else:
        print(f"WARNING: {fig3_script} not found — skipping figure regeneration.")

    return True


# ===========================================================================
# Entry point
# ===========================================================================

def main() -> int:
    parser = argparse.ArgumentParser(
        description="SynaptiPy consolidated rendering benchmark (raw + E2E, serial)."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=_REPO_ROOT / "paper" / "analysis_results",
        metavar="PATH",
        help="Destination directory for CSV outputs.",
    )
    # Internal flags used by subprocess invocations
    parser.add_argument("--_suite", choices=["rendering", "e2e"], help=argparse.SUPPRESS)
    parser.add_argument(
        "--_mode",
        choices=["software_transparent", "software_opaque", "opengl_transparent", "opengl_opaque", "software", "opengl"],
        help=argparse.SUPPRESS,
    )
    args = parser.parse_args()

    if args._suite and args._mode:
        if args._suite == "rendering":
            _child_raw_rendering(args._mode)
        else:
            _child_e2e(args._mode)
        return 0

    return 0 if run(args.output_dir) else 1


if __name__ == "__main__":
    sys.exit(main())
