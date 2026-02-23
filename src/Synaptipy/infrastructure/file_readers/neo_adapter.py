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

import sys
import logging
from pathlib import Path
from typing import Dict, List, Optional, Type, Tuple

import neo  # Added missing import
import neo.io as nIO  # Keep original import style
import numpy as np

# Import from our package structure
from Synaptipy.infrastructure.file_readers.neo_source_handle import NeoSourceHandle
from Synaptipy.core.data_model import Recording, Channel
from Synaptipy.shared.error_handling import (
    FileReadError,
    UnsupportedFormatError,
    SynaptipyFileNotFoundError,
    UnitError,
)
from Synaptipy.core.signal_processor import validate_sampling_rate

# Apply Patches
try:
    from Synaptipy.infrastructure.neo_patches import apply_winwcp_patch

    apply_winwcp_patch()
except (ImportError, AttributeError) as e:
    logging.getLogger(__name__).warning(f"Failed to apply Neo patches: {e}")

log = logging.getLogger(__name__)

# --- Dictionary mapping IO Class Names to extensions (Source of truth) ---
IODict = {
    "AlphaOmegaIO": ["lsx", "mpx"],
    "AsciiImageIO": [],
    "AsciiSignalIO": ["txt", "asc", "csv", "tsv"],
    "AsciiSpikeTrainIO": ["txt"],
    "AxographIO": ["axgd", "axgx"],
    "AxonIO": ["abf"],
    "AxonaIO": ["bin", "set"] + [str(i) for i in range(1, 33)],
    "BCI2000IO": ["dat"],
    "BiocamIO": ["h5", "brw"],
    "BlackrockIO": ["ns1", "ns2", "ns3", "ns4", "ns5", "ns6", "nev", "sif", "ccf"],
    "BrainVisionIO": ["vhdr"],
    "BrainwareDamIO": ["dam"],
    "BrainwareF32IO": ["f32"],
    "BrainwareSrcIO": ["src"],
    "CedIO": ["smr", "smrx"],
    "EDFIO": ["edf"],
    "ElanIO": ["eeg"],
    "IgorIO": ["ibw", "pxp"],
    "IntanIO": ["rhd", "rhs", "dat"],
    "KlustaKwikIO": ["fet", "clu", "res", "spk"],
    "KwikIO": ["kwik"],
    "MEArecIO": ["h5"],
    "MaxwellIO": ["h5"],
    "MedIO": ["medd", "rdat", "ridx"],
    "MicromedIO": ["trc", "TRC"],
    "NWBIO": ["nwb"],
    "NeoMatlabIO": ["mat"],
    "NestIO": ["gdf", "dat"],
    "NeuralynxIO": ["nse", "ncs", "nev", "ntt", "nvt", "nrd"],
    "NeuroExplorerIO": ["nex"],
    "NeuroScopeIO": ["xml", "dat", "lfp", "eeg"],
    "NeuroshareIO": ["nsn"],
    "NixIO": ["h5", "nix"],
    "OpenEphysBinaryIO": ["oebin"],
    "OpenEphysIO": ["continuous", "openephys", "spikes", "events", "xml"],
    "PhyIO": ["npy", "mat", "tsv", "dat"],
    "PickleIO": ["pkl", "pickle"],
    "Plexon2IO": ["pl2"],
    "PlexonIO": ["plx"],
    "RawBinarySignalIO": ["raw", "bin", "dat"],
    "RawMCSIO": ["raw"],
    "Spike2IO": ["smr", "smrx"],
    "SpikeGLXIO": ["bin", "meta"],
    "SpikeGadgetsIO": ["rec"],
    "StimfitIO": ["abf", "dat", "axgx", "axgd", "cfs"],
    "TdtIO": ["tbk", "tdx", "tev", "tin", "tnt", "tsq", "sev", "txt"],
    "TiffIO": ["tiff"],
    "WinWcpIO": ["wcp"],
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

    def _get_neo_io_class(self, filepath: Path) -> Type:  # Use generic Type hint
        """Determines appropriate neo IO class using neo.io.get_io first, then fallback to IODict."""
        if not filepath.is_file():
            raise SynaptipyFileNotFoundError(f"File not found: {filepath}")

        # Priority 1: Let Neo decide (Robust discovery)
        try:
            io_instance = neo.io.get_io(str(filepath))
            log.debug(f"neo.io.get_io detected class: {io_instance.__class__.__name__}")
            return io_instance.__class__
        except Exception as e:
            log.debug(f"neo.io.get_io failed to detect IO for {filepath}: {e}. Falling back to extension map.")

        # Priority 2: Fallback to extension-based lookup (IODict)
        extension = filepath.suffix.lower().lstrip(".")
        log.debug(f"Attempting to find IO for extension: '{extension}'")

        available_io_names = [
            io_name for io_name, exts in IODict.items() if extension in exts
        ]

        if not available_io_names:
            raise UnsupportedFormatError(
                f"Unsupported file extension '.{extension}'. No suitable IO found in IODict."
            )

        selected_io_name = available_io_names[0]
        if len(available_io_names) > 1:
            if (
                extension == "abf"
                and "AxonIO" in available_io_names
                and "StimfitIO" in available_io_names
            ):
                selected_io_name = "AxonIO"
                log.warning(
                    f"Multiple IOs support '.{extension}' ({available_io_names}). Prioritizing '{selected_io_name}'."
                )
            else:
                log.warning(
                    f"Multiple Neo IOs support '.{extension}': {available_io_names}. "
                    f"Using first match: '{selected_io_name}'."
                )
        else:
            log.debug(
                f"Selected Neo IO: '{selected_io_name}' for file extension '.{extension}'."
            )

        try:
            io_class = getattr(nIO, selected_io_name)
            return io_class
        except AttributeError:
            log.error(
                f"Internal IODict Error: IO class name '{selected_io_name}' not found in neo.io module."
            )
            raise ValueError(
                f"Invalid IO class name '{selected_io_name}' defined in IODict."
            )
        except Exception as e:
            log.error(
                f"Unexpected error retrieving Neo IO class '{selected_io_name}': {e}"
            )
            raise FileReadError(
                f"Error accessing Neo IO class '{selected_io_name}': {e}"
            )

    def get_supported_file_filter(self) -> str:
        """Generates a file filter string for QFileDialog based on the IODict."""
        filters = []
        all_exts_wildcard = set()
        sorted_io_names = sorted(IODict.keys())

        for io_name in sorted_io_names:
            extensions = IODict.get(io_name, [])
            if not extensions:
                continue

            wildcard_exts = [
                f"*.{ext.lower()}"
                for ext in extensions
                if ext and isinstance(ext, str) and "." not in ext
            ]
            if not wildcard_exts:
                continue

            display_name = io_name[:-2] if io_name.endswith("IO") else io_name
            filter_entry = f"{display_name} Files ({' '.join(sorted(wildcard_exts))})"  # Sort extensions here
            filters.append(filter_entry)
            all_exts_wildcard.update(wildcard_exts)

        if all_exts_wildcard:
            all_supported_entry = (
                f"All Supported Files ({' '.join(sorted(list(all_exts_wildcard)))})"
            )
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

    def _extract_axon_metadata(  # noqa: C901
        self, reader: nIO.AxonIO
    ) -> Tuple[Optional[str], Optional[float]]:
        """Extracts protocol name and estimated injected current range specifically for AxonIO."""
        protocol_name: Optional[str] = None
        injected_current: Optional[float] = None

        if not isinstance(reader, nIO.AxonIO):
            log.debug("Not AxonIO, skipping Axon meta.")
            return protocol_name, injected_current

        # --- Protocol Name ---
        try:
            if (
                hasattr(reader, "_axon_info")
                and reader._axon_info
                and "sProtocolPath" in reader._axon_info
            ):
                protocol_path_raw = reader._axon_info["sProtocolPath"]
                protocol_path = (
                    protocol_path_raw.decode("utf-8", "ignore")
                    if isinstance(protocol_path_raw, bytes)
                    else str(protocol_path_raw)
                )
                if protocol_path and protocol_path.strip():
                    filename = protocol_path.split("\\")[-1].split("/")[-1]
                    protocol_name = (
                        filename.rsplit(".", 1)[0] if "." in filename else filename
                    )
                    log.debug(f"Extracted protocol name: {protocol_name}")
                else:
                    log.debug("Axon header 'sProtocolPath' is present but empty.")
            else:
                log.debug("Axon header '_axon_info' or 'sProtocolPath' not found.")
        except (KeyError, TypeError, UnicodeDecodeError) as e:
            log.warning(f"Protocol name extraction failed: {e}")
            protocol_name = "Extraction Error"

        # --- Injected Current ---
        try:
            if hasattr(reader, "read_raw_protocol"):
                protocol_raw_list = reader.read_raw_protocol()
                if isinstance(protocol_raw_list, list) and protocol_raw_list:
                    all_command_signals = []
                    for seg_protocol in protocol_raw_list:
                        if (
                            isinstance(seg_protocol, (list, tuple))
                            and len(seg_protocol) > 0
                        ):
                            command_signal_data = seg_protocol[0]
                            if isinstance(command_signal_data, (np.ndarray, list)):
                                command_signal_array = np.asarray(
                                    command_signal_data
                                ).ravel()
                                if command_signal_array.size > 0:
                                    all_command_signals.append(command_signal_array)
                    # --- Corrected Indentation for Current Calculation --- START ---
                    if all_command_signals:
                        all_command_points = np.concatenate(all_command_signals)
                        if all_command_points.size > 0:
                            current_range = np.ptp(all_command_points)
                            injected_current = np.around(current_range, decimals=3)
                            log.debug(
                                f"Estimated injected current range (PTP): {injected_current}"
                            )
                        else:
                            log.debug(
                                "Concatenated command signals were empty."
                            )  # Aligned with inner if
                    else:
                        log.debug(
                            "No suitable command signals found in protocol structure."
                        )  # Aligned with 'if all_command_signals'
                    # --- Corrected Indentation for Current Calculation --- END ---
                else:
                    log.debug(
                        "'read_raw_protocol()' returned empty list or non-list structure."
                    )  # Aligned with outer if
            else:
                log.debug(
                    "AxonIO reader instance does not have 'read_raw_protocol()' method."
                )  # Aligned with hasattr
        except (KeyError, TypeError, ValueError, IndexError) as e:
            log.warning(f"Failed during injected current estimation: {e}")
            injected_current = None

        return protocol_name, injected_current

    def read_recording(  # noqa: C901
        self,
        filepath: Path,
        lazy: bool = False,
        channel_whitelist: Optional[List[str]] = None,
        force_kHz_to_Hz: bool = False,
    ) -> Recording:
        """
        Reads any neo-supported electrophysiology file and translates it into a
        robust Recording object. This is the definitive, file-format-agnostic implementation.
        """
        log.debug(
            f"Attempting to read file: {filepath} (lazy: {lazy}, whitelist: {channel_whitelist})"
        )
        filepath = Path(filepath)
        io_class = self._get_neo_io_class(filepath)
        try:
            reader = io_class(filename=str(filepath))
            block = reader.read_block(lazy=lazy, signal_group_mode="split-all")
            log.debug(f"Successfully read neo Block using {io_class.__name__}.")
        except Exception as e:
            log.error(
                f"Failed to read block from {filepath} (Lazy: {lazy}): {e}",
                exc_info=True,
            )
            # If not lazy, maybe try lazy as fallback?
            if not lazy:
                log.debug("Attempting lazy load fallback due to failure...")
                try:
                    reader = io_class(filename=str(filepath))  # Re-instantiate
                    block = reader.read_block(lazy=True, signal_group_mode="split-all")
                    log.debug("Lazy load fallback succeeded.")
                    # If we fallback, we must treat this as lazy=True for the rest of function
                    lazy = True
                except Exception as e_lazy:
                    log.error(f"Lazy fallback also failed: {e_lazy}")
                    raise FileReadError(f"Could not read file (even lazily): {e}")
            else:
                raise FileReadError(f"Could not read file: {e}")

        recording = Recording(source_file=filepath)
        if hasattr(block, "rec_datetime") and block.rec_datetime:
            recording.session_start_time_dt = block.rec_datetime
            log.debug(
                f"Extracted session start time: {recording.session_start_time_dt}"
            )

        # --- Definitive Universal Header-First Data Loading Strategy ---

        # Initialize Source Handle
        source_handle = NeoSourceHandle(filepath, block=block, reader=reader)
        recording.source_handle = source_handle

        # Stage 1: Discover ALL potential channels from the header first.
        num_segments = len(block.segments)
        channel_metadata_map = self._discover_channels_from_header(reader, num_segments, lazy)

        # Helper map for SourceHandle: id -> {signal_index, offset}
        # We populate this during the first segment scan or iteratively
        handle_map: Dict[str, Dict[str, int]] = {}

        # Stage 2: Aggregate data into the discovered channels.
        for seg_idx, segment in enumerate(block.segments):
            log.debug(
                f"Processing segment {seg_idx} with {len(segment.analogsignals)} analogsignals"
            )
            # Pass handle_map to extract logic
            self._process_segment_signals(
                segment, seg_idx, channel_metadata_map, lazy, channel_whitelist, handle_map, force_kHz_to_Hz
            )

        # Configure SourceHandle with the learned map
        source_handle.set_channel_map(handle_map)

        # Stage 3: Create Channel objects
        created_channels = self._build_channels(channel_metadata_map, lazy, recording)

        if created_channels:
            # Link channels to parent recording for lazy loading access
            for ch in created_channels:
                ch._recording_ref = recording

            first_ch = created_channels[0]
            recording.sampling_rate = first_ch.sampling_rate
            recording.t_start = first_ch.t_start

            # Duration calculation attempt (§II.4: use get_data instead of direct data_trials access)
            if not lazy and first_ch.num_trials > 0 and first_ch.sampling_rate > 0:
                first_trial_data = first_ch.get_data(0)
                if first_trial_data is not None:
                    recording.duration = len(first_trial_data) / first_ch.sampling_rate
            elif lazy and first_ch.loader:
                # Try to get duration from loader info or source handle?
                try:
                    # Approximation using Neo Block structure
                    if len(block.segments) > 0 and len(block.segments[0].analogsignals) > 0:
                        sig = block.segments[0].analogsignals[0]
                        recording.duration = (
                            float(sig.duration) if hasattr(sig, 'duration') else 0.0
                        )
                except Exception:
                    pass

        # Store block reference on recording (Crucial for keeping lazy file handles alive/accessible)
        # recording.neo_block = block # REMOVED: Replaced by source_handle
        recording.channels = {ch.id: ch for ch in created_channels}

        log.debug(
            f"Translation complete. Loaded {len(recording.channels)} channel(s). Lazy: {lazy}"
        )
        return recording

    # --- Refactored Helper Methods ---

    def _discover_channels_from_header(self, reader, num_segments: int, lazy: bool) -> Dict[str, Dict]:
        """Stage 1: Discover ALL potential channels from the header first."""
        channel_metadata_map: Dict[str, Dict] = {}
        header_channels = (
            reader.header.get("signal_channels") if hasattr(reader, "header") else None
        )

        if header_channels is not None and len(header_channels) > 0:
            log.debug(
                f"Header found. Discovering channels from {type(header_channels)}."
            )
            for i, ch_info in enumerate(header_channels):
                ch_id = (
                    str(ch_info.get("id", i))
                    if isinstance(ch_info, dict)
                    else str(ch_info["id"]) if "id" in ch_info.dtype.names else str(i)
                )
                if isinstance(ch_info, dict):
                    ch_name = str(ch_info.get("name", f"Channel {ch_id}"))
                else:
                    if "name" in ch_info.dtype.names and ch_info["name"]:
                        ch_name_raw = ch_info["name"]
                        ch_name = (
                            ch_name_raw.decode().strip()
                            if isinstance(ch_name_raw, bytes)
                            else str(ch_name_raw).strip()
                        )
                    else:
                        ch_name = f"Channel {ch_id}"

                map_key = f"id_{ch_id}"
                if map_key not in channel_metadata_map:
                    # Pre-allocate data_trials list if not lazy
                    data_trials_list = [None] * num_segments if not lazy else []
                    channel_metadata_map[map_key] = {
                        "id": ch_id,
                        "name": ch_name,
                        "data_trials": data_trials_list,
                    }

            log.debug(f"Discovered {len(channel_metadata_map)} channels from header.")
        return channel_metadata_map

    def _process_segment_signals(  # noqa: C901
        self,
        segment: neo.Segment,
        seg_idx: int,
        channel_metadata_map: Dict[str, Dict],
        lazy: bool,
        channel_whitelist: Optional[List[str]],
        handle_map: Optional[Dict[str, Dict[str, int]]] = None,
        force_kHz_to_Hz: bool = False,
    ):
        """Stage 2: Process signals in a segment and update the metadata map."""
        for anasig_idx, anasig in enumerate(segment.analogsignals):
            if not isinstance(
                anasig, (neo.AnalogSignal, neo.io.proxyobjects.AnalogSignalProxy)
            ):
                continue

            # Extract channel ID with fallbacks
            anasig_id = None
            if hasattr(anasig, "annotations") and "channel_id" in anasig.annotations:
                anasig_id = str(anasig.annotations["channel_id"])
            elif hasattr(anasig, "channel_index") and anasig.channel_index is not None:
                anasig_id = str(anasig.channel_index)
            elif (
                hasattr(anasig, "array_annotations")
                and "channel_id" in anasig.array_annotations
            ):
                anasig_id = str(anasig.array_annotations["channel_id"][0])
            else:
                anasig_id = str(anasig_idx)

            map_key = f"id_{anasig_id}"

            # Whitelist check
            should_load = True
            if channel_whitelist:
                should_load = False
                if anasig_id in channel_whitelist:
                    should_load = True
                elif map_key in channel_metadata_map:
                    if channel_metadata_map[map_key]["name"] in channel_whitelist:
                        should_load = True

            if not should_load:
                continue

            # Ensure entry exists
            if map_key not in channel_metadata_map:
                # Dynamic discovery fallback (shouldn't happen often with strict header read)
                # If we discover a channel late, we can't easily pre-allocate without knowing total segments here
                # So we might fallback to append, or assume handled.
                # For safety, initialize with empty list or pre-filled if we knew num_segments.
                # Since we don't pass num_segments here easily, let's just use append for fallback.
                channel_metadata_map[map_key] = {
                    "id": anasig_id,
                    "name": f"Channel {anasig_id}",
                    "data_trials": [],
                }
                log.warning(f"Channel {anasig_id} discovered late (not in header). Pre-allocation skipped.")

            # --- Populate Handle Map ---
            if handle_map is not None and anasig_id not in handle_map:
                # Assuming 1 AnalogSignal = 1 Channel for now.
                # Note: Currently Synaptipy treats each AnalogSignal as a channel usually,
                # unless we are splitting columns.
                # Assuming 1 AnalogSignal = 1 Channel for now as per previous logic.
                handle_map[anasig_id] = {
                    "signal_index": anasig_idx,
                    "channel_offset": 0  # Default to 0
                }

            # Extract Data/Ref
            if lazy:
                # We don't need to append refs anymore for loading, but we need to ensure the list exists
                # for the Channel object to know how many trials there are?
                # Channel object infers num_trials from data_trials length or metadata.
                # If lazy, data_trials is empty.
                # We should update metadata with the number of segments ideally.
                if "num_trials" not in channel_metadata_map[map_key]:
                    channel_metadata_map[map_key]["num_trials"] = 0
                channel_metadata_map[map_key]["num_trials"] += 1
            else:
                signal_data = np.array(anasig.magnitude).ravel()

                # --- Data unit standardization ---
                # Electrophysiology convention: voltage in mV, current in pA.
                # Neo files may store data in base SI units (V, A) or
                # scaled units (mV, pA, nA, etc.). Detect and rescale.
                try:
                    unit_str = str(anasig.units.dimensionality).strip()
                    # Voltage rescaling
                    if unit_str in ("V", "volt", "Volt"):
                        signal_data = signal_data * 1e3  # V -> mV
                        log.info(f"Channel {anasig_id}: rescaled data from V to mV")
                    elif unit_str in ("uV", "µV", "microvolt"):
                        signal_data = signal_data * 1e-3  # µV -> mV
                        log.info(f"Channel {anasig_id}: rescaled data from µV to mV")
                    # Current rescaling
                    elif unit_str in ("A", "amp", "ampere", "Amp"):
                        signal_data = signal_data * 1e12  # A -> pA
                        log.info(f"Channel {anasig_id}: rescaled data from A to pA")
                    elif unit_str in ("nA", "nanoampere"):
                        signal_data = signal_data * 1e3  # nA -> pA
                        log.info(f"Channel {anasig_id}: rescaled data from nA to pA")
                    elif unit_str in ("uA", "µA", "microampere"):
                        signal_data = signal_data * 1e6  # µA -> pA
                        log.info(f"Channel {anasig_id}: rescaled data from µA to pA")
                    # mV and pA are already in the expected units — no rescaling needed
                except Exception as e:
                    log.debug(f"Could not determine units for channel {anasig_id}: {e}")

                # Use direct assignment to pre-allocated slot if possible
                trials_list = channel_metadata_map[map_key]["data_trials"]
                if seg_idx < len(trials_list):
                    trials_list[seg_idx] = signal_data
                else:
                    # Fallback if list was short (e.g. late discovery)
                    trials_list.append(signal_data)

            # Metadata Extraction (First encounter)
            if "sampling_rate" not in channel_metadata_map[map_key]:
                try:
                    raw_fs = float(anasig.sampling_rate)

                    if force_kHz_to_Hz:
                        # Apply Correction
                        fs = raw_fs * 1000.0
                        units_dim = "Hz"  # Explicitly corrected
                        log.info(f"Applying Unit Correction: {raw_fs} -> {fs} Hz for Channel {anasig_id}")
                    else:
                        fs = raw_fs
                        units_dim = str(anasig.units.dimensionality)

                    channel_metadata_map[map_key].update(
                        {
                            "units": units_dim,
                            "sampling_rate": fs,
                            "t_start": float(anasig.t_start),
                        }
                    )

                    # Phase 4: Validate sampling rate
                    # If forced, we assume the new 'fs' is correct and we skip the 'UnitError' check
                    # (though we might still want to warn if it's STILL low, but the explicit intent was to fix it)

                    # Phase 4: Identify Suspicious Sampling Rates
                    # If forced, we assume the new 'fs' is correct.
                    # Otherwise, if < 100Hz, we suspect unit mismatch (kHz vs Hz).

                    validate_sampling_rate(fs)

                    if not force_kHz_to_Hz and fs < 100.0:
                        # Strict Scientific Safety Rule:
                        # If < 100Hz, we assume units are wrong (e.g. kHz input as Hz) or data is invalid.
                        raise UnitError(f"Critical Safety: Sampling Rate {fs}Hz is dangerously low (<100Hz). "
                                        f"Check if units are in kHz.")
                except UnitError:
                    raise
                except Exception:
                    # Re-raise UnitError to be caught by UI
                    if isinstance(sys.exc_info()[1], UnitError):
                        raise
                    pass

    def _build_channels(
        self, channel_metadata_map: Dict[str, Dict], lazy: bool, recording: Recording
    ) -> List[Channel]:
        """Stage 3: Create Channel objects from the populated metadata map."""
        created_channels: List[Channel] = []

        # Helper to create a closure for the loader
        def create_loader(ch_id: str, handle: NeoSourceHandle):
            return lambda idx: handle.load_channel_data(ch_id, idx)

        for meta in channel_metadata_map.values():
            has_data = len(meta["data_trials"]) > 0
            is_lazy_mode = lazy

            if not has_data and not is_lazy_mode and meta.get("sampling_rate") is None:
                continue

            # Instantiate Loader if needed
            loader = None
            if lazy and recording.source_handle:
                # Use the decoupled SourceHandle
                handle = recording.source_handle
                if isinstance(handle, NeoSourceHandle):
                    loader = create_loader(meta["id"], handle)

            channel = Channel(
                id=meta["id"],
                name=meta["name"],
                units=meta.get("units", "unknown"),
                sampling_rate=meta.get("sampling_rate", 0.0),
                data_trials=meta["data_trials"] if not lazy else [],
                loader=loader,
            )
            channel.t_start = meta.get("t_start", 0.0)

            # Pass num_trials metadata if lazy
            if lazy and "num_trials" in meta:
                channel.metadata["num_trials"] = meta["num_trials"]

            created_channels.append(channel)

        return created_channels
