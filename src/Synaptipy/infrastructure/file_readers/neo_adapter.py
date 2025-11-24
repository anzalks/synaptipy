# src/Synaptipy/infrastructure/file_readers/neo_adapter.py
# -*- coding: utf-8 -*-
"""
Adapter for reading various electrophysiology file formats using the neo library
and translating them into the application's core domain model.
IO class selection uses a predefined dictionary mapping extensions to IO names.

The read_recording method implements a robust "Header-First" approach:
1. Reads file header first to discover ALL channels with their metadata
2. Creates a definitive channel map before processing any signal data
3. Aggregates data from segments to the correct channels using stable IDs
4. Ensures all channels (including custom-labeled ones) are correctly identified

This approach eliminates assumptions about data structure and ensures that
what's in the file header is what gets loaded, making the software truly versatile
for WCP, ABF, and other supported file formats.

Also provides a method to generate a Qt file dialog filter based on its supported IOs.
"""
__author__ = "Anzal KS"
__copyright__ = "Copyright 2024-, Anzal KS"
__maintainer__ = "Anzal KS"
__email__ = "anzalks@ncbs.res.in"

import logging
from pathlib import Path
from typing import Dict, List, Optional, Type, Tuple, Any # Added Type
import os
import re

import neo # Added missing import
import neo.io as nIO # Keep original import style
import numpy as np
import quantities as pq
from quantities import Quantity, s, ms, V, mV, A, pA, nA # Import base quantities

# Import from our package structure
from Synaptipy.core.data_model import Recording, Channel # Removed RecordingHeader
from Synaptipy.shared.error_handling import FileReadError, UnsupportedFormatError, SynaptipyFileNotFoundError

log = logging.getLogger('Synaptipy.infrastructure.file_readers.neo_adapter')

# --- Dictionary mapping IO Class Names to extensions (Source of truth) ---
IODict = {
    'AlphaOmegaIO': ['lsx', 'mpx'],
    'AsciiImageIO': [],
    'AsciiSignalIO': ['txt', 'asc', 'csv', 'tsv'],
    'AsciiSpikeTrainIO': ['txt'],
    'AxographIO': ['axgd', 'axgx'],
    'AxonIO': ['abf'],
    'AxonaIO': ['bin', 'set'] + [str(i) for i in range(1, 33)],
    'BCI2000IO': ['dat'],
    'BiocamIO': ['h5', 'brw'],
    'BlackrockIO': ['ns1', 'ns2', 'ns3', 'ns4', 'ns5', 'ns6', 'nev', 'sif', 'ccf'],
    'BrainVisionIO': ['vhdr'],
    'BrainwareDamIO': ['dam'],
    'BrainwareF32IO': ['f32'],
    'BrainwareSrcIO': ['src'],
    'CedIO': ['smr', 'smrx'],
    'EDFIO': ['edf'],
    'ElanIO': ['eeg'],
    'IgorIO': ['ibw', 'pxp'],
    'IntanIO': ['rhd', 'rhs', 'dat'],
    'KlustaKwikIO': ['fet', 'clu', 'res', 'spk'],
    'KwikIO': ['kwik'],
    'MEArecIO': ['h5'],
    'MaxwellIO': ['h5'],
    'MedIO': ['medd', 'rdat', 'ridx'],
    'MicromedIO': ['trc', 'TRC'],
    'NWBIO': ['nwb'],
    'NeoMatlabIO': ['mat'],
    'NestIO': ['gdf', 'dat'],
    'NeuralynxIO': ['nse', 'ncs', 'nev', 'ntt', 'nvt', 'nrd'],
    'NeuroExplorerIO': ['nex'],
    'NeuroScopeIO': ['xml', 'dat', 'lfp', 'eeg'],
    'NeuroshareIO': ['nsn'],
    'NixIO': ['h5', 'nix'],
    'OpenEphysBinaryIO': ['oebin'],
    'OpenEphysIO': ['continuous', 'openephys', 'spikes', 'events', 'xml'],
    'PhyIO': ['npy', 'mat', 'tsv', 'dat'],
    'PickleIO': ['pkl', 'pickle'],
    'Plexon2IO': ['pl2'],
    'PlexonIO': ['plx'],
    'RawBinarySignalIO': ['raw', 'bin', 'dat'],
    'RawMCSIO': ['raw'],
    'Spike2IO': ['smr', 'smrx'],
    'SpikeGLXIO': ['bin', 'meta'],
    'SpikeGadgetsIO': ['rec'],
    'StimfitIO': ['abf', 'dat', 'axgx', 'axgd', 'cfs'],
    'TdtIO': ['tbk', 'tdx', 'tev', 'tin', 'tnt', 'tsq', 'sev', 'txt'],
    'TiffIO': ['tiff'],
    'WinWcpIO': ['wcp'],
}

