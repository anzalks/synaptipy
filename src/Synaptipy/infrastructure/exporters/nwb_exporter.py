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
                              plus optional 'experimenter', 'lab', 'institution', 'session_id',
                              and Subject/Device/Electrode info.

        Raises:
            ExportError: If any error occurs during the NWB file creation or writing.
        """
        if not PYNWB_AVAILABLE:
            raise ExportError("pynwb library is not installed. Cannot export to NWB.")

        log.info(f"Starting NWB export for recording from: {getattr(recording, 'source_file', 'Unknown Source').name}")
        log.debug(f"Output path: {output_path}")

        # --- Validate Recording Object ---
        if not isinstance(recording, Recording):
            raise TypeError("Invalid 'recording' object provided to NWBExporter.")
        if not hasattr(recording, 'channels') or not isinstance(recording.channels, dict):
             raise ValueError("Recording object is missing 'channels' dictionary or is not a dictionary.")

        # --- Validate Metadata & Prepare NWBFile ---
        required_keys = ['session_description', 'identifier', 'session_start_time']
        missing_keys = [key for key in required_keys if key not in session_metadata or not session_metadata[key]]
        if missing_keys:
            raise ValueError(f"Missing required NWB session metadata: {missing_keys}")

        start_time = session_metadata['session_start_time']
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
        subj_id = session_metadata.get('subject_id')
        if subj_id:
            try:
                from pynwb.file import Subject
                subject = Subject(
                    subject_id=subj_id,
                    species=session_metadata.get('species'),
                    sex=session_metadata.get('sex', 'U'), # Default Unknown
                    age=session_metadata.get('age'),
                    description=session_metadata.get('subject_description'),
                    genotype=session_metadata.get('genotype'),
                    weight=session_metadata.get('weight')
                )
                log.debug(f"Created NWB Subject object for ID: {subj_id}")
            except Exception as e_subj:
                log.error(f"Failed to create Subject object: {e_subj}")
                # Continue without subject if it fails, or raise? Proceeding is safer for user exp.

        # --- Create NWB File Object ---
        try:
            # Construct notes
            notes_list = []
            if session_metadata.get('notes'):
                notes_list.append(session_metadata['notes'])
            
            # Append technical details to notes
            source_file_name = getattr(recording, 'source_file', Path("Unknown")).name
            notes_list.append(f"Original file: {source_file_name}")
            if hasattr(recording, 'protocol_name') and recording.protocol_name:
                notes_list.append(f"Protocol: {recording.protocol_name}")
                
            notes_combined = "\n".join(notes_list)

            nwbfile = NWBFile(
                session_description=session_metadata['session_description'],
                identifier=session_metadata['identifier'],
                session_start_time=start_time,
                experimenter=session_metadata.get('experimenter'),
                lab=session_metadata.get('lab'),
                institution=session_metadata.get('institution'),
                session_id=session_metadata.get('session_id'),
                notes=notes_combined,
                subject=subject  # Attach Subject
            )

            # --- Device ---
            # Prefer metadata from dialog, fallback to recording metadata, then defaults
            dev_name = session_metadata.get('device_name') or recording.metadata.get('device_name') or 'Amplifier'
            dev_descr = session_metadata.get('device_description') or recording.metadata.get('device_description') or 'Electrophysiology amplifier'
            dev_manu = session_metadata.get('device_manufacturer') or recording.metadata.get('device_manufacturer') or 'Unknown'
            
            device = nwbfile.create_device(name=dev_name, description=dev_descr, manufacturer=dev_manu)
            log.debug(f"Using device: {device.name}")

            # --- Electrode Defaults ---
            # Defaults from dialog
            elec_desc_def = session_metadata.get('electrode_description_default', 'Intracellular Electrode')
            elec_loc_def = session_metadata.get('electrode_location_default', 'Unknown')
            elec_filt_def = session_metadata.get('electrode_filtering_default', 'unknown')

            # --- Add Channels ---
            num_channels_processed = 0
            if not recording.channels:
                 log.warning("Recording contains no channels to export.")

            for chan_id, channel in recording.channels.items():
                if not isinstance(channel, Channel):
                    continue
                if not getattr(channel, 'data_trials', None):
                    continue

                log.debug(f"Processing channel '{channel.name}' (ID: {chan_id})")

                # --- Create/Get IntracellularElectrode ---
                electrode_name = f"electrode_{chan_id}"
                
                # Check for specific channel overrides (if any in future) -> currently use defaults from dialog
                # unless channel object has specific metadata populated
                ic_desc = getattr(channel, 'electrode_description', None) or elec_desc_def
                ic_loc = getattr(channel, 'electrode_location', None) or elec_loc_def
                ic_filt = getattr(channel, 'electrode_filtering', None) or elec_filt_def
                
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
                            filtering=str(ic_filt)
                        )
                    except Exception as e_elec:
                         log.error(f"Failed to create electrode '{electrode_name}': {e_elec}")
                         continue

                # --- Create PatchClampSeries ---
                for trial_idx, trial_data in enumerate(channel.data_trials):
                    if trial_data.size == 0: continue

                    ts_name = f"{channel.name}_trial_{trial_idx:03d}"
                    ts_desc = f"Raw data for channel '{channel.name}', trial {trial_idx+1}"
                    
                    # Units & Verification
                    # If units imply voltage -> CurrentClampSeries (measures V)
                    # If units imply current -> VoltageClampSeries (measures I)
                    # For now, generic PatchClampSeries is safer if mode unknown, 
                    # BUT PyNWB encourages specific if possible.
                    # NWB: VoltageClampSeries (records Current, units=Amps). CurrentClampSeries (records Voltage, units=Volts).
                    
                    units = getattr(channel, 'units', 'unknown').lower()
                    
                    # Convert common units to SI for NWB (V, A) ? 
                    # PyNWB expects SI units generally (Volts, Amps). 
                    # !!! CRITICAL: Neo/Synaptipy usually keeps data in mV/pA.
                    # We should ideally convert or set the unit string correctly.
                    # If we set 'unit="mV"', PyNWB handles it? Yes, it accepts string units.
                    
                    final_units = getattr(channel, 'units', 'unknown')
                    
                    # Decide Class based on units if possible
                    SeriesClass = PatchClampSeries
                    if 'v' in units: # likely Voltage -> CurrentClampSeries (records V)
                        pass # PyNWB structure is complex: CurrentClampSeries stores MEASURED VOLTAGE in 'data'
                        # For simplicity/safety, sticking to parent PatchClampSeries is often better unless we are SURE of clamp mode.
                        # However, NWB guidelines prefer specific classes.
                        # Let's stick to PatchClampSeries to avoid validation errors if we misuse the specific ones without full clamp params (Series resistance etc)
                    
                    channel_rate = getattr(channel, 'sampling_rate', recording.sampling_rate)
                    
                    try:
                        time_series = PatchClampSeries(
                            name=ts_name,
                            description=ts_desc,
                            data=trial_data,
                            unit=final_units,
                            electrode=ic_electrode,
                            rate=float(channel_rate) if channel_rate else 1000.0,
                            starting_time=float(getattr(channel, 't_start', 0.0)),
                            gain=1.0, # Assumed data is already scaled
                            sweep_number=np.uint64(trial_idx)
                        )
                        nwbfile.add_acquisition(time_series)
                    except Exception as e_ts:
                         log.error(f"Failed to add series '{ts_name}': {e_ts}")
                         continue

                num_channels_processed += 1

            if num_channels_processed == 0:
                 log.warning("No valid channels exported.")

            # --- Write File ---
            log.info(f"Writing NWB to: {output_path}")
            with NWBHDF5IO(str(output_path), 'w') as io:
                io.write(nwbfile)
                
            log.info("NWB export complete.")

        except Exception as e:
            log.error(f"NWB Export failed: {e}", exc_info=True)
            raise ExportError(f"Failed to export to NWB: {e}") from e