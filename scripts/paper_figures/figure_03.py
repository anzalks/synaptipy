import csv
import sys
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# Add parent scripts directory to path to import plot_utils
sys.path.append(str(Path(__file__).resolve().parent.parent))
from plot_utils import COLORS, add_panel_label, set_paper_styles, add_panel_title, add_legend, style_bar_axis, style_line_axis, add_figure_suptitle

def main():
    set_paper_styles()
    
    repo_root = Path(__file__).resolve().parent.parent.parent
    base = repo_root / "paper" / "results"
    
    import sys
    os_tag = {"darwin": "macos", "win32": "windows"}.get(sys.platform, sys.platform)
    csv_path = base / f"benchmark_results_{os_tag}.csv"
    
    if not csv_path.exists():
        csv_path = base / "benchmark_results.csv" # fallback
        
    bench_res = []
    with open(csv_path, "r") as f:
        for row in csv.DictReader(f):
            bench_res.append(row)
    
    datasets = list(dict.fromkeys(r["dataset"] for r in bench_res))
    colors = {"0021 spike_detection": COLORS["blue"], "0022 event_detection": COLORS["red"]}
    markers = {"0021 spike_detection": "o", "0022 event_detection": "s"}
    
    # Highly contrasty colors for the components
    COMP_COLOR = "#4CAF50" # Green for Compute
    IO_COLOR = "#FFC107"   # Amber for IO
    OVER_COLOR = "#E0E0E0" # Light Grey for Overhead
    
    panel_labels = ["A", "B", "C", "D"]
    
    fig1, axes1 = plt.subplots(2, 2, figsize=(14, 10))
    
    for row_idx, label in enumerate(datasets):
        rows = [r for r in bench_res if r["dataset"] == label]
        workers = [int(r["max_workers"]) for r in rows]
        times = [float(r["mean_time_s"]) for r in rows]
        sem_times = [float(r["sem_time_s"]) for r in rows]
    
        color = colors.get(label, COLORS["dark_grey"])
        marker = markers.get(label, "o")
    
        # Time plot with stacked bars
        ax_time = axes1[row_idx, 0]
        
        n_files = int(rows[0]["n_files"])
        io_component = []
        compute_component = []
        overhead_component = []
        
        sem_compute_component = []
        sem_overhead_component = []
        
        for w, t, r in zip(workers, times, rows):
            act_comp = float(r.get("mean_compute_s", 0))
            io_and_overhead = float(r.get("mean_io_s", 0))
            act_sem = float(r.get("sem_compute_s", 0))
            io_sem = float(r.get("sem_io_s", 0))
            
            compute_component.append(act_comp)
            overhead_component.append(io_and_overhead)
            sem_compute_component.append(act_sem)
            sem_overhead_component.append(io_sem)

        # Stacked bars for absolute time breakdown (Linear Scale)
        bar_width = 0.6
        ax_time.bar(workers, compute_component, bar_width, label="Active Compute Time", color=COMP_COLOR, alpha=0.9)
        ax_time.bar(workers, overhead_component, bar_width, bottom=compute_component, label="File I/O & Overhead", color=OVER_COLOR, alpha=0.8)

        # Plot tracking lines with SEM error bars
        # 1. Solid black line tracking the top of Compute
        ax_time.errorbar(
            workers,
            compute_component,
            yerr=sem_compute_component,
            fmt="k-",
            marker=marker,
            capsize=4,
            linewidth=2,
            label="Compute Track",
            zorder=3
        )
        
        # 2. Dashed black line tracking Overhead
        ax_time.errorbar(
            workers,
            overhead_component,
            yerr=sem_overhead_component,
            fmt="k--",
            marker=marker,
            capsize=4,
            linewidth=2,
            label="Overhead Track",
            zorder=3
        )

        # 3. Distinct dashed line for Total Wall Time (Grey dash-dot)
        ax_time.errorbar(
            workers,
            times,
            yerr=sem_times,
            fmt="-.",
            color="#555555",
            marker=marker,
            capsize=4,
            linewidth=2.5,
            label="Total Wall Time",
            zorder=4
        )
        
        ax_time.set_xlabel("CPU Cores (max_workers)")
        ax_time.set_ylabel("Elapsed Time (s)")
        add_panel_label(ax_time, panel_labels[row_idx * 2])
        ax_time.set_xticks(workers)
        add_legend(ax_time, loc='upper right')
        add_panel_title(ax_time, f"{label} - Execution Time Breakdown")
        style_bar_axis(ax_time)

        # Speedup plot
        ax_speedup = axes1[row_idx, 1]
        
        baseline = times[0]
        speedup = [baseline / t for t in times]
        
        # Approximate SEM for speedup: S = T1/T. Error propagation: dS/S = dT/T (assuming T1 is exact for baseline)
        sem_speedup = [s * (err / t) for s, t, err in zip(speedup, times, sem_times)]
        
        # Plot Measured Speedup with SEM
        ax_speedup.errorbar(
            workers, 
            speedup, 
            yerr=sem_speedup,
            fmt="k-", 
            marker=marker,
            capsize=4,
            linewidth=2.5, 
            label="Measured Speedup"
        )
        ax_speedup.plot(workers, [float(w) for w in workers], "--", color="#555555", linewidth=1.5, alpha=0.6, label="Ideal Linear (S=W)")
        
        ax_speedup.set_ylabel("Parallel Speedup")
        ax_speedup.set_xlabel("CPU Cores (max_workers)")
        ax_speedup.set_xticks(workers)
        
        add_legend(ax_speedup, loc='upper left')
        add_panel_label(ax_speedup, panel_labels[row_idx * 2 + 1])
        add_panel_title(ax_speedup, f"{label} - Parallel Scaling")
        style_line_axis(ax_speedup)
    
    add_figure_suptitle(fig1, "Figure 3: Multi-Core Computational Scaling & Profiling", y=0.98)
    fig1.tight_layout(rect=[0, 0, 1, 0.95])
    final_path = base / "figure_03.png"
    fig1.savefig(final_path, dpi=300)
    plt.close(fig1)
    print(f"Figure 3 saved to {final_path}")

if __name__ == "__main__":
    main()
