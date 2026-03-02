import logging
from typing import Any, Dict, List, Tuple, Union

from Synaptipy.core.results import AnalysisResult, RinResult, SpikeTrainResult

log = logging.getLogger(__name__)


class AnalysisResultFormatter:
    """
    Encapsulates logic for formatting analysis results into human-readable strings
    for display in the ExporterTab and other UI components.
    """

    @staticmethod
    def format_result(result: Union[Dict[str, Any], AnalysisResult]) -> Tuple[str, List[str]]:  # noqa: C901
        """
        Formats a single analysis result (dict or object).
        Returns: (value_str, details_list)
        """
        # Convert object to dict-like access or handle logic
        if isinstance(result, AnalysisResult):
            # Map object types to legacy string IDs or new logic
            if isinstance(result, SpikeTrainResult):
                analysis_type = "Spike Detection (Threshold)"
                res_dict = {
                    "spike_count": len(result.spike_times) if result.spike_times is not None else 0,
                    "average_firing_rate_hz": result.mean_frequency,
                    "threshold": result.parameters.get("threshold"),
                    "threshold_units": "mV",  # Assumed
                    "refractory_period_ms": (
                        result.parameters.get("refractory_period", 0) * 1000
                        if result.parameters.get("refractory_period")
                        else None
                    ),
                }
                return AnalysisResultFormatter._format_spike_detection(
                    res_dict
                ), AnalysisResultFormatter._details_spike_detection(res_dict)

            elif isinstance(result, RinResult):
                res_dict = {
                    "Input Resistance (kOhm)": result.value if result.unit == "kOhm" else None,
                    "Rin (MΩ)": result.value if result.unit == "MOhm" else None,
                    "delta_mV": result.voltage_deflection,
                    "delta_pA": result.current_injection,
                }
                return AnalysisResultFormatter._format_input_resistance(
                    res_dict
                ), AnalysisResultFormatter._details_input_resistance(res_dict)

            analysis_type = "Unknown object"

        else:
            # It's a dictionary. Check if it has a nested "result" object and flatten its attributes
            nested_result = result.get("result")
            if hasattr(nested_result, "__dict__"):
                # Merge the nested object's attributes into the dictionary for easier formatting
                result = {**nested_result.__dict__, **result}

            analysis_type = result.get("analysis_type", "Unknown")

        value_str = "N/A"
        details = []

        try:
            target_type = analysis_type.lower()
            if "resistance" in target_type or "rin" in target_type:
                value_str = AnalysisResultFormatter._format_input_resistance(result)
                details = AnalysisResultFormatter._details_input_resistance(result)
                if value_str == "N/A":
                    value_str, details_fallback = AnalysisResultFormatter._format_rin_fallback(result)
                    if details_fallback:
                        details.extend(details_fallback)

            elif "baseline" in target_type or "rmp" in target_type:
                value_str = AnalysisResultFormatter._format_baseline(result)
                details = AnalysisResultFormatter._details_baseline(result)
                if value_str == "N/A":
                    value_str, details_fallback = AnalysisResultFormatter._format_rmp_fallback(result)
                    if details_fallback:
                        details.extend(details_fallback)

            elif "spike" in target_type or "action potential" in target_type:
                value_str = AnalysisResultFormatter._format_spike_detection(result)
                details = AnalysisResultFormatter._details_spike_detection(result)

            elif "event" in target_type or "template" in target_type or "epsc" in target_type or "ipsc" in target_type:
                value_str = AnalysisResultFormatter._format_event_detection(result)
                details = AnalysisResultFormatter._details_event_detection(result)

            elif "phase" in target_type:
                value_str = AnalysisResultFormatter._format_phase_plane(result)
                details = AnalysisResultFormatter._details_phase_plane(result)

            elif "excitability" in target_type or "f-i" in target_type or "f/i" in target_type:
                value_str = AnalysisResultFormatter._format_excitability(result)
                details = AnalysisResultFormatter._details_excitability(result)

            elif "tau" in target_type or "time constant" in target_type:
                value_str = AnalysisResultFormatter._format_tau(result)

            else:
                # Provide a generic fallback for other analysis types
                # Just show the first few numeric values found
                numeric_vals = [
                    f"{k}: {AnalysisResultFormatter._to_float(v):.2f}"
                    for k, v in result.items()
                    if isinstance(v, (int, float)) and not isinstance(v, bool)
                ]
                if numeric_vals:
                    value_str = numeric_vals[0]
                    if len(numeric_vals) > 1:
                        details.extend(numeric_vals[1:])

        except Exception as e:
            log.warning(f"Error formatting value for {analysis_type}: {e}")
            value_str = "Error"

        return value_str, details

    @staticmethod
    def _to_float(val: Any) -> float:
        """Safe float conversion handling numpy items."""
        if isinstance(val, (int, float)):
            return float(val)
        if hasattr(val, "item"):
            return float(val.item())
        return float(val)

    # --- Input Resistance ---
    @staticmethod
    def _format_input_resistance(result: Dict[str, Any]) -> str:
        # Try different possible keys for the resistance value
        for key in ["Input Resistance (kOhm)", "Rin (MΩ)"]:
            value = result.get(key)
            if value is not None:
                try:
                    value_float = AnalysisResultFormatter._to_float(value)
                    if key == "Input Resistance (kOhm)":
                        return f"{value_float:.2f} kOhm"
                    else:
                        return f"{value_float:.2f} MΩ"
                except (ValueError, TypeError, AttributeError):
                    continue
        return "N/A"

    @staticmethod
    def _details_input_resistance(result: Dict[str, Any]) -> List[str]:
        details = []
        mode = result.get("mode", "")
        if mode:
            details.append(f"Mode: {mode}")

        delta_v = result.get("delta_mV") if "delta_mV" in result else result.get("ΔV (mV)")
        delta_i = result.get("delta_pA") if "delta_pA" in result else result.get("ΔI (pA)")

        if delta_v is not None:
            try:
                dv_float = AnalysisResultFormatter._to_float(delta_v)
                details.append(f"ΔV: {dv_float:.2f} mV")
            except (ValueError, TypeError, AttributeError):
                details.append(f"ΔV: {delta_v} mV")

        if delta_i is not None:
            try:
                di_float = AnalysisResultFormatter._to_float(delta_i)
                details.append(f"ΔI: {di_float:.2f} pA")
            except (ValueError, TypeError, AttributeError):
                details.append(f"ΔI: {delta_i} pA")

        return details

    @staticmethod
    def _format_rin_fallback(result: Dict[str, Any]) -> Tuple[str, List[str]]:
        """Fallback for Rin keys."""
        value_str = "N/A"
        details = []
        rin = result.get("rin_mohm")
        if rin is not None:
            try:
                val = AnalysisResultFormatter._to_float(rin)
                value_str = f"{val:.2f} MΩ"

                g = result.get("conductance_us")
                if g is not None:
                    g_val = AnalysisResultFormatter._to_float(g)
                    details.append(f"Cond: {g_val:.2f} uS")
            except (ValueError, TypeError, AttributeError) as e:
                log.debug(f"Skipped conductance formatting: {e}")
        return value_str, details

    @staticmethod
    def _method_display_suffix(method: str) -> str:
        """Return a short display suffix for a calculation method string."""
        if method.startswith("auto_"):
            return " (Auto)"
        if method.startswith("manual_"):
            return " (Manual)"
        if method.startswith("interactive_"):
            return " (Interactive)"
        return ""

    # --- Baseline / RMP ---
    @staticmethod
    def _format_baseline(result: Dict[str, Any]) -> str:
        mean = result.get("baseline_mean")
        sd = result.get("baseline_sd")
        units = result.get("baseline_units", "")
        method = result.get("calculation_method", "")

        # Fallback to rmp_mv if baseline_mean is not found
        if mean is None:
            mean = result.get("rmp_mv")
        if sd is None:
            sd = result.get("rmp_std")
        if not units:
            units = "mV"

        method_display = AnalysisResultFormatter._method_display_suffix(method)

        if mean is None or sd is None:
            return "N/A"
        try:
            mean_float = AnalysisResultFormatter._to_float(mean)
            sd_float = AnalysisResultFormatter._to_float(sd)
            return f"{mean_float:.3f} ± {sd_float:.3f} {units}{method_display}"
        except (ValueError, TypeError, AttributeError):
            return f"Mean: {mean}, SD: {sd} {units}{method_display}"

    @staticmethod
    def _details_baseline(result: Dict[str, Any]) -> List[str]:
        details = []
        method = result.get("calculation_method", "")
        if method:
            if method.startswith("auto_mode_tolerance="):
                try:
                    tolerance = method.split("=")[1].rstrip("mV")
                    details.append(f"Method: Auto (Mode-based, Tolerance: {tolerance} mV)")
                except (IndexError, ValueError):
                    details.append("Method: Auto (Mode-based)")
            elif method.startswith("auto_"):
                details.append("Method: Automatic")
            elif method.startswith("manual_"):
                details.append("Method: Manual Time Window")
            elif method.startswith("interactive_"):
                details.append("Method: Interactive Region")
            else:
                details.append(f"Method: {method}")

        # Also check drift
        drift = result.get("rmp_drift")
        if drift is not None:
            details.append(f"Drift: {drift} mV/s")

        return details

    @staticmethod
    def _format_rmp_fallback(result: Dict[str, Any]) -> Tuple[str, List[str]]:
        value_str = "N/A"
        details = []
        rmp = result.get("rmp_mv")
        if rmp is not None:
            try:
                val = AnalysisResultFormatter._to_float(rmp)
                value_str = f"{val:.2f} mV"

                std = result.get("rmp_std")
                if std is not None:
                    video_std = AnalysisResultFormatter._to_float(std)
                    value_str += f" ± {video_std:.2f}"

                drift = result.get("rmp_drift")
                if drift is not None:
                    details.append(f"Drift: {drift} mV/s")
            except (ValueError, TypeError, AttributeError) as e:
                log.debug(f"Skipped RMP drift formatting: {e}")
        return value_str, details

    # --- Spike Detection ---
    @staticmethod
    def _format_spike_detection(result: Dict[str, Any]) -> str:
        spike_count = result.get("spike_count")
        if spike_count is not None:
            try:
                count = int(AnalysisResultFormatter._to_float(spike_count))
                value_str = f"{count} spikes"

                rate = result.get("average_firing_rate_hz")
                if rate is not None:
                    try:
                        rate_float = AnalysisResultFormatter._to_float(rate)
                        value_str += f" ({rate_float:.2f} Hz)"
                    except (ValueError, TypeError, AttributeError) as e:
                        log.debug(f"Skipped firing rate formatting: {e}")
                return value_str
            except (ValueError, TypeError, AttributeError):
                return f"{spike_count} spikes"
        return "N/A"

    @staticmethod
    def _details_spike_detection(result: Dict[str, Any]) -> List[str]:
        details = []
        threshold = result.get("threshold")
        units = result.get("threshold_units", "")
        if threshold is not None:
            try:
                threshold_float = AnalysisResultFormatter._to_float(threshold)
                details.append(f"Threshold: {threshold_float} {units}")
            except (ValueError, TypeError, AttributeError):
                details.append(f"Threshold: {threshold} {units}")

        refractory = result.get("refractory_period_ms")
        if refractory is not None:
            try:
                refractory_float = AnalysisResultFormatter._to_float(refractory)
                details.append(f"Refractory: {refractory_float} ms")
            except (ValueError, TypeError, AttributeError):
                details.append(f"Refractory: {refractory} ms")
        return details

    # --- Event Detection ---
    @staticmethod
    def _format_event_detection(result: Dict[str, Any]) -> str:
        event_count = result.get("event_count")

        # Fallback to older nested stat structure
        if event_count is None:
            summary_stats = result.get("summary_stats", {})
            if isinstance(summary_stats, dict):
                event_count = summary_stats.get("count")

        if event_count is not None:
            try:
                count = int(AnalysisResultFormatter._to_float(event_count))
                value_str = f"{count} events"

                freq = result.get("frequency_hz")
                if freq is None and "summary_stats" in result and isinstance(result["summary_stats"], dict):
                    freq = result["summary_stats"].get("frequency_hz")

                if freq is not None:
                    try:
                        freq_float = AnalysisResultFormatter._to_float(freq)
                        value_str += f" ({freq_float:.2f} Hz)"
                    except (ValueError, TypeError, AttributeError) as e:
                        log.debug(f"Skipped event frequency formatting: {e}")
                return value_str
            except (ValueError, TypeError, AttributeError):
                return f"{event_count} events"
        return "N/A"

    @staticmethod
    def _details_event_detection(result: Dict[str, Any]) -> List[str]:  # noqa: C901
        details = []
        method = result.get("method", result.get("detection_method", ""))
        if method:
            details.append(f"Method: {method}")

        direction = result.get("direction")
        if direction:
            details.append(f"Direction: {direction}")

        params = result.get("parameters", {})
        if isinstance(params, dict):
            filter_val = params.get("filter")
            if filter_val is not None:
                try:
                    filter_float = AnalysisResultFormatter._to_float(filter_val)
                    details.append(f"Filter: {filter_float} Hz")
                except (ValueError, TypeError, AttributeError):
                    details.append(f"Filter: {filter_val} Hz")

        mean_amp = result.get("mean_amplitude")
        if mean_amp is None and "summary_stats" in result and isinstance(result["summary_stats"], dict):
            mean_amp = result["summary_stats"].get("mean_amplitude")

        amp_units = result.get("units", "pA")
        if mean_amp is not None:
            try:
                amp_float = AnalysisResultFormatter._to_float(mean_amp)
                details.append(f"Mean Amplitude: {amp_float:.2f} {amp_units}")
            except (ValueError, TypeError, AttributeError):
                details.append(f"Mean Amplitude: {mean_amp} {amp_units}")

        return details

    # --- Phase Plane ---
    @staticmethod
    def _format_phase_plane(result: Dict[str, Any]) -> str:
        max_dvdt = result.get("max_dvdt")
        if max_dvdt is not None:
            try:
                val = AnalysisResultFormatter._to_float(max_dvdt)
                return f"Max dV/dt: {val:.2f} V/s"
            except Exception:
                return f"Max dV/dt: {max_dvdt}"
        return "N/A"

    @staticmethod
    def _details_phase_plane(result: Dict[str, Any]) -> List[str]:
        details = []
        thresh = result.get("threshold_mean")
        if thresh is not None:
            try:
                val = AnalysisResultFormatter._to_float(thresh)
                details.append(f"Mean Thresh: {val:.2f} mV")
            except Exception as e:
                log.debug(f"Skipped threshold formatting: {e}")
        return details

    # --- Excitability ---
    @staticmethod
    def _format_excitability(result: Dict[str, Any]) -> str:
        slope = result.get("fi_slope")
        if slope is not None:
            try:
                val = AnalysisResultFormatter._to_float(slope)
                return f"Slope: {val:.3f} Hz/pA"
            except Exception:
                return f"Slope: {slope}"
        return "N/A"

    @staticmethod
    def _details_excitability(result: Dict[str, Any]) -> List[str]:
        details = []
        rheo = result.get("rheobase_pa")
        if rheo is not None:
            details.append(f"Rheobase: {rheo} pA")

        max_freq = result.get("max_freq_hz")
        if max_freq is not None:
            try:
                val = AnalysisResultFormatter._to_float(max_freq)
                details.append(f"Max Freq: {val:.2f} Hz")
            except Exception as e:
                log.debug(f"Skipped max frequency formatting: {e}")
        return details

    # --- Tau ---
    @staticmethod
    def _format_tau(result: Dict[str, Any]) -> str:
        tau = result.get("tau_ms")
        if tau is not None:
            try:
                val = AnalysisResultFormatter._to_float(tau)
                return f"{val:.2f} ms"
            except Exception:
                return f"{tau} ms"
        return "N/A"


