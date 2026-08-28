# tests/gui/test_evoked_responses_tab.py
# -*- coding: utf-8 -*-
"""Regression tests for the Evoked Responses / optogenetics analysis sub-tab.

The tab aggregates three timing-dependent analyses behind one method selector
and feeds them a TTL channel chosen in its own dropdown.  Every failure covered
here produced either a hard block or a full, confident-looking results table
built from inputs the user never asked for.
"""

from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest
from PySide6 import QtWidgets

import synaptipy.core.analysis  # noqa: F401 — registers the built-in analyses
from synaptipy.application.gui.analysis_tabs.base import AnalysisNotConfigured
from synaptipy.application.gui.analysis_tabs.metadata_driven import MetadataDrivenAnalysisTab
from synaptipy.core.data_model import Channel, Recording

FS = 20_000.0
DURATION = 2.0
STIM_ONSETS = (0.2, 0.25, 0.6, 0.65, 1.0, 1.05)


def _evoked_recording(units: str = "mV", flat_ttl: bool = False) -> Recording:
    """A current-clamp trace with paired EPSPs plus the TTL channel that drove them.

    ``flat_ttl`` keeps the stimulus channel at rest, which is what a wrong channel
    choice looks like: selectable, but carrying no detectable edges.
    """
    n_samples = int(FS * DURATION)
    time = np.arange(n_samples) / FS
    signal = np.full(n_samples, -65.0)
    for index, onset in enumerate(STIM_ONSETS):
        start = int(onset * FS)
        elapsed = time[start:] - onset
        amplitude = 8.0 if index % 2 == 0 else 5.0
        signal[start:] += amplitude * (np.exp(-elapsed / 0.02) - np.exp(-elapsed / 0.002))

    ttl = np.zeros(n_samples)
    if not flat_ttl:
        for onset in STIM_ONSETS:
            ttl[int(onset * FS) : int((onset + 0.002) * FS)] = 5.0

    recording = Recording(Path("evoked.abf"))
    recording.sampling_rate = FS
    recording.duration = DURATION
    recording.channels = {
        "0": Channel("0", "Vm", units, FS, [signal]),
        "1": Channel("1", "TTL", "V", FS, [ttl]),
    }
    return recording


@pytest.fixture
def evoked_tab(qtbot):
    """The Evoked Responses tab with a recording loaded and plotted."""
    tab = MetadataDrivenAnalysisTab("evoked_responses", neo_adapter=MagicMock())
    qtbot.addWidget(tab)
    return tab


def _load(tab, recording):
    tab._analysis_items = [{"path": recording.source_file, "target_type": "Current Trial", "trial_index": 0}]
    tab._selected_item_index = 0
    tab._on_item_load_success(recording)
    tab._plot_selected_data()


def _select_ttl(tab, channel_id):
    combo = tab._secondary_channel_combobox
    for index in range(combo.count()):
        if combo.itemData(index) == channel_id:
            combo.setCurrentIndex(index)
            return
    raise AssertionError(f"Secondary channel {channel_id!r} not offered by the tab")


def _select_method(tab, label):
    tab.method_combobox.setCurrentIndex(tab.method_combobox.findText(label))
    tab._on_method_selector_changed()


def _run(tab):
    params = tab._gather_analysis_parameters()
    return tab._execute_core_analysis(dict(params), tab._current_plot_data)


# ---------------------------------------------------------------------------
# Protocol gating
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "method",
    ["Evoked Sync", "Paired-Pulse Ratio", "Stimulus Train (STP)"],
)
def test_evoked_analyses_run_on_a_recording_with_no_protocol_map(evoked_tab, method):
    """A file without a hand-built Protocol Map must still be analysable.

    Timing-dependent analyses used to be marked ``incompatible`` against the
    implicit signal-only placeholder, so every evoked method raised
    "Protocol Map is incompatible with this analysis" on an ordinary recording
    and the whole tab was unusable.
    """
    recording = _evoked_recording()
    assert not recording.protocol_map.assignments  # no map: the common case

    _load(evoked_tab, recording)
    _select_method(evoked_tab, method)
    _select_ttl(evoked_tab, "1")

    results = _run(evoked_tab)

    assert results is not None
    assert results["metrics"]


