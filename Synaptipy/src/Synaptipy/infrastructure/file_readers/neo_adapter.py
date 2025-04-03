"""
Adapter for reading various electrophysiology file formats using the neo library
and translating them into the application's core domain model.
"""

import logging
from pathlib import Path
from typing import Dict, List, Optional, Type, Tuple

import neo.io as nIO
import numpy as np

# Placeholder imports for Core Domain Model and Shared Kernel
# Replace with actual imports once those modules are created
# from ...core.data_model import Recording, Channel, Experiment # Expected Domain Model
# from ...shared.error_handling import FileReadError, UnsupportedFormatError # Expected Exceptions

# --- Placeholder Classes (until Core Domain is implemented) ---
class Channel:
    """Placeholder for Core Domain Channel."""
    def __init__(self, id: str, name: str, units: str, sampling_rate: float, data_trials: List[np.ndarray]):
        self.id = id
        self.name = name
        self.units = units
        self.sampling_rate = sampling_rate
        # Store data as a list of arrays, one array per trial/segment
        self.data_trials = data_trials
        self.t_start = 0.0 # Placeholder, should come from neo signal

class Recording:
    """Placeholder for Core Domain Recording."""
    def __init__(self, source_file: Path):
        self.source_file = source_file
        self.channels: Dict[str, Channel] = {}
        self.sampling_rate: Optional[float] = None
        self.duration: Optional[float] = None
        self.t_start: Optional[float] = None
        self.protocol_name: Optional[str] = None
        self.injected_current: Optional[float] = None
        self.metadata: Dict = {} # For any other misc metadata

class Experiment: # Optional higher-level container
    """Placeholder for Core Domain Experiment."""
    def __init__(self):
        self.recordings: List[Recording] = []
        self.metadata: Dict = {}

# --- Placeholder Exceptions (until Shared Kernel is implemented) ---
class FileReadError(IOError):
    pass
class UnsupportedFormatError(ValueError):
    pass
# --- End Placeholders ---

# Configure logging
log = logging.getLogger(__name__)

# Dictionary of known neo IO classes and their typical extensions
# Kept for reference or potential advanced IO selection logic
NEO_IO_EXTENSIONS = {
    'AlphaOmegaIO':['lsx', 'mpx'],
    'AsciiSignalIO':['txt', 'asc', 'csv', 'tsv'],
    # ... (include all from your original list if needed for reference) ...
    'AxonIO':['abf'],
    'BrainVisionIO':['vhdr'],
    'CedIO':['smr', 'smrx'],
    'IgorIO':['ibw', 'pxp'],
    'IntanIO':['rhd', 'rhs'],
    'NWBIO':['nwb'],
    'NeuroExplorerIO':['nex'],
    'PlexonIO':['plx'],
    'SpikeGLXIO':['meta', 'bin'],
    # ... add others as commonly encountered ...
}

