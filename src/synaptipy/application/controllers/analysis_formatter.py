import logging
from typing import Any, Dict, List, Tuple, Union

import numpy as np

from synaptipy.core.results import AnalysisResult, RinResult, SpikeTrainResult

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
            # Dictionary result: unpack nested 'result', Schema v1 'metrics', and 'specific_data'
            merged: Dict[str, Any] = {}
            nested_result = result.get("result")
            if hasattr(nested_result, "__dict__"):
                merged.update({k: v for k, v in nested_result.__dict__.items() if not str(k).startswith("_")})
            if isinstance(result.get("specific_data"), dict):
                merged.update({k: v for k, v in result["specific_data"].items() if not str(k).startswith("_")})
            if isinstance(result.get("metrics"), dict):
                merged.update({k: v for k, v in result["metrics"].items() if not str(k).startswith("_")})
            for k, v in result.items():
                if k not in ("metrics", "specific_data", "schema_version") and not str(k).startswith("_"):
                    merged[k] = v
            result = merged
            analysis_type = str(result.get("analysis_type") or result.get("analysis_name") or "Unknown")

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

            elif "i-v" in target_type or "iv_curve" in target_type:
                rin_iv = result.get("rin_aggregate_mohm")
                value_str = f"{AnalysisResultFormatter._to_float(rin_iv):.2f} MOhm" if rin_iv is not None else "N/A"
                if result.get("iv_r_squared") is not None:
                    details.append(f"R^2: {AnalysisResultFormatter._to_float(result['iv_r_squared']):.3f}")

            elif "capacitance" in target_type:
                cm = result.get("capacitance_pf")
                value_str = f"{AnalysisResultFormatter._to_float(cm):.2f} pF" if cm is not None else "N/A"

            elif "baseline" in target_type or "rmp" in target_type or "resting membrane" in target_type:
                value_str = AnalysisResultFormatter._format_baseline(result)
                details = AnalysisResultFormatter._details_baseline(result)
                if value_str == "N/A":
                    value_str, details_fallback = AnalysisResultFormatter._format_rmp_fallback(result)
                    if details_fallback:
                        details.extend(details_fallback)

            elif "train dynamics" in target_type or target_type == "train_dynamics":
                cv = result.get("cv")
                value_str = f"CV: {AnalysisResultFormatter._to_float(cv):.3f}" if cv is not None else "N/A"
                if result.get("spike_count") is not None:
                    details.append(f"Spikes: {int(result['spike_count'])}")

            elif "burst" in target_type:
                bc = result.get("burst_count")
                value_str = f"{int(bc)} bursts" if bc is not None else "N/A"

            elif "paired-pulse" in target_type or "ppr" in target_type:
                ppr = result.get("ratio_p2", result.get("ppr"))
                value_str = f"PPR: {AnalysisResultFormatter._to_float(ppr):.3f}" if ppr is not None else "N/A"

            elif "evoked sync" in target_type or "optogenetic" in target_type:
                lat = result.get("optical_latency_ms")
                value_str = f"Latency: {AnalysisResultFormatter._to_float(lat):.2f} ms" if lat is not None else "N/A"
                if result.get("response_probability_pct") is not None:
                    prob_val = AnalysisResultFormatter._to_float(result["response_probability_pct"])
                    details.append(f"Prob: {prob_val:.1f}%")

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

            elif "sag" in target_type:
                value_str = AnalysisResultFormatter._format_sag(result)
                details = AnalysisResultFormatter._details_sag(result)

            else:
                skip_meta = {
                    "analysis_type",
                    "analysis_name",
                    "channel_id",
                    "channel_name",
                    "trial_index_used",
                    "schema_version",
                    "data_source_used",
                    "source_file_name",
                    "source_file_path",
                    "item_target_type",
                    "timestamp_saved",
                }
                numeric_vals = [
                    f"{k}: {AnalysisResultFormatter._to_float(v):.2f}"
                    for k, v in result.items()
                    if k not in skip_meta
                    and isinstance(v, (int, float, np.number))
                    and not isinstance(v, bool)
                    and np.isfinite(float(v))
                    and "time" not in k.lower()
                ]

                if numeric_vals:
                    value_str = numeric_vals[0]
                    if len(numeric_vals) > 1:
                        details.extend(numeric_vals[1:])
                else:
                    other_vals = [
                        f"{k}: {v}"
                        for k, v in result.items()
                        if not isinstance(v, (dict, list, tuple, np.ndarray)) and k not in skip_meta
                    ]
                    if other_vals:
                        value_str = other_vals[0]
                        if len(other_vals) > 1:
                            details.extend(other_vals[1:])

        except Exception as e:
            log.warning(f"Error formatting value for {analysis_type}: {e}")
            value_str = "Error"

        return value_str, details

    @staticmethod
    def _to_float(val: Any) -> float:
        """Safe float conversion handling numpy items."""
        import numpy as np

        if isinstance(val, (int, float, np.number)):
            return float(val)
        if hasattr(val, "item"):
            return float(val.item())
        return float(val)

    # --- Sag Ratio ---
    @staticmethod
    def _format_sag(result: Dict[str, Any]) -> str:
        for key in ["sag_ratio", "Sag Ratio", "Ratio"]:
            value = result.get(key)
            if value is not None:
                try:
                    vf = AnalysisResultFormatter._to_float(value)
                    return f"{vf:.3f}"
                except (ValueError, TypeError, AttributeError):
                    pass
        return "N/A"

    @staticmethod
    def _details_sag(result: Dict[str, Any]) -> List[str]:
        details = []
        for dkey in ["peak_mV", "steady_state_mV", "baseline_mV"]:
            if dkey in result:
                try:
                    details.append(f"{dkey}: {AnalysisResultFormatter._to_float(result[dkey]):.2f} mV")
                except Exception:
                    details.append(f"{dkey}: {result[dkey]}")
        return details

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

        if mean is None:
            mean = result.get("rmp_mv")
        if mean is None:
            mean = result.get("RMP (mV)")
        if sd is None:
            sd = result.get("rmp_std")
        if sd is None:
            sd = result.get("Std Dev (mV)")
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

                rate = result.get("average_firing_rate_hz", result.get("mean_freq_hz"))
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
        event_count = result.get("event_count", result.get("Event Count"))

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


