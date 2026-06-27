# -*- coding: utf-8 -*-
"""Tests for the multifile-average workflow introduced in cross_file_utils.

Covers:
- build_averaged_recording() happy path
- build_averaged_recording() returns None when no files are loadable
- _make_mfa_label() label generation
- DataLoaderService.load_recording_direct() emits without a thread
"""

from pathlib import Path
from unittest.mock import MagicMock

import numpy as np

from synaptipy.core.analysis.cross_file_utils import (
    _make_mfa_label,
    build_averaged_recording,
)
from synaptipy.core.data_model import Channel, Recording

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_channel(value: float = -65.0, n_trials: int = 3, fs: float = 10_000.0, n: int = 500) -> Channel:
    """Return a real Channel with *n_trials* identical constant-valued trials."""
    data = np.full(n, value)
    ch = Channel(
        id="ch0",
        name="Vm",
        units="mV",
        sampling_rate=fs,
        data_trials=[data.copy() for _ in range(n_trials)],
    )
    # Attach get_data / get_relative_time_vector via normal Channel API
    return ch


_rec_counter = 0


def _make_recording(ch_value: float = -65.0) -> Recording:
    """Return a minimal Recording with one channel (unique source_file per call)."""
    global _rec_counter
    _rec_counter += 1
    rec = Recording(source_file=Path(f"dummy_{_rec_counter}.abf"))
    ch = _make_channel(value=ch_value)
    # Channel needs get_data and get_relative_time_vector working
    fs = ch.sampling_rate
    n = len(ch.data_trials[0])
    time = np.linspace(0.0, n / fs, n, endpoint=False)

    # Patch methods used by extract_per_file_trace
    ch.get_data = lambda trial_idx: ch.data_trials[trial_idx] if trial_idx < len(ch.data_trials) else None
    ch.get_relative_time_vector = lambda trial_idx: time
    rec.channels = {"ch0": ch}
    return rec


def _make_neo_adapter(recordings: list):
    """Return a mock neo_adapter that serves recordings in order per path."""
    adapter = MagicMock()
    path_map = {}
    for rec in recordings:
        path_map[rec.source_file] = rec

    def _read(path):
        return path_map.get(Path(path))

    adapter.read_recording.side_effect = _read
    return adapter


# ---------------------------------------------------------------------------
# Tests: _make_mfa_label
# ---------------------------------------------------------------------------


class TestMakeMfaLabel:
    def test_two_files(self):
        paths = [Path("rec_001.abf"), Path("rec_002.abf")]
        label = _make_mfa_label(paths)
        assert label == "multifile_average(001,002)"

    def test_five_files(self):
        paths = [Path(f"rec_{i:03d}.abf") for i in range(1, 6)]
        label = _make_mfa_label(paths)
        assert label == "multifile_average(001,002,003,004,005)"

    def test_six_files_truncated(self):
        paths = [Path(f"rec_{i:03d}.abf") for i in range(1, 7)]
        label = _make_mfa_label(paths)
        # Only first 2 and last 2 are shown
        assert label == "multifile_average(001,002,...,005,006)"

    def test_empty_list(self):
        assert _make_mfa_label([]) == "multifile_average()"

    def test_short_stem(self):
        label = _make_mfa_label([Path("ab.abf")])
        # stem shorter than 3 chars - uses full stem
        assert label == "multifile_average(ab)"


# ---------------------------------------------------------------------------
# Tests: build_averaged_recording
# ---------------------------------------------------------------------------


