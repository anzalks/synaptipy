# Contributing to Synaptipy

Thank you for your interest in contributing to Synaptipy. This document
describes how to set up a development environment, run verification checks, and
submit pull requests.

## Code of Conduct

All participants are expected to follow the [Code of Conduct](CODE_OF_CONDUCT.md).

## Getting Started

### Prerequisites

- Python 3.10, 3.11, or 3.12 (`PySide6==6.7.3` is pinned across all platforms)
- [Anaconda](https://www.anaconda.com/download) or
  [Miniconda](https://docs.conda.io/en/latest/miniconda.html)

### Setting Up the Development Environment

```bash
# 1. Clone the repository
git clone https://github.com/anzalks/synaptipy.git
cd synaptipy

# 2. Create and activate the conda environment
conda env create -f environment.yml
conda activate synaptipy

# 3. Install in editable mode with dev dependencies
pip install -e ".[dev]"
```

### Verifying the Setup

Run the full local CI verification suite (which sets `QT_QPA_PLATFORM=offscreen`
automatically and checks formatting, linting, 90-percent test coverage, and
source hygiene):

```bash
conda run -n synaptipy python scripts/verify_ci.py
```

When running headless `pytest` directly (`QT_QPA_PLATFORM=offscreen python -m pytest`),
`tests/conftest.py` exits at session teardown via `os._exit` (POSIX) or
`TerminateProcess` (Windows) after reporting results to avoid Qt C++ destructor
races; inspect the `N passed` summary line and zero `FAILED` count.

## Development Workflow

### 1. Create a Branch

```bash
git checkout -b feature/my-feature
```

### 2. Make Your Changes

- Follow [PEP 8](https://peps.python.org/pep-0008/) with a max line length of 120 characters.
- Use type hints throughout and add docstrings to all public functions and classes.
- Keep function cyclomatic complexity at or below 10 (`flake8` C901).
- Use standard ASCII hyphens (`-`). Never use em dashes, en dashes, or emojis in
  code, documentation, commit messages, or changelogs.
- Respect layer boundaries: `src/synaptipy/core/` must remain pure Python/NumPy/SciPy
  with zero GUI (`PySide6`, `pyqtgraph`, `matplotlib.pyplot`) imports.

### 3. Format, Lint, and Verify

Run the formatters, linter, and CI verifier before committing:

```bash
conda run -n synaptipy black src/ tests/ scripts/
conda run -n synaptipy isort src/ tests/ scripts/
conda run -n synaptipy flake8 src/ tests/
conda run -n synaptipy python scripts/verify_ci.py
```

*(Note: `scripts/fix_style.py` only strips trailing whitespace on blank lines
and normalizes end-of-file newlines; always run `black`, `isort`, `flake8`, and
`scripts/verify_ci.py`.)*

### 4. Submit a Pull Request

- Push your branch and open a PR against `main`.
- Provide a clear technical summary of what changed and why, referencing related issues.
- Every core algorithm change requires unit tests in `tests/core/`; GUI changes
  require `pytest-qt` tests under `tests/gui/` or `tests/application/`.

## Extending Analyses (5-Pillar Architecture and Plugins)

Synaptipy's core Analyser UI is fixed to five consolidated pillar modules
(`passive_properties`, `single_spike`, `firing_dynamics`, `synaptic_events`,
and `evoked_responses`), plus registered signal-preprocessing processors in
`src/synaptipy/core/analysis/preprocessing.py`.

- **New specialized or experimental analyses**: Implement them as standalone
  plugin modules in `examples/plugins/` (or `~/.synaptipy/plugins/` for personal
  use) using `@AnalysisRegistry.register`. Toggle **Enable Custom Plugins** in
  **Edit > Preferences > Extensions** (or download bundled examples via
  **Help > Download Example Plugins...** in pip installations) to hot-reload
  plugins in-process.
- **Core refinements within the five pillars**: Follow the pure-logic + registry
  wrapper separation in `src/synaptipy/templates/analysis_template.py` and
  ensure outputs normalize cleanly through `AnalysisResult`
  (`src/synaptipy/core/analysis/contracts.py`).

See `docs/extending_synaptipy.md` and `docs/developer_guide.md` for complete
specifications.

## Reporting Issues

Use the [GitHub issue tracker](https://github.com/anzalks/synaptipy/issues) and
include:

- Operating system and CPU architecture (`arm64` vs `x86_64`)
- Python and Synaptipy versions
- Steps to reproduce and log output from `~/.synaptipy/logs/app.log`

## License

By contributing to Synaptipy, you agree that your contributions will be
licensed under the [AGPL-3.0](LICENSE) license.

## Releasing a New Version

Release instructions are maintained in the [developer release guide](docs/development/release_process.md).
Use the version-bump script - never edit canonical version strings by hand:

```bash
conda run -n synaptipy python scripts/bump_version.py 0.1.9 --dry-run
conda run -n synaptipy python scripts/bump_version.py 0.1.9
```
