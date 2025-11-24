"""
Batch Analysis Engine for Synaptipy.
Handles processing multiple files and aggregating results using a flexible registry-based pipeline.
"""
import logging
import pandas as pd
from pathlib import Path
from typing import List, Dict, Any, Optional, Callable
import numpy as np

from Synaptipy.infrastructure.file_readers import NeoAdapter
from Synaptipy.core.analysis.registry import AnalysisRegistry

# Import analysis modules to trigger registration
import Synaptipy.core.analysis.spike_analysis  # noqa: F401 - Import triggers registration

log = logging.getLogger(__name__)


class BatchAnalysisEngine:
    """
    Engine for running analysis across multiple files/recordings using a flexible pipeline.
    
    The engine uses a registry-based architecture where analysis functions register
    themselves via decorators, and the pipeline configuration defines what analyses
    to run on which data scopes.
    """
    
    def __init__(self):
        self.neo_adapter = NeoAdapter()
        
    def run_batch(self, 
                  files: List[Path], 
                  pipeline_config: List[Dict[str, Any]],
                  progress_callback: Optional[Callable[[int, int, str], None]] = None) -> pd.DataFrame:
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
                    'analysis': 'spike_detection',
                    'scope': 'average',
                    'params': {'threshold': -10.0, 'refractory_ms': 2.0}
                }
            ]
        """
        results_list = []
        total_files = len(files)
        
        # Validate pipeline config
        if not pipeline_config:
            log.warning("Empty pipeline_config provided. No analyses will be run.")
            return pd.DataFrame()
        
        for i, file_path in enumerate(files):
            if progress_callback:
                progress_callback(i, total_files, f"Processing {file_path.name}...")
                
            try:
                # Load recording
                recording = self.neo_adapter.read_recording(file_path)
                if not recording:
                    log.warning(f"Failed to load {file_path}")
                    continue
                
                # Iterate through channels
                for channel_name, channel in recording.channels.items():
                    # Process each task in the pipeline
                    for task in pipeline_config:
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
                    'error': str(e)
                })
        
        if progress_callback:
            progress_callback(total_files, total_files, "Batch analysis complete.")
            
        return pd.DataFrame(results_list)
    
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
