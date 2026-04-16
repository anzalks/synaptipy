# src/Synaptipy/infrastructure/exporters/csv_exporter.py
# -*- coding: utf-8 -*-
"""
CSV Exporter for Synaptipy.
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
    import Synaptipy

    _SYNAPTIPY_VERSION = getattr(Synaptipy, "__version__", "unknown")
except Exception:
    _SYNAPTIPY_VERSION = "unknown"

from Synaptipy.core.data_model import Recording

log = logging.getLogger(__name__)

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
        "scope",
        "sampling_rate",
        "channel_units",
        "trial_count",
        "protocol",
        "recording_duration_s",
        "batch_timestamp",
        "timestamp_saved",
        "data_source_used",
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
    "rs_mohm": "MOhm",
    "rs_cc_mohm": "MOhm",
    "cm_pf": "pF",
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
    "max_dvdt": "V/s",
    "min_dvdt": "V/s",
    "absolute_peak_mv": "mV",
    "overshoot_mv": "mV",
    "ppr": "ratio",
    "ppr_naive": "ratio",
    "tau_p1_ms": "ms",
    "interpulse_interval_ms": "ms",
    "event_amplitude": "pA",
    "event_frequency_hz": "Hz",
    "tau_mono_ms": "ms",
    "adaptation_index": "ratio",
}


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
        if not isinstance(value, (int, float, bool, str, type(None))):
            continue
        if metric in ("error", "debug_trace"):
            continue
        unit = _TIDY_UNIT_MAP.get(metric, units_chan)
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
    if isinstance(flat.get("metrics"), dict):
        for k, v in flat.pop("metrics").items():
            flat.setdefault(k, v)
    file_val = _tidy_get_meta(flat, file_keys)
    group_val = _tidy_get_meta(flat, group_keys)
    sweep_val = flat.get("trial_index", flat.get("trial_index_used", ""))
    channel_val = flat.get("channel_name", flat.get("channel", flat.get("channel_id", "")))
    analysis_val = flat.get("analysis_type", flat.get("analysis", ""))
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
        source_stem = recording.source_file.stem

        for chan_id, channel in recording.channels.items():
            if not channel.data_trials:
                continue

            chan_name_safe = str(chan_id).replace(" ", "_").replace("/", "-")

            for trial_idx, trial_data in enumerate(channel.data_trials):
                try:
                    time_vec = channel.get_relative_time_vector(trial_idx)
                    if time_vec is None or time_vec.shape != trial_data.shape:
                        log.error(f"Time/Data mismatch for {chan_id} trial {trial_idx}")
                        error_count += 1
                        continue

                    data_to_save = np.column_stack((time_vec, trial_data))

                    filename = f"{source_stem}_chan_{chan_name_safe}_trial_{trial_idx:03d}.csv"
                    filepath = output_dir / filename

                    header = f"Time (s),Data ({channel.units or 'unknown'})"
                    np.savetxt(filepath, data_to_save, delimiter=",", header=header, comments="")

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
            log.debug(f"Writing {len(results)} analysis results to CSV: {output_path}")

            # Pre-flatten consolidated-module schema: {"module_used": ..., "metrics": {...}}
            # so that metric keys appear as top-level columns rather than a single "metrics" column.
            def _pre_flatten(r: dict) -> dict:
                out = dict(r)
                if isinstance(out.get("metrics"), dict):
                    for k, v in out.pop("metrics").items():
                        out.setdefault(k, v)
                return out

            results = [_pre_flatten(r) for r in results]

            # Determine all possible fields across all results
            all_fields = set()

            # First pass to identify all fields, including nested ones
            for result in results:
                for key, value in result.items():
                    if isinstance(value, dict):
                        # For nested dictionaries, add flattened keys
                        for nested_key in value.keys():
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

            # Helper function to convert numpy values to Python native types
            def convert_value(val):
                """Convert numpy types to Python native types for CSV compatibility."""
                if pd.isna(val):
                    return ""

                # Convert numpy arrays to lists
                if hasattr(val, "tolist") and callable(getattr(val, "tolist")):
                    try:
                        return str(val.tolist())
                    except (ValueError, AttributeError):
                        return str(val)

                # Convert numpy scalar types to native Python types
                if hasattr(val, "item") and callable(getattr(val, "item")):
                    try:
                        return val.item()
                    except (ValueError, AttributeError):
                        return str(val)

                # Handle other types
                if isinstance(val, (list, tuple)):
                    return str(val)

                return val

            # Process each result to handle nested dictionaries
            flat_results = []
            for result in results:
                # Create a flattened copy of the result
                flat_result = {}

                # Process each key-value pair in the result dictionary
                for key, value in result.items():
                    if isinstance(value, dict):
                        # For nested dictionaries (like summary_stats or parameters)
                        for nested_key, nested_value in value.items():
                            flat_key = f"{key}.{nested_key}"
                            if flat_key in ordered_fields:
                                flat_result[flat_key] = convert_value(nested_value)
                    else:
                        if key in ordered_fields:
                            flat_result[key] = convert_value(value)

                flat_results.append(flat_result)

            # Convert to DataFrame
            df = pd.DataFrame(flat_results, columns=ordered_fields)

            # Replace empty strings with NaN for proper dropna
            df.replace("", pd.NA, inplace=True)

            # Key fix: Drop columns that are completely NA across all rows
            df.dropna(axis=1, how="all", inplace=True)

            # Replace NaN back to empty string for clean CSV
            df.fillna("", inplace=True)

            # Create the CSV file
            df.to_csv(output_path, index=False, encoding="utf-8")

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

        # Collect unique source file names and analysis types
        source_files = sorted({str(r.get("source_file_name", "")) for r in results if r.get("source_file_name")})
        analysis_types = sorted({str(r.get("analysis_type", "")) for r in results if r.get("analysis_type")})

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
