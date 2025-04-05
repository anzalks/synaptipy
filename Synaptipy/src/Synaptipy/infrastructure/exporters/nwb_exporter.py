# src/Synaptipy/infrastructure/exporters/nwb_exporter.py
# -*- coding: utf-8 -*-
"""
Exporter for saving Recording data to the NWB:N 2.0 format.
Utilizes metadata extracted by NeoAdapter and stored in data_model objects.
"""
__author__ = "Anzal KS"
__copyright__ = "Copyright 2024-, Anzal KS"
__maintainer__ = "Anzal KS"
__email__ = "anzalks@ncbs.res.in"

import logging
from pathlib import Path
from datetime import datetime, timezone
import uuid
from typing import Dict, Any, Optional

import numpy as np
# Ensure pynwb is installed: pip install pynwb
try:
    from pynwb import NWBHDF5IO, NWBFile
    from pynwb.icephys import PatchClampSeries, IntracellularElectrode
    PYNWB_AVAILABLE = True
except ImportError:
    # Define dummy classes if pynwb not installed, so rest of file can be parsed
    log_fallback = logging.getLogger(__name__)
    log_fallback.error("pynwb library not found. NWB Export functionality will be disabled. Please install it (`pip install pynwb`).")
    PYNWB_AVAILABLE = False
    class NWBHDF5IO: pass
    class NWBFile: pass
    class PatchClampSeries: pass
    class IntracellularElectrode: pass


# Import from our package structure using relative paths
try:
    from ...core.data_model import Recording, Channel
    from ...shared.error_handling import ExportError
except ImportError:
    # Fallback for standalone execution or if package structure isn't fully resolved
    log_fallback = logging.getLogger(__name__)
    log_fallback.warning("Could not perform relative imports for data_model/error_handling. Using placeholders.")
    class Recording: pass
    class Channel: pass
    class ExportError(IOError): pass

# Configure logging (use specific logger for this module)
log = logging.getLogger('Synaptipy.infrastructure.exporters.nwb_exporter')


