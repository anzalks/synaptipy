import logging
import datetime
import numpy as np
import struct
from neo.rawio.winwcprawio import WinWcpRawIO, HeaderReader, AnalysisDescription

log = logging.getLogger('Synaptipy.infrastructure.neo_patches')

def apply_winwcp_patch():
    """
    Monkeypatches neo.rawio.winwcprawio.WinWcpRawIO._parse_header to fix UnboundLocalError
    when reading truncated or corrupted files where the segment loop doesn't run.
    """
    original_parse_header = WinWcpRawIO._parse_header
    
    def patched_parse_header(self):
        # Retrieve necessary private/internal structures if possible, or replicate logic
        # Since we are replacing the whole method, we copy the logic and add the fix.
        
        SECTORSIZE = 512

        # one unique block with several segments
        # one unique buffer splited in several streams
        self._buffer_descriptions = {0: {}}

        with open(self.filename, "rb") as fid:

            headertext = fid.read(1024)
            headertext = headertext.decode("ascii", errors="ignore") # Added errors="ignore" for robustness
            header = {}
            for line in headertext.split("\r\n"):
                if "=" not in line:
                    continue
                key, val = line.split("=")
                if key in [
                    "VER",
                    "NC",
                    "NR",
                    "NBH",
                    "NBA",
                    "NBD",
                    "ADCMAX",
                    "NP",
                    "NZ",
                ]:
                    try: val = int(val)
                    except: val = 0 # Fallback
                elif key in [
                    "AD",
                    "DT",
                ]:
                    val = val.replace(",", ".")
                    try: val = float(val)
                    except: val = 0.0
                header[key] = val

            # Validations for missing keys
            if "NR" not in header: header["NR"] = 0
            if "NC" not in header: header["NC"] = 1
            if "NBD" not in header: header["NBD"] = 1
            if "NBA" not in header: header["NBA"] = 0
            if "ADCMAX" not in header: header["ADCMAX"] = 1

            # --- FIX START: Estimate NR from file size if 0 ---
            if header["NR"] == 0:
                try:
                    import os
                    file_size = os.path.getsize(self.filename)
                    # Block Size = AnalysisHeader (1024) + Data (SECTORSIZE * NBD)
                    block_size = 1024 + (SECTORSIZE * header["NBD"])
                    # Header is 1024 bytes
                    data_area_size = file_size - 1024
                    if data_area_size > 0 and block_size > 0:
                        estimated_nr = data_area_size // block_size
                        if estimated_nr > 0:
                            header["NR"] = estimated_nr
                            log.warning(f"Header indicates NR=0. Estimated NR={estimated_nr} from file size.")
                except Exception as e:
                     log.warning(f"Failed to estimate NR from file size: {e}")
            # --- FIX END ---

            nb_segment = header["NR"]

            # get rec_datetime when WCP data file version is later than 8
            if header.get("VER", 0) > 8 and "RTIME" in header:
                try:
                    rec_datetime = datetime.datetime.strptime(header["RTIME"], "%d/%m/%Y %H:%M:%S")
                except:
                    rec_datetime = None
            else:
                rec_datetime = None
            
            all_sampling_interval = []
            
            # --- FIX START: Initialize analysisHeader ---
            analysisHeader = None
            # --- FIX END ---

            # loop for record number
            for seg_index in range(header["NR"]):
                offset = 1024 + seg_index * (SECTORSIZE * header["NBD"] + 1024)

                try:
                    # read analysis zone
                    analysisHeader = HeaderReader(fid, AnalysisDescription).read_f(offset=offset)
                    all_sampling_interval.append(analysisHeader["SamplingInterval"])
                except Exception as e:
                    log.warning(f"Failed to read analysis header for segment {seg_index}: {e}")
                    continue

                # read data settings
                NP = (SECTORSIZE * header["NBD"]) // 2
                if header["NC"] > 0:
                    NP = NP - NP % header["NC"]
                    NP = NP // header["NC"]
                else: 
                    NP = 0
                    
                NC = header["NC"]
                ind0 = offset + header["NBA"] * SECTORSIZE
                buffer_id = "0"
                
                if seg_index not in self._buffer_descriptions[0]:
                    self._buffer_descriptions[0][seg_index] = {}
                    
                self._buffer_descriptions[0][seg_index][buffer_id] = {
                    "type": "raw",
                    "file_path": str(self.filename),
                    "dtype": "int16",
                    "order": "C",
                    "file_offset": ind0,
                    "shape": (NP, NC),
                }

            # --- FIX START: Handling missing analysisHeader ---
            if analysisHeader is None:
                log.warning("analysisHeader was not populated (NR=0 or read failed). Attempting fallback read at offset 1024.")
                try:
                    analysisHeader = HeaderReader(fid, AnalysisDescription).read_f(offset=1024)
                    if "SamplingInterval" in analysisHeader:
                        all_sampling_interval.append(analysisHeader["SamplingInterval"])
                except Exception as e:
                    log.error(f"Fallback analysis header read failed: {e}")
                    # Construct dummy analysisHeader to prevent crash
                    # AnalysisDescription usually defines structs. We need a dict-like object with 'VMax'
                    # AnalysisDescription = [('RecordType','4s'), ..., ('SamplingInterval','f'), ..., ('VMax','32f'), ...]
                    # We assume 32f for VMax based on standard WCP
                    analysisHeader = {
                        "SamplingInterval": 1.0, # Dummy
                        "VMax": [1.0] * 128 # Dummy array big enough for channels
                    }
                    all_sampling_interval.append(1.0)
            # --- FIX END ---

        # sampling interval can be slightly varying due to float precision
        # all_sampling_interval are not always unique
        if all_sampling_interval:
            self._sampling_rate = 1.0 / np.median(all_sampling_interval)
        else:
            self._sampling_rate = 1000.0 # Default fallback

        signal_channels = []
        for c in range(header["NC"]):
            YG_key = f"YG{c}"
            YG = float(header[YG_key].replace(",", ".")) if YG_key in header else 1.0
            ADCMAX = header["ADCMAX"]
            
            # Safe Access to VMax
            try:
                if isinstance(analysisHeader["VMax"], (list, tuple, np.ndarray)):
                    VMax = analysisHeader["VMax"][c]
                else:
                    VMax = 1.0
            except:
                VMax = 1.0

            name = header.get(f"YN{c}", f"Chan{c}")
            chan_id = header.get(f"YO{c}", c)
            units = header.get(f"YU{c}", "V")
            
            try:
                gain = VMax / ADCMAX / YG
            except:
                gain = 1.0
                
            offset = 0.0
            stream_id = "0"
            buffer_id = "0"
            _signal_channel_dtype = [
                ('name', 'U64'), ('id', 'U64'), ('sampling_rate', 'float64'), ('dtype', 'U16'),
                ('units', 'U64'), ('gain', 'float64'), ('offset', 'float64'), ('stream_id', 'U64'), ('buffer_id', 'U64')
            ]
            signal_channels.append(
                (name, str(chan_id), self._sampling_rate, "int16", units, gain, offset, stream_id, buffer_id)
            )

        signal_channels = np.array(signal_channels, dtype=_signal_channel_dtype)
        
        # --- Common Characteristics Logic ---
        # Need to import _common_sig_characteristics or define it
        _common_sig_characteristics = ['sampling_rate', 'dtype', 'stream_id'] 
        
        characteristics = signal_channels[_common_sig_characteristics]
        unique_characteristics = np.unique(characteristics)
        signal_streams = []
        self._stream_buffer_slice = {}
        
        _signal_stream_dtype = [('name', 'U64'), ('id', 'U64'), ('buffer_id', 'U64')]
        
        for i in range(unique_characteristics.size):
            mask = unique_characteristics[i] == characteristics
            signal_channels["stream_id"][mask] = str(i)
            # unique buffer for all streams
            buffer_id = "0"
            stream_id = str(i)
            signal_streams.append((f"stream {i}", stream_id, buffer_id))
            self._stream_buffer_slice[stream_id] = np.flatnonzero(mask)
        signal_streams = np.array(signal_streams, dtype=_signal_stream_dtype)

        # all stream are in the same unique buffer : memmap
        _signal_buffer_dtype = [('name', 'U64'), ('id', 'U64')]
        signal_buffers = np.array([("", "0")], dtype=_signal_buffer_dtype)

        # No events
        _event_channel_dtype = [('name', 'U64'), ('id', 'U64'), ('type', 'S5')]
        event_channels = []
        event_channels = np.array(event_channels, dtype=_event_channel_dtype)

        # No spikes
        _spike_channel_dtype = [('name', 'U64'), ('id', 'U64'), ('sampling_rate', 'float64'), ('dtype', 'U16'), ('units', 'U64'), ('gain', 'float64'), ('offset', 'float64'), ('stream_id', 'U64')]
        spike_channels = []
        spike_channels = np.array(spike_channels, dtype=_spike_channel_dtype)

        # fille into header dict
        self.header = {}
        self.header["nb_block"] = 1
        self.header["nb_segment"] = [nb_segment]
        self.header["signal_buffers"] = signal_buffers
        self.header["signal_streams"] = signal_streams
        self.header["signal_channels"] = signal_channels
        self.header["spike_channels"] = spike_channels
        self.header["event_channels"] = event_channels

        # insert some annotation at some place
        self._generate_minimal_annotations()
        bl_annotations = self.raw_annotations["blocks"][0]
        bl_annotations["rec_datetime"] = rec_datetime

    # Apply the patch
    WinWcpRawIO._parse_header = patched_parse_header
    log.info("Successfully patched WinWcpRawIO._parse_header for robust loading.")
