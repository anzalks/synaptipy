# -*- coding: utf-8 -*-
"""Tests for EpochManager and Epoch."""

import numpy as np
import pytest

from Synaptipy.core.analysis.epoch_manager import Epoch, EpochManager
from Synaptipy.core.data_model import Channel

# ---------------------------------------------------------------------------
# Epoch dataclass tests
# ---------------------------------------------------------------------------


class TestEpoch:
    """Tests for the Epoch dataclass."""

    def test_epoch_duration(self):
        e = Epoch(name="Baseline", start_time=0.0, end_time=5.0)
        assert e.duration == pytest.approx(5.0)

    def test_epoch_zero_duration(self):
        e = Epoch(name="Empty", start_time=3.0, end_time=3.0)
        assert e.duration == 0.0

    def test_epoch_negative_duration_clamped(self):
        # end < start - duration should clamp to 0
        e = Epoch(name="Bad", start_time=5.0, end_time=2.0)
        assert e.duration == 0.0

    def test_epoch_contains_inside(self):
        e = Epoch(name="Stim", start_time=1.0, end_time=4.0)
        assert e.contains(1.0)
        assert e.contains(2.5)
        assert e.contains(4.0)

    def test_epoch_contains_outside(self):
        e = Epoch(name="Stim", start_time=1.0, end_time=4.0)
        assert not e.contains(0.9)
        assert not e.contains(4.1)

    def test_epoch_repr(self):
        e = Epoch(name="Washout", start_time=10.0, end_time=20.0)
        r = repr(e)
        assert "Washout" in r
        assert "10.0000" in r

    def test_epoch_metadata_field(self):
        e = Epoch(name="A", start_time=0.0, end_time=1.0, metadata={"source": "ttl"})
        assert e.metadata["source"] == "ttl"


# ---------------------------------------------------------------------------
# EpochManager tests
# ---------------------------------------------------------------------------


class TestEpochManagerManual:
    """Tests for manual epoch creation."""

    def test_add_manual_epoch(self):
        em = EpochManager()
        epoch = em.add_manual_epoch("Baseline", 0.0, 60.0)
        assert epoch.name == "Baseline"
        assert epoch.start_time == 0.0
        assert epoch.end_time == 60.0
        assert epoch.epoch_type == "manual"
        assert len(em) == 1

    def test_add_manual_epoch_with_metadata(self):
        em = EpochManager()
        epoch = em.add_manual_epoch("Drug", 30.0, 90.0, concentration="10uM")
        assert epoch.metadata["concentration"] == "10uM"

    def test_add_epoch_invalid_times_raises(self):
        em = EpochManager()
        with pytest.raises(ValueError):
            em.add_manual_epoch("Bad", 10.0, 5.0)  # end <= start

    def test_add_epoch_equal_times_raises(self):
        em = EpochManager()
        with pytest.raises(ValueError):
            em.add_manual_epoch("Bad", 5.0, 5.0)

    def test_epochs_sorted_by_start_time(self):
        em = EpochManager()
        em.add_manual_epoch("Washout", 120.0, 300.0)
        em.add_manual_epoch("Baseline", 0.0, 60.0)
        em.add_manual_epoch("Stim", 60.0, 120.0)
        names = em.epoch_names
        assert names == ["Baseline", "Stim", "Washout"]

    def test_len(self):
        em = EpochManager()
        assert len(em) == 0
        em.add_manual_epoch("A", 0.0, 1.0)
        em.add_manual_epoch("B", 1.0, 2.0)
        assert len(em) == 2

    def test_repr(self):
        em = EpochManager()
        em.add_manual_epoch("X", 0.0, 1.0)
        assert "EpochManager" in repr(em)


class TestEpochManagerQuerying:
    """Tests for query methods."""

    @pytest.fixture
    def em_with_epochs(self):
        em = EpochManager()
        em.add_manual_epoch("Baseline", 0.0, 60.0)
        em.add_manual_epoch("Stim", 60.0, 120.0)
        em.add_manual_epoch("Washout", 120.0, 300.0)
        return em

    def test_get_epoch_found(self, em_with_epochs):
        e = em_with_epochs.get_epoch("Stim")
        assert e is not None
        assert e.name == "Stim"

    def test_get_epoch_case_insensitive(self, em_with_epochs):
        e = em_with_epochs.get_epoch("BASELINE")
        assert e is not None
        assert e.name == "Baseline"

    def test_get_epoch_not_found(self, em_with_epochs):
        assert em_with_epochs.get_epoch("NonExistent") is None

    def test_epochs_at_time(self, em_with_epochs):
        # Time inside Stim only
        found = em_with_epochs.epochs_at_time(90.0)
        assert len(found) == 1
        assert found[0].name == "Stim"

    def test_epochs_at_boundary(self, em_with_epochs):
        # t=60.0 is at the boundary of Baseline (end) and Stim (start)
        found = em_with_epochs.epochs_at_time(60.0)
        names = {e.name for e in found}
        assert "Baseline" in names
        assert "Stim" in names

    def test_epochs_at_time_none(self, em_with_epochs):
        # Before all epochs
        found = em_with_epochs.epochs_at_time(-1.0)
        assert found == []


