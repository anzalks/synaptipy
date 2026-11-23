# src/synaptipy/infrastructure/exporters/csv_exporter.py
# -*- coding: utf-8 -*-
"""
CSV Exporter for synaptipy.
Handles exporting recording data and analysis results to CSV format.
Automatically writes a companion provenance JSON alongside every results CSV.
"""

import importlib.metadata
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

try:
    import synaptipy

    _SYNAPTIPY_VERSION = getattr(synaptipy, "__version__", "unknown")
except Exception:
    _SYNAPTIPY_VERSION = "unknown"

from synaptipy.core.data_model import Recording

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# CSV value sanitisation
# ---------------------------------------------------------------------------

_SIG_FIGS = 6
_TIME_SIG_FIGS = 10
_MAX_ARRAY_PREVIEW = 10
_HIGH_PRECISION_TIME_SUFFIXES = (
    "_time",
    "_time_s",
    "_times",
    "_times_s",
    "_onset",
    "_onset_s",
    "_onsets",
    "_latency_s",
    "_latency_ms",
    "_delay",
    "_delay_s",
    "_delay_ms",
    "isi_s",
    "isi_ms",
)


def _round_sig(x: float, sig: int = _SIG_FIGS) -> float:
    """Round *x* to *sig* significant figures. Returns *x* unchanged if not finite."""
    import math

    try:
        val = float(x)
    except (TypeError, ValueError):
        return x
    if not math.isfinite(val):
        return val
    if val == 0.0:
        return 0.0
    sig_clamped = max(1, int(sig))
    return float(f"{val:.{sig_clamped}g}")


def _sanitize_elem(val: Any, sig: int = _SIG_FIGS) -> Any:
    """Convert a single scalar *val* to a CSV-safe Python native type."""
    if isinstance(val, (np.bool_,)):
        return bool(val)
    if isinstance(val, (np.floating,)):
        f = float(val)
        return _round_sig(f, sig=sig) if np.isfinite(f) else f
    if isinstance(val, (np.integer,)):
        return int(val)
    if isinstance(val, float):
        return _round_sig(val, sig=sig) if np.isfinite(val) else val
    return val


def _is_high_precision_time_key(key: Optional[str]) -> bool:
    """Return True if *key* represents a timestamp or latency requiring >=10 sig figs."""
    if not key:
        return False
    k_low = key.lower()
    if k_low in ("time", "time_s", "spike_times", "event_times", "peak_times", "ap_delay"):
        return True
    return k_low.endswith(_HIGH_PRECISION_TIME_SUFFIXES)


def _sanitize_csv_value(val: Any, key: Optional[str] = None) -> Any:
    """Convert *val* to a CSV-safe Python scalar or compact string."""
    if val is None:
        return np.nan

    sig = _TIME_SIG_FIGS if _is_high_precision_time_key(key) else _SIG_FIGS

    # numpy scalar
    if isinstance(val, (np.floating, np.integer, np.bool_)):
        return _sanitize_elem(val, sig=sig)

    # plain Python float
    if isinstance(val, float):
        return _sanitize_elem(val, sig=sig)

    # numpy array -> convert to list then fall through
    if isinstance(val, np.ndarray):
        val = val.tolist()

    # list / tuple
    if isinstance(val, (list, tuple)):
        if len(val) == 0:
            return np.nan
        clean = [_sanitize_elem(v, sig=sig) for v in val]
        if len(clean) > _MAX_ARRAY_PREVIEW:
            preview = clean[:_MAX_ARRAY_PREVIEW]
            return f"{preview} ... ({len(clean)} total)"
        return str(clean)

    return val


# ---------------------------------------------------------------------------
# Dependency version helpers
# ---------------------------------------------------------------------------

_DEP_PACKAGES = ("numpy", "scipy", "neo", "pyqtgraph")


def _get_dependency_versions() -> Dict[str, str]:
    """Return installed versions of key scientific dependencies.

    Uses :mod:`importlib.metadata` so the result always reflects the
    *currently running* environment rather than any cached build artefact.
    Unknown packages are reported as ``"unknown"`` rather than raising.

    Returns:
        Mapping of package name to version string.
    """
    versions: Dict[str, str] = {}
    for pkg in _DEP_PACKAGES:
        try:
            versions[pkg] = importlib.metadata.version(pkg)
        except importlib.metadata.PackageNotFoundError:
            versions[pkg] = "unknown"
    return versions


