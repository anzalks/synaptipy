# Synaptipy — GitHub Copilot Instructions

## Language and framework
- Python 3.10–3.12, PySide6 (Qt6), pyqtgraph, NumPy, SciPy
- Tests use pytest + pytest-qt; CI runs on ubuntu/windows/macos × Python 3.10/3.11/3.12
- Linting: `flake8 src/ tests/` with `.flake8` config (max-line-length=120, max-complexity=10)
- Formatting: `black` (line-length=120, target-version=py310) and `isort` (profile=black)
- CI enforces `black --check`, `isort --check`, and `flake8` — PRs that fail any of these are rejected

## Code style
- Follow PEP 8; max line length 120 characters
- All code must be formatted with `black` and imports sorted with `isort`
- All public functions and classes must have docstrings
- Use type hints throughout
- Keep function complexity ≤ 10 (flake8 C901)

## Analysis registry pattern
- New analysis functions are registered with `@AnalysisRegistry.register(name=..., ui_params=[...], plots=[...])`
- `ui_params` entries drive the GUI automatically; use `visible_when: {"param": "...", "value": "..."}` for conditional visibility
- Wrapper functions must return a plain `dict`; private keys (starting with `_`) are hidden from the results table

### Registry import rule — DO NOT import only registry.py
To populate the `AnalysisRegistry`, **import the full package**
`import Synaptipy.core.analysis` (which triggers `__init__.py` → `from . import
basic_features`, etc.).  **Never** rely on
`from Synaptipy.core.analysis.registry import AnalysisRegistry` alone — that
only imports the class and does NOT execute the analysis sub-modules' decorators.
This was the root cause of the Windows bug where the Analyser tab showed 0 tabs
while macOS showed 15 (on macOS the batch engine happened to be imported earlier
via a different path, masking the issue).

### Editable install must point to the active workspace
`pip install -e .` stores the editable project location.  If the repo is cloned
to a new directory, the old editable link still points to the previous path.
Run `pip install -e .` from the new workspace to update.  Symptom: modules
visible on disk (`capacitance.py`, `optogenetics.py`, `train_dynamics.py`) throw
`ModuleNotFoundError` because Python resolves the package from the stale path.

### Preprocessing reset must propagate globally
`BaseAnalysisTab._handle_preprocessing_reset()` is connected to
`PreprocessingWidget.preprocessing_reset_requested`.  When fired it must:
1. Clear `_active_preprocessing_settings`, `_preprocessed_data`, and `pipeline`
2. Call `preprocessing_widget.reset_ui()` to reset combo boxes to "None"
3. Walk up to the parent `AnalyserTab` and call `set_global_preprocessing(None)`
   so **all** sibling tabs also reset
4. Clear `SessionManager().preprocessing_settings`
5. Re-plot with raw data

`apply_global_preprocessing(None)` (called on sibling tabs) must also call
`preprocessing_widget.reset_ui()` so every tab's UI visually reflects the reset.

## CI / test rules — DO NOT VIOLATE

### PySide6 version constraint — DO NOT WIDEN
`requirements.txt`, `pyproject.toml`, and `environment.yml` all pin
`pyside6==6.7.3` (exact).  **Do not remove or loosen this pin.**

PySide6 6.10.x changed the internal signal-connection machinery so that
deferred ViewBox geometry callbacks re-queue themselves *during* `connect()`
calls inside `PlotItem.__init__`.  Because the canvas reuses a single
`GraphicsLayoutWidget` across many test invocations, stale post-`widget.clear()`
events that are still in the queue when the next `addPlot()` runs dereference
already-freed C++ pointers → access violation (Windows) / segfault (macOS).
This was diagnosed across CI runs 22418950288 – 22420935486 on all platforms.
The constraint must stay until pyqtgraph ships a fix or we switch to creating
a fresh `GraphicsLayoutWidget` per rebuild cycle.

