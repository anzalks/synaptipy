"""
Batch Analysis Engine for synaptipy.
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
import synaptipy.core.analysis  # noqa: F401 - Import triggers all registrations
from synaptipy.core.analysis.cross_file_utils import (
    average_time_aligned_trials,
    canonical_unit_and_scale,
    sampling_rate_from_timebase,
    time_bases_compatible,
)
from synaptipy.core.analysis.registry import AnalysisRegistry
from synaptipy.core.data_model import Channel, Recording
from synaptipy.core.protocols import ProtocolMap, ResolvedProtocol, resolve_protocols, slice_segment
from synaptipy.core.trial_qc import summarise_trial_qc
from synaptipy.infrastructure.file_readers import NeoAdapter

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
    "protocol_family",
    "protocol_fingerprint",
    "protocol_source",
    "protocol_status",
    "protocol_assignment_id",
    "segment_start_s",
    "segment_end_s",
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

    Example::

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

    # Raw electrophysiology files routinely expand while Neo/NumPy objects,
    # trial arrays, and analysis intermediates are created.  This conservative
    # multiplier keeps the configured RAM budget meaningful without assuming a
    # particular file format or compression ratio.
    _RAM_ESTIMATE_MULTIPLIER = 4

    def __init__(
        self,
        neo_adapter: Optional[NeoAdapter] = None,
        max_workers: int = 1,
        max_ram_allocation_gb: Optional[float] = None,
    ):
        """
        Initialize the batch analysis engine.

        Args:
            neo_adapter: Optional NeoAdapter instance. If None, creates a new one.
            max_workers: Number of parallel worker processes for :meth:`run_batch`.
                         1 (default) means fully sequential execution.
                         Values > 1 enable :class:`~concurrent.futures.ProcessPoolExecutor`
                         parallelism.  Pass ``-1`` to use all available CPU cores.
            max_ram_allocation_gb: Optional total memory budget used to cap
                concurrent file workers conservatively.
        """
        self.neo_adapter = neo_adapter if neo_adapter else NeoAdapter()
        self._cancelled = False
        cpu_count = multiprocessing.cpu_count()
        if max_workers < 0:
            self.max_workers: int = cpu_count
        else:
            self.max_workers = max(1, int(max_workers))
        self.max_ram_allocation_gb = (
            max(0.5, float(max_ram_allocation_gb)) if max_ram_allocation_gb is not None else None
        )

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
            self.max_ram_allocation_gb = max(0.5, float(settings["max_ram_allocation_gb"]))
            log.info("BatchAnalysisEngine: RAM budget updated to %.2f GB.", self.max_ram_allocation_gb)

    def _effective_worker_count(self, files: List[Union[Path, "Recording"]]) -> int:
        """Return a worker count that respects the configured RAM budget."""
        if self.max_ram_allocation_gb is None or self.max_workers <= 1:
            return self.max_workers

        sizes = []
        for item in files:
            if not isinstance(item, (str, Path)):
                continue
            try:
                sizes.append(Path(item).stat().st_size)
            except OSError:
                # Unknown size is handled by the configured CPU limit rather
                # than preventing a valid batch from running.
                continue
        if not sizes:
            return self.max_workers

        estimated_per_worker = max(sizes) * self._RAM_ESTIMATE_MULTIPLIER
        budget_bytes = int(self.max_ram_allocation_gb * 1024**3)
        budget_workers = max(1, budget_bytes // max(1, estimated_per_worker))
        effective = min(self.max_workers, budget_workers)
        if effective < self.max_workers:
            log.warning(
                "BatchAnalysisEngine: reducing parallelism from %d to %d to respect the %.2f GB RAM budget.",
                self.max_workers,
                effective,
                self.max_ram_allocation_gb,
            )
        return effective

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

    # Keys whose arrays represent discrete events (spike times, PSP amplitudes,
    # etc.) and should be preserved verbatim inside ``_raw_arrays`` for downstream
    # plotting and long-format CSV export.  Full continuous trace arrays (fitting
    # curves, 10 kHz voltage traces) must NOT appear here to avoid memory spikes.
    _EVENT_ARRAY_KEYS: frozenset = frozenset(
        {
            "event_times",
            "event_amplitudes",
            "event_iei",
            "spike_times",
            "spike_amplitudes",
            "spike_counts",
            "frequencies",
            "current_steps",
            "adaptation_ratios",
            "broadening_indices",
            "isi_array",
            "event_rise_times",
            "event_decay_times",
            "event_charges",
        }
    )

    @staticmethod
    def _sanitise_result_for_export(result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Make a single result row export-friendly.

        Dual-representation architecture
        ---------------------------------
        1. Public array keys whose names appear in ``_EVENT_ARRAY_KEYS`` produce
           both a human-readable summary string (kept in the main dict so UI
           tables render correctly) *and* a copy of the raw NumPy array stored
           under ``result["_raw_arrays"][key]``.  Only discrete-event arrays
           (spike times, PSP amplitudes, …) are stored this way; continuous
           10 kHz trace buffers are excluded to avoid memory spikes.
        2. All other non-scalar values are summarised as strings and the raw
           object moved to a ``_``-prefixed key (existing behaviour).
        3. Human-readable aliases are added for cryptic algorithm names.
        4. Private ``_``-prefixed keys are left untouched.

        Returns:
            Cleaned result dict (modified in-place for efficiency).
        """
        raw_arrays: Dict[str, Any] = result.get("_raw_arrays", {})  # may already exist
        keys_to_add: Dict[str, Any] = {}

        for key, value in list(result.items()):
            if key.startswith("_"):
                continue
            new_value, stash = BatchAnalysisEngine._sanitise_value(key, value)
            result[key] = new_value

            # For discrete-event arrays: also store raw data under _raw_arrays.
            if key in BatchAnalysisEngine._EVENT_ARRAY_KEYS and isinstance(value, (np.ndarray, list)):
                arr = np.asarray(value) if isinstance(value, list) else value
                # Only store compact discrete-event arrays (<= 50 000 elements)
                # to guard against accidentally persisting continuous traces.
                if arr.ndim <= 2 and arr.size <= 50_000:
                    raw_arrays[key] = arr

            if stash is not None:
                keys_to_add[stash[0]] = stash[1]

        if raw_arrays:
            result["_raw_arrays"] = raw_arrays

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
        if getattr(recording, "imported_protocol_label", None):
            meta["imported_protocol_label"] = recording.imported_protocol_label
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
        worker_count: Optional[int] = None,
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
        pool_kwargs: Dict[str, Any] = {"max_workers": worker_count or self.max_workers}
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
        rs_tolerance: float = 0.20,
        cross_file_average: bool = False,
    ) -> pd.DataFrame:
        """
        Run analysis on a list of files/recordings using a flexible pipeline configuration.

        When :attr:`max_workers` > 1 **and** *files* contains at least two items, the
        file-level loop is distributed across worker processes via
        :class:`~concurrent.futures.ProcessPoolExecutor`.  The GUI thread is never
        blocked in either mode — callers should wrap this in a
        :class:`~synaptipy.application.gui.analysis_worker.BatchWorker` QThread.

        Args:
            files: List of file paths OR Recording objects to process.
            pipeline_config: List of task dictionaries.
            progress_callback: Optional callback (current, total, status_msg).
            channel_filter: Optional list of channel names/IDs to process.
            rs_tolerance: Maximum fractional increase in series resistance compared
                to the first valid Rs measurement before a sweep is flagged with
                ``rs_qc_warning``.  Default 0.20 (20 %).  Set to ``float('inf')``
                to disable the check.

        Returns:
            pandas DataFrame containing aggregated results with metadata.
        """
        self._cancelled = False
        total_files = len(files)

        # Validate pipeline config
        if not pipeline_config:
            log.warning("Empty pipeline_config provided. No analyses will be run.")
            return pd.DataFrame()

        # Route to cross-file average mode when requested
        if cross_file_average:
            log.info("BatchAnalysisEngine: cross-file average mode enabled (%d files).", total_files)
            return self._run_cross_file_average(files, pipeline_config, progress_callback, channel_filter)

        # Route to parallel executor when CPU and RAM limits allow it.
        effective_workers = self._effective_worker_count(files)
        if effective_workers > 1 and total_files > 1:
            log.info(
                "BatchAnalysisEngine: starting parallel batch (%d workers, %d files).", effective_workers, total_files
            )
            return self._run_batch_parallel(
                files, pipeline_config, progress_callback, channel_filter, worker_count=effective_workers
            )

        return self._run_batch_sequential(files, pipeline_config, progress_callback, channel_filter, rs_tolerance)

    def _run_cross_file_average(  # noqa: C901
        self,
        files: List[Union[Path, "Recording"]],
        pipeline_config: List[Dict[str, Any]],
        progress_callback: Optional[Callable[[int, int, str], None]],
        channel_filter: Optional[List[str]],
    ) -> pd.DataFrame:
        """Build protocol-compatible, file-balanced cross-file averages.

        It honours selected-trial scopes, keeps protocol groups separate, and first
        averages technical repeats within each file so a file with many sweeps
        does not dominate the cross-file result.
        """
        return self._run_protocol_aware_cross_file_average(files, pipeline_config, progress_callback, channel_filter)

    def _run_protocol_aware_cross_file_average(  # noqa: C901
        self,
        files: List[Union[Path, "Recording"]],
        pipeline_config: List[Dict[str, Any]],
        progress_callback: Optional[Callable[[int, int, str], None]],
        channel_filter: Optional[List[str]],
    ) -> pd.DataFrame:
        """Plan, validate, and execute one average per compatible protocol group."""
        batch_start_time = datetime.now()
        loaded: List[Tuple[str, str, str, Recording]] = []
        total_files = len(files)

        for index, item in enumerate(files):
            if self._cancelled:
                break
            try:
                if isinstance(item, (str, Path)):
                    path = Path(item)
                    if progress_callback:
                        progress_callback(index, total_files, f"Loading {path.name}...")
                    recording = self.neo_adapter.read_recording(path, channel_whitelist=channel_filter)
                    if recording is None:
                        continue
                    loaded.append((path.name, str(path), f"{path}::{index}", recording))
                else:
                    source = getattr(item, "source_file", None)
                    name = source.name if source else f"InMemory_{index}"
                    loaded.append((name, str(source or name), f"{source or name}::{index}", item))
            except Exception as exc:  # noqa: BLE001
                log.warning("Cross-file planner could not load %r: %s", item, exc)

        results: List[Dict[str, Any]] = []
        for task in pipeline_config:
            if self._cancelled:
                break
            analysis_name = task.get("analysis")
            analysis_func = AnalysisRegistry.get_function(analysis_name)
            scope = task.get("scope", "average")
            params = dict(task.get("params", {}))
            if analysis_func is None:
                results.append({"analysis": analysis_name, "scope": scope, "error": "Analysis is not registered"})
                continue

            # Key: (channel display name, canonical unit, protocol fingerprint).
            # Value: file path -> file-level technical repeats for that group.
            groups: Dict[Tuple[str, str, str], Dict[str, Dict[str, Any]]] = {}
            excluded: Dict[Tuple[str, str, str], List[str]] = {}

            for file_name, file_path, source_key, recording in loaded:
                for channel_key, channel in recording.channels.items():
                    if channel_filter and channel_key not in channel_filter and str(channel_key) not in channel_filter:
                        continue
                    channel_name = getattr(channel, "name", None) or str(channel_key)
                    units, scale = canonical_unit_and_scale(getattr(channel, "units", ""))
                    if units is None or scale is None:
                        continue
                    try:
                        if scope == "specific_trial":
                            indices = [int(params.get("trial_index", 0))]
                        elif scope in ("selected_trials", "selected_trials_average") and params.get("trial_indices"):
                            from synaptipy.shared.utils import parse_trial_selection_string

                            indices = sorted(
                                parse_trial_selection_string(params["trial_indices"], channel.num_trials, strict=True)
                            )
                        elif scope == "first_trial":
                            indices = [0]
                        else:
                            indices = list(range(channel.num_trials))
                    except ValueError as exc:
                        results.append(
                            {
                                "file_name": file_name,
                                "file_path": file_path,
                                "channel": channel_name,
                                "analysis": analysis_name,
                                "scope": scope,
                                "error": str(exc),
                            }
                        )
                        continue

                    for trial_index in indices:
                        data = channel.get_data(trial_index)
                        time = channel.get_relative_time_vector(trial_index)
                        if data is None or time is None:
                            continue
                        duration = float(time[-1]) if len(time) else None
                        for protocol in resolve_protocols(recording, trial_index, duration, analysis_name):
                            key = (channel_name, units, protocol.protocol_fingerprint)
                            if protocol.status == "incompatible":
                                excluded.setdefault(key, []).append(
                                    f"{file_name}: trial {trial_index} ({'; '.join(protocol.missing)})"
                                )
                                continue
                            segment_data, segment_time = slice_segment(data, time, protocol)
                            if len(segment_data) == 0:
                                excluded.setdefault(key, []).append(
                                    f"{file_name}: trial {trial_index} has no segment samples"
                                )
                                continue
                            bucket = groups.setdefault(key, {}).setdefault(
                                source_key,
                                {
                                    "file_name": file_name,
                                    "file_path": file_path,
                                    "traces": [],
                                    "times": [],
                                    "protocol": protocol,
                                },
                            )
                            bucket["traces"].append(np.asarray(segment_data, dtype=float) * scale)
                            bucket["times"].append(np.asarray(segment_time, dtype=float))

            for (channel_name, units, fingerprint), contributors in groups.items():
                per_file_traces: List[np.ndarray] = []
                per_file_times: List[np.ndarray] = []
                used_protocol: Optional[ResolvedProtocol] = None
                contributor_rows: List[Dict[str, Any]] = []
                for _source_key, bucket in contributors.items():
                    time, trace = average_time_aligned_trials(bucket["traces"], bucket["times"])
                    if time is None or trace is None:
                        continue
                    if per_file_times and not time_bases_compatible(per_file_times[0], time):
                        excluded.setdefault((channel_name, units, fingerprint), []).append(
                            f"{bucket['file_name']}: incompatible segment time base"
                        )
                        continue
                    per_file_times.append(time)
                    per_file_traces.append(trace)
                    used_protocol = bucket["protocol"]
                    contributor_rows.append(
                        {
                            "file_name": bucket["file_name"],
                            "file_path": bucket["file_path"],
                            "n_segments": len(bucket["traces"]),
                        }
                    )
                master_time, master_trace = average_time_aligned_trials(per_file_traces, per_file_times)
                if master_time is None or master_trace is None or used_protocol is None:
                    continue
                sampling_rate = sampling_rate_from_timebase(master_time)
                clean_params = {
                    key: value for key, value in params.items() if key not in {"trial_index", "trial_indices"}
                }
                meta = {
                    "file_name": "CROSS_FILE_MASTER_AVERAGE",
                    "file_path": f"CROSS_FILE_PROTOCOL_AVERAGE ({len(per_file_traces)} files)",
                    "channel": channel_name,
                    "channel_units": units,
                    "analysis": analysis_name,
                    "scope": scope,
                    "sampling_rate": sampling_rate,
                    "trial_count": sum(row["n_segments"] for row in contributor_rows),
                    "contributing_file_count": len(per_file_traces),
                    "cross_file_weighting": "equal file weight",
                    "cross_file_contributors": contributor_rows,
                    "cross_file_exclusions": excluded.get((channel_name, units, fingerprint), []),
                    **used_protocol.as_result_metadata(),
                }
                try:
                    analysis_result = AnalysisRegistry.execute(
                        analysis_name, master_trace, master_time, sampling_rate, **clean_params
                    )
                    result = analysis_result.export_row(**meta)
                    self._sanitise_result_for_export(result)
                    results.append(result)
                except Exception as exc:  # noqa: BLE001
                    results.append({**meta, "error": str(exc), "debug_trace": traceback.format_exc()})

        if progress_callback:
            progress_callback(total_files, total_files, "Cross-file average complete.")
        df = pd.DataFrame(results)
        if not df.empty:
            df["batch_timestamp"] = batch_start_time.isoformat()
            df = self._order_columns(df)
        return df

    def _run_batch_sequential(  # noqa: C901
        self,
        files: List[Union[Path, "Recording"]],
        pipeline_config: List[Dict[str, Any]],
        progress_callback: Optional[Callable[[int, int, str], None]],
        channel_filter: Optional[List[str]],
        rs_tolerance: float = 0.20,
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

                    import time

                    t0_io = time.perf_counter()
                    # Load recording from disk with whitelist (Memory Optimization)
                    recording = self.neo_adapter.read_recording(file_path, channel_whitelist=channel_filter)
                    file_io_time = time.perf_counter() - t0_io
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
                    file_io_time = 0.0

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

                import time

                t0_compute = time.perf_counter()

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

                    # Series-resistance stability tracker: reset for each new channel.
                    # rs_reference_mohm stores the Rs from the first valid sweep so
                    # all subsequent sweeps can be checked for drift.
                    rs_reference_mohm: Optional[float] = None

                    # Process each task in the pipeline
                    for task in pipeline_config:
                        if self._cancelled:
                            break

                        try:
                            # Pass the context to allow tasks to use/modify it
                            task_results, updated_context = self._process_task(
                                task=task,
                                recording=recording,
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

                            # --- Series-Resistance Stability QC ---
                            # Track rs_mohm across trials.  If Rs increases by more
                            # than rs_tolerance relative to Sweep 1, flag the row with
                            # a warning so analysts can exclude unstable patches.
                            for res in task_results:
                                rs_val = res.get("rs_mohm")
                                if rs_val is None:
                                    continue
                                try:
                                    rs_float = float(rs_val)
                                except (TypeError, ValueError):
                                    continue
                                if rs_float != rs_float:  # NaN guard
                                    continue
                                if rs_reference_mohm is None:
                                    rs_reference_mohm = rs_float
                                    log.debug(
                                        "Rs reference %.2f MOhm set for %s / %s.",
                                        rs_float,
                                        file_name,
                                        channel_name,
                                    )
                                elif rs_float > rs_reference_mohm * (1.0 + rs_tolerance):
                                    delta_pct = (rs_float - rs_reference_mohm) / rs_reference_mohm * 100.0
                                    log.warning(
                                        "Series resistance destabilized: Rs=%.2f MOhm "
                                        "(ref=%.2f MOhm, +%.1f%%) in %s / %s trial %s "
                                        "(tolerance=%.0f%%).",
                                        rs_float,
                                        rs_reference_mohm,
                                        delta_pct,
                                        file_name,
                                        channel_name,
                                        res.get("trial_index", "?"),
                                        rs_tolerance * 100.0,
                                    )
                                    res["rs_qc_warning"] = (
                                        f"Series resistance destabilized: "
                                        f"Rs={rs_float:.1f} MOhm (ref={rs_reference_mohm:.1f} "
                                        f"MOhm, +{delta_pct:.1f}%)"
                                    )

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

                    # Explicitly release the per-channel data buffer so NumPy arrays
                    # held in pipeline_context (which can be 10–200 MB for a long ABF)
                    # are freed before processing the next channel in this file.
                    pipeline_context = {"scope": None, "data": None, "time": None}

                file_compute_time = time.perf_counter() - t0_compute

                # Append the IO and compute times to all rows generated for this file
                for row in results_list:
                    if row.get("file_path") == file_path_str:
                        row["io_time_s"] = file_io_time
                        row["compute_time_s"] = file_compute_time

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

                # Aggressive memory management: collect garbage every 10 files and after each file
                # if the results list is large (>500 rows), to prevent OOM on 8GB systems.
                if (i + 1) % 10 == 0 or len(results_list) > 500:
                    gc.collect()
                    log.debug("gc.collect() called after processing item %d (results: %d rows).", i, len(results_list))

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
        self,
        task: Dict[str, Any],
        channel,
        channel_name: str,
        file_path: Path,
        context: Dict[str, Any],
        recording: Optional[Recording] = None,
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
        params = dict(task.get("params", {}))

        # Check metadata for type and batch-dispatch flags
        meta = AnalysisRegistry.get_metadata(analysis_name)
        is_preprocessing = meta.get("type") == "preprocessing"
        expects_list = meta.get("expects_list", False)
        supported_units = tuple(meta.get("supported_channel_units", ()))
        channel_units = str(getattr(channel, "units", ""))
        if supported_units and channel_units not in supported_units:
            return [
                {
                    "file_name": file_path.name,
                    "file_path": str(file_path),
                    "channel": channel_name,
                    "analysis": analysis_name,
                    "scope": scope,
                    "error": (
                        f"{meta.get('label', analysis_name)} requires channel units "
                        f"{', '.join(supported_units)}, not {channel_units or 'unknown units'}."
                    ),
                }
            ], None

        secondary_config = meta.get("requires_secondary_channel")
        secondary_channel = None
        secondary_param_name = ""
        if isinstance(secondary_config, dict):
            secondary_param_name = str(secondary_config.get("param_name", "secondary_data"))
            # An explicit payload remains valid for scripted pipelines and
            # backward-compatible built-ins such as ``optogenetic_sync``.
            # Otherwise resolve the declared secondary channel from the recording.
            if secondary_param_name not in params:
                secondary_selector = task.get("secondary_channel", params.pop("secondary_channel", None))
                if recording is None or not secondary_selector:
                    return [
                        {
                            "file_name": file_path.name,
                            "file_path": str(file_path),
                            "channel": channel_name,
                            "analysis": analysis_name,
                            "scope": scope,
                            "error": (
                                "This analysis requires a secondary channel. "
                                "Set secondary_channel to its ID or name."
                            ),
                        }
                    ], None
                selector = str(secondary_selector)
                secondary_channel = recording.channels.get(selector)
                if secondary_channel is None:
                    secondary_channel = next(
                        (
                            candidate
                            for channel_id, candidate in recording.channels.items()
                            if str(channel_id) == selector or str(getattr(candidate, "name", "")) == selector
                        ),
                        None,
                    )
                if secondary_channel is None:
                    return [
                        {
                            "file_name": file_path.name,
                            "file_path": str(file_path),
                            "channel": channel_name,
                            "analysis": analysis_name,
                            "scope": scope,
                            "error": f"Secondary channel '{selector}' was not found in this recording.",
                        }
                    ], None

        # Get the registered analysis function
        analysis_func = AnalysisRegistry.get_function(analysis_name)
        if analysis_func is None:
            # Provide helpful suggestions using fuzzy string matching
            available_analyses = AnalysisRegistry.list_analysis()
            error_msg = f"Analysis function '{analysis_name}' not registered"

            # Simple fuzzy matching: find analyses with similar names
            from difflib import get_close_matches

            suggestions = get_close_matches(analysis_name, available_analyses, n=3, cutoff=0.6)

            if suggestions:
                error_msg += f". Did you mean: {', '.join(suggestions)}?"
            else:
                error_msg += f". Available analyses: {', '.join(sorted(available_analyses)[:10])}"
                if len(available_analyses) > 10:
                    error_msg += f" (and {len(available_analyses) - 10} more)"

            log.error(error_msg)
            return [
                {
                    "file_name": file_path.name,
                    "file_path": str(file_path),
                    "channel": channel_name,
                    "analysis": analysis_name,
                    "scope": scope,
                    "error": error_msg,
                }
            ], None

        results = []
        sampling_rate = channel.sampling_rate
        protocol_enabled = isinstance(getattr(recording, "protocol_map", None), ProtocolMap)

        def protocols_for_trial(trial_idx: int, trial_time: Any) -> List[ResolvedProtocol]:
            """Resolve protocol context without making incomplete maps invisible."""
            if not protocol_enabled:
                return []
            try:
                duration = float(np.asarray(trial_time)[-1]) if trial_time is not None and len(trial_time) else None
                return resolve_protocols(recording, trial_idx, duration, analysis_name)
            except Exception as exc:  # noqa: BLE001 - a bad map must not crash a batch
                log.warning("Could not resolve protocol for %s trial %d: %s", file_path.name, trial_idx, exc)
                return []

        # --- Data Retrieval Strategy ---
        # 1. If context matches requested scope, use it.
        # 2. If context exists but scope differs, try to adapt (e.g. average existing trials).
        # 3. If no context, load from channel.

        data = None
        time = None
        selected_trial_indices: Optional[List[int]] = None
        average_qc_metadata: Dict[str, Any] = {}

        # Check if we can use context
        if context["data"] is not None:
            # If scope matches, use directly
            if context["scope"] == scope:
                data = context["data"]
                time = context["time"]

            # Adaptation: If we have 'all_trials' data but need 'average'
            elif context["scope"] == "all_trials" and scope == "average":
                # Compute average from cached trials.  Guard against mixed-protocol
                # files where trials can have different sample counts.
                try:
                    if len(context["data"]) > 0:
                        trial_lengths = [len(a) for a in context["data"]]
                        lengths_set = set(trial_lengths)
                        if len(lengths_set) > 1:
                            # Build detailed error message showing which trials have which lengths
                            length_counts = {}
                            for i, length in enumerate(trial_lengths):
                                if length not in length_counts:
                                    length_counts[length] = []
                                length_counts[length].append(i)

                            length_desc = ", ".join(
                                f"{length} samples (trials {','.join(map(str, trials))})"
                                for length, trials in sorted(length_counts.items())
                            )
                            raise ValueError(
                                f"Cannot average trials with mismatched lengths in "
                                f"{file_path.name}/{channel_name}: {length_desc}. "
                                "Use 'first_trial' or 'specific_trial' scope instead, or ensure "
                                "all sweeps use the same protocol duration."
                            )
                        data = np.mean(np.array(context["data"]), axis=0)
                        time = context["time"][0]
                    else:
                        log.warning("Context data empty, cannot average.")
                except ValueError as e:
                    if "Cannot average" in str(e) or "mismatched lengths" in str(e):
                        return [
                            {
                                "file_name": file_path.name,
                                "file_path": str(file_path),
                                "channel": channel_name,
                                "analysis": analysis_name,
                                "scope": scope,
                                "error": "Cannot average mixed-length trials",
                                "error_type": "TRIAL_LENGTH_MISMATCH",
                            }
                        ], None
                    log.warning(
                        "Could not average trials from context (%s/%s): %s. Reloading from source.",
                        file_path.name,
                        channel_name,
                        e,
                    )
                except Exception as e:
                    log.warning(
                        "Could not average trials from context (%s/%s): %s. Reloading from source.",
                        file_path.name,
                        channel_name,
                        e,
                    )

            # Adaptation: If we have 'all_trials' data but need 'selected_trials_average'
            elif context["scope"] == "all_trials" and scope == "selected_trials_average":
                try:
                    # Extract list of indices from task params, or default to all
                    trial_indices_str = params.get("trial_indices", "")
                    if trial_indices_str:
                        from synaptipy.shared.utils import parse_trial_selection_string

                        try:
                            parsed_indices = parse_trial_selection_string(
                                trial_indices_str, len(context["data"]), strict=True
                            )
                            selected_indices = sorted(list(parsed_indices))
                        except ValueError as e:
                            log.error(f"Invalid trial selection string in {file_path.name}/{channel_name}: {e}")
                            # Return early with error
                            return [
                                {
                                    "file_name": file_path.name,
                                    "file_path": str(file_path),
                                    "channel": channel_name,
                                    "analysis": analysis_name,
                                    "scope": scope,
                                    "error": str(e),
                                }
                            ], None
                    else:
                        selected_indices = list(range(len(context["data"])))

                    if selected_indices:
                        selected_trial_indices = selected_indices
                        selected_data = [context["data"][i] for i in selected_indices if i < len(context["data"])]
                        lengths = {len(a) for a in selected_data}
                        if len(lengths) > 1:
                            raise ValueError(
                                f"Cannot average selected trials with mismatched lengths "
                                f"{sorted(lengths)} in {file_path.name}/{channel_name}. "
                                "Ensure all selected sweeps use the same protocol duration."
                            )
                        data = np.mean(np.array(selected_data), axis=0)
                        time = context["time"][0]
                    else:
                        log.warning("No valid trials selected for averaging from context.")
                except ValueError as e:
                    if "Cannot average" in str(e) or "mismatched lengths" in str(e):
                        return [
                            {
                                "file_name": file_path.name,
                                "file_path": str(file_path),
                                "channel": channel_name,
                                "analysis": analysis_name,
                                "scope": scope,
                                "error": "Cannot average mixed-length trials",
                                "error_type": "TRIAL_LENGTH_MISMATCH",
                            }
                        ], None
                    log.warning(
                        "Could not average selected trials from context (%s/%s): %s. Reloading from source.",
                        file_path.name,
                        channel_name,
                        e,
                    )
                except (IndexError, KeyError, TypeError) as exc:
                    log.warning(
                        "Could not average selected trials from context (%s/%s): %s. Reloading from source.",
                        file_path.name,
                        channel_name,
                        exc,
                    )

            elif context["scope"] == "all_trials" and scope == "selected_trials":
                trial_indices_str = params.get("trial_indices", "")
                try:
                    if trial_indices_str:
                        from synaptipy.shared.utils import parse_trial_selection_string

                        selected_trial_indices = sorted(
                            parse_trial_selection_string(trial_indices_str, len(context["data"]), strict=True)
                        )
                    else:
                        selected_trial_indices = list(range(len(context["data"])))
                    data = [context["data"][index] for index in selected_trial_indices]
                    time = [context["time"][index] for index in selected_trial_indices]
                except ValueError as exc:
                    return [
                        {
                            "file_name": file_path.name,
                            "file_path": str(file_path),
                            "channel": channel_name,
                            "analysis": analysis_name,
                            "scope": scope,
                            "error": str(exc),
                        }
                    ], None
                except (IndexError, KeyError, TypeError) as exc:
                    log.warning(
                        "Could not select trials from context (%s/%s): %s. Reloading from source.",
                        file_path.name,
                        channel_name,
                        exc,
                    )

        # If data is still None, load from channel
        if data is None:
            # Validate scope against available data
            if scope in ("all_trials", "selected_trials", "channel_set") and channel.num_trials == 0:
                log.error(
                    f"Scope '{scope}' requires trials, but channel {channel_name} in "
                    f"{file_path.name} has no trials loaded."
                )
                return [
                    {
                        "file_name": file_path.name,
                        "file_path": str(file_path),
                        "channel": channel_name,
                        "analysis": analysis_name,
                        "scope": scope,
                        "error": f"Scope '{scope}' requires trials but channel has no trials",
                    }
                ], None

            if scope == "average":
                if isinstance(channel, Channel):
                    average = channel.get_time_aligned_average()
                    data = average.data
                    time = average.time
                    average_qc_metadata = summarise_trial_qc(average.decisions)
                    average_qc_metadata["average_alignment_method"] = average.alignment_method
                else:
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
                    from synaptipy.shared.utils import parse_trial_selection_string

                    try:
                        parsed_indices = parse_trial_selection_string(
                            trial_indices_str, channel.num_trials, strict=True
                        )
                        selected_indices = sorted(list(parsed_indices))
                    except ValueError as e:
                        log.error(f"Invalid trial selection string in {file_path.name}/{channel_name}: {e}")
                        return [
                            {
                                "file_name": file_path.name,
                                "file_path": str(file_path),
                                "channel": channel_name,
                                "analysis": analysis_name,
                                "scope": scope,
                                "error": str(e),
                            }
                        ], None
                else:
                    selected_indices = list(range(channel.num_trials))

                for i in selected_indices:
                    d = channel.get_data(i)
                    t = channel.get_relative_time_vector(i)
                    if d is not None:
                        data.append(d)
                        time.append(t)
                selected_trial_indices = selected_indices

            elif scope == "selected_trials_average":
                trial_indices_str = params.get("trial_indices", "")
                if trial_indices_str:
                    from synaptipy.shared.utils import parse_trial_selection_string

                    try:
                        parsed_indices = parse_trial_selection_string(
                            trial_indices_str, channel.num_trials, strict=True
                        )
                        selected_indices = sorted(list(parsed_indices))
                    except ValueError as e:
                        log.error(f"Invalid trial selection string in {file_path.name}/{channel_name}: {e}")
                        return [
                            {
                                "file_name": file_path.name,
                                "file_path": str(file_path),
                                "channel": channel_name,
                                "analysis": analysis_name,
                                "scope": scope,
                                "error": str(e),
                            }
                        ], None
                else:
                    selected_indices = None

                if isinstance(channel, Channel):
                    average = channel.get_time_aligned_average(selected_indices)
                    data = average.data
                    time = average.time
                    average_qc_metadata = summarise_trial_qc(average.decisions)
                    average_qc_metadata["average_alignment_method"] = average.alignment_method
                else:
                    data = channel.get_averaged_data(trial_indices=selected_indices)
                    time = channel.get_relative_averaged_time_vector(trial_indices=selected_indices)
                selected_trial_indices = (
                    selected_indices if selected_indices is not None else list(range(channel.num_trials))
                )

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

        # Averages and list-based analyses cannot be scientifically interpreted
        # when they combine explicit, incompatible protocol assignments.
        # Recordings without a protocol map remain ``needs_review``.
        if protocol_enabled and scope in ("average", "selected_trials_average", "channel_set"):
            if scope == "selected_trials_average" and params.get("trial_indices"):
                from synaptipy.shared.utils import parse_trial_selection_string

                selected_for_check = sorted(
                    parse_trial_selection_string(params["trial_indices"], channel.num_trials, strict=True)
                )
            elif scope == "channel_set":
                selected_for_check = list(range(channel.num_trials))
            else:
                selected_for_check = list(range(channel.num_trials))
            contexts = []
            for index in selected_for_check:
                trial_time = channel.get_relative_time_vector(index)
                contexts.extend(protocols_for_trial(index, trial_time))
            incompatible = [ctx for ctx in contexts if ctx.status == "incompatible"]
            fingerprints = {ctx.protocol_fingerprint for ctx in contexts if ctx.status != "incompatible"}
            if incompatible:
                return [
                    {
                        "file_name": file_path.name,
                        "file_path": str(file_path),
                        "channel": channel_name,
                        "analysis": analysis_name,
                        "scope": scope,
                        "error": "Selected data contain protocol segments incompatible with this analysis.",
                        "protocol_status": "incompatible",
                    }
                ], None
            if len(fingerprints) > 1:
                return [
                    {
                        "file_name": file_path.name,
                        "file_path": str(file_path),
                        "channel": channel_name,
                        "analysis": analysis_name,
                        "scope": scope,
                        "error": "Cannot combine explicit mixed-protocol segments; select one protocol group.",
                        "protocol_status": "mixed_protocol",
                    }
                ], None

        # --- expects_list enforcement ---
        # Controls how multi-trial data is dispatched to the analysis function
        # when scope="all_trials":
        #   expects_list=False (default): iterate - call once per trial (existing behaviour)
        #   expects_list=True: pass the complete list in a single call (like channel_set)
        # No data transformation is applied here; the flag is used by the
        # execution dispatcher below.

        # --- Execution ---

        if is_preprocessing:
            # Preprocessing: Modify data and return new context
            # Store original context to restore on failure (prevents contamination)
            original_context = context.copy() if context else None

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
                # Restore original context to prevent contamination of subsequent tasks
                error_row = {
                    "file_name": file_path.name,
                    "file_path": str(file_path),
                    "channel": channel_name,
                    "analysis": analysis_name,
                    "scope": scope,
                    "sampling_rate": sampling_rate,
                    "error": f"Preprocessing failed: {e}",
                    "debug_trace": traceback.format_exc(),
                }
                return [error_row], original_context

        else:
            # Standard Analysis
            try:
                # Helper to run analysis and format result
                total_trials = getattr(channel, "num_trials", 0)

                def secondary_trace(trial_idx: Optional[int] = None):
                    """Return the secondary trace aligned with the requested primary scope."""
                    if secondary_channel is None:
                        return None
                    if scope in ("average", "selected_trials_average"):
                        indices = selected_trial_indices if scope == "selected_trials_average" else None
                        return secondary_channel.get_time_aligned_average(indices).data
                    index = 0 if trial_idx is None else trial_idx
                    return secondary_channel.get_data(index)

                def secondary_trial_list() -> List[Any]:
                    """Return every selected secondary trial for list-based analyses."""
                    if secondary_channel is None:
                        return []
                    indices = selected_trial_indices
                    if indices is None:
                        indices = list(range(channel.num_trials))
                    traces = [secondary_channel.get_data(index) for index in indices]
                    if any(trace is None for trace in traces):
                        raise ValueError("The selected secondary channel does not contain every requested trial.")
                    return traces

                def run_single(d, t, trial_idx=None, protocol: Optional[ResolvedProtocol] = None):
                    # Remove trial_index from params if present
                    p = params.copy()
                    p.pop("trial_index", None)
                    if secondary_channel is not None:
                        trace = secondary_trace(trial_idx)
                        if trace is None:
                            raise ValueError("The selected secondary channel has no matching trial.")
                        p[secondary_param_name] = trace

                    analysis_result = AnalysisRegistry.execute(analysis_name, d, t, sampling_rate, **p)
                    res = analysis_result.export_row(
                        file_name=file_path.name,
                        file_path=str(file_path),
                        channel=channel_name,
                        analysis=analysis_name,
                        scope=scope,
                        sampling_rate=sampling_rate,
                        trial_count=(
                            len(selected_trial_indices)
                            if scope == "selected_trials_average" and selected_trial_indices is not None
                            else total_trials
                        ),
                    )
                    if selected_trial_indices is not None:
                        res["selected_trial_indices"] = ",".join(str(index) for index in selected_trial_indices)
                        res["selected_trial_count"] = len(selected_trial_indices)
                    res.update(average_qc_metadata)
                    if secondary_channel is not None:
                        res["secondary_channel"] = getattr(secondary_channel, "name", None) or secondary_param_name
                    if trial_idx is not None:
                        res["trial_index"] = trial_idx
                    if protocol is not None:
                        res.update(protocol.as_result_metadata())
                    return res

                def run_segmented(d, t, trial_idx: int) -> List[Dict[str, Any]]:
                    """Run a single-trace analysis once per compatible segment."""
                    contexts = protocols_for_trial(trial_idx, t)
                    if not contexts:
                        return [run_single(d, t, trial_idx)]
                    rows: List[Dict[str, Any]] = []
                    for protocol in contexts:
                        if protocol.status == "incompatible":
                            rows.append(
                                {
                                    "file_name": file_path.name,
                                    "file_path": str(file_path),
                                    "channel": channel_name,
                                    "analysis": analysis_name,
                                    "scope": scope,
                                    "trial_index": trial_idx,
                                    "error": "Protocol segment is incompatible with this analysis.",
                                    **protocol.as_result_metadata(),
                                }
                            )
                            continue
                        segment_data, segment_time = slice_segment(d, t, protocol)
                        if len(segment_data) == 0:
                            rows.append(
                                {
                                    "file_name": file_path.name,
                                    "file_path": str(file_path),
                                    "channel": channel_name,
                                    "analysis": analysis_name,
                                    "scope": scope,
                                    "trial_index": trial_idx,
                                    "error": "Protocol segment contains no samples.",
                                    **protocol.as_result_metadata(),
                                }
                            )
                            continue
                        rows.append(run_single(segment_data, segment_time, trial_idx, protocol))
                    return rows

                if scope in ("all_trials", "selected_trials", "channel_set"):
                    # For channel_set, some functions expect the list (e.g. F-I curve)
                    # others expect iteration.
                    # Check if function handles list?
                    # NOTE: Original code treated 'channel_set' as passing the list to func.
                    # 'all_trials' iterated.

                    if scope == "channel_set" or (scope == "all_trials" and expects_list):
                        # Pass full list (channel_set always, all_trials when expects_list=True)
                        list_params = params.copy()
                        if secondary_channel is not None:
                            list_params[secondary_param_name] = secondary_trial_list()
                        analysis_result = AnalysisRegistry.execute(
                            analysis_name, data, time, sampling_rate, **list_params
                        )
                        res = analysis_result.export_row(
                            file_name=file_path.name,
                            file_path=str(file_path),
                            channel=channel_name,
                            analysis=analysis_name,
                            scope=scope,
                            sampling_rate=sampling_rate,
                            trial_count=len(data) if isinstance(data, list) else 1,
                        )
                        if secondary_channel is not None:
                            res["secondary_channel"] = getattr(secondary_channel, "name", None) or secondary_param_name
                        results.append(res)
                    else:
                        # Iterate 'all_trials' or 'selected_trials'
                        # For 'selected_trials', extract the specific indices used
                        if scope == "selected_trials":
                            trial_indices_str = task.get("params", {}).get("trial_indices", "")
                            if trial_indices_str:
                                from synaptipy.shared.utils import parse_trial_selection_string

                                try:
                                    parsed_indices = parse_trial_selection_string(
                                        trial_indices_str, total_trials, strict=True
                                    )
                                    indices_list = sorted(list(parsed_indices))
                                except ValueError as e:
                                    log.error(f"Invalid trial selection string in {file_path.name}/{channel_name}: {e}")
                                    return [
                                        {
                                            "file_name": file_path.name,
                                            "file_path": str(file_path),
                                            "channel": channel_name,
                                            "analysis": analysis_name,
                                            "scope": scope,
                                            "error": str(e),
                                        }
                                    ], None
                            else:
                                indices_list = list(range(total_trials))
                        else:
                            indices_list = list(range(total_trials))

                        for i, (d, t) in enumerate(zip(data, time)):
                            # Ensure we output correct trial index
                            real_idx = indices_list[i] if i < len(indices_list) else i
                            results.extend(run_segmented(d, t, real_idx))

                elif scope == "specific_trial":
                    idx = int(params.get("trial_index", 0))
                    results.extend(run_segmented(data, time, idx))
                elif scope == "first_trial":
                    results.extend(run_segmented(data, time, 0))
                else:
                    # Single trace (average, first_trial)
                    protocol = None
                    if protocol_enabled:
                        contexts = protocols_for_trial(0, time)
                        protocol = contexts[0] if len(contexts) == 1 else None
                    results.append(run_single(data, time, protocol=protocol))

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
    import synaptipy.core.analysis  # noqa: F401,F811
    from synaptipy.application.plugin_manager import PluginManager

    # Spawned workers start with a fresh interpreter.  Load optional plugins
    # here as well so a pipeline behaves identically with one or many workers.
    for failure in PluginManager.load_plugins():
        log.warning("Worker did not load plugin %s: %s", failure.path.name, failure.reason)

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
