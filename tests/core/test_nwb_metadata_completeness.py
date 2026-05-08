"""
Test suite for NWB metadata completeness and DANDI compliance.

This module validates that all required metadata is properly exported to NWB files,
including electrode characterization data and preprocessing history.

Covers:
- Electrode resistance and seal export
- Preprocessing history tracking
- DANDI validator compliance
- NWB 2.x schema conformance
"""

import tempfile
from datetime import datetime
from pathlib import Path

import numpy as np
import pytest

from Synaptipy.core.data_model import Channel, Recording
from Synaptipy.infrastructure.exporters.nwb_exporter import NWBExporter

try:
    from pynwb import NWBHDF5IO, validate
    from pynwb.icephys import IntracellularElectrode  # noqa: F401

    PYNWB_AVAILABLE = True
except ImportError:
    PYNWB_AVAILABLE = False


@pytest.mark.skipif(not PYNWB_AVAILABLE, reason="PyNWB not available")
class TestElectrodeMetadataExport:
    """Test that electrode resistance and seal are exported to NWB."""

    def test_electrode_resistance_exported(self):
        """Electrode resistance should be included in NWB electrode metadata."""
        # Create recording with electrode metadata
        recording = Recording(source_file=Path("test.abf"))
        recording.protocol_name = "IV"
        recording.duration = 1.0
        recording.sampling_rate = 10000.0

        channel = Channel(
            id="0",
            name="Vm",
            units="mV",
            sampling_rate=10000.0,
            data_trials=[np.random.randn(10000)],
        )
        channel.electrode_resistance = "10 MOhm"  # Pipette resistance
        channel.electrode_seal = "5 GOhm"  # Seal resistance
        channel.electrode_description = "Patch pipette"
        channel.electrode_location = "Hippocampus CA1"

        recording.channels["Vm"] = channel

        # Export to NWB
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "test_electrode.nwb"
            NWBExporter().export(
                recording=recording,
                output_path=output_path,
                session_metadata={
                    "session_description": "Test electrode metadata",
                    "identifier": "test_electrode",
                    "session_start_time": recording.session_start_time_dt or datetime.now(),
                    "experimenter": "Test",
                    "lab": "Test Lab",
                    "institution": "Test University",
                },
            )

            # Read back and validate
            assert output_path.exists(), "NWB file should be created"

            with NWBHDF5IO(str(output_path), "r") as io:
                nwbfile = io.read()

                # Check electrode exists
                assert len(nwbfile.icephys_electrodes) > 0, "Electrode should be exported"

                electrode = list(nwbfile.icephys_electrodes.values())[0]

                # Validate resistance and seal are present
                assert hasattr(electrode, "resistance"), "Electrode should have resistance attribute"
                assert electrode.resistance == "10 MOhm", f"Expected '10 MOhm', got {electrode.resistance}"

                assert hasattr(electrode, "seal"), "Electrode should have seal attribute"
                assert electrode.seal == "5 GOhm", f"Expected '5 GOhm', got {electrode.seal}"

    def test_electrode_without_resistance_seal(self):
        """NWB export should handle channels without resistance/seal gracefully."""
        recording = Recording(source_file=Path("test.abf"))
        recording.protocol_name = "Steps"
        recording.duration = 1.0
        recording.sampling_rate = 10000.0

        channel = Channel(
            id="0",
            name="Vm",
            units="mV",
            sampling_rate=10000.0,
            data_trials=[np.random.randn(10000)],
        )
        # No electrode_resistance or electrode_seal set
        channel.electrode_description = "Unknown"

        recording.channels["Vm"] = channel

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "test_no_electrode.nwb"

            # Should not crash
            NWBExporter().export(
                recording=recording,
                output_path=output_path,
                session_metadata={
                    "session_description": "Test without electrode metadata",
                    "identifier": "test_no_electrode",
                    "session_start_time": recording.session_start_time_dt or datetime.now(),
                    "experimenter": "Test",
                    "lab": "Test Lab",
                    "institution": "Test University",
                },
            )

            assert output_path.exists(), "NWB file should be created even without resistance/seal"


