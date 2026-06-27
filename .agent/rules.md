# SYNAPTIPY PROJECT CONSTITUTION

## I. ARCHITECTURAL COMPLIANCE

**1. Separation of Concerns (Core vs. Application)**
* **Core Layer (`src/synaptipy/core/`)**: Must contain **PURE LOGIC ONLY**.
    * **FORBIDDEN IMPORTS**: `PySide6`, `PyQt6`, `matplotlib.pyplot`, or any GUI-related libraries.
    * **Input/Output**: Functions must accept standard data types (NumPy arrays) and return structured objects (Dataclasses/Result Objects).
* **Application Layer (`src/synaptipy/application/`)**: Handles all GUI interactions, widget management, and user feedback.

**2. Dependency & Import Integrity**
* **No "Dummy" Imports**: NEVER import core classes (`Recording`, `Channel`) from `dummy_classes.py` or similar hacks.
    * **Correct Usage**: Import from `src/synaptipy/core/data_model.py`.
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
* **Primitive Obsession**: Core functions must never return unstructured tuples or dicts. Use `dataclasses` defined in `src/synaptipy/core/results.py`.
* **Single Source of Truth**: Wrappers MUST NOT hardcode default values that differ from the Core function.
    * *Pattern:* The Wrapper should extract parameters using `.get()`. If the parameter is missing, pass `None` to the Core function and let the Core function apply the scientific default.

### 3. Visualization Safety Protocol (Factory Pattern)
* **Strict Prohibition**: Direct instantiation of `pg.PlotWidget` or `pg.GraphicsLayoutWidget` is **FORBIDDEN**.
    * *Reason:* Windows-specific OpenGL crashes and styling inconsistencies.
* **Mandatory Factory**: Always use `SynaptipyPlotFactory`.
    * *Code:* `from synaptipy.shared.plot_factory import synaptipyPlotFactory`
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
* **Requirement**: Use constants from `src/synaptipy/shared/constants.py` (e.g., `APP_NAME`).

### 6. Zero-Tolerance for Dead Code & Duplication (AUDIT LESSON)
* **Unused Variables & Imports**: Must be aggressively cleared. Do not leave `dt = 0.001` if `dt` is never used. Do not import types like `List` if unused. Flake8 F401/F841 rules MUST be respected.
* **Duplicate Definitions**: Do not define a dictionary key twice in the same structure, and never define a method twice in the same class (e.g., leaving a stub above the real implementation).

## III. REQUIRED CONTEXT & REFERENCE ARCHETYPES

**CRITICAL INSTRUCTION:** You MUST read the **Template Files** below before writing any code.

* **The Analysis Standard (Immutable)**:
    * **File:** `src/synaptipy/templates/analysis_template.py`
    * **Action:** Copy this structure for `core/analysis/`. Enforce Logic vs. Wrapper separation.

* **The GUI Tab Standard (Immutable)**:
    * **File:** `src/synaptipy/templates/tab_template.py`
    * **Action:** Use this for all files in `application/gui/analysis_tabs/`.
    * **Crucial:** Must define `ANALYSIS_TAB_CLASS` at the end. Must override `_plot_analysis_visualizations`.

* **The Unit Test Standard (Immutable)**:
    * **File:** `src/synaptipy/templates/test_template.py`
    * **Action:** Use `pytest` fixtures. Never import GUI widgets in `tests/core/`.

* **The Visualization Factory**:
    * **File:** `src/synaptipy/shared/plot_factory.py`
    * **Action:** Use `create_plot_widget` for all plotting.

## IV. CI/CD & QUALITY ASSURANCE

**1. Linting Compliance (Flake8 Strictness)**
* **Line Length**: Strictly <= 127 characters (matches the project `.flake8` configuration; do not use 120).
* **Complexity**: Keep function cyclomatic complexity strictly under 10. Refactor complex logic into helper functions before resorting to `# noqa: C901`. Every `noqa` suppression must include a comment explaining why the suppression is necessary.
* **Unused Imports/Vars**: Clean them up before finalizing code. Flake8 F401 (unused import) and F841 (unused variable) violations are not acceptable.
* **Execution Constraint**: Before marking any Phase or batch of work completed, the Agent MUST run:
    ```bash
    conda run -n synaptipy flake8 src/ tests/ scripts/ --count --max-complexity=10 --max-line-length=127 --statistics
    ```
    and verify the output is exactly `0`.