### Local macOS exit codes are misleading
`pytest_sessionfinish` calls `os._exit()` (macOS/Linux) or
`kernel32.TerminateProcess()` (Windows) in offscreen mode; the macOS process
always prints `Abort trap: 6` even when all tests passed.  **Never judge a
local macOS run by the shell exit code.**  Check the pytest output lines
(`N passed`, zero `FAILED`):
```bash
conda run -n synaptipy python -m pytest tests/ 2>&1 | grep -c PASSED
conda run -n synaptipy python -m pytest tests/ 2>&1 | grep "FAILED\|ERROR "
```

### Windows pytest_sessionfinish uses TerminateProcess — DO NOT CHANGE
`pytest_sessionfinish` calls `kernel32.TerminateProcess(ctypes.c_void_p(-1), int(exitstatus))`
on Windows.  **Do not replace with `os._exit()`, `RtlExitUserProcess`, or any
other function.**

- `os._exit()` calls `ExitProcess()` which fires `DLL_PROCESS_DETACH` on all
  loaded DLLs (including Qt) → access violation on freed Qt C++ objects.
- `ntdll.RtlExitUserProcess()` still calls `LdrShutdownProcess()` which also
  fires `DLL_PROCESS_DETACH` → same crash.  Confirmed via faulthandler traceback
  in CI run 22433271920: crash at `conftest.py::pytest_sessionfinish` line 76.