def generate_methods_text(result: Any) -> str:
    """
    Generate a natural language description of the analysis performed.

    Args:
        result: The result object (e.g. SpikeTrainResult) containing parameters.

    Returns:
        String description suitable for a paper's Methods section.
    """
    if not hasattr(result, "parameters") or not result.parameters:
        return "Analysis was performed using default parameters."

    params = result.parameters

    if isinstance(result, SpikeTrainResult):
        threshold = params.get("threshold", "unknown")
        refractory = params.get("refractory_period", "unknown")

        # Convert to ms if float (assuming seconds)
        if isinstance(refractory, (float, int)):
            refractory_str = f"{refractory * 1000.0:.2f} ms"
        else:
            refractory_str = str(refractory)

        text = (
            f"Action potentials were detected using a voltage threshold crossing algorithm. "
            f"The detection threshold was set to {threshold} mV with a refractory period "
            f"enforced to prevent double-counting within {refractory_str} of a spike. "
        )

        if "dvdt_threshold" in params:
            text += (
                f"Spike features were calculated based on the derivative of the membrane potential, "
                f"using a dV/dt onset threshold of {params['dvdt_threshold']} V/s. "
            )

        return text

    # Fallback for generic results
    param_str = ", ".join([f"{k}={v}" for k, v in params.items()])
    return f"Analysis performed with parameters: {param_str}."
