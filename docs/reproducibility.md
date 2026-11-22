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

For full system-level reproducibility, build the Docker image (whose default
entrypoint is `python -m pytest` with `QT_QPA_PLATFORM=offscreen`):

```bash
docker build -t synaptipy .

# Run the automated pytest suite (default container command):
docker run synaptipy

# Execute the standalone algorithmic validation scripts:
docker run --entrypoint python synaptipy validation/validate_algorithms.py
```

The Docker image copies `src/`, `tests/`, `validation/`, `examples/`, and
`paper/` so test and validation commands operate on the exact tree used by
reviewers.

## Headless CLI Batch Execution

Headless pipelines can be replayed deterministically from the command line
using `synaptipy-batch`:

```bash
# List all registered built-in, preprocessing, and plugin analyses:
synaptipy-batch list-analyses

# Execute a JSON pipeline across recordings and write CSV + provenance JSON:
synaptipy-batch run data/*.abf \
    --pipeline pipeline.json \
    --output results/summary.csv \
    --channel Vm_prime \
    --max-workers 1
```

Every `synaptipy-batch run` invocation writes a companion
`<stem>_provenance.json` file alongside `<stem>.csv` (for example,
`results/summary_provenance.json`). The provenance record captures
`generated_at_utc`, `synaptipy_version`, `command`, `input_files`,
`pipeline_file`, the full resolved `pipeline` task list, `channel_filter`,
`max_workers`, and `cross_file_average` so any exported table can be audited
and re-run verbatim.

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

Synaptipy's analysis algorithms are **fully deterministic** - no
stochastic elements are used in:
- Spike detection (threshold-based, not stochastic)
- Curve fitting (deterministic initial conditions from data statistics)
- Event detection (deterministic matched filter)
- Signal processing (IIR/FIR filters)

The only source of non-determinism is floating-point ordering in
parallel operations (disabled by default when `max_workers=1`). All `curve_fit`
initial parameter estimates are derived deterministically from the input data
(for example, the initial membrane tau estimate is computed via ordinary
least-squares linear regression on `log(|V - V_ss|)` versus time as
`-1.0 / slope`, clipped to `tau_bounds`, with a deterministic `10 ms` fallback
when the log-linear fit is degenerate).

## Verification

After installing, verify your environment produces expected results:

```bash
conda run -n synaptipy python validation/validate_algorithms.py
```

All checks should pass within the tolerances specified in the validation
scripts.

## Analysis Provenance and Eligibility

Synaptipy records the selected trials for batch analyses. Time-aware averages
interpolate eligible trials on a shared relative time axis and retain the
number of contributors at each sample. Empty traces, non-finite samples,
invalid time axes, and explicitly excluded trials are retained as quality
control decisions rather than silently contributing to an average.

Stimulus-locked analyses require recorded timing evidence or verified manual
stimulus times in the Protocol Map. A voltage trace is not treated as a TTL
signal when timing data are absent.

For Neo-loaded recordings, Synaptipy retains ABF command waveforms obtained
from the reader and pulse onsets from channels whose native labels explicitly
identify TTL or stimulation timing. These appear as unverified Protocol Map
annotations. The import does not classify a waveform as a current-step,
paired-pulse, train, or optogenetic experiment: that experimental context must
be selected and reviewed by the scientist before it becomes an analysis
segment. This preserves useful acquisition evidence without making a semantic
claim that the file alone cannot support.

Every figure export writes a JSON sidecar next to the figure. It records the
export format, DPI, source recording metadata, and the analysis context passed
by the application, including visible trial selection where available.

## File-format Validation Tiers

ABF and NWB are validated Synaptipy acquisition formats. Their reader,
analysis, batch, and export paths have dedicated test coverage. Other formats
discoverable through Neo are experimental until they receive equivalent
end-to-end fixtures and validation tests. The extension list therefore
describes reader discovery, not equal validation status for every format.

### Empirical Comparison Example

![Example empirical comparison with Clampfit](tutorial/screenshots/empirical_validation.png)

`validation/benchmark_real_data.py` generates this comparison from its fixed
benchmark inputs. It is an example validation artifact, not a claim that every
recording or every analysis method will agree exactly with another package;
inspect the script, inputs, and its recorded tolerances when reproducing it.

## Version Pinning Rationale

| Dependency | Pin | Reason |
|-----------|-----|--------|
| NumPy >= 2.0.0 | Uses new copy semantics; array API changes in 2.0 |
| SciPy >= 1.14.0 | `sosfiltfilt` stability improvements |
| PySide6 == 6.7.3 | Known crashes in 6.8.0 (QTBUG-130070) and 6.10.x signal-connection changes |
| Neo >= 0.14.0 | ABF2 reader fixes for multi-protocol files |
| PyNWB >= 3.1.0 | IcephysFile schema corrections |
| h5py >= 3.14.0 | Thread-safety improvements for concurrent reads |
