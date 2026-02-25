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

### processEvents() before addPlot() in offscreen mode
`SynaptipyPlotCanvas.add_plot()` calls `QCoreApplication.processEvents()`
before `widget.addPlot()` when offscreen.  Do not remove this.  On Windows +
PySide6 ≥ 6.9 deferred callbacks pending from a prior `widget.clear()` fire
*inside* `PlotItem.__init__()`, dereference freed C++ pointers, and silently
kill the test worker process.

### removePostedEvents() must skip macOS
Both the global conftest drain fixture and the per-file drain in
`test_explorer_refactor.py` guard `removePostedEvents(None, 0)` with
`if sys.platform != 'darwin': return`.  On macOS this call discards pyqtgraph
internal events needed to maintain `AllViews` / geometry caches, corrupting
session-scoped widget state and causing segfaults in `widget.clear()`.

### enableMenu=False in offscreen mode
`add_plot()` passes `enableMenu=False` to `widget.addPlot()` when offscreen.
This prevents `ViewBoxMenu.__init__` (which calls `QWidgetAction`) from
crashing on Windows/macOS without a real display.

### Plot teardown order in clear_plots()
The mandatory sequence is:
1. `_unlink_all_plots()` — break axis links before teardown
2. `_close_all_plots()` — disconnect ctrl signals and call `PlotItem.close()` while scene is valid
3. `_cancel_pending_qt_events()` — discard stale events (Win/Linux only)
4. `widget.clear()` — destroy C++ children
5. `plot_items.clear()` — drop Python refs *after* C++ teardown
6. `_flush_qt_registry()` — discard events posted *by* `widget.clear()`

Dropping Python refs before `widget.clear()` causes PySide6 ≥ 6.7 to segfault
on macOS.

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
