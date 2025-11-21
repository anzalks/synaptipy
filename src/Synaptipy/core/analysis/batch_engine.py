"""
Batch Analysis Engine for Synaptipy.
Handles processing multiple files and aggregating results.
"""
import logging
import pandas as pd
from pathlib import Path
from typing import List, Dict, Any, Optional, Callable
import numpy as np

from Synaptipy.infrastructure.file_readers import NeoAdapter
from Synaptipy.core.analysis import spike_analysis, intrinsic_properties as ip
from Synaptipy.core.results import AnalysisResult, SpikeTrainResult, RinResult

log = logging.getLogger(__name__)

class BatchAnalysisEngine:
    """
    Engine for running analysis across multiple files/recordings.
    """
    
    def __init__(self):
        self.neo_adapter = NeoAdapter()
        
    def run_batch(self, 
                  files: List[Path], 
                  analysis_config: Dict[str, Any],
                  progress_callback: Optional[Callable[[int, int, str], None]] = None) -> pd.DataFrame:
        """
        Run analysis on a list of files.
        
        Args:
            files: List of file paths to process.
            analysis_config: Dictionary defining what analysis to run and parameters.
                             Example:
                             {
                                 'spike_detection': {'enabled': True, 'threshold': -20, 'refractory_ms': 2},
                                 'rin': {'enabled': False}
                             }
            progress_callback: Optional callback (current, total, status_msg).
            
        Returns:
            pandas DataFrame containing aggregated results.
        """
        results_list = []
        total_files = len(files)
        
        for i, file_path in enumerate(files):
            if progress_callback:
                progress_callback(i, total_files, f"Processing {file_path.name}...")
                
            try:
                # Load recording
                recording = self.neo_adapter.read_recording(file_path)
                if not recording:
                    log.warning(f"Failed to load {file_path}")
                    continue
                
                # Iterate through channels (or specific ones if config says so)
                # For now, process all analog signals
                for channel_name, channel in recording.channels.items():
                    # Base result row
                    row = {
                        'file_name': file_path.name,
                        'file_path': str(file_path),
                        'channel': channel_name,
                        'sampling_rate': channel.sampling_rate
                    }
                    
                    # --- Spike Detection ---
                    spike_cfg = analysis_config.get('spike_detection', {})
                    if spike_cfg.get('enabled', False):
                        self._run_spike_detection(channel, spike_cfg, row)
                        
                    # --- Rin / Intrinsic Properties ---
                    rin_cfg = analysis_config.get('rin', {})
                    if rin_cfg.get('enabled', False):
                        self._run_rin_analysis(channel, rin_cfg, row)
                    
                    results_list.append(row)
                    
            except Exception as e:
                log.error(f"Error processing batch file {file_path}: {e}", exc_info=True)
                # Add error row
                results_list.append({
                    'file_name': file_path.name,
                    'error': str(e)
                })
        
        if progress_callback:
            progress_callback(total_files, total_files, "Batch analysis complete.")
            
        return pd.DataFrame(results_list)

    def _run_spike_detection(self, channel, config: Dict, row: Dict):
        """Helper to run spike detection and update result row."""
        try:
            # Concatenate all trials for simple continuous analysis or handle per-trial?
            # For batch, usually we want per-sweep or average. Let's do per-sweep stats?
            # Or just treat first trial for simplicity in this prototype.
            if not channel.data_trials:
                return

            # Use first trial for now (TODO: Multi-sweep support)
            data = channel.data_trials[0]
            time = channel.get_time_vector(0)
            fs = channel.sampling_rate
            
            threshold = config.get('threshold', 0.0)
            refractory_ms = config.get('refractory_ms', 2.0)
            refractory_samples = int((refractory_ms / 1000.0) * fs)
            
            result = spike_analysis.detect_spikes_threshold(data, time, threshold, refractory_samples)
            
            if result.is_valid:
                row['spike_count'] = len(result.spike_indices)
                row['mean_freq_hz'] = result.mean_frequency
                # Add more features if needed
            else:
                row['spike_error'] = result.error_message
                
        except Exception as e:
            log.error(f"Batch spike detection error: {e}")
            row['spike_error'] = str(e)

    def _run_rin_analysis(self, channel, config: Dict, row: Dict):
        """Helper to run Rin analysis."""
        # Requires knowing windows, which is hard in batch without metadata.
        # This is a placeholder for now.
        pass
