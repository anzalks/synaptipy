import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest

from Synaptipy.core.data_model import Channel, Recording
from Synaptipy.infrastructure.exporters.nwb_exporter import NWBExporter
from Synaptipy.shared.error_handling import ExportError


@pytest.fixture
def base_recording():
    rec = Recording(source_file=Path("test.abf"))
    rec.sampling_rate = 10000.0
    rec.session_start_time_dt = datetime.now(timezone.utc)
    ch1 = Channel("0", "Vm", "mV", 10000.0, [np.array([1.0, 2.0, 3.0])])
    ch1.current_data_trials = [np.array([10.0, 10.0, 10.0])]  # cmd
    ch1.current_units = "pA"
    rec.channels = {"0": ch1}
    return rec


@pytest.fixture
def base_metadata(base_recording):
    return {
        "session_description": "Coverage session",
        "identifier": str(uuid.uuid4()),
        "session_start_time": base_recording.session_start_time_dt,
        "subject_id": "SUBJ_001",
        "device_description": "Coverage Device",
        "species": "Mouse",
        "device_name": "Test Amp",
    }


def test_export_pynwb_unavailable(base_recording, base_metadata, tmp_path):
    exporter = NWBExporter()
    with patch("Synaptipy.infrastructure.exporters.nwb_exporter.PYNWB_AVAILABLE", False):
        with pytest.raises(ExportError, match="pynwb library is not installed"):
            exporter.export(base_recording, tmp_path / "out.nwb", base_metadata)


def test_make_stim_series_coverage():
    from Synaptipy.infrastructure.exporters.nwb_exporter import NWBExporter

    try:
        from datetime import datetime, timezone

        from pynwb import NWBFile
    except ImportError:
        pytest.skip("pynwb not installed")

    nwbfile = NWBFile("desc", "id", datetime.now(timezone.utc))
    device = nwbfile.create_device("dev")
    ic_elec = nwbfile.create_icephys_electrode(name="elec", description="desc", device=device)

    cmd_data = np.array([1.0, 2.0])

    # Test 'mv'
    stim1 = NWBExporter._make_stim_series(cmd_data, "mv", "s1", "desc", ic_elec, 1000.0, 0.0, 0, nwbfile)
    assert stim1 is not None

    # Test 'v'
    stim2 = NWBExporter._make_stim_series(cmd_data, "v", "s2", "desc", ic_elec, 1000.0, 0.0, 0, nwbfile)
    assert stim2 is not None

    # Test 'na'
    stim3 = NWBExporter._make_stim_series(cmd_data, "na", "s3", "desc", ic_elec, 1000.0, 0.0, 0, nwbfile)
    assert stim3 is not None

    # Test unknown
    stim4 = NWBExporter._make_stim_series(cmd_data, "unknown", "s4", "desc", ic_elec, 1000.0, 0.0, 0, nwbfile)
    assert stim4 is not None

    # Test exception handling inside _make_stim_series
    with patch.object(nwbfile, "add_stimulus", side_effect=Exception("Mock Stim Error")):
        stim_fail = NWBExporter._make_stim_series(cmd_data, "pa", "s_fail", "desc", ic_elec, 1000.0, 0.0, 0, nwbfile)
        assert stim_fail is None


def test_build_stim_from_abf_epochs():
    from Synaptipy.infrastructure.exporters.nwb_exporter import NWBExporter

    epochs = [
        {
            "nEpochType": 1,
            "fEpochInitLevel": -60.0,
            "fEpochLevelInc": 10.0,
            "lEpochInitDuration": 100,
            "lEpochDurationInc": 0,
        },
        {"nEpochType": 0},  # skipped
        {
            "nEpochType": 1,
            "fEpochInitLevel": 20.0,
            "fEpochLevelInc": 0.0,
            "lEpochInitDuration": 50,
            "lEpochDurationInc": 0,
        },
    ]

    # trial_idx=1 -> level=-50.0 for 100 samples
    synth = NWBExporter._build_stim_from_abf_epochs(epochs, 1, 120)
    assert synth is not None
    assert synth[0] == -50.0
    assert synth[100] == 20.0

    # Test invalid input
    assert NWBExporter._build_stim_from_abf_epochs({}, 0, 10) is None
    assert NWBExporter._build_stim_from_abf_epochs([{"invalid": "data"}], 0, 10) is None


