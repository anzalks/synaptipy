# SYNAPTIPY PROJECT CONSTITUTION

## I. ARCHITECTURAL COMPLIANCE

**1. Separation of Concerns (Core vs. Application)**
* **Core Layer (`src/Synaptipy/core/`)**: Must contain **PURE LOGIC ONLY**.
    * **FORBIDDEN IMPORTS**: `PySide6`, `PyQt6`, `matplotlib.pyplot`, or any GUI-related libraries.
    * **Input/Output**: Functions must accept standard data types (NumPy arrays) and return structured objects (Dataclasses/Result Objects).
* **Application Layer (`src/Synaptipy/application/`)**: Handles all GUI interactions, widget management, and user feedback.

**2. Dependency & Import Integrity**
* **No "Dummy" Imports**: NEVER import core classes (`Recording`, `Channel`) from `dummy_classes.py` or similar hacks.
    * **Correct Usage**: Import from `src/Synaptipy/core/data_model.py`.
    * **Circular Imports**: Resolve them using `from typing import TYPE_CHECKING` blocks.

**3. Logging Standard**
* **No Prints**: `print()` statements are strictly forbidden in production code.
* **Dynamic Identity**: ALWAYS initialize loggers dynamically to avoid copy-paste errors.
    * *Correct:* `log = logging.getLogger(__name__)`
    * *Forbidden:* `log = logging.getLogger('hardcoded.string.path')`

## II. CODING STANDARDS & PATTERNS

### 1. Analysis Registry Pattern (The "Two-Layer" Rule)
All analysis features must be split into two distinct parts:
1.  **The Pure Logic Function** (in `core/`):
    * **MUST** return a typed Result Object (e.g., `BurstResult`), NOT a dictionary.
    * **MUST** accept explicit arguments (no `**kwargs` parsing inside logic).
2.  **The Registry Wrapper** (decorated with `@AnalysisRegistry.register`):
    * Parses `**kwargs` from the GUI.
    * Calls the Pure Logic Function.
    * **Returns** a flat `Dict[str, Any]` strictly for the GUI/Batch engine.
    * *Constraint:* Wrappers MUST NOT contain orchestration logic (e.g., calling function A then function B).

### 2. Data Contracts & Default Values
* **Primitive Obsession**: Core functions must never return unstructured tuples or dicts. Use `dataclasses` defined in `src/Synaptipy/core/results.py`.
* **Single Source of Truth**: Wrappers MUST NOT hardcode default values that differ from the Core function.
    * *Pattern:* The Wrapper should extract parameters using `.get()`. If the parameter is missing, pass `None` to the Core function and let the Core function apply the scientific default.

### 3. Visualization Safety Protocol (Factory Pattern)
* **Strict Prohibition**: Direct instantiation of `pg.PlotWidget` or `pg.GraphicsLayoutWidget` is **FORBIDDEN**.
    * *Reason:* Windows-specific OpenGL crashes and styling inconsistencies.
* **Mandatory Factory**: Always use `SynaptipyPlotFactory`.
    * *Code:* `from Synaptipy.shared.plot_factory import SynaptipyPlotFactory`
    * *Usage:* `self.plot = SynaptipyPlotFactory.create_plot_widget(...)`
* **Performance Throttling**:
    * **Downsampling**: For traces > 100,000 points, plotting widgets MUST implement 'Peak-to-Peak' or 'Subsample' downsampling logic to maintain 60 FPS.
    * **Update Coalescing**: Real-time plot updates must be debounced (min interval 30ms) to prevent blocking the GUI thread.

### 4. IO & Data Abstraction
* **No Direct I/O**: Never use `open()`, `numpy.load()`, or `pickle` directly in feature code. Use `NeoAdapter` or `DataLoader`.
* **Lazy Loading Strictness**:
    * **CRITICAL**: Never access `channel.data_trials` directly. In lazy mode, this list contains `None`.
    * **Correct Usage**: Always use `channel.get_data(trial_index)`, which handles lazy fetching safely.

### 5. Persistence Safety (No Magic Strings)
* **QSettings**: Do not hardcode app names or keys in `QSettings`.
* **Requirement**: Use constants from `src/Synaptipy/shared/constants.py` (e.g., `APP_NAME`).

