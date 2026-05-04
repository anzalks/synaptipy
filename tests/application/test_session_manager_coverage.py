# tests/application/test_session_manager_coverage.py
# -*- coding: utf-8 -*-
"""
Coverage-boosting tests for application/session_manager.py.

Targets previously uncovered lines by exercising:
  - LJP property getter/setter (lines 62, 67)
  - current_recording setter (same value → no emit) (lines 88-90)
  - selected_analysis_items setter (lines 94, 97-100)
  - update_global_setting same-value guard (line 104)
  - set_global_settings same-value guard (lines 105-106)
  - set_file_context + properties (lines 117, 121)
  - preprocessing_settings: None clear, slot format, single step baseline,
    single step filter, unknown type early return
  - clear_preprocessing_slot: baseline, filter, empty guard
  - get_preprocessing_steps: with and without baseline/filters
  - performance_settings setter with invalid type (line 217)
  - emit_preferences_changed (line 241)
  - save_session / load_session / apply_session edge cases (lines 297-358)
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from Synaptipy.application.session_manager import SessionManager

# ---------------------------------------------------------------------------
# Reset singleton state between tests so they are independent
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _fresh_session_manager():
    """Reset singleton mutable state before every test in this module."""
    sm = SessionManager()
    sm._current_recording = None
    sm._selected_analysis_items = []
    sm._global_settings = {"liquid_junction_potential_mv": 0.0}
    sm._preprocessing_settings = None
    sm._file_list = []
    sm._current_file_index = -1
    sm._performance_settings = {"max_cpu_cores": 1, "max_ram_allocation_gb": 4.0}
    yield


# ---------------------------------------------------------------------------
# LJP property
# ---------------------------------------------------------------------------


class TestLjpProperty:
    def test_default_is_zero(self):
        assert SessionManager().liquid_junction_potential_mv == pytest.approx(0.0)

    def test_setter_updates_value(self):
        sm = SessionManager()
        sm.liquid_junction_potential_mv = 12.5
        assert sm.liquid_junction_potential_mv == pytest.approx(12.5)

    def test_setter_emits_signal(self, qtbot):
        sm = SessionManager()
        with qtbot.waitSignal(sm.global_settings_changed, timeout=500):
            sm.liquid_junction_potential_mv = 5.0


# ---------------------------------------------------------------------------
# current_recording setter
# ---------------------------------------------------------------------------


class TestCurrentRecordingSetter:
    def test_same_value_does_not_emit(self, qtbot):
        """Lines 88-90: if recording does not change, no signal is emitted."""
        from Synaptipy.core.data_model import Recording

        sm = SessionManager()
        rec = Recording(source_file=Path("/fake/test.abf"))
        sm._current_recording = rec  # Set directly without triggering signal

        received = []
        sm.current_recording_changed.connect(received.append)
        sm.current_recording = rec  # Should NOT emit — same object
        assert len(received) == 0

    def test_none_recording_emits(self, qtbot):
        sm = SessionManager()
        received = []
        sm.current_recording_changed.connect(received.append)
        sm.current_recording = None
        # None → None is still "different" only if prev was not None; but
        # both start as None so nothing should fire
        assert len(received) == 0  # _current_recording starts None; same → no emit


# ---------------------------------------------------------------------------
# selected_analysis_items setter
# ---------------------------------------------------------------------------


class TestSelectedAnalysisItems:
    def test_setter_emits_signal(self, qtbot):
        sm = SessionManager()
        received = []
        sm.selected_analysis_items_changed.connect(received.append)
        # Use a structurally-valid item so any connected GUI slots don't raise
        items = [{"id": "x", "path": Path("/fake/test.abf"), "target_type": "Recording"}]
        sm.selected_analysis_items = items
        assert len(received) == 1
        assert received[0] == items

    def test_getter_returns_set_value(self):
        sm = SessionManager()
        items = [
            {"id": "a", "path": Path("/fake/a.abf"), "target_type": "Recording"},
            {"id": "b", "path": Path("/fake/b.abf"), "target_type": "Recording"},
        ]
        sm.selected_analysis_items = items
        assert sm.selected_analysis_items == items


# ---------------------------------------------------------------------------
# update_global_setting / set_global_settings
# ---------------------------------------------------------------------------


class TestGlobalSettings:
    def test_update_same_value_does_not_emit(self, qtbot):
        """Line 104: guard against redundant emissions."""
        sm = SessionManager()
        sm._global_settings["liquid_junction_potential_mv"] = 7.0
        received = []
        sm.global_settings_changed.connect(received.append)
        sm.update_global_setting("liquid_junction_potential_mv", 7.0)
        assert len(received) == 0

    def test_set_global_settings_same_dict_no_emit(self, qtbot):
        """Lines 105-106: if dict is identical, no signal is emitted."""
        sm = SessionManager()
        current = dict(sm._global_settings)
        received = []
        sm.global_settings_changed.connect(received.append)
        sm.set_global_settings(current)
        assert len(received) == 0


# ---------------------------------------------------------------------------
# set_file_context + properties
# ---------------------------------------------------------------------------


class TestFileContext:
    def test_set_file_context_emits_signal(self, qtbot):
        sm = SessionManager()
        paths = [Path("/a.abf"), Path("/b.abf")]
        received = []
        sm.file_context_changed.connect(lambda fl, idx: received.append((fl, idx)))
        sm.set_file_context(paths, 1)
        assert len(received) == 1
        assert received[0] == (paths, 1)

    def test_file_list_property(self):
        sm = SessionManager()
        paths = [Path("/c.abf")]
        sm.set_file_context(paths, 0)
        assert sm.file_list == paths

    def test_current_file_index_property(self):
        sm = SessionManager()
        sm.set_file_context([], 3)
        assert sm.current_file_index == 3


# ---------------------------------------------------------------------------
# preprocessing_settings
# ---------------------------------------------------------------------------


class TestPreprocessingSettings:
    def test_set_none_clears(self, qtbot):
        sm = SessionManager()
        sm._preprocessing_settings = {"baseline": {"type": "baseline"}}
        received = []
        sm.preprocessing_settings_changed.connect(received.append)
        sm.preprocessing_settings = None
        assert sm._preprocessing_settings is None
        assert received == [None]

    def test_set_slot_format(self):
        sm = SessionManager()
        slot_cfg = {"baseline": {"type": "baseline", "method": "mean"}}
        sm.preprocessing_settings = slot_cfg
        assert sm._preprocessing_settings == slot_cfg

    def test_set_single_step_baseline(self):
        sm = SessionManager()
        step = {"type": "baseline", "method": "mean", "start": 0, "end": 0.1}
        sm.preprocessing_settings = step
        assert "baseline" in sm._preprocessing_settings
        assert sm._preprocessing_settings["baseline"]["method"] == "mean"

    def test_set_single_step_filter(self):
        sm = SessionManager()
        step = {"type": "filter", "method": "lowpass", "cutoff": 500}
        sm.preprocessing_settings = step
        assert "filters" in sm._preprocessing_settings
        assert "lowpass" in sm._preprocessing_settings["filters"]

    def test_set_single_step_filter_merges_existing(self):
        sm = SessionManager()
        sm.preprocessing_settings = {"type": "filter", "method": "lowpass", "cutoff": 500}
        sm.preprocessing_settings = {"type": "filter", "method": "highpass", "cutoff": 100}
        assert "lowpass" in sm._preprocessing_settings["filters"]
        assert "highpass" in sm._preprocessing_settings["filters"]

    def test_unknown_step_type_returns_without_emit(self, qtbot):
        """Lines 199-208: unknown step type logs warning and returns early."""
        sm = SessionManager()
        received = []
        sm.preprocessing_settings_changed.connect(received.append)
        sm.preprocessing_settings = {"type": "UNKNOWN_STEP"}
        assert len(received) == 0

    def test_filter_method_defaults_to_unknown_when_missing(self):
        sm = SessionManager()
        sm.preprocessing_settings = {"type": "filter"}  # no 'method' key
        assert "unknown" in sm._preprocessing_settings["filters"]


# ---------------------------------------------------------------------------
# clear_preprocessing_slot
# ---------------------------------------------------------------------------


class TestClearPreprocessingSlot:
    def test_clear_noop_when_no_settings(self):
        sm = SessionManager()
        sm._preprocessing_settings = None
        # Should not raise
        sm.clear_preprocessing_slot("baseline")

    def test_clear_baseline(self):
        sm = SessionManager()
        sm._preprocessing_settings = {"baseline": {"type": "baseline"}}
        sm.clear_preprocessing_slot("baseline")
        assert sm._preprocessing_settings is None

    def test_clear_filter(self):
        sm = SessionManager()
        sm._preprocessing_settings = {"filters": {"lowpass": {"cutoff": 500}}}
        sm.clear_preprocessing_slot("filter", filter_method="lowpass")
        assert sm._preprocessing_settings is None

    def test_clear_filter_keeps_other_filters(self):
        sm = SessionManager()
        sm._preprocessing_settings = {"filters": {"lowpass": {"cutoff": 500}, "highpass": {"cutoff": 100}}}
        sm.clear_preprocessing_slot("filter", filter_method="lowpass")
        assert "highpass" in sm._preprocessing_settings["filters"]
        assert "lowpass" not in sm._preprocessing_settings["filters"]


# ---------------------------------------------------------------------------
# get_preprocessing_steps
# ---------------------------------------------------------------------------


class TestGetPreprocessingSteps:
    def test_empty_when_no_settings(self):
        sm = SessionManager()
        assert sm.get_preprocessing_steps() == []

    def test_baseline_first(self):
        sm = SessionManager()
        baseline = {"type": "baseline", "method": "mean"}
        filt = {"method": "lowpass", "cutoff": 500}
        sm._preprocessing_settings = {"baseline": baseline, "filters": {"lowpass": filt}}
        steps = sm.get_preprocessing_steps()
        assert steps[0] == baseline
        assert steps[1] == filt

    def test_filters_sorted_alphabetically(self):
        sm = SessionManager()
        sm._preprocessing_settings = {"filters": {"lowpass": {"m": "lp"}, "bandpass": {"m": "bp"}}}
        steps = sm.get_preprocessing_steps()
        assert steps[0]["m"] == "bp"  # bandpass before lowpass
        assert steps[1]["m"] == "lp"


# ---------------------------------------------------------------------------
# performance_settings
# ---------------------------------------------------------------------------


class TestPerformanceSettings:
    def test_setter_updates_and_emits(self, qtbot):
        sm = SessionManager()
        received = []
        sm.preferences_changed.connect(received.append)
        sm.performance_settings = {"max_cpu_cores": 4}
        assert sm._performance_settings["max_cpu_cores"] == 4
        assert len(received) == 1

    def test_invalid_type_logs_warning_no_emit(self, qtbot, caplog):
        """Line 217: non-dict argument must be rejected with a warning."""
        import logging

        sm = SessionManager()
        received = []
        sm.preferences_changed.connect(received.append)
        with caplog.at_level(logging.WARNING, logger="Synaptipy.application.session_manager"):
            sm.performance_settings = "not a dict"  # type: ignore[assignment]
        assert len(received) == 0
        assert any("dict" in r.message for r in caplog.records)

    def test_emit_preferences_changed(self, qtbot):
        """Line 241: emit_preferences_changed re-fires the current settings."""
        sm = SessionManager()
        received = []
        sm.preferences_changed.connect(received.append)
        sm.emit_preferences_changed()
        assert len(received) == 1
        assert received[0]["max_cpu_cores"] == sm._performance_settings["max_cpu_cores"]


# ---------------------------------------------------------------------------
# save_session / load_session / apply_session
# ---------------------------------------------------------------------------


class TestSessionPersistence:
    def test_save_returns_false_on_io_error(self, tmp_path, monkeypatch):
        """Lines 297-299: write failure must return False without raising."""
        import Synaptipy.application.session_manager as sm_mod

        monkeypatch.setattr(sm_mod, "_SESSION_DIR", tmp_path / "no_perms")
        monkeypatch.setattr(sm_mod, "_SESSION_FILE", tmp_path / "no_perms" / "session.json")

        sm = SessionManager()
        # Make mkdir raise by pointing at a location with a file where a dir is needed
        blocker = tmp_path / "no_perms"
        blocker.write_bytes(b"block")  # file exists → mkdir will fail
        result = sm.save_session()
        assert result is False

    def test_load_returns_none_for_corrupt_json(self, tmp_path, monkeypatch):
        """Lines 319-321: corrupt JSON returns None."""
        import Synaptipy.application.session_manager as sm_mod

        session_file = tmp_path / "bad.json"
        session_file.write_text("NOT JSON {{{", encoding="utf-8")
        monkeypatch.setattr(sm_mod, "_SESSION_FILE", session_file)

        assert SessionManager.load_session() is None

    def test_load_returns_none_for_non_dict_json(self, tmp_path, monkeypatch):
        """Lines 324: JSON that is not a dict returns None."""
        import Synaptipy.application.session_manager as sm_mod

        session_file = tmp_path / "list.json"
        session_file.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
        monkeypatch.setattr(sm_mod, "_SESSION_FILE", session_file)

        assert SessionManager.load_session() is None

    def test_apply_session_ignores_non_dict(self):
        """Line 355: apply_session with non-dict arg must be a no-op."""
        sm = SessionManager()
        original_settings = dict(sm._global_settings)
        sm.apply_session("not a dict")  # type: ignore[arg-type]
        assert sm._global_settings == original_settings

    def test_apply_session_restores_settings(self, tmp_path, monkeypatch):
        """Lines 355-358: apply_session updates global and performance settings."""
        import Synaptipy.application.session_manager as sm_mod

        session_file = tmp_path / "session.json"
        monkeypatch.setattr(sm_mod, "_SESSION_DIR", tmp_path)
        monkeypatch.setattr(sm_mod, "_SESSION_FILE", session_file)

        sm = SessionManager()
        sm._file_list = []
        sm._current_file_index = -1
        sm.save_session()

        loaded = SessionManager.load_session()
        assert loaded is not None

        sm.apply_session({"global_settings": {"liquid_junction_potential_mv": 9.9}})
        assert sm.liquid_junction_potential_mv == pytest.approx(9.9)

    def test_save_and_load_round_trip_with_analysis_params(self, tmp_path, monkeypatch):
        """Lines 297-309: analysis_params are preserved in round-trip."""
        import Synaptipy.application.session_manager as sm_mod

        session_file = tmp_path / "session_ap.json"
        monkeypatch.setattr(sm_mod, "_SESSION_DIR", tmp_path)
        monkeypatch.setattr(sm_mod, "_SESSION_FILE", session_file)

        sm = SessionManager()
        sm._file_list = []
        sm._current_file_index = -1
        result = sm.save_session(active_tab_index=2, analysis_params={"threshold": -30.0})
        assert result is True

        loaded = SessionManager.load_session()
        assert loaded is not None
        assert loaded["analysis_params"]["threshold"] == pytest.approx(-30.0)
        assert loaded["active_tab_index"] == 2