* **Pre-Push Mandate**: ALWAYS run `python scripts/verify_ci.py` before pushing or requesting review. This script replicates the strict CI/CD environment (linting, headless tests, emoji scan). Zero tolerance for failures.
* **Whitespace Hygiene**: Agents MUST inspect and fix all flake8 whitespace warnings (W293, W391, W504, etc.) before finishing a task.

**2. Mandatory Formatting and Test Gate (Zero-Tolerance)**
* **Every Generation Cycle**: After writing or modifying any Python file, the Agent MUST automatically run all of the following in sequence and fix every error before proceeding:
    ```bash
    conda run -n synaptipy black src/ tests/ scripts/
    conda run -n synaptipy isort src/ tests/ scripts/
    conda run -n synaptipy flake8 src/ tests/ scripts/ --count --max-complexity=10 --max-line-length=127 --statistics
    conda run -n synaptipy python scripts/verify_ci.py
    ```
* **Non-Negotiable Rule**: Do NOT stop generating or fixing until all four commands succeed with zero errors and all tests pass. If tests fail, automatically debug and fix regressions before moving on.
* **Pre-Completion Checklist**: Before marking any task as complete, `scripts/verify_ci.py` MUST output `[SUCCESS] All CI Checks Passed!`.

**3. Cross-Platform Compatibility (The "Windows" Rule)**
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

**4. Dependency Management (The Unified Source of Truth)**
* **Single Source of Truth**: `pyproject.toml` is the absolute single source of truth for all Python dependencies. No other file may introduce packages that are not declared there first.
* **Lockfile Automation (DO NOT EDIT MANUALLY)**: `requirements.txt` is strictly a compiled lockfile. It MUST NEVER be edited by hand. If dependencies change, run `pip-compile pyproject.toml -o requirements.txt` (via `pip-tools`) to regenerate it. An agent must instruct the user to run this command if a dependency change is needed.
* **PEP 508 Environment Markers for OS Edge Cases**: You MUST NOT create separate OS-specific dependency files (e.g., `environment-windows.yml`). If a package is required only on a specific operating system, declare it in `pyproject.toml` using standard PEP 508 environment markers:
    * Windows only: `"pywin32 ; sys_platform == 'win32'"`
    * macOS only: `"pyobjc-framework-Cocoa ; sys_platform == 'darwin'"`
* **Universal Environment**: `environment.yml` manages only cross-platform system-level setup (e.g., Python version, conda channels) and delegates package installation by calling `pip install -e .[dev]`. It MUST NOT duplicate package pinning already expressed in `pyproject.toml`.

**5. IO & Data Abstraction**
* **Native Discovery**: In `NeoAdapter`, strictly prioritize `neo.io.get_io(filename)` over manual extension mapping lists (`IODict`), which become stale.
* **Memory Hygiene**: When aggregating signals from multiple segments, PRE-ALLOCATE NumPy arrays based on header info. Do not append to lists in a loop for massive datasets.

**6. Dependency Management & Synchronization (The "Three-Pillar" Rule)**
* **Unconditional Sync**: Dependency updates MUST be applied consistently across the entire ecosystem. If you add or remove an environment requirement, you MUST synchronize:
    1. `pyproject.toml` (authoritative source -- edit this first)
    2. Regenerate `requirements.txt` via `pip-compile pyproject.toml -o requirements.txt` (never edit manually)
    3. `environment.yml` (system setup only -- update Python version or conda channels here)
* **Mismatch Prevention**: Ensure Python floor versions match exactly (e.g., `>=3.10`). Do not leave old classifiers (e.g., Python 3.9) in `pyproject.toml` if the floor is 3.10.

**7. Headless Execution Mandate (CI/CD Crash Prevention)**
* **Hard Requirement**: Any automated script that instantiates Qt widgets -- including unit tests, benchmarking scripts, and screenshot generators such as `capture_screenshots.py` -- MUST enforce headless mode before any Qt object is created:
    ```python
    import os
    if "QT_QPA_PLATFORM" not in os.environ:
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
    ```
* **Rationale**: GitHub Actions Linux and macOS runners operate without a display server. Failing to set this environment variable causes a fatal SIGSEGV crash that silently kills the test worker process and reports exit code 127 instead of a meaningful test failure.
* **Scope**: This rule applies to `scripts/capture_screenshots.py`, `scripts/benchmark_rendering.py`, all files under `tests/gui/`, and any future script that imports `PySide6` or `pyqtgraph` at the top level.