class NeoAdapter:
    """
    Reads electrophysiology files using the neo library and translates the data
    into the application's Core Domain Model (Recording, Channel).
    Handles multiple file formats supported by neo.
    """

    def _get_neo_io_class(self, filepath: Path) -> Type[nIO.BaseIO]:
        """
        Determines the appropriate neo IO class based on the file extension.

        Args:
            filepath: Path object for the input file.

        Returns:
            The neo IO class capable of reading the file.

        Raises:
            UnsupportedFormatError: If no suitable neo IO is found for the extension.
            FileNotFoundError: If the filepath does not exist.
        """
        if not filepath.is_file():
            raise FileNotFoundError(f"File not found: {filepath}")

        extension = filepath.suffix.lower().lstrip('.')

        try:
            # Use neo's built-in mechanism first
            io_class = nIO.get_io(filepath)
            log.info(f"Using neo.get_io() detected IO: {io_class.__name__} for '{filepath.name}'")
            return io_class
        except ValueError as e:
            log.warning(f"neo.get_io() failed for extension '{extension}': {e}. Falling back to manual check.")
            # Fallback: Iterate through known IOs (less robust than neo's internal check)
            for io_name, extensions in NEO_IO_EXTENSIONS.items():
                if extension in extensions:
                    try:
                        io_class = getattr(nIO, io_name)
                        log.info(f"Manually selected IO: {io_name} for extension '{extension}'")
                        return io_class
                    except AttributeError:
                        log.warning(f"IO class '{io_name}' not found in neo.io, skipping.")
                        continue # Should not happen if NEO_IO_EXTENSIONS is correct

            # If loop completes without finding a match
            raise UnsupportedFormatError(
                f"Unsupported file extension '.{extension}'. No neo IO found."
            )
        except Exception as e: # Catch other potential get_io errors
             raise UnsupportedFormatError(
                f"Error determining IO for file {filepath}: {e}"
            )


    def _extract_axon_metadata(self, reader: nIO.BaseIO) -> Tuple[Optional[str], Optional[float]]:
        """
        Extracts protocol name and estimated injected current specifically for AxonIO files.
        Returns (None, None) if extraction fails or reader is not AxonIO.
        """
        protocol_name = None
        injected_current = None

        # Check if it's actually an AxonIO reader and has the necessary info
        # Use isinstance() for robust type checking
        if not isinstance(reader, nIO.AxonIO) or not hasattr(reader, '_axon_info'):
            log.debug("Reader is not AxonIO or lacks _axon_info; skipping Axon metadata extraction.")
            return protocol_name, injected_current

        # Extract Protocol Name
        try:
            protocol_path_raw = reader._axon_info.get('sProtocolPath', b'')
            if isinstance(protocol_path_raw, bytes):
                # Decode bytes, be robust against encoding errors
                protocol_path = protocol_path_raw.decode('utf-8', errors='ignore')
            else:
                protocol_path = str(protocol_path_raw) # Should ideally be bytes, but handle other cases

            if protocol_path:
                # Attempt to get the filename part, handle both Windows and Unix separators
                protocol_name = protocol_path.split('\\')[-1].split('/')[-1]
                # Remove extension if present
                if '.' in protocol_name:
                    protocol_name = protocol_name.rsplit('.', 1)[0]
                log.info(f"Extracted protocol name: {protocol_name}")
            else:
                log.info("Protocol path is empty in Axon metadata.")

        except Exception as e:
            log.warning(f"Could not extract protocol name from AxonIO metadata: {e}", exc_info=True)
            protocol_name = "Extraction Error" # Indicate failure clearly

        # Extract Injected Current (approximation based on command signal range)
        try:
            # Check if the method exists before calling
            if hasattr(reader, 'read_raw_protocol'):
                protocol_raw = reader.read_raw_protocol()
                # protocol_raw structure can vary; common case is list of tuples/lists per segment
                if protocol_raw and isinstance(protocol_raw, list) and protocol_raw[0] and isinstance(protocol_raw[0], (list, tuple)):
                    # Aggregate command signals across segments.
                    # Assume command signal is often the first element in the tuple/list per segment.
                    # This requires knowledge of the specific Axon file structure/protocol.
                    command_signals = []
                    for seg_protocol in protocol_raw:
                        if seg_protocol and isinstance(seg_protocol, (list, tuple)) and len(seg_protocol) > 0:
                           # Check if the first element looks like signal data (numpy array or list of numbers)
                           potential_signal = seg_protocol[0]
                           if isinstance(potential_signal, (np.ndarray, list)):
                               command_signals.append(np.asarray(potential_signal)) # Ensure numpy array
                           else:
                               log.debug(f"Skipping non-array element in segment protocol: {type(potential_signal)}")
                        else:
                             log.debug("Empty or invalid segment protocol structure found.")


                    if command_signals:
                        # Concatenate all command points across segments/trials
                        all_command_points = np.concatenate([cs.ravel() for cs in command_signals])
                        if all_command_points.size > 0:
                            i_min = np.min(all_command_points)
                            i_max = np.max(all_command_points)
                            # This difference is a simple measure, might not be the 'step amplitude'
                            # but represents the range of the command signal.
                            injected_current = np.around(abs(i_max - i_min), 3) # Use more precision
                            log.info(f"Estimated injected current command range (max-min): {injected_current} (units unknown without header info)")
                        else:
                            log.info("Command signals found but contained no data points.")
                    else:
                        log.info("No suitable command signals found in raw protocol for current estimation.")
                else:
                    log.info("Raw protocol format not recognized or empty for current estimation.")
            else:
                log.info("Reader does not support read_raw_protocol() for current estimation.")

        except Exception as e:
            # Catch potential errors during protocol reading or processing
            log.warning(f"Could not estimate injected current from AxonIO: {e}", exc_info=True)

        return protocol_name, injected_current

    def read_recording(self, filepath: Path) -> Recording:
        """
        Reads the specified file using the appropriate neo IO and translates
        it into a Recording object from the Core Domain Model.

        Args:
            filepath: The path to the electrophysiology data file.

        Returns:
            A Recording object containing the data and metadata.

        Raises:
            FileNotFoundError: If the file does not exist.
            UnsupportedFormatError: If the file format is not supported by neo.
            FileReadError: If there's an error during file reading or parsing.
        """
        log.info(f"Attempting to read file: {filepath}")
        filepath = Path(filepath) # Ensure it's a Path object

        io_class = None # Initialize for logging in case of early failure
        try:
            io_class = self._get_neo_io_class(filepath)
            reader = io_class(filename=str(filepath))

            # Read the main data block.
            # 'split-all' ensures each AnalogSignal corresponds to one physical channel per segment.
            # lazy=False loads data immediately. Consider lazy=True for very large files,
            # but requires loading data explicitly later during translation/visualization.
            # Adjust parameters based on memory constraints and performance needs.
            block = reader.read_block(lazy=False, signal_group_mode='split-all')
            log.info(f"Successfully read neo Block using {io_class.__name__}.")

        except (FileNotFoundError, UnsupportedFormatError) as e:
             log.error(f"Pre-read check failed: {e}")
             raise e # Re-raise specific, expected errors
        except Exception as e:
            # Catch potential errors during IO initialization or block reading
            io_name = io_class.__name__ if io_class else "Unknown IO"
            log.error(f"Failed to read file '{filepath.name}' using {io_name}: {e}", exc_info=True)
            # Wrap generic exceptions in our custom error type
            raise FileReadError(f"Error reading file {filepath} with {io_name}: {e}") from e

        if not block or not block.segments:
            log.warning(f"File '{filepath.name}' read successfully but contained no data segments.")
            # Return an empty Recording or raise a different error, depending on desired behavior
            return Recording(source_file=filepath) # Return empty recording

        recording = Recording(source_file=filepath)

        # --- Add extraction of session start time ---
        if hasattr(block, 'rec_datetime') and block.rec_datetime:
            recording.session_start_time_dt = block.rec_datetime
            log.info(f"Extracted session start time from neo block: {recording.session_start_time_dt}")
        else:
            log.warning("Could not extract session start time (rec_datetime) from neo block.")
            recording.session_start_time_dt = None  # Explicitly set to None
        # ---


        # Extract global metadata from neo Block if available
        recording.metadata = block.annotations if block.annotations else {} # Ensure it's a dict
        recording.metadata['neo_block_description'] = block.description
        recording.metadata['neo_file_origin'] = block.file_origin
        # Add any other relevant block-level info here

        # Attempt to extract Axon-specific metadata (won't harm other types)
        proto_name, inj_curr = self._extract_axon_metadata(reader)
        recording.protocol_name = proto_name
        recording.injected_current = inj_curr
        # Add reader type to metadata for context
        recording.metadata['neo_reader_class'] = reader.__class__.__name__


        # Process segments (often correspond to trials or sweeps)
        num_segments = len(block.segments)
        log.info(f"Found {num_segments} segment(s). Translating to domain model...")

        # Temporary storage to group data by physical channel across segments
        # Key: channel_id (preferred) or channel_name (fallback)
        # Value: List of numpy arrays (data for each trial/segment)
        channel_data_map: Dict[str, List[np.ndarray]] = {}
        # Key: channel_id/name, Value: Dict containing metadata like name, units, rate
        channel_metadata_map: Dict[str, Dict] = {}

        # Iterate through segments and the analogsignals within each segment
        for seg_index, segment in enumerate(block.segments):
            log.debug(f"Processing segment {seg_index + 1}/{num_segments}")
            if not segment.analogsignals:
                 log.debug(f"Segment {seg_index + 1} has no analog signals.")
                 continue

            for anasig in segment.analogsignals:
                # With 'split-all', each anasig should represent one channel for this segment
                if anasig.shape[1] != 1:
                    # This shouldn't happen with 'split-all' but check just in case
                    log.warning(f"AnalogSignal in segment {seg_index+1} has unexpected shape {anasig.shape}. Skipping. Expected shape (n_samples, 1).")
                    continue

                # --- Identify the channel ---
                # Prefer channel_id if available in annotations (more robust)
                ch_id = anasig.annotations.get('channel_id', None)
                ch_name = anasig.annotations.get('channel_name', None)

                # Determine a unique key for grouping this channel's data across segments
                if ch_id is not None:
                    map_key = str(ch_id) # Use channel ID as the primary key
                    if ch_name is None: # Try to get name from header if missing in annotation
                       try:
                           # neo headers vary; this is a common pattern but not guaranteed
                           header_ch_name = reader.header['signal_channels'][ch_id]['name']
                           ch_name = header_ch_name
                           log.debug(f"Retrieved channel name '{ch_name}' from header for ID {ch_id}")
                       except (KeyError, IndexError, TypeError):
                           ch_name = f'Ch_{ch_id}' # Fallback name if header lookup fails
                           log.debug(f"Using fallback name '{ch_name}' for ID {ch_id}")
                elif ch_name is not None:
                    # Fallback to using channel name if ID is missing
                    map_key = ch_name
                    log.warning(f"Channel ID missing for signal '{ch_name}' in segment {seg_index+1}. Using name as key. Ensure names are unique!")
                else:
                    # If both ID and name are missing, generate a placeholder key (least reliable)
                    placeholder_key = f"UnnamedSig_{anasig.name or id(anasig)}"
                    map_key = placeholder_key
                    ch_name = placeholder_key # Use the key as the name too
                    log.error(f"Channel ID and Name missing for a signal in segment {seg_index+1}. Using placeholder key '{map_key}'. Data might be grouped incorrectly.")

                # --- Extract data and metadata for this signal instance ---
                try:
                    data = np.ravel(anasig.magnitude) # Get the data array for this segment
                    units = str(anasig.units.dimensionality) # Get units as string (e.g., 'mV', 'pA', 'V')
                    sampling_rate = float(anasig.sampling_rate.magnitude)
                    t_start = float(anasig.t_start.magnitude) # Time of the first sample in this segment
                except Exception as e:
                    log.error(f"Error extracting data/metadata for signal {map_key} in segment {seg_index+1}: {e}", exc_info=True)
                    continue # Skip this problematic signal

                # --- Store or update metadata for this channel (using the map_key) ---
                if map_key not in channel_metadata_map:
                    # First time encountering this channel
                    channel_metadata_map[map_key] = {
                        'name': ch_name,
                        'units': units,
                        'sampling_rate': sampling_rate,
                        't_start': t_start, # Store t_start from the first segment encountered
                        'id': ch_id # Store original ID if available, even if name was used as key
                    }
                    channel_data_map[map_key] = [] # Initialize the list for data arrays
                    log.debug(f"Initializing channel '{ch_name}' (key: {map_key}) with rate {sampling_rate} {anasig.sampling_rate.units}")
                else:
                    # Check for consistency if channel already seen
                    existing_meta = channel_metadata_map[map_key]
                    if existing_meta['sampling_rate'] != sampling_rate:
                         log.warning(f"Inconsistent sampling rate for channel '{ch_name}' (key: {map_key}) across segments! Using rate from first segment ({existing_meta['sampling_rate']}). Segment {seg_index+1} rate: {sampling_rate}")
                         # Keep the first rate encountered. Could alternatively raise error or handle differently.
                    if existing_meta['units'] != units:
                         log.warning(f"Inconsistent units for channel '{ch_name}' (key: {map_key}) across segments! Using units from first segment ('{existing_meta['units']}'). Segment {seg_index+1} units: '{units}'")
                         # Keep the first units encountered.

                # --- Append the data for this trial/segment ---
                channel_data_map[map_key].append(data)

                # --- Set global recording properties from the first valid signal encountered ---
                if recording.sampling_rate is None:
                    recording.sampling_rate = sampling_rate
                    recording.t_start = t_start # Overall recording start time assumed from first signal
                    # Estimate duration from the first signal's data length
                    # This assumes all segments/trials have the same length for this channel
                    if sampling_rate > 0:
                        recording.duration = data.shape[0] / sampling_rate
                    else:
                        recording.duration = 0
                    log.info(f"Set recording sampling rate to {recording.sampling_rate} Hz and estimated duration to {recording.duration:.3f} s from first signal.")

        # --- Create final Core Domain Channel objects from the aggregated data ---
        if not channel_data_map:
             log.warning("No valid channel data could be extracted from any segment.")
             # Return the recording object, potentially empty of channels
             return recording

        log.info(f"Aggregated data for {len(channel_data_map)} unique channel(s). Creating domain objects...")
        for map_key, data_trials in channel_data_map.items():
            meta = channel_metadata_map[map_key]
            if not data_trials: # Skip if no data was actually added (e.g., due to errors)
                 log.warning(f"Skipping channel '{meta['name']}' (key: {map_key}) as no data trials were collected.")
                 continue

            # Use the map_key (preferably derived from channel ID) as the domain model ID
            channel_domain_id = map_key

            # Create the Channel domain object
            channel = Channel(
                id=channel_domain_id,
                name=meta['name'],
                units=meta['units'],
                sampling_rate=meta['sampling_rate'], # Use the consistent rate stored in meta
                data_trials=data_trials # List of numpy arrays, one per segment/trial
            )
            # Assign t_start from the first segment where this channel was seen
            channel.t_start = meta['t_start']

            # Add the created Channel object to the Recording's channel dictionary
            recording.channels[channel.id] = channel
            log.debug(f"Created Domain Channel: ID='{channel.id}', Name='{channel.name}', Units='{channel.units}', Trials={len(data_trials)}, Samples/Trial={data_trials[0].shape[0] if data_trials else 0}")

        # --- Final checks and logging ---
        if recording.sampling_rate is None and recording.channels:
            # Fallback if, for some reason, the global rate wasn't set initially
            first_channel = next(iter(recording.channels.values()))
            recording.sampling_rate = first_channel.sampling_rate
            recording.t_start = first_channel.t_start
            if first_channel.data_trials and first_channel.sampling_rate > 0:
                 recording.duration = first_channel.data_trials[0].shape[0] / first_channel.sampling_rate
            log.warning("Recording sampling rate was not set during segment iteration; derived from first created channel.")

        log.info(f"Successfully translated '{filepath.name}'. Recording contains {len(recording.channels)} channel(s). Sampling Rate: {recording.sampling_rate} Hz.")
        return recording