## III. REQUIRED CONTEXT & REFERENCE ARCHETYPES

**CRITICAL INSTRUCTION:** You MUST read the **Template Files** below before writing any code.

* **The Analysis Standard (Immutable)**:
    * **File:** `src/Synaptipy/templates/analysis_template.py`
    * **Action:** Copy this structure for `core/analysis/`. Enforce Logic vs. Wrapper separation.

* **The GUI Tab Standard (Immutable)**:
    * **File:** `src/Synaptipy/templates/tab_template.py`
    * **Action:** Use this for all files in `application/gui/analysis_tabs/`.
    * **Crucial:** Must define `ANALYSIS_TAB_CLASS` at the end. Must override `_plot_analysis_visualizations`.

* **The Unit Test Standard (Immutable)**:
    * **File:** `src/Synaptipy/templates/test_template.py`
    * **Action:** Use `pytest` fixtures. Never import GUI widgets in `tests/core/`.

* **The Visualization Factory**:
    * **File:** `src/Synaptipy/shared/plot_factory.py`
    * **Action:** Use `create_plot_widget` for all plotting.

## IV. CI/CD & QUALITY ASSURANCE

**1. Linting Compliance (Flake8)**
* **Line Length**: Strictly < 120 characters (matches `.flake8`).
* **Complexity**: Keep function cyclomatic complexity under 10. Refactor if logic gets too nested.
* **Unused Imports**: Remove them. (Exception: `__init__.py` files).
* **Command**: Before finalizing code, the Agent should verify with: `flake8 src tests`
* **Pre-Push Mandate**: ALWAYS run `python scripts/verify_ci.py` before pushing or requesting review. This script replicates the strict CI/CD environment (Linting + Headless Tests). **Zero Tolerance** for failures (0 errors allowed).

**2. Cross-Platform Compatibility (The "Windows" Rule)**
* **Path Handling**: NEVER use string concatenation for paths (e.g., `"data/" + filename`).
    * **Requirement**: ALWAYS use `pathlib.Path` (e.g., `Path("data") / filename`).
    * *Reason*: The CI pipeline runs on `windows-latest`, which will fail on hardcoded forward slashes.
* **Encoding**: Always specify `encoding='utf-8'` when opening text files. Windows defaults to `cp1252` and will crash on special characters.

**3. Headless Testing Protocol**
* **Context**: The CI environment runs with `QT_QPA_PLATFORM: offscreen`.
* **Constraint**: Tests must NEVER require a physical window to be visible.
    * *Bad:* `widget.show()` (in a test without a fixture handling it).
    * *Good:* Instantiate widgets, verify state, but do not rely on rendering frames.
* **Qt Mocking**: Use `pytest-qt` fixtures (`qtbot`) for all GUI interactions in tests. Do not use `time.sleep()`; use `qtbot.wait()`.

**4. Dependency Management**
* **Lockfile Integrity**: If you import a new third-party library, you **MUST** explicitly tell the user to add it to `requirements.txt`.
* *Reason*: The CI pipeline installs dependencies strictly from `requirements.txt`. If you skip this, the build fails.

**5. IO & Data Abstraction**
* **Native Discovery**: In `NeoAdapter`, strictly prioritize `neo.io.get_io(filename)` over manual extension mapping lists (`IODict`), which become stale.
* **Memory Hygiene**: When aggregating signals from multiple segments, PRE-ALLOCATE NumPy arrays based on header info. Do not append to lists in a loop for massive datasets.

## V. DOCUMENTATION & PROFESSIONALISM

**1. Professional Tone & Style**
*   **No Emojis**: Emojis are strictly forbidden in **ALL** files (Source Code, Documentation, Commit Messages).
    *   *Forbidden*: "🚀 Key Features", "# TODO: Fix this 🐛", "print('Done! 🎉')"
    *   *Required*: "Key Features", "# TODO: Fix this bug", "print('Done!')"
*   **Objective Language**: Use formal, technical language. Avoid marketing fluff or casual slang.
    *   *Bad*: "This app is super fast and cool."
    *   *Good*: "The application utilizes optimized algorithms for high-performance signal processing."