# ---------------------------------------------------------------------------
# TTL channel wiring
# ---------------------------------------------------------------------------


def test_paired_pulse_uses_the_ttl_channel_selected_in_the_tab(evoked_tab):
    """Picking a TTL channel must drive the measurement, not sit unused.

    ``use_ttl`` defaulted to False, so PPR measured at the placeholder 0.1/0.2 s
    onsets while the tab displayed the user's TTL selection above it.
    """
    _load(evoked_tab, _evoked_recording())
    _select_method(evoked_tab, "Paired-Pulse Ratio")
    _select_ttl(evoked_tab, "1")

    metrics = _run(evoked_tab)["metrics"]

    assert metrics["ppr_error"] is None
    assert metrics["_stim_onsets"] == pytest.approx([0.2, 0.25], abs=1e-3)
    # 8 mV then 5 mV EPSPs -> paired-pulse depression, not a negative ratio.
    assert 0.5 < metrics["ratio_p2"] < 0.8


@pytest.mark.parametrize(
    "method",
    ["Evoked Sync", "Paired-Pulse Ratio", "Stimulus Train (STP)"],
)
def test_no_selected_stimulus_channel_names_the_control_that_fixes_it(evoked_tab, method):
    """Leaving the TTL dropdown on "(None)" blocks, and says what to do about it.

    The timing guardrail stands, but its message used to be
    "Protocol Map is incompatible with this analysis: requires protocol family:
    ...", which sends the user to a dialog when the fix is the dropdown directly
    above the button they just pressed.
    """
    _load(evoked_tab, _evoked_recording())
    _select_method(evoked_tab, method)
    _select_ttl(evoked_tab, None)  # the "(None)" entry

    with pytest.raises(AnalysisNotConfigured) as excinfo:
        _run(evoked_tab)

    message = str(excinfo.value)
    assert "TTL / Stimulus Channel" in message
    assert "Protocol Map is incompatible" not in message


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def test_analysis_errors_are_shown_next_to_the_results_table(evoked_tab):
    """An input error the analysis reported must be visible in the GUI.

    A channel that carries no edges yields a full-looking run with an error
    metric; that metric never reached the screen, so nothing distinguished it
    from a successful analysis.
    """
    _load(evoked_tab, _evoked_recording(flat_ttl=True))
    _select_method(evoked_tab, "Stimulus Train (STP)")
    _select_ttl(evoked_tab, "1")

    evoked_tab._display_analysis_results(_run(evoked_tab))

    assert not evoked_tab.analysis_message_label.isHidden()
    assert "TTL detection found no stimulus onsets" in evoked_tab.analysis_message_label.text()


def test_analysis_warnings_are_shown_and_cleared_on_the_next_clean_run(evoked_tab):
    """Warnings reach the user, and do not linger once the input is fixed."""
    _load(evoked_tab, _evoked_recording())
    _select_method(evoked_tab, "Paired-Pulse Ratio")
    _select_ttl(evoked_tab, "1")

    # Ask for more pulses than the TTL channel actually carries.
    evoked_tab.param_generator.widgets["n_pulses"].setValue(10)
    evoked_tab._display_analysis_results(_run(evoked_tab))
    assert not evoked_tab.analysis_message_label.isHidden()
    assert "10 pulses" in evoked_tab.analysis_message_label.text()

    evoked_tab.param_generator.widgets["n_pulses"].setValue(2)
    evoked_tab._display_analysis_results(_run(evoked_tab))
    assert evoked_tab.analysis_message_label.isHidden()


