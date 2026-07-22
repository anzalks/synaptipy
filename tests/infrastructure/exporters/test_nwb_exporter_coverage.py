import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest

from synaptipy.core.data_model import Channel, Recording
from synaptipy.infrastructure.exporters.nwb_exporter import NWBExporter
from synaptipy.shared.error_handling import ExportError


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
    with patch("synaptipy.infrastructure.exporters.nwb_exporter.PYNWB_AVAILABLE", False):
        with pytest.raises(ExportError, match="pynwb library is not installed"):
            exporter.export(base_recording, tmp_path / "out.nwb", base_metadata)


def test_make_stim_series_coverage():
    from synaptipy.infrastructure.exporters.nwb_exporter import NWBExporter

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
    from synaptipy.infrastructure.exporters.nwb_exporter import NWBExporter

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


def test_build_stim_from_abf_epochs_handles_bounds_and_malformed_values():
    """Epoch reconstruction must be bounded and fail safely on corrupt headers."""
    bounded = NWBExporter._build_stim_from_abf_epochs(
        [{"nEpochType": 1, "fEpochInitLevel": 12.0, "lEpochInitDuration": 50}],
        trial_idx=0,
        n_samples=3,
    )
    assert np.array_equal(bounded, np.array([12.0, 12.0, 12.0]))

    assert NWBExporter._build_stim_from_abf_epochs([{"nEpochType": "not-an-integer"}], trial_idx=0, n_samples=3) is None
    assert (
        NWBExporter._build_stim_from_abf_epochs(
            [{"nEpochType": 1, "fEpochInitLevel": 0.0, "lEpochInitDuration": 3}], trial_idx=0, n_samples=3
        )
        is None
    )


def test_make_stim_series_converts_picoamps_and_uses_default_rate():
    """Command waveforms are written in SI units even when a rate is unavailable."""
    from pynwb import NWBFile

    nwbfile = NWBFile("desc", "id-pa", datetime.now(timezone.utc))
    device = nwbfile.create_device("dev")
    electrode = nwbfile.create_icephys_electrode(name="elec-pa", description="desc", device=device)
    stim = NWBExporter._make_stim_series(np.array([100.0]), "pA", "stim-pa", "desc", electrode, 0.0, 0.0, 2, nwbfile)

    assert stim is not None
    assert stim.unit == "amperes"
    assert float(stim.data[0]) == pytest.approx(100e-12)
    assert stim.rate == pytest.approx(1000.0)


def test_resolve_stimulus_series(base_recording):
    from synaptipy.infrastructure.exporters.nwb_exporter import NWBExporter

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

    from pynwb import NWBHDF5IO

    with NWBHDF5IO(str(out_file), "r") as io:
        nwbfile = io.read()
        assert "analysis" in nwbfile.processing
        assert "Vm_event_detection" in nwbfile.processing["analysis"].data_interfaces


def test_export_invalid_session_metadata(base_recording, base_metadata, tmp_path):
    exporter = NWBExporter()
    base_metadata["subject_id"] = None
    with pytest.raises(ValueError, match="MINDS metadata"):
        exporter.export(base_recording, tmp_path / "bad.nwb", base_metadata)

    base_metadata["subject_id"] = "Subj"
    base_metadata["session_start_time"] = "Not a datetime"
    with pytest.raises(ValueError, match="must be a datetime object"):
        exporter.export(base_recording, tmp_path / "bad2.nwb", base_metadata)


def test_export_analysis_results_ignores_incomplete_rows(base_recording, base_metadata, tmp_path):
    """Incomplete analysis rows are skipped without losing valid event tables."""
    analysis_rows = [
        "not-a-result-row",
        {"_raw_arrays": {}},
        {"channel": "Vm", "analysis": "events", "_raw_arrays": {"event_times": [0.1, 0.3]}},
    ]

    out_file = tmp_path / "analysis_incomplete_rows.nwb"
    NWBExporter().export(base_recording, out_file, base_metadata, analysis_results=analysis_rows)
    assert out_file.exists()

    from pynwb import NWBHDF5IO

    with NWBHDF5IO(str(out_file), "r") as io:
        nwbfile = io.read()
        assert "Vm_events" in nwbfile.processing["analysis"].data_interfaces


def test_export_channel_units(base_recording, base_metadata, tmp_path):
    exporter = NWBExporter()
    base_recording.channels["0"].units = "v"

    ch2 = Channel("1", "Im", "pA", 10000.0, [np.array([1.0])])
    ch2.units = "a"
    base_recording.channels["1"] = ch2

    ch3 = Channel("2", "unknown", "arb", 10000.0, [np.array([1.0])])
    base_recording.channels["2"] = ch3

    ch4 = Channel("3", "Im-pA", "pA", 10000.0, [np.array([1.0])])
    base_recording.channels["3"] = ch4

    ch5 = Channel("4", "Im-nA", "nA", 10000.0, [np.array([1.0])])
    base_recording.channels["4"] = ch5

    try:
        import pynwb  # noqa: F401
    except ImportError:
        pytest.skip("pynwb not installed")

    out_file = tmp_path / "units.nwb"
    exporter.export(base_recording, out_file, base_metadata)
    assert out_file.exists()