# --- Example Usage (for testing this module directly) ---
if __name__ == '__main__':
    # Configure basic logging to see output when running the script directly
    logging.basicConfig(
        level=logging.INFO, # Set to DEBUG for more verbose output
        format='%(asctime)s - %(name)s - [%(levelname)s] - %(message)s'
    )

    log.info("Running NeoAdapter example usage...")

    # --- IMPORTANT: Replace with the actual path to a test file ---
    # Find a small sample file (e.g., .abf, .smr, .nex) supported by neo
    test_file_path = Path("path/to/your/test_data_file.abf") # <-- CHANGE THIS PATH
    # -------------------------------------------------------------

    if not test_file_path.exists():
        log.error(f"Test file not found: {test_file_path}")
        log.warning("Please update the 'test_file_path' variable in the example usage block.")
    else:
        adapter = NeoAdapter()
        try:
            # Call the main method to read and translate the file
            recording_data = adapter.read_recording(test_file_path)

            # --- Print a summary of the loaded Recording object ---
            print("\n" + "="*30)
            print("   RECORDING SUMMARY")
            print("="*30)
            print(f"Source File:       {recording_data.source_file.name}")
            print(f"Sampling Rate:     {recording_data.sampling_rate} Hz")
            print(f"Est. Duration:     {recording_data.duration:.4f} s" if recording_data.duration is not None else "N/A")
            print(f"Start Time (t0):   {recording_data.t_start} s" if recording_data.t_start is not None else "N/A")
            print(f"Protocol Name:     {recording_data.protocol_name if recording_data.protocol_name else 'N/A'}")
            print(f"Inj. Current Est.: {recording_data.injected_current if recording_data.injected_current else 'N/A'}")
            print(f"Neo Reader Used:   {recording_data.metadata.get('neo_reader_class', 'N/A')}")
            print(f"Number of Channels:{len(recording_data.channels)}")
            print("-"*30)

            if not recording_data.channels:
                print("No channels were found or loaded.")
            else:
                print("Channels:")
                for ch_id, channel in recording_data.channels.items():
                    num_trials = len(channel.data_trials)
                    samples_per_trial = channel.data_trials[0].shape[0] if num_trials > 0 else 0
                    print(f"  - ID: {ch_id:<15} Name: {channel.name:<20} Units: {channel.units:<5} "
                          f"Trials: {num_trials:<4} Samples/Trial: {samples_per_trial}")
            print("="*30 + "\n")

        except FileNotFoundError as e:
            log.error(f"File not found during example: {e}")
        except UnsupportedFormatError as e:
            log.error(f"Unsupported file format during example: {e}")
        except FileReadError as e:
            log.error(f"Error reading file during example: {e}", exc_info=True) # Show traceback for read errors
        except Exception as e:
            # Catch any other unexpected errors during the example run
            log.error(f"An unexpected error occurred during example usage: {e}", exc_info=True)

    # You can add more test cases here, e.g., for non-existent files or unsupported extensions
    # Example: Test non-existent file
    # try:
    #     log.info("\\nTesting non-existent file...")
    #     adapter = NeoAdapter()
    #     adapter.read_recording(Path("./non_existent_file.hopefully"))
    # except FileNotFoundError as e:
    #     log.info(f"Successfully caught expected error: {e}")
    # except Exception as e:
    #     log.error(f"Caught unexpected error: {e}", exc_info=True)

    # Example: Test unsupported extension
    # try:
    #    log.info("\\nTesting unsupported extension...")
    #    adapter = NeoAdapter()
    #    dummy_unsupported = Path("./dummy.unsupported_xyz")
    #    dummy_unsupported.touch() # Create empty file
    #    adapter.read_recording(dummy_unsupported)
    #    dummy_unsupported.unlink() # Clean up
    # except UnsupportedFormatError as e:
    #    log.info(f"Successfully caught expected error: {e}")
    #    if dummy_unsupported.exists(): dummy_unsupported.unlink() # Clean up
    # except Exception as e:
    #    log.error(f"Caught unexpected error: {e}", exc_info=True)
    #    if dummy_unsupported.exists(): dummy_unsupported.unlink() # Clean up

    log.info("NeoAdapter example usage finished.")