class NWBExporter:
    """Handles exporting Recording domain objects to NWB files."""

    def export(self, recording: Recording, output_path: Path, session_metadata: Dict[str, Any]):
        """
        Exports the given Recording object to an NWB file.

        Args:
            recording: The Recording object containing data and metadata.
            output_path: The Path object where the .nwb file will be saved.
            session_metadata: A dictionary containing user-provided or default
                              metadata required for NWBFile creation. Expected keys:
                              'session_description', 'identifier', 'session_start_time',
                              plus optional 'experimenter', 'lab', 'institution', 'session_id'.

        Raises:
            ExportError: If any error occurs during the NWB file creation or writing,
                         or if pynwb is not installed.
            ValueError: If essential session_metadata is missing or invalid.
            FileNotFoundError: If the recording source file path is invalid (should be checked earlier).
            TypeError: If the recording object is not of the expected type.
        """
        if not PYNWB_AVAILABLE:
            raise ExportError("pynwb library is not installed. Cannot export to NWB.")

        log.info(f"Starting NWB export for recording from: {getattr(recording, 'source_file', 'Unknown Source').name}")
        log.debug(f"Output path: {output_path}")
        log.debug(f"Session metadata received: {session_metadata}")

        # --- Validate Recording Object ---
        if not isinstance(recording, Recording):
            raise TypeError("Invalid 'recording' object provided to NWBExporter.")
        if not hasattr(recording, 'channels') or not isinstance(recording.channels, dict):
             raise ValueError("Recording object is missing 'channels' dictionary or is not a dictionary.")
        source_file_name = getattr(recording, 'source_file', Path("Unknown")).name

        # --- Validate Metadata & Prepare NWBFile ---
        required_keys = ['session_description', 'identifier', 'session_start_time']
        missing_keys = [key for key in required_keys if key not in session_metadata or not session_metadata[key]]
        if missing_keys:
            raise ValueError(f"Missing required NWB session metadata: {missing_keys}")

        start_time = session_metadata['session_start_time']
        if not isinstance(start_time, datetime):
             raise ValueError(f"session_start_time must be a datetime object, got {type(start_time)}.")

        # Ensure session_start_time is timezone-aware (CRITICAL for NWB)
        if start_time.tzinfo is None:
            log.warning("NWB session_start_time is timezone naive. Attempting to localize.")
            try:
                import tzlocal
                local_tz = tzlocal.get_localzone()
                start_time = start_time.replace(tzinfo=local_tz)
                log.info(f"Applied local timezone: {local_tz.key}")
            except Exception as tz_err:
                 log.error(f"Failed to apply local timezone using tzlocal ({tz_err}). Forcing UTC.")
                 start_time = start_time.replace(tzinfo=timezone.utc) # Fallback to UTC
        else:
            log.info(f"Session start time already timezone-aware: {start_time.tzinfo}")


        # --- Create NWB File Object ---
        try:
            # Extract optional fields safely
            experimenter = session_metadata.get('experimenter')
            lab = session_metadata.get('lab')
            institution = session_metadata.get('institution')
            session_id = session_metadata.get('session_id') # Optional user-defined session ID

            # Construct notes from recording metadata safely
            notes_list = [f"Original file: {source_file_name}"]
            if hasattr(recording, 'sampling_rate') and recording.sampling_rate:
                notes_list.append(f"Source sampling rate: {recording.sampling_rate:.2f} Hz")
            if hasattr(recording, 'protocol_name') and recording.protocol_name:
                notes_list.append(f"Protocol: {recording.protocol_name}")
            if hasattr(recording, 'metadata') and isinstance(recording.metadata, dict):
                 rec_notes = recording.metadata.get('notes')
                 if rec_notes: notes_list.append(str(rec_notes))
            notes = "\n".join(notes_list)

            nwbfile = NWBFile(
                session_description=session_metadata['session_description'],
                identifier=session_metadata['identifier'], # Should be unique UUID or similar
                session_start_time=start_time, # Must be timezone-aware datetime
                experimenter=experimenter if experimenter else None, # List of strings or None
                lab=lab if lab else None,
                institution=institution if institution else None,
                notes=notes,
                session_id=session_id if session_id else None,
                # file_create_date is added automatically by NWB
            )
            log.debug(f"NWBFile object created with identifier: {nwbfile.identifier}")

            # --- Device ---
            device_name = recording.metadata.get('device_name', 'Amplifier')
            device_descr = recording.metadata.get('device_description', 'Electrophysiology amplifier (details unknown)')
            device_manu = recording.metadata.get('device_manufacturer', 'Unknown')
            device = nwbfile.devices.get(device_name)
            if device is None:
                 device = nwbfile.create_device(name=device_name, description=device_descr, manufacturer=device_manu)
            log.debug(f"Using device: {device.name}")

            # --- Add Channels as PatchClampSeries ---
            num_channels_processed = 0
            if not recording.channels:
                 log.warning("Recording contains no channels to export.")
            else:
                 log.info(f"Processing {len(recording.channels)} channels...")

            for chan_id, channel in recording.channels.items():
                if not isinstance(channel, Channel):
                    log.warning(f"Skipping invalid channel object for ID '{chan_id}' (type: {type(channel)}).")
                    continue
                if not hasattr(channel, 'data_trials') or not channel.data_trials or not isinstance(channel.data_trials, list):
                    log.warning(f"Skipping channel '{getattr(channel, 'name', chan_id)}' (ID: {chan_id}): No valid data trials found.")
                    continue

                log.debug(f"Processing channel '{channel.name}' (ID: {chan_id}) with {channel.num_trials} trial(s).")

                # --- Create IntracellularElectrode object ---
                electrode_name = f"electrode_{chan_id}" # Use a consistent, unique name

                # --- Check for existing electrode by name (optional but safer) ---
                # Access existing electrodes via nwbfile.ic_electrodes if added (check first)
                ic_electrode: Optional[IntracellularElectrode] = None
                if electrode_name in nwbfile.ic_electrodes: # Check if the attribute exists and name is in it
                    ic_electrode = nwbfile.ic_electrodes[electrode_name]
                    log.warning(f"Intracellular electrode '{electrode_name}' already exists. Reusing.")

                # If not found, create it
                if ic_electrode is None:
                    ic_description = getattr(channel, 'electrode_description', f"Intracellular electrode for {channel.name}")
                    ic_location = getattr(channel, 'electrode_location', 'Unknown')
                    ic_filtering = getattr(channel, 'electrode_filtering', 'unknown')
                    # TODO: Parse resistance/seal if stored as strings (e.g., "10 MOhm" -> 10e6)
                    ic_resistance = None
                    ic_seal = None

                    try:
                        # Instantiate IntracellularElectrode directly
                        ic_electrode = IntracellularElectrode(
                            name=electrode_name,
                            description=str(ic_description) if ic_description else "N/A",
                            device=device, # Link to device
                            location=str(ic_location) if ic_location else "Unknown",
                            filtering=str(ic_filtering) if ic_filtering else "unknown",
                            resistance=ic_resistance, # Expects float in Ohms or None
                            seal=ic_seal            # Expects float in Ohms or None
                        )
                        # Add the created electrode to the NWB file
                        nwbfile.add_ic_electrode(ic_electrode)
                        log.debug(f"Created and added IntracellularElectrode: {electrode_name}")
                    except Exception as e_elec:
                         log.error(f"Failed to create or add IntracellularElectrode '{electrode_name}': {e_elec}", exc_info=True)
                         continue # Skip processing trials for this channel if electrode fails


                # --- Create PatchClampSeries for each trial ---
                for trial_idx, trial_data in enumerate(channel.data_trials):
                    if not isinstance(trial_data, np.ndarray) or trial_data.ndim != 1 or trial_data.size == 0:
                        log.warning(f"Skipping invalid trial data for Ch '{channel.name}', Trial {trial_idx} (type: {type(trial_data)}, shape: {getattr(trial_data, 'shape', 'N/A')}).")
                        continue

                    ts_name = f"{channel.name}_trial_{trial_idx:03d}" # Padded index
                    ts_description = f"Raw data for channel '{channel.name}' (ID: {chan_id}), trial {trial_idx+1}." # User-friendly 1-based index
                    channel_units = getattr(channel, 'units', 'unknown')
                    channel_sampling_rate = getattr(channel, 'sampling_rate', recording.sampling_rate) # Use channel rate if available
                    channel_t_start = getattr(channel, 't_start', 0.0) # Relative to recording start

                    if channel_sampling_rate is None or channel_sampling_rate <= 0:
                        log.error(f"Invalid sampling rate ({channel_sampling_rate}) for Ch '{channel.name}', Trial {trial_idx}. Skipping trial.")
                        continue

                    # Assume data is already in physical units from neo/adapter
                    ts_gain = 1.0
                    ts_offset = getattr(channel, 'electrode_offset', np.nan)
                    ts_offset = 0.0 if np.isnan(ts_offset) else float(ts_offset) # Use 0.0 if NaN

                    try:
                        time_series = PatchClampSeries(
                            name=ts_name,
                            description=ts_description,
                            data=trial_data,
                            unit=str(channel_units) if channel_units else 'unknown',
                            electrode=ic_electrode, # Link to the IntracellularElectrode object
                            gain=ts_gain,
                            offset=ts_offset,
                            stimulus_description="Stimulus details not available", # Placeholder
                            sweep_number=np.uint64(trial_idx),
                            rate=float(channel_sampling_rate),
                            starting_time=float(channel_t_start) # Relative to NWBFile session_start_time
                        )
                        nwbfile.add_acquisition(time_series) # Add raw data to acquisition
                        log.debug(f"Added PatchClampSeries: {ts_name} to acquisition.")
                    except Exception as e_ts:
                        log.error(f"Failed to create or add PatchClampSeries '{ts_name}': {e_ts}", exc_info=True)
                        # Continue processing other trials/channels

                num_channels_processed += 1 # Increment count only after successful channel processing


            if num_channels_processed == 0:
                 log.warning("No valid channel data was processed for export. NWB file may be empty.")
                 # Consider if an error should be raised here if no channels are exported

            # --- Write NWB File ---
            log.info(f"Writing NWB data to: {output_path}")
            output_path.parent.mkdir(parents=True, exist_ok=True) # Ensure directory exists
            with NWBHDF5IO(str(output_path), 'w') as io:
                io.write(nwbfile)
            log.info("NWB export completed successfully.")

        except ValueError as ve: # Catch specific ValueErrors (e.g., metadata)
             log.error(f"Data validation error during NWB export: {ve}")
             raise ExportError(f"Data validation error: {ve}") from ve
        except TypeError as te: # Catch specific TypeErrors (e.g., wrong object type)
             log.error(f"Type error during NWB export: {te}", exc_info=True) # Add traceback for TypeErrors
             raise ExportError(f"Type error during export: {te}") from te
        except Exception as e: # Catch any other unexpected errors
            log.error(f"Unexpected error during NWB export process: {e}", exc_info=True)
            # Wrap generic exceptions in ExportError for consistent handling upstream
            raise ExportError(f"Failed to export to NWB: {e}") from e