def _extract_result_parameters(result: Any) -> Dict[str, Any]:
    """Extract parameters dict from a Result dataclass, boundary AnalysisResult, or raw dict."""
    if hasattr(result, "parameters") and isinstance(getattr(result, "parameters"), dict):
        return dict(result.parameters)
    if hasattr(result, "metrics") and isinstance(getattr(result, "metrics"), dict):
        m_params = result.metrics.get("parameters")
        if isinstance(m_params, dict):
            return dict(m_params)
    if hasattr(result, "provenance") and isinstance(getattr(result, "provenance"), dict):
        p_params = result.provenance.get("parameters")
        if isinstance(p_params, dict):
            return dict(p_params)
    if isinstance(result, dict):
        if isinstance(result.get("parameters"), dict):
            return dict(result["parameters"])
        if isinstance(result.get("provenance"), dict) and isinstance(result["provenance"].get("parameters"), dict):
            return dict(result["provenance"]["parameters"])
        if isinstance(result.get("metrics"), dict) and isinstance(result["metrics"].get("parameters"), dict):
            return dict(result["metrics"]["parameters"])
    return {}


def _extract_analysis_name(result: Any) -> str:
    """Resolve canonical analysis name or label from result object or dict."""
    if isinstance(result, SpikeTrainResult):
        return "spike_detection"
    if isinstance(result, RinResult):
        return "rin_analysis"
    if hasattr(result, "analysis_name") and getattr(result, "analysis_name"):
        return str(result.analysis_name)
    if isinstance(result, dict):
        for k in ("analysis_name", "_analysis_type_override", "analysis_type"):
            if result.get(k):
                return str(result[k])
    return ""


