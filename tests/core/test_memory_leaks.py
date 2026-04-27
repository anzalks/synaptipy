# -*- coding: utf-8 -*-
"""Memory-leak regression tests for Synaptipy's BatchAnalysisEngine.

These tests verify that repeated batch runs on a tiny in-memory dataset do
not cause runaway heap growth.  The test uses the stdlib ``tracemalloc``
module so no extra test dependencies (e.g. pytest-memray) are required.

Design rationale
----------------
* We run the engine **50 times** with a 2-trial, 200-sample channel.
* Each run exercises the full ``run_batch()`` path including the per-channel
  cleanup added in Phase 5 Task 1.
* We measure the *peak allocated* bytes during runs 5-10 and 45-50 (skipping
  the first few to let Python's allocator settle).
* The test passes if the late-window peak is not more than **50 %** larger
  than the early-window peak — a 50 % headroom is deliberately generous to
  accommodate normal Python heap fragmentation while still catching
  multi-megabyte cumulative leaks that would cause OOM on real 100-file
  batches.

No ``pytest-memray`` is required; the stdlib ``tracemalloc`` module is always
available.  A comment at the bottom explains how to add memray if desired.
"""

import gc
import tracemalloc
from pathlib import Path

import numpy as np

import Synaptipy.core.analysis  # noqa: F401 -- populate AnalysisRegistry
from Synaptipy.core.analysis.batch_engine import BatchAnalysisEngine
from Synaptipy.core.analysis.registry import AnalysisRegistry
from Synaptipy.core.data_model import Channel, Recording

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FS = 10_000.0  # Hz
_N_SAMPLES = 200
_N_TRIALS = 2
_N_RUNS = 50
_EARLY_WINDOW = range(5, 11)  # runs 5-10 inclusive
_LATE_WINDOW = range(45, 51)  # runs 45-50 inclusive
_LEAK_THRESHOLD = 1.50  # late peak must be < 1.5x early peak


def _make_recording() -> Recording:
    """Return a minimal single-channel two-trial Recording."""
    trials = [np.zeros(_N_SAMPLES) for _ in range(_N_TRIALS)]
    channel = Channel(id="0", name="Vm", units="mV", sampling_rate=_FS, data_trials=trials)
    rec = Recording(source_file=Path("mem_test.abf"))
    rec.channels["0"] = channel
    return rec


def _rmp_pipeline() -> list:
    """Minimal pipeline: one analysis, average scope."""
    return [{"analysis": "rmp_analysis", "scope": "all_trials", "params": {}}]


class _RegistryGuard:
    """Save/restore AnalysisRegistry so leak-test pipelines don't pollute it."""

    def __enter__(self):
        self._r = dict(AnalysisRegistry._registry)
        self._m = dict(AnalysisRegistry._metadata)
        return self

    def __exit__(self, *_):
        AnalysisRegistry._registry.clear()
        AnalysisRegistry._metadata.clear()
        AnalysisRegistry._registry.update(self._r)
        AnalysisRegistry._metadata.update(self._m)


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------


def test_batch_engine_no_runaway_memory_leak():
    """BatchAnalysisEngine does not leak memory across 50 repeated runs.

    Passes if the peak heap usage in runs 45-50 is less than 1.5x the peak
    heap usage in runs 5-10.  This allows normal Python allocator growth while
    catching multi-megabyte cumulative leaks.
    """
    pipeline = _rmp_pipeline()

    # Ensure rmp_analysis is available (it is a built-in, but guard anyway)
    if "rmp_analysis" not in AnalysisRegistry._registry:
        import pytest

        pytest.skip("rmp_analysis not registered - skipping memory leak test")

    engine = BatchAnalysisEngine(max_workers=1)

    early_peaks: list = []
    late_peaks: list = []

    gc.collect()
    tracemalloc.start()

    try:
        for run_idx in range(_N_RUNS):
            rec = _make_recording()

            # snapshot before
            tracemalloc.clear_traces()
            gc.collect()

            engine.run_batch([rec], pipeline)

            # snapshot after
            gc.collect()
            _, peak = tracemalloc.get_traced_memory()

            if run_idx in _EARLY_WINDOW:
                early_peaks.append(peak)
            if run_idx in _LATE_WINDOW:
                late_peaks.append(peak)
    finally:
        tracemalloc.stop()

    assert early_peaks, "Early window never sampled — logic error in test"
    assert late_peaks, "Late window never sampled — logic error in test"

    avg_early = sum(early_peaks) / len(early_peaks)
    avg_late = sum(late_peaks) / len(late_peaks)

    # Report for debugging when the test fails
    early_mb = avg_early / 1024 / 1024
    late_mb = avg_late / 1024 / 1024
    ratio = avg_late / avg_early if avg_early > 0 else float("inf")

    assert ratio < _LEAK_THRESHOLD, (
        f"BatchAnalysisEngine memory leak detected: "
        f"early avg peak = {early_mb:.2f} MB, "
        f"late avg peak = {late_mb:.2f} MB, "
        f"ratio = {ratio:.2f} (threshold {_LEAK_THRESHOLD:.2f}). "
        "The engine is not releasing per-channel data between runs."
    )


# ---------------------------------------------------------------------------
# Note on pytest-memray
# ---------------------------------------------------------------------------
# To get richer memory profiling in CI, add `pytest-memray` to requirements:
#   pip install pytest-memray
# Then annotate the test:
#   @pytest.mark.limit_memory("50 MB")
#   def test_batch_engine_no_runaway_memory_leak(): ...
# and run pytest with: pytest --memray tests/core/test_memory_leaks.py
# The @limit_memory decorator replaces the manual tracemalloc check above.
# ---------------------------------------------------------------------------