**2. Documentation Standards**
*   **Comprehensive Detail**: Documentation must accurately reflect the codebase capabilities. Do not omit technical details for the sake of brevity if they are crucial for understanding.
*   **Formatting**: Use standard Markdown consistently.
    *   Headers: `#` for titles, `##` for sections, `###` for subsections.
    *   Code Blocks: Always specify the language (e.g., `python`, `bash`).
    *   Lists: Use `-` for bullet points.

## VI. REFACTORING CONSTRAINTS

**1. "God Object" Prevention**
*   **Class Limit**: No class should exceed **500 lines**. If it grows beyond, refactor into smaller, focused classes.
*   **Method Limit**: No single method should exceed **50 lines** of logic. Extract helper methods for complex logic.

**2. Explicit Error Handling**
*   **Forbidden**: Generic `except Exception` or bare `except:` blocks in production code.
*   **Requirement**: Catch specific exceptions (e.g., `KeyError`, `ValueError`, `IOError`). Use a global handler for truly unexpected errors.
*   *Reason*: Generic catches mask bugs and make debugging difficult.

**3. Domain Purity (Strict)**
* **FORBIDDEN**: Core domain objects (`Channel`, `Recording`, `Experiment`) must NOT hold direct references to infrastructure objects (e.g., `neo_block`, `neo.io` readers, file handles).
* **Requirement**: Use the `SourceHandle` protocol (`src/Synaptipy/core/source_interfaces.py`) for abstract data access.
* *Reason*: Decouples the core domain from specific I/O libraries (Neo), enabling easier testing and future library swaps.

**4. Test Canonicalization**
*   **Forbidden**: Standalone `verify_*.py` scripts for testing. All tests must be discoverable by `pytest`.
*   **Requirement**: All test files must reside in `tests/` and follow `test_*.py` naming.
*   *Reason*: Ensures CI runs all tests and provides uniform coverage reporting.

## VII. SCIENTIFIC RIGOR & MATHEMATICAL CORRECTNESS

**1. The Vectorization Mandate (Performance)**
* **Prohibition**: Python `for` loops are strictly **FORBIDDEN** for iterating over signal arrays, time series, or detected event lists (e.g., spikes) inside Core logic.
* **Requirement**: You MUST use NumPy vectorization, broadcasting, or `scipy.ndimage` operations.
    * *Bad*: `for i in range(len(data)): ...`
    * *Good*: `np.where(data > threshold)` or `data[indices] - data[indices-1]`

**2. The Provenance Protocol (Reproducibility)**
* **Traceability**: Every "Result Object" (e.g., `SpikeTrainResult`, `RinResult`) MUST contain a `parameters` field (Dict) storing the exact configuration used to generate it (e.g., threshold values, window sizes).
* **Constraint**: A scientist must be able to reconstruct the analysis solely from the saved Result object.

**3. Algorithmic Flexibility (No Hardcoding)**
* **Forbidden**: Hardcoded scientific bounds or constants (e.g., `tau_bounds=[0, 1]`, `threshold=-20`) inside logic functions.
* **Requirement**: All bounds and constants must be exposed as function arguments with defaults provided only in the `ui_params` of the Registry Wrapper, not the core logic.
* **Model Selection**: Fitting functions (e.g., Tau) MUST support multiple models (e.g., Mono-exponential vs. Bi-exponential) via a `mode` argument.

**4. Unit Safety & Validation**
* **Magnitude Checks**: Functions accepting `sampling_rate` MUST implement sanity checks (e.g., if `fs < 100`, warn "Is this Hz or kHz?").
* **Zero-State Safety**: All statistical aggregators (mean, std) MUST explicitly handle empty arrays to prevent `NaN` propagation or RuntimeWarnings.

**5. Infrastructure Robustness (IO)**
* **Native Discovery**: In `neo_adapter.py`, strictly prioritize `neo.io.get_io(filename)` over manual extension mapping lists (`IODict`). Manual mapping is only a fallback.
* **Memory Hygiene**: When aggregating signals from multiple segments, PRE-ALLOCATE NumPy arrays based on header info. Do not use `.append()` on lists inside data loops.