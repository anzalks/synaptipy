# Development Guides

Internal guides covering the development infrastructure, UI patterns, and
code style used across the Synaptipy codebase.

## Overview

Synaptipy follows a strict three-layer architecture:

- **Core layer** (`src/Synaptipy/core/`) - Pure Python analysis logic, fully
  decoupled from the GUI and independently testable. All analysis functions
  are registered via the `@AnalysisRegistry.register()` decorator.
- **Application layer** (`src/Synaptipy/application/`) - PySide6 (Qt6) user
  interface, plugin manager, session state, and controllers.
- **Infrastructure layer** (`src/Synaptipy/infrastructure/`) - File I/O via
  Neo and PyNWB; NWB export.

## Code Quality

All code must pass the following checks before merging:

```bash
# Auto-format
black src/ tests/
isort src/ tests/

# Lint
flake8 src/ tests/

# Test
python scripts/run_tests.py
```

- **black** - line-length 120, target Python 3.10
- **isort** - profile `black`
- **flake8** - max-line-length 120, max-complexity 10
- **pytest** - CI runs on Ubuntu/Windows/macOS across Python 3.10, 3.11, 3.12

## Key Design Rules

1. **Registry import rule** - Always `import Synaptipy.core.analysis` (the
   full package), never just `from Synaptipy.core.analysis.registry import
   AnalysisRegistry`. The full import triggers sub-module decorators.
2. **PySide6 == 6.7.3** - Do not widen or loosen this pin.
3. **GC disabled in offscreen mode** - `gc.disable()` in test conftest.
4. **Plot teardown order** - unlink, close, cancel events, widget.clear(),
   clear refs, flush registry. See the developer guide for details.

## Contributing

See the [Developer Guide](../developer_guide.md) for environment setup,
coding standards, testing, and the contribution workflow. The
[Plugin Guide](../extending_synaptipy.md) covers adding analysis modules
without modifying core code.

```{toctree}
:maxdepth: 2
:caption: Development

styling_guide
```
