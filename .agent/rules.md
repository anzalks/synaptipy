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