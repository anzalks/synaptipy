"""
Batch Analysis Engine for Synaptipy.
Handles processing multiple files and aggregating results using a flexible registry-based pipeline.

The engine uses a registry-based architecture where analysis functions register
themselves via decorators, and the pipeline configuration defines what analyses
to run on which data scopes.

Author: Anzal KS <anzal.ks@gmail.com>
"""
import logging
import pandas as pd
from pathlib import Path
from typing import List, Dict, Any, Optional, Callable, Union
import numpy as np
from datetime import datetime

from Synaptipy.infrastructure.file_readers import NeoAdapter
from Synaptipy.core.analysis.registry import AnalysisRegistry

# Import analysis package to trigger all registrations
import Synaptipy.core.analysis  # noqa: F401 - Import triggers all registrations

log = logging.getLogger(__name__)


class BatchAnalysisEngine:
    """
    Engine for running analysis across multiple files/recordings using a flexible pipeline.
    
    The engine uses a registry-based architecture where analysis functions register
    themselves via decorators, and the pipeline configuration defines what analyses
    to run on which data scopes.
    
    Example Usage:
        engine = BatchAnalysisEngine()
        files = [Path("file1.abf"), Path("file2.abf")]
        pipeline = [
            {
                'analysis': 'spike_detection',
                'scope': 'all_trials',
                'params': {'threshold': -15.0, 'refractory_ms': 2.0}
            },
            {
                'analysis': 'rmp_analysis',
                'scope': 'average',
                'params': {'baseline_start': 0.0, 'baseline_end': 0.1}
            }
        ]
        results_df = engine.run_batch(files, pipeline)
    """
    
    def __init__(self, neo_adapter: Optional[NeoAdapter] = None):
        """
        Initialize the batch analysis engine.
        
        Args:
            neo_adapter: Optional NeoAdapter instance. If None, creates a new one.
        """
        self.neo_adapter = neo_adapter if neo_adapter else NeoAdapter()
        self._cancelled = False
    
    def cancel(self):
        """Request cancellation of the current batch run."""
        self._cancelled = True
        log.info("Batch analysis cancellation requested.")
    
    @staticmethod
    def list_available_analyses() -> List[str]:
        """
        Get a list of all registered analysis function names.
        
        Returns:
            List of available analysis names.
        """
        return AnalysisRegistry.list_registered()
    
    @staticmethod
    def get_analysis_info(name: str) -> Optional[Dict[str, Any]]:
        """
        Get information about a registered analysis function.
        
        Args:
            name: The registered name of the analysis function.
            
        Returns:
            Dictionary with function info (docstring, etc.) or None if not found.
        """
        func = AnalysisRegistry.get_function(name)
        if func is None:
            return None
        
        return {
            'name': name,
            'docstring': func.__doc__ or "No documentation available.",
            'module': func.__module__,
        }
        
    def run_batch(self, 
                  files: List[Path], 
                  pipeline_config: List[Dict[str, Any]],
                  progress_callback: Optional[Callable[[int, int, str], None]] = None,
                  channel_filter: Optional[List[str]] = None) -> pd.DataFrame:
        """
        Run analysis on a list of files using a flexible pipeline configuration.
        
        Args:
            files: List of file paths to process.
            pipeline_config: List of task dictionaries, each defining:
                {
                    'analysis': str,  # Name of registered analysis function (e.g., 'spike_detection')
                    'scope': str,     # 'average', 'all_trials', or 'first_trial'
                    'params': dict    # Parameters to pass to the analysis function
                }
            progress_callback: Optional callback (current, total, status_msg).
            channel_filter: Optional list of channel names/IDs to process. If None, all channels are processed.
            
        Returns:
            pandas DataFrame containing aggregated results with metadata.
            
        Example:
            pipeline_config = [
                {
                    'analysis': 'spike_detection',
                    'scope': 'all_trials',
                    'params': {'threshold': -15.0, 'refractory_ms': 2.0}
                },
                {
                    'analysis': 'rmp_analysis',
                    'scope': 'average',
                    'params': {'baseline_start': 0.0, 'baseline_end': 0.1}
                }
            ]
        """
        self._cancelled = False
        results_list = []
        total_files = len(files)
        
        # Validate pipeline config
        if not pipeline_config:
            log.warning("Empty pipeline_config provided. No analyses will be run.")
            return pd.DataFrame()
        
        # Add batch metadata
        batch_start_time = datetime.now()
        
        for i, file_path in enumerate(files):
            # Check for cancellation
            if self._cancelled:
                log.info("Batch analysis cancelled by user.")
                if progress_callback:
                    progress_callback(i, total_files, "Cancelled")
                break
                
            if progress_callback:
                progress_callback(i, total_files, f"Processing {file_path.name}...")
                
            try:
                # Load recording
                recording = self.neo_adapter.read_recording(file_path)
                if not recording:
                    log.warning(f"Failed to load {file_path}")
                    results_list.append({
                        'file_name': file_path.name,
                        'file_path': str(file_path),
                        'error': "Failed to load recording"
                    })
                    continue
                
                # Filter channels if specified
                channels_to_process = recording.channels.items()
                if channel_filter:
                    log.debug(f"Applying channel filter: {channel_filter}")
                    log.debug(f"Available channels: {list(recording.channels.keys())}")
                    channels_to_process = [
                        (name, ch) for name, ch in recording.channels.items()
                        if name in channel_filter or str(name) in channel_filter
                    ]
                    if not channels_to_process:
                        log.warning(f"Channel filter {channel_filter} matched no channels in {file_path.name}. Available: {list(recording.channels.keys())}")
                
                log.debug(f"Processing {len(channels_to_process)} channels: {[n for n, c in channels_to_process]}")
                
                # Iterate through channels
                for channel_name, channel in channels_to_process:
                    # Check for cancellation
                    if self._cancelled:
                        break
                        
                    # Process each task in the pipeline
                    for task in pipeline_config:
                        if self._cancelled:
                            break
                            
                        try:
                            task_results = self._process_task(
                                task=task,
                                channel=channel,
                                channel_name=channel_name,
                                file_path=file_path
                            )
                            # Extend results list with all results from this task
                            results_list.extend(task_results)
                        except Exception as e:
                            log.error(f"Error processing task {task.get('analysis', 'unknown')} on {file_path.name}/{channel_name}: {e}", exc_info=True)
                            # Add error row
                            results_list.append({
                                'file_name': file_path.name,
                                'file_path': str(file_path),
                                'channel': channel_name,
                                'analysis': task.get('analysis', 'unknown'),
                                'scope': task.get('scope', 'unknown'),
                                'error': str(e)
                            })
                    
            except Exception as e:
                log.error(f"Error processing batch file {file_path}: {e}", exc_info=True)
                # Add error row
                results_list.append({
                    'file_name': file_path.name,
                    'file_path': str(file_path),
                    'error': str(e)
                })
        
        if progress_callback:
            if self._cancelled:
                progress_callback(i, total_files, "Batch analysis cancelled.")
            else:
                progress_callback(total_files, total_files, "Batch analysis complete.")
        
        # Create DataFrame and add batch metadata
        df = pd.DataFrame(results_list)
        if not df.empty:
            df['batch_timestamp'] = batch_start_time.isoformat()
            
        return df
    
    def _process_task(self, 
                     task: Dict[str, Any],
                     channel,
                     channel_name: str,
                     file_path: Path) -> List[Dict[str, Any]]:
        """
        Process a single analysis task on a channel.
        
        Args:
            task: Task configuration dict with 'analysis', 'scope', and 'params'
            channel: Channel object to analyze
            channel_name: Name/ID of the channel
            file_path: Path to the source file
            
        Returns:
            List of result dictionaries (one per trial if scope is 'all_trials')
        """
        analysis_name = task.get('analysis')
        scope = task.get('scope', 'first_trial')
        params = task.get('params', {})
        
        # Get the registered analysis function
        analysis_func = AnalysisRegistry.get_function(analysis_name)
        if analysis_func is None:
            log.error(f"Analysis function '{analysis_name}' not found in registry")
            return [{
                'file_name': file_path.name,
                'file_path': str(file_path),
                'channel': channel_name,
                'analysis': analysis_name,
                'scope': scope,
                'error': f"Analysis function '{analysis_name}' not registered"
            }]
        
        results = []
        sampling_rate = channel.sampling_rate
        
        # Determine data scope and extract data
        if scope == 'average':
            # Analyze the averaged trace
            data = channel.get_averaged_data()
            time = channel.get_relative_averaged_time_vector()
            
            if data is None or time is None:
                log.warning(f"No averaged data available for {channel_name} in {file_path.name}")
                return [{
                    'file_name': file_path.name,
                    'file_path': str(file_path),
                    'channel': channel_name,
                    'analysis': analysis_name,
                    'scope': scope,
                    'error': "No averaged data available"
                }]
            
            # Run analysis
            try:
                result_dict = analysis_func(data, time, sampling_rate, **params)
                # Add metadata
                result_dict.update({
                    'file_name': file_path.name,
                    'file_path': str(file_path),
                    'channel': channel_name,
                    'analysis': analysis_name,
                    'scope': scope,
                    'trial_index': None,  # Average has no trial index
                    'sampling_rate': sampling_rate
                })
                results.append(result_dict)
            except Exception as e:
                log.error(f"Error running {analysis_name} on average trace: {e}", exc_info=True)
                results.append({
                    'file_name': file_path.name,
                    'file_path': str(file_path),
                    'channel': channel_name,
                    'analysis': analysis_name,
                    'scope': scope,
                    'error': str(e)
                })
                
        elif scope == 'all_trials':
            # Analyze each trial separately
            num_trials = channel.num_trials
            if num_trials == 0:
                log.warning(f"No trials available for {channel_name} in {file_path.name}")
                return [{
                    'file_name': file_path.name,
                    'file_path': str(file_path),
                    'channel': channel_name,
                    'analysis': analysis_name,
                    'scope': scope,
                    'error': "No trials available"
                }]
            
            for trial_idx in range(num_trials):
                data = channel.get_data(trial_idx)
                time = channel.get_relative_time_vector(trial_idx)
                
                if data is None or time is None:
                    log.warning(f"No data available for trial {trial_idx} of {channel_name} in {file_path.name}")
                    continue
                
                # Run analysis
                try:
                    result_dict = analysis_func(data, time, sampling_rate, **params)
                    # Add metadata
                    result_dict.update({
                        'file_name': file_path.name,
                        'file_path': str(file_path),
                        'channel': channel_name,
                        'analysis': analysis_name,
                        'scope': scope,
                        'trial_index': trial_idx,
                        'sampling_rate': sampling_rate
                    })
                    results.append(result_dict)
                except Exception as e:
                    log.error(f"Error running {analysis_name} on trial {trial_idx}: {e}", exc_info=True)
                    results.append({
                        'file_name': file_path.name,
                        'file_path': str(file_path),
                        'channel': channel_name,
                        'analysis': analysis_name,
                        'scope': scope,
                        'trial_index': trial_idx,
                        'error': str(e)
                    })
                    
        elif scope == 'first_trial':
            # Analyze only the first trial
            data = channel.get_data(0)
            time = channel.get_relative_time_vector(0)
            
            if data is None or time is None:
                log.warning(f"No data available for first trial of {channel_name} in {file_path.name}")
                return [{
                    'file_name': file_path.name,
                    'file_path': str(file_path),
                    'channel': channel_name,
                    'analysis': analysis_name,
                    'scope': scope,
                    'error': "No data available for first trial"
                }]
            
            # Run analysis
            try:
                result_dict = analysis_func(data, time, sampling_rate, **params)
                # Add metadata
                result_dict.update({
                    'file_name': file_path.name,
                    'file_path': str(file_path),
                    'channel': channel_name,
                    'analysis': analysis_name,
                    'scope': scope,
                    'trial_index': 0,
                    'sampling_rate': sampling_rate
                })
                results.append(result_dict)
            except Exception as e:
                log.error(f"Error running {analysis_name} on first trial: {e}", exc_info=True)
                results.append({
                    'file_name': file_path.name,
                    'file_path': str(file_path),
                    'channel': channel_name,
                    'analysis': analysis_name,
                    'scope': scope,
                    'error': str(e)
                })
        elif scope == 'channel_set':
            # Analyze all trials together as a set
            num_trials = channel.num_trials
            if num_trials == 0:
                log.warning(f"No trials available for {channel_name} in {file_path.name}")
                return [{
                    'file_name': file_path.name,
                    'file_path': str(file_path),
                    'channel': channel_name,
                    'analysis': analysis_name,
                    'scope': scope,
                    'error': "No trials available"
                }]
            
            # Aggregate data from all trials
            data_list = []
            time_list = []
            valid_trials = []
            
            for trial_idx in range(num_trials):
                data = channel.get_data(trial_idx)
                time = channel.get_relative_time_vector(trial_idx)
                
                if data is not None and time is not None:
                    data_list.append(data)
                    time_list.append(time)
                    valid_trials.append(trial_idx)
            
            if not data_list:
                log.warning(f"No valid data found for any trial of {channel_name} in {file_path.name}")
                return [{
                    'file_name': file_path.name,
                    'file_path': str(file_path),
                    'channel': channel_name,
                    'analysis': analysis_name,
                    'scope': scope,
                    'error': "No valid data found"
                }]
                
            # Run analysis on the aggregated set
            try:
                # The analysis function is expected to handle lists of arrays
                result_dict = analysis_func(data_list, time_list, sampling_rate, **params)
                
                # Add metadata
                result_dict.update({
                    'file_name': file_path.name,
                    'file_path': str(file_path),
                    'channel': channel_name,
                    'analysis': analysis_name,
                    'scope': scope,
                    'trial_count': len(valid_trials),
                    'sampling_rate': sampling_rate
                })
                results.append(result_dict)
            except Exception as e:
                log.error(f"Error running {analysis_name} on channel set: {e}", exc_info=True)
                results.append({
                    'file_name': file_path.name,
                    'file_path': str(file_path),
                    'channel': channel_name,
                    'analysis': analysis_name,
                    'scope': scope,
                    'error': str(e)
                })

        else:
            log.warning(f"Unknown scope '{scope}' for analysis '{analysis_name}'. Skipping.")
            results.append({
                'file_name': file_path.name,
                'file_path': str(file_path),
                'channel': channel_name,
                'analysis': analysis_name,
                'scope': scope,
                'error': f"Unknown scope: {scope}"
            })
        
        return results
