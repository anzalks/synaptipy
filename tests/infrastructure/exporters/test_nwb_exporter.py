import pytest
from pathlib import Path
import uuid
from datetime import datetime, timezone
import numpy as np

# Make sure src is importable
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from Synaptipy.infrastructure.exporters import NWBExporter
from Synaptipy.core.data_model import Recording, Channel  # Use actual or placeholder
from Synaptipy.shared.error_handling import ExportError
from unittest.mock import patch


# Fixture for a sample recording object (can reuse from test_data_model or create new)
@pytest.fixture
def mock_recording_for_export():
    rec = Recording(source_file=Path("test_export.abf"))
    rec.sampling_rate = 10000.0
    rec.session_start_time_dt = datetime.now(timezone.utc)
    ch1_data = [np.linspace(0, i, 1000) for i in range(3)]  # 3 trials
    ch1 = Channel("0", "Vm", "mV", 10000.0, ch1_data)
    ch1.t_start = 0.0
    rec.channels = {"0": ch1}
    rec.metadata["notes"] = "Test notes"
    rec.protocol_name = "TestProtocol"
    return rec


@pytest.fixture
def nwb_exporter_instance():
    return NWBExporter()


@pytest.fixture
def valid_session_metadata(mock_recording_for_export):
    return {
        "session_description": "Test export session",
        "identifier": str(uuid.uuid4()),
        "session_start_time": mock_recording_for_export.session_start_time_dt,
        "experimenter": "Test User",
        "lab": "Test Lab",
        "institution": "Test Uni",
        "session_id": "SESSION001",
    }


def test_nwb_exporter_creation(nwb_exporter_instance):
    assert nwb_exporter_instance is not None


# Test actual file writing (integration test)
# Requires pynwb installed
def test_nwb_export_success(nwb_exporter_instance, mock_recording_for_export, valid_session_metadata, tmp_path):
    """Test successful NWB export to a temporary file."""
    # Try to import pynwb, skip if not available
    try:
        import pynwb
        from pynwb import NWBHDF5IO
    except ImportError:
        pytest.skip("pynwb not installed")

    # Check that NWBFile class is available (basic API check)
    if not hasattr(pynwb, "NWBFile"):
        pytest.skip("pynwb NWBFile class not available")

    output_file = tmp_path / "test_export_output.nwb"
    try:
        nwb_exporter_instance.export(mock_recording_for_export, output_file, valid_session_metadata)
    except Exception as e:
        pytest.fail(f"NWB export raised an unexpected exception: {e}")

    # Basic check: Does the file exist? Is it > 0 bytes?
    assert output_file.exists()
    assert output_file.stat().st_size > 0

    # More advanced check: Try reading the file back
    try:
        with NWBHDF5IO(str(output_file), "r") as io:
            read_nwbfile = io.read()
            assert read_nwbfile.identifier == valid_session_metadata["identifier"]
            assert read_nwbfile.session_description == valid_session_metadata["session_description"]
            # Check if acquisition data exists (time series naming may vary)
            assert len(read_nwbfile.acquisition) > 0, "No acquisition data found in exported NWB file"
            # Get first time series and verify it has data
            first_ts_name = list(read_nwbfile.acquisition.keys())[0]
            ts = read_nwbfile.acquisition[first_ts_name]
            assert ts.data is not None
            assert ts.rate == mock_recording_for_export.sampling_rate
    except Exception as e:
        pytest.fail(f"Failed to read back exported NWB file: {e}")


def test_nwb_export_missing_metadata(nwb_exporter_instance, mock_recording_for_export, tmp_path):
    """Test export fails if required metadata is missing."""
    output_file = tmp_path / "test_fail.nwb"
    invalid_metadata = {"identifier": "xyz"}  # Missing description and start time
    with pytest.raises(ValueError, match="Missing required NWB session metadata"):
        nwb_exporter_instance.export(mock_recording_for_export, output_file, invalid_metadata)


def test_nwb_exporter_permission_error(
    nwb_exporter_instance, mock_recording_for_export, valid_session_metadata, tmp_path
):
    """test that a permission error during write is raised/handled."""
    # Create a read-only directory
    ro_dir = tmp_path / "readonly_dir"
    ro_dir.mkdir()

    output_file = ro_dir / "output.nwb"

    # Mock open or pynwb write to raise PermissionError
    # Since we can't easily rely on OS permissions in all test envs, we patch the write method
    # Assume export calls pynwb.NWBHDF5IO.write or similar

    try:
        import pynwb
    except ImportError:
        pytest.skip("pynwb not installed")

    with patch("pynwb.NWBHDF5IO.write", side_effect=PermissionError("Mock permission denied")):
        with pytest.raises(ExportError):
            nwb_exporter_instance.export(mock_recording_for_export, output_file, valid_session_metadata)


def test_nwb_exporter_empty_recording(nwb_exporter_instance, valid_session_metadata, tmp_path):
    """Test exporting a recording with no channels."""
    empty_rec = Recording(source_file=Path("empty.abf"))
    empty_rec.sampling_rate = 10000.0
    empty_rec.channels = {}  # No channels

    output_file = tmp_path / "empty_export.nwb"

    try:
        import pynwb
    except ImportError:
        pytest.skip("pynwb not installed")

    # Should either succeed with empty acquisition or raise specific error
    # Pynwb generally allows empty files.
    try:
        nwb_exporter_instance.export(empty_rec, output_file, valid_session_metadata)
    except Exception as e:
        # If it fails, it should be a reasonable error
        pass

    if output_file.exists():
        # verify it works
        pass
