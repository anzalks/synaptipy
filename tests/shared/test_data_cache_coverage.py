# tests/shared/test_data_cache_coverage.py
# -*- coding: utf-8 -*-
"""
Coverage-boosting tests for shared/data_cache.py.

Targets the previously uncovered lines:
  51, 55   : singleton double-checked-locking path
  90       : path normalisation in get() (str input)
  121      : path normalisation in put() (str input)
  146      : cache is_full()
  179      : _active_trace cleared in clear()
  260      : _cleanup_recording: recording.close() invoked
  262      : _cleanup_recording: channel.data_trials.clear()
  265-266  : _cleanup_recording: channel.current_data_trials.clear()
  274      : _cleanup_recording: recording.neo_block = None
  278-279  : _cleanup_recording: exception during cleanup is swallowed
  __len__, __contains__, __repr__
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import numpy as np

from Synaptipy.core.data_model import Channel, Recording
from Synaptipy.shared.data_cache import DataCache

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fresh_cache(max_size: int = 10) -> DataCache:
    """Return a fresh DataCache (resets the singleton)."""
    DataCache.reset_instance()
    return DataCache(max_size=max_size)


def _make_recording(path: Path = Path("test.abf")) -> Recording:
    rec = Recording(source_file=path)
    ch = Channel(id="0", name="Ch0", units="mV", sampling_rate=10_000.0, data_trials=[np.zeros(100)])
    rec.channels["0"] = ch
    return rec


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestDataCacheCoverage:
    def setup_method(self):
        self.cache = _fresh_cache()

    def teardown_method(self):
        DataCache.reset_instance()

    # -- Singleton paths ------------------------------------------------

    def test_get_instance_creates_if_none(self):
        """Lines 51, 55: get_instance() calls __init__ when _instance is None."""
        DataCache.reset_instance()
        cache = DataCache.get_instance()
        assert isinstance(cache, DataCache)

    def test_second_direct_constructor_call_hits_initialized_guard(self):
        """Line 51: calling DataCache() directly when already initialized hits the early return."""
        # After setup_method, singleton is fresh. Calling it again without reset
        # should hit the 'if self._initialized: return' branch.
        second_call = DataCache()  # singleton already initialised → hits line 51
        assert second_call is self.cache

    def test_second_get_instance_returns_same(self):
        inst1 = DataCache.get_instance()
        inst2 = DataCache.get_instance()
        assert inst1 is inst2

    # -- get() path normalisation ---------------------------------------

    def test_get_str_path_is_normalised(self):
        """Line 90: str paths must be coerced to Path in get()."""
        path = Path("normalise_test.abf")
        rec = _make_recording(path)
        self.cache.put(path, rec)
        result = self.cache.get(str(path))  # Pass as string
        assert result is rec

    # -- put() path normalisation ---------------------------------------

    def test_put_str_path_is_normalised(self):
        """Line 121: str paths must be coerced to Path in put()."""
        path_str = "str_path_cache.abf"
        rec = _make_recording(Path(path_str))
        self.cache.put(path_str, rec)  # Pass as string
        assert self.cache.contains(Path(path_str))

    # -- is_full --------------------------------------------------------

    def test_is_full_when_at_capacity(self):
        """Line 146: is_full() returns True when len == max_size."""
        DataCache.reset_instance()
        cache = DataCache(max_size=2)
        cache.put(Path("a.abf"), _make_recording(Path("a.abf")))
        cache.put(Path("b.abf"), _make_recording(Path("b.abf")))
        assert cache.is_full() is True

    def test_is_full_below_capacity(self):
        self.cache.put(Path("a.abf"), _make_recording(Path("a.abf")))
        assert self.cache.is_full() is False

    # -- clear() sets _active_trace to None ----------------------------

    def test_clear_resets_active_trace(self):
        """Line 179: clear() must also clear the active trace."""
        self.cache.set_active_trace(np.zeros(100), 10_000.0, {"ch": "0"})
        assert self.cache.get_active_trace() is not None
        self.cache.clear()
        assert self.cache.get_active_trace() is None

    # -- put() path normalisation with str input covers line 121 -------

    def test_put_accepts_string_path(self):
        """Line 121: put() normalises str to Path."""
        rec = _make_recording(Path("str_put.abf"))
        self.cache.put("str_put.abf", rec)  # str → Path conversion (line 111-112)
        assert self.cache.contains(Path("str_put.abf"))

    def test_put_same_path_twice_replaces_entry(self):
        """Line 121 (del self._cache[path]): re-putting the same path evicts the old entry."""
        p = Path("duplicate.abf")
        rec1 = _make_recording(p)
        rec2 = _make_recording(p)
        self.cache.put(p, rec1)
        self.cache.put(p, rec2)  # triggers del self._cache[path] on line 121
        assert self.cache.get(p) is rec2
        assert self.cache.size() == 1

    def test_remove_accepts_string_path(self):
        """Line 146: remove() normalises str to Path."""
        p = Path("remove_str.abf")
        self.cache.put(p, _make_recording(p))
        removed = self.cache.remove("remove_str.abf")  # str → Path (line 146)
        assert removed is True
        assert not self.cache.contains(p)

    def test_contains_accepts_string_path(self):
        """Line 179: contains() normalises str to Path."""
        p = Path("contains_str.abf")
        self.cache.put(p, _make_recording(p))
        assert self.cache.contains("contains_str.abf")  # str → Path (line 179)

    # -- _cleanup_recording: close() -----------------------------------

    def test_cleanup_recording_calls_close(self):
        """Line 260: if recording has close(), it is called."""
        rec = _make_recording()
        rec.close = MagicMock()

        self.cache._cleanup_recording(rec)
        rec.close.assert_called_once()

    # -- _cleanup_recording: channel.data_trials.clear() ---------------

    def test_cleanup_recording_clears_data_trials(self):
        """Line 262: channel.data_trials.clear() is called."""
        rec = _make_recording()
        ch = rec.channels["0"]
        ch.data_trials = [np.zeros(100), np.zeros(100)]

        self.cache._cleanup_recording(rec)
        assert ch.data_trials == []

    # -- _cleanup_recording: current_data_trials -----------------------

    def test_cleanup_recording_clears_current_data_trials(self):
        """Lines 265-266: current_data_trials.clear() when attribute present."""
        rec = _make_recording()
        ch = rec.channels["0"]
        ch.current_data_trials = [np.zeros(50)]

        self.cache._cleanup_recording(rec)
        assert ch.current_data_trials == []

    # -- _cleanup_recording: neo_block / neo_reader --------------------

    def test_cleanup_recording_clears_neo_block(self):
        """Line 274: neo_block is set to None."""
        rec = _make_recording()
        rec.neo_block = object()
        rec.neo_reader = object()

        self.cache._cleanup_recording(rec)
        assert rec.neo_block is None
        assert rec.neo_reader is None

    # -- _cleanup_recording: exception is swallowed --------------------

    def test_cleanup_recording_swallows_exception(self):
        """Lines 278-279: exception during cleanup must be caught, not raised."""
        rec = _make_recording()
        # Monkey-patch close to raise
        rec.close = MagicMock(side_effect=RuntimeError("Broken close"))

        # Must not raise
        self.cache._cleanup_recording(rec)

    # -- Magic methods --------------------------------------------------

    def test_len_returns_cache_size(self):
        """__len__."""
        self.cache.put(Path("a.abf"), _make_recording(Path("a.abf")))
        assert len(self.cache) == 1

    def test_contains_operator(self):
        """__contains__."""
        p = Path("check.abf")
        self.cache.put(p, _make_recording(p))
        assert p in self.cache
        assert Path("missing.abf") not in self.cache

    def test_repr_contains_size(self):
        """__repr__."""
        r = repr(self.cache)
        assert "DataCache" in r

    # -- set/get/clear active trace ------------------------------------

    def test_set_and_get_active_trace(self):
        data = np.arange(100, dtype=float)
        self.cache.set_active_trace(data, 10_000.0, {"ch": "0"})
        result = self.cache.get_active_trace()
        assert result is not None
        np.testing.assert_array_equal(result[0], data)
        assert result[1] == 10_000.0
        assert result[2] == {"ch": "0"}

    def test_set_active_trace_defaults_metadata_to_empty_dict(self):
        data = np.zeros(50)
        self.cache.set_active_trace(data, 5_000.0)
        result = self.cache.get_active_trace()
        assert result[2] == {}

    def test_clear_active_trace(self):
        self.cache.set_active_trace(np.zeros(10), 1_000.0)
        self.cache.clear_active_trace()
        assert self.cache.get_active_trace() is None
