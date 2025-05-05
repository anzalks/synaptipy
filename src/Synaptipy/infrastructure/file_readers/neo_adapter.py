# src/Synaptipy/infrastructure/file_readers/neo_adapter.py
# -*- coding: utf-8 -*-
"""
Adapter for reading various electrophysiology file formats using the neo library
and translating them into the application's core domain model.
IO class selection uses a predefined dictionary mapping extensions to IO names.
Attempts to use reader header information for robust channel identification and
extracts additional metadata where available.
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
    Uses a fixed dictionary (IODict) for IO selection and prioritizes reader
    header for channel identification. Extracts additional metadata.
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

    def read_recording(self, filepath: Path) -> Recording:
        """Reads an electrophysiology file using Neo and translates it into a Recording object."""
        log.info(f"Attempting to read file: {filepath}")
        filepath = Path(filepath)
        io_class = None
        reader = None
        io_class_name = "Unknown"

        try:
            # --- Use the IODict lookup method ---
            io_class = self._get_neo_io_class(filepath)
            io_class_name = io_class.__name__
            log.debug(f"Instantiating IO class: {io_class_name}")
            reader = io_class(filename=str(filepath))
            # --- End Change ---

            # --- Header processing ---
            header_channel_info: Dict[int, Dict[str, str]] = {}
            try:
                if hasattr(reader, 'header') and reader.header and 'signal_channels' in reader.header:
                    signal_channels_header = reader.header['signal_channels']
                    if signal_channels_header is not None and hasattr(signal_channels_header, '__len__') and hasattr(signal_channels_header, '__getitem__'):
                        log.debug(f"Processing 'signal_channels' header (type: {type(signal_channels_header)}, len: {len(signal_channels_header)})")
                        for idx, header_entry in enumerate(signal_channels_header):
                            ch_name = f'HeaderCh_{idx}'; ch_id = str(idx) # Defaults
                            try:
                                if isinstance(header_entry, dict):
                                    ch_name_try = header_entry.get('name', header_entry.get('label', header_entry.get('channel_name', ch_name)))
                                    ch_id_try = header_entry.get('id', header_entry.get('channel_id', ch_id))
                                elif hasattr(header_entry, 'dtype') and hasattr(header_entry.dtype, 'names'):
                                    names = header_entry.dtype.names
                                    ch_name_try = header_entry['name'] if 'name' in names else header_entry['label'] if 'label' in names else header_entry['channel_name'] if 'channel_name' in names else ch_name
                                    ch_id_try = header_entry['id'] if 'id' in names else header_entry['channel_id'] if 'channel_id' in names else ch_id
                                else: ch_name_try = str(header_entry) if isinstance(header_entry, (str, bytes)) else ch_name; ch_id_try = ch_id
                                ch_name = ch_name_try.decode('utf-8', 'ignore') if isinstance(ch_name_try, bytes) else str(ch_name_try)
                                ch_id = ch_id_try.decode('utf-8', 'ignore') if isinstance(ch_id_try, bytes) else str(ch_id_try)
                            except Exception as e_inner: log.warning(f"Failed to fully parse header entry at index {idx}: {e_inner}. Using defaults.")
                            header_channel_info[idx] = {'id': ch_id, 'name': ch_name}
                            log.debug(f"Header map: Index {idx} -> ID='{ch_id}', Name='{ch_name}'")
                    else: log.warning("'signal_channels' in header is not list-like or is None.")
                else: log.warning("Reader header does not contain 'signal_channels' or is missing.")
            except Exception as e_header: log.warning(f"Error processing reader header: {e_header}", exc_info=True)

            # --- Read Block ---
            block = reader.read_block(lazy=False, signal_group_mode='split-all')
            log.info(f"Successfully read neo Block using {io_class_name}.")

        except (SynaptipyFileNotFoundError, UnsupportedFormatError) as e: log.error(f"File pre-read error: {e}"); raise e
        except neo.io.NeoReadWriteError as ne: log.error(f"Neo failed to read file '{filepath.name}' with {io_class_name}: {ne}", exc_info=True); raise FileReadError(f"Neo error reading {filepath.name}: {ne}") from ne
        except IOError as ioe: log.error(f"IOError obtaining reader or reading '{filepath.name}': {ioe}", exc_info=True); raise UnsupportedFormatError(f"Cannot read file {filepath.name}. Check format/permissions.") from ioe
        except Exception as e: log.error(f"Unexpected error reading file '{filepath.name}' using {io_class_name}: {e}", exc_info=True); raise FileReadError(f"Unexpected error reading {filepath.name} with {io_class_name}: {e}") from e

        # --- Start Translation to Synaptipy Domain Model --- Simplified Approach ---
        recording = Recording(source_file=filepath)

        # Extract session start time and assign to recording
        if hasattr(block, 'rec_datetime') and block.rec_datetime:
            recording.session_start_time_dt = block.rec_datetime # Assign directly to recording
            log.info(f"Extracted session start time: {recording.session_start_time_dt}")
        else: 
            log.warning("Could not extract session start time (rec_datetime).")
            if not hasattr(recording, 'session_start_time_dt'): recording.session_start_time_dt = None # Ensure attr exists

        # Extract global metadata and assign to recording
        recording.metadata = block.annotations if block.annotations else {} # Assign directly to recording
        recording.metadata['neo_block_description'] = block.description
        recording.metadata['neo_file_origin'] = block.file_origin
        recording.metadata['neo_reader_class'] = reader.__class__.__name__ if reader else (io_class.__name__ if io_class else "Unknown IO")

        # Extract Axon-specific metadata (if applicable) and assign to recording
        proto_name, inj_curr = self._extract_axon_metadata(reader)
        recording.protocol_name = proto_name # Assign directly to recording
        recording.injected_current = inj_curr # Assign directly to recording
        # Ensure other expected attrs exist even if None
        if not hasattr(recording, 'protocol_name'): recording.protocol_name = None
        if not hasattr(recording, 'injected_current'): recording.injected_current = None
        if not hasattr(recording, 'sampling_rate'): recording.sampling_rate = None
        if not hasattr(recording, 't_start'): recording.t_start = None
        if not hasattr(recording, 'duration'): recording.duration = None

        # --- Process Segments and Signals --- Generic Approach ---
        num_segments = len(block.segments)
        log.info(f"Processing {num_segments} segment(s) generically...")

        channel_data_map: Dict[str, List[np.ndarray]] = {} # Key: Unique channel map_key
        channel_metadata_map: Dict[str, Dict[str, Any]] = {} # Key: Unique channel map_key

        for seg_index, segment in enumerate(block.segments):
            log.debug(f"--- SEGMENT {seg_index + 1}/{num_segments} ---")
            if not hasattr(segment, 'analogsignals') or not segment.analogsignals:
                 log.debug(f"  Segment has no analogsignals.")
                 continue
            log.debug(f"  Segment contains {len(segment.analogsignals)} AnalogSignal object(s).")

            for sig_index, anasig in enumerate(segment.analogsignals):
                log.debug(f"    Processing signal index {sig_index} in segment...")
                # Basic validation
                if not isinstance(anasig, neo.AnalogSignal):
                    log.warning(f"    Skipping non-AnalogSignal object: {type(anasig)}")
                    continue
                if anasig.shape[1] != 1:
                    log.warning(f"    AnalogSignal has unexpected shape {anasig.shape}. Skipping. Expected (n_samples, 1).")
                    continue
                if anasig.size == 0:
                     log.warning(f"    AnalogSignal is empty (size 0). Skipping.")
                     continue

                # --- Robust Channel Identification Logic (adapted from site-packages version) ---
                ch_id = None; ch_name = None; original_neo_id = None; map_key = None
                log.debug(f"      Attempting identification for signal {sig_index}...")
                log.debug(f"        channel_index: {getattr(anasig, 'channel_index', 'N/A')}")
                log.debug(f"        annotations: {getattr(anasig, 'annotations', '{}')}")

                # 1. Try channel_index (often corresponds to physical channel)
                if hasattr(anasig, 'channel_index') and anasig.channel_index is not None:
                     map_key = f"neo_ch_idx_{anasig.channel_index}"
                     original_neo_id = anasig.channel_index
                     ch_id = anasig.channel_index # Use index as potential domain ID
                     ch_name = anasig.annotations.get('channel_name', None)
                     log.debug(f"        Trying channel_index {original_neo_id} as map_key.")
                     # Try to get name from header if not in annotations
                     if not ch_name and reader and hasattr(reader, 'header'):
                          try:
                               if 'signal_channels' in reader.header:
                                    header_channels = reader.header['signal_channels']
                                    if isinstance(header_channels, (list, np.ndarray)) and original_neo_id < len(header_channels):
                                         entry = header_channels[original_neo_id]
                                         if hasattr(entry, 'dtype') and 'name' in entry.dtype.names: ch_name = entry['name']
                                         elif isinstance(entry, dict) and 'name' in entry: ch_name = entry['name']
                                    elif isinstance(header_channels, dict) and original_neo_id in header_channels:
                                         entry = header_channels[original_neo_id]
                                         if isinstance(entry, dict) and 'name' in entry: ch_name = entry['name']
                               if isinstance(ch_name, bytes): ch_name = ch_name.decode('utf-8', 'ignore')
                               if ch_name: log.debug(f"        Got channel name '{ch_name}' from header.")
                          except Exception as e_header_name:
                               log.debug(f"        Failed to get channel name from header: {e_header_name}")
                     # Final fallback name based on index
                     if not ch_name: ch_name = f"Channel Index {original_neo_id}"
                     log.debug(f"        Using channel_index: Key='{map_key}', Name='{ch_name}', ID={ch_id}")

                # 2. Fallback to annotations if channel_index is missing/None
                elif anasig.annotations:
                     log.debug(f"        Falling back to annotations.")
                     ann_ch_id = anasig.annotations.get('channel_id', None)
                     ann_ch_name = anasig.annotations.get('channel_name', None)
                     if ann_ch_id is not None:
                          # Use annotation channel_id as primary key if available
                          map_key = str(ann_ch_id); original_neo_id = ann_ch_id; ch_id = ann_ch_id
                          ch_name = ann_ch_name if ann_ch_name else f"Ch_ID_{ann_ch_id}"
                          log.debug(f"        Using annotation channel_id: Key='{map_key}', Name='{ch_name}', ID={ch_id}")
                     elif ann_ch_name is not None:
                          # Use annotation channel_name if ID is missing (ensure unique names!)
                          map_key = ann_ch_name; original_neo_id = ann_ch_name; ch_name = ann_ch_name
                          log.warning(f"        Using annotation channel_name '{ann_ch_name}' as map_key (ID missing). Ensure names are unique.")
                     else:
                          # Fallback: Use signal index within segment as key (ASSUMES consistent order across segments)
                          map_key = f"Signal_{sig_index}"
                          # Try getting name from header info based on sig_index
                          header_name_info = header_channel_info.get(sig_index)
                          if header_name_info and 'name' in header_name_info:
                               ch_name = header_name_info['name']
                               log.debug(f"        Using header name '{ch_name}' for fallback key '{map_key}'.")
                          else:
                              ch_name = f"Signal {sig_index}" # Default name based on signal index
                              log.warning(f"        No usable annotations or header name found. Using placeholder name '{ch_name}' based on signal index {sig_index}.")
                          original_neo_id = map_key # Use the generated key as the original ID placeholder
                          log.warning(f"        Using placeholder key '{map_key}' based on signal index {sig_index}.")
                else:
                     # Fallback: No channel_index and no annotations. Use signal index.
                     map_key = f"Signal_{sig_index}"
                     # Try getting name from header info based on sig_index
                     header_name_info = header_channel_info.get(sig_index)
                     if header_name_info and 'name' in header_name_info:
                          ch_name = header_name_info['name']
                          log.debug(f"        Using header name '{ch_name}' for fallback key '{map_key}'.")
                     else:
                         ch_name = f"Signal {sig_index}" # Default name based on signal index
                         log.warning(f"        No channel_index, annotations, or header name found. Using placeholder name '{ch_name}' based on signal index {sig_index}.")
                     original_neo_id = map_key # Use the generated key as the original ID placeholder
                     log.warning(f"        Using placeholder key '{map_key}' based on signal index {sig_index}.")
                # --- End Channel ID Logic ---

                # --- Extract data and metadata ---
                try:
                    data = np.ravel(anasig.magnitude)
                    units_obj = anasig.units; units = str(units_obj.dimensionality) if hasattr(units_obj, 'dimensionality') else 'unknown'
                    units = 'dimensionless' if units.lower() == 'dimensionless' else units
                    sampling_rate = float(anasig.sampling_rate.magnitude)
                    t_start_signal = float(anasig.t_start.magnitude)
                    log.debug(f"      Extracted: Units='{units}', Rate={sampling_rate}, t_start={t_start_signal}, Data points={data.shape[0]}")
                except Exception as e:
                    log.error(f"      Error extracting data/metadata for signal key '{map_key}': {e}", exc_info=True)
                    continue # Skip this signal

                # --- Store/Update channel metadata and data ---
                if map_key not in channel_metadata_map:
                    log.debug(f"      First encounter for map_key '{map_key}'. Storing metadata.")
                    # Extract electrode metadata from annotations
                    electrode_description=anasig.annotations.get('description', anasig.annotations.get('comment', None))
                    electrode_location=anasig.annotations.get('location', None)
                    electrode_filtering=anasig.annotations.get('filtering', None)
                    electrode_gain=float(getattr(anasig, 'gain', np.nan)); electrode_gain=anasig.annotations.get('gain', electrode_gain) if np.isnan(electrode_gain) else electrode_gain
                    electrode_offset=float(getattr(anasig, 'offset', np.nan)); electrode_offset=anasig.annotations.get('offset', electrode_offset) if np.isnan(electrode_offset) else electrode_offset
                    electrode_resistance=anasig.annotations.get('resistance', None); electrode_seal=anasig.annotations.get('seal', None)
                    
                    channel_metadata_map[map_key] = {
                        'name': ch_name, 'units': units, 'sampling_rate': sampling_rate,
                        't_start': t_start_signal, 'original_neo_id': original_neo_id,
                        'domain_id': ch_id, # Store the potential domain ID found
                        'electrode_description': electrode_description, 'electrode_location': electrode_location,
                        'electrode_filtering': electrode_filtering, 'electrode_gain': electrode_gain,
                        'electrode_offset': electrode_offset, 'electrode_resistance': electrode_resistance,
                        'electrode_seal': electrode_seal
                    }
                    channel_data_map[map_key] = [data] # Initialize data list

                    # --- Set global recording properties from the *first valid signal* ---
                    if recording.sampling_rate is None:
                        recording.sampling_rate = sampling_rate
                        recording.t_start = t_start_signal
                        if sampling_rate > 0: recording.duration = data.shape[0] / sampling_rate
                        else: recording.duration = 0.0
                        log.info(f"      Set recording props from first signal: Rate={recording.sampling_rate}, t0={recording.t_start}, Est.Duration={recording.duration:.3f} s")
                else:
                    # Channel key seen before, check consistency and append data
                    log.debug(f"      Map_key '{map_key}' seen before. Appending data.")
                    existing_meta = channel_metadata_map[map_key]
                    if not np.isclose(existing_meta['sampling_rate'], sampling_rate):
                         log.warning(f"      Inconsistent sampling rate for channel key '{map_key}' ('{existing_meta['name']}'). Seg {seg_index+1} rate: {sampling_rate}. Using initial rate: {existing_meta['sampling_rate']}")
                    if existing_meta['units'] != units:
                         log.warning(f"      Inconsistent units for channel key '{map_key}' ('{existing_meta['name']}'). Seg {seg_index+1} units: '{units}'. Using initial units: '{existing_meta['units']}'")
                    channel_data_map[map_key].append(data)

        # --- Create final Synaptipy Channel objects --- Generic Approach ---
        if not channel_data_map:
             log.warning("No channel data aggregated after processing all segments.")
             return recording

        log.info(f"Aggregated data for {len(channel_data_map)} unique channel key(s). Creating Synaptipy Channel objects...")
        created_channels: List[Channel] = []
        for map_key, data_trials in channel_data_map.items():
            meta = channel_metadata_map[map_key]
            log.debug(f"  Creating Channel for map_key: '{map_key}'")
            if not data_trials: log.warning(f"    Skipping map_key '{map_key}' ('{meta['name']}') - no data trials collected."); continue

            # Determine the final ID for the Synaptipy Channel object
            final_channel_id = str(meta['domain_id']) if meta['domain_id'] is not None else map_key
            log.debug(f"    Using final_channel_id: '{final_channel_id}'")
            
            try:
                channel = Channel(
                    id=final_channel_id, name=meta['name'], units=meta['units'],
                    sampling_rate=meta['sampling_rate'], data_trials=data_trials
                )
                channel.metadata = {} # Initialize metadata dictionary
                channel.t_start = meta['t_start']
                # Assign optional electrode metadata
                channel.electrode_description = meta['electrode_description']; channel.electrode_location = meta['electrode_location']
                channel.electrode_filtering = meta['electrode_filtering']; channel.electrode_gain = meta['electrode_gain']
                channel.electrode_offset = meta['electrode_offset']; channel.electrode_resistance = meta['electrode_resistance']
                channel.electrode_seal = meta['electrode_seal']
                # Store original neo identifier in metadata
                channel.metadata['original_neo_id'] = meta['original_neo_id']

                created_channels.append(channel)
                log.debug(f"    Successfully created Channel: ID='{channel.id}', Name='{channel.name}', Units='{channel.units}', Trials={len(channel.data_trials)}, Samples/Trial={data_trials[0].shape[0] if data_trials else 0}")
            except Exception as e_channel_create:
                log.error(f"    Failed to create Synaptipy Channel object for map_key '{map_key}' ('{meta['name']}'): {e_channel_create}", exc_info=True)

        # Convert the list of channels to a dictionary keyed by channel ID
        recording.channels = {ch.id: ch for ch in created_channels}

        # --- Final Fallback Checks for Recording Properties (if needed) ---
        # Check if channels is a non-empty dict before trying to access its first element
        if recording.sampling_rate is None and recording.channels and isinstance(recording.channels, dict):
            log.warning("Recording sampling rate not set during segment iteration. Attempting fallback from first created Channel.")
            # Get the first channel object from the dictionary values
            first_channel = next(iter(recording.channels.values()))
            recording.sampling_rate = first_channel.sampling_rate
            recording.t_start = first_channel.t_start
            if first_channel.data_trials and first_channel.sampling_rate > 0:
                 try: recording.duration = first_channel.data_trials[0].shape[0] / first_channel.sampling_rate
                 except Exception: log.warning("Could not estimate duration from first channel fallback."); recording.duration = 0.0
            else: recording.duration = 0.0
            log.info(f"    Set recording properties via fallback: Rate={recording.sampling_rate}, t0={recording.t_start}, Est.Duration={recording.duration:.3f} s")

        # Use len(recording.channels) for the final log message, as it's now a dict
        log.info(f"Generic translation complete for '{filepath.name}'. Recording contains {len(recording.channels)} channel(s).")
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