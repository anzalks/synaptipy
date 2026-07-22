"""UI tests for the protocol-map editor."""

from pathlib import Path

import numpy as np
import pytest
from PySide6 import QtWidgets

from synaptipy.application.gui.dialogs.protocol_map_dialog import ProtocolMapDialog
from synaptipy.core.data_model import Channel, Recording
from synaptipy.core.protocols import ProtocolAssignment, ProtocolSource


def _recording():
    recording = Recording(Path("ui_protocols.abf"))
    recording.channels = {"Vm": Channel("Vm", "Vm", "mV", 1_000, [np.zeros(100), np.zeros(100)])}
    return recording


@pytest.fixture(scope="module")
def qapp():
    """Keep this dialog test independent of external pytest GUI plugins."""
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    yield app


def test_protocol_map_dialog_adds_one_based_trial_assignment(qapp):
    dialog = ProtocolMapDialog(_recording(), current_trial=0)
    dialog.trials.setText("1-2")
    dialog.family.setCurrentText("current_step")
    dialog.manual_steps.setChecked(True)
    dialog.verified.setChecked(True)
    dialog._add()

    assignment = dialog.recording.protocol_map.assignments[0]
    assert assignment.trial_indices == (0, 1)
    assert assignment.parameters["current_steps"] == "manual"
    assert assignment.verified is True
    assert dialog.table.rowCount() == 1


def test_protocol_map_dialog_allows_overlapping_annotation(qapp):
    dialog = ProtocolMapDialog(_recording(), current_trial=0)
    dialog.start.setValue(0.1)
    dialog.end.setValue(0.3)
    dialog._add()
    dialog.annotation.setChecked(True)
    dialog.start.setValue(0.2)
    dialog.end.setValue(0.4)
    dialog._add()

    assert len(dialog.recording.protocol_map.assignments) == 2
    assert dialog.recording.protocol_map.assignments[1].is_analysis_segment is False


def test_protocol_map_dialog_promotes_detected_evidence_into_reviewable_assignment(qapp):
    recording = _recording()
    evidence = recording.protocol_map.add(
        ProtocolAssignment(
            protocol_family="recorded_evidence",
            trial_indices=(0,),
            source=ProtocolSource.RECORDED,
            parameters={
                "auto_detected": True,
                "ttl_channel": "ttl",
                "stimulus_times": [0.02, 0.05],
            },
            label="Auto-detected TTL pulses: Stim TTL",
            is_analysis_segment=False,
        )
    )
    dialog = ProtocolMapDialog(recording, current_trial=0)

    dialog.detected_evidence.setCurrentIndex(dialog.detected_evidence.findData(evidence.assignment_id))
    dialog.family.setCurrentText("paired_pulse")
    dialog.verified.setChecked(True)
    dialog._add()

    assignment = recording.protocol_map.assignments[-1]
    assert assignment.is_analysis_segment is True
    assert assignment.source == ProtocolSource.RECORDED
    assert assignment.parameters["ttl_channel"] == "ttl"
    assert assignment.parameters["stimulus_times"] == [0.02, 0.05]
    assert assignment.verified is True


def test_protocol_map_dialog_renders_to_screenshot(qapp):
    """The documented Protocol Map controls must render in the pinned Qt build."""
    dialog = ProtocolMapDialog(_recording(), current_trial=0)
    dialog.show()
    qapp.processEvents()

    screenshot = dialog.grab().toImage()

    assert screenshot.width() >= 700
    assert screenshot.height() >= 400
    assert not screenshot.isNull()
    dialog.close()
