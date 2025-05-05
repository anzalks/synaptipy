# src/Synaptipy/application/gui/dummy_classes.py
# -*- coding: utf-8 -*-
"""
Dummy implementations for Synaptipy components used when the main library is not available.
Also handles the initial import attempt and sets the SYNAPTIPY_AVAILABLE flag.
"""
import logging
import numpy as np
from pathlib import Path
from datetime import datetime, timezone

# Use a specific logger
log = logging.getLogger('Synaptipy.application.gui.dummy_classes')

# --- Try importing real Synaptipy using ABSOLUTE paths ---
try:
    # These imports assume Synaptipy is installed and accessible
    from Synaptipy.core.data_model import Recording, Channel
    from Synaptipy.infrastructure.file_readers import NeoAdapter
    from Synaptipy.infrastructure.exporters import NWBExporter
    from Synaptipy.shared import constants as VisConstants # Use alias
    from Synaptipy.shared.error_handling import (
        FileReadError, UnsupportedFormatError, ExportError, SynaptipyError, 
        SynaptipyFileNotFoundError)
    SYNAPTIPY_AVAILABLE = True
    log.info("Successfully imported real Synaptipy modules.")

except Exception as e_import:
    # --- Synaptipy not found, set up dummy environment ---
    log.warning(f"Failed to import Synaptipy modules: {e_import}. Using dummy implementations.")
    SYNAPTIPY_AVAILABLE = False

    # --- Define Dummy Classes (Keep definitions as before) ---
    # V V V Paste Dummy Class definitions here V V V
    class DummyChannel:
        def __init__(self, id, name, units='mV', num_trials=5, duration=1.0, rate=10000.0):
            self.id = id; self.name = name; self.units = units; self.num_trials = num_trials
            self._duration = duration; self._rate = rate; self._num_samples = int(duration * rate)
            self.tvecs = [np.linspace(0, duration, self._num_samples, endpoint=False) for _ in range(num_trials)]
            self.data = []
            for i in range(num_trials):
                noise = np.random.randn(self._num_samples) * 0.1 * (i + 1)
                sine_wave = np.sin(self.tvecs[i] * (i + 1) * 2 * np.pi / duration) * 0.5 * (i + 1)
                baseline_shift = i * 0.2
                self.data.append(noise + sine_wave + baseline_shift)
        def get_data(self, trial_idx): return self.data[trial_idx] if 0 <= trial_idx < self.num_trials else None
        def get_relative_time_vector(self, trial_idx): return self.tvecs[trial_idx] if 0 <= trial_idx < self.num_trials else None
        def get_averaged_data(self):
            if self.num_trials > 0 and self.data:
                try:
                    min_len = min(len(d) for d in self.data); data_to_avg = [d[:min_len] for d in self.data]
                    return np.mean(np.array(data_to_avg), axis=0)
                except Exception as e: log.error(f"Error averaging dummy data for channel {self.id}: {e}"); return None
            else: return None
        def get_relative_averaged_time_vector(self):
            if self.num_trials > 0 and self.tvecs:
                 min_len = min(len(d) for d in self.data) if self.data else self._num_samples
                 return self.tvecs[0][:min_len]
            else: return None

    class DummyRecording:
        def __init__(self, filepath, num_channels=3):
            self.source_file = Path(filepath); self.sampling_rate = 10000.0; self.duration = 2.0
            self.num_channels = num_channels; self.max_trials = 10
            ch_ids = [f'Ch{i+1:02d}' for i in range(num_channels)]
            self.channels = { ch_ids[i]: DummyChannel(id=ch_ids[i], name=f'Channel {i+1}', units='pA' if i % 2 == 0 else 'mV', num_trials=self.max_trials, duration=self.duration, rate=self.sampling_rate) for i in range(num_channels)}
            self.session_start_time_dt = datetime.now(timezone.utc) # Ensure dummy time is timezone-aware

    class DummyNeoAdapter:
        def get_supported_file_filter(self): return "Dummy Files (*.dummy);;All Files (*)"
        def read_recording(self, filepath):
            log.info(f"DummyNeoAdapter: Simulating read for {filepath}")
            if not Path(filepath).exists():
                try: Path(filepath).touch()
                except Exception as e: log.warning(f"Could not create dummy file {filepath}: {e}")
            fname_lower = str(filepath).lower()
            if '5ch' in fname_lower: num_chan = 5
            elif '1ch' in fname_lower: num_chan = 1
            else: num_chan = 3
            log.debug(f"DummyNeoAdapter: Creating recording with {num_chan} channels.")
            return DummyRecording(filepath, num_channels=num_chan)

    class DummyNWBExporter:
        def export(self, recording, output_path, metadata):
            log.info(f"DummyNWBExporter: Simulating export of '{recording.source_file.name}' to {output_path} with metadata {metadata}")
            try:
                output_path.touch()
                log.info(f"DummyNWBExporter: Touched output file {output_path}")
            except Exception as e:
                log.error(f"DummyNWBExporter: Failed to touch output file {output_path}: {e}")
                # Need to define ExportError within this block if real one failed
                class DummyExportError(Exception): pass
                raise DummyExportError(f"Dummy export failed: {e}")

    class DummyVisConstants:
        TRIAL_COLOR = '#888888'; TRIAL_ALPHA = 70; AVERAGE_COLOR = '#EE4B2B'
        DEFAULT_PLOT_PEN_WIDTH = 1; DOWNSAMPLING_THRESHOLD = 5000

    def DummyErrors():
        class SynaptipyError(Exception): pass
        class FileReadError(SynaptipyError): pass
        class UnsupportedFormatError(SynaptipyError): pass
        class ExportError(SynaptipyError): pass
        class SynaptipyFileNotFoundError(SynaptipyError): pass
        return SynaptipyError, FileReadError, UnsupportedFormatError, ExportError, SynaptipyFileNotFoundError

    # --- Assign dummy classes/values ---
    Recording, Channel = DummyRecording, DummyChannel
    NeoAdapter, NWBExporter = DummyNeoAdapter, DummyNWBExporter
    VisConstants = DummyVisConstants()
    SynaptipyError, FileReadError, UnsupportedFormatError, ExportError, SynaptipyFileNotFoundError = DummyErrors()
    # ^ ^ ^ End of Dummy Class definitions ^ ^ ^

# --- Define constants if VisConstants is None ---
# This is a safety fallback
if 'VisConstants' not in locals() or VisConstants is None:
    log.warning("VisConstants is None after dummy setup, defining fallback constants.")
    class FallbackVisConstants:
        TRIAL_COLOR = '#888888'; TRIAL_ALPHA = 70; AVERAGE_COLOR = '#EE4B2B'
        DEFAULT_PLOT_PEN_WIDTH = 1; DOWNSAMPLING_THRESHOLD = 5000
    VisConstants = FallbackVisConstants()
if 'NeoAdapter' not in locals(): NeoAdapter = DummyNeoAdapter # Ensure NeoAdapter exists even if only dummies defined
if 'NWBExporter' not in locals(): NWBExporter = DummyNWBExporter
if 'Recording' not in locals(): Recording = DummyRecording
if 'SynaptipyError' not in locals(): SynaptipyError, FileReadError, UnsupportedFormatError, ExportError, SynaptipyFileNotFoundError = DummyErrors()