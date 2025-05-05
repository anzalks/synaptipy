# Changelog

All notable changes to Synaptipy will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2025-05-06

### Added
- Initial release of Synaptipy
- GUI application with PySide6 and pyqtgraph for electrophysiology visualization
- Support for various file formats via the Neo library
- Explorer tab for viewing and navigating data files
- Analyzer tab with:
  - Input Resistance/Conductance calculation
  - Baseline/RMP analysis
- Exporter tab with:
  - NWB export functionality
  - CSV export for analysis results
- Comprehensive test suite with pytest fixtures
- Command-line interface for running the application
- Released under GNU Affero General Public License Version 3 (AGPL-3.0)

### Known Issues
- Limited documentation
- Examples need further development
- No support for all possible Neo file formats (depends on installed backends)
