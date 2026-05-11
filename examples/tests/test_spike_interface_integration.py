# examples/tests/test_spike_interface_integration.py
# -*- coding: utf-8 -*-
"""
Tests for the spike_interface_integration plugin.

NOTE: This test file lives in ``examples/tests/`` and is intentionally
excluded from the core Synaptipy CI test suite (``testpaths = ["tests"]``
in pyproject.toml).  Run it manually alongside the plugin:

    conda run -n synaptipy python -m pytest examples/tests/ -v

Architecture
------------
The plugin accepts a plain 1-D numpy array from Synaptipy's channel selector,
wraps it in ``spikeinterface.core.NumpyRecording``, bandpass-filters it, and
runs ``detect_peaks`` - exactly the same way as using any other analysis on a
selected channel.  No sorter binary and no file path are needed.

All SpikeInterface modules are replaced with ``unittest.mock`` objects via
``patch.dict(sys.modules, ...)`` so the tests run without spikeinterface
installed and finish in milliseconds.

Note on IMPORT_FROM bytecode
----------------------------
``import spikeinterface.core as sc`` compiles to ``IMPORT_NAME`` followed by
``IMPORT_FROM extractors``.  ``IMPORT_FROM`` calls ``getattr(si_top, 'core')``
on the parent module - NOT a sys.modules lookup.  Sub-module mocks must
therefore be wired as attributes on the parent mock AND registered in
sys.modules.  ``_si_patch()`` handles this.

Tests cover
-----------
1. Return schema (module_used, metrics keys, private _spike_times, _spike_amplitudes).
2. Correct delegation to the mocked SpikeInterface API.
3. NumpyRecording receives the correct 2-D float32 array.
4. bandpass_filter receives correct freq_min / freq_max kwargs.
5. detect_peaks receives the filtered recording and correct kwargs.
6. Graceful handling of empty data and near-zero noise.
7. Registry metadata (name, ui_params, run_button, vlines + markers plots).
"""

import copy
import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from Synaptipy.core.analysis.registry import AnalysisRegistry

# ---------------------------------------------------------------------------
# Load plugin module once at import time (lazy SI imports mean the file loads
# without spikeinterface present).
# ---------------------------------------------------------------------------
_PLUGIN_PATH = Path(__file__).resolve().parents[2] / "examples" / "plugins" / "spike_interface_integration.py"
_spec = importlib.util.spec_from_file_location("spike_interface_integration", _PLUGIN_PATH)
_plugin_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_plugin_mod)

run_spike_interface_wrapper = _plugin_mod.run_spike_interface_wrapper
detect_spikes_spikeinterface = _plugin_mod.detect_spikes_spikeinterface


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _si_patch(sc_mock, spp_mock, pd_mock):
    """Return sys.modules dict for patching SpikeInterface lazy imports.

    Sub-module mocks are wired as attributes on the parent mock so that
    ``IMPORT_FROM`` bytecode (``getattr(si_top, 'core')``) resolves to
    the correct mock rather than an auto-generated attribute.
    """
    si_top = MagicMock(name="spikeinterface_top")
    si_top.core = sc_mock
    si_top.preprocessing = spp_mock

    # spikeinterface.sortingcomponents.peak_detection is a deep sub-module
    si_top.sortingcomponents = MagicMock(name="si_sortcomp")
    si_top.sortingcomponents.peak_detection = pd_mock

    return {
        "spikeinterface": si_top,
        "spikeinterface.core": sc_mock,
        "spikeinterface.preprocessing": spp_mock,
        "spikeinterface.sortingcomponents": MagicMock(name="si_sortcomp"),
        "spikeinterface.sortingcomponents.peak_detection": pd_mock,
    }


def _make_peaks_array(sample_indices):
    """Return a structured numpy array matching detect_peaks output dtype."""
    n = len(sample_indices)
    dtype = np.dtype(
        [
            ("sample_index", np.int64),
            ("channel_index", np.int64),
            ("amplitude", np.float32),
            ("segment_index", np.int64),
        ]
    )
    arr = np.zeros(n, dtype=dtype)
    arr["sample_index"] = np.asarray(sample_indices, dtype=np.int64)
    arr["amplitude"] = -200.0
    return arr


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def isolate_registry():
    """Restore AnalysisRegistry state around each test."""
    saved_registry = dict(AnalysisRegistry._registry)
    saved_metadata = copy.deepcopy(AnalysisRegistry._metadata)
    saved_original = copy.deepcopy(AnalysisRegistry._original_metadata)
    yield
    AnalysisRegistry._registry.clear()
    AnalysisRegistry._metadata.clear()
    AnalysisRegistry._original_metadata.clear()
    AnalysisRegistry._registry.update(saved_registry)
    AnalysisRegistry._metadata.update(saved_metadata)
    AnalysisRegistry._original_metadata.update(saved_original)


