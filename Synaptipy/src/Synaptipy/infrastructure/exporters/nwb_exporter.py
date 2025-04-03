"""
Exporter for saving Recording data to the NWB:N 2.0 format.
"""

import logging
from pathlib import Path
from datetime import datetime, timezone
import uuid
from typing import Dict, Any, Optional

import numpy as np
from pynwb import NWBHDF5IO, NWBFile
from pynwb.icephys import PatchClampSeries # More specific type if applicable

# Assuming Recording and Channel are imported correctly relative to this file's location
try:
    from ...core.data_model import Recording, Channel
    from ...shared.error_handling import ExportError # Assuming ExportError exists
except ImportError:
    # Allow script to be imported even if package structure isn't fully resolved
    # Add placeholder classes if needed for standalone testing/linting
    class Recording: pass
    class Channel: pass
    class ExportError(IOError): pass


log = logging.getLogger(__name__)

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
                              'experimenter', 'lab', 'institution', etc.

        Raises:
            ExportError: If any error occurs during the NWB file creation or writing.
            ValueError: If essential session_metadata is missing.
        """
        log.info(f"Starting NWB export for recording: {recording.source_file.name}")
        log.debug(f"Output path: {output_path}")
        log.debug(f"Session metadata received: {session_metadata}")

        # --- Validate Metadata & Prepare NWBFile ---
        required_keys = ['session_description', 'identifier', 'session_start_time']
        if not all(key in session_metadata for key in required_keys):
            missing = [key for key in required_keys if key not in session_metadata]
            raise ValueError(f"Missing required NWB session metadata: {missing}")

        start_time = session_metadata['session_start_time']
        if not isinstance(start_time, datetime):
             # Attempt conversion if it's a string? For now, require datetime.
             raise ValueError("session_start_time must be a datetime object.")
        # Ensure timezone awareness (important for NWB)
        if start_time.tzinfo is None:
            log.warning("NWB session_start_time is timezone naive. Assuming local timezone.")
            # Or force UTC: start_time = start_time.replace(tzinfo=timezone.utc)
            # Or use system's local timezone:
            try:
                import tzlocal
                start_time = start_time.replace(tzinfo=tzlocal.get_localzone())
            except ImportError:
                 log.warning("tzlocal not installed. NWB time may be ambiguous. Using system default.")
                 # Fallback: no explicit timezone, NWB might default or warn
                 start_time = start_time # Keep naive, rely on pynwb default behavior/warnings


        try:
            nwbfile = NWBFile(
                session_description=session_metadata['session_description'],
                identifier=session_metadata['identifier'],
                session_start_time=start_time,
                experimenter=session_metadata.get('experimenter'), # Optional
                lab=session_metadata.get('lab'),                   # Optional
                institution=session_metadata.get('institution'),       # Optional
                # Add other relevant metadata from session_metadata or recording.metadata
                notes=f"Original file: {recording.source_file.name}\n"
                      f"Source sampling rate: {recording.sampling_rate} Hz\n"
                      f"Protocol: {recording.protocol_name}\n"
                      f"{recording.metadata.get('notes', '')}", # Append existing notes
                session_id=session_metadata.get('session_id'), # Optional
                # file_create_date=datetime.now(timezone.utc) # NWB adds this automatically
            )
            log.debug("NWBFile object created.")

            # --- Device and Electrodes (Placeholders) ---
            # For real data, you'd fetch this from headers or user input
            device = nwbfile.create_device(name='Amplifier', description='Electrophysiology amplifier (details unknown)', manufacturer='Unknown')
            electrode_group = nwbfile.create_electrode_group(
                name='electrode_group_0',
                description='Placeholder electrode group',
                location='Unknown',
                device=device
            )

            # --- Add Channels as TimeSeries ---
            log.info(f"Processing {recording.num_channels} channels...")
            for chan_id, channel in recording.channels.items():
                if not channel.data_trials:
                    log.warning(f"Skipping channel '{channel.name}' (ID: {chan_id}): No data trials found.")
                    continue

                # Create a placeholder electrode table entry for this channel
                # Ideally, electrode info comes from metadata
                electrode_table_region = nwbfile.create_electrode_table_region(
                     region=[len(nwbfile.electrodes) if nwbfile.electrodes else 0], # Index of the electrode to add
                     description=f"Electrode for channel {channel.name}"
                )
                # Add electrode if it doesn't exist (simplified - assumes one electrode per channel)
                # For multi-electrode arrays, electrode mapping is more complex.
                nwbfile.add_electrode(
                    id=int(chan_id) if chan_id.isdigit() else len(nwbfile.electrodes), # Try using numeric ID if possible
                    x=np.nan, y=np.nan, z=np.nan, # Coordinates unknown
                    imp=np.nan, # Impedance unknown
                    location=electrode_group.location,
                    filtering='unknown',
                    group=electrode_group,
                )

                log.debug(f"Processing channel '{channel.name}' (ID: {chan_id}) with {channel.num_trials} trial(s).")
                # Store each trial as a separate TimeSeries
                for trial_idx, trial_data in enumerate(channel.data_trials):
                    # Determine starting time or timestamps for this specific trial
                    # Simple approach: use rate and assume trials are segments starting at channel.t_start
                    # More robust: If neo provides segment start times relative to block start, use those.
                    # For now, just use rate. t_start is relative to NWBFile session_start_time.
                    # This assumes channel.t_start IS relative to session start. If not, adjustment needed.
                    ts_name = f"{channel.name}_trial_{trial_idx}"
                    ts_description = f"Raw data for channel '{channel.name}' (ID: {chan_id}), trial {trial_idx}."

                    # Use PatchClampSeries if appropriate metadata exists, otherwise generic TimeSeries
                    # Example check: if channel looks like voltage clamp data, etc.
                    # Here we use PatchClampSeries as a common type for intracellular.
                    # If metadata isn't present, some fields might be default/None.
                    time_series = PatchClampSeries(
                        name=ts_name,
                        description=ts_description,
                        data=trial_data,
                        unit=channel.units if channel.units else 'unknown',
                        electrode=electrode_table_region, # Link to the electrode table region
                        gain=np.nan, # Gain unknown from basic model
                        stimulus_description="Stimulus details unknown", # Need stimulus info
                        sweep_number=np.uint64(trial_idx), # Add sweep number if applicable
                        rate=channel.sampling_rate,
                        starting_time=channel.t_start # Assumes t_start is relative to session_start_time
                        # Alternatively use timestamps=channel.get_time_vector(trial_idx) if absolute times needed
                    )

                    # Add to acquisition (for raw data) or stimulus/processing modules if appropriate
                    nwbfile.add_acquisition(time_series)
                    log.debug(f"Added TimeSeries: {ts_name}")

            # --- Write NWB File ---
            log.info(f"Writing NWB data to: {output_path}")
            with NWBHDF5IO(str(output_path), 'w') as io:
                io.write(nwbfile)
            log.info("NWB export completed successfully.")

        except ValueError as ve:
             log.error(f"Metadata validation error during NWB export: {ve}")
             raise ve # Re-raise validation errors
        except ImportError:
            log.error("pynwb library not found. Please install it (`pip install pynwb`).")
            raise ExportError("pynwb library not found.")
        except Exception as e:
            log.error(f"Error during NWB export process: {e}", exc_info=True)
            raise ExportError(f"Failed to export to NWB: {e}") from e