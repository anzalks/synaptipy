# tests/application/test_data_loader_coverage.py
# -*- coding: utf-8 -*-
"""
Coverage-boosting tests for application/data_loader.py.

Targets the previously uncovered lines:
  70       : file does not exist → data_error emitted
  83-84    : path is not a file → data_error emitted
  113      : cache hit → data_ready emitted immediately
  116-119  : neo_adapter returns wrong type → data_error emitted
  122-125  : recording has no channels → data_error emitted
  132-135  : store-to-cache + data_ready emit path
  148-151  : SynaptipyError handler
  154-157  : generic Exception handler
  171-181  : cleanup() clears cache
  191-195  : _should_lazy_load OSError fallback
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from Synaptipy.application.data_loader import _LARGE_FILE_THRESHOLD_BYTES, DataLoader
from Synaptipy.shared.error_handling import SynaptipyError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_recording(n_channels: int = 2, source_file: Path = Path("/fake/test.abf")):
    """Return a minimal synthetic Recording with the requested channel count."""
    from Synaptipy.core.data_model import Channel, Recording

    rec = Recording(source_file=source_file)
    rec.sampling_rate = 10_000.0
    for i in range(n_channels):
        ch = Channel(
            id=str(i),
            name=f"Ch{i}",
            units="mV",
            sampling_rate=10_000.0,
            data_trials=[],
        )
        rec.channels[ch.id] = ch
    return rec


# ---------------------------------------------------------------------------
# _should_lazy_load
# ---------------------------------------------------------------------------


class TestShouldLazyLoad:
    def test_always_lazy_when_flag_true(self, tmp_path):
        small = tmp_path / "small.bin"
        small.write_bytes(b"\x00" * 1024)
        assert DataLoader._should_lazy_load(small, lazy_load=True) is True

    def test_not_lazy_for_small_file(self, tmp_path):
        small = tmp_path / "small.bin"
        small.write_bytes(b"\x00" * 1024)
        assert DataLoader._should_lazy_load(small, lazy_load=False) is False

    def test_lazy_promoted_for_large_file(self, tmp_path):
        large = tmp_path / "large.bin"
        large.write_bytes(b"\x00" * _LARGE_FILE_THRESHOLD_BYTES)
        assert DataLoader._should_lazy_load(large, lazy_load=False) is True

    def test_oserror_returns_false(self, tmp_path):
        """Lines 191-195: OSError when stat()-ing the file falls back to False."""
        # Provide a path whose stat() raises OSError
        missing = tmp_path / "does_not_exist.bin"
        # File does not exist → stat() raises OSError; function should return False
        result = DataLoader._should_lazy_load(missing, lazy_load=False)
        assert result is False


# ---------------------------------------------------------------------------
# load_file error paths
# ---------------------------------------------------------------------------


class TestLoadFileErrorPaths:
    """Test every error branch in DataLoader.load_file."""

    def setup_method(self):
        self.loader = DataLoader()
        # Collect emitted signals
        self.errors = []
        self.ready = []
        self.progress = []
        self.loader.data_error.connect(self.errors.append)
        self.loader.data_ready.connect(self.ready.append)
        self.loader.loading_progress.connect(self.progress.append)

    def test_file_not_found_emits_error(self, tmp_path):
        """Line 70: non-existent file → data_error emitted."""
        missing = tmp_path / "missing.abf"
        self.loader.load_file(missing)
        assert len(self.errors) == 1
        assert "not found" in self.errors[0].lower() or "File not found" in self.errors[0]
        assert not self.ready

    def test_path_is_directory_emits_error(self, tmp_path):
        """Lines 83-84: path is a directory (not a regular file) → data_error."""
        # tmp_path IS a directory
        self.loader.load_file(tmp_path)
        assert len(self.errors) == 1
        assert "not a file" in self.errors[0].lower() or "not a file" in self.errors[0]
        assert not self.ready

    def test_cache_hit_emits_data_ready_immediately(self, tmp_path):
        """Line 113: if the file is in the cache, data_ready fires without neo."""
        real_file = tmp_path / "cached.abf"
        real_file.write_bytes(b"\x00" * 512)

        rec = _make_recording(source_file=real_file)
        self.loader.cache.put(real_file, rec)

        with patch.object(self.loader.neo_adapter, "read_recording") as mock_read:
            self.loader.load_file(real_file)
            mock_read.assert_not_called()

        assert len(self.ready) == 1
        assert self.ready[0] is rec
        assert not self.errors

    def test_neo_returns_wrong_type_emits_error(self, tmp_path):
        """Lines 116-119: NeoAdapter returns non-Recording → data_error."""
        real_file = tmp_path / "bad.abf"
        real_file.write_bytes(b"\x00" * 512)

        with patch.object(self.loader.neo_adapter, "read_recording", return_value="not a recording"):
            self.loader.load_file(real_file)

        assert len(self.errors) == 1
        assert "invalid data type" in self.errors[0].lower()
        assert not self.ready

    def test_recording_no_channels_emits_error(self, tmp_path):
        """Lines 122-125: recording has zero channels → data_error."""
        real_file = tmp_path / "nochans.abf"
        real_file.write_bytes(b"\x00" * 512)

        rec = _make_recording(n_channels=0, source_file=real_file)
        with patch.object(self.loader.neo_adapter, "read_recording", return_value=rec):
            self.loader.load_file(real_file)

        assert len(self.errors) == 1
        assert "no channels" in self.errors[0].lower()
        assert not self.ready

    def test_successful_load_caches_and_emits(self, tmp_path):
        """Lines 132-135: successful load stores result in cache and emits data_ready."""
        real_file = tmp_path / "good.abf"
        real_file.write_bytes(b"\x00" * 512)

        rec = _make_recording(n_channels=2, source_file=real_file)
        with patch.object(self.loader.neo_adapter, "read_recording", return_value=rec):
            self.loader.load_file(real_file)

        assert len(self.ready) == 1
        assert self.ready[0] is rec
        assert not self.errors
        # Verify it was cached
        assert self.loader.cache.get(real_file) is rec

    def test_synaptipy_error_emits_error(self, tmp_path):
        """Lines 148-151: SynaptipyError propagates as data_error signal."""
        real_file = tmp_path / "synerr.abf"
        real_file.write_bytes(b"\x00" * 512)

        with patch.object(
            self.loader.neo_adapter,
            "read_recording",
            side_effect=SynaptipyError("Synthetic SynaptipyError"),
        ):
            self.loader.load_file(real_file)

        assert len(self.errors) == 1
        assert "synaptipy error" in self.errors[0].lower()
        assert not self.ready

    def test_generic_exception_emits_error(self, tmp_path):
        """Lines 154-157: unexpected Exception propagates as data_error signal."""
        real_file = tmp_path / "generr.abf"
        real_file.write_bytes(b"\x00" * 512)

        with patch.object(
            self.loader.neo_adapter,
            "read_recording",
            side_effect=RuntimeError("Unexpected boom"),
        ):
            self.loader.load_file(real_file)

        assert len(self.errors) == 1
        assert "unexpected error" in self.errors[0].lower()
        assert not self.ready

    def test_string_path_is_coerced_to_path(self, tmp_path):
        """File path passed as str must be accepted without error."""
        real_file = tmp_path / "str_path.abf"
        real_file.write_bytes(b"\x00" * 512)

        rec = _make_recording(source_file=real_file)
        with patch.object(self.loader.neo_adapter, "read_recording", return_value=rec):
            # Pass as string instead of Path
            self.loader.load_file(str(real_file))

        assert len(self.ready) == 1
        assert not self.errors


# ---------------------------------------------------------------------------
# cleanup()
# ---------------------------------------------------------------------------


class TestDataLoaderCleanup:
    """Lines 171-181: cleanup() must clear the data cache."""

    def test_cleanup_clears_cache(self, tmp_path):
        loader = DataLoader()
        real_file = tmp_path / "toclean.abf"
        real_file.write_bytes(b"\x00" * 512)

        rec = _make_recording(source_file=real_file)
        loader.cache.put(real_file, rec)
        assert loader.cache.get(real_file) is rec

        loader.cleanup()
        # After cleanup the cache should be empty (get returns None)
        assert loader.cache.get(real_file) is None
