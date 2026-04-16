"""
Batch Analysis Engine for Synaptipy.
Handles processing multiple files and aggregating results using a flexible registry-based pipeline.

The engine uses a registry-based architecture where analysis functions register
themselves via decorators, and the pipeline configuration defines what analyses
to run on which data scopes.

Output Design Principles
------------------------
1. Every row is fully traceable to its source (file, channel, trial, analysis).
2. Metadata columns appear first; analysis results in the middle; internal/debug last.
3. Scalar results live in their own columns; array values are summarised for tabular
   compatibility (Excel, Origin, R, MATLAB) and the raw arrays are kept under
   private ``_``-prefixed keys that are stripped during CSV export.
4. Channel physical units are always recorded so downstream scripts can auto-label axes.
5. Recording-level metadata (protocol, duration, session time) is propagated when available.

Author: Anzal K Shahul <anzal.ks@gmail.com>
"""

import gc
import logging
import multiprocessing
import traceback  # Added for stack trace logging
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

import numpy as np
import pandas as pd

# Import analysis package to trigger all registrations
import Synaptipy.core.analysis  # noqa: F401 - Import triggers all registrations
from Synaptipy.core.analysis.registry import AnalysisRegistry
from Synaptipy.core.data_model import Recording
from Synaptipy.infrastructure.file_readers import NeoAdapter

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Column ordering constants — metadata first, results middle, debug last
# ---------------------------------------------------------------------------
_METADATA_COLUMNS_ORDER = [
    "subject_id",
    "cell_id",
    "file_name",
    "file_path",
    "protocol",
    "recording_duration_s",
    "channel",
    "channel_units",
    "analysis",
    "scope",
    "trial_index",
    "trial_count",
    "sampling_rate",
]
_TRAILING_COLUMNS = [
    "batch_timestamp",
    "error",
    "debug_trace",
]