@pytest.fixture
def fs():
    return 20000.0


@pytest.fixture
def synthetic_trace(fs):
    """1-second trace with 3 large negative spikes plus broadband noise."""
    rng = np.random.default_rng(0)
    n = int(fs)
    data = rng.standard_normal(n).astype(np.float64) * 20.0  # noise ~20 uV
    # Insert 3 spikes at 0.2 s, 0.5 s, 0.8 s  (amplitude ~-200 uV)
    for t_spike in (0.2, 0.5, 0.8):
        idx = int(t_spike * fs)
        data[idx] = -200.0
    return data


@pytest.fixture
def si_mocks(fs, synthetic_trace):
    """Return configured SI mocks and activate sys.modules patch."""
    sc_mock = MagicMock(name="sc")
    spp_mock = MagicMock(name="spp")
    pd_mock = MagicMock(name="pd")

    mock_recording = MagicMock(name="MockNumpyRecording")
    mock_filtered = MagicMock(name="MockFiltered")

    # Filtered trace: same length, values close to input
    filt_2d = synthetic_trace.astype(np.float32).reshape(-1, 1)
    mock_filtered.get_traces.return_value = filt_2d

    sc_mock.NumpyRecording.return_value = mock_recording
    spp_mock.bandpass_filter.return_value = mock_filtered

    # 3 spikes at samples 4000, 10000, 16000
    peaks_arr = _make_peaks_array([4000, 10000, 16000])
    pd_mock.detect_peaks.return_value = peaks_arr

    with patch.dict(sys.modules, _si_patch(sc_mock, spp_mock, pd_mock)):
        yield {
            "sc": sc_mock,
            "spp": spp_mock,
            "pd": pd_mock,
            "recording": mock_recording,
            "filtered": mock_filtered,
            "peaks": peaks_arr,
        }


# ---------------------------------------------------------------------------
# Tests: return schema
# ---------------------------------------------------------------------------


class TestReturnSchema:
    def test_module_used_is_spike_interface(self, si_mocks, synthetic_trace, fs):
        t = np.arange(len(synthetic_trace)) / fs
        result = run_spike_interface_wrapper(synthetic_trace, t, fs)
        assert result.get("module_used") == "spike_interface"

    def test_metrics_dict_present(self, si_mocks, synthetic_trace, fs):
        t = np.arange(len(synthetic_trace)) / fs
        result = run_spike_interface_wrapper(synthetic_trace, t, fs)
        assert isinstance(result.get("metrics"), dict)

    def test_metrics_has_spike_count(self, si_mocks, synthetic_trace, fs):
        t = np.arange(len(synthetic_trace)) / fs
        result = run_spike_interface_wrapper(synthetic_trace, t, fs)
        assert "Spike_Count" in result["metrics"]

    def test_metrics_has_noise_estimate(self, si_mocks, synthetic_trace, fs):
        t = np.arange(len(synthetic_trace)) / fs
        result = run_spike_interface_wrapper(synthetic_trace, t, fs)
        assert "Noise_Estimate" in result["metrics"]

    def test_metrics_has_threshold(self, si_mocks, synthetic_trace, fs):
        t = np.arange(len(synthetic_trace)) / fs
        result = run_spike_interface_wrapper(synthetic_trace, t, fs)
        assert "Threshold" in result["metrics"]

    def test_metrics_has_firing_rate(self, si_mocks, synthetic_trace, fs):
        t = np.arange(len(synthetic_trace)) / fs
        result = run_spike_interface_wrapper(synthetic_trace, t, fs)
        assert "Mean_Firing_Rate_Hz" in result["metrics"]

    def test_private_spike_times_key_present(self, si_mocks, synthetic_trace, fs):
        t = np.arange(len(synthetic_trace)) / fs
        result = run_spike_interface_wrapper(synthetic_trace, t, fs)
        assert "_spike_times" in result

    def test_spike_times_is_list(self, si_mocks, synthetic_trace, fs):
        t = np.arange(len(synthetic_trace)) / fs
        result = run_spike_interface_wrapper(synthetic_trace, t, fs)
        assert isinstance(result["_spike_times"], list)

    def test_spike_count_matches_list_length(self, si_mocks, synthetic_trace, fs):
        t = np.arange(len(synthetic_trace)) / fs
        result = run_spike_interface_wrapper(synthetic_trace, t, fs)
        assert result["metrics"]["Spike_Count"] == len(result["_spike_times"])

    def test_spike_times_are_floats_in_seconds(self, si_mocks, synthetic_trace, fs):
        t = np.arange(len(synthetic_trace)) / fs
        result = run_spike_interface_wrapper(synthetic_trace, t, fs)
        # Mocked sample_indices [4000, 10000, 16000] / 20000 Hz
        expected = [4000 / fs, 10000 / fs, 16000 / fs]
        assert result["_spike_times"] == pytest.approx(expected, abs=1e-6)

    def test_spike_count_value_equals_3(self, si_mocks, synthetic_trace, fs):
        t = np.arange(len(synthetic_trace)) / fs
        result = run_spike_interface_wrapper(synthetic_trace, t, fs)
        assert result["metrics"]["Spike_Count"] == 3

    def test_private_spike_amplitudes_key_present(self, si_mocks, synthetic_trace, fs):
        t = np.arange(len(synthetic_trace)) / fs
        result = run_spike_interface_wrapper(synthetic_trace, t, fs)
        assert "_spike_amplitudes" in result

    def test_spike_amplitudes_is_list_same_length(self, si_mocks, synthetic_trace, fs):
        t = np.arange(len(synthetic_trace)) / fs
        result = run_spike_interface_wrapper(synthetic_trace, t, fs)
        assert isinstance(result["_spike_amplitudes"], list)
        assert len(result["_spike_amplitudes"]) == len(result["_spike_times"])


