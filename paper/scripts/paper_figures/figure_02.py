import os
import sys
from pathlib import Path
import pandas as pd
from scipy.stats import pearsonr
import numpy as np

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# Add parent scripts directory to path to import plot_utils
sys.path.append(str(Path(__file__).resolve().parent.parent))
from plot_utils import COLORS, add_panel_label, set_paper_styles, add_panel_title, add_legend, style_scatter_axis, add_figure_suptitle

def main():
    set_paper_styles()
    
    repo_root = Path(__file__).resolve().parent.parent.parent.parent
    sys.path.insert(0, str(repo_root / "scripts"))
    data_dir = repo_root / "paper" / "analysis_results"
    fig_dir = repo_root / "paper" / "figures"
    
    bench_df = pd.read_csv(data_dir / "benchmark_comparison.csv")
    
    fig_bio, axes_bio = plt.subplots(2, 2, figsize=(12, 11))
    axes_bio = axes_bio.flatten()
    
    metrics = [
        ("Peak Voltage", "syn_peak_mV", "efel_peak_mV", "ipfx_peak_mV", "mV", "A"),
        ("Half-Width", "syn_hw_ms", "efel_hw_ms", "ipfx_hw_ms", "ms", "B"),
        ("Max dV/dt", "syn_maxdvdt", "efel_maxdvdt", "ipfx_maxdvdt", "V/s", "C"),
        ("Min dV/dt", "syn_mindvdt", "efel_mindvdt", "ipfx_mindvdt", "V/s", "D"),
    ]
    
    def format_p(p):
        if p < 0.0001:
            return "< 0.0001"
        return f"= {p:.4f}"
    
    for i, (title, c_syn, c_efel, c_ipfx, unit, panel_label) in enumerate(metrics):
        ax = axes_bio[i]
        df_valid = bench_df.dropna(subset=[c_syn, c_efel, c_ipfx])
    
        y_syn = df_valid[c_syn].values
        x_efel = df_valid[c_efel].values
        x_ipfx = df_valid[c_ipfx].values
    
        r_e, p_e = pearsonr(x_efel, y_syn)
        mb_e = np.mean(y_syn - x_efel)
    
        r_i, p_i = pearsonr(x_ipfx, y_syn)
        mb_i = np.mean(y_syn - x_ipfx)
    
        ax.scatter(
            x_efel,
            y_syn,
            color=COLORS["blue"],
            s=80,
            edgecolors="white",
            linewidths=0.75,
            label=f"eFEL\nr={r_e:.4f}, p{format_p(p_e)}\nBias: {mb_e:+.2f}",
        )
    
        ax.scatter(
            x_ipfx,
            y_syn,
            color=COLORS["red"],
            s=80,
            edgecolors="white",
            linewidths=0.75,
            marker="s",
            label=f"IPFX\nr={r_i:.4f}, p{format_p(p_i)}\nBias: {mb_i:+.2f}",
            zorder=3
        )
        
        ax.scatter(
            y_syn,
            y_syn,
            color="black",
            s=80,
            edgecolors="white",
            linewidths=0.75,
            marker="^",
            label="SynaptiPy",
            zorder=4
        )
    
        # Remove manual lims/unity plotting here since style_scatter_axis can handle it
        min_val = min(np.min(y_syn), np.min(x_efel), np.min(x_ipfx))
        max_val = max(np.max(y_syn), np.max(x_efel), np.max(x_ipfx))
        margin = (max_val - min_val) * 0.1
        lims = [min_val - margin, max_val + margin]
    
        ax.set_xlabel(f"Benchmark Value ({unit})")
        ax.set_ylabel(f"SynaptiPy Value ({unit})")
        
        # Apply standard typography
        add_panel_title(ax, title)
        add_panel_label(ax, panel_label)
        add_legend(ax, loc="best", markerscale=0.7)
        
        # Apply standard axis styles
        style_scatter_axis(ax, unity_line=True, lims=lims)
    
    add_figure_suptitle(fig_bio, "Biological Validation: Feature Extraction Benchmark", y=0.98)
    fig_bio.tight_layout(rect=[0, 0, 1, 0.95])
    final_path = fig_dir / "figure_02.png"
    fig_bio.savefig(final_path, dpi=300)
    plt.close(fig_bio)
    print(f"Figure 2 saved to {final_path}")

if __name__ == "__main__":
    main()