def test_resolve_stimulus_series(base_recording):
    from Synaptipy.infrastructure.exporters.nwb_exporter import NWBExporter

    try:
        from datetime import datetime, timezone

        from pynwb import NWBFile
    except ImportError:
        pytest.skip("pynwb not installed")

    nwbfile = NWBFile("desc", "id", datetime.now(timezone.utc))
    device = nwbfile.create_device("dev")
    ic_elec = nwbfile.create_icephys_electrode(name="elec", description="desc", device=device)

    ch = base_recording.channels["0"]

    # Attempt 1: Raw digitized command
    stim, note = NWBExporter._resolve_stimulus_series(ch, 0, base_recording, ic_elec, 1000.0, 3, nwbfile)
    assert stim is not None
    assert note == ""

    # Attempt 2: Synthetic from ABF
    ch.current_data_trials = []  # Remove raw
    base_recording.metadata["abf_epochs"] = [{"nEpochType": 1, "fEpochInitLevel": 10.0, "lEpochInitDuration": 3}]
    stim2, note2 = NWBExporter._resolve_stimulus_series(ch, 0, base_recording, ic_elec, 1000.0, 3, nwbfile)
    assert stim2 is not None
    assert note2 == ""

    # Attempt 3: No stimulus available
    base_recording.metadata["abf_epochs"] = []
    stim3, note3 = NWBExporter._resolve_stimulus_series(ch, 0, base_recording, ic_elec, 1000.0, 3, nwbfile)
    assert stim3 is None
    assert "WARNING" in note3


def test_export_analysis_results(base_recording, base_metadata, tmp_path):
    exporter = NWBExporter()

    analysis_results = {
        "channel_name": "Vm",
        "analysis": "event_detection",
        "_raw_arrays": {"event_times": [0.1, 0.2], "event_amplitudes": [5.0, 6.0]},
    }

    base_recording.metadata["processing_history"] = [
        {"timestamp": "2024", "operation": "filter", "parameters": {"cutoff": 100}}
    ]

    try:
        import pynwb  # noqa: F401
    except ImportError:
        pytest.skip("pynwb not installed")

    out_file = tmp_path / "analysis.nwb"
    exporter.export(base_recording, out_file, base_metadata, analysis_results=analysis_results)
    assert out_file.exists()


def test_export_invalid_session_metadata(base_recording, base_metadata, tmp_path):
    exporter = NWBExporter()
    base_metadata["subject_id"] = None
    with pytest.raises(ValueError, match="MINDS metadata"):
        exporter.export(base_recording, tmp_path / "bad.nwb", base_metadata)

    base_metadata["subject_id"] = "Subj"
    base_metadata["session_start_time"] = "Not a datetime"
    with pytest.raises(ValueError, match="must be a datetime object"):
        exporter.export(base_recording, tmp_path / "bad2.nwb", base_metadata)


def test_export_channel_units(base_recording, base_metadata, tmp_path):
    exporter = NWBExporter()
    base_recording.channels["0"].units = "v"

    ch2 = Channel("1", "Im", "pA", 10000.0, [np.array([1.0])])
    ch2.units = "a"
    base_recording.channels["1"] = ch2

    ch3 = Channel("2", "unknown", "arb", 10000.0, [np.array([1.0])])
    base_recording.channels["2"] = ch3

    try:
        import pynwb  # noqa: F401
    except ImportError:
        pytest.skip("pynwb not installed")

    out_file = tmp_path / "units.nwb"
    exporter.export(base_recording, out_file, base_metadata)
    assert out_file.exists()


def test_subject_creation_failure(base_recording, base_metadata, tmp_path):
    exporter = NWBExporter()

    try:
        import pynwb  # noqa: F401
    except ImportError:
        pytest.skip("pynwb not installed")

    # Patch Subject creation to fail
    with patch("pynwb.file.Subject", side_effect=Exception("Mock Subject Error")):
        out_file = tmp_path / "subj_fail.nwb"
        # Should not crash, should continue without subject
        exporter.export(base_recording, out_file, base_metadata)
        assert out_file.exists()