class TestEpochManagerFromTTL:
    """Tests for auto-detection from TTL signal."""

    def _make_ttl(self, fs=1000.0, duration=10.0, pulse_start=2.0, pulse_end=7.0):
        """Create a simple square-wave TTL signal."""
        n = int(duration * fs)
        time = np.linspace(0, duration, n, endpoint=False)
        ttl = np.zeros(n)
        ttl[(time >= pulse_start) & (time < pulse_end)] = 5.0
        return ttl, time

    def test_from_ttl_creates_three_epochs(self):
        ttl, time = self._make_ttl()
        em = EpochManager()
        epochs = em.from_ttl(ttl, time, pre_stim_s=0.5, post_stim_s=0.5)
        assert len(epochs) == 3
        names = [e.name for e in epochs]
        assert "Baseline" in names
        assert "Stim" in names
        assert "Washout" in names

    def test_from_ttl_epoch_types(self):
        ttl, time = self._make_ttl()
        em = EpochManager()
        epochs = em.from_ttl(ttl, time, pre_stim_s=0.5, post_stim_s=0.5)
        for e in epochs:
            assert e.epoch_type == "ttl"

    def test_from_ttl_empty_data_returns_empty(self):
        em = EpochManager()
        result = em.from_ttl(np.array([]), np.array([]))
        assert result == []
        assert len(em) == 0

    def test_from_ttl_no_pulses_above_threshold(self):
        ttl = np.ones(1000) * 0.1  # All below default threshold 2.5
        time = np.linspace(0, 1.0, 1000)
        em = EpochManager()
        result = em.from_ttl(ttl, time, ttl_threshold=2.5)
        assert result == []

    def test_from_ttl_no_pre_stim_time(self):
        """TTL starts at t=0 so no Baseline epoch is created."""
        n = 5000
        time = np.linspace(0, 5.0, n, endpoint=False)
        ttl = np.zeros(n)
        ttl[:2500] = 5.0  # Pulse from 0 to 2.5 s
        em = EpochManager()
        epochs = em.from_ttl(ttl, time, pre_stim_s=0.0, min_inter_epoch_s=0.5)
        names = [e.name for e in epochs]
        assert "Baseline" not in names

    def test_from_ttl_no_post_stim_time(self):
        """TTL ends at the very end so no Washout epoch is created."""
        n = 5000
        time = np.linspace(0, 5.0, n, endpoint=False)
        ttl = np.zeros(n)
        ttl[2000:] = 5.0  # Pulse from 2.0 s to end
        em = EpochManager()
        epochs = em.from_ttl(ttl, time, post_stim_s=0.0, min_inter_epoch_s=0.5)
        names = [e.name for e in epochs]
        assert "Washout" not in names


class TestEpochManagerGetEpochSlices:
    """Tests for get_epoch_slices."""

    @pytest.fixture
    def channel_1s(self):
        fs = 1000.0
        n = 1000
        data = np.linspace(0, 1, n)
        return Channel(id="ch0", name="Vm", units="mV", sampling_rate=fs, data_trials=[data])

    def test_slices_correct_shape(self, channel_1s):
        em = EpochManager()
        em.add_manual_epoch("First", 0.0, 0.5)
        em.add_manual_epoch("Second", 0.5, 1.0)
        slices = em.get_epoch_slices(channel_1s, trial_index=0)
        assert "First" in slices
        assert "Second" in slices
        first_data, first_time = slices["First"]
        assert len(first_data) > 0
        assert len(first_data) == len(first_time)

    def test_slices_out_of_range_epoch(self, channel_1s):
        """An epoch completely outside the data range returns empty arrays."""
        em = EpochManager()
        em.add_manual_epoch("Far", 10.0, 20.0)
        slices = em.get_epoch_slices(channel_1s, trial_index=0)
        data, time = slices["Far"]
        assert data.size == 0
        assert time.size == 0

    def test_slices_empty_channel(self):
        """Channel with no data returns empty arrays per epoch."""
        ch = Channel(id="empty", name="X", units="mV", sampling_rate=1000.0, data_trials=[])
        em = EpochManager()
        em.add_manual_epoch("A", 0.0, 1.0)
        slices = em.get_epoch_slices(ch, trial_index=0)
        assert slices["A"][0].size == 0
