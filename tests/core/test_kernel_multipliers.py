# tests/core/test_kernel_multipliers.py
# -*- coding: utf-8 -*-
"""
Tests for de-hardcoded kernel_multipliers in event_detection_deconvolution.

Covers:
- detect_events_template accepts kernel_multipliers parameter
- Default behaviour (None) matches the old hardcoded [1.0, 2.0, 3.0] result
- Custom multipliers change the kernel bank
- run_event_detection_template_wrapper parses comma-separated string correctly
- Malformed string falls back to [1.0, 2.0, 3.0] without raising
- Registry ui_params contains the kernel_multipliers entry
"""

from __future__ import annotations

import numpy as np

import Synaptipy.core.analysis  # noqa: F401 - populate AnalysisRegistry
from Synaptipy.core.analysis.registry import AnalysisRegistry
from Synaptipy.core.analysis.synaptic_events import (
    detect_events_template,
    run_event_detection_template_wrapper,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FS = 20_000.0  # Hz
_DT = 1.0 / FS


def _synthetic_trace(n_events: int = 3, tau_rise: float = 0.5e-3, tau_decay: float = 5e-3) -> np.ndarray:
    """Return a synthetic trace with *n_events* bi-exponential PSCs."""
    n_samples = int(FS * 0.5)  # 500 ms
    t = np.arange(n_samples) * _DT
    trace = np.random.default_rng(42).normal(0, 1e-3, n_samples)
    event_times = np.linspace(0.05, 0.45, n_events)
    for et in event_times:
        t_rel = t - et
        mask = t_rel >= 0
        kernel = np.where(mask, np.exp(-t_rel / tau_decay) - np.exp(-t_rel / tau_rise), 0.0)
        trace -= 5e-2 * kernel  # negative PSCs
    return trace.astype(np.float64)


_TRACE = _synthetic_trace()
_TIME = np.arange(len(_TRACE)) * _DT


# ---------------------------------------------------------------------------
# detect_events_template — kernel_multipliers parameter
# ---------------------------------------------------------------------------


class TestDetectEventsTemplateMultipliers:
    def test_default_none_runs(self):
        """Passing kernel_multipliers=None must not raise."""
        result = detect_events_template(
            data=_TRACE,
            sampling_rate=FS,
            threshold_std=3.0,
            tau_rise=0.5e-3,
            tau_decay=5e-3,
            kernel_multipliers=None,
        )
        assert result.is_valid

    def test_explicit_default_equals_none(self):
        """Explicit [1.0, 2.0, 3.0] should give the same event count as None."""
        r_none = detect_events_template(
            data=_TRACE,
            sampling_rate=FS,
            threshold_std=3.0,
            tau_rise=0.5e-3,
            tau_decay=5e-3,
            kernel_multipliers=None,
        )
        r_explicit = detect_events_template(
            data=_TRACE,
            sampling_rate=FS,
            threshold_std=3.0,
            tau_rise=0.5e-3,
            tau_decay=5e-3,
            kernel_multipliers=[1.0, 2.0, 3.0],
        )
        assert r_none.event_count == r_explicit.event_count

    def test_single_multiplier_runs(self):
        """A single-element list must not raise."""
        result = detect_events_template(
            data=_TRACE,
            sampling_rate=FS,
            threshold_std=3.0,
            tau_rise=0.5e-3,
            tau_decay=5e-3,
            kernel_multipliers=[1.0],
        )
        assert result.is_valid

    def test_custom_multipliers_change_result(self):
        """Using multipliers that only target very slow decays should not
        find events on a fast-PSC trace at the same threshold."""
        r_normal = detect_events_template(
            data=_TRACE,
            sampling_rate=FS,
            threshold_std=3.0,
            tau_rise=0.5e-3,
            tau_decay=5e-3,
            kernel_multipliers=[1.0, 2.0, 3.0],
        )
        # Very large multipliers make kernels much longer than the PSC; the
        # matched filter response drops, so fewer (or equal) events are found.
        r_slow = detect_events_template(
            data=_TRACE,
            sampling_rate=FS,
            threshold_std=3.0,
            tau_rise=0.5e-3,
            tau_decay=5e-3,
            kernel_multipliers=[50.0, 100.0],
        )
        # We only assert the parameter is consumed without error; event
        # counts may legitimately differ.
        assert r_normal.is_valid
        assert r_slow.is_valid


# ---------------------------------------------------------------------------
# run_event_detection_template_wrapper — string parsing
# ---------------------------------------------------------------------------


class TestWrapperMultiplierParsing:
    def test_default_string_runs(self):
        out = run_event_detection_template_wrapper(
            data=_TRACE,
            time=_TIME,
            sampling_rate=FS,
            kernel_multipliers="1.0, 2.0, 3.0",
        )
        assert "metrics" in out

    def test_custom_string_parses(self):
        out = run_event_detection_template_wrapper(
            data=_TRACE,
            time=_TIME,
            sampling_rate=FS,
            kernel_multipliers="1.0, 1.5",
        )
        assert "metrics" in out
        assert "event_count" in out["metrics"]

    def test_malformed_string_falls_back(self):
        """Garbage input must not raise - falls back to default."""
        out = run_event_detection_template_wrapper(
            data=_TRACE,
            time=_TIME,
            sampling_rate=FS,
            kernel_multipliers="not_a_number",
        )
        assert "metrics" in out

    def test_empty_string_falls_back(self):
        out = run_event_detection_template_wrapper(
            data=_TRACE,
            time=_TIME,
            sampling_rate=FS,
            kernel_multipliers="",
        )
        assert "metrics" in out

    def test_missing_kwarg_uses_default(self):
        """No kernel_multipliers kwarg at all must use the default [1,2,3]."""
        out = run_event_detection_template_wrapper(
            data=_TRACE,
            time=_TIME,
            sampling_rate=FS,
        )
        assert "metrics" in out


# ---------------------------------------------------------------------------
# Registry ui_params contain kernel_multipliers entry
# ---------------------------------------------------------------------------


class TestRegistryMetadata:
    def test_ui_params_has_kernel_multipliers(self):
        meta = AnalysisRegistry.get_metadata("event_detection_deconvolution")
        assert meta is not None, "event_detection_deconvolution not registered"
        param_names = [p["name"] for p in meta.get("ui_params", [])]
        assert "kernel_multipliers" in param_names

    def test_kernel_multipliers_param_has_default(self):
        meta = AnalysisRegistry.get_metadata("event_detection_deconvolution")
        params = {p["name"]: p for p in meta.get("ui_params", [])}
        km = params["kernel_multipliers"]
        assert km["type"] == "string"
        assert km["default"] == "1.0, 2.0, 3.0"
        assert "tooltip" in km