**8. PyInstaller Hidden Imports Guard**
* **Mandatory Evaluation**: Because PyInstaller's bytecode scanner does not follow dynamic imports, any package newly added to the project dependencies MUST be evaluated for inclusion in `synaptipy.spec`:
    * If the package uses plugin patterns, type registries, or lazy module loading (common in `neo`, `pynwb`, `hdmf`, `dask`, `pyqtgraph`), add `collect_submodules("package_name")` to `hiddenimports`.
    * If the package ships non-Python data files (schemas, JSON specs, Qt resources), add `collect_data_files("package_name")` to `datas`.
* **Version Sync**: The `synaptipy.spec` version regex `re.search(r'^version\s*=\s*"([^"]+)"', ...)` reads from `pyproject.toml` at build time. `bump_version.py` updates `pyproject.toml`, `installer/windows_setup.iss`, and `environment.yml` atomically. The spec must NEVER hardcode a version string.

## V. DOCUMENTATION & PROFESSIONALISM

**1. Zero-Tolerance Emoji Policy**
*   **FATAL CI CRASH WARNING**: Generating emojis in any Markdown or Python file will instantly trigger a fatal CI failure via `scripts/verify_ci.py`, blocking the release pipeline. There are no exceptions and no overrides.
*   **Scope**: Emojis are strictly forbidden in **ALL** project files without exception: source code, documentation (`.md`, `.rst`), commit messages, docstrings, and inline comments.
*   **Covered Unicode ranges** (enforced by `verify_ci.py`):
    *   Supplementary plane U+10000-U+10FFFF (e.g., 😀 🎉 🚀)
    *   Miscellaneous Symbols U+2600-U+26FF (e.g., ⚠ ☆ ★)
    *   Dingbats U+2700-U+27BF (e.g., ✅ ❌ ✨ ✔ ➔)
    *   Star and circle emoji U+2B50, U+2B55
    *   Variation selectors U+FE00-U+FE0F (e.g., the invisible U+FE0F that converts ⚠ into ⚠️)
*   **Permitted exception**: Box-drawing characters U+2500-U+25FF (e.g., `─`, `│`) used as structural separators in code comments or YAML section dividers.
*   *Forbidden patterns* (replace as shown):
    *   `🚀 Key Features` → `Key Features`
    *   `# TODO: Fix this 🐛` → `# TODO: Fix this bug`
    *   `## ✅ Benefits` → `## Benefits`
    *   `- ❌ Removed: ...` → `- Removed: ...`
    *   `print('Done! 🎉')` → `print('Done!')`
    *   `"⚠️ Active preprocessing"` → `"[PREPROCESSING ACTIVE]"`
*   **Enforcement**: Before completing any documentation task, run `python scripts/verify_ci.py` and confirm the `[PASS] Emoji Check Passed` line appears.

**2. Source-Verified Accuracy (The "Ground Truth" Rule)**
*   **CRITICAL**: Every technical statement in documentation MUST be verified against the actual source code before being written. Never document from memory, assumption, or from other documentation files.
*   **CLI entry points**: ALWAYS read `pyproject.toml` `[project.scripts]` to confirm the exact command name(s) before documenting CLI usage. The command is `synaptipy` (NOT `synaptipy-gui`).
*   **CLI flags**: ALWAYS read `src/synaptipy/__main__.py` to confirm argument names before documenting them.
*   **Python version floor**: ALWAYS check `pyproject.toml` `requires-python` field. Current floor is `>=3.10`.
*   **Import paths**: ALWAYS verify module paths by reading the actual `src/` tree. Do not invent paths. Analysis functions live in `src/synaptipy/core/analysis/`, not in a top-level `analysis/` module.
*   **Function signatures**: ALWAYS read the function definition before documenting its arguments. Do not add parameters that do not exist in the actual code.
*   **Default paths**: ALWAYS read the relevant config/shared module to verify default directory paths (e.g., log directory is `~/.synaptipy/logs/` — confirmed from `src/synaptipy/shared/logging_config.py`).

**3. Publication-Quality Language**
*   **Objective Language**: Use formal, precise, technical language throughout. Avoid marketing language, casual phrasing, or informal abbreviations.
    *   *Forbidden*: "This app is super fast and cool."
    *   *Required*: "The application uses optimized rendering with automatic downsampling for high-performance signal visualization."
*   **Prohibited filler phrases**: Never use: "simply", "just", "easy", "quick", "seamlessly", "powerful", "robust" (unless quantified), "blazing fast", "out of the box", "no-brainer", "super", "awesome", "cool".
*   **Active, factual constructions**: State what the system does, not vague claims about what it "can" or "might" do.
    *   *Forbidden*: "You can easily load files."
    *   *Required*: "Load a file by selecting File > Open or pressing Ctrl+O."