def test_evoked_sync_reports_a_baseline_subtracted_response_amplitude(evoked_tab):
    """The peak amplitude the parameters promise must appear as a metric.

    ``amplitude_window_ms`` drove only the plot markers; the amplitude itself
    was never reported, so the tab could not answer "how big was the response".
    """
    _load(evoked_tab, _evoked_recording())
    _select_method(evoked_tab, "Evoked Sync")
    _select_ttl(evoked_tab, "1")

    metrics = _run(evoked_tab)["metrics"]

    # 8 mV / 5 mV alternating EPSPs, measured against the pre-stimulus baseline.
    assert metrics["mean_response_amplitude"] == pytest.approx(4.5, abs=1.0)
    assert len(metrics["response_amplitudes"]) == len(STIM_ONSETS)
    # Absolute peaks stay in signal units for the plot markers.
    assert all(value < -50.0 for value in metrics["_peak_amps"])


# ---------------------------------------------------------------------------
# Clamp-aware defaults
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("units", "expected_polarity", "expected_peak"),
    [("mV", "positive", "max"), ("pA", "negative", "min")],
)
def test_response_polarity_defaults_follow_the_channel_clamp_mode(qtbot, units, expected_polarity, expected_peak):
    """A negative default on a current-clamp EPSP detects nothing at all."""
    tab = MetadataDrivenAnalysisTab("evoked_responses", neo_adapter=MagicMock())
    qtbot.addWidget(tab)
    _load(tab, _evoked_recording(units=units))

    _select_method(tab, "Paired-Pulse Ratio")
    assert tab.param_generator.widgets["polarity"].currentText() == expected_polarity

    _select_method(tab, "Evoked Sync")
    assert tab.param_generator.widgets["response_polarity"].currentText() == expected_peak
    assert tab.param_generator.widgets["event_direction"].currentText() == expected_polarity


def test_a_hand_set_polarity_survives_a_channel_change(evoked_tab):
    """Context defaults fill in a blank; they never overwrite an explicit choice."""
    _load(evoked_tab, _evoked_recording(units="mV"))
    _select_method(evoked_tab, "Paired-Pulse Ratio")
    assert evoked_tab.param_generator.widgets["polarity"].currentText() == "positive"

    evoked_tab.param_generator.widgets["polarity"].setCurrentText("negative")
    evoked_tab._update_parameter_visibility()

    assert evoked_tab.param_generator.widgets["polarity"].currentText() == "negative"


# ---------------------------------------------------------------------------
# Method switching
# ---------------------------------------------------------------------------


def test_switching_method_drops_the_previous_method_overlays(evoked_tab):
    """Stimulus lines and fits from the old method must leave the canvas."""
    _load(evoked_tab, _evoked_recording())
    _select_method(evoked_tab, "Paired-Pulse Ratio")
    _select_ttl(evoked_tab, "1")
    evoked_tab._plot_analysis_visualizations(_run(evoked_tab))
    assert evoked_tab._dynamic_plot_items

    _select_method(evoked_tab, "Evoked Sync")

    assert not evoked_tab._dynamic_plot_items
    assert evoked_tab.analysis_message_label.isHidden()


def test_switching_method_retargets_the_secondary_channel_parameter(evoked_tab):
    """Each sub-analysis names its own secondary input; the tab must follow."""
    _load(evoked_tab, _evoked_recording())
    for method in ("Evoked Sync", "Paired-Pulse Ratio", "Stimulus Train (STP)"):
        _select_method(evoked_tab, method)
        expected = evoked_tab.metadata["requires_secondary_channel"]["param_name"]
        assert evoked_tab._secondary_channel_param_name == expected


# ---------------------------------------------------------------------------
# Unconfigured state must not interrupt the user
# ---------------------------------------------------------------------------


@pytest.fixture
def no_modal_dialogs(monkeypatch):
    """Record every modal QMessageBox instead of showing one."""
    shown = []

    for name in ("critical", "warning", "information", "question"):

        def spy(*args, _name=name, **kwargs):
            shown.append((_name, str(args[2]) if len(args) > 2 else ""))
            return QtWidgets.QMessageBox.StandardButton.Ok

        monkeypatch.setattr(QtWidgets.QMessageBox, name, staticmethod(spy))
    return shown


