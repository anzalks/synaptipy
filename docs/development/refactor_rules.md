# Refactor and Publication Rules

This document is the standing contract for refactoring Synaptipy before a
methods publication or release. It answers three questions reviewers and future
contributors should not have to infer from code history: where code belongs,
what behavior must remain stable, and what evidence is required before merging.

## Layer Boundaries

### `src/synaptipy/core/`

Core contains the scientific model and numerical behavior.

- Keep it GUI-free: no `PySide6`, `pyqtgraph`, widgets, dialogs, clipboard, or
  application window imports.
- Put analysis algorithms in `core/analysis/` and register public analyses with
  `@AnalysisRegistry.register`.
- Put reusable signal operations in `signal_processor.py` or
  `processing_pipeline.py` when they are not tied to a single analysis module.
- Return explicit metrics and flags rather than raising for biologically invalid
  traces. Invalid fits should produce `NaN` plus a reason/quality flag where the
  surrounding API already supports one.
- Preserve deterministic behavior. Random data belongs only in tests or
  examples and must use a fixed generator seed.

### `src/synaptipy/infrastructure/`

Infrastructure owns external formats and serialization.

- File reading belongs in `infrastructure/file_readers/`.
- CSV/NWB/Prism export belongs in `infrastructure/exporters/`.
- Do not put electrophysiology algorithms here. Convert external data into
  `Recording`/`Channel` objects, then call core code.
- Exported tabular outputs must preserve provenance: source file, channel, trial,
  analysis name, parameters, software version, and timestamp.
- NWB exports must remain schema-valid and should prefer standard icephys
  containers before custom processing tables.

### `src/synaptipy/application/`

Application owns user workflows.

- GUI widgets, dialogs, Qt workers, controllers, plugin loading, preferences, and
  sessions stay here.
- GUI code may call core and infrastructure code; core and infrastructure must
  not call GUI code.
- Long operations must run off the UI thread.
- Interactive parameters must map to the same dictionary shape used by
  `BatchAnalysisEngine`, so GUI and headless runs stay equivalent.
- Headless reviewer/reproduction workflows belong in `application/cli/`, not in
  GUI classes.

### `src/synaptipy/shared/`

Shared is for cross-cutting helpers.

- Use it for constants, logging, cache helpers, theme/plot utilities, and small
  functions reused across layers.
- Do not hide domain algorithms in `shared`; move them to `core`.
- Keep names specific. A helper that only one module uses should usually stay
  beside that module.

### `paper/`, `validation/`, `examples/`, and `docs/`

- `paper/` contains reproducibility scripts, data manifests, generated paper
  figures, and paper-specific environment files.
- `validation/` contains independent checks and reports for algorithmic accuracy.
- `examples/` contains user-facing demonstrations and small fixture recordings.
- `docs/` contains source documentation. Generated docs stay out of commits.

## Expected Behavior That Must Not Regress

- `pip install -e ".[dev]"` exposes `synaptipy` and `synaptipy-batch`.
- `python -m synaptipy --version` prints the package version.
- `synaptipy-batch run --pipeline PIPELINE.json --output results.csv FILE...`
  writes a CSV and companion provenance JSON without importing GUI widgets.
- `BatchAnalysisEngine` must accept the same pipeline dictionaries used by the
  GUI.
- Batch rows must remain traceable to file, channel, trial, scope, analysis, and
  sampling rate.
- CSV and NWB exports must not silently drop source/provenance metadata.
- Paper reproduction must have a lightweight `--check-only` path that validates
  scripts and manifests without requiring AllenSDK downloads.
- Paper table generation must be manifest-driven, not hidden in hardcoded IDs.

## Refactor Rules

1. Keep behavior changes separate from mechanical moves when possible.
2. If an algorithm changes, update the algorithmic definition, golden tests, and
   paper/validation outputs in the same pull request.
3. If a public metric key changes, either preserve the old key as an alias or
   document the breaking change in `CHANGELOG.md`.
4. If a dependency pin changes, document why and run the CI matrix or the
   closest available local subset.
5. Do not add new generated outputs unless they are intentionally publication
   artifacts.
6. Do not add hidden data selection criteria in scripts. Put them in a manifest.
7. Prefer narrow helpers over broad abstractions unless two or more modules need
   the same behavior.
8. Every reviewer-facing script should support `--help`; expensive scripts should
   also support `--check-only` or a tiny smoke mode.

## Merge Checklist

- Formatting: `black src/ tests/` and `isort src/ tests/`
- Static checks: `flake8 src/ tests/`
- Core tests: `python -m pytest tests/core tests/infrastructure`
- GUI-sensitive tests: run with `QT_QPA_PLATFORM=offscreen` or `xvfb-run`
- Paper smoke check:

```bash
conda run -n synaptipy python paper/scripts/paper_figures/generate_paper_figures.py --check-only
conda run -n synaptipy python paper/scripts/generate_paper_tables.py --check-only
```

- Reproduction evidence: attach or commit updated provenance JSON when paper
  tables/figures are regenerated intentionally.
