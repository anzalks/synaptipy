import csv
import sys
from pathlib import Path
import numpy as np

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# Add parent scripts directory to path to import plot_utils
sys.path.append(str(Path(__file__).resolve().parent.parent))
from plot_utils import COLORS, add_panel_label, set_paper_styles, add_panel_title, add_legend, style_bar_axis, style_line_axis, add_figure_suptitle

def main():
    set_paper_styles()
    
    repo_root = Path(__file__).resolve().parent.parent.parent.parent
    data_dir = repo_root / "paper" / "analysis_results"
    fig_dir = repo_root / "paper" / "figures"
    
    mac_data = {}
    sw_ov = []
    gl_ov = []
    sw_cs = None
    gl_cs = None
    
    try:
        # Check MacOS
        with open(data_dir / "e2e_rendering_results_macos.csv", "r") as f:
            for row in csv.DictReader(f):
                entry = {
                    "n_trials": int(row["n_trials"]),
                    "mean_ms": float(row["mean_ms"]),
                    "sem_ms": float(row["sem_ms"]),
                }
                if row["renderer"] == "software":
                    if row["benchmark_mode"] == "overlay_avg":
                        sw_ov.append(entry)
                    else:
                        sw_cs = entry
                elif row["renderer"] == "opengl":
                    if row["benchmark_mode"] == "overlay_avg":
                        gl_ov.append(entry)
                    else:
                        gl_cs = entry
    except FileNotFoundError:
        print("Could not find e2e_rendering_results_macos.csv. Please ensure benchmarks have run.")
        sys.exit(1)
        
    sw_ov = sorted(sw_ov, key=lambda x: x["n_trials"])
    gl_ov = sorted(gl_ov, key=lambda x: x["n_trials"])
    levels3 = [e["n_trials"] for e in sw_ov]
    
    sw_med = [e["mean_ms"] for e in sw_ov]
    sw_sem = [e["sem_ms"] for e in sw_ov]
    
    gl_med = [e["mean_ms"] for e in gl_ov]
    gl_sem = [e["sem_ms"] for e in gl_ov]
    
    fig3, (ax3a, ax3b) = plt.subplots(1, 2, figsize=(12, 4.5))
    
    # Line plot
    ax3a.errorbar(
        levels3,
        sw_med,
        yerr=sw_sem,
        fmt="s--",
        color=COLORS["red"],
        ecolor=COLORS["light_red"],
        label="Software (Mean ± SEM)",
    )
    ax3a.errorbar(
        levels3,
        gl_med,
        yerr=gl_sem,
        fmt="o-",
        color=COLORS["blue"],
        ecolor=COLORS["light_blue"],
        label="OpenGL (Mean ± SEM)",
    )
    ax3a.set_xlabel("Overlaid trials (N)")
    ax3a.set_ylabel("_update_plot() time (ms)")
    ax3a.set_xticks(levels3)
    add_legend(ax3a)
    add_panel_title(ax3a, "A. Update Time vs Overlaid Trials")
    add_panel_label(ax3a, "A")
    style_line_axis(ax3a)
    
    # Bar chart
    width = 0.35
    x3 = np.arange(len(levels3))
    ax3b.bar(
        x3 - width / 2,
        sw_med,
        width,
        label="Software (Mean ± SEM)",
        color=COLORS["red"],
        yerr=sw_sem,
        error_kw={"ecolor": COLORS["light_red"]},
    )
    ax3b.bar(
        x3 + width / 2,
        gl_med,
        width,
        label="OpenGL (Mean ± SEM)",
        color=COLORS["blue"],
        yerr=gl_sem,
        error_kw={"ecolor": COLORS["light_blue"]},
    )
    ax3b.set_xticks(x3)
    ax3b.set_xticklabels([str(n) for n in levels3])
    ax3b.set_xlabel("Overlaid trials (N)")
    ax3b.set_ylabel("Frame time (ms)")
    add_legend(ax3b)
    add_panel_title(ax3b, "B. Rendering Performance Comparison")
    add_panel_label(ax3b, "B")
    style_bar_axis(ax3b)
    
    add_figure_suptitle(fig3, "Figure 5: End-to-End Viewport Rendering Performance", y=0.98)
    fig3.tight_layout(rect=[0, 0, 1, 0.95])
    final_path = fig_dir / "figure_05.png"
    fig3.savefig(final_path, dpi=300)
    plt.close(fig3)
    print(f"Figure 5 saved to {final_path}")

if __name__ == "__main__":
    main()
