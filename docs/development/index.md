# Development Guides

Technical guides covering the development infrastructure, layer boundaries, UI
theming patterns, and release procedures used across the Synaptipy codebase.

## Overview

Synaptipy follows a strict four-layer architecture:

- **Core layer** (`src/synaptipy/core/`) - Pure Python analysis and signal-processing
  logic, decoupled from the GUI and independently testable. Public analyses
  register with `@AnalysisRegistry.register` and signal preprocessors register
  with `@AnalysisRegistry.register_processor`.
- **Application layer** (`src/synaptipy/application/`) - PySide6 (Qt6) user
  interface, headless `synaptipy-batch` CLI, plugin manager, session state,
  and controllers.
- **Infrastructure layer** (`src/synaptipy/infrastructure/`) - File I/O via
  Neo and PyNWB; tabular (`CSVExporter`) and archival (`NWBExporter`) exports.
- **Shared layer** (`src/synaptipy/shared/`) - Cross-cutting constants, logging,
  theme management, plot factory, caching, and dependency-free XLSX writing.

## Code Quality

All code must pass the local CI gate before merging:

```bash
# Auto-format
conda run -n synaptipy black src/ tests/ scripts/
conda run -n synaptipy isort src/ tests/ scripts/

# Lint
conda run -n synaptipy flake8 src/ tests/

# Full CI gate (formatting, lint, >= 90% coverage pytest, zero-emoji check)
conda run -n synaptipy python scripts/verify_ci.py
```

- **black** - line-length 120, target Python 3.10
- **isort** - profile `black`, line-length 120
- **flake8** - max-line-length 120, max-complexity 10
- **pytest** - CI runs on Ubuntu, Windows, and macOS across Python 3.10, 3.11, and 3.12

## Key Design Rules

1. **Registry import rule** - Always `import synaptipy.core.analysis` (the
   full package), never only `from synaptipy.core.analysis.registry import
   AnalysisRegistry`. Importing the package triggers all sub-module decorators.
2. **PySide6 == 6.7.3** - Do not widen or loosen this pin.
3. **Headless Qt mode** - Automated scripts and tests set `QT_QPA_PLATFORM=offscreen`
   before creating Qt objects, with `gc.disable()` managed in `tests/conftest.py`.
4. **Plot factory and teardown order** - Instantiate plots exclusively through
   `SynaptipyPlotFactory` and follow the teardown sequence documented in the
   Developer Guide.

## Contributing

See the [Developer Guide](../developer_guide.md) for environment setup,
coding standards, testing, and the contribution workflow. The
[Plugin Guide](../extending_synaptipy.md) covers adding custom analysis
routines without modifying core code.

```{toctree}
:maxdepth: 2
:caption: Development

refactor_rules
styling_guide
release_process
manuals/CROSS_PLATFORM_SETUP
```
