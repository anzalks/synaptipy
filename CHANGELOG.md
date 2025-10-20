# Changelog

All notable changes to Synaptipy will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed
- **CRITICAL**: Fixed severe UI lag caused by repeated instantiation of PlotCustomizationManager in `get_plot_pens()`. Now uses singleton pattern, eliminating thousands of unnecessary disk reads.
- **CRITICAL**: Optimized `update_plot_pens()` in explorer_tab to fetch pens once outside loop instead of hundreds of times inside nested loops. Reduces function calls from N×M to 2.
- **CRITICAL**: Fixed multi-channel data loading bug in neo_adapter where only the first channel received data. Enhanced channel ID extraction with multiple fallback methods to ensure all channels load correctly.
- Added comprehensive debug logging for data loading to aid troubleshooting
- Improved robustness of channel identification across different file formats (ABF, WCP, etc.)

### Performance
- Dramatically improved plot customization responsiveness (~99% reduction in disk I/O)
- Reduced pen update operations from hundreds to 2 per update cycle
- UI remains responsive during all plot customization operations

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
