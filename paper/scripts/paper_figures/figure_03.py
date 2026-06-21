import csv
import sys
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# Add parent scripts directory to path to import plot_utils
sys.path.append(str(Path(__file__).resolve().parent.parent))
from plot_utils import (
    COLORS, add_panel_label, set_paper_styles, add_panel_title, 
    add_legend, style_bar_axis, style_line_axis, BAR_WIDTH, 
    ALPHA_SOLID, ALPHA_MUTED, add_figure_suptitle,
    create_paper_figure, save_paper_figure, add_threshold_line
)

def load_csv(path_prefix, data_dir, os_tag):
    """Attempt to load OS-specific or fallback CSV, return list of dicts."""
    p_os = data_dir / f"{path_prefix}_{os_tag}.csv"
    p_fallback = data_dir / f"{path_prefix}.csv"
    p_cpu = data_dir / f"cpu_{path_prefix}_{os_tag}.csv"
    
    target = None
    for p in (p_cpu, p_os, p_fallback):
        if p.exists():
            target = p
            break
            
    res = []
    if target:
        with open(target, "r") as f:
            for row in csv.DictReader(f):
                res.append(row)
    return res

def main():
    set_paper_styles()
    
    repo_root = Path(__file__).resolve().parent.parent.parent.parent
    data_dir = repo_root / "paper" / "analysis_results"
    fig_dir = repo_root / "paper" / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)
    
    os_tag = "macos" if sys.platform == "darwin" else "linux"
    
    bench_res = load_csv("benchmark_results", data_dir, os_tag)
    rend_res = load_csv("rendering_results", data_dir, os_tag)
    e2e_res = load_csv("e2e_rendering_results", data_dir, os_tag)

    # 2x2 grid for the final 4-panel Figure 3
    fig, axes = create_paper_figure(2, 2, figsize=(12, 10))
    add_figure_suptitle(fig, "Figure 3: Computational Performance and Rendering Benchmarks", y=0.98)
    
    datasets = list(dict.fromkeys(r["dataset"] for r in bench_res))
    colors_map = {
        "0021 spike_detection": COLORS["blue"], 
        "0022 event_detection": COLORS["blue"]
    }
    markers_map = {
        "0021 spike_detection": "o", 
        "0022 event_detection": "s"
    }

    # =======================================================================
    # PANELS A & B: Batch Processing Execution Breakdowns
    # =======================================================================
    for col_idx, label in enumerate(datasets):
        if col_idx > 1: break # Safety limit
        
        rows = [r for r in bench_res if r["dataset"] == label]
        workers = [int(r.get("max_workers", r.get("workers", 1))) for r in rows]
        times = [float(r.get("mean_time_s", r.get("mean_wall_time_s", 0))) for r in rows]
        sem_times = [float(r.get("sem_time_s", r.get("sem_wall_time_s", 0))) for r in rows]
    
        color = colors_map.get(label, COLORS["black"])
        marker = markers_map.get(label, "o")
    
        ax_time = axes[0, col_idx]
        compute_component = [float(r.get("mean_compute_s", 0)) for r in rows]
        overhead_component = [float(r.get("mean_io_s", 0)) for r in rows]
        sem_compute_component = [float(r.get("sem_compute_s", 0)) for r in rows]
        
        # Stacked bars
        ax_time.bar(workers, compute_component, BAR_WIDTH, label="Active Compute (Bar)", color=color, alpha=ALPHA_SOLID, edgecolor="none")
        ax_time.bar(workers, overhead_component, BAR_WIDTH, bottom=compute_component, label="I/O & Overhead (Bar)", color=COLORS["very_light_grey"], alpha=ALPHA_MUTED, edgecolor="none")
        
        # Point plots connecting the top of Active Compute, matching bar color
        ax_time.errorbar(workers, compute_component, yerr=sem_compute_component, fmt="-", color=color, marker=marker, label="Compute Track", zorder=3, capsize=4)
        # Point plots connecting the top of the Stack (Total Wall Time)
        ax_time.errorbar(workers, times, yerr=sem_times, fmt="-.", color=COLORS["black"], marker="^", label="Total Wall Time", zorder=4, capsize=4)
        
        add_panel_label(ax_time, "A" if col_idx == 0 else "B")
        
        # Simple legend inside the plot, avoid redundancy
        add_legend(ax_time, loc="upper right")
        
        clean_label = label.replace("_", " ").title()
        subtitle = "Lightweight Task" if "0021" in label else "CPU-Bound Task"
        add_panel_title(ax_time, f"Execution Breakdown: {clean_label}\n({subtitle})")
        style_bar_axis(ax_time, xlabel="CPU Cores (max_workers)", ylabel="Elapsed Time (s)", xticks=workers)

    # Equally-spaced target N values for both panels C and D.
    TARGET_N = [10, 20, 30, 40, 50]

    def _ext_rend(mode_name):
        """Extract raw-rendering data and interpolate to TARGET_N."""
        rows = sorted(
            [r for r in rend_res if r["renderer_mode"] == mode_name],
            key=lambda x: int(x["n_trials"]),
        )
        if not rows:
            return [], [], []
        ns_src = np.array([int(r["n_trials"]) for r in rows])
        meds_src = np.array([float(r["mean_ms"]) for r in rows])
        sems_src = np.array([float(r["sem_ms"]) for r in rows])
        # Interpolate (or extrapolate via clamp) to TARGET_N
        ns_out, meds_out, sems_out = [], [], []
        for n in TARGET_N:
            if n < ns_src[0] or n > ns_src[-1]:
                # Clamp to nearest measured endpoint instead of extrapolating
                idx = 0 if n < ns_src[0] else -1
                ns_out.append(n)
                meds_out.append(float(meds_src[idx]))
                sems_out.append(float(sems_src[idx]))
            else:
                ns_out.append(n)
                meds_out.append(float(np.interp(n, ns_src, meds_src)))
                sems_out.append(float(np.interp(n, ns_src, sems_src)))
        return ns_out, meds_out, sems_out

    def _ext_e2e(renderer):
        """Extract full-app data at TARGET_N values that have real measurements."""
        rows = sorted(
            [r for r in e2e_res if r["renderer"] == renderer and r["benchmark_mode"] == "overlay_avg"],
            key=lambda x: int(x["n_trials"]),
        )
        ns, meds, sems = [], [], []
        for r in rows:
            n = int(r["n_trials"])
            if n in TARGET_N:
                ns.append(n)
                meds.append(float(r["mean_ms"]))
                sems.append(float(r["sem_ms"]))
        return ns, meds, sems

    # =======================================================================
    # PANEL C: Software Rendering (Raw opaque vs Full App)
    # =======================================================================
    ax_rend = axes[1, 0]
    if rend_res and e2e_res:
        # Use opaque mode for raw pyqtgraph — matches the default rendering
        # mode the application uses, giving a fair overhead comparison.
        sw_rend_n, sw_rend_med, sw_rend_sem = _ext_rend("software_opaque")
        sw_e2e_n, sw_e2e_med, sw_e2e_sem = _ext_e2e("software")

        if sw_rend_med and sw_e2e_med:
            ax_rend.errorbar(sw_rend_n, sw_rend_med, yerr=sw_rend_sem, fmt="o--", color=COLORS["black"], capsize=4, label="Raw pyqtgraph", linewidth=2)
            ax_rend.errorbar(sw_e2e_n, sw_e2e_med, yerr=sw_e2e_sem, fmt="s-", color=COLORS["blue"], capsize=4, label="Full Application", linewidth=2)

            add_legend(ax_rend, loc='upper left')
            add_panel_label(ax_rend, "C")
            add_panel_title(ax_rend, "Software Rendering Overhead\n(Raw Layer vs End-to-End)")

            style_line_axis(ax_rend, xlabel="Overlaid Trials (N)", ylabel="Latency (ms)",
                            xticks=TARGET_N, xticklabels=[str(n) for n in TARGET_N])

            add_threshold_line(ax_rend, 16.6, label="60 FPS Threshold")
            add_legend(ax_rend, loc='upper left')

    # =======================================================================
    # PANEL D: OpenGL Rendering (Raw opaque vs Full App)
    # =======================================================================
    ax_e2e = axes[1, 1]
    if rend_res and e2e_res:
        # Use opaque mode for raw pyqtgraph — consistent with Panel C.
        gl_rend_n, gl_rend_med, gl_rend_sem = _ext_rend("opengl_opaque")
        gl_e2e_n, gl_e2e_med, gl_e2e_sem = _ext_e2e("opengl")

        if gl_rend_med and gl_e2e_med:
            ax_e2e.errorbar(gl_rend_n, gl_rend_med, yerr=gl_rend_sem, fmt="o--", color=COLORS["black"], capsize=4, label="Raw pyqtgraph", linewidth=2)
            ax_e2e.errorbar(gl_e2e_n, gl_e2e_med, yerr=gl_e2e_sem, fmt="s-", color=COLORS["blue"], capsize=4, label="Full Application", linewidth=2)

            add_panel_label(ax_e2e, "D")

            add_legend(ax_e2e, loc='upper left')
            add_panel_title(ax_e2e, "OpenGL Rendering Overhead\n(Raw Layer vs End-to-End)")

            style_line_axis(ax_e2e, xlabel="Overlaid Trials (N)", ylabel="Latency (ms)",
                            xticks=TARGET_N, xticklabels=[str(n) for n in TARGET_N])

            add_threshold_line(ax_e2e, 16.6, label="60 FPS Threshold")
            add_legend(ax_e2e, loc='upper left')

    final_path = fig_dir / "figure_03.png"
    save_paper_figure(fig, final_path)
    print(f"Figure 3 (4-Panel Complete) saved to {final_path}")

if __name__ == "__main__":
    main()
