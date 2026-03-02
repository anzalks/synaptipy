# src/Synaptipy/infrastructure/exporters/csv_exporter.py
# -*- coding: utf-8 -*-
"""
CSV Exporter for Synaptipy.
Handles exporting recording data and analysis results to CSV format.
"""

import csv
import logging
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np

from Synaptipy.core.data_model import Recording

log = logging.getLogger(__name__)


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

    def export_analysis_results(self, results: List[Dict[str, Any]], output_path: Path) -> bool:  # noqa: C901
        """
        Export a list of analysis result dictionaries to a single CSV file.
        Handles nested dictionaries (e.g., 'summary_stats', 'parameters') by flattening them.

        Args:
            results: List of result dictionaries.
            output_path: Path to save the CSV file.

        Returns:
            True if successful, False otherwise.
        """
        if not results:
            log.warning("No results to export.")
            return False

        try:
            log.debug(f"Writing {len(results)} analysis results to CSV: {output_path}")

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

            # Helper function to convert numpy values to Python native types
            def convert_value(val):
                """Convert numpy types to Python native types for CSV compatibility."""
                if val is None:
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

            # Create the CSV file
            with open(output_path, "w", newline="", encoding="utf-8") as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=ordered_fields)
                writer.writeheader()

                # Process each result to handle nested dictionaries
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

                    # Fill in missing fields with empty strings
                    for field in ordered_fields:
                        if field not in flat_result:
                            flat_result[field] = ""

                    # Write the flattened result
                    writer.writerow(flat_result)

            log.info(f"Successfully exported {len(results)} analysis results to {output_path}")
            return True

        except Exception as e:
            log.error(f"Failed to export analysis results: {e}", exc_info=True)
            return False
