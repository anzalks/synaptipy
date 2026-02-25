# Synaptipy — GitHub Copilot Instructions

## Language and framework
- Python 3.10–3.12, PySide6 (Qt6), pyqtgraph, NumPy, SciPy
- Tests use pytest + pytest-qt; CI runs on ubuntu/windows/macos × Python 3.10/3.11/3.12
- Linting: `flake8 src/ tests/` with `.flake8` config (max-line-length=120, max-complexity=10)

## Code style
- Follow PEP 8; max line length 120 characters
- All public functions and classes must have docstrings
- Use type hints throughout
- Keep function complexity ≤ 10 (flake8 C901)

## Analysis registry pattern
- New analysis functions are registered with `@AnalysisRegistry.register(name=..., ui_params=[...], plots=[...])`
- `ui_params` entries drive the GUI automatically; use `visible_when: {"param": "...", "value": "..."}` for conditional visibility
- Wrapper functions must return a plain `dict`; private keys (starting with `_`) are hidden from the results table

## CI / test rules — DO NOT VIOLATE

### Local macOS exit codes are misleading
`pytest_sessionfinish` calls `os._exit()` in offscreen mode; the process always
prints `Abort trap: 6` on macOS even when all tests passed.  **Never judge a
local macOS run by the shell exit code.**  Check the pytest output lines
(`N passed`, zero `FAILED`):
```bash
conda run -n synaptipy python -m pytest tests/ 2>&1 | grep -c PASSED
conda run -n synaptipy python -m pytest tests/ 2>&1 | grep "FAILED\|ERROR "
```

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
