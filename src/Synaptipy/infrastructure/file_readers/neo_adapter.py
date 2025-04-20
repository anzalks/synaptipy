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

import neo.io as nIO # Keep original import style
import numpy as np

# Import from our package structure using relative paths
try:
    from ...core.data_model import Recording, Channel
    from ...shared.error_handling import FileReadError, UnsupportedFormatError
except ImportError:
    log_fallback = logging.getLogger(__name__)
    log_fallback.warning("Could not perform relative imports for data_model/error_handling. Using placeholders.")
    class Recording: pass
    class Channel: pass
    class FileReadError(IOError): pass
    class UnsupportedFormatError(ValueError): pass

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
            raise FileNotFoundError(f"File not found: {filepath}")

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

        except (FileNotFoundError, UnsupportedFormatError) as e: log.error(f"File pre-read error: {e}"); raise e
        except neo.io.NeoReadWriteError as ne: log.error(f"Neo failed to read file '{filepath.name}' with {io_class_name}: {ne}", exc_info=True); raise FileReadError(f"Neo error reading {filepath.name}: {ne}") from ne
        except IOError as ioe: log.error(f"IOError obtaining reader or reading '{filepath.name}': {ioe}", exc_info=True); raise UnsupportedFormatError(f"Cannot read file {filepath.name}. Check format/permissions.") from ioe
        except Exception as e: log.error(f"Unexpected error reading file '{filepath.name}' using {io_class_name}: {e}", exc_info=True); raise FileReadError(f"Unexpected error reading {filepath.name} with {io_class_name}: {e}") from e

        # --- Process Neo Block ---
        if not block or not block.segments:
            log.warning(f"Neo block read from '{filepath.name}' contains no segments.")
            recording = Recording(source_file=filepath)
            if block: recording.metadata = block.annotations.copy() if block.annotations else {}; recording.metadata['neo_block_description'] = block.description; recording.metadata['neo_file_origin'] = block.file_origin
            if hasattr(block, 'rec_datetime') and block.rec_datetime: recording.session_start_time_dt = block.rec_datetime
            if reader: recording.metadata['neo_reader_class'] = reader.__class__.__name__
            return recording

        recording = Recording(source_file=filepath)
        if hasattr(block, 'rec_datetime') and block.rec_datetime: recording.session_start_time_dt = block.rec_datetime; log.info(f"Set recording session start time: {recording.session_start_time_dt}")
        else: log.warning("Recording session start time (rec_datetime) not found."); recording.session_start_time_dt = None
        recording.metadata = block.annotations.copy() if block.annotations else {}
        recording.metadata['neo_block_description'] = block.description; recording.metadata['neo_file_origin'] = block.file_origin
        if reader: recording.metadata['neo_reader_class'] = reader.__class__.__name__
        if isinstance(reader, nIO.AxonIO):
            protocol_name, injected_current = self._extract_axon_metadata(reader); recording.protocol_name = protocol_name; recording.injected_current = injected_current
            recording.metadata['axon_protocol_name'] = protocol_name; recording.metadata['axon_estimated_current_range'] = injected_current

        num_segments = len(block.segments); log.info(f"Processing {num_segments} segment(s)...")
        
        # --- MODIFIED: Data Aggregation Strategy --- 
        # Step 1: Collect voltage/current signal pairs per segment
        segment_signal_pairs: List[Dict[str, Optional[neo.AnalogSignal]]] = [] 
        
        for seg_index, segment in enumerate(block.segments):
            log.debug(f"Processing Segment {seg_index + 1}/{num_segments}")
            segment_voltages: Dict[Any, neo.AnalogSignal] = {} # Keyed by channel index or similar
            segment_currents: Dict[Any, neo.AnalogSignal] = {} # Keyed by channel index or similar
            
            if not segment.analogsignals: log.debug(f"Segment {seg_index+1} has no analogsignals."); continue
            
            for sig_index_in_segment, anasig in enumerate(segment.analogsignals):
                if not hasattr(anasig, 'shape') or anasig.ndim < 1 or anasig.size == 0:
                    log.warning(f"Skipping invalid/empty signal. Seg={seg_index}, NeoIdx={sig_index_in_segment}")
                    continue
                
                # Try to get a consistent physical channel index/ID
                # This needs refinement based on how neo presents multi-channel signals
                phys_chan_id = getattr(anasig, 'channel_index', sig_index_in_segment) # Use neo index as fallback key
                signal_units = str(getattr(anasig, 'units', '')).lower()
                
                if 'v' in signal_units: # Identify as potential voltage
                    if phys_chan_id in segment_voltages:
                        log.warning(f"Seg {seg_index}: Multiple voltage signals found for physical channel ID {phys_chan_id}. Keeping first.")
                    else:
                        segment_voltages[phys_chan_id] = anasig
                        log.debug(f"Seg {seg_index}: Found Voltage Signal for PhysChanID {phys_chan_id}, Units: {anasig.units}")
                elif 'a' in signal_units: # Identify as potential current
                    if phys_chan_id in segment_currents:
                         log.warning(f"Seg {seg_index}: Multiple current signals found for physical channel ID {phys_chan_id}. Keeping first.")
                    else:
                        segment_currents[phys_chan_id] = anasig
                        log.debug(f"Seg {seg_index}: Found Current Signal for PhysChanID {phys_chan_id}, Units: {anasig.units}")
                else:
                    log.warning(f"Seg {seg_index}, PhysChanID {phys_chan_id}: Signal units '{anasig.units}' not recognized as V or A. Skipping.")
            
            # Pair up signals for this segment based on physical channel ID
            # Assuming V and I for the same electrode have the same phys_chan_id
            paired_signals_in_segment = {}
            for phys_chan_id, voltage_sig in segment_voltages.items():
                current_sig = segment_currents.get(phys_chan_id)
                if current_sig is None:
                    log.warning(f"Seg {seg_index}: Found voltage for PhysChanID {phys_chan_id} but no matching current signal.")
                else:
                     log.debug(f"Seg {seg_index}: Paired V and I for PhysChanID {phys_chan_id}")
                # Store pair, even if current is missing, keyed by voltage channel ID for grouping later
                paired_signals_in_segment[phys_chan_id] = {'voltage': voltage_sig, 'current': current_sig} 
            
            segment_signal_pairs.append(paired_signals_in_segment)

        # ---> ADDED DEBUG LOG <-----
        log.debug(f"Collected segment_signal_pairs structure: {segment_signal_pairs}")
        # ---> END ADDED DEBUG LOG <-----
        
        # Step 2: Group data by Voltage Channel ID across segments
        voltage_trials_map: Dict[str, List[np.ndarray]] = {}
        current_trials_map: Dict[str, List[np.ndarray]] = {}
        channel_metadata_map: Dict[str, Dict[str, Any]] = {}
        current_units_map: Dict[str, str] = {}
        processed_voltage_ids = set()

        for seg_index, paired_signals_in_segment in enumerate(segment_signal_pairs):
            for voltage_phys_id, signals in paired_signals_in_segment.items():
                voltage_sig = signals.get('voltage')
                current_sig = signals.get('current')
                
                if voltage_sig is None: continue # Should not happen if keyed correctly, but safety check

                # Determine the Domain Channel ID (using header/annotations if available, fallback)
                # This reuses part of the previous logic but applies it here
                header_info = header_channel_info.get(voltage_phys_id) # Use physical ID for header lookup?
                domain_chan_id: str; channel_name: str
                original_neo_chan_id = str(getattr(voltage_sig, 'channel_index', voltage_phys_id))
                if header_info:
                    domain_chan_id = header_info['id']; channel_name = header_info['name']
                else: # Fallback using annotations or physical ID (simplified)
                    annotations = getattr(voltage_sig, 'annotations', {})
                    ann_id = annotations.get('channel_id')
                    ann_name = annotations.get('channel_name')
                    if ann_id is not None: domain_chan_id = str(ann_id); channel_name = str(ann_name) if ann_name else f"AnnCh_{domain_chan_id}"
                    elif ann_name is not None: domain_chan_id = str(ann_name); channel_name = str(ann_name)
                    else: domain_chan_id = f"PhysicalChannel_{original_neo_chan_id}"; channel_name = domain_chan_id

                # Store metadata ONCE per domain_chan_id
                if domain_chan_id not in processed_voltage_ids:
                    try:
                        units_obj = voltage_sig.units
                        units = str(units_obj.dimensionality) if hasattr(units_obj, 'dimensionality') else 'unknown'
                        units = 'unknown' if 'dimensionless' in units.lower() else units
                        sampling_rate = float(voltage_sig.sampling_rate.magnitude)
                        t_start_segment = float(voltage_sig.t_start.magnitude)
                        
                        # Extract other metadata (gain, offset etc.) from voltage signal
                        annotations = getattr(voltage_sig, 'annotations', {})
                        electrode_description=annotations.get('description', annotations.get('comment', None)); electrode_location=annotations.get('location', None)
                        electrode_filtering=annotations.get('filtering', None); electrode_gain=float(getattr(voltage_sig, 'gain', np.nan)); electrode_gain=annotations.get('gain', electrode_gain) if np.isnan(electrode_gain) else electrode_gain
                        electrode_offset=float(getattr(voltage_sig, 'offset', np.nan)); electrode_offset=annotations.get('offset', electrode_offset) if np.isnan(electrode_offset) else electrode_offset
                        electrode_resistance=annotations.get('resistance', None); electrode_seal=annotations.get('seal', None)
                        
                        channel_metadata_map[domain_chan_id] = { 'name': channel_name, 'units': units, 'sampling_rate': sampling_rate, 't_start': t_start_segment, 'original_neo_id': original_neo_chan_id, 'electrode_description': electrode_description, 'electrode_location': electrode_location, 'electrode_filtering': electrode_filtering, 'electrode_gain': electrode_gain, 'electrode_offset': electrode_offset, 'electrode_resistance': electrode_resistance, 'electrode_seal': electrode_seal }
                        voltage_trials_map[domain_chan_id] = []
                        current_trials_map[domain_chan_id] = [] # Initialize current list too
                        processed_voltage_ids.add(domain_chan_id)
                        log.debug(f"Initialized group for Domain Channel ID='{domain_chan_id}', Name='{channel_name}' based on Seg {seg_index}")

                        # Set recording-level properties from the very first valid voltage signal
                        if recording.sampling_rate is None:
                            recording.sampling_rate = sampling_rate
                            recording.t_start = t_start_segment
                            log.info(f"Set recording props: Rate={recording.sampling_rate:.2f} Hz, t0={recording.t_start:.4f} s")
                    except Exception as e_meta:
                        log.error(f"Error extracting metadata for DomainID '{domain_chan_id}' from Seg {seg_index}: {e_meta}")
                        continue # Skip processing this channel ID if metadata failed
                
                # Append data for this segment/trial
                try:
                    voltage_data = np.ravel(voltage_sig.magnitude)
                    voltage_trials_map[domain_chan_id].append(voltage_data)
                    
                    if current_sig is not None:
                        current_data = np.ravel(current_sig.magnitude)
                        current_trials_map[domain_chan_id].append(current_data)
                        # Store current units if not already stored for this domain_chan_id
                        if domain_chan_id not in current_units_map:
                             curr_units_obj = current_sig.units
                             curr_units_str = str(curr_units_obj.dimensionality) if hasattr(curr_units_obj, 'dimensionality') else 'unknown'
                             current_units_map[domain_chan_id] = 'unknown' if 'dimensionless' in curr_units_str.lower() else curr_units_str
                    else:
                        # If current is missing for this trial, append placeholder? Or handle downstream?
                        # Appending None might complicate averaging. Appending zeros or NaNs? Or skip?
                        # Let's skip appending to current_trials_map if current_sig is None for this trial.
                        # Downstream averaging needs to handle potentially shorter current_data_trials list.
                        log.debug(f"Skipping current data for DomainID '{domain_chan_id}' in Seg {seg_index} as it was not found/paired.")
                        pass 

                except Exception as e_data:
                    log.error(f"Error extracting data for DomainID '{domain_chan_id}' from Seg {seg_index}: {e_data}")

        # Step 3: Create Domain Channel objects
        if not voltage_trials_map: log.warning(f"No valid channel data extracted from '{filepath.name}'."); return recording
        log.info(f"Creating domain Channel objects for {len(voltage_trials_map)} unique voltage channel IDs.")
        
        for domain_chan_id, voltage_trials_list in voltage_trials_map.items():
            meta = channel_metadata_map[domain_chan_id]
            current_trials_list = current_trials_map.get(domain_chan_id, []) # Get corresponding current trials
            current_units = current_units_map.get(domain_chan_id)
            
            if not voltage_trials_list: log.warning(f"Skipping Channel ID='{domain_chan_id}': No voltage data appended."); continue
            
            try:
                # Create the Channel object using voltage data first
                channel = Channel(id=domain_chan_id, name=meta['name'], units=meta['units'], sampling_rate=meta['sampling_rate'], data_trials=voltage_trials_list)
                
                # Assign voltage-related metadata
                channel.t_start = meta['t_start']; channel.electrode_description = meta['electrode_description']; channel.electrode_location = meta['electrode_location']
                channel.electrode_filtering = meta['electrode_filtering']; channel.electrode_gain = meta['electrode_gain']; channel.electrode_offset = meta['electrode_offset']
                channel.electrode_resistance = meta['electrode_resistance']; channel.electrode_seal = meta['electrode_seal']
                
                # Assign associated current data
                channel.current_data_trials = current_trials_list
                channel.current_units = current_units
                
                # Add channel to recording
                recording.channels[channel.id] = channel
                log.debug(f"Created Domain Ch: ID='{channel.id}', Name='{channel.name}', Units='{channel.units}', Rate={channel.sampling_rate:.2f}, V_Trials={len(voltage_trials_list)}, I_Trials={len(current_trials_list)}, I_Units={current_units}, t0={channel.t_start:.4f}")
            except Exception as e_channel: 
                log.error(f"Failed to create Channel object for ID='{domain_chan_id}': {e_channel}", exc_info=True)

        # --- Final Checks/Adjustments (e.g., duration) ---
        if recording.sampling_rate and recording.t_start is not None and not recording.duration:
            # Estimate duration from the first channel with data
            first_channel_with_data = next((ch for ch in recording.channels.values() if ch.data_trials), None)
            if first_channel_with_data and first_channel_with_data.data_trials:
                try: recording.duration = first_channel_with_data.data_trials[0].shape[0] / recording.sampling_rate
                except Exception: pass
        if recording.duration is not None and recording.duration < 0: log.warning(f"Negative duration ({recording.duration:.3f}s). Setting None."); recording.duration = None
        log.info(f"Translation complete for '{filepath.name}'. Recording has {len(recording.channels)} channels.")
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