class TestBuildAveragedRecording:
    def test_happy_path_two_files(self):
        """Averaged recording has one trial per channel with mean of both files."""
        rec1 = _make_recording(ch_value=-60.0)
        rec2 = _make_recording(ch_value=-70.0)
        adapter = _make_neo_adapter([rec1, rec2])
        items = [
            {"path": rec1.source_file, "target_type": "Recording"},
            {"path": rec2.source_file, "target_type": "Recording"},
        ]
        result = build_averaged_recording(items, trial_indices=[0], neo_adapter=adapter)

        assert result is not None
        assert result.metadata.get("is_multifile_average") is True
        assert len(result.channels) == 1
        ch = list(result.channels.values())[0]
        assert ch.num_trials == 1
        # Grand average of -60 and -70 is -65
        np.testing.assert_allclose(ch.data_trials[0], np.full(500, -65.0), atol=1e-6)

    def test_metadata_stored(self):
        rec1 = _make_recording()
        rec2 = _make_recording()
        adapter = _make_neo_adapter([rec1, rec2])
        items = [
            {"path": rec1.source_file},
            {"path": rec2.source_file},
        ]
        result = build_averaged_recording(items, trial_indices=[0], neo_adapter=adapter, label="test_label")
        assert result.metadata["label"] == "test_label"
        # n_files_averaged is stored per-channel, not on the Recording
        ch = list(result.channels.values())[0]
        assert ch.metadata["n_files_averaged"] == 2
        assert ch.metadata["trial_indices"] == [0]

    def test_returns_none_when_all_files_fail(self):
        adapter = MagicMock()
        adapter.read_recording.return_value = None
        items = [{"path": Path("bad1.abf")}, {"path": Path("bad2.abf")}]
        result = build_averaged_recording(items, trial_indices=[0], neo_adapter=adapter)
        assert result is None

    def test_synthetic_source_file_path(self):
        rec1 = _make_recording()
        rec2 = _make_recording()
        adapter = _make_neo_adapter([rec1, rec2])
        items = [{"path": rec1.source_file}, {"path": rec2.source_file}]
        result = build_averaged_recording(items, trial_indices=[0], neo_adapter=adapter, label="myavg")
        assert str(result.source_file).startswith("__mfa__")
        assert "myavg" in str(result.source_file)

    def test_multiple_trials_averaged(self):
        """Averaging trials [0, 1] within a single file still works."""
        rec = _make_recording(ch_value=-65.0)
        # Override trial 1 to have a different value
        rec.channels["ch0"].data_trials[1] = np.full(500, -55.0)
        rec.channels["ch0"].get_data = lambda idx, ch=rec.channels["ch0"]: (
            ch.data_trials[idx] if idx < len(ch.data_trials) else None
        )
        adapter = _make_neo_adapter([rec])
        items = [{"path": rec.source_file}]
        result = build_averaged_recording(items, trial_indices=[0, 1], neo_adapter=adapter)
        # Within-file average of [-65, -55] = -60; cross-file (1 file) stays -60
        assert result is not None
        ch = list(result.channels.values())[0]
        np.testing.assert_allclose(ch.data_trials[0], np.full(500, -60.0), atol=1e-6)


# ---------------------------------------------------------------------------
# Tests: DataLoaderService.load_recording_direct
# ---------------------------------------------------------------------------


class TestLoadRecordingDirect:
    def test_emits_recording_without_thread(self):
        """load_recording_direct emits the recording synchronously."""
        from synaptipy.application.services.data_loader_service import DataLoaderService

        adapter = MagicMock()
        service = DataLoaderService(neo_adapter=adapter)

        received = []
        finished = []
        service.recording_loaded.connect(lambda r: received.append(r))
        service.load_finished.connect(lambda: finished.append(True))

        rec = _make_recording()
        service.load_recording_direct(rec)

        assert received == [rec]
        assert finished == [True]
        # No actual disk read should have occurred
        adapter.read_recording.assert_not_called()

    def test_emits_none_directly(self):
        """load_recording_direct works for None (e.g. cleared state)."""
        from synaptipy.application.services.data_loader_service import DataLoaderService

        adapter = MagicMock()
        service = DataLoaderService(neo_adapter=adapter)

        received = []
        service.recording_loaded.connect(lambda r: received.append(r))
        service.load_recording_direct(None)
        assert received == [None]