class NeoAdapter:
    """
    Reads ephys files using neo, translating data to the Core Domain Model.
    Uses a fixed dictionary (IODict) for IO selection and implements a robust
    "Header-First" approach for channel identification.
    
    The Header-First approach ensures:
    - All channels are discovered from file header before data processing
    - Custom channel labels are preserved and correctly mapped
    - No assumptions are made about data structure
    - Versatile support for WCP, ABF, and other formats
    """

    def _get_neo_io_class(self, filepath: Path) -> Type: # Use generic Type hint
        """Determines appropriate neo IO class using the predefined IODict."""
        if not filepath.is_file():
            raise SynaptipyFileNotFoundError(f"File not found: {filepath}")

        extension = filepath.suffix.lower().lstrip('.')
        log.debug(f"Attempting to find IO for extension: '{extension}'")

        available_io_names = [io_name for io_name, exts in IODict.items() if extension in exts]

        if not available_io_names:
            raise UnsupportedFormatError(f"Unsupported file extension '.{extension}'. No suitable IO found in IODict.")

        selected_io_name = available_io_names[0]
        if len(available_io_names) > 1:
            if extension == 'abf' and 'AxonIO' in available_io_names and 'StimfitIO' in available_io_names:
                 selected_io_name = 'AxonIO'
                 log.warning(f"Multiple IOs support '.{extension}' ({available_io_names}). Prioritizing '{selected_io_name}'.")
            else:
                 log.warning(f"Multiple Neo IOs support '.{extension}': {available_io_names}. Using first match: '{selected_io_name}'.")
        else:
            log.info(f"Selected Neo IO: '{selected_io_name}' for file extension '.{extension}'.")

        try:
            io_class = getattr(nIO, selected_io_name)
            # Optional check (can be removed if causing issues):
            # if not (isinstance(io_class, type) and hasattr(nIO, 'baseio') and issubclass(io_class, nIO.baseio.BaseIO)):
            #      log.warning(f"'{selected_io_name}' found via getattr but might not be a valid Neo IO class.")
            return io_class
        except AttributeError:
            log.error(f"Internal IODict Error: IO class name '{selected_io_name}' not found in neo.io module.")
            raise ValueError(f"Invalid IO class name '{selected_io_name}' defined in IODict.")
        except Exception as e:
            log.error(f"Unexpected error retrieving Neo IO class '{selected_io_name}': {e}")
            raise FileReadError(f"Error accessing Neo IO class '{selected_io_name}': {e}")

    def get_supported_file_filter(self) -> str:
        """Generates a file filter string for QFileDialog based on the IODict."""
        filters = []
        all_exts_wildcard = set()
        sorted_io_names = sorted(IODict.keys())

        for io_name in sorted_io_names:
            extensions = IODict.get(io_name, [])
            if not extensions: continue

            wildcard_exts = [f"*.{ext.lower()}" for ext in extensions if ext and isinstance(ext, str) and '.' not in ext]
            if not wildcard_exts: continue

            display_name = io_name[:-2] if io_name.endswith("IO") else io_name
            filter_entry = f"{display_name} Files ({' '.join(sorted(wildcard_exts))})" # Sort extensions here
            filters.append(filter_entry)
            all_exts_wildcard.update(wildcard_exts)

        if all_exts_wildcard:
            all_supported_entry = f"All Supported Files ({' '.join(sorted(list(all_exts_wildcard)))})"
            filters.insert(0, all_supported_entry)

        filters.append("All Files (*)")
        log.debug(f"Generated filter string using IODict: {' ;; '.join(filters)}")
        return ";;".join(filters)

    def get_supported_extensions(self) -> List[str]:
        """
        Returns a list of all supported file extensions (e.g. ['abf', 'dat', ...]).
        Used for filtering file views.
        """
        all_exts = set()
        for exts in IODict.values():
            for ext in exts:
                if ext and isinstance(ext, str):
                    all_exts.add(ext.lower())
        return sorted(list(all_exts))

    def _extract_axon_metadata(self, reader: nIO.AxonIO) -> Tuple[Optional[str], Optional[float]]:
        """Extracts protocol name and estimated injected current range specifically for AxonIO."""
        protocol_name: Optional[str] = None
        injected_current: Optional[float] = None

        if not isinstance(reader, nIO.AxonIO):
            log.debug("Not AxonIO, skipping Axon meta.")
            return protocol_name, injected_current

        # --- Protocol Name ---
        try:
            if hasattr(reader, '_axon_info') and reader._axon_info and 'sProtocolPath' in reader._axon_info:
                protocol_path_raw = reader._axon_info['sProtocolPath']
                protocol_path = protocol_path_raw.decode('utf-8', 'ignore') if isinstance(protocol_path_raw, bytes) else str(protocol_path_raw)
                if protocol_path and protocol_path.strip():
                    filename = protocol_path.split('\\')[-1].split('/')[-1]
                    protocol_name = filename.rsplit('.', 1)[0] if '.' in filename else filename
                    log.info(f"Extracted protocol name: {protocol_name}")
                else:
                    log.info("Axon header 'sProtocolPath' is present but empty.")
            else:
                log.info("Axon header '_axon_info' or 'sProtocolPath' not found.")
        except Exception as e:
            log.warning(f"Protocol name extraction failed: {e}")
            protocol_name = "Extraction Error"

        # --- Injected Current ---
        try:
            if hasattr(reader, 'read_raw_protocol'):
                protocol_raw_list = reader.read_raw_protocol()
                if isinstance(protocol_raw_list, list) and protocol_raw_list:
                    all_command_signals = []
                    for seg_protocol in protocol_raw_list:
                        if isinstance(seg_protocol, (list, tuple)) and len(seg_protocol) > 0:
                            command_signal_data = seg_protocol[0]
                            if isinstance(command_signal_data, (np.ndarray, list)):
                                command_signal_array = np.asarray(command_signal_data).ravel()
                                if command_signal_array.size > 0:
                                    all_command_signals.append(command_signal_array)
                    # --- Corrected Indentation for Current Calculation --- START ---
                    if all_command_signals:
                        all_command_points = np.concatenate(all_command_signals)
                        if all_command_points.size > 0:
                            current_range = np.ptp(all_command_points)
                            injected_current = np.around(current_range, decimals=3)
                            log.info(f"Estimated injected current range (PTP): {injected_current}")
                        else:
                            log.info("Concatenated command signals were empty.") # Aligned with inner if
                    else:
                        log.info("No suitable command signals found in protocol structure.") # Aligned with 'if all_command_signals'
                    # --- Corrected Indentation for Current Calculation --- END ---
                else:
                     log.info("'read_raw_protocol()' returned empty list or non-list structure.") # Aligned with outer if
            else:
                log.info("AxonIO reader instance does not have 'read_raw_protocol()' method.") # Aligned with hasattr
        except Exception as e:
            log.warning(f"Failed during injected current estimation: {e}", exc_info=True)
            injected_current = None

        return protocol_name, injected_current

    def read_recording(self, filepath: Path, lazy: bool = False) -> Recording:
        """
        Reads any neo-supported electrophysiology file and translates it into a
        robust Recording object. This is the definitive, file-format-agnostic implementation.
        """
        log.info(f"Attempting to read file: {filepath} (lazy mode: {lazy})")
        filepath = Path(filepath)
        io_class = self._get_neo_io_class(filepath)
        reader = io_class(filename=str(filepath))
        block = reader.read_block(lazy=lazy, signal_group_mode='split-all')
        log.info(f"Successfully read neo Block using {io_class.__name__}.")
        
        recording = Recording(source_file=filepath)
        if hasattr(block, 'rec_datetime') and block.rec_datetime:
            recording.session_start_time_dt = block.rec_datetime
            log.info(f"Extracted session start time: {recording.session_start_time_dt}")

        # --- Definitive Universal Header-First Data Loading Strategy ---
        channel_metadata_map: Dict[str, Dict] = {}

        # Stage 1: Discover ALL potential channels from the header first.
        header_channels = reader.header.get('signal_channels') if hasattr(reader, 'header') else None
        if header_channels is not None and len(header_channels) > 0:
            log.info(f"Header found. Discovering channels from {type(header_channels)}.")
            for i, ch_info in enumerate(header_channels):
                ch_id = str(ch_info.get('id', i)) if isinstance(ch_info, dict) else str(ch_info['id']) if 'id' in ch_info.dtype.names else str(i)
                if isinstance(ch_info, dict):
                    ch_name = str(ch_info.get('name', f'Channel {ch_id}'))
                else:
                    if 'name' in ch_info.dtype.names and ch_info['name']:
                        ch_name_raw = ch_info['name']
                        if isinstance(ch_name_raw, bytes):
                            ch_name = ch_name_raw.decode().strip()
                        elif isinstance(ch_name_raw, (str, np.str_)):
                            ch_name = str(ch_name_raw).strip()
                        else:
                            ch_name = f"Channel {ch_id}"
                    else:
                        ch_name = f"Channel {ch_id}"
                map_key = f"id_{ch_id}"
                if map_key not in channel_metadata_map:
                    channel_metadata_map[map_key] = {'id': ch_id, 'name': ch_name, 'data_trials': []}
            log.info(f"Discovered {len(channel_metadata_map)} channels from header.")
        
        # Stage 2: Aggregate data into the discovered channels.
        for seg_idx, segment in enumerate(block.segments):
            log.debug(f"Processing segment {seg_idx} with {len(segment.analogsignals)} analogsignals")
            
            # Critical fix: Iterate through ALL analogsignals by index to ensure each channel gets its data
            for anasig_idx, anasig in enumerate(segment.analogsignals):
                if not isinstance(anasig, (neo.AnalogSignal, neo.io.proxyobjects.AnalogSignalProxy)):
                    log.debug(f"Skipping non-AnalogSignal object at index {anasig_idx}")
                    continue
                
                # Extract channel ID using multiple fallback methods for robustness
                # Try annotation first, then attributes, finally use the signal index
                anasig_id = None
                if hasattr(anasig, 'annotations') and 'channel_id' in anasig.annotations:
                    anasig_id = str(anasig.annotations['channel_id'])
                elif hasattr(anasig, 'channel_index') and anasig.channel_index is not None:
                    anasig_id = str(anasig.channel_index)
                elif hasattr(anasig, 'array_annotations') and 'channel_id' in anasig.array_annotations:
                    anasig_id = str(anasig.array_annotations['channel_id'][0])
                else:
                    # Use the signal's position in the list as the channel ID
                    anasig_id = str(anasig_idx)
                    log.debug(f"Using signal index {anasig_idx} as channel ID (no channel metadata found)")
                
                map_key = f"id_{anasig_id}"
                log.debug(f"Processing analogsignal {anasig_idx} -> channel ID '{anasig_id}' (map_key: {map_key})")
                
                if map_key not in channel_metadata_map:
                    log.warning(f"Data for channel ID '{anasig_id}' not in header; creating fallback channel.")
                    channel_metadata_map[map_key] = {
                        'id': anasig_id, 
                        'name': f"Channel {anasig_id}", 
                        'data_trials': []
                    }
                
                # Extract and append the signal data for THIS specific channel
                signal_data = np.array(anasig.magnitude).ravel()
                channel_metadata_map[map_key]['data_trials'].append(signal_data)
                log.debug(f"Appended {len(signal_data)} samples to channel '{anasig_id}' from segment {seg_idx}")
                
                # Store metadata on first encounter
                if 'sampling_rate' not in channel_metadata_map[map_key]:
                    channel_metadata_map[map_key].update({
                        'units': str(anasig.units.dimensionality),
                        'sampling_rate': float(anasig.sampling_rate),
                        't_start': float(anasig.t_start)
                    })
                    log.debug(f"Stored metadata for channel '{anasig_id}': {channel_metadata_map[map_key]['sampling_rate']} Hz")

        # Stage 3: Create Channel objects ONLY for channels that actually have data.
        created_channels: List[Channel] = []
        for meta in channel_metadata_map.values():
            if not meta['data_trials'] or meta.get('sampling_rate') is None:
                log.info(f"Channel '{meta['name']}' discovered but contained no data; skipping.")
                continue
                
            channel = Channel(
                id=meta['id'], name=meta['name'], units=meta['units'],
                sampling_rate=meta['sampling_rate'], data_trials=meta['data_trials']
            )
            channel.t_start = meta.get('t_start', 0.0)
            created_channels.append(channel)

        recording.channels = {ch.id: ch for ch in created_channels}
        if created_channels:
            first_ch = created_channels[0]
            recording.sampling_rate = first_ch.sampling_rate
            recording.t_start = first_ch.t_start
            if first_ch.data_trials and first_ch.sampling_rate > 0:
                recording.duration = len(first_ch.data_trials[0]) / first_ch.sampling_rate

        log.info(f"Translation complete. Loaded {len(recording.channels)} data-containing channel(s).")
        return recording