# Human-readable aliases for result keys that lack biological context.
# Only applied as *additional* columns; originals are preserved for scripting.
_HUMAN_READABLE_ALIASES: Dict[str, str] = {
    "cv": "coeff_of_variation",
    "cv2": "local_cv2_holt",
    "lv": "local_variation_shinomoto",
    "fi_slope": "fi_gain_hz_per_pa",
    "fi_r_squared": "fi_fit_r_squared",
    "iv_r_squared": "iv_fit_r_squared",
}


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

    def __init__(self, neo_adapter: Optional[NeoAdapter] = None, max_workers: int = 1):
        """
        Initialize the batch analysis engine.

        Args:
            neo_adapter: Optional NeoAdapter instance. If None, creates a new one.
            max_workers: Number of parallel worker processes for :meth:`run_batch`.
                         1 (default) means fully sequential execution.
                         Values > 1 enable :class:`~concurrent.futures.ProcessPoolExecutor`
                         parallelism.  Pass ``-1`` to use all available CPU cores.
        """
        self.neo_adapter = neo_adapter if neo_adapter else NeoAdapter()
        self._cancelled = False
        cpu_count = multiprocessing.cpu_count()
        if max_workers < 0:
            self.max_workers: int = cpu_count
        else:
            self.max_workers = max(1, int(max_workers))

    def cancel(self):
        """Request cancellation of the current batch run."""
        self._cancelled = True
        log.debug("Batch analysis cancellation requested.")

    def update_performance_settings(self, settings: Dict[str, Any]) -> None:
        """Dynamically update performance limits without restarting.

        Reads ``max_cpu_cores`` from *settings* and updates :attr:`max_workers`
        immediately so the next :meth:`run_batch` call picks up the new value.
        This is the subscriber side of the pub/sub ``preferences_changed`` signal.

        Args:
            settings: Dict that may contain ``"max_cpu_cores"`` (int) and/or
                      ``"max_ram_allocation_gb"`` (float, logged but not enforced here).
        """
        if "max_cpu_cores" in settings:
            requested = int(settings["max_cpu_cores"])
            cpu_count = multiprocessing.cpu_count()
            self.max_workers = max(1, min(requested, cpu_count))
            log.info("BatchAnalysisEngine: max_workers updated to %d.", self.max_workers)

        if "max_ram_allocation_gb" in settings:
            log.info(
                "BatchAnalysisEngine: max_ram_allocation_gb=%s noted (OOM guard via gc.collect).",
                settings["max_ram_allocation_gb"],
            )

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

    # ------------------------------------------------------------------
    # Output post-processing helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _sanitise_value(key: str, value: Any) -> Tuple[Any, Optional[Tuple[str, Any]]]:
        """Sanitise a single result value for export.

        Returns:
            Tuple of (replacement_value, optional (stash_key, stash_value)).
        """
        if isinstance(value, np.ndarray):
            return BatchAnalysisEngine._sanitise_ndarray(key, value)
        if isinstance(value, list) and len(value) > 5:
            return BatchAnalysisEngine._sanitise_long_list(key, value)
        if not isinstance(value, (int, float, str, bool, type(None))):
            return f"{type(value).__name__}", (f"_{key}_obj", value)
        return value, None

    @staticmethod
    def _sanitise_ndarray(key: str, value: np.ndarray) -> Tuple[Any, Optional[Tuple[str, Any]]]:
        """Summarise numpy arrays for CSV-friendly output."""
        if value.size <= 5:
            return value.tolist(), None
        summary = f"n={value.size}"
        if np.issubdtype(value.dtype, np.floating):
            summary = (
                f"n={value.size}, "
                f"mean={np.nanmean(value):.4g}, "
                f"min={np.nanmin(value):.4g}, "
                f"max={np.nanmax(value):.4g}"
            )
        return summary, (f"_{key}_raw", value)

    @staticmethod
    def _sanitise_long_list(key: str, value: list) -> Tuple[Any, Optional[Tuple[str, Any]]]:
        """Summarise long lists for CSV-friendly output."""
        try:
            arr = np.asarray(value, dtype=float)
            summary = (
                f"n={arr.size}, "
                f"mean={np.nanmean(arr):.4g}, "
                f"min={np.nanmin(arr):.4g}, "
                f"max={np.nanmax(arr):.4g}"
            )
            return summary, (f"_{key}_raw", arr)
        except (ValueError, TypeError):
            return f"[{len(value)} items]", None

    @staticmethod
    def _sanitise_result_for_export(result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Make a single result row export-friendly.

        1. Non-scalar values (numpy arrays, lists, complex objects) are summarised
           as human-readable strings and the raw data moved to ``_``-prefixed keys.
        2. Human-readable aliases are added for cryptic algorithm names.
        3. Private keys are preserved internally but clearly marked.

        Returns:
            Cleaned result dict (modified in-place for efficiency).
        """
        keys_to_add: Dict[str, Any] = {}

        for key, value in list(result.items()):
            if key.startswith("_"):
                continue
            new_value, stash = BatchAnalysisEngine._sanitise_value(key, value)
            result[key] = new_value
            if stash is not None:
                keys_to_add[stash[0]] = stash[1]

        result.update(keys_to_add)

        # Add human-readable aliases for cryptic keys
        for orig_key, alias in _HUMAN_READABLE_ALIASES.items():
            if orig_key in result and alias not in result:
                result[alias] = result[orig_key]

        return result

    @staticmethod
    def _recording_metadata(recording: "Recording") -> Dict[str, Any]:
        """Extract recording-level metadata for result rows.

        Includes ``subject_id`` and ``cell_id`` when set on the Recording so
        that downstream hierarchical mixed-effects analyses can distinguish
        between-subject (N) from within-subject (n) observations.
        """
        meta: Dict[str, Any] = {}
        if recording is None:
            return meta
        if hasattr(recording, "protocol_name") and recording.protocol_name:
            meta["protocol"] = recording.protocol_name
        if hasattr(recording, "duration") and recording.duration is not None:
            meta["recording_duration_s"] = round(float(recording.duration), 4)
        if hasattr(recording, "subject_id"):
            meta["subject_id"] = recording.subject_id
        if hasattr(recording, "cell_id"):
            meta["cell_id"] = recording.cell_id
        return meta

    @staticmethod
    def _order_columns(df: pd.DataFrame) -> pd.DataFrame:
        """Reorder DataFrame columns: metadata → results → trailing/debug."""
        if df.empty:
            return df

        all_cols = list(df.columns)

        # 1. Leading metadata columns (in defined order)
        leading = [c for c in _METADATA_COLUMNS_ORDER if c in all_cols]

        # 2. Trailing debug/internal columns
        trailing = [c for c in _TRAILING_COLUMNS if c in all_cols]

        # 3. Private columns (underscore-prefixed)
        private = sorted(c for c in all_cols if c.startswith("_"))

        # 4. Everything else = result columns, alphabetically
        used = set(leading) | set(trailing) | set(private)
        results = sorted(c for c in all_cols if c not in used)

        ordered = leading + results + trailing + private
        return df[[c for c in ordered if c in all_cols]]

    @staticmethod
    def _append_batch_error_log(file_name: str, file_path_str: str, exc: Exception) -> None:
        """Append a one-line error entry to ``~/.synaptipy/logs/batch_errors.log``.

        Writing errors to a dedicated log file ensures a 100-file batch is never
        aborted by a single corrupted recording.  Each line is ISO-8601 timestamped
        so the analyst can correlate entries with their batch run.

        Args:
            file_name:     Base name of the failed file.
            file_path_str: Full path string for the failed file.
            exc:           The exception that caused the failure.
        """
        try:
            log_dir = Path.home() / ".synaptipy" / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            error_log_path = log_dir / "batch_errors.log"
            timestamp = datetime.now().isoformat(timespec="seconds")
            entry = f"{timestamp} | {file_name} | {file_path_str} | {type(exc).__name__}: {exc}\n"
            with open(error_log_path, "a", encoding="utf-8") as fh:
                fh.write(entry)
        except Exception as write_exc:  # noqa: BLE001
            log.warning("Could not write to batch_errors.log: %s", write_exc)

    # ------------------------------------------------------------------
    # Parallel execution helpers
    # ------------------------------------------------------------------

    def _run_batch_parallel(  # noqa: C901
        self,
        files: List[Union[Path, "Recording"]],
        pipeline_config: List[Dict[str, Any]],
        progress_callback: Optional[Callable[[int, int, str], None]],
        channel_filter: Optional[List[str]],
    ) -> pd.DataFrame:
        """Distribute file-level processing across :attr:`max_workers` worker processes.

        Each worker process receives a single file path (in-memory Recording objects
        are serialised via pickle), imports the full analysis package to populate the
        registry, and returns a list of result-row dicts.  Progress signals are emitted
        through the optional *progress_callback* as each future completes.

        OOM safety: every worker calls ``gc.collect()`` after processing its file.
        """
        total_files = len(files)
        batch_start_time = datetime.now()

        # Separate paths from pre-loaded Recording objects.
        # Pre-loaded Recording objects are processed sequentially (pickle cost not worth it).
        path_tasks: List[Tuple[int, Path]] = []
        inline_recordings: List[Tuple[int, Any]] = []

        for idx, item in enumerate(files):
            if isinstance(item, (str, Path)):
                path_tasks.append((idx, Path(item)))
            else:
                inline_recordings.append((idx, item))

        all_rows: List[List[Dict[str, Any]]] = [[] for _ in range(total_files)]
        completed_count = 0

        # Submit path-based tasks to the pool
        future_to_idx: Dict[Any, int] = {}
        pool_kwargs: Dict[str, Any] = {"max_workers": self.max_workers}
        # Use spawn context on all platforms for process-safety with Qt/numpy
        ctx = multiprocessing.get_context("spawn")
        pool_kwargs["mp_context"] = ctx

        with ProcessPoolExecutor(**pool_kwargs) as executor:
            for orig_idx, file_path in path_tasks:
                future = executor.submit(
                    _worker_process_file,
                    str(file_path),
                    pipeline_config,
                    channel_filter,
                )
                future_to_idx[future] = orig_idx

            for future in as_completed(future_to_idx):
                orig_idx = future_to_idx[future]
                file_path = files[orig_idx]
                file_name = Path(str(file_path)).name
                completed_count += 1

                try:
                    rows = future.result()
                    all_rows[orig_idx] = rows
                except Exception as exc:  # noqa: BLE001
                    log.error("Worker failed for %s: %s", file_path, exc, exc_info=True)
                    self._append_batch_error_log(file_name, str(file_path), exc)
                    all_rows[orig_idx] = [
                        {
                            "file_name": file_name,
                            "file_path": str(file_path),
                            "error": str(exc),
                            "debug_trace": traceback.format_exc(),
                        }
                    ]
                finally:
                    if progress_callback:
                        progress_callback(completed_count, total_files, f"Processed {file_name}")

                if self._cancelled:
                    executor.shutdown(wait=False, cancel_futures=True)
                    break

        # Process in-memory recordings sequentially (they can't be pickled reliably)
        for orig_idx, recording in inline_recordings:
            if self._cancelled:
                break
            completed_count += 1
            file_name = getattr(getattr(recording, "source_file", None), "name", f"InMemory_{orig_idx}")
            if progress_callback:
                progress_callback(completed_count, total_files, f"Processing {file_name}...")
            try:
                df_inline = self._run_batch_sequential([recording], pipeline_config, None, channel_filter)
                all_rows[orig_idx] = df_inline.to_dict("records") if not df_inline.empty else []
            except Exception as exc:  # noqa: BLE001
                log.error("Inline recording failed: %s", exc, exc_info=True)
                all_rows[orig_idx] = [
                    {"file_name": file_name, "error": str(exc), "debug_trace": traceback.format_exc()}
                ]

        if progress_callback:
            msg = "Batch cancelled." if self._cancelled else "Batch analysis complete."
            progress_callback(total_files, total_files, msg)

        flat_rows = [row for rows in all_rows for row in rows]
        df = pd.DataFrame(flat_rows)
        if not df.empty:
            df["batch_timestamp"] = batch_start_time.isoformat()
            df = self._order_columns(df)
        return df

    def run_batch(  # noqa: C901
        self,
        files: List[Union[Path, "Recording"]],
        pipeline_config: List[Dict[str, Any]],
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
        channel_filter: Optional[List[str]] = None,
    ) -> pd.DataFrame:
        """
        Run analysis on a list of files/recordings using a flexible pipeline configuration.

        When :attr:`max_workers` > 1 **and** *files* contains at least two items, the
        file-level loop is distributed across worker processes via
        :class:`~concurrent.futures.ProcessPoolExecutor`.  The GUI thread is never
        blocked in either mode — callers should wrap this in a
        :class:`~Synaptipy.application.gui.analysis_worker.BatchWorker` QThread.

        Args:
            files: List of file paths OR Recording objects to process.
            pipeline_config: List of task dictionaries.
            progress_callback: Optional callback (current, total, status_msg).
            channel_filter: Optional list of channel names/IDs to process.

        Returns:
            pandas DataFrame containing aggregated results with metadata.
        """
        self._cancelled = False
        total_files = len(files)

        # Validate pipeline config
        if not pipeline_config:
            log.warning("Empty pipeline_config provided. No analyses will be run.")
            return pd.DataFrame()

        # Route to parallel executor when max_workers > 1 and we have multiple files
        if self.max_workers > 1 and total_files > 1:
            log.info(
                "BatchAnalysisEngine: starting parallel batch (%d workers, %d files).", self.max_workers, total_files
            )
            return self._run_batch_parallel(files, pipeline_config, progress_callback, channel_filter)

        return self._run_batch_sequential(files, pipeline_config, progress_callback, channel_filter)

    def _run_batch_sequential(  # noqa: C901
        self,
        files: List[Union[Path, "Recording"]],
        pipeline_config: List[Dict[str, Any]],
        progress_callback: Optional[Callable[[int, int, str], None]],
        channel_filter: Optional[List[str]],
    ) -> pd.DataFrame:
        """Sequential (single-process) batch processing — the original implementation."""
        results_list = []
        total_files = len(files)

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

                # Extract recording-level metadata once per file
                rec_meta = self._recording_metadata(recording)

                # Iterate through channels
                for channel_key, channel in channels_to_process:
                    # Check for cancellation
                    if self._cancelled:
                        break

                    # Prefer the native channel name from the acquisition file header.
                    # Fall back to the channel key (ID) only when no name is available.
                    native_channel_name = getattr(channel, "name", None)
                    channel_name = native_channel_name if native_channel_name else channel_key

                    # Per-channel metadata available to every result row
                    ch_meta = {
                        "channel_units": getattr(channel, "units", "unknown"),
                        "trial_count": getattr(channel, "num_trials", 0),
                    }
                    ch_meta.update(rec_meta)

                    # Data Buffer for the pipeline (stores (data, time) tuples or lists)
                    pipeline_context = {
                        "scope": None,  # Current scope of data in context
                        "data": None,  # The data (array or list)
                        "time": None,  # The time (array or list)
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
                                context=pipeline_context,
                            )

                            # Update context if the task modified it (e.g. preprocessing)
                            if updated_context:
                                pipeline_context = updated_context

                            # Enrich each result row with channel/recording metadata
                            for res in task_results:
                                for mk, mv in ch_meta.items():
                                    res.setdefault(mk, mv)
                                # Sanitise for export (arrays → summaries, aliases)
                                self._sanitise_result_for_export(res)

                            # Extend results list with all results from this task
                            results_list.extend(task_results)
                        except Exception as e:  # noqa: BLE001 - broad catch intentional for fault-tolerance
                            log.error(
                                f"Error processing task {task.get('analysis', 'unknown')} on "
                                f"{file_path.name}/{channel_name}: {e}",
                                exc_info=True,
                            )
                            # Add error row — include full metadata for filtering
                            error_row = {
                                "file_name": file_path.name,
                                "file_path": str(file_path),
                                "channel": channel_name,
                                "analysis": task.get("analysis", "unknown"),
                                "scope": task.get("scope", "unknown"),
                                "sampling_rate": getattr(channel, "sampling_rate", None),
                                "error": str(e),
                                "debug_trace": traceback.format_exc(),
                            }
                            error_row.update(ch_meta)
                            results_list.append(error_row)
                            continue

            except Exception as e:  # noqa: BLE001 - broad catch intentional; Domino Defense
                # A single corrupted or unreadable file must never abort the entire batch run.
                # Log the full traceback to batch_errors.log and continue to the next file.
                log.error(f"Error processing batch file {file_path}: {e}", exc_info=True)
                self._append_batch_error_log(file_name, file_path_str, e)
                results_list.append(
                    {
                        "file_name": file_name,
                        "file_path": file_path_str,
                        "error": str(e),
                        "debug_trace": traceback.format_exc(),
                    }
                )
                continue
            finally:
                # Release the Recording object and collected data immediately after
                # each file to prevent cumulative PySide6 / NumPy OOM in headless batch
                # runs.  gc.collect() ensures cyclic references are broken even when
                # GC is otherwise disabled for test-mode offscreen stability.
                recording = None  # noqa: F841  # drop reference
                gc.collect()
                log.debug("gc.collect() called after processing item %d.", i)

        if progress_callback:
            if self._cancelled:
                progress_callback(i, total_files, "Batch analysis cancelled.")
            else:
                progress_callback(total_files, total_files, "Batch analysis complete.")

        # Create DataFrame and add batch metadata
        df = pd.DataFrame(results_list)
        if not df.empty:
            df["batch_timestamp"] = batch_start_time.isoformat()
            df = self._order_columns(df)

        return df

    def _process_task(  # noqa: C901
        self, task: Dict[str, Any], channel, channel_name: str, file_path: Path, context: Dict[str, Any]
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
                        data = np.mean(context["data"], axis=0)  # Only works if all same shape
                        time = context["time"][0]  # Use first time vector
                    else:
                        log.warning("Context data empty, cannot average.")
                except Exception as e:
                    log.warning(f"Could not compute average from context: {e}. Reloading from source.")

            # Adaptation: If we have 'all_trials' data but need 'selected_trials_average'
            elif context["scope"] == "all_trials" and scope == "selected_trials_average":
                try:
                    import numpy as np

                    # Extract list of indices from task params, or default to all
                    trial_indices_str = params.get("trial_indices", "")
                    if trial_indices_str:
                        from Synaptipy.shared.utils import parse_trial_selection_string

                        # context['data'] length should be num_trials if it was 'all_trials'
                        parsed_indices = parse_trial_selection_string(trial_indices_str, len(context["data"]))
                        selected_indices = sorted(list(parsed_indices))
                    else:
                        selected_indices = list(range(len(context["data"])))

                    if selected_indices:
                        selected_data = [context["data"][i] for i in selected_indices if i < len(context["data"])]
                        data = np.mean(selected_data, axis=0)  # Average only selected
                        time = context["time"][0]  # Use first time vector
                    else:
                        log.warning("No valid trials selected for averaging from context.")
                except Exception as e:
                    log.warning(f"Could not compute selected average from context: {e}. Reloading from source.")

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

            elif scope == "selected_trials":
                data = []
                time = []
                trial_indices_str = params.get("trial_indices", "")
                if trial_indices_str:
                    from Synaptipy.shared.utils import parse_trial_selection_string

                    parsed_indices = parse_trial_selection_string(trial_indices_str, channel.num_trials)
                    selected_indices = sorted(list(parsed_indices))
                else:
                    selected_indices = list(range(channel.num_trials))

                for i in selected_indices:
                    d = channel.get_data(i)
                    t = channel.get_relative_time_vector(i)
                    if d is not None:
                        data.append(d)
                        time.append(t)

            elif scope == "selected_trials_average":
                trial_indices_str = params.get("trial_indices", "")
                if trial_indices_str:
                    from Synaptipy.shared.utils import parse_trial_selection_string

                    parsed_indices = parse_trial_selection_string(trial_indices_str, channel.num_trials)
                    selected_indices = sorted(list(parsed_indices))
                else:
                    selected_indices = None

                data = channel.get_averaged_data(trial_indices=selected_indices)
                time = channel.get_relative_averaged_time_vector()

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
            return [
                {
                    "file_name": file_path.name,
                    "file_path": str(file_path),
                    "channel": channel_name,
                    "analysis": analysis_name,
                    "error": "No data available",
                }
            ], None

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
                        new_time.append(t)  # Assume time unchanged

                    modified_data = new_data
                    modified_time = new_time
                else:
                    # Single trace
                    modified_data = analysis_func(data, time, sampling_rate, **params)
                    modified_time = time

                # Return empty results, but updated context
                new_context = {"scope": scope, "data": modified_data, "time": modified_time}
                return [], new_context

            except Exception as e:
                log.error(f"Preprocessing failed: {e}", exc_info=True)
                return [
                    {
                        "file_name": file_path.name,
                        "file_path": str(file_path),
                        "channel": channel_name,
                        "analysis": analysis_name,
                        "scope": scope,
                        "sampling_rate": sampling_rate,
                        "error": f"Preprocessing failed: {e}",
                        "debug_trace": traceback.format_exc(),
                    }
                ], None

        else:
            # Standard Analysis
            try:
                # Helper to run analysis and format result
                total_trials = getattr(channel, "num_trials", 0)

                def run_single(d, t, trial_idx=None):
                    # Remove trial_index from params if present
                    p = params.copy()
                    p.pop("trial_index", None)

                    res = analysis_func(d, t, sampling_rate, **p)
                    # Flatten consolidated-module schema: {"module_used": ..., "metrics": {...}}
                    if "metrics" in res and isinstance(res.get("metrics"), dict):
                        metrics = res.pop("metrics")
                        res.update(metrics)
                    # Add metadata
                    res.update(
                        {
                            "file_name": file_path.name,
                            "file_path": str(file_path),
                            "channel": channel_name,
                            "analysis": analysis_name,
                            "scope": scope,
                            "sampling_rate": sampling_rate,
                            "trial_count": total_trials,
                        }
                    )
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
                        # Flatten consolidated-module schema: {"module_used": ..., "metrics": {...}}
                        if "metrics" in res and isinstance(res.get("metrics"), dict):
                            metrics = res.pop("metrics")
                            res.update(metrics)
                        res.update(
                            {
                                "file_name": file_path.name,
                                "file_path": str(file_path),
                                "channel": channel_name,
                                "analysis": analysis_name,
                                "scope": scope,
                                "sampling_rate": sampling_rate,
                                "trial_count": len(data) if isinstance(data, list) else 1,
                            }
                        )
                        results.append(res)
                    else:
                        # Iterate 'all_trials' or 'selected_trials'
                        # For 'selected_trials', extract the specific indices used
                        if scope == "selected_trials":
                            trial_indices_str = task.get("params", {}).get("trial_indices", "")
                            if trial_indices_str:
                                from Synaptipy.shared.utils import parse_trial_selection_string

                                parsed_indices = parse_trial_selection_string(trial_indices_str, total_trials)
                                indices_list = sorted(list(parsed_indices))
                            else:
                                indices_list = list(range(total_trials))
                        else:
                            indices_list = list(range(total_trials))

                        for i, (d, t) in enumerate(zip(data, time)):
                            # Ensure we output correct trial index
                            real_idx = indices_list[i] if i < len(indices_list) else i
                            results.append(run_single(d, t, real_idx))

                elif scope == "specific_trial":
                    idx = int(params.get("trial_index", 0))
                    results.append(run_single(data, time, idx))
                else:
                    # Single trace (average, first_trial)
                    results.append(run_single(data, time))

                return results, None  # No context update

            except Exception as e:
                log.error(f"Analysis failed: {e}", exc_info=True)
                return [
                    {
                        "file_name": file_path.name,
                        "file_path": str(file_path),
                        "channel": channel_name,
                        "analysis": analysis_name,
                        "scope": scope,
                        "sampling_rate": sampling_rate,
                        "error": f"Analysis failed: {e}",
                        "debug_trace": traceback.format_exc(),
                    }
                ], None


# ---------------------------------------------------------------------------
# Module-level worker function for ProcessPoolExecutor
# ---------------------------------------------------------------------------


def _worker_process_file(
    file_path_str: str,
    pipeline_config: List[Dict[str, Any]],
    channel_filter: Optional[List[str]],
) -> List[Dict[str, Any]]:
    """Process a single file in an isolated worker process.

    This function is called by :class:`~concurrent.futures.ProcessPoolExecutor`
    in a freshly spawned process.  It re-imports the full analysis package so
    that all ``@AnalysisRegistry.register`` decorators execute, then delegates
    to :class:`BatchAnalysisEngine` with ``max_workers=1`` (sequential) to avoid
    recursive parallelism.

    OOM safety: ``gc.collect()`` is called explicitly after processing.

    Args:
        file_path_str: Absolute path to the recording file (str, pickle-safe).
        pipeline_config: Serialised pipeline task list.
        channel_filter: Optional channel whitelist.

    Returns:
        List of result-row dicts ready for ``pd.DataFrame()``.
    """
    import gc as _gc  # avoid shadowing module-level gc import
    from pathlib import Path as _Path

    # Trigger all @AnalysisRegistry.register decorators in this new process
    import Synaptipy.core.analysis  # noqa: F401,F811

    engine = BatchAnalysisEngine(max_workers=1)
    try:
        df = engine._run_batch_sequential(
            [_Path(file_path_str)],
            pipeline_config,
            None,  # progress_callback not serialisable across processes
            channel_filter,
        )
        return df.to_dict("records") if not df.empty else []
    finally:
        _gc.collect()
