# Synaptipy Developer Guide

This guide is intended for developers who want to understand, modify, or contribute to Synaptipy.

## Table of Contents

- [Development Environment Setup](#development-environment-setup)
- [Project Structure](#project-structure)
- [Writing Custom Analysis Plugins](#writing-custom-analysis-plugins)
- [Development Workflow](#development-workflow)
- [Testing](#testing)
- [CI Behaviour and Platform-Specific Test Rules](#ci-behaviour-and-platform-specific-test-rules)
- [Coding Standards](#coding-standards)
- [License Compliance](#license-compliance)

## Development Environment Setup

### Prerequisites

- Python 3.10+
- Git
- pip or conda package manager

### Setting Up Your Development Environment

1. Clone the repository:
   ```bash
   git clone https://github.com/anzalks/synaptipy.git
   cd synaptipy
   ```

2. Create and activate the conda environment:
   ```bash
   conda env create -f environment.yml
   conda activate synaptipy
   ```

3. Install in development mode:
   ```bash
   pip install -e ".[dev]"
   ```

This will install Synaptipy in development mode with all development dependencies.

## Project Structure

The Synaptipy codebase is organized as follows:

```
src/Synaptipy/                  # Main package
├── __init__.py                 # Package initialization
├── __main__.py                 # Entry point for CLI
├── application/                # GUI application components
│   ├── app.py                  # Main application entry
│   └── gui/                    # UI components and tabs
├── core/                       # Core data structures and analysis
│   ├── data_model.py           # Recording and Channel classes
│   ├── results.py              # Typed result dataclasses
│   └── analysis/               # Analysis algorithms
│       ├── intrinsic_properties.py  # Rin, tau, conductance, sag ratio, I-V curve
│       ├── spike_analysis.py        # Spike detection and features
│       ├── basic_features.py        # RMP, baseline statistics
│       ├── excitability.py          # F-I curve
│       ├── burst_analysis.py        # Burst detection
│       ├── phase_plane.py           # Phase-plane analysis
│       └── ...                      # Additional analysis modules
├── infrastructure/             # Supporting components
│   ├── file_readers/           # Data file readers
│   └── exporters/              # Data exporters
└── shared/                     # Shared utilities
    ├── constants.py            # Constants used across the package
    └── error_handling.py       # Custom error classes

tests/                          # Test suite
├── conftest.py                 # Pytest fixtures
├── application/                # Application tests
├── core/                       # Core module tests
└── infrastructure/             # Infrastructure tests

scripts/                        # Utility scripts
└── run_tests.py                # Test runner script

docs/                           # Documentation
examples/                       # Example scripts
```

## Writing Custom Analysis Plugins

Synaptipy supports two ways to add new analysis functions:

1. **User plugins (no source edits):** Drop a `.py` file in `~/.synaptipy/plugins/`.
   The file is auto-discovered at startup and your analysis appears as a new
   Analyser tab.  This is the recommended approach for end users.

2. **Built-in modules (core contributors):** Add a module to
   `src/Synaptipy/core/analysis/`, register the import in `__init__.py`,
   and add tests.

A ready-to-copy template is at `src/Synaptipy/templates/plugin_template.py`.
For the complete reference — including all `ui_params` types, `plots` types,
return-dict conventions, `visible_when` rules, and a fully annotated example —
see the dedicated guide: **[Writing Custom Analysis Plugins](extending_synaptipy.md)**.

## Development Workflow

### Feature Development

1. **Create a branch**: For new features or bug fixes, create a branch:
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Implement changes**: Make your changes in the relevant files

3. **Add tests**: Write tests for your new code

4. **Run tests**: Ensure all tests pass:
   ```bash
   python scripts/run_tests.py
   ```

5. **Submit a pull request**: Push your branch and create a pull request

### Code Review Process

All contributions go through code review. Maintainers will review your code for:

- Functionality
- Test coverage
- Code style
- Documentation

## Testing

### Running Tests

Run the full test suite:

```bash
python scripts/run_tests.py
```

Run specific tests:

```bash
python scripts/run_tests.py --test test_main_window
```

Run with coverage reporting:

```bash
python scripts/run_tests.py --coverage
```

### Writing Tests

- Place tests in the appropriate subdirectory of the `tests/` folder
- Name test files with `test_` prefix
- Use pytest fixtures for setup and teardown
- Mock external dependencies where appropriate

## CI Behaviour and Platform-Specific Test Rules

The test suite involves PySide6 and pyqtgraph widgets running under
`QT_QPA_PLATFORM=offscreen`.  Several platform-specific crash patterns have been
resolved; the rules below **must not be reverted** or the CI will break again.

### Analysis Registry import rule — DO NOT import only registry.py

To populate the `AnalysisRegistry`, **always import the full package**:
```python
import Synaptipy.core.analysis  # triggers __init__.py → from . import basic_features, etc.
```

**Never** rely on `from Synaptipy.core.analysis.registry import AnalysisRegistry`
alone — that only imports the registry *class* and does NOT execute the analysis
sub-modules' `@AnalysisRegistry.register` decorators.

This was the root cause of a Windows-only bug where the Analyser tab showed 0
tabs while macOS showed 15: on macOS the batch engine happened to import the
full package earlier via a different path (masking the issue), but on Windows no
other code path triggered the import and the registry remained empty.

The fix is in two places:
- `startup_manager._begin_loading()` — imports the full package before building
  the GUI so the registry is pre-populated.
- `analyser_tab._load_analysis_tabs()` — imports the full package immediately
  before calling `AnalysisRegistry.list_registered()` as a safety net.

### Editable install must point to the active workspace

`pip install -e .` stores the editable project location.  If the repo is cloned
to a new directory, the old editable link still points to the previous path.
Run `pip install -e .` **from the new workspace** to update.

Symptom: modules visible on disk (e.g. `capacitance.py`, `optogenetics.py`,
`train_dynamics.py`) throw `ModuleNotFoundError` because Python resolves the
package from the stale path.  Verify with:
```bash
pip show Synaptipy | grep "Editable project location"
```

### Why local macOS tests always exit non-zero

`pytest_sessionfinish` in `tests/conftest.py` calls `os._exit(exitstatus)` when
`QT_QPA_PLATFORM=offscreen` is set.  This causes the macOS process to terminate
with a `QThread: Destroyed while thread is still running` message and an
`Abort trap: 6` printed by the shell — **even when every test passed**.  The
exit code written to the OS is the real pytest exit code (0 = all passed).  The
shell may still report exit code 1 because conda intercepts the abnormal
termination.

**Rule:** Do not judge local macOS test runs by the shell exit code or the
`Abort trap` message.  Always check the pytest output lines (`N passed`, no
`FAILED`) or use:
```bash
conda run -n synaptipy python -m pytest tests/ 2>&1 | grep -c PASSED
conda run -n synaptipy python -m pytest tests/ 2>&1 | grep "FAILED\|ERROR "
```

### GC must be disabled in offscreen mode

`pytest_configure` disables Python's cyclic GC when `QT_QPA_PLATFORM=offscreen`
(see `tests/conftest.py`).  Do **not** remove this.  With GC enabled, Python can
trigger `tp_dealloc` on PySide6 wrapper objects while Qt's C++ destructor chain
is still running, causing `SIGBUS` on macOS and access violations on Windows.

### processEvents() before addPlot() in offscreen mode

`SynaptipyPlotCanvas.add_plot()` calls
`QCoreApplication.processEvents()` before `widget.addPlot()` when
`QT_QPA_PLATFORM=offscreen`.  This **must not be removed**.  On Windows +
PySide6 ≥ 6.9, deferred callbacks queued by a prior `widget.clear()` or widget
construction fire *inside* `PlotItem.__init__()` if they are still pending,
dereferences freed C++ pointers, and causes an access violation that silently
kills the test worker process (all remaining tests never run).

Using `processEvents()` (execute callbacks) rather than `removePostedEvents()`
(discard callbacks) is intentional:
- `removePostedEvents` on macOS discards events that pyqtgraph needs to maintain
  its `AllViews` registry and internal geometry caches; discarding them corrupts
  session-scoped widget state and causes segfaults in `widget.clear()` on the
  next test.
- `processEvents` is safe on all platforms.

### removePostedEvents() must skip macOS

The global `_drain_qt_events_after_test` fixture in `tests/conftest.py` and the
per-file drain in `tests/application/gui/test_explorer_refactor.py` both guard
the `removePostedEvents(None, 0)` call with `if sys.platform != 'darwin': return`.
Do **not** remove this guard.  On macOS, draining the global event queue between
tests discards pyqtgraph's internal range/layout events and corrupts
`ViewBox` geometry caches, causing later `widget.clear()` calls to segfault.

### enableMenu=False in offscreen mode

`SynaptipyPlotCanvas.add_plot()` passes `enableMenu=False` to `widget.addPlot()`
when `QT_QPA_PLATFORM=offscreen`.  This prevents `ViewBoxMenu.__init__` from
calling `QWidgetAction`, which crashes PySide6 on Windows and macOS when there
is no real display available.

### Plot teardown order

`SynaptipyPlotCanvas.clear_plots()` must follow this exact sequence:
1. `_unlink_all_plots()` — break `setXLink` / `setYLink` connections before teardown.
2. `_close_all_plots()` — disconnect ctrl signals and call `PlotItem.close()`
   while the scene is still valid.
3. `_cancel_pending_qt_events()` — discard stale events (Win/Linux only).
4. `widget.clear()` — destroy C++ layout children via Qt's scene graph.
5. `plot_items.clear()` — drop Python references *after* C++ teardown.
6. `_flush_qt_registry()` — discard any events posted *by* `widget.clear()`.

Dropping Python references (step 5) **before** `widget.clear()` (step 4) causes
PySide6 ≥ 6.7 to segfault on macOS when the C++ destructor tries to reach the
Python side.

## Coding Standards

- **PEP 8**: Follow Python style guidelines
- **Docstrings**: All public functions, classes, and methods should have docstrings
- **Type Hints**: Use type hints for function parameters and return values
- **Error Handling**: Use custom error classes and handle exceptions appropriately

## License Compliance

Synaptipy is licensed under the GNU Affero General Public License Version 3 (AGPL-3.0).

### License Requirements

As a developer, you should:

1. **Include license notice**: All source files should include a reference to the AGPL-3.0 license
2. **Preserve copyright notices**: Keep all copyright notices intact
3. **Document changes**: Note significant modifications in the code and CHANGELOG
4. **Share modifications**: If you distribute modified versions, you must release the source code

### Adding New Files

When adding new files to the project, include this header:

```python
#!/usr/bin/env python3
"""
Brief description of the file

Detailed description of the file's purpose and functionality.

This file is part of Synaptipy, licensed under the GNU Affero General Public License v3.0.
See the LICENSE file in the root of the repository for full license details.
"""
```

### Third-Party Dependencies

When adding new dependencies, ensure they have licenses compatible with AGPL-3.0. Generally, this means:

- GPL-3.0 and AGPL-3.0 are fully compatible
- LGPL, MIT, BSD, and Apache 2.0 licenses can be used alongside AGPL-3.0
- Proprietary licenses are typically incompatible

If you're unsure about compatibility, discuss with project maintainers before adding the dependency.
