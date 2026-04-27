# src/Synaptipy/infrastructure/exporters/nwb_exporter.py
# -*- coding: utf-8 -*-
"""
Exporter for saving Recording data to the NWB:N 2.0 format.
Utilizes metadata extracted by NeoAdapter and stored in data_model objects.
"""

__author__ = "Anzal K Shahul"
__copyright__ = "Copyright 2024-, Anzal K Shahul"
__maintainer__ = "Anzal K Shahul"
__email__ = "anzalks@ncbs.res.in"

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

import numpy as np

# Ensure pynwb is installed: pip install pynwb
try:  # noqa: C901
    from pynwb import NWBHDF5IO, NWBFile
    from pynwb.icephys import (
        CurrentClampSeries,
        CurrentClampStimulusSeries,
        IntracellularElectrode,
        PatchClampSeries,
        VoltageClampSeries,
        VoltageClampStimulusSeries,
    )

    PYNWB_AVAILABLE = True
except ImportError:
    # Define sentinel classes if pynwb not installed, so rest of file can be parsed.
    # The export() method checks PYNWB_AVAILABLE and raises ExportError before
    # any of these classes would be instantiated.
    log_fallback = logging.getLogger(__name__)
    log_fallback.warning(
        "pynwb library not found. NWB Export functionality will be disabled. " "Install it with: pip install pynwb"
    )
    PYNWB_AVAILABLE = False

    class NWBHDF5IO:  # type: ignore[no-redef]
        """Sentinel: pynwb not installed."""

        def __init__(self, *args, **kwargs):
            raise ImportError("pynwb is required for NWB export. Install with: pip install pynwb")

    class NWBFile:  # type: ignore[no-redef]
        """Sentinel: pynwb not installed."""

        def __init__(self, *args, **kwargs):
            raise ImportError("pynwb is required for NWB export. Install with: pip install pynwb")

    class PatchClampSeries:  # type: ignore[no-redef]
        """Sentinel: pynwb not installed."""

        def __init__(self, *args, **kwargs):
            raise ImportError("pynwb is required for NWB export. Install with: pip install pynwb")

    class CurrentClampSeries:  # type: ignore[no-redef]
        """Sentinel: pynwb not installed."""

        def __init__(self, *args, **kwargs):
            raise ImportError("pynwb is required for NWB export. Install with: pip install pynwb")

    class VoltageClampSeries:  # type: ignore[no-redef]
        """Sentinel: pynwb not installed."""

        def __init__(self, *args, **kwargs):
            raise ImportError("pynwb is required for NWB export. Install with: pip install pynwb")

    class CurrentClampStimulusSeries:  # type: ignore[no-redef]
        """Sentinel: pynwb not installed."""

        def __init__(self, *args, **kwargs):
            raise ImportError("pynwb is required for NWB export. Install with: pip install pynwb")

    class VoltageClampStimulusSeries:  # type: ignore[no-redef]
        """Sentinel: pynwb not installed."""

        def __init__(self, *args, **kwargs):
            raise ImportError("pynwb is required for NWB export. Install with: pip install pynwb")

    class IntracellularElectrode:  # type: ignore[no-redef]
        """Sentinel: pynwb not installed."""

        def __init__(self, *args, **kwargs):
            raise ImportError("pynwb is required for NWB export. Install with: pip install pynwb")


# Import from our package structure using relative paths
try:
    from ...core.data_model import Channel, Recording
    from ...shared.error_handling import ExportError
except ImportError:
    # Fallback for standalone execution or if package structure isn't fully resolved
    log_fallback = logging.getLogger(__name__)
    log_fallback.warning("Could not perform relative imports for data_model/error_handling. Using placeholders.")

    class Recording:  # type: ignore[no-redef]
        """Sentinel: package imports not resolved."""

        pass

    class Channel:  # type: ignore[no-redef]
        """Sentinel: package imports not resolved."""

        pass

    class ExportError(IOError):  # type: ignore[no-redef]
        """Sentinel: package imports not resolved."""

        pass


# Configure logging (use specific logger for this module)
log = logging.getLogger(__name__)


