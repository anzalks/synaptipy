# Changelog

All notable changes to Synaptipy will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0b3] - 2026-03-01

> **Beta nightly release.** Explorer tab improvements, custom analysis plugin documentation and template, flaky test fixes.

### Added

- **Custom Analysis Plugin Documentation**: Comprehensive guide (`extending_synaptipy.md`) for writing analysis plugins without modifying source code
- **Plugin Template**: Ready-to-copy template at `src/Synaptipy/templates/plugin_template.py` with inline comments for all parameter types and plot overlays
- **Plugin Tests**: 16 tests validating plugin template logic, PluginManager loading, and wrapper conventions
- **Tutorial Section 3.6**: Step-by-step "Adding Your Own Analysis Tab" section in the user tutorial under the Analyser Tab
- **Stress Tests**: File cycling stress tests for plot canvas rebuild stability (100 iterations)
- **Explorer Debounce**: Debounce timer for file navigation to prevent rapid teardown cycles

### Fixed

- **Flaky Qt Tests**: Added `processEvents()` calls in 3 test files to resolve non-deterministic offscreen failures caused by stale deferred ViewBox geometry callbacks
- **Explorer Plot Layout**: Fixed Windows Explorer plot view state preservation during file cycling
- **Lint Errors**: Resolved all flake8 CI failures in `analysis_formatter` and `exporter_tab`
- **CSV Export**: Updated tidy per-type CSV export for batch results

### Changed

- Updated `docs/index.rst` toctree, `developer_guide.md`, and tutorial `Appendix B` with plugin cross-references

## [0.1.0b2] - 2026-02-26

> **Beta nightly release.** Fixes Windows-specific analysis loading bug and preprocessing reset propagation across all analysis tabs.

### Fixed

- **Windows Analysis Loading**: Fixed registry import bug where `AnalysisRegistry` remained
  empty on Windows because only `registry.py` was imported (not the full
  `Synaptipy.core.analysis` package that triggers `@register` decorators). Added
  `import Synaptipy.core.analysis` in `analyser_tab.py` and `startup_manager.py`.
- **Preprocessing Reset**: Connected the `preprocessing_reset_requested` signal in
  `BaseAnalysisTab` and added `_handle_preprocessing_reset()` handler. Added
  `reset_ui()` method to `PreprocessingWidget`. Reset now propagates globally to
  all sibling analysis tabs via `AnalyserTab.set_global_preprocessing(None)`.

### Added

- Regression tests for registry population (`test_registry_metadata.py`)
- Regression tests for preprocessing reset propagation (`test_preprocessing_reset.py`)
- Developer documentation for registry import rule, editable install, and
  preprocessing reset propagation (copilot-instructions.md, developer_guide.md)

## [0.1.0b1] - 2026-02-25

> **Beta nightly release.** Core GUI, all 14 analysis modules, batch processing, NWB export, and plugin interface are functional. Issued as a pre-release for wider testing before a stable 0.1.0 tag.

### Fixed

**Analysis Module Bug Fixes**
- **Tau (Time Constant)**: Added exponential fit overlay plot — `calculate_tau` now returns
  fit curve data (`fit_time`, `fit_values`) alongside `tau_ms`, and the registration
  includes `overlay_fit` plot metadata so the fit curve is drawn on the main trace
- **Excitability (F-I Curve)**: Added `popup_xy` plot metadata to show F-I Curve popup
  (Frequency vs Current) after multi-trial analysis
- **Spike Train Dynamics**: Added ISI popup plot — wrapper now returns `isi_numbers` and
  `isi_ms` arrays, and registration includes `popup_xy` plot metadata
- **Optogenetic Synchronization**: Added secondary channel selector (`requires_secondary_channel`
  metadata) so users can pick a dedicated TTL/trigger channel instead of falling back to
  the voltage trace; added stimulus onset vertical line markers to the plot
