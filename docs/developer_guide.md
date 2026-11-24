# Synaptipy Developer Guide

This guide is intended for developers who want to understand, modify, or contribute to Synaptipy.

## Table of Contents

- [Development Environment Setup](#development-environment-setup)
- [Project Structure](#project-structure)
- [5-Pillar Analyser Architecture](#5-pillar-analyser-architecture)
- [Writing Custom Analysis Plugins](#writing-custom-analysis-plugins)
- [Architecture and Performance Patterns](#architecture-and-performance-patterns)
- [UI and Styling Guidelines](#ui-and-styling-guidelines)
- [Development Workflow](#development-workflow)
- [Testing](#testing)
- [CI Behaviour and Platform-Specific Test Rules](#ci-behaviour-and-platform-specific-test-rules)
- [Coding Standards](#coding-standards)
- [License Compliance](#license-compliance)

## Development Environment Setup

### Prerequisites

- Python 3.10-3.12 (`requires-python = ">=3.10,<3.13"`)
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

This installs Synaptipy in editable mode with all development and testing dependencies.

## Project Structure

The Synaptipy codebase is organized into strict architectural layers (`core/`, `infrastructure/`, `application/`, and `shared/`):

```text
src/synaptipy/                           # Main package
├── __init__.py                          # Package initialization and __version__
├── __main__.py                          # Entry point for `synaptipy` / `python -m synaptipy`
├── application/                         # GUI and CLI application layer
│   ├── __main__.py                      # GUI entry point (run_gui)
│   ├── cli/                             # Headless command-line interface
│   │   └── main.py                      # Entry point for `synaptipy-batch`
│   ├── controllers/                     # MVC controllers
│   │   ├── analysis_formatter.py        # Format analysis results for display
│   │   ├── analysis_plot_manager.py     # Manage plot overlays for analysis
│   │   ├── file_io_controller.py        # File open/save coordination
│   │   ├── live_analysis_controller.py  # Real-time spike detection
│   │   └── shortcut_manager.py          # Keyboard shortcut bindings
│   ├── data_loader.py                   # Background file loading (QThread)
│   ├── gui/                             # Main GUI components
│   │   ├── main_window.py               # MainWindow (Explorer, Analyser, Exporter tabs)
│   │   ├── analyser_tab.py              # Dynamic 5-pillar analysis tab manager
│   │   ├── exporter_tab.py              # NWB/CSV export tab
│   │   ├── about_dialog.py              # About and citation dialog
│   │   ├── analysis_config_dialog.py    # Global analysis parameter defaults dialog
│   │   ├── analysis_worker.py           # Worker thread for asynchronous analysis
│   │   ├── batch_dialog.py              # Interactive batch analysis dialog
│   │   ├── help_window.py               # Offline Qt Help (.qhc) viewer window
│   │   ├── nwb_dialog.py                # NWB metadata configuration dialog
│   │   ├── plot_customization_dialog.py # Global plot styling customization dialog
│   │   ├── plot_save_dialog.py          # Plot image/vector save dialog
│   │   ├── preferences_dialog.py        # Application preferences dialog
│   │   ├── session_summary_dialog.py    # Session summary dialog
│   │   ├── ui_generator.py              # Dynamic UI generation from registry metadata
│   │   ├── welcome_screen.py            # Demo data and plugin download banner
│   │   ├── analysis_tabs/               # Analysis tab framework
│   │   │   ├── base.py                  # BaseAnalysisTab (ABC)
│   │   │   └── metadata_driven.py       # MetadataDrivenAnalysisTab
│   │   ├── dialogs/                     # Specialized modal dialogs
│   │   │   ├── export_manager.py        # Unified export coordination dialog
│   │   │   ├── plot_export_dialog.py    # Publication plot export options
│   │   │   ├── protocol_map_dialog.py   # Trial/segment ProtocolMap editor
│   │   │   └── trial_selection_dialog.py # Per-trial inclusion/exclusion selector
│   │   ├── explorer/                    # Data Explorer tab components
│   │   │   ├── config_panel.py          # Preprocessing and display controls
│   │   │   ├── explorer_tab.py          # Explorer container widget
│   │   │   ├── plot_canvas.py           # Multi-channel trace canvas
│   │   │   ├── sidebar.py               # File tree and recording metadata panel
│   │   │   ├── toolbar.py               # Navigation and zoom toolbar
│   │   │   └── y_controls.py            # Per-channel Y-axis scale controls
│   │   └── widgets/                     # Reusable GUI widgets
│   │       ├── log_streamer.py          # Live analysis log window
│   │       ├── plot_canvas.py           # SynaptipyPlotCanvas wrapper
│   │       ├── preprocessing.py         # Preprocessing control widget
│   │       └── preprocessing_comparison.py # Raw vs processed trace preview
│   ├── services/                        # Application services layer
│   │   ├── data_loader_service.py       # Service wrapper around data loading
│   │   ├── methods_generator.py         # Automated Materials & Methods text builder
│   │   └── parameter_templates.py       # Saved analysis parameter presets
│   ├── plugin_manager.py                # Plugin discovery, consent, and hot-reload
│   ├── session_manager.py               # Session state persistence
│   └── startup_manager.py               # Application startup and update checks
├── core/                                # Pure logic and domain models (zero GUI imports)
│   ├── averaging.py                     # TimeAlignedAverage and physical-time averaging
│   ├── constants.py                     # Physical and numerical domain constants
│   ├── data_model.py                    # Recording, Channel, UndoStack, Experiment
│   ├── error_handler.py                 # Crash reporter and install_excepthook
│   ├── processing_pipeline.py           # SignalProcessingPipeline and apply_trace_corrections
│   │                                    # (immutable 5-step A -> B -> C -> D -> E order)
│   ├── protocols.py                     # ProtocolMap, ProtocolAssignment, validation
│   ├── results.py                       # Typed result dataclasses (RinResult, etc.)
│   ├── signal_processor.py              # Pure NumPy/SciPy DSP filters and quality checks
│   ├── source_interfaces.py             # SourceHandle protocol for lazy I/O decoupling
│   ├── trial_qc.py                      # TrialQCDecision and auditable sweep eligibility
│   └── analysis/                        # Analysis algorithms and registry
│       ├── registry.py                  # AnalysisRegistry (@register, @register_processor)
│       ├── contracts.py                 # Canonical AnalysisResult (schema v1) contract
│       ├── preprocessing.py             # 7 registered batch/CLI signal preprocessors
│       ├── batch_engine.py              # Parallel BatchAnalysisEngine
│       ├── epoch_manager.py             # EpochManager for TTL and manual epochs
│       ├── cross_file_utils.py          # Cross-file trial averaging and compatibility report
│       ├── passive_properties.py        # Pillar 1: RMP, Rin, Tau, Sag, I-V, Capacitance
│       ├── single_spike.py              # Pillar 2: Spike detection and phase plane
│       ├── firing_dynamics.py           # Pillar 3: Excitability, burst, train dynamics
│       ├── synaptic_events.py           # Pillar 4: Threshold and deconvolution events
│       └── evoked_responses.py          # Pillar 5: Evoked Sync, PPR, Stimulus Train (STP)
├── infrastructure/                      # File I/O and external format adapters
│   ├── file_readers/                    # Neo and rescue file readers
│   │   ├── neo_adapter.py               # Header-first NeoAdapter
│   │   ├── neo_source_handle.py         # Lazy trial loader handle
│   │   ├── abf_reader.py                # ABF helper utilities
│   │   └── format_support.py            # Explicit validation tier map per extension
│   ├── exporters/                       # Scientific data exporters
│   │   ├── csv_exporter.py              # Summary, tidy, events, recording, Prism CSV + JSON provenance
│   │   └── nwb_exporter.py              # NWB:N 2.0 / DANDI exporter (NWBExporter)
│   └── neo_patches.py                   # Upstream Neo compatibility patches
├── shared/                              # Cross-cutting utilities and plot styling
│   ├── constants.py                     # Application-wide constants (APP_NAME, etc.)
│   ├── cursor_manager.py                # Interactive plot cursor management
│   ├── data_cache.py                    # Recording cache singleton
│   ├── error_handling.py                # Custom exception hierarchy
│   ├── logging_config.py                # Logging setup and boot.log stdio guard
│   ├── plot_customization.py            # PlotCustomizationManager pens and brushes
│   ├── plot_exporter.py                 # Plot export logic (PNG, PDF, SVG)
│   ├── plot_factory.py                  # SynaptipyPlotFactory (mandatory widget factory)
│   ├── plot_zoom_sync.py                # Cross-tab zoom synchronization
│   ├── scroll_settings.py               # Scroll direction preferences
│   ├── styling.py                       # Qt widget styling helpers (style_button)
│   ├── theme_manager.py                 # Light/dark/system theme state management
│   ├── utils.py                         # General shared utilities
│   ├── viewbox.py                       # Custom pyqtgraph ViewBox subclass
│   ├── xlsx_exporter.py                 # Dependency-free XLSX workbook writer
│   └── zoom_theme.py                    # Zoom state theming utilities
├── resources/                           # Icons and compiled offline help (.qhc/.qch)
└── templates/                           # Reference archetypes and starter templates
    ├── analysis_template.py             # Annotated two-layer analysis template
    ├── plugin_template.py               # Starter user plugin template
    ├── tab_template.py                  # Custom GUI analysis tab template
    └── test_template.py                 # Pytest unit test template

tests/                                   # Pytest test suite
├── conftest.py                          # Session fixtures, QSettings isolation, offscreen guards
├── application/                         # Application, CLI, and controller tests
├── core/                                # Core analysis, DSP, and golden master tests
├── gui/                                 # Headless Qt/pyqtgraph widget tests
├── infrastructure/                      # File reader and NWB/CSV exporter tests
└── shared/                              # Shared utility tests

scripts/                                 # Developer and CI automation scripts
├── verify_ci.py                         # Full local CI gate (black, isort, flake8, pytest, emoji scan)
├── run_tests.py                         # Convenient test runner wrapper
├── bump_version.py                      # Atomic version updater (pyproject.toml, Inno Setup, environment.yml)
├── build_offline_help.py                # Compiles Sphinx QtHelp (.qhc/.qch) offline manual
├── check_published_docs.py              # Validates built HTML documentation output
├── capture_screenshots.py               # Deterministic offscreen UI screenshot generator
└── build_icons.py                       # Cross-platform icon builder (.icns / .ico)

docs/                                    # Sphinx + MyST documentation source
examples/                                # Example scripts, notebooks, data, and 5 plugins
```

## 5-Pillar Analyser Architecture

The Synaptipy Analyser UI is strictly fixed to five core pillar tabs. Each
pillar corresponds to a module-level aggregator entry in `AnalysisRegistry`,
covering 16 built-in leaf analysis routines in total (alongside 7 registered
signal preprocessors in `core/analysis/preprocessing.py`). Sub-analyses are
exposed via `method_selector` drop-downs inside each pillar tab and are never
added as separate core top-level tabs.

| Pillar | Module file | Registry key | Sub-analyses (16 total) |
|---|---|---|---|
| 1 - Passive Properties | `passive_properties.py` | `passive_properties` | Baseline (RMP), Input Resistance, Tau, Sag Ratio, I-V Curve, Capacitance |
| 2 - Single Spike Kinetics | `single_spike.py` | `single_spike` | Spike Detection, Phase Plane |
| 3 - Firing Dynamics | `firing_dynamics.py` | `firing_dynamics` | Excitability, Burst Analysis, Spike Train Dynamics |
| 4 - Synaptic Events | `synaptic_events.py` | `synaptic_events` | Amplitude (Threshold), Template (Deconvolution) |
| 5 - Evoked Responses | `evoked_responses.py` | `evoked_responses` | Evoked Sync, Paired-Pulse Ratio, Stimulus Train (STP) |

Specialized or domain-specific analyses are implemented as standalone plugins
in `examples/plugins/` (or `~/.synaptipy/plugins/`), which appear after the
five core pillars when custom plugins are enabled.

### Immutable Trace Correction Pipeline

All backend trace conditioning runs through `apply_trace_corrections()` in
`src/synaptipy/core/processing_pipeline.py`. Regardless of the order in which a
user toggles controls in the GUI, `apply_trace_corrections()` enforces an
immutable five-step sequence (`A -> B -> C -> D -> E`):

1. **Step A - Unit-Aware LJP Voltage Offset:** Subtracts the liquid junction
   potential on voltage traces (`V_true = V_recorded - ljp_mv` in `mV`, with
   automatic scaling for `V` and `uV`; skipped on current channels).
2. **Step B - P/N Leak Subtraction:** Computes the per-sample mean across
   sub-threshold P/N sweeps (`pn_traces`), scales by `pn_scale`, and subtracts
   capacitive transients and steady-state leak currents.
3. **Step C - Pre-Event Noise Floor Zeroing:** Subtracts the scalar median of
   the specified pre-event baseline window (`pre_event_window_s = (t_start, t_end)`).
4. **Step D - Pre-Filter Linear Artifact Interpolation:** Linearly interpolates
   across stimulus artifact windows (`artifact_interp_steps`) after Steps A-C
   and before filtering so sharp transient edges cannot induce Gibbs ringing.
5. **Step E - DSP Filtering:** Applies digital filter steps (`filter_steps`)
   through `SignalProcessingPipeline.process()`.

See [Algorithmic Definitions](algorithmic_definitions.md) for the mathematical
specification of each stage.

## Writing Custom Analysis Plugins

Synaptipy supports two ways to add analysis functionality:

1. **Standalone plugins (recommended for new metrics):** Place a `.py` file in
   `~/.synaptipy/plugins/` (or contribute reusable domain examples to
   `examples/plugins/`). Because the core UI is locked to the five pillar tabs,
   novel standalone metrics belong in plugins rather than new core tabs.
2. **Core pillar sub-analyses (core contributors):** When extending one of the
   five existing pillars, add a pure logic function (returning a typed dataclass
   from `src/synaptipy/core/results.py`) and an `@AnalysisRegistry.register`
   wrapper inside the appropriate pillar module in `src/synaptipy/core/analysis/`,
   wire it into that pillar's `method_selector`, and add unit tests in `tests/core/`.

Five example plugins are available from **Help > Download Example Plugins...**.
They are saved to `~/.synaptipy/plugins/` and load when **Enable Custom
Plugins** is checked under **Edit > Preferences** (**Extensions** group).
Source checkouts and desktop bundles also include these files in
`examples/plugins/`:

| Plugin file | Tab label | Purpose |
|---|---|---|
| `synaptic_charge.py` | Synaptic Charge (AUC) | Integrates postsynaptic current between zero-crossings to compute total charge (pC) |
| `opto_jitter.py` | Opto Latency Jitter | Trial-to-trial evoked response latency variability after TTL pulses |
| `miniml_integration.py` | miniML Events | Deep-learning event detection via miniML (optional dependency; requires TensorFlow and cloned miniML repository) |
| `spike_interface_integration.py` | Spike Detection (SpikeInterface) | Extracellular spike detection via SpikeInterface (optional dependency; `pip install spikeinterface`) |

A starter template is provided at `src/synaptipy/templates/plugin_template.py`.
For the complete plugin specification - including `ui_params` widgets, `plots`
overlays, `@AnalysisRegistry.register_processor`, return-dict conventions, and
annotated examples - see **[Writing Custom Analysis Plugins](extending_synaptipy.md)**.

## Architecture and Performance Patterns

### Asynchronous UI and Background Loading

Synaptipy uses `QThread` and `QRunnable` for background data loading and
analysis. Recording files (`.abf`, `.wcp`, `.nwb`, etc.) are loaded
asynchronously so large multi-sweep files do not block the Qt event loop.

Because of this asynchronous architecture, direct UI assertions in tests must
synchronize with background worker completion using `qtbot.waitUntil` rather
than `time.sleep()`.

### UI Interaction Debouncing and Plot Factory

- **Mandatory Plot Factory:** Never instantiate `pg.PlotWidget` or
  `pg.GraphicsLayoutWidget` directly. Always create plot widgets via
  `SynaptipyPlotFactory` (`src/synaptipy/shared/plot_factory.py`) to preserve
  cross-platform OpenGL safety and theme consistency.
- **Debouncing:** Rapid zoom and pan signals in `explorer_tab.py` and real-time
  parameter updates are debounced to prevent flooding the main GUI thread.

## UI and Styling Guidelines

Synaptipy prioritizes visual accessibility. Multi-trial plotting uses
colorblind-safe palettes (such as Okabe-Ito or Viridis).

When extending the UI or configuring plugin overlays:
- Do not hardcode overlapping red and green traces.
- Use `get_plot_customization_manager()` (`src/synaptipy/shared/plot_customization.py`)
  and `theme_manager.py` rather than hardcoded widget stylesheets.
- Use `style_button(button)` for standard controls and
  `style_button(button, "primary")` for at most one primary action per visible
  panel. See the [Styling Guide](development/styling_guide.md) for details.

## Development Workflow

### Feature Development

1. **Create a branch**: Create a feature or fix branch from `main`:
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Implement changes**: Follow the separation-of-concerns rules (`core/` must
   never import `PySide6`, `PyQt6`, or `matplotlib.pyplot`).

3. **Add tests**: Place unit tests in `tests/core/` and headless GUI tests in
   `tests/gui/`.

4. **Run local CI verification**: Verify formatting, linting, emoji checks, and
   headless test coverage before pushing:
   ```bash
   conda run -n synaptipy python scripts/verify_ci.py
   ```

5. **Submit a pull request**: Push your branch and open a pull request against
   `main`.

### Code Review Process

All contributions undergo review for:

- Architectural boundaries (`core/` purity, `SourceHandle` lazy loading, `channel.get_data(trial_index)`)
- Scientific accuracy and unit safety (epsilon guards, `np.nan` sentinels, provenance recording)
- Test coverage and headless cross-platform stability
- Formatting, complexity (`<= 10`), and documentation standards

## Testing

### Running Tests

Run the full local CI verification gate (recommended before every push):

```bash
conda run -n synaptipy python scripts/verify_ci.py
```

Run the test suite via `scripts/run_tests.py`:

```bash
conda run -n synaptipy python scripts/run_tests.py
```

Run a specific test module:

```bash
conda run -n synaptipy python scripts/run_tests.py --test test_main_window
```

Run with coverage reporting:

```bash
conda run -n synaptipy python scripts/run_tests.py --coverage
```

### CI Test Matrix

CI runs on all three major operating systems across Python 3.10, 3.11, and 3.12:

| Platform | Python Versions |
|---|---|
| Ubuntu (latest) | 3.10, 3.11, 3.12 |
| Windows (latest) | 3.10, 3.11, 3.12 |
| macOS (latest) | 3.10, 3.11, 3.12 |

CI enforces `black --check`, `isort --check`, `flake8`, and the zero-emoji
policy. Pull requests that fail any check are rejected.

The CI coverage gate enforces a minimum of 90% coverage across `src/synaptipy`,
while new engineering changes target 95% coverage. On macOS, run the full GUI
suite with `QT_QPA_PLATFORM=offscreen` and use targeted non-offscreen `pytest`
runs when inspecting local `coverage.py` reports on individual modules, because
the intentional offscreen force-exit bypasses Python `atexit` handlers. CI's
Linux runner generates the canonical `coverage.xml` report.

### Documentation Screenshot Refresh

Published screenshots are deterministic UI captures generated from the pinned
environment:

```bash
conda run --no-capture-output -n synaptipy env QT_QPA_PLATFORM=offscreen \
  python scripts/capture_screenshots.py
```

The capture runner applies a deterministic dark theme, isolates bundled example
plugins from `~/.synaptipy/plugins/`, and refreshes independent screenshot
groups in fresh Qt processes while preserving hand-authored figures.
`scripts/verify_ci.py --with-screenshots` validates screenshot generation within
a 180-second timeout.

Additional release-safety jobs run automatically in CI:

- **`minimum-viable`**: Python 3.10 with lower-bound dependency versions
  (`numpy==2.0.0`, `scipy==1.14.0`, `neo==0.14.0`, `pyqtgraph==0.13.3`,
  `PySide6==6.7.3`).
- **`latest-dependencies`**: Python 3.12 with all upgradable dependencies at
  their latest compatible releases (`PySide6` remains pinned to `6.7.3`).
- **`hidpi`** and **`notebooks`**: High-DPI Qt/pyqtgraph verification and
  executable tutorial notebook checks.
- **`wheel-install`**: Builds the wheel and verifies installation in a clean
  virtual environment, including compiled offline documentation checks via
  `scripts/build_offline_help.py` and `scripts/check_published_docs.py`.
- **`security`**: Audits packaged sources for security issues.

### Golden Master Tests

`tests/core/test_golden_master.py` freezes floating-point outputs from core
algorithms against reference ABF recordings in `examples/data/` and synthetic
traces. If a dependency update alters a computed metric beyond tolerance
(`rel=1e-5` for most metrics, `rel=1e-2` for exponential `tau` fits), these
tests fail and identify the drifting metric.

**When to update golden master values:**

If you intentionally revise an algorithm (for example, refining initial-guess
estimation in `calculate_tau`), inspect the updated output on an example ABF
recording and update `tests/core/test_golden_master.py` in a dedicated commit:

```bash
conda run -n synaptipy python -c "
from pathlib import Path
from synaptipy.infrastructure.file_readers.neo_adapter import NeoAdapter
from synaptipy.core.analysis.passive_properties import calculate_rmp

adapter = NeoAdapter()
rec = adapter.read_recording(Path('examples/data/2023_04_11_0018.abf'))
ch = list(rec.channels.values())[0]
v = ch.get_data(0)
t = ch.get_relative_time_vector(0)
print(calculate_rmp(v, t, baseline_window=(0.0, 0.5)))
"
# Update tests/core/test_golden_master.py with the verified reference value
# and commit with a clear message, e.g.: 'test: update golden masters for revised tau fit'
```

Do not loosen golden master tolerances without documented numerical justification.

### Writing Tests

- Place tests in the matching subdirectory of `tests/` (`core/`, `gui/`, `application/`, `infrastructure/`, `shared/`).
- Name all test files `test_*.py` so `pytest` discovers them automatically.
- Use `pytest` fixtures (`qtbot` for GUI widgets; never import `PySide6` inside `tests/core/`).
- Use `pathlib.Path` for all filesystem paths and `encoding="utf-8"` when reading or writing text files.

## CI Behaviour and Platform-Specific Test Rules

The test suite runs `PySide6` (`==6.7.3`) and `pyqtgraph` widgets under
`QT_QPA_PLATFORM=offscreen`. Several platform-specific crash patterns have been
eliminated; the safeguards below must not be removed.

### PyInstaller `console=False` and `faulthandler.enable()`

Windowed executables built with `console=False` may set `sys.stdout` and
`sys.stderr` to `None` or to streams lacking an OS file descriptor. Standard
library `faulthandler.enable()` calls `sys.stderr.fileno()`; replacing `None`
with `io.StringIO` still raises `io.UnsupportedOperation`. Entry points call
`ensure_stdio_streams_support_fileno()` in `synaptipy.shared.logging_config`
before importing Qt. When either stream is missing or lacks `fileno()`, it is
pointed at an append handle to `~/.synaptipy/logs/boot.log` (or
`SYNAPTIPY_LOG_DIR/boot.log`) so early startup crashes and C tracebacks are
preserved on disk, falling back to `os.devnull` only if the log directory is
not writable.

### Analysis Registry import rule - DO NOT import only `registry.py`

To populate `AnalysisRegistry`, always import the full analysis package:

```python
import synaptipy.core.analysis  # triggers __init__.py -> passive_properties, single_spike, preprocessing, etc.
```

Never rely on `from synaptipy.core.analysis.registry import AnalysisRegistry`
alone when looking up built-in analyses: importing `registry.py` defines the
class without executing the `@AnalysisRegistry.register` and
`@AnalysisRegistry.register_processor` decorators in the sibling modules.

Both `startup_manager._begin_loading()` and
`analyser_tab._load_analysis_tabs()` import `synaptipy.core.analysis` before
querying `AnalysisRegistry.list_registered()` so Windows and macOS populate
identical registry snapshots regardless of prior import order.

### Editable install must point to the active workspace

`pip install -e .` records the editable source path in `.pth` metadata. If the
repository is moved or cloned to a second directory, an older editable install
continues resolving imports from the previous checkout. Re-run
`pip install -e ".[dev]"` from the active workspace whenever switching worktrees.

Symptom: newly added modules visible on disk (such as `contracts.py`,
`preprocessing.py`, or `protocols.py`) raise `ModuleNotFoundError` because
Python imports `synaptipy` from a stale checkout. Verify the active path with:

```bash
pip show synaptipy | grep "Editable project location"
```

### Offscreen `pytest_sessionfinish` teardown on POSIX and Windows

`PySide6` and `pyqtgraph` leave C++ scene-graph wrappers partially alive at
interpreter shutdown. Allowing normal C++/CRT teardown after an offscreen GUI
session dereferences freed C++ pointers. `pytest_sessionfinish` in
`tests/conftest.py` therefore terminates the process explicitly when
`QT_QPA_PLATFORM=offscreen` is set:

- **macOS and Linux (POSIX):** Calls `os._exit(exitstatus)`, invoking libc
  `_exit()` directly to bypass C++ static destructors, `atexit` handlers, and
  cyclic garbage collection. On macOS, `conda run` may print an `Abort trap: 6`
  or `QThread` message even when `exitstatus == 0`; inspect pytest's summary
  line (`N passed`, zero `FAILED` / `ERROR`) rather than conda's wrapper message:
  ```bash
  conda run -n synaptipy python -m pytest tests/ 2>&1 | grep -c PASSED
  conda run -n synaptipy python -m pytest tests/ 2>&1 | grep "FAILED\|ERROR "
  ```
- **Windows (`sys.platform == "win32"`):** Calls Win32
  `kernel32.TerminateProcess(ctypes.c_void_p(-1), int(exitstatus))` with
  explicit 64-bit `argtypes`. On Windows, `os._exit()` calls `ExitProcess()`,
  which still dispatches `DLL_PROCESS_DETACH` to loaded Qt DLLs and triggers
  access violations; `TerminateProcess` bypasses `DLL_PROCESS_DETACH` while
  preserving the exact `pytest` exit status code.

### GC must be disabled in offscreen mode

`pytest_configure` in `tests/conftest.py` disables Python's cyclic garbage
collector (`gc.disable()`) when `QT_QPA_PLATFORM=offscreen`. Do not remove this
guard: cyclic GC can invoke `tp_dealloc` on `PySide6` wrapper objects mid-way
through Qt's C++ destructor chain, causing `SIGBUS` on macOS and access
violations on Windows.

### `processEvents()` before `addPlot()` in offscreen mode

`SynaptipyPlotCanvas.add_plot()` calls `QCoreApplication.processEvents()`
before `widget.addPlot()` when `QT_QPA_PLATFORM=offscreen`. Deferred callbacks
queued by an earlier `widget.clear()` or widget construction must execute before
`PlotItem.__init__()` runs; otherwise they fire mid-constructor and dereference
freed C++ pointers on Windows.

Executing pending events with `processEvents()` rather than discarding them with
`removePostedEvents()` is required because `removePostedEvents` on macOS drops
internal `pyqtgraph` `AllViews` range and geometry events, corrupting subsequent
`widget.clear()` calls.

### `removePostedEvents()` must skip macOS

The `_drain_qt_events_after_test` fixture in `tests/conftest.py` guards
`QCoreApplication.removePostedEvents(None, 0)` with
`if sys.platform != "darwin":`. Keep this platform guard intact so macOS
`ViewBox` geometry caches remain consistent across session-scoped tests.

### `enableMenu=False` in offscreen mode

`SynaptipyPlotCanvas.add_plot()` passes `enableMenu=False` to `widget.addPlot()`
when `QT_QPA_PLATFORM=offscreen`. This skips `ViewBoxMenu.__init__` and avoids
`QWidgetAction` crashes when no display server is attached.

### Plot teardown order

`SynaptipyPlotCanvas.clear_plots()` executes six steps in strict order:

1. `_unlink_all_plots()` - break `setXLink` / `setYLink` connections before teardown.
2. `_close_all_plots()` - disconnect control signals and call `PlotItem.close()` while the scene is valid.
3. `_cancel_pending_qt_events()` - discard stale posted events (Windows/Linux only).
4. `widget.clear()` - destroy C++ layout children via Qt's scene graph.
5. `plot_items.clear()` - drop Python references *after* C++ teardown completes.
6. `_flush_qt_registry()` - clear residual registry references posted by `widget.clear()`.

Dropping Python references (step 5) before `widget.clear()` (step 4) causes
`PySide6` >= 6.7 to segfault on macOS when C++ destructors reach back into
collected Python wrappers.

### `NeoAdapter` ABF rescue path

`src/synaptipy/infrastructure/file_readers/neo_adapter.py` reads
electrophysiology recordings via `neo`. Certain `.abf` files report truncated
single-character unit prefixes (`"p"`, `"n"`, `"m"` instead of `"pA"`, `"nA"`,
`"mV"`) or fail inside `AxonIO` chunking. When this occurs, `NeoAdapter` falls
back to `pyabf` (`_pyabf_to_neo_block`):

- The `pyabf` rescue path runs *before* the generic `lazy=True` fallback so
  broken `AnalogSignalProxy` objects do not mask unit or chunking errors.
- `_ABF_PREFIX_UNITS` maps truncated SI prefixes to `quantities` units
  (`"p" -> pq.pA`, `"n" -> pq.nA`, `"m" -> pq.mV`).
- Rescue activation logs at `DEBUG` / `INFO` level rather than `ERROR`, as
  fallback recovery is an expected code path for affected ABF headers.

## Coding Standards

- **Formatting**: Code is formatted with [**black**](https://github.com/psf/black) and [**isort**](https://pycqa.github.io/isort/) (`--profile black`).
- **Linting**: [**flake8**](https://flake8.pycqa.org/en/latest/) enforces style and cyclomatic complexity (`max-complexity = 10`; `.flake8` sets `max-line-length = 120` on `src/` and `tests/`, and CI also checks syntax/line limits up to 127 characters). Zero unused imports (`F401`) or unused variables (`F841`) are permitted.
- **Zero Emojis and Typography**: Emojis, Dingbats, em dashes, and en dashes are strictly prohibited across code, docstrings, and documentation (`scripts/verify_ci.py` fails on any match).
- **Docstrings and Type Hints**: Public classes, functions, and methods require docstrings and explicit Python type annotations.
- **Explicit Error Handling**: Catch specific exception classes (`ValueError`, `KeyError`, `OSError`, or `SynaptipyError` subclasses in `shared/error_handling.py`) rather than bare `except:` or broad `except Exception:` blocks in core logic.

### Formatting Your Code

Run formatters, linter, and the full CI verifier before committing:

```bash
# Format imports and code
conda run -n synaptipy isort src/ tests/ scripts/
conda run -n synaptipy black src/ tests/ scripts/

# Lint for style and cyclomatic complexity
conda run -n synaptipy flake8 src/ tests/ --count --statistics

# Run the complete local CI gate (format check, flake8, headless pytest, emoji scan)
conda run -n synaptipy python scripts/verify_ci.py
```

Verify formatting non-destructively (matching GitHub Actions):

```bash
conda run -n synaptipy black --check --diff src/ tests/
conda run -n synaptipy isort --check --diff src/ tests/
```

## License Compliance

Synaptipy is licensed under the GNU Affero General Public License Version 3 (AGPL-3.0-or-later).

### License Requirements

Contributors must:

1. **Include license notice**: Reference the AGPL-3.0 license in new source files.
2. **Preserve copyright notices**: Retain existing copyright attributions.
3. **Document changes**: Record user-visible additions, fixes, and breaking changes under `[Unreleased]` in `CHANGELOG.md`.
4. **Share modifications**: Distribute complete corresponding source code when deploying modified builds.

### Adding New Files

Include the standard license header in new Python modules:

```python
#!/usr/bin/env python3
"""
Brief description of the module.

Detailed description of the module's purpose and functionality.

This file is part of Synaptipy, licensed under the GNU Affero General Public License v3.0.
See the LICENSE file in the root of the repository for full license details.
"""
```

### Third-Party Dependencies

All Python dependencies must be declared in `pyproject.toml` (the single source
of truth), and `requirements.txt` must be regenerated via
`pip-compile pyproject.toml -o requirements.txt` rather than edited manually.
Any new dependency must carry an AGPL-3.0-compatible license:

- GPL-3.0 and AGPL-3.0 are directly compatible.
- Permissive licenses (LGPL, MIT, BSD, Apache 2.0) are compatible alongside AGPL-3.0.
- Proprietary or non-commercial-only licenses are incompatible and must not be added.

Discuss proposed dependencies with the maintainers before opening a pull request,
and evaluate whether dynamic imports or data files require entries in `synaptipy.spec`.
