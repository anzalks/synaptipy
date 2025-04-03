# -*- coding: utf-8 -*-
"""
Adapter for reading various electrophysiology file formats using the neo library
and translating them into the application's core domain model.
IO class selection uses a predefined dictionary mapping extensions to IO names.
Attempts to use reader header information for robust channel identification.
"""
__author__ = "Anzal KS"
__copyright__ = "Copyright 2024-, Anzal KS"
__maintainer__ = "Anzal KS"
__email__ = "anzalks@ncbs.res.in"

import logging
from pathlib import Path
from typing import Dict, List, Optional, Type, Tuple, Any

import neo.io as nIO
import numpy as np

# Import from our package structure
from Synaptipy.core.data_model import Recording, Channel
from Synaptipy.shared.error_handling import FileReadError, UnsupportedFormatError

# Configure logging
log = logging.getLogger(__name__)

# Dictionary mapping IO Class Names to extensions (Based on user script)
IODict = { # Using user-provided dict name
    'AlphaOmegaIO':['lsx', 'mpx'], 'AsciiImageIO':[], 'AsciiSignalIO':['txt', 'asc', 'csv', 'tsv'],
    'AsciiSpikeTrainIO':['txt'], 'AxographIO':['axgd', 'axgx'], 'AxonIO':['abf'],
    'AxonaIO':['bin', 'set'] + [str(i) for i in range(1, 33)], # Simplified range
    'BCI2000IO':['dat'], 'BiocamIO':['h5', 'brw'],
    'BlackrockIO':['ns1', 'ns2', 'ns3', 'ns4', 'ns5', 'ns6', 'nev', 'sif', 'ccf'],
    'BrainVisionIO':['vhdr'], 'BrainwareDamIO':['dam'], 'BrainwareF32IO':['f32'], 'BrainwareSrcIO':['src'],
    'CedIO':['smr', 'smrx'], 'EDFIO':['edf'], 'ElanIO':['eeg'], 'IgorIO':['ibw', 'pxp'],
    'IntanIO':['rhd', 'rhs', 'dat'], 'KlustaKwikIO':['fet', 'clu', 'res', 'spk'], 'KwikIO':['kwik'],
    'MEArecIO':['h5'], 'MaxwellIO':['h5'], 'MedIO':['medd', 'rdat', 'ridx'], 'MicromedIO':['trc', 'TRC'],
    'NWBIO':['nwb'], 'NeoMatlabIO':['mat'], 'NestIO':['gdf', 'dat'],
    'NeuralynxIO':['nse', 'ncs', 'nev', 'ntt', 'nvt', 'nrd'], 'NeuroExplorerIO':['nex'],
    'NeuroScopeIO':['xml', 'dat', 'lfp', 'eeg'], 'NeuroshareIO':['nsn'], 'NixIO':['h5', 'nix'],
    'OpenEphysBinaryIO':['oebin'], # Removed others, often need more info
    'OpenEphysIO':['continuous', 'openephys', 'spikes', 'events', 'xml'], 'PhyIO':['npy', 'mat', 'tsv', 'dat'],
    'PickleIO':['pkl', 'pickle'], 'Plexon2IO':['pl2'], 'PlexonIO':['plx'],
    'RawBinarySignalIO':['raw', 'bin', 'dat'], 'RawMCSIO':['raw'], 'Spike2IO':['smr', 'smrx'],
    'SpikeGLXIO':['bin'], 'SpikeGadgetsIO':['rec'], 'StimfitIO':['abf', 'dat', 'axgx', 'axgd', 'cfs'],
    'TdtIO':['tbk', 'tdx', 'tev', 'tin', 'tnt', 'tsq', 'sev', 'txt'], 'TiffIO':['tiff'], 'WinWcpIO':['wcp'],
}

