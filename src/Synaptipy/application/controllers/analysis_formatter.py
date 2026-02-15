# src/Synaptipy/application/controllers/analysis_formatter.py
from typing import Dict, Any, Tuple, List
import logging
from Synaptipy.core.results import SpikeTrainResult

log = logging.getLogger(__name__)


class AnalysisResultFormatter:
    """
    Encapsulates logic for formatting analysis results into human-readable strings
    for display in the ExporterTab and other UI components.
    """

    @staticmethod
    def format_result(result: Dict[str, Any]) -> Tuple[str, List[str]]:
        """
        Formats a single analysis result dictionary.
        Returns: (value_str, details_list)
        """
        analysis_type = result.get("analysis_type", "Unknown")
        value_str = "N/A"
        details = []

        try:
            if analysis_type in ["Input Resistance", "Input Resistance/Conductance"]:
                value_str = AnalysisResultFormatter._format_input_resistance(result)
                details = AnalysisResultFormatter._details_input_resistance(result)
                # Fallback check
                if value_str == "N/A":
                    value_str, details_fallback = AnalysisResultFormatter._format_rin_fallback(result)
                    if details_fallback:
                        details.extend(details_fallback)

            elif analysis_type == "Baseline Analysis":
                value_str = AnalysisResultFormatter._format_baseline(result)
                details = AnalysisResultFormatter._details_baseline(result)
                # Fallback check
                if value_str == "N/A":
                    value_str, details_fallback = AnalysisResultFormatter._format_rmp_fallback(result)
                    if details_fallback:
                        details.extend(details_fallback)

            elif analysis_type == "Spike Detection (Threshold)":
                value_str = AnalysisResultFormatter._format_spike_detection(result)
                details = AnalysisResultFormatter._details_spike_detection(result)

            elif analysis_type == "Event Detection":
                value_str = AnalysisResultFormatter._format_event_detection(result)
                details = AnalysisResultFormatter._details_event_detection(result)

            elif analysis_type in ["Phase Plane Analysis", "phase_plane_analysis"]:
                value_str = AnalysisResultFormatter._format_phase_plane(result)
                details = AnalysisResultFormatter._details_phase_plane(result)

            elif analysis_type in ["Excitability Analysis", "excitability_analysis"]:
                value_str = AnalysisResultFormatter._format_excitability(result)
                details = AnalysisResultFormatter._details_excitability(result)

            elif analysis_type in ["Membrane Time Constant (Tau)", "tau_analysis"]:
                value_str = AnalysisResultFormatter._format_tau(result)

            # Check explicit fallbacks for older keys if analysis_type implies them
            elif analysis_type in ["rmp_analysis"]:
                value_str, details_fallback = AnalysisResultFormatter._format_rmp_fallback(result)
                details.extend(details_fallback)

            elif analysis_type in ["rin_analysis"]:
                value_str, details_fallback = AnalysisResultFormatter._format_rin_fallback(result)
                details.extend(details_fallback)

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
            except (ValueError, TypeError, AttributeError):
                pass
        return value_str, details

    # --- Baseline / RMP ---
    @staticmethod
    def _format_baseline(result: Dict[str, Any]) -> str:
        mean = result.get("baseline_mean")
        sd = result.get("baseline_sd")
        units = result.get("baseline_units", "")
        method = result.get("calculation_method", "")

        method_display = ""
        if method:
            if method.startswith("auto_"):
                method_display = " (Auto)"
            elif method.startswith("manual_"):
                method_display = " (Manual)"
            elif method.startswith("interactive_"):
                method_display = " (Interactive)"

        if mean is not None and sd is not None:
            try:
                mean_float = AnalysisResultFormatter._to_float(mean)
                sd_float = AnalysisResultFormatter._to_float(sd)
                return f"{mean_float:.3f} ± {sd_float:.3f} {units}{method_display}"
            except (ValueError, TypeError, AttributeError):
                return f"Mean: {mean}, SD: {sd} {units}{method_display}"
        return "N/A"

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
            except (ValueError, TypeError, AttributeError):
                pass
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
                    except (ValueError, TypeError, AttributeError):
                        pass
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
        summary_stats = result.get("summary_stats", {})
        if not isinstance(summary_stats, dict):
            summary_stats = {}

        event_count = summary_stats.get("count")
        if event_count is not None:
            try:
                count = int(AnalysisResultFormatter._to_float(event_count))
                value_str = f"{count} events"

                freq = summary_stats.get("frequency_hz")
                if freq is not None:
                    try:
                        freq_float = AnalysisResultFormatter._to_float(freq)
                        value_str += f" ({freq_float:.2f} Hz)"
                    except (ValueError, TypeError, AttributeError):
                        pass
                return value_str
            except (ValueError, TypeError, AttributeError):
                return f"{event_count} events"
        return "N/A"

    @staticmethod
    def _details_event_detection(result: Dict[str, Any]) -> List[str]:
        details = []
        method = result.get("method", "")
        if method:
            details.append(f"Method: {method}")

        params = result.get("parameters", {})
        if isinstance(params, dict):
            direction = params.get("direction")
            if direction:
                details.append(f"Direction: {direction}")

            filter_val = params.get("filter")
            if filter_val is not None:
                try:
                    filter_float = AnalysisResultFormatter._to_float(filter_val)
                    details.append(f"Filter: {filter_float} Hz")
                except (ValueError, TypeError, AttributeError):
                    details.append(f"Filter: {filter_val} Hz")

        summary_stats = result.get("summary_stats", {})
        if isinstance(summary_stats, dict):
            mean_amp = summary_stats.get("mean_amplitude")
            amp_units = result.get("units", "")
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
            except Exception:
                pass
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
            except Exception:
                pass
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