# ---------------------------------------------------------------------------
# Tests: NumpyRecording construction
# ---------------------------------------------------------------------------


class TestNumpyRecording:
    def test_numpy_recording_called_once(self, si_mocks, synthetic_trace, fs):
        t = np.arange(len(synthetic_trace)) / fs
        run_spike_interface_wrapper(synthetic_trace, t, fs)
        si_mocks["sc"].NumpyRecording.assert_called_once()

    def test_numpy_recording_sampling_frequency(self, si_mocks, synthetic_trace, fs):
        t = np.arange(len(synthetic_trace)) / fs
        run_spike_interface_wrapper(synthetic_trace, t, fs)
        kwargs = si_mocks["sc"].NumpyRecording.call_args.kwargs
        assert kwargs["sampling_frequency"] == pytest.approx(fs)

    def test_numpy_recording_traces_shape(self, si_mocks, synthetic_trace, fs):
        """traces_list must contain one (N, 1) float32 array."""
        t = np.arange(len(synthetic_trace)) / fs
        run_spike_interface_wrapper(synthetic_trace, t, fs)
        kwargs = si_mocks["sc"].NumpyRecording.call_args.kwargs
        traces = kwargs["traces_list"][0]
        assert traces.shape == (len(synthetic_trace), 1)
        assert traces.dtype == np.float32

    def test_numpy_recording_data_values(self, si_mocks, synthetic_trace, fs):
        """The traces_list array must contain the same values as the input."""
        t = np.arange(len(synthetic_trace)) / fs
        run_spike_interface_wrapper(synthetic_trace, t, fs)
        kwargs = si_mocks["sc"].NumpyRecording.call_args.kwargs
        traces = kwargs["traces_list"][0].ravel()
        np.testing.assert_array_almost_equal(traces, synthetic_trace.astype(np.float32))


# ---------------------------------------------------------------------------
# Tests: bandpass_filter delegation
# ---------------------------------------------------------------------------


