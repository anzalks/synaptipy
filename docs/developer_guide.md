# Synaptipy Developer Guide

This guide is intended for developers who want to understand, modify, or contribute to Synaptipy.

## Table of Contents

- [Development Environment Setup](#development-environment-setup)
- [Project Structure](#project-structure)
- [Development Workflow](#development-workflow)
- [Testing](#testing)
- [Coding Standards](#coding-standards)
- [License Compliance](#license-compliance)

## Development Environment Setup

### Prerequisites

- Python 3.9+
- Git
- pip or conda package manager

### Setting Up Your Development Environment

1. Clone the repository:
   ```bash
   git clone https://github.com/anzalks/synaptipy.git
   cd synaptipy
   ```

2. Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
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
├── core/                       # Core data structures
│   └── data_model.py           # Recording and Channel classes
├── analysis/                   # Analysis algorithms
│   └── resistance_analysis.py  # Input resistance calculations
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

## Coding Standards

Synaptipy follows these coding standards:

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
