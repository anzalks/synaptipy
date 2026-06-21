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
    
    opengl_data = {}
    software_data = {}
    with open(data_dir / "rendering_results.csv", "r") as f:
        for row in csv.DictReader(f):
            mode = row.get("renderer", row.get("renderer_mode"))
            n = int(row["n_trials"])
            stats = {"mean_ms": float(row["mean_ms"]), "sem_ms": float(row["sem_ms"])}
            if mode == "opengl" or mode == "opengl_transparent":
                opengl_data[n] = stats
            elif mode == "software" or mode == "software_transparent":
                software_data[n] = stats
    
    levels = sorted(opengl_data.keys())
    med_gl = [opengl_data[n]["mean_ms"] for n in levels]
    sem_gl = [opengl_data[n]["sem_ms"] for n in levels]
    
    med_sw = [software_data[n]["mean_ms"] for n in levels]
    sem_sw = [software_data[n]["sem_ms"] for n in levels]
    
    fig2, (ax_abs, ax_ratio) = plt.subplots(1, 2, figsize=(12, 4.5))
    
    # Line plot
    ax_abs.errorbar(
        levels,
        med_gl,
        yerr=sem_gl,
        fmt="o-",
        color=COLORS["blue"],
        ecolor=COLORS["light_blue"],
        label="OpenGL (Mean ± SEM)",
    )
    ax_abs.errorbar(
        levels,
        med_sw,
        yerr=sem_sw,
        fmt="s--",
        color=COLORS["red"],
        ecolor=COLORS["light_red"],
        label="Software (Mean ± SEM)",
    )
    ax_abs.set_xlabel("Overlaid trials (N)")
    ax_abs.set_ylabel("Per-frame update time (ms)")
    ax_abs.set_xticks(levels)
    add_legend(ax_abs)
    add_panel_title(ax_abs, "A. Update Time vs Overlaid Trials")
    add_panel_label(ax_abs, "A")
    style_line_axis(ax_abs)
    
    # Bar chart
    width = 0.35
    x = np.arange(len(levels))
    ax_ratio.bar(
        x - width / 2,
        med_sw,
        width,
        label="Software (Mean ± SEM)",
        color=COLORS["red"],
        yerr=sem_sw,
        error_kw={"ecolor": COLORS["light_red"]},
    )
    ax_ratio.bar(
        x + width / 2,
        med_gl,
        width,
        label="OpenGL (Mean ± SEM)",
        color=COLORS["blue"],
        yerr=sem_gl,
        error_kw={"ecolor": COLORS["light_blue"]},
    )
    ax_ratio.set_xticks(x)
    ax_ratio.set_xticklabels([str(n) for n in levels])
    ax_ratio.set_xlabel("Overlaid trials (N)")
    ax_ratio.set_ylabel("Per-frame update time (ms)")
    add_legend(ax_ratio)
    add_panel_title(ax_ratio, "B. Rendering Performance Comparison")
    add_panel_label(ax_ratio, "B")
    style_bar_axis(ax_ratio)
    
    add_figure_suptitle(fig2, "Figure 4: GUI Viewport Rendering Performance", y=0.98)
    fig2.tight_layout(rect=[0, 0, 1, 0.95])
    final_path = fig_dir / "figure_04.png"
    fig2.savefig(final_path, dpi=300)
    plt.close(fig2)
    print(f"Figure 4 saved to {final_path}")

if __name__ == "__main__":
    main()