**4. Markdown & reStructuredText Formatting Standards**
*   **Header hierarchy**: Strict and consistent — `#` for document title, `##` for major sections, `###` for subsections, `####` for sub-subsections. No skipping levels.
*   **Code blocks**: ALL code blocks MUST include a language specifier. No bare triple-backtick blocks.
    *   Shell commands: ` ```bash `
    *   Python code: ` ```python `
    *   YAML config: ` ```yaml `
    *   Plain output: ` ```text ` (not ` ``` `)
*   **Lists**: Use `-` for unordered lists. Use `1.` only for genuinely ordered/sequential steps.
*   **Inline code**: Wrap all command names, file paths, function names, class names, and identifiers in backticks.
*   **No raw HTML** in Markdown files unless absolutely required (e.g., image sizing in .rst).
*   **Typography Restriction**: NEVER use em dashes (`—`) or en dashes (`–`) in any prose, documentation, code, or changelogs. ALWAYS use standard ASCII hyphens (`-`). AI agents often default to em dashes when summarizing; you must actively avoid generating them.

**5. Sphinx Build Compliance**
*   **Zero Warnings Policy**: The Sphinx build (`make html` from `docs/`) MUST produce zero warnings. Any new documentation change must be validated by running the build.
    *   Command: `conda run -n synaptipy sphinx-build -W -b html docs/ docs/_build/html`
    *   The `-W` flag treats all warnings as errors.
*   **Valid cross-references**: All `:ref:`, `:doc:`, and `.. toctree::` entries must resolve without error.
*   **No placeholder content**: Documentation MUST NOT contain lorem ipsum, `TODO:`, `FIXME:`, or incomplete sections marked with `[TBD]` or similar. Every section must be complete before merging.

**6. Documentation & Changelog Standards**
*   **Changelog Maintenance**: Any bug fixes, performance improvements, or new features MUST be added to the `[Unreleased]` section of `CHANGELOG.md` immediately when the work completes. Do not defer changelog entries to release time.
*   **Consistent Terminology**: Use the exact project name `Synaptipy` (capital S, lowercase the rest) throughout. Do not use `SynaptiPy`, `synaptipy`, or `SYNAPTIPY` in prose (only in code/CLI contexts).
*   **Cross-reference accuracy**: When one documentation file references another, verify the link target exists. Dead links are not acceptable.

## VI. UI ARCHITECTURE IMMUTABLE DIRECTIVES

### RULE 1 - Strict 5-Pillar Analysis Tab Architecture
All core analysis features MUST be rigidly mapped into exactly five UI subtabs:
1. `Passive Properties`
2. `Single Spike Kinetics`
3. `Firing Dynamics`
4. `Synaptic Events`
5. `Evoked Responses`

Any highly specialized or novel metric requested in the future MUST be implemented
as a separate file in `examples/plugins/` and NEVER added to the core UI tabs.
This rule is immutable: no exceptions are permitted without a documented architectural
decision record approved by the lead developer.

### RULE 2 - Popup Discipline
Never trigger popup plots automatically upon file load. Analysis popups MUST ONLY
trigger when the user explicitly navigates to the `Analyser` tab or clicks a
dedicated plot button. Auto-popup on file load is forbidden without exception.

## VII. REFACTORING CONSTRAINTS

**1. "God Object" Prevention**
*   **Class Limit**: No class should exceed **500 lines**. If it grows beyond, refactor into smaller, focused classes.
*   **Method Limit**: No single method should exceed **50 lines** of logic. Extract helper methods for complex logic.

**2. Explicit Error Handling**
*   **Forbidden**: Generic `except Exception` or bare `except:` blocks in production code.
*   **Requirement**: Catch specific exceptions (e.g., `KeyError`, `ValueError`, `IOError`). Use a global handler for truly unexpected errors.
*   *Reason*: Generic catches mask bugs and make debugging difficult.

**3. Domain Purity (Strict)**
* **FORBIDDEN**: Core domain objects (`Channel`, `Recording`, `Experiment`) must NOT hold direct references to infrastructure objects (e.g., `neo_block`, `neo.io` readers, file handles).
* **Requirement**: Use the `SourceHandle` protocol (`src/synaptipy/core/source_interfaces.py`) for abstract data access.
* *Reason*: Decouples the core domain from specific I/O libraries (Neo), enabling easier testing and future library swaps.

## VIII. NATIVE CI/CD & TELEMETRY

### RULE 0 - Codecov Pathing Integrity
**Codecov Pathing Integrity:** When modifying testing or CI configurations, you MUST preserve the `[tool.coverage.paths]` mapping in `pyproject.toml`. GitHub Actions runners (Linux, macOS, Windows) execute in absolute paths that do not exist on the git tree. Stripping these mappings will result in a 0% coverage failure on Codecov.

### RULE 3 - Native CI/CD & Telemetry
Never integrate third-party coverage dashboards or telemetry services (e.g., Codecov, Coveralls). All test coverage reporting, metrics, and CI analytics MUST remain strictly native to GitHub via standard Actions and PR comments.

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
**8. The Epsilon Guard Rule (Division-by-Zero Prevention)**
* **Hard Prohibition**: NEVER use exact floating-point equality to test whether a biological or mathematical value is zero (e.g., `if value == 0:` or `if denominator == 0:`). Hardware noise, floating-point underflow, and subtraction cancellation make exact zero comparisons unreliable in electrophysiology data.
* **Mandatory Pattern**: Always use an epsilon-based comparison:
    ```python
    EPSILON = 1e-9  # appropriate for biological voltage (mV) and time (s) scales
    if abs(denominator) < EPSILON:
        return np.nan  # or 0.0 if a sentinel is more appropriate for the metric
    ```
* **Contextual Epsilons**: Choose the epsilon value to match the physical scale of the quantity:
    * Voltage denominators (mV scale): `1e-9`
    * Time denominators (s scale): `1e-9`
    * Current denominators (pA scale): `1e-15`
    * Squared time denominators (s^2, used in LV): `1e-15`
* **Propagation**: When a division produces `NaN` due to an epsilon guard, downstream aggregators MUST use `numpy.nanmean` / `numpy.nanstd` rather than `numpy.mean` / `numpy.std` to exclude the guarded value from summary statistics.

**9. FAIR Compliance for Preprocessing Provenance**
* **Mandate**: Any new analytical function that modifies the raw data trace -- including filters, baseline subtractions, detrending, artefact blanking, or downsampling -- MUST record its operation in the `pipeline_context` of the enclosing analysis call.
* **Required fields** (passed as a dict to the context):
    * `operation`: short canonical name (e.g., `"lowpass_filter"`, `"baseline_subtract"`)
    * `parameters`: a dict of all non-default arguments used (e.g., `{"cutoff_hz": 300, "order": 4}`)
    * `timestamp`: ISO 8601 string at the time of application
* **NWB export**: Preprocessing context entries are exported to the NWB `ProcessingModule` named `preprocessing` as a `DynamicTable` with columns `timestamp`, `operation`, and `parameters` (JSON-serialised). This satisfies the DANDI Archive reproducibility requirement that all transformations applied to raw data are traceable from the archived NWB file alone.
* **Enforcement**: Any analysis wrapper that accepts preprocessing settings MUST pass them through the pipeline context. Omitting provenance from a data-modifying operation is treated as a correctness defect, not a cosmetic issue.
**5. Infrastructure Robustness (IO)**
* **Native Discovery**: In `neo_adapter.py`, strictly prioritize `neo.io.get_io(filename)` over manual extension mapping lists (`IODict`). Manual mapping is only a fallback.
* **Memory Hygiene**: When aggregating signals from multiple segments, PRE-ALLOCATE NumPy arrays based on header info. Do not use `.append()` on lists inside data loops.

**6. Unit Safety, Conversion & Validation (AUDIT LESSON)**
* **Explicit Conversions**: When a formula requires unit conversions (e.g., current in pA to resistance in MOhm), the mathematical conversion MUST be explicitly documented as an inline comment.
    * *Example:* `# Rin = |delta_V| / |delta_I| -> mV / (pA / 1000) = MOhm`
* **Thresholds & Derivatives**: If a parameter operates in one unit (e.g., V/s limit) but the data is in another (e.g., mV), explicit scaling (e.g., `* 1000.0`) must be done immediately, and testing must assert this conversion.

**7. Edge-Case & Noise Robustness (AUDIT LESSON)**
* **Sentinel Values**: Do NOT use `0.0` as a fallback or default for biological metrics like `max_dvdt` or `ap_threshold` when they are unable to be computed. Use `np.nan` or a representative baseline boundary. Using `0.0` creates severe statistical artifacts in Pandas aggregations.
* **Noise Resistance**: Prefer percentiles (e.g., `np.percentile(data, 5)`) over absolute extrema (`np.min(data)`) for calculating baselines or maximum deflections (like sag potential), which are heavily susceptible to single-point hardware noise spikes.
* **Empty Vectors**: Always check `if my_array.size == 0:` before executing math that causes RuntimeWarnings (e.g. `np.max()`, `np.mean()`) to handle edge cases where zero spikes/events are found.