class NeoAdapter:
    """
    Reads ephys files using neo, translating data to the Core Domain Model.
    Uses a fixed dictionary (IODict) for IO selection and prioritizes reader
    header for channel identification.
    """

    def _get_neo_io_class(self, filepath: Path) -> Type[Any]:
        """Determines neo IO class using the predefined IODict."""
        if not filepath.is_file(): raise FileNotFoundError(f"File not found: {filepath}")
        extension = filepath.suffix.lower().lstrip('.'); log.debug(f"Ext: '{extension}'")
        available_io_names = [io_name for io_name, exts in IODict.items() if extension in exts]
        if not available_io_names: raise UnsupportedFormatError(f"Unsupported extension '.{extension}'. No IO found in IODict.")
        selected_io_name = available_io_names[0]
        if len(available_io_names) > 1: log.warning(f"Multiple IOs for '{extension}': {available_io_names}. Using '{selected_io_name}'.")
        else: log.info(f"Selected IO: '{selected_io_name}' for '{extension}'.")
        try: return getattr(nIO, selected_io_name)
        except AttributeError: log.error(f"IODict Error: '{selected_io_name}' not in neo.io."); raise ValueError(f"Invalid IO name '{selected_io_name}'")
        except Exception as e: log.error(f"Error getting IO '{selected_io_name}': {e}"); raise FileReadError(f"Error accessing IO '{selected_io_name}': {e}")

    def _extract_axon_metadata(self, reader: nIO.AxonIO) -> Tuple[Optional[str], Optional[float]]:
        """Extracts metadata specifically for AxonIO files."""
        protocol_name, injected_current = None, None
        if not isinstance(reader, nIO.AxonIO): return protocol_name, injected_current
        # Protocol Name
        try:
            if hasattr(reader, '_axon_info') and reader._axon_info and 'sProtocolPath' in reader._axon_info:
                protocol_path_raw = reader._axon_info['sProtocolPath']
                protocol_path = protocol_path_raw.decode('utf-8', 'ignore') if isinstance(protocol_path_raw, bytes) else str(protocol_path_raw)
                if protocol_path: filename = protocol_path.split('\\')[-1].split('/')[-1]; protocol_name = filename.rsplit('.', 1)[0] if '.' in filename else filename; log.info(f"Protocol name: {protocol_name}")
                else: log.info("Protocol path empty.")
            else: log.info("Protocol path not found in Axon metadata.")
        except Exception as e: log.warning(f"Protocol name extraction failed: {e}"); protocol_name = "Extraction Error"
        # Injected Current
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
                                if command_signal_array.size > 0: all_command_signals.append(command_signal_array)
                    if all_command_signals:
                        all_command_points = np.concatenate(all_command_signals)
                        if all_command_points.size > 0: current_range = np.ptp(all_command_points); injected_current = np.around(current_range, 3); log.info(f"Est. current range (max-min): {injected_current}")
                        else: log.info("Command signals empty.")
                    else: log.info("No suitable command signals found.")
                else: log.info("read_raw_protocol() empty/non-list.")
            else: log.info("Reader lacks read_raw_protocol().")
        except Exception as e: log.warning(f"Current estimation failed: {e}")
        return protocol_name, injected_current

    def read_recording(self, filepath: Path) -> Recording:
        """Reads ephys file, translates to Recording object using header info preferentially."""
        log.info(f"Reading file: {filepath}")
        filepath = Path(filepath)

        io_class = None; reader = None # Initialize
        try:
            io_class = self._get_neo_io_class(filepath)
            reader = io_class(filename=str(filepath)) # Create reader instance

            # --- Get Header Info for Channel Mapping (if available) --- START ---
            header_channel_info = {}  # Dict to store {original_index: {'id': id, 'name': name}}
            try:
                # Check for header and signal_channels attribute
                if hasattr(reader, 'header') and reader.header and \
                        'signal_channels' in reader.header and reader.header['signal_channels'] is not None:

                    signal_channels_header = reader.header['signal_channels']
                    log.debug(
                        f"Processing 'signal_channels' header (type: {type(signal_channels_header)}): {signal_channels_header}")

                    # Check if it's list-like (list, tuple, ndarray)
                    if hasattr(signal_channels_header, '__len__') and hasattr(signal_channels_header, '__getitem__'):
                        for idx, header_entry in enumerate(signal_channels_header):
                            ch_name = f'HeaderCh_{idx}'  # Default name
                            ch_id = str(idx)  # Default ID

                            # Try extracting based on common patterns
                            try:
                                if isinstance(header_entry, dict):
                                    # Try common dictionary keys
                                    ch_name_try = header_entry.get('name', header_entry.get('label', header_entry.get(
                                        'channel_name', ch_name)))
                                    ch_id_try = header_entry.get('id', header_entry.get('channel_id', ch_id))
                                elif hasattr(header_entry, 'dtype') and hasattr(header_entry.dtype,
                                                                                'names'):  # Numpy structured array
                                    # Try common field names
                                    if 'name' in header_entry.dtype.names:
                                        ch_name_try = header_entry['name']
                                    elif 'label' in header_entry.dtype.names:
                                        ch_name_try = header_entry['label']
                                    elif 'channel_name' in header_entry.dtype.names:
                                        ch_name_try = header_entry['channel_name']
                                    else:
                                        ch_name_try = ch_name  # Keep default if no known name field

                                    if 'id' in header_entry.dtype.names:
                                        ch_id_try = header_entry['id']
                                    elif 'channel_id' in header_entry.dtype.names:
                                        ch_id_try = header_entry['channel_id']
                                    else:
                                        ch_id_try = ch_id  # Keep default if no known id field
                                else:
                                    # Fallback for other types (e.g., simple list of strings?)
                                    log.warning(
                                        f"Header entry type {type(header_entry)} not explicitly handled for name/id extraction.")
                                    ch_name_try = str(header_entry) if isinstance(header_entry,
                                                                                  (str, bytes)) else ch_name
                                    ch_id_try = ch_id

                                # Decode if bytes and assign if extraction succeeded
                                if isinstance(ch_name_try, bytes):
                                    ch_name = ch_name_try.decode('utf-8', 'ignore')
                                else:
                                    ch_name = str(ch_name_try)  # Ensure string

                                if isinstance(ch_id_try, bytes):
                                    ch_id = ch_id_try.decode('utf-8', 'ignore')
                                else:
                                    ch_id = str(ch_id_try)  # Ensure string

                            except Exception as e_inner:
                                log.warning(
                                    f"Could not fully parse header entry {idx} ({header_entry}): {e_inner}. Using defaults.")
                                # Keep default ch_name, ch_id assigned above

                            # Store whatever we got (even if it's the default)
                            header_channel_info[idx] = {'id': ch_id, 'name': ch_name}
                            log.debug(f"Header map: Index {idx} -> ID: {ch_id}, Name: {ch_name}")
                    else:
                        log.warning("'signal_channels' header is not list-like. Cannot extract channel info by index.")

                else:
                    log.warning(
                        "Reader header missing, lacks 'signal_channels', or 'signal_channels' is None. Relying on signal annotations or index.")
            except Exception as e:
                log.warning(f"Could not process reader header for channel info: {e}",
                            exc_info=True)  # Log full traceback for unexpected header errors
            # --- Get Header Info for Channel Mapping --- END ---


            # --- Read Data Block ---
            block = reader.read_block(lazy=False, signal_group_mode='split-all')
            log.info(f"Read neo Block using {io_class.__name__}.")

        except (FileNotFoundError, UnsupportedFormatError) as e: log.error(f"Pre-read check failed: {e}"); raise e
        except Exception as e: io_name = io_class.__name__ if io_class else "Unknown IO"; log.error(f"Failed read '{filepath.name}' using {io_name}: {e}", exc_info=True); raise FileReadError(f"Error reading {filepath} with {io_name}: {e}") from e

        if not block or not block.segments: log.warning(f"'{filepath.name}' has no data segments."); return Recording(source_file=filepath)

        # --- Translation Logic ---
        recording = Recording(source_file=filepath)
        # Extract session start time
        if hasattr(block, 'rec_datetime') and block.rec_datetime: recording.session_start_time_dt = block.rec_datetime; log.info(f"Extracted session start time: {recording.session_start_time_dt}")
        else: log.warning("Could not extract session start time."); recording.session_start_time_dt = None
        # Extract other metadata
        recording.metadata = block.annotations if block.annotations else {}; recording.metadata['neo_block_description'] = block.description; recording.metadata['neo_file_origin'] = block.file_origin
        if reader: recording.metadata['neo_reader_class'] = reader.__class__.__name__ # Add reader info
        # Axon specific
        if isinstance(reader, nIO.AxonIO): proto_name, inj_curr = self._extract_axon_metadata(reader); recording.protocol_name = proto_name; recording.injected_current = inj_curr

        # Process segments
        num_segments = len(block.segments); log.info(f"Processing {num_segments} segment(s)...")
        channel_data_map: Dict[str, List[np.ndarray]] = {} # Key: Domain Channel ID (from header ID or placeholder)
        channel_metadata_map: Dict[str, Dict] = {} # Key: Domain Channel ID

        for seg_index, segment in enumerate(block.segments):
            log.debug(f"Segment {seg_index + 1}/{num_segments}")
            if not segment.analogsignals: continue

            for sig_index_in_segment, anasig in enumerate(segment.analogsignals):
                if anasig.shape[1] != 1: log.warning(f"Skip multi-col signal seg={seg_index}, idx={sig_index_in_segment}, shape={anasig.shape}"); continue

                # --- NEW Channel Identification Logic --- START ---
                domain_chan_id = None # The ID we will use for our Channel object
                channel_name = None   # The name we will use
                original_neo_chan_id = None # Store the ID from neo header if found

                # 1. Try using Header Info based on signal's index in segment
                header_info = header_channel_info.get(sig_index_in_segment)
                if header_info:
                    domain_chan_id = header_info['id'] # Use ID from header map
                    channel_name = header_info['name']
                    original_neo_chan_id = domain_chan_id # Store for metadata if needed
                    log.debug(f"Seg {seg_index}, Sig Idx {sig_index_in_segment}: Found header info -> ID: {domain_chan_id}, Name: {channel_name}")
                else:
                    # 2. Try using Annotations on the AnalogSignal (less reliable)
                    ann_id = anasig.annotations.get('channel_id', None)
                    ann_name = anasig.annotations.get('channel_name', None)
                    if ann_id is not None:
                        domain_chan_id = str(ann_id) # Use annotation ID
                        channel_name = ann_name if ann_name else f"AnnCh_{domain_chan_id}"
                        log.debug(f"Seg {seg_index}, Sig Idx {sig_index_in_segment}: No header match. Found annotation -> ID: {domain_chan_id}, Name: {channel_name}")
                    elif ann_name is not None:
                        domain_chan_id = ann_name # Fallback to using name as ID
                        channel_name = ann_name
                        log.warning(f"Seg {seg_index}, Sig Idx {sig_index_in_segment}: No header/ann_id. Using Annotation Name '{channel_name}' as ID. Ensure unique!")
                    else:
                        # 3. Fallback to Placeholder based on index in segment
                        domain_chan_id = f"PhysicalChannel_{sig_index_in_segment}"
                        channel_name = domain_chan_id # Use placeholder as name too
                        log.warning(f"Seg {seg_index}, Sig Idx {sig_index_in_segment}: No header/annotation ID/Name. Using Fallback ID '{domain_chan_id}'. Assumes consistent signal order.")
                # --- NEW Channel Identification Logic --- END ---

                # --- Extract Data and Core Metadata ---
                try:
                    data = np.ravel(anasig.magnitude)
                    units_obj = anasig.units; units = str(units_obj.dimensionality) if hasattr(units_obj, 'dimensionality') else 'unknown'; units = units if units and units.lower() != 'dimensionless' else 'dimensionless'
                    sampling_rate = float(anasig.sampling_rate.magnitude)
                    t_start_segment = float(anasig.t_start.magnitude) # Start time of this segment's data relative to block start
                except Exception as e: log.error(f"Error extracting data/meta for ChID '{domain_chan_id}' in seg {seg_index}: {e}"); continue

                # --- Store/Update Channel Info using domain_chan_id ---
                map_key = domain_chan_id # Use the derived ID as the key for grouping
                if map_key not in channel_metadata_map:
                    channel_metadata_map[map_key] = {
                        'name': channel_name, 'units': units, 'sampling_rate': sampling_rate,
                        't_start': t_start_segment, # Store t_start of the FIRST segment encountered
                        'original_neo_id': original_neo_chan_id, # Store original ID from header if available
                    }
                    channel_data_map[map_key] = []
                    log.debug(f"Initialized channel group: Key='{map_key}', Name='{channel_name}', Rate={sampling_rate}, Units='{units}'")
                else: # Consistency checks
                    existing_meta = channel_metadata_map[map_key]
                    if not np.isclose(existing_meta['sampling_rate'], sampling_rate): log.warning(f"Inconsistent Rate! Ch='{map_key}', {existing_meta['sampling_rate']} vs {sampling_rate}")
                    if existing_meta['units'] != units: log.warning(f"Inconsistent Units! Ch='{map_key}', {existing_meta['units']} vs {units}")

                # Append data for this trial/segment
                channel_data_map[map_key].append(data)

                # Set Global Recording Properties (from first valid signal)
                if recording.sampling_rate is None:
                    recording.sampling_rate = sampling_rate
                    recording.t_start = t_start_segment # Base recording start on first segment's data start
                    recording.duration = data.shape[0] / sampling_rate if sampling_rate > 0 else 0
                    log.info(f"Set recording props: Rate={recording.sampling_rate:.2f}Hz, t0={recording.t_start:.4f}s, dur={recording.duration:.3f}s")

        # --- Create Core Domain Channel objects ---
        if not channel_data_map: log.warning("No channel data extracted."); return recording
        log.info(f"Creating domain objects for {len(channel_data_map)} channel groups.")
        for map_key, data_trials in channel_data_map.items():
            meta = channel_metadata_map[map_key]
            if not data_trials: log.warning(f"Skipping group '{map_key}': No data."); continue
            # Use the map_key (derived channel ID) as the ID for the domain Channel object
            channel = Channel( id=map_key, name=meta['name'], units=meta['units'],
                              sampling_rate=meta['sampling_rate'], data_trials=data_trials )
            channel.t_start = meta['t_start'] # Assign t_start from first segment encountered
            recording.channels[channel.id] = channel # Add using the same ID
            log.debug(f"Created Domain Channel: ID='{channel.id}', Name='{channel.name}', Units='{channel.units}', Trials={len(data_trials)}")

        # Final fallback checks (if global props somehow missed)
        if recording.sampling_rate is None and recording.channels:
            first_channel = next(iter(recording.channels.values())); recording.sampling_rate = first_channel.sampling_rate; recording.t_start = first_channel.t_start
            if first_channel.data_trials and first_channel.sampling_rate > 0: recording.duration = first_channel.data_trials[0].shape[0] / first_channel.sampling_rate
            log.warning("Recording props derived from first channel fallback.")

        log.info(f"Translation complete for '{filepath.name}'. Found {len(recording.channels)} channels.")
        return recording