def test_selecting_the_tab_never_raises_a_modal_error(qtbot, no_modal_dialogs):
    """Opening the tab must not greet the user with an "Analysis Error" box.

    The tab auto-runs when it becomes visible.  With no stimulus channel chosen
    that run cannot proceed, which used to surface as a modal dialog the moment
    the user clicked onto the tab, on top of whatever else was on screen.
    """
    tabs = QtWidgets.QTabWidget()
    qtbot.addWidget(tabs)
    tabs.addTab(QtWidgets.QWidget(), "Other")
    tab = MetadataDrivenAnalysisTab("evoked_responses", neo_adapter=MagicMock())
    tabs.addTab(tab, "Evoked Responses")
    tabs.show()

    # Channel names carry no stimulus hint, so nothing is preselected.
    recording = _evoked_recording()
    recording.channels["1"].name = "IN1"
    _load(tab, recording)
    _select_ttl(tab, None)

    tabs.setCurrentWidget(tab)
    qtbot.wait(600)

    assert no_modal_dialogs == []
    assert not tab.analysis_message_label.isHidden()
    assert "Select the TTL / Stimulus Channel" in tab.analysis_message_label.text()
    assert tab.results_table.rowCount() == 0


def test_an_unconfigured_manual_run_explains_itself_without_a_dialog(evoked_tab, no_modal_dialogs):
    """Pressing Run before choosing a channel is a setup state, not a failure."""
    recording = _evoked_recording()
    recording.channels["1"].name = "IN1"
    _load(evoked_tab, recording)
    _select_ttl(evoked_tab, None)

    evoked_tab._trigger_analysis()

    assert no_modal_dialogs == []
    assert "needs stimulus timing" in evoked_tab.analysis_message_label.text()


# ---------------------------------------------------------------------------
# Stimulus channel preselection
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("channel_name", ["TTL", "StimOut", "Opto_LED", "digital_trig"])
def test_a_channel_named_as_the_stimulus_is_preselected(qtbot, channel_name):
    """The tab should not open blocked on a dropdown the user has to hunt for."""
    tab = MetadataDrivenAnalysisTab("evoked_responses", neo_adapter=MagicMock())
    qtbot.addWidget(tab)
    recording = _evoked_recording()
    recording.channels["1"].name = channel_name

    _load(tab, recording)

    assert tab._secondary_channel_combobox.currentData() == "1"


@pytest.mark.parametrize(
    "names",
    [
        ("Imo", "IN1"),  # nothing identifies a stimulus channel
        ("TTL_a", "TTL_b"),  # ambiguous: two candidates
    ],
)
def test_preselection_stays_on_none_when_the_choice_is_not_obvious(qtbot, names):
    """A guess is only made from an unambiguous recorded name."""
    tab = MetadataDrivenAnalysisTab("evoked_responses", neo_adapter=MagicMock())
    qtbot.addWidget(tab)
    recording = _evoked_recording()
    recording.channels["0"].name, recording.channels["1"].name = names
    if names == ("TTL_a", "TTL_b"):
        recording.channels["2"] = Channel("2", "TTL_c", "V", FS, [np.zeros(int(FS * DURATION))])

    _load(tab, recording)

    assert tab._secondary_channel_combobox.currentData() is None


def test_preselection_never_moves_an_existing_selection(evoked_tab):
    """Preselection fills a blank dropdown; it does not second-guess a choice."""
    recording = _evoked_recording()
    # A second, differently named channel the user might legitimately prefer.
    recording.channels["2"] = Channel("2", "AuxIn", "V", FS, [np.zeros(int(FS * DURATION))])
    _load(evoked_tab, recording)
    assert evoked_tab._secondary_channel_combobox.currentData() == "1"  # named TTL

    _select_ttl(evoked_tab, "2")
    evoked_tab._preselect_named_stimulus_channel()

    assert evoked_tab._secondary_channel_combobox.currentData() == "2"


# ---------------------------------------------------------------------------
# Manual stimulus timing
# ---------------------------------------------------------------------------