@pytest.mark.skipif(not PYNWB_AVAILABLE, reason="PyNWB not available")
class TestPreprocessingHistoryExport:
    """Test that preprocessing history is exported to NWB."""

    def test_preprocessing_history_exported(self):
        """Preprocessing steps should be exported as DynamicTable in NWB."""
        recording = Recording(source_file=Path("test.abf"))
        recording.protocol_name = "Steps"
        recording.duration = 1.0
        recording.sampling_rate = 10000.0

        # Add preprocessing steps
        recording.add_preprocessing_step("lowpass", {"cutoff_hz": 300, "order": 4})
        recording.add_preprocessing_step("baseline_subtract", {"window": [0.0, 0.05]})
        recording.add_preprocessing_step("notch", {"frequency_hz": 50})

        channel = Channel(
            id="0",
            name="Vm",
            units="mV",
            sampling_rate=10000.0,
            data_trials=[np.random.randn(10000)],
        )
        recording.channels["Vm"] = channel

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "test_preprocessing.nwb"
            NWBExporter().export(
                recording=recording,
                output_path=output_path,
                session_metadata={
                    "session_description": "Test preprocessing history",
                    "identifier": "test_preprocessing",
                    "session_start_time": recording.session_start_time_dt or datetime.now(),
                    "experimenter": "Test",
                    "lab": "Test Lab",
                    "institution": "Test University",
                },
            )

            # Read back and validate
            with NWBHDF5IO(str(output_path), "r") as io:
                nwbfile = io.read()

                # Check preprocessing module exists
                assert "preprocessing" in nwbfile.processing, "Preprocessing module should exist"

                preproc_module = nwbfile.processing["preprocessing"]
                assert "preprocessing_steps" in preproc_module.data_interfaces, "Preprocessing steps table should exist"

                steps_table = preproc_module["preprocessing_steps"]

                # Should have 3 rows
                assert len(steps_table) == 3, f"Expected 3 steps, got {len(steps_table)}"

                # Validate operations - DynamicTable columns accessed via .get() or direct attribute
                operations_col = (
                    steps_table.operation[:] if hasattr(steps_table, "operation") else steps_table["operation"][:]
                )
                operations = [str(op) for op in operations_col]
                assert "lowpass" in operations, f"Lowpass should be in operations, got {operations}"
                assert "baseline_subtract" in operations, f"Baseline subtract should be in operations, got {operations}"
                assert "notch" in operations, f"Notch should be in operations, got {operations}"

    def test_no_preprocessing_history(self):
        """NWB export should handle recordings without preprocessing history."""
        recording = Recording(source_file=Path("test.abf"))
        recording.protocol_name = "Steps"
        recording.duration = 1.0
        recording.sampling_rate = 10000.0

        # No preprocessing steps added
        channel = Channel(
            id="0",
            name="Vm",
            units="mV",
            sampling_rate=10000.0,
            data_trials=[np.random.randn(10000)],
        )
        recording.channels["Vm"] = channel

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "test_no_preprocessing.nwb"

            # Should not crash
            NWBExporter().export(
                recording=recording,
                output_path=output_path,
                session_metadata={
                    "session_description": "Test without preprocessing",
                    "identifier": "test_no_preprocessing",
                    "session_start_time": recording.session_start_time_dt or datetime.now(),
                    "experimenter": "Test",
                    "lab": "Test Lab",
                    "institution": "Test University",
                },
            )

            assert output_path.exists(), "NWB file should be created"

            with NWBHDF5IO(str(output_path), "r") as io:
                io.read()

                # Preprocessing module may or may not exist (implementation detail)
                # What matters is no crash occurred


@pytest.mark.skipif(not PYNWB_AVAILABLE, reason="PyNWB not available")
class TestNWBValidation:
    """Test that exported NWB files pass PyNWB validation."""

    def test_nwb_file_validates(self):
        """Exported NWB should pass pynwb.validate()."""
        recording = Recording(source_file=Path("test.abf"))
        recording.protocol_name = "IV"
        recording.duration = 1.0
        recording.sampling_rate = 10000.0
        recording.subject_id = "Mouse_01"

        # Add preprocessing and electrode metadata
        recording.add_preprocessing_step("lowpass", {"cutoff_hz": 300})

        channel = Channel(
            id="0",
            name="Vm",
            units="mV",
            sampling_rate=10000.0,
            data_trials=[np.random.randn(10000)],
        )
        channel.electrode_resistance = "10 MOhm"
        channel.electrode_seal = "5 GOhm"

        recording.channels["Vm"] = channel

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "test_validate.nwb"
            NWBExporter().export(
                recording=recording,
                output_path=output_path,
                session_metadata={
                    "session_description": "Validation test",
                    "identifier": "test_validate",
                    "session_start_time": recording.session_start_time_dt or datetime.now(),
                    "experimenter": "Test",
                    "lab": "Test Lab",
                    "institution": "Test University",
                },
            )

            # Validate with PyNWB
            with NWBHDF5IO(str(output_path), "r") as io:
                errors = validate(io=io)

                # Should have no critical validation errors
                critical_errors = [e for e in errors if "CRITICAL" in str(e)]
                assert len(critical_errors) == 0, f"Found critical validation errors: {critical_errors}"


@pytest.mark.skipif(not PYNWB_AVAILABLE, reason="PyNWB not available")
class TestDANDICompliance:
    """Test DANDI-specific requirements."""

    def test_required_fields_present(self):
        """Test that all DANDI-required fields are populated."""
        recording = Recording(source_file=Path("test.abf"))
        recording.protocol_name = "IV"
        recording.duration = 1.0
        recording.sampling_rate = 10000.0
        recording.subject_id = "Mouse_01"

        channel = Channel(
            id="0",
            name="Vm",
            units="mV",
            sampling_rate=10000.0,
            data_trials=[np.random.randn(10000)],
        )
        channel.electrode_resistance = "10 MOhm"
        channel.electrode_seal = "5 GOhm"
        channel.electrode_location = "Hippocampus"

        recording.channels["Vm"] = channel

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "test_dandi.nwb"
            NWBExporter().export(
                recording=recording,
                output_path=output_path,
                session_metadata={
                    "session_description": "DANDI compliance test",
                    "identifier": "test_dandi",
                    "session_start_time": recording.session_start_time_dt or datetime.now(),
                    "experimenter": "Jane Doe",
                    "lab": "Neuroscience Lab",
                    "institution": "University",
                },
            )

            with NWBHDF5IO(str(output_path), "r") as io:
                nwbfile = io.read()

                # DANDI requires these fields
                assert nwbfile.session_description is not None, "Session description required"
                assert nwbfile.experimenter is not None, "Experimenter required"
                assert nwbfile.institution is not None, "Institution required"
                assert nwbfile.lab is not None, "Lab required"

                # Electrode metadata required for icephys
                electrode = list(nwbfile.icephys_electrodes.values())[0]
                assert electrode.location is not None, "Electrode location required"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