- **Event Detection (Template Match)**: Lowered default threshold from 4.0 SD to 3.0 SD
  for better sensitivity; added `direction` parameter to UI so users can switch polarity;
  fixed time-axis reconstruction to use actual `time` array instead of synthesising from
  sampling rate (fixes event time accuracy when data doesn't start at t=0)
- **Event Detection (Threshold)**: Fixed noise-floor guard that could override user threshold —
  the 2-SD noise guard now only activates when the user's threshold is below 1 SD, otherwise
  the user's explicit threshold is honoured
- Added `overlay_fit` visualisation type to `MetadataDrivenAnalysisTab` for drawing
  analysis fit curves on the main plot
- Added `_inject_secondary_channel_data` to `MetadataDrivenAnalysisTab` for loading
  data from a user-selected secondary channel and passing it to analysis functions

**Publication Readiness Audit — Error Handling & Robustness**
- Replaced ~25 silent `except: pass` blocks with diagnostic `log.debug()` calls across 15 files
- Added logging to error-swallowing blocks in neo_adapter, analysis_formatter, explorer_tab,
  plot_canvas (widgets & explorer), analysis_plot_manager, main_window, startup_manager,
  zoom_theme, plot_customization, and analysis_tabs/base
- Added docstrings to NWB exporter fallback sentinel classes
- Removed trailing `pass` statements and dead placeholder code from explorer_tab,
  shortcut_manager, main_window, file_io_controller, data_loader, and base analysis tab
- Cleaned up duplicate comment in base analysis tab error handler
- Removed unnecessary `pass` after `log.debug` in theme_manager

**Publication Readiness Audit — Code Quality**
- Fixed unused variable `param_key` in metadata_driven analysis tab
- Fixed unused variable `dt` in optogenetics wrapper
- Replaced long conditional expressions with readable intermediate variables in
  optogenetics.py and train_dynamics.py
- Rewrote conversational docstring in optogenetics wrapper with proper Args/Returns format
- Fixed all flake8 violations: trailing whitespace, missing blank lines, line length, W391
- Cleaned up CLI placeholder module with proper docstrings (removed 50 lines of dead scaffolding)
- Removed stale `CSVExporter` comments from exporters `__init__.py`

**Publication Readiness Audit — Package Structure**
- Populated `__all__` exports in `application/controllers/__init__.py` (9 symbols)
- Populated `__all__` exports in `application/gui/analysis_tabs/__init__.py` (3 symbols)
- Added `__all__` and module docstring to `application/gui/explorer/__init__.py`

**Publication Readiness Audit — CI/CD**
- Added Python 3.12 to CI test matrix (now tests 3.10, 3.11, 3.12)
- Added `pytest-cov` coverage reporting to CI (`--cov=Synaptipy --cov-report=term-missing`)
- Added coverage XML artifact upload for ubuntu/3.11 builds

**Publication Readiness Audit — Scientific Accuracy**
- Fixed line-noise detection baseline overlap in `signal_processor.py`
- Fixed max/min dV/dt zeroing bias in `spike_analysis.py` (sentinel values)
- Fixed AHP depth sign convention in `spike_analysis.py`
- Fixed mean frequency calculation to use spike span instead of trace duration
- Fixed Rin unit conversion clarity (mV/pA → MOhm derivation)
- Refined sag ratio calculation to use 5th percentile for robustness
- Fixed z-score normalization in template matching (subtract median)
- Added dV/dt unit conversion documentation in `phase_plane.py`
- Removed duplicate dictionary keys in spike detection registry

**Publication Readiness Audit — Code Quality**
- Removed redundant imports, unused variables, and duplicate function definitions
- Added edge-case handling for empty spike indices
- Added docstring for `_find_stable_baseline_segment`
- Converted unresolvable TODO to NOTE (async limitation in batch load)
- Standardized all flake8 compliance to max-line-length 120

**Publication Readiness Audit — CI/CD & Infrastructure**
- Made flake8 lint failures blocking in CI (removed `--exit-zero`)
- Added `pytest-cov` to CI dependencies
- Aligned Python version floor to 3.10 in pyproject.toml, environment.yml, README
- Standardized author email and license (AGPL-3.0-or-later)
- Cleaned stale files, relocated tests, removed empty directories
- Added `.coverage`, `htmlcov/`, `.pytest_cache/` to `.gitignore`
- Removed stale Python 3.9 classifier from `pyproject.toml`
- Added `pytest-cov` and `flake8` to `environment.yml`
- Added 7 targeted scientific accuracy tests

**Phase 1: Critical Performance & Data Loading**
- **CRITICAL**: Fixed severe UI lag caused by repeated instantiation of PlotCustomizationManager in `get_plot_pens()`. Now uses singleton pattern, eliminating thousands of unnecessary disk reads.
- **CRITICAL**: Optimized `update_plot_pens()` in explorer_tab to fetch pens once outside loop instead of hundreds of times inside nested loops. Reduces function calls from N×M to 2.
- **CRITICAL**: Fixed multi-channel data loading bug in neo_adapter where only the first channel received data. Enhanced channel ID extraction with multiple fallback methods to ensure all channels load correctly.

**Phase 2: Architectural Performance Overhaul**
- **CRITICAL**: Eliminated double-loading architectural flaw where data was loaded twice (background thread + UI thread). Now passes pre-loaded Recording object directly, cutting load time by 50%.
- **CRITICAL**: Fixed plotting lag for large files by respecting plot mode - only plots single trial in CYCLE_SINGLE mode instead of all trials, resulting in 95%+ faster plot updates.
- **CRITICAL**: Enabled linked X-axis zooming across all channel plots for synchronized time-aligned inspection.
- Added comprehensive debug logging for data flow and plot operations
- Improved robustness of channel identification across different file formats (ABF, WCP, etc.)

**Phase 3: Rendering Performance Optimizations**
- **PERFORMANCE**: Optimized PyQtGraph downsampling using 'peak' mode to preserve spikes while reducing render load
- **PERFORMANCE**: Enabled setClipToView(True) on all plot items to skip rendering data outside visible viewport, reducing memory usage by 60-80%
- **PERFORMANCE**: Added "Force Opaque Single Trials" option to eliminate expensive alpha blending, providing 2-5x faster rendering with 20+ overlaid trials
- **PERFORMANCE**: Implemented 50ms debounce timers for zoom/pan sliders and scrollbars, reducing redraws by 98% during rapid interactions
- Added user-controlled performance checkbox in plot customization dialog
- Enhanced logging for all rendering optimizations

### Performance
- Dramatically improved plot customization responsiveness (~99% reduction in disk I/O)
- Reduced pen update operations from hundreds to 2 per update cycle
- Eliminated redundant file loading (50% faster initial load)
- Instant plot updates for large files in single-trial mode (95%+ improvement)
- Synchronized multi-channel plot zooming
- **3-6x faster** rendering with optimized downsampling, clipping, and optional opaque mode
- Smoother slider interactions with 50ms debouncing (98% fewer redraws)
- Reduced memory usage during zooming (60-80% reduction with clipping)
- UI remains responsive during all operations

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