def generate_methods_text(result: Any) -> str:  # noqa: C901
    """
    Generate a natural language description of the analysis performed.

    Args:
        result: The result object, boundary AnalysisResult, or dict containing parameters.

    Returns:
        String description suitable for a paper's Methods section.
    """
    params = _extract_result_parameters(result)
    analysis_id = _extract_analysis_name(result).lower()

    if isinstance(result, SpikeTrainResult) or "spike_detection" in analysis_id or analysis_id == "spike detection":
        if not params:
            return "Action potentials were detected using a voltage threshold crossing algorithm."
        threshold = params.get("threshold", "unknown")
        refractory = params.get("refractory_period", "unknown")

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

        return text.strip()

    if "rmp" in analysis_id or "baseline" in analysis_id:
        b0 = params.get("baseline_start", 0.0)
        b1 = params.get("baseline_end", 0.1)
        ljp = params.get("ljp_correction_mv", 0.0)
        txt = f"Resting membrane potential (RMP) was measured as the mean baseline potential over {b0}-{b1} s."
        if ljp:
            txt += f" Voltages were corrected for a liquid junction potential of {ljp} mV."
        return txt

    if "rin" in analysis_id or "input resistance" in analysis_id:
        step_i = params.get("current_amplitude")
        step_v = params.get("voltage_step")
        stim_desc = f"{step_i} pA current step" if step_i else (f"{step_v} mV voltage step" if step_v else "step pulse")
        return (
            f"Input resistance was calculated from the steady-state deflection evoked by a {stim_desc} "
            f"relative to pre-stimulus baseline."
        )

    if "tau" in analysis_id or "time constant" in analysis_id:
        model = params.get("tau_model", params.get("model", "mono"))
        dur = params.get("fit_duration", 0.05)
        return (
            f"Membrane time constant (tau) was estimated by fitting a {model}-exponential function "
            f"over a {dur} s window following stimulus onset."
        )

    if "sag" in analysis_id:
        return (
            "Hyperpolarization-activated sag ratio was quantified from baseline, peak hyperpolarization, "
            "and steady-state membrane potential windows."
        )

    if "iv_curve" in analysis_id or "i-v" in analysis_id:
        return (
            "Current-voltage (I-V) relationships were constructed across sequential current steps "
            "and input resistance was derived by subthreshold linear regression."
        )

    if "phase_plane" in analysis_id or "phase plane" in analysis_id:
        dvdt_thr = params.get("dvdt_threshold", 20.0)
        sigma = params.get("sigma_ms", 0.1)
        return (
            f"Action potential phase-plane trajectories (dV/dt vs. V) were computed using Savitzky-Golay "
            f"differentiation ({sigma} ms window) with an onset threshold of {dvdt_thr} V/s."
        )

    if "excitability" in analysis_id or "f-i" in analysis_id:
        thr = params.get("threshold", -20.0)
        return (
            f"Intrinsic excitability (F-I curve and rheobase) was quantified across current steps "
            f"using a spike threshold of {thr} mV, fitting firing-frequency gain over the linear rising phase."
        )

    if "deconvolution" in analysis_id or "template" in analysis_id:
        tr = params.get("tau_rise_ms", 0.5)
        td = params.get("tau_decay_ms", 5.0)
        sd = params.get("threshold_sd", 4.0)
        return (
            f"Synaptic events were detected via zero-mean template matching (tau_rise={tr} ms, "
            f"tau_decay={td} ms, detection threshold={sd} SD)."
        )

    if "event_detection" in analysis_id or "event" in analysis_id:
        thr = params.get("threshold", 5.0)
        pol = params.get("direction", "negative")
        return (
            f"Spontaneous synaptic events ({pol} polarity) were detected using rolling-baseline "
            f"adaptive prominence thresholding (threshold={thr})."
        )

    if "paired_pulse" in analysis_id or "ppr" in analysis_id:
        win = params.get("response_window_ms", 20.0)
        return (
            f"Paired-pulse ratios (PPR) were computed within a {win} ms post-stimulus peak window "
            f"with exponential decay residual subtraction."
        )

    if "optogenetic" in analysis_id or "evoked sync" in analysis_id:
        win = params.get("response_window_ms", 20.0)
        return (
            f"Stimulus-evoked synchronization, latency, and jitter were quantified within a "
            f"{win} ms post-TTL response window."
        )

    if not params:
        if analysis_id:
            return f"{analysis_id.replace('_', ' ').title()} analysis was performed using default parameters."
        return "Analysis was performed using default parameters."

    clean_params = {
        k: v for k, v in params.items() if not str(k).startswith("_") and not isinstance(v, (np.ndarray, list, dict))
    }
    param_str = ", ".join([f"{k}={v}" for k, v in clean_params.items()])
    prefix = f"{analysis_id.replace('_', ' ').title()} analysis" if analysis_id else "Analysis"
    return f"{prefix} performed with parameters: {param_str}."