# ---------------------------------------------------------------------------
# Module-level constants for tidy long-format export
# ---------------------------------------------------------------------------

_TIDY_METADATA_KEYS = frozenset(
    {
        "file",
        "file_name",
        "source_file_name",
        "source_file_path",
        "file_path",
        "group",
        "channel",
        "channel_id",
        "channel_name",
        "trial_index",
        "trial_index_used",
        "sweep",
        "analysis_type",
        "analysis",
        "analysis_name",
        "scope",
        "sampling_rate",
        "channel_units",
        "trial_count",
        "protocol",
        "recording_duration_s",
        "batch_timestamp",
        "timestamp_saved",
        "data_source_used",
        "subject_id",
        "cell_id",
        "protocol_family",
        "protocol_fingerprint",
        "protocol_source",
        "protocol_status",
        "protocol_assignment_id",
        "segment_start_s",
        "segment_end_s",
        "analysis_result_schema_version",
        "analysis_result_warnings",
        "io_time_s",
        "compute_time_s",
        "module_used",
        "schema_version",
        "selected_trial_indices",
        "selected_trial_count",
        "secondary_channel",
        "plot_payload",
        "parameters",
        "metrics",
    }
)

_TIDY_UNIT_MAP: Dict[str, str] = {
    "rmp_mv": "mV",
    "tau_ms": "ms",
    "tau_fast_ms": "ms",
    "tau_slow_ms": "ms",
    "rin_mohm": "MOhm",
    "rin_peak_mohm": "MOhm",
    "rin_steady_state_mohm": "MOhm",
    "rin_aggregate_mohm": "MOhm",
    "rs_mohm": "MOhm",
    "rs_cc_mohm": "MOhm",
    "series_resistance_mohm": "MOhm",
    "conductance_us": "uS",
    "cm_pf": "pF",
    "capacitance_pf": "pF",
    "capacitance_charge_pf": "pF",
    "cm_fit_pf": "pF",
    "cm_derived_pf": "pF",
    "sag_ratio": "ratio",
    "sag_percentage": "%",
    "rheobase_pa": "pA",
    "fi_slope": "Hz/pA",
    "amplitude": "mV",
    "half_width": "ms",
    "rise_time_10_90": "ms",
    "decay_time_90_10": "ms",
    "fahp_depth": "mV",
    "mahp_depth": "mV",
    "adp_amplitude": "mV",
    "max_dvdt": "V/s",
    "min_dvdt": "V/s",
    "absolute_peak_mv": "mV",
    "overshoot_mv": "mV",
    "ppr": "ratio",
    "paired_pulse_ratio": "ratio",
    "ppr_naive": "ratio",
    "rectification_index": "ratio",
    "response_probability": "ratio",
    "response_probability_pct": "%",
    "tau_p1_ms": "ms",
    "interpulse_interval_ms": "ms",
    "event_amplitude": "pA",
    "event_frequency_hz": "Hz",
    "frequency_hz": "Hz",
    "mean_frequency": "Hz",
    "window_frequency_hz": "Hz",
    "tau_mono_ms": "ms",
    "adaptation_index": "ratio",
    "spike_count": "",
    "burst_count": "",
    "event_count": "",
    "pulse_count": "",
    "cv": "",
    "cv2": "",
    "lv": "",
    "r_squared": "",
    "iv_r_squared": "",
    "tau_r_squared": "",
}


def _prism_get_group(row: Dict[str, Any], fallbacks: List[str]) -> str:
    """Return the first non-None group label found in *row* using *fallbacks*."""
    for k in fallbacks:
        v = row.get(k)
        if v is not None:
            return str(v)
    return "Unknown"


def _prism_get_value(row: Dict[str, Any], metric: str) -> Optional[float]:
    """Extract a finite scalar *metric* value from *row*, flattening nested 'metrics' dicts."""
    import math

    flat: Dict[str, Any] = dict(row)
    if isinstance(flat.get("metrics"), dict):
        for k, v in flat.pop("metrics").items():
            flat.setdefault(k, v)
    raw = flat.get(metric)
    if raw is None or isinstance(raw, bool):
        return None
    try:
        val = float(raw)
    except (TypeError, ValueError):
        return None
    return val if math.isfinite(val) else None