class NWBExporter:
    """Handles exporting Recording domain objects to NWB files."""

    def export(self, recording: Recording, output_path: Path, session_metadata: Dict[str, Any]):  # noqa: C901
        """
        Exports the given Recording object to an NWB file.

        Args:
            recording: The Recording object containing data and metadata.
            output_path: The Path object where the .nwb file will be saved.
            session_metadata: A dictionary containing user-provided or default
                              metadata required for NWBFile creation. Expected keys:
                              'session_description', 'identifier', 'session_start_time',
                              plus optional 'experimenter', 'lab', 'institution', 'session_id',
                              and Subject/Device/Electrode info.

        Raises:
            ExportError: If any error occurs during the NWB file creation or writing.
        """
        if not PYNWB_AVAILABLE:
            raise ExportError("pynwb library is not installed. Cannot export to NWB.")

        log.debug(f"Starting NWB export for recording from: {getattr(recording, 'source_file', 'Unknown Source').name}")
        log.debug(f"Output path: {output_path}")

        # --- Validate Recording Object ---
        if not isinstance(recording, Recording):
            raise TypeError("Invalid 'recording' object provided to NWBExporter.")
        if not hasattr(recording, "channels") or not isinstance(recording.channels, dict):
            raise ValueError("Recording object is missing 'channels' dictionary or is not a dictionary.")

        # --- Inject required metadata defaults for DANDI compliance ---
        # Subject ID and Species are required by NWB/DANDI validators.
        if not session_metadata.get("subject_id"):
            session_metadata = dict(session_metadata)  # avoid mutating caller's dict
            session_metadata.setdefault("subject_id", "unknown_subject")
            log.warning("NWB export: 'subject_id' not provided; defaulting to 'unknown_subject'.")
        if not session_metadata.get("species"):
            session_metadata.setdefault("species", "unknown species")
            log.warning("NWB export: 'species' not provided; defaulting to 'unknown species'.")
        if not session_metadata.get("device_name"):
            session_metadata = dict(session_metadata)
            session_metadata.setdefault("device_name", "Amplifier")
            log.warning("NWB export: 'device_name' not provided; defaulting to 'Amplifier'.")

        # --- Validate Metadata & Prepare NWBFile ---
        required_keys = ["session_description", "identifier", "session_start_time"]
        missing_keys = [key for key in required_keys if key not in session_metadata or not session_metadata[key]]
        if missing_keys:
            raise ValueError(f"Missing required NWB session metadata: {missing_keys}")

        start_time = session_metadata["session_start_time"]
        if not isinstance(start_time, datetime):
            raise ValueError(f"session_start_time must be a datetime object, got {type(start_time)}.")

        # Ensure session_start_time is timezone-aware
        if start_time.tzinfo is None:
            log.warning("NWB session_start_time is timezone naive. Attempting to localize.")
            try:
                import tzlocal

                local_tz = tzlocal.get_localzone()
                start_time = start_time.replace(tzinfo=local_tz)
            except Exception:
                start_time = start_time.replace(tzinfo=timezone.utc)

        # --- Create Subject Object ---
        subject = None
        # Extract subject specific keys (assuming flattened structure from dialog or specific keys)
        subj_id = session_metadata.get("subject_id")
        if subj_id:
            try:
                from pynwb.file import Subject

                subject = Subject(
                    subject_id=subj_id,
                    species=session_metadata.get("species"),
                    sex=session_metadata.get("sex", "U"),  # Default Unknown
                    age=session_metadata.get("age"),
                    description=session_metadata.get("subject_description"),
                    genotype=session_metadata.get("genotype"),
                    weight=session_metadata.get("weight"),
                )
                log.debug(f"Created NWB Subject object for ID: {subj_id}")
            except Exception as e_subj:
                log.error(f"Failed to create Subject object: {e_subj}")
                # Continue without subject if it fails, or raise? Proceeding is safer for user exp.

        # --- Create NWB File Object ---
        try:
            # Construct notes
            notes_list = []
            if session_metadata.get("notes"):
                notes_list.append(session_metadata["notes"])

            # Append technical details to notes
            source_file_name = getattr(recording, "source_file", Path("Unknown")).name
            notes_list.append(f"Original file: {source_file_name}")
            if hasattr(recording, "protocol_name") and recording.protocol_name:
                notes_list.append(f"Protocol: {recording.protocol_name}")

            notes_combined = "\n".join(notes_list)

            nwbfile = NWBFile(
                session_description=session_metadata["session_description"],
                identifier=session_metadata["identifier"],
                session_start_time=start_time,
                experimenter=session_metadata.get("experimenter"),
                lab=session_metadata.get("lab"),
                institution=session_metadata.get("institution"),
                session_id=session_metadata.get("session_id"),
                notes=notes_combined,
                subject=subject,  # Attach Subject
            )

            # --- Device ---
            # Prefer metadata from dialog, fallback to recording metadata, then defaults
            dev_name = session_metadata.get("device_name") or recording.metadata.get("device_name") or "Amplifier"
            dev_descr = (
                session_metadata.get("device_description")
                or recording.metadata.get("device_description")
                or "Electrophysiology amplifier"
            )
            dev_manu = (
                session_metadata.get("device_manufacturer")
                or recording.metadata.get("device_manufacturer")
                or "Unknown"
            )

            device = nwbfile.create_device(name=dev_name, description=dev_descr, manufacturer=dev_manu)
            log.debug(f"Using device: {device.name}")

            # --- Electrode Defaults ---
            # Defaults from dialog
            elec_desc_def = session_metadata.get("electrode_description_default", "Intracellular Electrode")
            elec_loc_def = session_metadata.get("electrode_location_default", "Unknown")
            elec_filt_def = session_metadata.get("electrode_filtering_default", "unknown")

            # --- Add Channels ---
            num_channels_processed = 0
            if not recording.channels:
                log.warning("Recording contains no channels to export.")

            for chan_id, channel in recording.channels.items():
                if not isinstance(channel, Channel):
                    continue
                if not getattr(channel, "data_trials", None):
                    continue

                log.debug(f"Processing channel '{channel.name}' (ID: {chan_id})")

                # --- Create/Get IntracellularElectrode ---
                electrode_name = f"electrode_{chan_id}"

                # Check for specific channel overrides (if any in future) -> currently use defaults from dialog
                # unless channel object has specific metadata populated
                ic_desc = getattr(channel, "electrode_description", None) or elec_desc_def
                ic_loc = getattr(channel, "electrode_location", None) or elec_loc_def
                ic_filt = getattr(channel, "electrode_filtering", None) or elec_filt_def

                # Since we iterate, check if electrode exists (though unique per channel usually)
                if electrode_name in nwbfile.icephys_electrodes:
                    ic_electrode = nwbfile.icephys_electrodes[electrode_name]
                else:
                    try:
                        ic_electrode = nwbfile.create_icephys_electrode(
                            name=electrode_name,
                            description=str(ic_desc),
                            device=device,
                            location=str(ic_loc),
                            filtering=str(ic_filt),
                        )
                    except Exception as e_elec:
                        log.error(f"Failed to create electrode '{electrode_name}': {e_elec}")
                        continue

                # --- Create PatchClampSeries ---
                for trial_idx, trial_data in enumerate(channel.data_trials):
                    if trial_data.size == 0:
                        continue

                    ts_name = f"{channel.name}_trial_{trial_idx:03d}"
                    ts_desc = f"Raw data for channel '{channel.name}', trial {trial_idx + 1}"

                    # Units & Verification
                    # If units imply voltage -> CurrentClampSeries (measures V)
                    # If units imply current -> VoltageClampSeries (measures I)
                    # For now, generic PatchClampSeries is safer if mode unknown,
                    # BUT PyNWB encourages specific if possible.
                    # NWB: VoltageClampSeries (records Current, units=Amps). CurrentClampSeries (records Voltage,
                    # units=Volts).

                    units = getattr(channel, "units", "unknown").lower()

                    # --- SI unit conversion and series class selection ---
                    # NWB best practice: store data in SI (volts, amperes).
                    # Synaptipy/Neo typically keeps data in mV or pA.
                    # We convert to SI and record the conversion factor.
                    export_data = trial_data.copy().astype(np.float64)
                    conversion = 1.0

                    # Select the appropriate NWB series class based on
                    # channel units, which indicate the clamp mode:
                    #   voltage units (mV, V) → CurrentClampSeries
                    #   current units (pA, nA, A) → VoltageClampSeries
                    SeriesClass = PatchClampSeries  # fallback

                    if units in ("mv", "millivolt", "millivolts"):
                        export_data = export_data * 1e-3  # mV → V
                        conversion = 1e-3
                        final_units = "volts"
                        SeriesClass = CurrentClampSeries
                    elif units in ("v", "volt", "volts"):
                        final_units = "volts"
                        SeriesClass = CurrentClampSeries
                    elif units in ("pa", "picoampere", "picoamperes"):
                        export_data = export_data * 1e-12  # pA → A
                        conversion = 1e-12
                        final_units = "amperes"
                        SeriesClass = VoltageClampSeries
                    elif units in ("na", "nanoampere", "nanoamperes"):
                        export_data = export_data * 1e-9  # nA → A
                        conversion = 1e-9
                        final_units = "amperes"
                        SeriesClass = VoltageClampSeries
                    elif units in ("a", "ampere", "amperes"):
                        final_units = "amperes"
                        SeriesClass = VoltageClampSeries
                    else:
                        final_units = getattr(channel, "units", "unknown")
                        log.warning(
                            "Unrecognised channel units '%s' for '%s'. " "Using generic PatchClampSeries.",
                            units,
                            channel.name,
                        )

                    channel_rate = getattr(channel, "sampling_rate", recording.sampling_rate)

                    try:
                        series_kwargs = dict(
                            name=ts_name,
                            description=ts_desc,
                            data=export_data,
                            unit=final_units,
                            electrode=ic_electrode,
                            rate=float(channel_rate) if channel_rate else 1000.0,
                            starting_time=float(getattr(channel, "t_start", 0.0)),
                            gain=1.0,
                            sweep_number=np.uint64(trial_idx),
                            conversion=conversion,
                        )
                        time_series = SeriesClass(**series_kwargs)
                        nwbfile.add_acquisition(time_series)

                        # --- Relational linking via IntracellularRecordingsTable ---
                        # Links each acquired series to its electrode in the NWB
                        # icephys table.  stimulus=None documents that the command
                        # waveform was not captured (valid per NWB:N 2.0 spec).
                        try:
                            nwbfile.add_intracellular_recording(
                                electrode=ic_electrode,
                                response=time_series,
                                response_start_index=0,
                                response_index_count=int(len(export_data)),
                                stimulus=None,
                            )
                        except Exception as e_icr:
                            log.debug(
                                "Could not add intracellular_recording entry for '%s': %s",
                                ts_name,
                                e_icr,
                            )
                    except Exception as e_ts:
                        log.error(f"Failed to add series '{ts_name}': {e_ts}")
                        continue

                num_channels_processed += 1

            if num_channels_processed == 0:
                log.warning("No valid channels exported.")

            # --- Write File ---
            log.debug(f"Writing NWB to: {output_path}")
            with NWBHDF5IO(str(output_path), "w") as io:
                io.write(nwbfile)

            # --- pynwb post-write validation ---
            # Validate the written file to flag DANDI-compliance issues.
            # Done after the write so that container_source is already set
            # on the nwbfile object (avoids "Cannot change container_source" error).
            try:
                from pynwb import validate as pynwb_validate

                with NWBHDF5IO(str(output_path), "r") as _io_val:
                    _validation_errors = pynwb_validate(io=_io_val)

                if _validation_errors:
                    err_lines = "\n  ".join(str(e) for e in _validation_errors)
                    log.warning(
                        "NWB validation found %d issue(s) — file may not be DANDI-compliant:\n  %s",
                        len(_validation_errors),
                        err_lines,
                    )
                else:
                    log.info("NWB validation passed (0 errors).")
            except ImportError:
                log.debug("pynwb.validate not available; skipping post-write validation.")
            except Exception as exc_val:
                log.warning("NWB validation step raised an unexpected error: %s", exc_val)

            log.info("NWB export complete.")

        except Exception as e:
            log.error(f"NWB Export failed: {e}", exc_info=True)
            raise ExportError(f"Failed to export to NWB: {e}") from e