# =============================================================================
# =============================================================================
# Example Usage Block
# =============================================================================
if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s [%(levelname)s] %(message)s') # DEBUG for more info
    log.info("="*30); log.info("Running NeoAdapter example (IODict lookup)..."); log.info("="*30)

    adapter = NeoAdapter() # Create adapter instance first

    # --- Generate and Log Filter String (FIXED) ---
    try:
        filter_string_raw = adapter.get_supported_file_filter()
        # Replace ;; with newline outside the f-string
        filter_string_formatted = filter_string_raw.replace(';;', '\n')
        log.info(f"Supported filter string:\n{filter_string_formatted}") # Log the formatted string
    except Exception as e_filter:
        log.error(f"Error generating file filter: {e_filter}")
    # --- End Filter String Fix ---

    # --- !!! UPDATE PATH !!! ---
    test_file_path = Path("./path/to/your/test_data_file.abf") # Or .axgd, .smr, etc.
    # --------------------------
    if not test_file_path.exists() or not test_file_path.is_file():
        log.error(f"Test file not found or is not a file: {test_file_path}")
        log.error("Please update 'test_file_path' in the `if __name__ == '__main__':` block.")
    else:
        log.info(f"\nAttempting to read: {test_file_path}")
        try:
            recording_data = adapter.read_recording(test_file_path)
            # --- Print Summary (Remains the same) ---
            print("\n--- Recording Summary ---")
            # ... (rest of the print statements for summary and channel details) ...
            print(f"Source File:         {recording_data.source_file.name}")
            print(f"Sampling Rate (Hz):  {recording_data.sampling_rate}")
            print(f"Estimated Duration (s): {recording_data.duration}")
            print(f"Session Start Time:  {recording_data.session_start_time_dt}")
            print(f"Protocol Name:       {recording_data.protocol_name}")
            print(f"Inj. Current (PTP):  {recording_data.injected_current}")
            print(f"Number of Channels:  {len(recording_data.channels)}")
            print(f"Max Trials in File:  {recording_data.max_trials}")
            print("\n--- Channel Details ---")
            for ch_id, channel in recording_data.channels.items():
                print(f"  Channel ID:          {ch_id}")
                print(f"    Name:              {channel.name}")
                print(f"    Units:             {channel.units}")
                print(f"    Sampling Rate:     {channel.sampling_rate:.2f} Hz")
                print(f"    Number of Trials:  {channel.num_trials}")
                print(f"    t_start (rel rec): {channel.t_start:.4f} s")
                print(f"    Electrode Desc:    {channel.electrode_description}")
                print(f"    Electrode Filter:  {channel.electrode_filtering}")
                print(f"    Gain:              {channel.electrode_gain}")
                print(f"    Offset:            {channel.electrode_offset}")
                if channel.data_trials: print(f"    First Trial Len:   {len(channel.data_trials[0])} samples")
                print("-" * 20)
        except Exception as e:
            print(f"\n--- ERROR during example execution ---"); log.exception("Exception occurred in example usage block:"); print(f"Error Type: {type(e).__name__}"); print(f"Error Details: {e}")
    log.info("="*30); log.info("NeoAdapter example finished."); log.info("="*30)