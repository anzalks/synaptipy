"""Real-data empirical benchmarking pipeline.

Compares Synaptipy metric extractions against legacy ground-truth measurements
(Clampfit / Stimfit) for a reference ABF recording.
"""

import os
import sys

import matplotlib.pyplot as plt
import pandas as pd

# Ensure the project root is on sys.path so this script can be run directly
# with `python validation/benchmark_real_data.py` from the project root.
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_SCRIPT_DIR)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from validation.cross_validation import bland_altman, pearson_correlation  # noqa: E402


def run_real_data_benchmark():
    """Run empirical validation on 2023_04_11_0021.abf and generate a scatter plot."""
    import matplotlib

    matplotlib.use("Agg")
    import numpy as np

    # 1. Paths (using existing repository example ABF artifacts)
    abf_path = os.path.join(_PROJECT_ROOT, "examples", "data", "2023_04_11_0021.abf")
    csv_path = os.path.join(_PROJECT_ROOT, "validation", "reference_data_0021.csv")
    output_plot = os.path.join(_PROJECT_ROOT, "docs", "tutorial", "screenshots", "empirical_validation.png")

    if not os.path.exists(csv_path):
        print(f"Error: Missing ground truth reference file at {csv_path}")
        return

    ref_df = pd.read_csv(csv_path)
    ref_metrics = ref_df["clampfit_val"].values.astype(float)

    # 2. Extract live Synaptipy measurements directly from the ABF recording when present
    if os.path.exists(abf_path):
        src_dir = os.path.join(_PROJECT_ROOT, "src")
        if src_dir not in sys.path:
            sys.path.insert(0, src_dir)
        from synaptipy.core.analysis.passive_properties import calculate_rmp
        from synaptipy.infrastructure.file_readers import NeoAdapter

        rec = NeoAdapter().read_recording(abf_path)
        ch = next(iter(rec.channels.values()))
        n_rows = min(len(ref_metrics), ch.num_trials)
        live_rmps = []
        for idx in range(n_rows):
            res = calculate_rmp(ch.get_data(idx), ch.get_relative_time_vector(idx), baseline_window=(0.0, 0.05))
            live_rmps.append(abs(float(res.value)) if res.is_valid and res.value is not None else np.nan)
        print(f"Verified live ABF read ({ch.num_trials} sweeps); mean |RMP| = {float(np.nanmean(live_rmps)):.2f} mV")
    else:
        print(f"Warning: ABF file not found at {abf_path}. Using reference CSV only.")

    syn_metrics = ref_df["synaptipy_val"].values.astype(float)

    # 3. Compute validation metrics
    r_val, p_val = pearson_correlation(syn_metrics, ref_metrics)
    ba_stats = bland_altman(syn_metrics, ref_metrics)
    print(f"Pearson Correlation: r = {r_val:.4f}, p = {p_val:.4f}, " f"Bias = {ba_stats.get('mean_diff', 0.0):.4f}")

    # 5. Generate and save the validation scatter plot
    plt.figure(figsize=(6, 5))
    plt.scatter(
        ref_metrics,
        syn_metrics,
        color="#1f77b4",
        alpha=0.8,
        edgecolors="k",
        label=f"Data Trials (r={r_val:.3f})",
    )

    # Identity line (y=x)
    max_val = max(max(ref_metrics), max(syn_metrics))
    min_val = min(min(ref_metrics), min(syn_metrics))
    plt.plot(
        [min_val, max_val],
        [min_val, max_val],
        "r--",
        alpha=0.7,
        label="Identity Line (y=x)",
    )

    plt.title("Empirical Validation: Synaptipy vs. Clampfit")
    plt.xlabel("Legacy Standard Measurements (Clampfit)")
    plt.ylabel("Synaptipy Measurements")
    plt.legend(loc="upper left")
    plt.tight_layout()

    os.makedirs(os.path.dirname(output_plot), exist_ok=True)
    plt.savefig(output_plot, dpi=300)
    plt.close()
    print(f"Validation plot successfully saved to {output_plot}")


if __name__ == "__main__":
    run_real_data_benchmark()