- `kernel32.TerminateProcess()` is the only API that truly bypasses
  `DLL_PROCESS_DETACH` (MSDN: "does not run the DLL entry function with
  DLL_PROCESS_DETACH").

`argtypes` and `ctypes.c_void_p(-1)` are mandatory:
without them, ctypes defaults `GetCurrentProcess()` restype to `c_int` (32-bit),
truncating the pseudo-handle from `0xFFFFFFFFFFFFFFFF` to `0xFFFFFFFF`.
`TerminateProcess` then receives the wrong handle, returns `ERROR_INVALID_HANDLE`,
falls through to normal Qt-cleanup exit → crash → exit code 127.

### GC must stay disabled in offscreen mode
`tests/conftest.py::pytest_configure` calls `gc.disable()` when
`QT_QPA_PLATFORM=offscreen`.  Do not remove this — cyclic GC can trigger
`tp_dealloc` while Qt's C++ destructor chain is running, causing SIGBUS /
access violations.

### processEvents() before addPlot() — Windows/Linux offscreen only
`SynaptipyPlotCanvas.add_plot()` calls `QCoreApplication.processEvents()`
before `widget.addPlot()` when `QT_QPA_PLATFORM=offscreen` **and**
`sys.platform != 'darwin'`.  Do not remove either condition.  On Windows +
PySide6 ≥ 6.9 deferred callbacks pending from a prior `widget.clear()` fire
*inside* `PlotItem.__init__()`, dereference freed C++ pointers, and silently
kill the test worker process.  On macOS `_unlink_all_plots()` + `_close_all_plots()`
disconnect all signals before `widget.clear()` so no stale callbacks queue up;
calling `processEvents()` there would instead execute post-`widget.clear()`
callbacks that reference freed C++ ViewBox objects → SIGSEGV.

### _cancel_pending_qt_events() uses processEvents() on Windows/Linux
`SynaptipyPlotCanvas._cancel_pending_qt_events()` calls
`QCoreApplication.processEvents()` (not `removePostedEvents()`) on Win/Linux
BEFORE `widget.clear()`.  This executes pending ViewBox geometry callbacks
while all C++ objects are still alive.  On PySide6 >= 6.10, simply discarding
with `removePostedEvents()` does NOT prevent crashes — PySide6 internally
re-queues some callbacks during `connect()` sequences in `PlotItem.__init__`.
macOS is excluded because `_unlink_all_plots()` prevents new callbacks from
being queued during `widget.clear()`.

### Drain fixtures use removePostedEvents() — skip macOS
All per-test drain fixtures (global conftest, `test_explorer_refactor.py`,
`test_plot_canvas.py`) call `QCoreApplication.removePostedEvents(None, 0)`
and guard with `if sys.platform != 'darwin': return`.

**Why removePostedEvents in fixtures vs processEvents in _cancel_pending_qt_events?**
In drain fixtures, `processEvents()` would run events belonging to session-scoped
widgets of OTHER tests, risking interaction crashes.  `removePostedEvents()` safely
discards inter-test residue; any remaining dirty ViewBox state is resolved by the
`processEvents()` call inside `_cancel_pending_qt_events()` at the START of the
next `rebuild_plots()`.

**Why skip macOS in drain fixtures?**  On macOS, pyqtgraph posts geometry events
between tests that maintain `AllViews` / geometry caches.  Draining them globally
corrupts session-scoped widget state and causes segfaults in `widget.clear()`.

### enableMenu=False in offscreen mode
`add_plot()` passes `enableMenu=False` to `widget.addPlot()` when offscreen.
This prevents `ViewBoxMenu.__init__` (which calls `QWidgetAction`) from
crashing on Windows/macOS without a real display.

### Plot teardown order in clear_plots()
The mandatory sequence is:
1. `_unlink_all_plots()` — break axis links before teardown
2. `_close_all_plots()` — disconnect ctrl signals and call `PlotItem.close()` while scene is valid
3. `_cancel_pending_qt_events()` — **execute** (not discard) stale events on Win/Linux while
   all C++ objects are alive; macOS skipped (unlink+close prevent queuing)
4. `widget.clear()` — destroy C++ children
5. `plot_items.clear()` — drop Python refs *after* C++ teardown
6. `_flush_qt_registry()` — drain events posted *by* `widget.clear()`:
   - macOS: `processEvents()` (signals already disconnected by step 2, so no freed-object
     callbacks can fire; executing ensures AllViews/geometry caches stay consistent)
   - Win/Linux: `removePostedEvents()` (post-clear events already executed in step 3)

## Explorer tab — GraphicsLayoutWidget rebuild rules

### Fresh widget on every rebuild — DO NOT reuse via widget.clear()
`ExplorerPlotCanvas.rebuild_plots()` creates a **new `GraphicsLayoutWidget`**
and swaps it into the parent layout, then deletes the old widget via
`deleteLater()`.  **Do not revert to calling `widget.clear()` + `addPlot()`
on the same widget.**

`widget.clear()` leaves Qt's internal scene graph in a broken state on Windows
(PySide6 6.7.x + pyqtgraph 0.13.x).  Specifically:
- `GraphicsLayout.removeItem()` calls `scene().removeItem()` for each PlotItem
  and its border, then disconnects `geometryChanged`.
- After clear, the viewport repaints once (showing nothing).
- When new PlotItems are added, the scene tracks them but the viewport's
  dirty-region heuristic (MinimalViewportUpdate) considers all regions clean
  because the previous repaint covered the entire viewport.
- Result: data items exist in the scene but are never painted — plots appear
  blank despite `listDataItems()` confirming items are present.

Switching to `FullViewportUpdate` mode partially helps but does not fix all
cases (stale `PlotItem.autoBtn = None` callbacks from `PlotItem.close()`
fire during `processEvents()` and crash).

The only reliable fix is a fresh widget per rebuild cycle.  The performance
cost is negligible (widget creation is < 5 ms).

**Implementation checklist for rebuild_plots():**
1. Find old widget's position in parent `QGridLayout`
2. Clear Python refs (`plot_items`, `plot_widgets`, etc.) BEFORE deleting
3. Create new widget via `SynaptipyPlotFactory.create_graphics_layout()`
4. `removeWidget(old)` → `old.hide()` → `old.setParent(None)` → `old.deleteLater()`
5. `addWidget(new, row, col, rspan, cspan)` at the same grid position
6. Assign `self.widget = new`

### Disable ViewBox auto-range in Explorer plots
After creating each PlotItem in `rebuild_plots()`, call
`plot_item.getViewBox().disableAutoRange()` **immediately**.  The Explorer
manages view ranges explicitly via `_reset_view()`.

If auto-range is left enabled (the pyqtgraph default), ViewBox queues a
**deferred** `updateAutoRange()` callback (`QTimer.singleShot(0, ...)`) every
time `plot_item.plot()` adds data.  These deferred callbacks fire *after*
`_reset_view()` has already set the correct X/Y ranges, overriding them with
a full-data auto-range.  Symptoms: data appears "shrunk" or the X-axis shows
a much wider range than expected (e.g. −25 to +17 instead of 0 to 17).

### Compute base_x_range from actual time vectors
`_calculate_base_ranges()` must derive `base_x_range` from
`channel.get_relative_time_vector(0)` (which always starts at 0), **not** from
`recording.duration` alone.  Some ABF protocols set a negative `t_start` at the
Neo level; `recording.duration` may reflect the full sweep length while the
plotted time axis starts at 0.

### Disconnect old ViewBox signals before widget replacement — DO NOT REMOVE
`ExplorerPlotCanvas.rebuild_plots()` disconnects `sigXRangeChanged`,
`sigYRangeChanged`, and `sigResized` on every old ViewBox **before** clearing
`plot_items` and calling `deleteLater()` on the old widget.

Without this, old ViewBoxes survive until the next event-loop iteration (Qt's
`deleteLater()` semantics) and can still emit signals.  Those signals propagate
through the canvas's `x_range_changed` → `_on_vb_x_range_changed` chain and
corrupt the slider/scrollbar values for the NEW recording.  This was the root
cause of the "X-axis shifted right" bug when cycling files.

### _reset_view() must block X-link propagation — DO NOT REMOVE
`_reset_view()` calls `vb.blockLink(True)` on **all** ViewBoxes before setting
X/Y ranges, then `vb.blockLink(False)` after.  Without this,
`linkedViewChanged()` recalculates X ranges from screen-geometry pixel offsets
between stacked ViewBoxes (which differ due to Y-axis label widths), producing
shifted X ranges.

### Y range must span all trials, not just trial 0
`_compute_channel_y_range()` samples up to 50 evenly-spaced trials (not only
trial 0) to compute the global min/max.  Trial 0 may be at resting potential
(−65 mV) while other trials contain action potentials (+40 mV); using only
trial 0 produces a Y range too narrow for overlay mode.

### Deferred initial reset uses generation counter
`_deferred_initial_reset(generation)` is scheduled via `QTimer.singleShot(0, ...)`
**only** for multichannel recordings and only when no view state restoration is
pending.  It checks `generation == self._display_generation` to discard stale
callbacks from previous file loads.  Without this guard, a deferred reset from
file A can fire after file B has already been loaded, overwriting B's correct
ranges.

### Downsampling defaults — preserve signal fidelity
- Always use `method="peak"` (never `"subsample"` which drops every Nth point
  and loses spikes/transients).
- `autoDownsampleThreshold` should be ≥ 5000 (pyqtgraph default).  Values
  below 5000 visibly degrade electrophysiology traces at typical zoom levels.
- `clipToView` should only be `True` when downsampling is enabled; otherwise
  it clamps data outside the current viewport and defeats zoom-out.

## numpy / scipy rules
- `np.searchsorted` only accepts `side="left"` or `side="right"` — not `"nearest"`.
  To find the nearest index use: insert with `"left"`, then compare `idx-1` vs `idx`.
- Do not use deprecated numpy APIs (e.g. `np.bool`, `np.int` — use built-ins).

## Testing rules
- Every new analysis function needs a test in `tests/core/`
- Every new GUI behaviour needs a test in `tests/gui/`
- Tests that create pyqtgraph widgets in session scope must account for the
  platform-specific drain behaviour described above
- After any edit, run: `conda run -n synaptipy python -m pytest tests/ 2>&1 | grep -c PASSED`
  and `conda run -n synaptipy flake8 src/ tests/` before declaring done