class TestBandpassFilter:
    def test_bandpass_filter_called_once(self, si_mocks, synthetic_trace, fs):
        t = np.arange(len(synthetic_trace)) / fs
        run_spike_interface_wrapper(synthetic_trace, t, fs)
        si_mocks["spp"].bandpass_filter.assert_called_once()

    def test_bandpass_filter_receives_numpy_recording(self, si_mocks, synthetic_trace, fs):
        t = np.arange(len(synthetic_trace)) / fs
        run_spike_interface_wrapper(synthetic_trace, t, fs)
        args = si_mocks["spp"].bandpass_filter.call_args.args
        assert args[0] is si_mocks["recording"]

    def test_bandpass_filter_default_freq_min(self, si_mocks, synthetic_trace, fs):
        t = np.arange(len(synthetic_trace)) / fs
        run_spike_interface_wrapper(synthetic_trace, t, fs)
        kw = si_mocks["spp"].bandpass_filter.call_args.kwargs
        assert kw["freq_min"] == pytest.approx(300.0)

    def test_bandpass_filter_default_freq_max(self, si_mocks, synthetic_trace, fs):
        t = np.arange(len(synthetic_trace)) / fs
        run_spike_interface_wrapper(synthetic_trace, t, fs)
        kw = si_mocks["spp"].bandpass_filter.call_args.kwargs
        assert kw["freq_max"] == pytest.approx(6000.0)

    def test_bandpass_filter_custom_freqs(self, si_mocks, synthetic_trace, fs):
        t = np.arange(len(synthetic_trace)) / fs
        run_spike_interface_wrapper(synthetic_trace, t, fs, freq_min=500.0, freq_max=3000.0)
        kw = si_mocks["spp"].bandpass_filter.call_args.kwargs
        assert kw["freq_min"] == pytest.approx(500.0)
        assert kw["freq_max"] == pytest.approx(3000.0)


# ---------------------------------------------------------------------------
# Tests: detect_peaks delegation
# ---------------------------------------------------------------------------


class TestDetectPeaks:
    def test_detect_peaks_called_once(self, si_mocks, synthetic_trace, fs):
        t = np.arange(len(synthetic_trace)) / fs
        run_spike_interface_wrapper(synthetic_trace, t, fs)
        si_mocks["pd"].detect_peaks.assert_called_once()

    def test_detect_peaks_receives_filtered_recording(self, si_mocks, synthetic_trace, fs):
        t = np.arange(len(synthetic_trace)) / fs
        run_spike_interface_wrapper(synthetic_trace, t, fs)
        args = si_mocks["pd"].detect_peaks.call_args.args
        assert args[0] is si_mocks["filtered"]

    def test_detect_peaks_default_threshold(self, si_mocks, synthetic_trace, fs):
        t = np.arange(len(synthetic_trace)) / fs
        run_spike_interface_wrapper(synthetic_trace, t, fs)
        kw = si_mocks["pd"].detect_peaks.call_args.kwargs
        assert kw["detect_threshold"] == pytest.approx(5.0)

    def test_detect_peaks_default_peak_sign_neg(self, si_mocks, synthetic_trace, fs):
        t = np.arange(len(synthetic_trace)) / fs
        run_spike_interface_wrapper(synthetic_trace, t, fs)
        kw = si_mocks["pd"].detect_peaks.call_args.kwargs
        assert kw["peak_sign"] == "neg"

    def test_detect_peaks_custom_threshold(self, si_mocks, synthetic_trace, fs):
        t = np.arange(len(synthetic_trace)) / fs
        run_spike_interface_wrapper(synthetic_trace, t, fs, threshold_mad=10.0)
        kw = si_mocks["pd"].detect_peaks.call_args.kwargs
        assert kw["detect_threshold"] == pytest.approx(10.0)

    def test_detect_peaks_by_channel_method(self, si_mocks, synthetic_trace, fs):
        t = np.arange(len(synthetic_trace)) / fs
        run_spike_interface_wrapper(synthetic_trace, t, fs)
        kw = si_mocks["pd"].detect_peaks.call_args.kwargs
        assert kw["method"] == "by_channel"


# ---------------------------------------------------------------------------
# Tests: edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_empty_data_returns_error(self, si_mocks, fs):
        result = detect_spikes_spikeinterface(np.array([]), fs, 300.0, 6000.0, 25.0, "neg")
        assert "error" in result

    def test_no_spikes_detected(self, si_mocks, synthetic_trace, fs):
        """When detect_peaks returns 0 peaks, Spike_Count should be 0."""
        si_mocks["pd"].detect_peaks.return_value = _make_peaks_array([])
        t = np.arange(len(synthetic_trace)) / fs
        result = run_spike_interface_wrapper(synthetic_trace, t, fs)
        assert result["metrics"]["Spike_Count"] == 0
        assert result["_spike_times"] == []

    def test_missing_spikeinterface_returns_error(self, synthetic_trace, fs):
        """Without spikeinterface installed the plugin must return an error dict."""
        blocker = {
            "spikeinterface": None,
            "spikeinterface.core": None,
            "spikeinterface.preprocessing": None,
            "spikeinterface.sortingcomponents": None,
            "spikeinterface.sortingcomponents.peak_detection": None,
        }
        with patch.dict(sys.modules, blocker):
            result = detect_spikes_spikeinterface(synthetic_trace, fs, 300.0, 6000.0, 25.0, "neg")
        assert "error" in result
        assert "SpikeInterface" in result["error"] or "spikeinterface" in result["error"].lower()


