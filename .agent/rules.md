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

## IV. CI/CD & QUALITY ASSURANCE

**1. Linting Compliance (Flake8)**
* **Line Length**: Strictly < 120 characters (matches `.flake8`).
* **Complexity**: Keep function cyclomatic complexity under 10. Refactor if logic gets too nested.
* **Unused Imports**: Remove them. (Exception: `__init__.py` files).
* **Command**: Before finalizing code, the Agent should verify with: `flake8 src tests`

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

## V. DOCUMENTATION & PROFESSIONALISM

**1. Professional Tone & Style**
*   **No Emojis**: Emojis are strictly forbidden in all documentation (`README.md`, docs), commit messages, and code comments.
    *   *Forbidden*: "🚀 Key Features", "Fixed bug 🐛"
    *   *Required*: "Key Features", "Fixed bug in signal processor"
*   **Objective Language**: Use formal, technical language. Avoid marketing fluff or casual slang.
    *   *Bad*: "This app is super fast and cool."
    *   *Good*: "The application utilizes optimized algorithms for high-performance signal processing."

**2. Documentation Standards**
*   **Comprehensive Detail**: Documentation must accurately reflect the codebase capabilities. Do not omit technical details for the sake of brevity if they are crucial for understanding.
*   **Formatting**: Use standard Markdown consistently.
    *   Headers: `#` for titles, `##` for sections, `###` for subsections.
    *   Code Blocks: Always specify the language (e.g., `python`, `bash`).
    *   Lists: Use `-` for bullet points.