def test_export_skips_invalid_channels_and_empty_trials(base_recording, base_metadata, tmp_path):
    """A malformed channel must not prevent the recording metadata from exporting."""
    base_recording.channels = {
        "not_a_channel": object(),
        "empty": Channel("empty", "empty", "mV", 10000.0, []),
        "zero_samples": Channel("zero", "zero", "mV", 10000.0, [np.array([])]),
    }

    out_file = tmp_path / "empty_channels.nwb"
    NWBExporter().export(base_recording, out_file, base_metadata)

    assert out_file.exists()


def test_export_empty_recording_writes_a_valid_nwb_file(base_recording, base_metadata, tmp_path):
    """An empty recording is exported as a valid metadata-only NWB file."""
    base_recording.channels = {}
    out_file = tmp_path / "no_channels.nwb"

    NWBExporter().export(base_recording, out_file, base_metadata)

    assert out_file.exists()


def test_export_supplies_optional_metadata_defaults_without_mutating_input(base_recording, tmp_path):
    """Missing optional DANDI metadata receives export defaults, not caller mutation."""
    metadata = {
        "session_description": "defaults",
        "identifier": "defaults-id",
        "session_start_time": datetime.now(timezone.utc),
        "subject_id": "S-defaults",
        "device_description": "Amplifier",
    }

    out_file = tmp_path / "defaults.nwb"
    NWBExporter().export(base_recording, out_file, metadata)

    assert out_file.exists()
    assert "species" not in metadata
    assert "device_name" not in metadata


def test_export_records_protocol_and_safely_defaults_invalid_temperature(base_recording, base_metadata, tmp_path):
    """Export metadata remains valid when optional acquisition metadata is malformed."""
    base_recording.imported_protocol_label = "current-step"
    base_recording.metadata["recording_temperature"] = "not-a-temperature"

    out_file = tmp_path / "protocol_temperature.nwb"
    NWBExporter().export(base_recording, out_file, base_metadata)

    from pynwb import NWBHDF5IO

    with NWBHDF5IO(str(out_file), "r") as io:
        nwbfile = io.read()
        assert "Imported protocol label: current-step" in nwbfile.notes
        assert "Recording temperature: 22.0 degC" in nwbfile.notes


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


# ---------------------------------------------------------------------------
# Additional targeted coverage: lines 336, 338, 343-347, 359
# ---------------------------------------------------------------------------


def test_export_non_recording_raises_type_error(base_metadata, tmp_path):
    """Line 336: non-Recording object raises TypeError."""
    from unittest.mock import MagicMock

    exporter = NWBExporter()
    fake = MagicMock()
    fake.source_file.name = "fake.wcp"
    # MagicMock is not an instance of Recording → TypeError
    with pytest.raises(TypeError, match="Invalid 'recording' object"):
        exporter.export(fake, tmp_path / "x.nwb", base_metadata)


def test_export_recording_no_channels_dict_raises(base_metadata, tmp_path):
    """Line 337-338: Recording without proper channels dict raises ValueError."""
    from synaptipy.core.data_model import Recording

    rec = Recording(source_file=Path("bad.wcp"))
    rec.channels = "not_a_dict"
    exporter = NWBExporter()
    with pytest.raises(ValueError, match="channels"):
        exporter.export(rec, tmp_path / "x.nwb", base_metadata)


def test_export_missing_device_description_raises(base_recording, tmp_path):
    """Line 359: missing device_description raises ValueError."""
    exporter = NWBExporter()
    metadata = {
        "session_description": "test",
        "identifier": "abc123",
        "session_start_time": datetime.now(timezone.utc),
        "subject_id": "S1",
        "species": "Mouse",
        "device_name": "Amp",
        # device_description intentionally missing
    }
    with pytest.raises(ValueError, match="device_description"):
        exporter.export(base_recording, tmp_path / "x.nwb", metadata)


def test_export_kwargs_injection(base_recording, tmp_path):
    """Lines 343-347: subject_id/session_start_time/device_description passed as kwargs."""
    try:
        import pynwb  # noqa: F401
    except ImportError:
        pytest.skip("pynwb not installed")

    exporter = NWBExporter()
    metadata = {
        "session_description": "kwarg test",
        "identifier": "kwarg-id",
        "species": "Mouse",
        "device_name": "Test Amp",
    }
    out_file = tmp_path / "kwargs.nwb"
    exporter.export(
        base_recording,
        out_file,
        metadata,
        subject_id="S_KWARG",
        session_start_time=datetime.now(timezone.utc),
        device_description="Patch clamp amplifier",
    )
    assert out_file.exists()


def test_export_naive_datetime_localizes(base_recording, tmp_path):
    """Lines 372-380: naive session_start_time gets localized (no tzinfo)."""
    try:
        import pynwb  # noqa: F401
    except ImportError:
        pytest.skip("pynwb not installed")

    exporter = NWBExporter()
    metadata = {
        "session_description": "naive dt test",
        "identifier": "naive-dt",
        "session_start_time": datetime(2024, 1, 1, 12, 0, 0),  # no tzinfo!
        "subject_id": "S1",
        "species": "Mouse",
        "device_name": "Amp",
        "device_description": "Patch clamp amplifier",
    }
    out_file = tmp_path / "naive.nwb"
    exporter.export(base_recording, out_file, metadata)
    assert out_file.exists()
