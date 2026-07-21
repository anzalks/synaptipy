# Reproducibility Guide

This document describes how to reproduce Synaptipy's published analysis
results exactly.

## Pinned Environment

For day-to-day development, use the cross-platform install recipe:

```bash
conda env create -f environment.yml
conda activate synaptipy
pip install -e ".[dev]"
```

For exact reproduction of paper outputs on the original paper platform, use the
frozen files in `paper/envs/`:

```bash
conda env create -f paper/envs/conda_env_macos_arm64.yml
conda activate synaptipy
```

## Docker Container

For full system-level reproducibility:

```bash
docker build -t synaptipy .
docker run synaptipy validation/ -v
```

The Docker image copies `src/`, `tests/`, `validation/`, `examples/`, and
`paper/` so validation commands operate on the same tree used by reviewers.

## Paper Reproduction

The paper pipeline is manifest-driven. The fixed Allen Institute validation
cohort is listed in `paper/data_manifest.json`; NWB files are downloaded into
`paper/data/allen_cache/`, which is not committed to git.

Run lightweight checks before downloading data:

```bash
conda run -n synaptipy python paper/scripts/paper_figures/generate_paper_figures.py --check-only
conda run -n synaptipy python paper/scripts/generate_paper_tables.py --check-only
```

Regenerate tables and figures:

```bash
conda run -n synaptipy python paper/scripts/paper_figures/generate_paper_figures.py --run-analysis --force
```

Generated tables include companion provenance JSON files containing the manifest,
software versions, command-line options, and git commit.

## Random Seed Policy

Synaptipy's analysis algorithms are **fully deterministic** — no
stochastic elements are used in:
- Spike detection (threshold-based, not stochastic)
- Curve fitting (deterministic initial conditions from data statistics)
- Event detection (deterministic matched filter)
- Signal processing (IIR/FIR filters)

The only source of non-determinism is floating-point ordering in
parallel operations (disabled by default). All `curve_fit` initial
parameter estimates are derived deterministically from the input data
(e.g., initial tau estimate = time to 63% of steady-state voltage).

## Verification

After installing, verify your environment produces correct results:

```bash
conda run -n synaptipy python validation/validate_algorithms.py
```

All checks should pass with tolerances specified in the validation
scripts.

## Version Pinning Rationale

| Dependency | Pin | Reason |
|-----------|-----|--------|
| NumPy >= 2.0.0 | Uses new copy semantics; array API changes in 2.0 |
| SciPy >= 1.14.0 | `sosfiltfilt` stability improvements |
| PySide6 == 6.7.3 | Known crashes in 6.8.0 (QTBUG-130070) and 6.10.x signal-connection changes |
| Neo >= 0.14.0 | ABF2 reader fixes for multi-protocol files |
| PyNWB >= 3.1.0 | IcephysFile schema corrections |
| h5py >= 3.14.0 | Thread-safety improvements for concurrent reads |