# ---------------------------------------------------------------------------
# Tests: registry metadata
# ---------------------------------------------------------------------------


class TestRegistryMetadata:
    def test_registered_under_correct_name(self):
        func = AnalysisRegistry.get_function("spike_interface_detection")
        assert func is not None

    def test_registered_function_is_wrapper(self):
        func = AnalysisRegistry.get_function("spike_interface_detection")
        assert func is run_spike_interface_wrapper

    def test_metadata_has_ui_params(self):
        meta = AnalysisRegistry._metadata.get("spike_interface_detection", {})
        assert "ui_params" in meta

    def test_ui_params_count_is_five(self):
        meta = AnalysisRegistry._metadata.get("spike_interface_detection", {})
        assert len(meta["ui_params"]) == 5

    def test_freq_min_param_is_float(self):
        meta = AnalysisRegistry._metadata.get("spike_interface_detection", {})
        p = next(p for p in meta["ui_params"] if p["name"] == "freq_min")
        assert p["type"] == "float"
        assert p["default"] == 300.0

    def test_freq_max_param_is_float(self):
        meta = AnalysisRegistry._metadata.get("spike_interface_detection", {})
        p = next(p for p in meta["ui_params"] if p["name"] == "freq_max")
        assert p["type"] == "float"
        assert p["default"] == 6000.0

    def test_threshold_mad_param_is_float(self):
        meta = AnalysisRegistry._metadata.get("spike_interface_detection", {})
        p = next(p for p in meta["ui_params"] if p["name"] == "threshold_mad")
        assert p["type"] == "float"
        assert p["default"] == 5.0

    def test_exclude_sweep_ms_param_is_float(self):
        meta = AnalysisRegistry._metadata.get("spike_interface_detection", {})
        p = next(p for p in meta["ui_params"] if p["name"] == "exclude_sweep_ms")
        assert p["type"] == "float"
        assert p["default"] == 5.0

    def test_peak_sign_param_is_choice(self):
        meta = AnalysisRegistry._metadata.get("spike_interface_detection", {})
        p = next(p for p in meta["ui_params"] if p["name"] == "peak_sign")
        assert p["type"] == "choice"
        assert "neg" in p["options"]
        assert p["default"] == "neg"

    def test_plots_defines_one_vlines(self):
        meta = AnalysisRegistry._metadata.get("spike_interface_detection", {})
        vlines = [p for p in meta.get("plots", []) if p.get("type") == "vlines"]
        assert len(vlines) == 1

    def test_vlines_colour_is_red(self):
        meta = AnalysisRegistry._metadata.get("spike_interface_detection", {})
        vlines = [p for p in meta["plots"] if p["type"] == "vlines"]
        assert vlines[0]["color"] == "r"

    def test_vlines_data_references_spike_times(self):
        meta = AnalysisRegistry._metadata.get("spike_interface_detection", {})
        vlines = [p for p in meta["plots"] if p["type"] == "vlines"]
        assert vlines[0]["data"] == "_spike_times"

    def test_run_button_is_true(self):
        meta = AnalysisRegistry._metadata.get("spike_interface_detection", {})
        assert meta.get("run_button") is True

    def test_plots_defines_one_markers(self):
        meta = AnalysisRegistry._metadata.get("spike_interface_detection", {})
        markers = [p for p in meta.get("plots", []) if p.get("type") == "markers"]
        assert len(markers) == 1

    def test_markers_x_references_spike_times(self):
        meta = AnalysisRegistry._metadata.get("spike_interface_detection", {})
        markers = [p for p in meta["plots"] if p["type"] == "markers"]
        assert markers[0]["x"] == "_spike_times"

    def test_markers_y_references_spike_amplitudes(self):
        meta = AnalysisRegistry._metadata.get("spike_interface_detection", {})
        markers = [p for p in meta["plots"] if p["type"] == "markers"]
        assert markers[0]["y"] == "_spike_amplitudes"
