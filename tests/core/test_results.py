# -*- coding: utf-8 -*-
"""Tests for core/results.py – result dataclasses."""

import numpy as np

from Synaptipy.core.results import (
    AnalysisResult,
    BurstResult,
    EventDetectionResult,
    RinResult,
    RmpResult,
    SpikeTrainResult,
)


class TestAnalysisResult:
    def test_default_valid(self):
        r = AnalysisResult(value=1.0, unit="mV")
        assert r.is_valid is True
        assert r.error_message is None

    def test_set_error(self):
        r = AnalysisResult(value=None, unit="mV")
        r.set_error("bad data")
        assert r.is_valid is False
        assert r.error_message == "bad data"

    def test_quality_flags_default_empty(self):
        r = AnalysisResult(value=0.0, unit="pA")
        assert r.quality_flags == []

    def test_metadata_default_empty(self):
        r = AnalysisResult(value=0.0, unit="pA")
        assert r.metadata == {}


class TestSpikeTrainResult:
    def test_repr_valid_with_spikes(self):
        times = np.array([0.1, 0.2, 0.3])
        r = SpikeTrainResult(value=3, unit="count", spike_times=times, mean_frequency=10.0)
        s = repr(r)
        assert "count=3" in s
        assert "10.00" in s

    def test_repr_valid_no_spike_times(self):
        r = SpikeTrainResult(value=0, unit="count")
        s = repr(r)
        assert "count=0" in s
        assert "N/A" in s

    def test_repr_invalid(self):
        r = SpikeTrainResult(value=None, unit="count", is_valid=False, error_message="no spikes")
        s = repr(r)
        assert "Error" in s
        assert "no spikes" in s

    def test_set_error(self):
        r = SpikeTrainResult(value=None, unit="count")
        r.set_error("failed")
        assert r.is_valid is False


class TestRinResult:
    def test_repr_valid(self):
        r = RinResult(value=100.0, unit="MOhm")
        s = repr(r)
        assert "100.00" in s
        assert "MOhm" in s

    def test_repr_invalid(self):
        r = RinResult(value=None, unit="MOhm", is_valid=False, error_message="zero current")
        s = repr(r)
        assert "Error" in s

    def test_repr_non_float_value(self):
        r = RinResult(value="unknown", unit="MOhm")
        s = repr(r)
        assert "unknown" in s

    def test_set_error(self):
        r = RinResult(value=None, unit="MOhm")
        r.set_error("failed")
        assert not r.is_valid


class TestRmpResult:
    def test_repr_valid(self):
        r = RmpResult(value=-65.3, unit="mV")
        s = repr(r)
        assert "-65.30" in s
        assert "mV" in s

    def test_repr_invalid(self):
        r = RmpResult(value=None, unit="mV", is_valid=False, error_message="no data")
        s = repr(r)
        assert "Error" in s

    def test_repr_non_float_value(self):
        r = RmpResult(value="N/A", unit="mV")
        s = repr(r)
        assert "N/A" in s

    def test_set_error(self):
        r = RmpResult(value=None, unit="mV")
        r.set_error("x")
        assert r.is_valid is False


class TestBurstResult:
    def test_repr_valid(self):
        r = BurstResult(value=5, unit="count", burst_count=5, burst_freq_hz=2.5)
        s = repr(r)
        assert "count=5" in s
        assert "2.50" in s

    def test_repr_valid_none_freq(self):
        r = BurstResult(value=0, unit="count", burst_count=0, burst_freq_hz=0.0)
        s = repr(r)
        assert "count=0" in s

    def test_repr_invalid(self):
        r = BurstResult(value=None, unit="count", is_valid=False, error_message="burst error")
        s = repr(r)
        assert "Error" in s

    def test_set_error(self):
        r = BurstResult(value=None, unit="count")
        r.set_error("fail")
        assert r.is_valid is False


class TestEventDetectionResult:
    def test_repr_valid(self):
        r = EventDetectionResult(value=10, unit="count", event_count=10, frequency_hz=5.0)
        s = repr(r)
        assert "count=10" in s
        assert "5.00" in s

    def test_repr_valid_none_freq(self):
        r = EventDetectionResult(value=0, unit="count", event_count=0, frequency_hz=None)
        s = repr(r)
        assert "N/A" in s

    def test_repr_invalid(self):
        r = EventDetectionResult(value=None, unit="count", is_valid=False, error_message="detection failed")
        s = repr(r)
        assert "Error" in s

    def test_set_error(self):
        r = EventDetectionResult(value=None, unit="count")
        r.set_error("fail")
        assert r.is_valid is False

    def test_summary_stats_default_empty(self):
        r = EventDetectionResult(value=0, unit="count")
        assert r.summary_stats == {}

    def test_n_artifacts_rejected_default(self):
        r = EventDetectionResult(value=0, unit="count")
        assert r.n_artifacts_rejected == 0
