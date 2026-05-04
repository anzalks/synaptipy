# tests/core/test_data_model_coverage.py
# -*- coding: utf-8 -*-
"""
Coverage-boosting tests for core/data_model.py.

Targets previously uncovered lines:
  206      : log.warning for invalid trial data type (non-ndarray in data_trials)
  209-210  : no valid numpy trials → return 0 in num_samples
  239      : get_consistent_samples() successful return
  324-326  : get_averaged_data() exception path
  345      : get_relative_averaged_time_vector() returns None
  363-365  : get_averaged_current_data() exception path
  412-414  : get_finite_data_bounds() exception path
  534      : Recording.max_trials when channels is empty
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from Synaptipy.core.data_model import Channel, Recording

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ch(trials=None, sampling_rate=10_000.0, units="mV"):
    return Channel(
        id="0",
        name="Ch0",
        units=units,
        sampling_rate=sampling_rate,
        data_trials=trials or [np.zeros(100)],
    )


# ---------------------------------------------------------------------------
# num_samples — lines 206, 209-210
# ---------------------------------------------------------------------------


class TestNumSamplesEdgeCases:
    def test_non_ndarray_in_trials_logs_warning(self, caplog):
        """Line 206: invalid (non-ndarray) trial in mix triggers log.warning."""
        import logging

        ch = _ch(trials=[])
        # First trial is valid (to pass the early guard at line 193), later trial is invalid
        ch.data_trials = [np.zeros(100), "not_an_array"]
        with caplog.at_level(logging.WARNING):
            ch.num_samples  # trigger the property
        # The warning at line 206 should fire for "not_an_array"
        assert any("invalid trial data type" in m.lower() for m in caplog.messages)


# ---------------------------------------------------------------------------
# get_consistent_samples — line 239
# ---------------------------------------------------------------------------


class TestGetConsistentSamples:
    def test_consistent_trials_returns_length(self):
        """Line 239: all trials same length → returns that length."""
        ch = _ch(trials=[np.ones(50), np.ones(50), np.ones(50)])
        assert ch.get_consistent_samples() == 50


# ---------------------------------------------------------------------------
# get_averaged_data — lines 324-326
# ---------------------------------------------------------------------------


class TestGetAveragedDataExceptionPath:
    def test_exception_in_averaging_returns_none(self, caplog):
        """Lines 324-326: ValueError in np.array(trials) → returns None."""
        import logging

        ch = Channel(id="0", name="Ch0", units="mV", sampling_rate=10_000.0, data_trials=[])
        # 2D arrays with same first dim (len) but different second dim → np.array fails
        ch.data_trials = [np.zeros((100, 2)), np.zeros((100, 3))]
        with caplog.at_level(logging.ERROR):
            result = ch.get_averaged_data()
        assert result is None


# ---------------------------------------------------------------------------
# get_relative_averaged_time_vector — line 345
# ---------------------------------------------------------------------------


class TestGetRelativeAveragedTimeVector:
    def test_returns_none_when_no_averaged_data(self):
        """Line 345: no averaged data → get_relative_averaged_time_vector returns None."""
        ch = Channel(id="0", name="Ch0", units="mV", sampling_rate=10_000.0, data_trials=[])
        result = ch.get_relative_averaged_time_vector()
        assert result is None

    def test_returns_none_when_no_sampling_rate(self):
        """Line 345: zero sampling_rate → get_relative_averaged_time_vector returns None."""
        ch = _ch(trials=[np.ones(50), np.ones(50)])
        ch.sampling_rate = 0.0
        result = ch.get_relative_averaged_time_vector()
        assert result is None


# ---------------------------------------------------------------------------
# get_averaged_current_data — lines 363-365
# ---------------------------------------------------------------------------


class TestGetAveragedCurrentDataExceptionPath:
    def test_exception_in_current_averaging_returns_none(self, caplog):
        """Lines 363-365: ValueError in np.array → returns None."""
        import logging

        ch = _ch()
        # 2D arrays with same first dim but different second dim → np.array fails in mean
        ch.current_data_trials = [np.zeros((50, 2)), np.zeros((50, 3))]
        with caplog.at_level(logging.ERROR):
            result = ch.get_averaged_current_data()
        assert result is None


# ---------------------------------------------------------------------------
# get_finite_data_bounds — lines 412-414
# ---------------------------------------------------------------------------


class TestGetFiniteDataBoundsExceptionPath:
    def test_all_nan_data_returns_none(self):
        """Lines 405-406: all-NaN data → all_finite_data is empty → returns None."""
        ch = _ch(trials=[np.full(50, np.nan)])
        result = ch.get_finite_data_bounds()
        assert result is None

    def test_empty_trials_returns_none(self):
        """Line 396: no data trials → returns None."""
        ch = Channel(id="0", name="Ch0", units="mV", sampling_rate=10_000.0, data_trials=[])
        result = ch.get_finite_data_bounds()
        assert result is None

    def test_structured_array_raises_exception_returns_none(self, caplog):
        """Lines 412-414: TypeError in np.isfinite on structured array → returns None."""
        import logging

        ch = _ch(trials=[])
        # Structured array: np.isfinite raises TypeError on structured arrays
        ch.data_trials = [np.array([(1.0,), (2.0,)], dtype=[("val", float)])]
        with caplog.at_level(logging.WARNING):
            result = ch.get_finite_data_bounds()
        # Must not raise; should return None
        assert result is None


# ---------------------------------------------------------------------------
# Recording.max_trials — line 534
# ---------------------------------------------------------------------------


class TestRecordingMaxTrials:
    def test_no_channels_returns_zero(self):
        """Line 534: Recording with no channels → max_trials = 0."""
        rec = Recording(source_file=Path("/fake/empty.abf"))
        # No channels added
        assert rec.max_trials == 0

    def test_with_channels_returns_correct_max(self):
        """Normal path: returns max across channels."""
        rec = Recording(source_file=Path("/fake/data.abf"))
        ch1 = Channel(id="0", name="Ch0", units="mV", sampling_rate=10_000.0, data_trials=[np.zeros(100)] * 3)
        ch2 = Channel(id="1", name="Ch1", units="mV", sampling_rate=10_000.0, data_trials=[np.zeros(100)] * 5)
        rec.channels = {"0": ch1, "1": ch2}
        assert rec.max_trials == 5
