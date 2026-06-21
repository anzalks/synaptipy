import csv
import sys
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# Add parent scripts directory to path to import plot_utils
sys.path.append(str(Path(__file__).resolve().parent.parent))
from plot_utils import COLORS, add_panel_label, set_paper_styles, add_panel_title, add_legend, style_bar_axis, style_line_axis, BAR_WIDTH, ALPHA_SOLID, ALPHA_MUTED, ALPHA_FAINT

def main():
    set_paper_styles()
    
    repo_root = Path(__file__).resolve().parent.parent.parent.parent
    data_dir = repo_root / "paper" / "analysis_results"
    fig_dir = repo_root / "paper" / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)
    
    os_tag = "macos" if sys.platform == "darwin" else "linux"
    
    csv_cpu = data_dir / f"cpu_benchmark_results_{os_tag}.csv"
    if not csv_cpu.exists():
        csv_cpu = data_dir / f"benchmark_results_{os_tag}.csv"
    if not csv_cpu.exists():
        csv_cpu = data_dir / "benchmark_results.csv" # fallback
        
    bench_res = []
    with open(csv_cpu, "r") as f:
        for row in csv.DictReader(f):
            bench_res.append(row)
    
    datasets = list(dict.fromkeys(r["dataset"] for r in bench_res))
    
    # We map datasets to line markers and colors based on eNeuro guidelines
    colors_map = {
        "0021 spike_detection": COLORS["blue"], 
        "0022 event_detection": COLORS["dark_grey"]
    }
    markers_map = {
        "0021 spike_detection": "o", 
        "0022 event_detection": "s"
    }
    
    # Colors for the components
    COMP_COLOR = COLORS["blue"] # Blue for Compute
    OVER_COLOR = COLORS["very_light_grey"] # Light Grey for Overhead
    
    panel_labels = ["A", "B", "C", "D"]
    
    fig, axes = plt.subplots(2, 2, figsize=(14, 11))
    
    for row_idx, label in enumerate(datasets):
        rows = [r for r in bench_res if r["dataset"] == label]
        workers = [int(r.get("max_workers", r.get("workers", 1))) for r in rows]
        times = [float(r.get("mean_time_s", r.get("mean_wall_time_s", 0))) for r in rows]
        sem_times = [float(r.get("sem_time_s", r.get("sem_wall_time_s", 0))) for r in rows]
    
        color = colors_map.get(label, COLORS["black"])
        marker = markers_map.get(label, "o")
    
        # Time plot with stacked bars
        ax_time = axes[row_idx, 0]
        
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
        ax_time.bar(workers, compute_component, BAR_WIDTH, label="Active Compute Time", color=COMP_COLOR, alpha=ALPHA_SOLID, edgecolor="none")
        ax_time.bar(workers, overhead_component, BAR_WIDTH, bottom=compute_component, label="File I/O & Overhead", color=OVER_COLOR, alpha=ALPHA_MUTED, edgecolor="none")

        # Plot tracking lines with SEM error bars based on exactly what the old script did
        # 1. Solid black line tracking the top of Compute
        ax_time.errorbar(
            workers,
            compute_component,
            yerr=sem_compute_component,
            fmt="-",
            color=color,
            marker=marker,
            label="Compute Track",
            zorder=3,
            capsize=6
        )
        
        # 2. Dashed black line tracking Overhead
        ax_time.errorbar(
            workers,
            overhead_component,
            yerr=sem_overhead_component,
            fmt="--",
            color=color,
            marker=marker,
            label="Overhead Track",
            zorder=3,
            capsize=6
        )

        # 3. Distinct dashed line for Total Wall Time
        ax_time.errorbar(
            workers,
            times,
            yerr=sem_times,
            fmt="-.",
            color=COLORS["black"],
            marker="^",
            label="Total Wall Time",
            zorder=4,
            capsize=6
        )
        
        ax_time.set_xlabel("CPU Cores (max_workers)")
        ax_time.set_ylabel("Elapsed Time (s)")
        add_panel_label(ax_time, panel_labels[row_idx * 2])
        ax_time.set_xticks(workers)
        add_legend(ax_time, loc='upper right')
        add_panel_title(ax_time, f"{label} - Execution Time Breakdown")
        style_bar_axis(ax_time)

        # Speedup plot
        ax_speedup = axes[row_idx, 1]
        
        baseline = times[0]
        speedup = [baseline / t for t in times]
        
        sem_speedup = [s * (err / t) for s, t, err in zip(speedup, times, sem_times)]
        
        # Plot Measured Speedup with SEM
        ax_speedup.errorbar(
            workers, 
            speedup, 
            yerr=sem_speedup,
            fmt="-",
            color=color,
            marker=marker,
            label="Measured Speedup",
            capsize=6
        )
        ax_speedup.plot(workers, [float(w) for w in workers], "--", color=COLORS["dark_grey"], alpha=ALPHA_FAINT, label="Ideal Linear (S=W)")
        
        ax_speedup.set_ylabel("Parallel Speedup")
        ax_speedup.set_xlabel("CPU Cores (max_workers)")
        ax_speedup.set_xticks(workers)
        
        add_legend(ax_speedup, loc='upper left')
        add_panel_label(ax_speedup, panel_labels[row_idx * 2 + 1])
        add_panel_title(ax_speedup, f"{label} - Parallel Scaling")
        style_line_axis(ax_speedup)
    
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    final_path = fig_dir / "figure_03.png"
    fig.savefig(final_path, dpi=300)
    plt.close(fig)
    print(f"Figure 3 saved to {final_path}")

if __name__ == "__main__":
    main()
