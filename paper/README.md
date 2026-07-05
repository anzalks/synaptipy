# SynaptiPy Paper Reproduction Pipeline

This directory contains the complete pipeline for reproducing the figures and benchmarks presented in the SynaptiPy paper. It is self-contained and adheres to FAIR principles of computational reproducibility.

## Folder Structure

The `paper/` directory is strictly organized into the following semantic folders:

- `envs/`: Contains dependency specs (`requirements_paper.txt`, `conda_env_macos_arm64.yml`, etc.) for exact environment reproduction.
- `data_manifest.json`: Fixed Allen Institute validation cohort and source metadata.
- `data/`: Contains the cached datasets (`allen_cache/`) downloaded automatically from the Allen Institute Cell Types Database.
- `scripts/`: Contains all analysis logic and figure generation scripts, isolated from the general `SynaptiPy` software scripts.
- `analysis_results/`: Stores all raw numerical outputs, validation benchmarks, and extracted physiological feature tables as `.csv` files.
- `figures/`: The final destination for publication-ready figures (`figure_01.png` - `figure_05.png`).
- `raw_nwb_plots/`: Stores individual cell-by-cell raw trace plots dumped during table generation for manual verification.

## Usage

First validate that all paper scripts and the dataset manifest are present:

```bash
python paper/scripts/paper_figures/generate_paper_figures.py --check-only
python paper/scripts/generate_paper_tables.py --check-only
```

To generate all data tables and figures from scratch:

1. Ensure the `synaptipy` conda environment is active (from `envs/`).
2. Run the master orchestrator script from the repository root:

```bash
conda run -n synaptipy python paper/scripts/paper_figures/generate_paper_figures.py --run-analysis
```

This will automatically:
1. Read the fixed Allen cohort from `data_manifest.json`.
2. Download required `NWB` sweeps into `data/allen_cache/`.
3. Extract benchmarking features using SynaptiPy, IPFX, and eFEL.
4. Save tabular comparisons and provenance JSON files to `analysis_results/`.
5. Plot the final overlays and save them to `figures/`.

Use `--force` to regenerate cached table outputs, `--skip-rendering-benchmark`
on machines without a usable Qt display, and `--skip-raw-plots` to avoid
cell-by-cell verification plot generation during a quick smoke run.

The Allen NWB cache can be large and is intentionally not committed to git.
Reviewer-facing provenance is written alongside generated CSV outputs so each
table can be traced to the manifest, package versions, and command-line options.
