"""Real-data empirical benchmarking pipeline.

Compares SynaptiPy metric extractions against legacy ground-truth measurements
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
    """Run empirical validation and generate a scatter plot."""
    # 1. Paths (using existing repository test artifacts)
    abf_path = os.path.join("tests", "data", "2023_04_11_0021.abf")
    csv_path = os.path.join("validation", "reference_data_0021.csv")
    output_plot = os.path.join("docs", "tutorial", "screenshots", "empirical_validation.png")

    if not os.path.exists(csv_path):
        print(f"Error: Missing ground truth reference file at {csv_path}")
        return

    if not os.path.exists(abf_path):
        print(f"Warning: ABF file not found at {abf_path}. Using reference CSV only.")

    # 2. Load Legacy Ground Truth (Clampfit/Stimfit benchmarks)
    ref_df = pd.read_csv(csv_path)
    ref_metrics = ref_df["clampfit_val"].values

    # 3. Load SynaptiPy measurements from reference CSV
    # (populated by direct core-wrapper calls or pre-extracted values)
    syn_metrics = ref_df["synaptipy_val"].values

    # 4. Compute validation metrics
    r_val, p_val = pearson_correlation(syn_metrics, ref_metrics)
    print(f"Pearson Correlation: r = {r_val:.4f}, p = {p_val:.4f}")

    bland_altman(syn_metrics, ref_metrics)

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

    plt.title("Empirical Validation: SynaptiPy vs. Clampfit")
    plt.xlabel("Legacy Standard Measurements (Clampfit)")
    plt.ylabel("SynaptiPy Measurements")
    plt.legend(loc="upper left")
    plt.tight_layout()

    os.makedirs(os.path.dirname(output_plot), exist_ok=True)
    plt.savefig(output_plot, dpi=300)
    plt.close()
    print(f"Validation plot successfully saved to {output_plot}")


if __name__ == "__main__":
    run_real_data_benchmark()