def _voltage_clamp_train_recording() -> Recording:
    """A voltage-clamp EPSC train with no TTL channel recorded alongside it."""
    n_samples = int(FS * 4.0)
    time = np.arange(n_samples) / FS
    current = np.zeros(n_samples)
    for index in range(10):
        onset = 2.0 + index * 0.05
        start = int(onset * FS)
        elapsed = time[start:] - onset
        amplitude = -80.0 * (0.85**index)
        current[start:] += amplitude * (np.exp(-elapsed / 0.008) - np.exp(-elapsed / 0.001))

    recording = Recording(Path("vclamp.abf"))
    recording.sampling_rate = FS
    recording.duration = 4.0
    recording.channels = {"0": Channel("0", "Im0", "pA", FS, [current])}
    return recording


@pytest.mark.parametrize(
    ("method", "settings"),
    [
        ("Stimulus Train (STP)", {"stim_start_s": 2.0, "stim_frequency_hz": 20.0, "n_pulses": 10}),
        ("Paired-Pulse Ratio", {"stim1_onset_s": 2.0, "stim2_onset_s": 2.05, "n_pulses": 2}),
    ],
)
def test_manual_stimulus_onsets_are_accepted_when_no_ttl_was_recorded(evoked_tab, method, settings):
    """Typing the onsets is supplying stimulus timing, and must not be blocked.

    Many rigs never record a TTL channel.  The timing gate only accepted a
    selected channel or a Protocol Map entry, so unticking "Detect Stim from
    TTL" and entering the onsets left the tab permanently stuck on
    "needs recorded stimulus timing" with no way forward.
    """
    _load(evoked_tab, _voltage_clamp_train_recording())
    _select_method(evoked_tab, method)
    assert evoked_tab._secondary_channel_combobox.currentData() is None  # nothing to select

    widgets = evoked_tab.param_generator.widgets
    widgets["use_ttl"].setChecked(False)
    for name, value in settings.items():
        widgets[name].setValue(value)

    results = _run(evoked_tab)

    assert results is not None
    assert results["metrics"]
    # The timing source is recorded on the result rather than assumed verified.
    assert any("entered manually" in w or "manual parameters" in w for w in results["warnings"])


def test_manual_timing_produces_the_expected_depressing_train(evoked_tab):
    """The manual path measures at the onsets given, not at placeholder defaults."""
    _load(evoked_tab, _voltage_clamp_train_recording())
    _select_method(evoked_tab, "Stimulus Train (STP)")

    widgets = evoked_tab.param_generator.widgets
    widgets["use_ttl"].setChecked(False)
    widgets["stim_start_s"].setValue(2.0)
    widgets["stim_frequency_hz"].setValue(20.0)
    widgets["n_pulses"].setValue(10)

    metrics = _run(evoked_tab)["metrics"]

    assert metrics["pulse_count"] == 10
    assert metrics["stp_type"] == "depression"
    assert metrics["amplitudes_norm"][-1] < metrics["amplitudes_norm"][0]


def test_manual_timing_warning_reaches_the_results_panel(evoked_tab):
    """A manually timed run says so on screen, not only in the exported CSV."""
    _load(evoked_tab, _voltage_clamp_train_recording())
    _select_method(evoked_tab, "Stimulus Train (STP)")
    widgets = evoked_tab.param_generator.widgets
    widgets["use_ttl"].setChecked(False)
    widgets["stim_start_s"].setValue(2.0)

    evoked_tab._display_analysis_results(_run(evoked_tab))

    assert not evoked_tab.analysis_message_label.isHidden()
    assert "not verified against a recorded TTL channel" in evoked_tab.analysis_message_label.text()


def test_the_block_message_offers_the_manual_route_only_where_one_exists(evoked_tab):
    """Evoked Sync can only read timing from a channel; the train analyses cannot lie about that."""
    _load(evoked_tab, _voltage_clamp_train_recording())

    _select_method(evoked_tab, "Stimulus Train (STP)")
    with pytest.raises(AnalysisNotConfigured) as train_error:
        _run(evoked_tab)
    assert "untick 'Detect Stim from TTL'" in str(train_error.value)

    _select_method(evoked_tab, "Evoked Sync")
    with pytest.raises(AnalysisNotConfigured) as sync_error:
        _run(evoked_tab)
    assert "untick" not in str(sync_error.value)
    assert "TTL / Stimulus Channel" in str(sync_error.value)