def _resolve_tidy_unit(metric: str, units_chan: str) -> str:
    """Resolve physical unit for *metric*, respecting channel clamp units on generic amplitude keys."""
    if metric in ("event_amplitude", "mean_amplitude", "mean_local_amplitude", "amplitude"):
        if units_chan:
            return units_chan
    if metric in _TIDY_UNIT_MAP:
        return _TIDY_UNIT_MAP[metric]
    m_low = metric.lower()
    if m_low.endswith(("_count", "_index", "_ratio", "r_squared")):
        return ""
    if m_low.endswith("_hz"):
        return "Hz"
    if m_low.endswith("_ms"):
        return "ms"
    if m_low.endswith("_s"):
        return "s"
    if m_low.endswith("_mv"):
        return "mV"
    if m_low.endswith("_pa"):
        return "pA"
    return units_chan


def _build_tidy_row(
    flat: Dict[str, Any],
    file_val: str,
    group_val: str,
    sweep_val: Any,
    channel_val: str,
    analysis_val: str,
    units_chan: str,
) -> List[Dict[str, Any]]:
    """Convert one flat wide-format dict into a list of tidy long-format dicts."""
    rows: List[Dict[str, Any]] = []
    for metric, value in flat.items():
        if metric in _TIDY_METADATA_KEYS or metric.startswith("_"):
            continue
        if isinstance(value, (list, np.ndarray, dict)):
            continue
        if not isinstance(value, (int, float, bool, str, type(None), np.integer, np.floating, np.bool_)):
            continue
        if metric in ("error", "debug_trace"):
            continue
        if isinstance(value, (np.integer, np.floating, np.bool_)):
            sig = _TIME_SIG_FIGS if _is_high_precision_time_key(metric) else _SIG_FIGS
            value = _sanitize_elem(value, sig=sig)
        unit = _resolve_tidy_unit(metric, units_chan)
        rows.append(
            {
                "File": file_val,
                "Group": group_val,
                "Channel": channel_val,
                "Sweep": sweep_val,
                "Analysis": analysis_val,
                "Metric": metric,
                "Value": value,
                "Unit": unit,
            }
        )
    return rows


def _tidy_get_meta(row: Dict[str, Any], keys: List[str]) -> str:
    """Return the first non-None string value for any of the given keys."""
    for k in keys:
        v = row.get(k)
        if v is not None:
            return str(v)
    return ""


def _tidy_row_to_long(
    row: Dict[str, Any],
    file_keys: List[str],
    group_keys: List[str],
) -> List[Dict[str, Any]]:
    """Convert one wide-format result dict into a list of tidy long-format dicts."""
    flat: Dict[str, Any] = dict(row)
    flat.pop("plot_payload", None)
    if isinstance(flat.get("metrics"), dict):
        for k, v in flat.pop("metrics").items():
            if not str(k).startswith("_"):
                flat.setdefault(k, v)
    file_val = _tidy_get_meta(flat, file_keys)
    group_val = _tidy_get_meta(flat, group_keys)
    sweep_val = flat.get("trial_index", flat.get("trial_index_used", ""))
    channel_val = _tidy_get_meta(flat, ["channel_name", "channel", "channel_id"])
    analysis_val = _tidy_get_meta(flat, ["analysis_type", "analysis", "analysis_name"])
    units_chan = flat.get("channel_units", "")
    return _build_tidy_row(flat, file_val, group_val, sweep_val, channel_val, analysis_val, units_chan)


