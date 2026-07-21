# Contributing to Synaptipy

Thank you for your interest in contributing to Synaptipy! This document
describes how to set up a development environment, run tests, and submit
pull requests.

## Code of Conduct

All participants are expected to follow the [Code of Conduct](CODE_OF_CONDUCT.md).

## Getting Started

### Prerequisites

- Python 3.10, 3.11, or 3.12
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

```bash
conda run -n synaptipy python -m pytest
```

All tests should pass. On macOS, ignore the `Abort trap: 6` exit code -
check the pytest output for `N passed` and zero `FAILED` lines instead.

## Development Workflow

### 1. Create a Branch

```bash
git checkout -b feature/my-feature
```

### 2. Make Your Changes

- Follow [PEP 8](https://peps.python.org/pep-0008/) with a max line length of 120 characters.
- Use type hints throughout.
- Add docstrings to all public functions and classes.
- Keep function complexity at or below 10 (flake8 C901).
- Use standard hyphens (`-`). Never use em dashes or en dashes in code,
  documentation, or changelogs.

### 3. Format and Lint

CI enforces `black`, `isort`, and `flake8`. Run the formatters **before**
committing:

```bash
# Auto-format
black src/ tests/
isort src/ tests/

# Lint (must produce zero errors)
flake8 src/ tests/
```

Alternatively, use the convenience script:

```bash
conda run -n synaptipy python scripts/fix_style.py
```

### 4. Run Tests

```bash
conda run -n synaptipy python scripts/run_tests.py
```

Or directly with pytest:

```bash
conda run -n synaptipy python -m pytest
```

Every new analysis function needs a test in `tests/core/`. Every new GUI
behaviour needs a test in `tests/gui/`.

### 5. Submit a Pull Request

- Push your branch and open a PR against `main`.
- Provide a clear description of what your PR does and why.
- Reference any related issues (e.g., "Closes #42").
- Ensure CI passes - PRs that fail `black --check`, `isort --check`,
  `flake8`, or the test suite will not be merged.

## Adding a New Analysis Function

Synaptipy uses a registry pattern for analysis functions. To add a new
analysis:

1. Create your function in `src/synaptipy/core/analysis/`.
2. Decorate it with `@AnalysisRegistry.register(name=..., ui_params=[...], plots=[...])`.
3. Import the module in `src/synaptipy/core/analysis/__init__.py` so the
   decorator executes at package import time.
4. Add a corresponding test in `tests/core/`.

See `src/synaptipy/templates/analysis_template.py` and
`docs/extending_synaptipy.md` for the full specification.

## Writing Plugins

For analysis routines that do not belong in the core package, use the plugin
interface. Place your plugin file in `~/.synaptipy/plugins/` and use the
`@AnalysisRegistry.register` decorator. See `examples/plugins/` for working
examples.

## Reporting Issues

Use the [GitHub issue tracker](https://github.com/anzalks/synaptipy/issues).
Bug reports should include:

- Operating system and version
- Python version
- Synaptipy version
- Steps to reproduce
- Full error traceback (if applicable)

## License

By contributing to Synaptipy, you agree that your contributions will be
licensed under the [AGPL-3.0](LICENSE) license.

## Releasing a new version

Release instructions are maintained in the [developer release guide](docs/development/release_process.md).
Use the version-bump script — never edit required version strings by hand:

```bash
conda run -n synaptipy python scripts/bump_version.py 0.1.6b1 --dry-run
conda run -n synaptipy python scripts/bump_version.py 0.1.6b1
```

For a real bump, the repository must be clean and the new version must be a
forward PEP 440 version. The script performs its update, makes one local
commit, and creates one local annotated `vX.Y.Z` tag. It never pushes or starts
GitHub workflows; run local verification, review the commit, then push the
commit and tag deliberately.
