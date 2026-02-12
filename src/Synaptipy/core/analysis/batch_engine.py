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
from typing import List, Dict, Any, Optional, Callable, Union, Tuple

import traceback  # Added for stack trace logging
from datetime import datetime

from Synaptipy.infrastructure.file_readers import NeoAdapter
from Synaptipy.core.analysis.registry import AnalysisRegistry
from Synaptipy.core.data_model import Recording

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
        log.debug("Batch analysis cancellation requested.")

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
            "name": name,
            "docstring": func.__doc__ or "No documentation available.",
            "module": func.__module__,
        }

    def run_batch(
        self,
        files: List[Union[Path, "Recording"]],
        pipeline_config: List[Dict[str, Any]],
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
        channel_filter: Optional[List[str]] = None,
    ) -> pd.DataFrame:
        """
        Run analysis on a list of files/recordings using a flexible pipeline configuration.

        Args:
            files: List of file paths OR Recording objects to process.
            pipeline_config: List of task dictionaries.
            progress_callback: Optional callback (current, total, status_msg).
            channel_filter: Optional list of channel names/IDs to process.

        Returns:
            pandas DataFrame containing aggregated results with metadata.
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

        for i, item in enumerate(files):
            # Check for cancellation
            if self._cancelled:
                log.debug("Batch analysis cancelled by user.")
                if progress_callback:
                    progress_callback(i, total_files, "Cancelled")
                break

            file_name = "Unknown"
            file_path_str = "InMemory"
            file_path = None  # Initialize file_path

            try:
                # Determine if item is Path or Recording
                recording = None
                if isinstance(item, (str, Path)):
                    file_path = Path(item)
                    file_name = file_path.name
                    file_path_str = str(file_path)

                    if progress_callback:
                        progress_callback(i, total_files, f"Processing {file_name}...")

                    # Load recording from disk with whitelist (Memory Optimization)
                    recording = self.neo_adapter.read_recording(file_path, channel_whitelist=channel_filter)
                    if not recording:
                        log.warning(f"Failed to load {file_path}")
                        results_list.append(
                            {"file_name": file_name, "file_path": file_path_str, "error": "Failed to load recording"}
                        )
                        continue

                else:
                    # Assume it is a Recording object
                    recording = item
                    if hasattr(recording, "source_file") and recording.source_file:
                        file_path = recording.source_file
                        file_name = recording.source_file.name
                        file_path_str = str(recording.source_file)
                    else:
                        # Fallback for purely in-memory recordings
                        file_path = Path(f"InMemory_Recording_{i}")
                        file_name = file_path.name
                        file_path_str = str(file_path)

                    if progress_callback:
                        progress_callback(i, total_files, f"Processing {file_name}...")

                # Filter channels if specified
                channels_to_process = recording.channels.items()
                if channel_filter:
                    log.debug(f"Applying channel filter: {channel_filter}")
                    channels_to_process = [
                        (name, ch)
                        for name, ch in recording.channels.items()
                        if name in channel_filter or str(name) in channel_filter
                    ]
                    if not channels_to_process:
                        log.warning(f"Channel filter {channel_filter} matched no channels in {file_name}.")

                log.debug(f"Processing {len(channels_to_process)} channels: {[n for n, c in channels_to_process]}")

                # Iterate through channels
                for channel_name, channel in channels_to_process:
                    # Check for cancellation
                    if self._cancelled:
                        break

                    # Data Buffer for the pipeline (stores (data, time) tuples or lists)
                    # Keyed by 'scope' to allow caching, but specialized for persistence
                    # We need a robust way to pass data between steps.
                    # As per plan, later steps consume data from previous steps if available.
                    # Currently, we'll support a 'channel_data' context.
                    pipeline_context = {
                        "scope": None,   # Current scope of data in context
                        "data": None,    # The data (array or list)
                        "time": None,    # The time (array or list)
                    }

                    # Process each task in the pipeline
                    for task in pipeline_config:
                        if self._cancelled:
                            break

                        try:
                            # Pass the context to allow tasks to use/modify it
                            task_results, updated_context = self._process_task(
                                task=task,
                                channel=channel,
                                channel_name=channel_name,
                                file_path=file_path,
                                context=pipeline_context
                            )
                            
                            # Update context if the task modified it (e.g. preprocessing)
                            if updated_context:
                                pipeline_context = updated_context

                            # Extend results list with all results from this task
                            results_list.extend(task_results)
                        except (ValueError, TypeError, KeyError, IndexError) as e:
                            log.error(
                                f"Error processing task {task.get('analysis', 'unknown')} on "
                                f"{file_path.name}/{channel_name}: {e}",
                                exc_info=True,
                            )
                            # Add error row
                            results_list.append(
                                {
                                    "file_name": file_path.name,
                                    "file_path": str(file_path),
                                    "channel": channel_name,
                                    "analysis": task.get("analysis", "unknown"),
                                    "scope": task.get("scope", "unknown"),
                                    "error": str(e),
                                    "debug_trace": traceback.format_exc(),
                                }
                            )

            except (ValueError, TypeError, KeyError, IndexError) as e:
                log.error(f"Error processing batch file {file_path}: {e}", exc_info=True)
                # Add error row
                results_list.append(
                    {
                        "file_name": file_path.name,
                        "file_path": str(file_path),
                        "error": str(e),
                        "debug_trace": traceback.format_exc(),
                    }
                )

        if progress_callback:
            if self._cancelled:
                progress_callback(i, total_files, "Batch analysis cancelled.")
            else:
                progress_callback(total_files, total_files, "Batch analysis complete.")

        # Create DataFrame and add batch metadata
        df = pd.DataFrame(results_list)
        if not df.empty:
            df["batch_timestamp"] = batch_start_time.isoformat()

        return df

    def _process_task(
        self,
        task: Dict[str, Any],
        channel,
        channel_name: str,
        file_path: Path,
        context: Dict[str, Any]
    ) -> Tuple[List[Dict[str, Any]], Optional[Dict[str, Any]]]:
        """
        Process a single analysis task on a channel, supporting preprocessing.

        Args:
            task: Task configuration dict
            channel: Channel object
            channel_name: Name/ID
            file_path: Path
            context: Current data context from previous steps

        Returns:
            Tuple: (List of results, Updated context or None)
        """
        analysis_name = task.get("analysis")
        scope = task.get("scope", "first_trial")
        params = task.get("params", {})
        
        # Check metadata for type
        meta = AnalysisRegistry.get_metadata(analysis_name)
        is_preprocessing = meta.get("type") == "preprocessing"

        # Get the registered analysis function
        analysis_func = AnalysisRegistry.get_function(analysis_name)
        if analysis_func is None:
            log.error(f"Analysis function '{analysis_name}' not found in registry")
            return [
                {
                    "file_name": file_path.name,
                    "file_path": str(file_path),
                    "channel": channel_name,
                    "analysis": analysis_name,
                    "scope": scope,
                    "error": f"Analysis function '{analysis_name}' not registered",
                }
            ], None

        results = []
        sampling_rate = channel.sampling_rate
        
        # --- Data Retrieval Strategy ---
        # 1. If context matches requested scope, use it.
        # 2. If context exists but scope differs, try to adapt (e.g. average existing trials).
        # 3. If no context, load from channel.
        
        data = None
        time = None
        
        # Check if we can use context
        if context["data"] is not None:
            # If scope matches, use directly
            if context["scope"] == scope:
                data = context["data"]
                time = context["time"]
            
            # Adaptation: If we have 'all_trials' data but need 'average'
            elif context["scope"] == "all_trials" and scope == "average":
                # Compute average from cached trials
                # context['data'] is list of arrays
                try:
                    import numpy as np
                    # Assume equal length for averaging - simplified for now
                    # In production, check lengths or align
                    if len(context["data"]) > 0:
                        data = np.mean(context["data"], axis=0) # Only works if all same shape
                        time = context["time"][0] # Use first time vector
                    else:
                        log.warning("Context data empty, cannot average.")
                except Exception as e:
                    log.warning(f"Could not compute average from context: {e}. Reloading from source.")
                    
        # If data is still None, load from channel
        if data is None:
            if scope == "average":
                data = channel.get_averaged_data()
                time = channel.get_relative_averaged_time_vector()
            elif scope == "all_trials":
                data = []
                time = []
                for i in range(channel.num_trials):
                    d = channel.get_data(i)
                    t = channel.get_relative_time_vector(i)
                    if d is not None:
                        data.append(d)
                        time.append(t)
                # If loading raw, we might want to update context if this was a heavy load?
                # For now, only update context if preprocessing occurs.
                
            elif scope == "first_trial":
                data = channel.get_data(0)
                time = channel.get_relative_time_vector(0)
                
            elif scope == "specific_trial":
                idx = int(params.get("trial_index", 0))
                data = channel.get_data(idx)
                time = channel.get_relative_time_vector(idx)
                
            elif scope == "channel_set":
                # channel_set usually implies list of all trials
                data = []
                time = []
                for i in range(channel.num_trials):
                    d = channel.get_data(i)
                    t = channel.get_relative_time_vector(i)
                    if d is not None:
                        data.append(d)
                        time.append(t)

        # Validation
        if data is None or (isinstance(data, list) and len(data) == 0):
             return [{
                    "file_name": file_path.name,
                    "file_path": str(file_path),
                    "channel": channel_name,
                    "analysis": analysis_name,
                    "error": "No data available",
                }], None
                
        # --- Execution ---
        
        if is_preprocessing:
            # Preprocessing: Modify data and return new context
            try:
                # Preprocessing functions typically take (data, time, fs, **kwargs)
                # and return modified data. 
                # If scope is 'all_trials', we might need to iterate if the func expects single trace.
                
                # Heuristic: Check if data is list (multiple trials)
                if isinstance(data, list):
                    # Apply to each item
                    new_data = []
                    new_time = [] 
                    for d, t in zip(data, time):
                        # Filter might modify data or time? Usually just data.
                        # Some filters might return (data, time) tuple?
                        # Let's assume standard signature returns just data for now, 
                        # or we check return type.
                        res = analysis_func(d, t, sampling_rate, **params)
                        new_data.append(res)
                        new_time.append(t) # Assume time unchanged
                    
                    modified_data = new_data
                    modified_time = new_time
                else:
                    # Single trace
                    modified_data = analysis_func(data, time, sampling_rate, **params)
                    modified_time = time
                
                # Return empty results, but updated context
                new_context = {
                    "scope": scope,
                    "data": modified_data,
                    "time": modified_time
                }
                return [], new_context
                
            except Exception as e:
                log.error(f"Preprocessing failed: {e}", exc_info=True)
                return [{
                    "file_name": file_path.name,
                    "analysis": analysis_name,
                    "error": f"Preprocessing failed: {e}"
                }], None
        
        else:
            # Standard Analysis
            try:
                # Helper to run analysis and format result
                def run_single(d, t, trial_idx=None):
                    # Remove trial_index from params if present
                    p = params.copy()
                    p.pop("trial_index", None)
                    
                    res = analysis_func(d, t, sampling_rate, **p)
                    # Add metadata
                    res.update({
                        "file_name": file_path.name,
                        "file_path": str(file_path),
                        "channel": channel_name,
                        "analysis": analysis_name,
                        "scope": scope,
                        "sampling_rate": sampling_rate
                    })
                    if trial_idx is not None:
                        res["trial_index"] = trial_idx
                    return res

                if scope == "all_trials" or scope == "channel_set":
                     # For channel_set, some functions expect the list (e.g. F-I curve)
                     # others expect iteration. 
                     # Check if function handles list? 
                     # NOTE: Original code treated 'channel_set' as passing the list to func.
                     # 'all_trials' iterated.
                     
                     if scope == "channel_set":
                         # Pass full list
                         res = analysis_func(data, time, sampling_rate, **params)
                         res.update({
                            "file_name": file_path.name,
                             "file_path": str(file_path),
                            "channel": channel_name,
                            "analysis": analysis_name,
                            "scope": scope,
                            "trial_count": len(data) if isinstance(data, list) else 1,
                         })
                         results.append(res)
                     else:
                        # Iterate 'all_trials'
                        for idx, (d, t) in enumerate(zip(data, time)):
                            results.append(run_single(d, t, idx))
                            
                elif scope == "specific_trial":
                     idx = int(params.get("trial_index", 0))
                     results.append(run_single(data, time, idx))
                else:
                    # Single trace (average, first_trial)
                    results.append(run_single(data, time))
                    
                return results, None # No context update

            except Exception as e:
                log.error(f"Analysis failed: {e}", exc_info=True)
                return [{
                    "file_name": file_path.name,
                    "analysis": analysis_name,
                    "error": f"Analysis failed: {e}"
                }], None