# --- Example Usage Block (Keep for testing, ensure path is updated) ---
if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s [%(levelname)s] %(message)s')
    log.info("Running NeoAdapter example (IODict lookup, header priority)...")
    test_file_path = Path("path/to/your/test_data_file.abf") # <-- CHANGE THIS
    if not test_file_path.exists(): log.error(f"Test file not found: {test_file_path}. Update path.")
    else:
        adapter = NeoAdapter()
        try:
            recording_data = adapter.read_recording(test_file_path)
            print("\n--- Recording Summary ---")
            print(f"Source: {recording_data.source_file.name}"); print(f"Sampling Rate: {recording_data.sampling_rate} Hz"); print(f"Duration: {recording_data.duration} s")
            print(f"Session Start: {recording_data.session_start_time_dt}"); print(f"Protocol: {recording_data.protocol_name}"); print(f"Inject Current Range: {recording_data.injected_current}")
            print(f"Num Channels: {len(recording_data.channels)}")
            for ch_id, channel in recording_data.channels.items(): print(f"  Ch ID: {ch_id}, Name: {channel.name}, Units: {channel.units}, Trials: {len(channel.data_trials)}")
        except Exception as e: print(f"\nError during example: {e}"); log.exception("Exception in example")
    log.info("NeoAdapter example finished.")