class CSVExporter:
    """
    Handles export of data to CSV files.
    """

    def export_recording(self, recording: Recording, output_dir: Path) -> Tuple[int, int]:
        """
        Export all channels in a recording to individual CSV files.

        Args:
            recording: The Recording object to export.
            output_dir: Directory to save CSV files.

        Returns:
            Tuple of (success_count, error_count)
        """
        if not output_dir.exists():
            output_dir.mkdir(parents=True, exist_ok=True)

        success_count = 0
        error_count = 0
        source_stem = recording.source_file.stem.replace("::", "_")

        for chan_id, channel in recording.channels.items():
            n_trials = getattr(channel, "num_trials", len(channel.data_trials or []))
            if n_trials <= 0:
                continue

            chan_name_safe = str(chan_id).replace(" ", "_").replace("/", "-")

            for trial_idx in range(n_trials):
                try:
                    trial_data = channel.get_data(trial_idx)
                    time_vec = channel.get_relative_time_vector(trial_idx)
                    if trial_data is None or time_vec is None or time_vec.shape != trial_data.shape:
                        log.error(f"Time/Data mismatch for {chan_id} trial {trial_idx}")
                        error_count += 1
                        continue

                    data_to_save = np.column_stack((time_vec, trial_data))

                    filename = f"{source_stem}_chan_{chan_name_safe}_trial_{trial_idx:03d}.csv"
                    filepath = output_dir / filename

                    header = f"Time (s),Data ({channel.units or 'unknown'})"
                    np.savetxt(filepath, data_to_save, delimiter=",", header=header, comments="", fmt="%.10g")

                    success_count += 1

                except Exception as e:
                    log.error(f"Failed to export CSV for {chan_id} trial {trial_idx}: {e}")
                    error_count += 1

        return success_count, error_count

    def export_analysis_results(  # noqa: C901
        self,
        results: List[Dict[str, Any]],
        output_path: Path,
        analysis_config: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Export a list of analysis result dictionaries to a single CSV file.
        Handles nested dictionaries (e.g., 'summary_stats', 'parameters') by flattening them.

        A companion ``<stem>_provenance.json`` file is automatically written
        next to the CSV.  It records the Synaptipy version, timestamp, analysis
        parameters, and source file names so that results are fully reproducible.

        Args:
            results: List of result dictionaries.
            output_path: Path to save the CSV file.
            analysis_config: Optional dict of analysis configuration parameters
                to embed in the provenance record.

        Returns:
            True if successful, False otherwise.
        """
        if not results:
            log.warning("No results to export.")
            return False

        try:
            output_path = Path(output_path)
            log.debug(f"Writing {len(results)} analysis results to CSV: {output_path}")

            # Pre-flatten consolidated-module schema: {"module_used": ..., "metrics": {...}}
            # so that metric keys appear as top-level columns rather than a single "metrics" column.
            def _pre_flatten(r: dict) -> dict:
                out = dict(r)
                out.pop("plot_payload", None)
                if isinstance(out.get("metrics"), dict):
                    for k, v in out.pop("metrics").items():
                        if not str(k).startswith("_") and k != "plot_payload":
                            out.setdefault(k, v)
                return out

            results = [_pre_flatten(r) for r in results]

            # Determine all possible fields across all results
            all_fields = set()

            # First pass to identify all fields, including nested ones
            for result in results:
                for key, value in result.items():
                    if str(key).startswith("_") or key == "plot_payload":
                        continue
                    if isinstance(value, dict):
                        # For nested dictionaries, add flattened keys (skipping private _* keys)
                        for nested_key in value.keys():
                            if str(nested_key).startswith("_"):
                                continue
                            flat_key = f"{key}.{nested_key}"
                            all_fields.add(flat_key)
                    else:
                        all_fields.add(key)

            # Sort fields in a logical order
            # First, specify key fields that should appear first
            priority_fields = [
                "analysis_type",
                "source_file_name",
                "source_file_path",
                "data_source_used",
                "trial_index_used",
                "channel_id",
                "channel_name",
                "timestamp_saved",
            ]

            # Then add analysis-specific fields by type (common ones)
            rin_fields = [
                "Input Resistance (kOhm)",
                "Rin (MΩ)",
                "Input Conductance (nS)",
                "delta_mV",
                "ΔV (mV)",
                "delta_pA",
                "ΔI (pA)",
                "baseline_mean",
                "response_mean",
                "mode",
            ]

            baseline_fields = ["baseline_mean", "baseline_sd", "baseline_units", "calculation_method"]

            spike_fields = [
                "spike_count",
                "average_firing_rate_hz",
                "threshold",
                "threshold_units",
                "refractory_period_ms",
                "spike_times",
                "spike_amplitudes",
            ]

            event_fields = [
                "method",
                "parameters.direction",
                "parameters.filter",
                "parameters.prominence",
                "parameters.sampling_rate_hz",
                "summary_stats.count",
                "summary_stats.frequency_hz",
                "summary_stats.baseline_mean",
                "summary_stats.baseline_sd",
                "summary_stats.threshold",
                "summary_stats.mean_amplitude",
                "summary_stats.amplitude_sd",
                "summary_stats.mean_rise_time_ms",
                "summary_stats.rise_time_sd_ms",
                "summary_stats.mean_decay_half_time_ms",
                "summary_stats.decay_half_time_sd_ms",
            ]

            # Create ordered list of fields
            ordered_fields = priority_fields.copy()

            # Add analysis-specific fields from each type
            for field_list in [rin_fields, baseline_fields, spike_fields, event_fields]:
                for field in field_list:
                    if field in all_fields and field not in ordered_fields:
                        ordered_fields.append(field)

            # Add any remaining fields not already included
            for field in sorted(all_fields):
                if field not in ordered_fields:
                    ordered_fields.append(field)

            import pandas as pd

            # Process each result to handle nested dictionaries
            flat_results = []
            for result in results:
                # Create a flattened copy of the result
                flat_result = {}

                # Process each key-value pair in the result dictionary
                for key, value in result.items():
                    # Skip private/internal keys (used by GUI but not useful in CSV)
                    if str(key).startswith("_") or key == "plot_payload":
                        continue
                    if isinstance(value, dict):
                        # For nested dictionaries (like summary_stats or parameters)
                        for nested_key, nested_value in value.items():
                            if str(nested_key).startswith("_"):
                                continue
                            flat_key = f"{key}.{nested_key}"
                            if flat_key in ordered_fields:
                                flat_result[flat_key] = _sanitize_csv_value(nested_value, key=nested_key)
                    else:
                        if key in ordered_fields:
                            flat_result[key] = _sanitize_csv_value(value, key=key)

                flat_results.append(flat_result)

            # Convert to DataFrame
            df = pd.DataFrame(flat_results, columns=ordered_fields)

            # Replace empty strings with NaN for proper dropna
            df.replace("", pd.NA, inplace=True)

            # Key fix: Drop columns that are completely NA across all rows
            df.dropna(axis=1, how="all", inplace=True)

            # Ensure parent directory exists and create the CSV file
            output_path.parent.mkdir(parents=True, exist_ok=True)
            df.to_csv(output_path, index=False, encoding="utf-8", na_rep="")

            log.info(f"Successfully exported {len(results)} analysis results to {output_path}")

            # --- Write provenance JSON ---
            self._write_provenance(
                csv_path=output_path,
                results=results,
                analysis_config=analysis_config,
            )

            return True

        except Exception as e:
            log.error(f"Failed to export analysis results: {e}", exc_info=True)
            return False

    # ------------------------------------------------------------------
    def _write_provenance(
        self,
        csv_path: Path,
        results: List[Dict[str, Any]],
        analysis_config: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Write a companion ``<stem>_provenance.json`` next to *csv_path*.

        The file is intentionally human-readable (indent=2) and contains:

        - ``synaptipy_version`` – package version string
        - ``timestamp_utc``     – ISO-8601 export timestamp (UTC)
        - ``csv_file``          – basename of the exported CSV
        - ``source_files``      – list of unique source file names extracted
          from the result rows (``source_file_name`` key)
        - ``analysis_config``   – the caller-supplied config dict (or ``{}``
          when not provided)
        - ``analysis_types``    – list of unique ``analysis_type`` values found
          in the result rows
        """
        provenance_path = csv_path.with_name(csv_path.stem + "_provenance.json")

        # Collect unique source file names and analysis types across GUI and Batch schemas
        source_files = sorted(
            {
                str(r.get("source_file_name") or r.get("file_name") or r.get("file") or "")
                for r in results
                if isinstance(r, dict) and (r.get("source_file_name") or r.get("file_name") or r.get("file"))
            }
        )
        analysis_types = sorted(
            {
                str(r.get("analysis_type") or r.get("analysis") or r.get("analysis_name") or "")
                for r in results
                if isinstance(r, dict) and (r.get("analysis_type") or r.get("analysis") or r.get("analysis_name"))
            }
        )

        provenance: Dict[str, Any] = {
            "synaptipy_version": _SYNAPTIPY_VERSION,
            "timestamp_utc": datetime.now(tz=timezone.utc).isoformat(),
            "csv_file": csv_path.name,
            "source_files": source_files,
            "analysis_types": analysis_types,
            "analysis_config": analysis_config or {},
            "dependencies": _get_dependency_versions(),
        }

        try:
            with open(provenance_path, "w", encoding="utf-8") as fh:
                json.dump(provenance, fh, indent=2, default=str)
            log.info("Provenance wrote to %s", provenance_path)
        except Exception as exc:
            log.warning("Could not write provenance JSON: %s", exc)

    def export_tidy(
        self,
        results: List[Dict[str, Any]],
        output_path: Path,
        analysis_config: Optional[Dict[str, Any]] = None,
        file_col: str = "file",
        group_col: str = "group",
    ) -> bool:
        """Export analysis results in tidy (long-format) CSV.

        Each row represents one ``(File, Group, Sweep, Metric, Value, Unit)``
        observation.  This layout is directly compatible with R ``tidyverse``,
        Python ``seaborn``/``pandas``, MATLAB, and Origin for statistical
        analysis and plotting.

        Scalar result values are pivoted from the wide-format rows produced
        by ``export_analysis_results``.  Private keys (starting with ``_``)
        and non-scalar values (lists, arrays) are skipped.

        A companion ``<stem>_provenance.json`` is written alongside the CSV.

        Parameters
        ----------
        results : list of dict
            Wide-format result rows, as produced by
            ``BatchAnalysisEngine.run_batch``.
        output_path : Path
            Destination CSV path.
        analysis_config : dict, optional
            Analysis configuration embedded in the provenance record.
        file_col : str
            Key in each result dict that carries the source file name
            (default ``"file"``; also tries ``"file_name"`` and
            ``"source_file_name"`` as fallbacks).
        group_col : str
            Key in each result dict that carries the experimental group label
            (default ``"group"``; falls back to empty string when absent).

        Returns
        -------
        bool
            ``True`` on success, ``False`` on failure.
        """
        if not results:
            log.warning("export_tidy: no results to export.")
            return False

        try:
            import csv as _csv

            _file_keys = [file_col, "file_name", "source_file_name", "file"]
            _group_keys = [group_col, "group"]

            tidy_rows: List[Dict[str, Any]] = []
            for row in results:
                tidy_rows.extend(_tidy_row_to_long(row, _file_keys, _group_keys))

            if not tidy_rows:
                log.warning("export_tidy: no scalar metrics found; writing empty file.")

            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w", newline="", encoding="utf-8") as fh:
                writer = _csv.DictWriter(
                    fh,
                    fieldnames=["File", "Group", "Channel", "Sweep", "Analysis", "Metric", "Value", "Unit"],
                )
                writer.writeheader()
                writer.writerows(tidy_rows)

            log.info("export_tidy: wrote %d rows to %s", len(tidy_rows), output_path)

            self._write_provenance(
                csv_path=output_path,
                results=results,
                analysis_config=analysis_config,
            )
            return True

        except Exception as exc:
            log.error("export_tidy failed: %s", exc, exc_info=True)
            return False

    def export_events(
        self,
        results: List[Dict[str, Any]],
        output_path: Path,
    ) -> bool:
        """Write a relational long-format events CSV from ``_raw_arrays``.

        The wide-format summary CSV cannot represent discrete event arrays
        (spike times, PSP amplitudes, …) on a per-event basis.  When a result
        row contains ``result["_raw_arrays"]["_event_times"]`` *and*
        ``result["_raw_arrays"]["_event_amplitudes"]``, this method generates a
        second file ``<stem>_events.csv`` with one row per event:

        ``File, Channel, Trial, Event_Index, Time_s, Amplitude``

        The file name is derived from *output_path* by inserting ``_events``
        before the ``.csv`` suffix.

        Parameters
        ----------
        results : list of dict
            Result rows as returned by ``BatchAnalysisEngine.run_batch``.
        output_path : Path
            The *summary* CSV path; the events file is placed next to it.

        Returns
        -------
        bool
            ``True`` if at least one event row was written, ``False`` otherwise.
        """
        import csv as _csv

        events_path = output_path.with_name(output_path.stem + "_events.csv")
        fieldnames = ["File", "Channel", "Trial", "Event_Index", "Time_s", "Amplitude"]

        event_rows: List[Dict[str, Any]] = []
        for row in results:
            raw = row.get("_raw_arrays")
            if not isinstance(raw, dict):
                continue

            times_arr = raw.get("event_times")
            amps_arr = raw.get("event_amplitudes")
            if times_arr is None and amps_arr is None:
                continue

            file_val = row.get("file_name") or row.get("source_file_name") or row.get("file") or ""
            chan_val = row.get("channel_name") or row.get("channel") or row.get("channel_id") or ""
            trial_val = row.get("trial_index", row.get("trial_index_used", ""))

            times_arr = np.asarray(times_arr) if times_arr is not None else np.array([])
            amps_arr = np.asarray(amps_arr) if amps_arr is not None else np.full(len(times_arr), np.nan)

            n_events = max(len(times_arr), len(amps_arr))
            for evt_idx in range(n_events):
                t_val = float(times_arr[evt_idx]) if evt_idx < len(times_arr) else float("nan")
                a_val = float(amps_arr[evt_idx]) if evt_idx < len(amps_arr) else float("nan")
                event_rows.append(
                    {
                        "File": file_val,
                        "Channel": chan_val,
                        "Trial": trial_val,
                        "Event_Index": evt_idx,
                        "Time_s": t_val,
                        "Amplitude": a_val,
                    }
                )

        if not event_rows:
            log.info("export_events: no event arrays found in results; events file not written.")
            return False

        try:
            events_path.parent.mkdir(parents=True, exist_ok=True)
            with open(events_path, "w", newline="", encoding="utf-8") as fh:
                writer = _csv.DictWriter(fh, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(event_rows)
            log.info("export_events: wrote %d event rows to %s", len(event_rows), events_path)
            return True
        except Exception as exc:
            log.error("export_events failed: %s", exc, exc_info=True)
            return False

    @staticmethod
    def _collect_prism_groups(
        results: List[Dict[str, Any]],
        metric: str,
        fallbacks: List[str],
        aggregate_by_file: bool,
    ) -> Tuple[List[str], Dict[str, List[float]]]:
        """Collect finite metric values grouped by condition (optionally averaged per file)."""
        from collections import defaultdict

        groups: Dict[str, List[float]] = defaultdict(list)
        file_buckets: Dict[str, Dict[str, List[float]]] = defaultdict(lambda: defaultdict(list))
        group_order: List[str] = []
        for idx, row in enumerate(results):
            grp = _prism_get_group(row, fallbacks)
            val = _prism_get_value(row, metric)
            if val is None:
                continue
            if grp not in group_order:
                group_order.append(grp)
            if aggregate_by_file:
                f_id = str(row.get("source_file_name") or row.get("file_name") or row.get("file") or f"row_{idx}")
                file_buckets[grp][f_id].append(val)
            else:
                groups[grp].append(val)
        if aggregate_by_file:
            for grp in group_order:
                groups[grp] = [float(np.mean(vals)) for vals in file_buckets[grp].values() if vals]
        return group_order, groups

    def export_to_prism_format(
        self,
        results: List[Dict[str, Any]],
        output_path: Path,
        metric: str,
        group_by_key: str = "Condition",
        aggregate_by_file: bool = False,
    ) -> bool:
        """Export one scalar metric in GraphPad Prism grouped-column format.

        When *aggregate_by_file* is True, sweeps belonging to the same source
        recording within each group are averaged into a single biological-replicate
        mean prior to export to avoid sweep-level pseudoreplication.
        """
        if not results:
            log.warning("export_to_prism_format: no results provided.")
            return False

        import csv as _csv

        _group_fallbacks = [group_by_key, "group", "source_file_name", "file_name", "file"]
        group_order, groups = self._collect_prism_groups(results, metric, _group_fallbacks, aggregate_by_file)

        if not group_order:
            log.warning("export_to_prism_format: metric '%s' not found in any result row.", metric)
            return False

        max_n = max(len(groups[g]) for g in group_order)
        padded: Dict[str, List[Any]] = {}
        for g in group_order:
            vals: List[Any] = [_round_sig(v) for v in groups[g]]
            vals += [""] * (max_n - len(vals))
            padded[g] = vals

        safe_metric = metric.replace(" ", "_").replace("/", "-")
        prism_path = output_path.with_name(f"{output_path.stem}_prism_{safe_metric}.csv")

        try:
            prism_path.parent.mkdir(parents=True, exist_ok=True)
            with open(prism_path, "w", newline="", encoding="utf-8") as fh:
                writer = _csv.DictWriter(fh, fieldnames=group_order)
                writer.writeheader()
                for i in range(max_n):
                    writer.writerow({g: padded[g][i] for g in group_order})

            log.info(
                "export_to_prism_format: wrote %d groups x %d rows to %s",
                len(group_order),
                max_n,
                prism_path,
            )

            self._write_provenance(
                csv_path=prism_path,
                results=results,
                analysis_config={
                    "metric": metric,
                    "group_by_key": group_by_key,
                    "aggregate_by_file": aggregate_by_file,
                },
            )
            return True

        except Exception as exc:
            log.error("export_to_prism_format failed: %s", exc, exc_info=True)
            return False
