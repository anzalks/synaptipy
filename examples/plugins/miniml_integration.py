# -*- coding: utf-8 -*-
"""
Synaptipy Plugin for miniML Event Detection
https://github.com/delvendahl/miniML

This file is a **GUI plugin template** for Synaptipy's @AnalysisRegistry
system. It is NOT a standalone script. Drop it (or a copy) into
~/.synaptipy/plugins/ and enable "Enable Custom Plugins" in
Edit > Preferences to have it appear as a tab in the Analyser.

miniML is NOT a pip-installable package. It must be cloned from GitHub and
its core/ directory must be reachable from Python.

Setup (3 steps):
    1. Clone miniML once (outside the Synaptipy directory):
           git clone https://github.com/delvendahl/miniML.git ~/PycharmProjects/miniML

    2. Install miniML Python dependencies into your Synaptipy environment:
           conda activate synaptipy
           pip install "tensorflow>=2.17" tf_keras h5py scikit-learn ruptures==1.1.10

    3. In the Analyser "miniML Events" tab:
       - Paste the full path to the miniML core/ directory into "miniML core/ Path"
         e.g. /Users/you/PycharmProjects/miniML/core
       - Paste the full path to your .h5 model file into "Model Path (.h5)"
         e.g. /Users/you/PycharmProjects/miniML/models/GC_mEPSC_model.h5
       - Click Run Analysis.

miniML class API (as of commit 9bab948):
    MiniTrace(data, sampling_interval=<1/fs in seconds>)
    EventDetection(data=trace, event_direction='negative'|'positive',
                   model_path=<str>, model_threshold=<float>, batch_size=<int>)
    detector.detect_events()   # populates event_locations (sample indices)
    trace.sampling             # sampling interval in seconds (= 1/fs)
"""

import contextlib
import io
import logging
import os
import sys
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from synaptipy.core.analysis.registry import AnalysisRegistry

log = logging.getLogger(__name__)
_loaded_miniml_core_path: Optional[str] = None
_SETTINGS_CORE_KEY = "plugins/miniml/core_path"
_SETTINGS_MODEL_KEY = "plugins/miniml/model_path"


def _load_saved_miniml_paths() -> Tuple[str, str]:
    """Return persisted ``(core_path, model_path)`` from QSettings or standard local clone if present."""
    core_default = ""
    model_default = ""
    try:
        from PySide6.QtCore import QSettings

        from synaptipy.shared.constants import APP_NAME, SETTINGS_SECTION

        settings = QSettings(APP_NAME, SETTINGS_SECTION)
        core_default = str(settings.value(_SETTINGS_CORE_KEY, "", type=str) or "").strip()
        model_default = str(settings.value(_SETTINGS_MODEL_KEY, "", type=str) or "").strip()
    except Exception:
        pass

    if not core_default:
        for cand in (
            Path.home() / "PycharmProjects" / "miniML" / "core",
            Path.home() / "miniML" / "core",
        ):
            if (cand / "miniML.py").is_file():
                core_default = str(cand)
                break
    return core_default, model_default


def _save_miniml_paths(core_path: str, model_path: str) -> None:
    """Persist validated miniML directory and model file paths in QSettings."""
    try:
        from PySide6.QtCore import QSettings

        from synaptipy.shared.constants import APP_NAME, SETTINGS_SECTION

        settings = QSettings(APP_NAME, SETTINGS_SECTION)
        settings.setValue(_SETTINGS_CORE_KEY, core_path)
        settings.setValue(_SETTINGS_MODEL_KEY, model_path)
    except Exception:
        pass


def _normalize_core_dir(raw_core_path: str) -> str:
    """Expand ``~`` and auto-descend into ``core/`` if the user selected the miniML repository root."""
    cleaned = os.path.expanduser(str(raw_core_path or "").strip())
    if not cleaned:
        return ""
    p = Path(cleaned)
    if (p / "miniML.py").is_file():
        return str(p.resolve())
    if (p / "core" / "miniML.py").is_file():
        return str((p / "core").resolve())
    return os.path.abspath(cleaned)


class _StreamToLogger(io.TextIOBase):
    """Redirect a stream (stdout/stderr) to a Python logger line by line."""

    def __init__(self, logger: logging.Logger, level: int = logging.INFO) -> None:
        super().__init__()
        self._logger = logger
        self._level = level
        self._buf = ""

    def write(self, s: str) -> int:
        self._buf += s
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            stripped = line.rstrip()
            if stripped:
                self._logger.log(self._level, "%s", stripped)
        return len(s)

    def flush(self) -> None:
        if self._buf.strip():
            self._logger.log(self._level, "%s", self._buf.rstrip())
            self._buf = ""


def _evict_stale_miniml_modules(previous_dir: str) -> None:
    """Remove cached miniML modules and old sys.path entry when switching core_path."""
    prev_norm = os.path.normcase(os.path.abspath(previous_dir))
    sys.path[:] = [p for p in sys.path if os.path.normcase(os.path.abspath(p)) != prev_norm]
    prefix_with_sep = prev_norm + os.sep
    for mod_name in list(sys.modules.keys()):
        mod_obj = sys.modules.get(mod_name)
        mod_file = getattr(mod_obj, "__file__", None) if mod_obj is not None else None
        from_prev = bool(mod_file and os.path.normcase(os.path.abspath(mod_file)).startswith(prefix_with_sep))
        if mod_name == "miniML" or mod_name.startswith(("miniML.", "miniML_")) or from_prev:
            sys.modules.pop(mod_name, None)


def _import_miniml(miniml_core_path: str):
    """Lazily import miniML classes after adding core/ to sys.path.

    Returns (MiniTrace, EventDetection) or raises ImportError.
    """
    global _loaded_miniml_core_path

    core_path = _normalize_core_dir(miniml_core_path)
    if not core_path:
        raise ImportError(
            "miniML core/ path is empty. "
            "Paste the path to the miniML/core/ directory "
            "(the folder containing miniML.py) into the 'miniML core/ Path' field."
        )
    resolved_core = os.path.abspath(core_path)
    existing_mod = sys.modules.get("miniML")
    existing_file = getattr(existing_mod, "__file__", None) if existing_mod is not None else None
    existing_dir = os.path.abspath(os.path.dirname(existing_file)) if existing_file else _loaded_miniml_core_path
    if existing_dir is not None and os.path.normcase(existing_dir) != os.path.normcase(resolved_core):
        _evict_stale_miniml_modules(existing_dir)

    # TensorFlow >= 2.16 ships Keras 3 by default; .h5 models saved under
    # Keras 2 require the tf_keras compatibility layer. Setting this env var
    # before TF imports redirects tf.keras -> tf_keras (Keras 2 API).
    os.environ.setdefault("TF_USE_LEGACY_KERAS", "1")
    if core_path in sys.path:
        sys.path.remove(core_path)
    sys.path.insert(0, core_path)
    try:
        import importlib

        miniml_mod = importlib.import_module("miniML")
        MiniTrace = miniml_mod.MiniTrace
        EventDetection = miniml_mod.EventDetection
        _loaded_miniml_core_path = resolved_core
    except Exception as exc:
        raise ImportError(
            f"Could not import miniML from '{core_path}': {type(exc).__name__}: {exc}. "
            "Make sure the path points to the miniML/core/ directory "
            "(the folder that contains miniML.py and miniML_functions.py)."
        ) from exc
    return MiniTrace, EventDetection


def _locate_event_peaks(
    data: np.ndarray,
    ev_locs: np.ndarray,
    valid_mask: np.ndarray,
    direction: str,
    window_size: int,
    sampling_interval: float,
    time_start: float,
    time: Optional[np.ndarray] = None,
):
    """Map validated onset indices to amplitude-peak times and data values."""
    valid_locs = ev_locs[valid_mask]
    if valid_locs.size == 0:
        return [], []
    max_search = max(5, int(0.015 / sampling_interval)) if sampling_interval > 0 else max(1, window_size // 2)
    half_win = min(max(1, window_size // 2), max_search)
    find_extremum = np.argmin if direction == "negative" else np.argmax
    peak_indices = np.empty(len(valid_locs), dtype=np.int64)
    for k, onset in enumerate(valid_locs):
        next_onset = int(valid_locs[k + 1]) if k + 1 < len(valid_locs) else len(data)
        end_idx = min(int(onset) + half_win, max(int(onset) + 1, next_onset), len(data))
        seg = data[int(onset) : end_idx]
        peak_indices[k] = onset + find_extremum(seg) if len(seg) > 0 else onset
    if time is not None and len(time) == len(data):
        ev_times = np.asarray(time, dtype=float)[peak_indices].tolist()
    else:
        ev_times = (peak_indices * sampling_interval + time_start).tolist()
    ev_peaks = data[peak_indices].tolist()
    return ev_times, ev_peaks


def _compute_event_scores(detector: Any, ev_locs: np.ndarray, valid_mask: np.ndarray):
    """Extract per-event confidence scores from the detector if available."""
    if hasattr(detector, "event_scores") and len(detector.event_scores) == len(ev_locs):
        scores_arr = np.asarray(detector.event_scores)[valid_mask]
        if len(scores_arr) > 0:
            return (
                scores_arr.tolist(),
                round(float(np.mean(scores_arr)), 4),
                round(float(np.min(scores_arr)), 4),
            )
    return None, None, None


def _validate_miniml_inputs(
    data: Optional[np.ndarray],
    time: Optional[np.ndarray],
    sampling_rate: float,
    model_path: str,
) -> Optional[str]:
    """Validate array shapes, sampling rate, and model path; return error string or None."""
    if data is None or data.size == 0:
        return "Empty data array provided."
    if sampling_rate is None or not np.isfinite(sampling_rate) or sampling_rate <= 0:
        return "sampling_rate must be a positive finite value."
    if time is None or len(time) != len(data):
        return (
            f"Time and data length mismatch: len(time)={0 if time is None else len(time)} " f"vs len(data)={len(data)}."
        )
    if not model_path.strip():
        return "No model path provided. Paste the full path to your .h5 model file into the 'Model Path' field."
    expanded_model = os.path.expanduser(model_path.strip())
    if os.path.sep in expanded_model or expanded_model.startswith("."):
        if not os.path.isfile(expanded_model):
            return f"Model file not found: '{expanded_model}'."
    return None


def _build_minitrace(mini_trace_cls: Any, data: np.ndarray, sampling_interval: float, y_unit: str = "") -> Any:
    """Instantiate MiniTrace across legacy (`sampling`) and current (`sampling_interval`) APIs."""
    try:
        return mini_trace_cls(data=data, sampling_interval=sampling_interval, y_unit=y_unit)
    except TypeError:
        try:
            return mini_trace_cls(data=data, sampling_interval=sampling_interval)
        except TypeError:
            return mini_trace_cls(data=data, sampling=sampling_interval)


def _extract_event_positions_and_amplitudes(
    detector: Any,
    data: np.ndarray,
    time: np.ndarray,
    ev_locs: np.ndarray,
    valid_mask: np.ndarray,
    direction: str,
    window_size: int,
    sampling_interval: float,
) -> Tuple[List[float], List[float], List[float]]:
    """Return ``(ev_times_s, raw_trace_peaks, baseline_subtracted_amplitudes)``."""
    peak_locs = getattr(detector, "event_peak_locations", None)
    if peak_locs is not None and len(peak_locs) == len(ev_locs):
        pk_arr = np.asarray(peak_locs, dtype=np.int64)[valid_mask]
        pk_arr = np.clip(pk_arr, 0, max(0, len(data) - 1))
        ev_times = np.asarray(time, dtype=float)[pk_arr].tolist() if len(pk_arr) > 0 else []
        ev_peaks = data[pk_arr].astype(float).tolist() if len(pk_arr) > 0 else []
    else:
        ev_times, ev_peaks = _locate_event_peaks(
            data, ev_locs, valid_mask, direction, window_size, sampling_interval, float(time[0]), time=time
        )

    stats = getattr(detector, "event_stats", None)
    stat_amps = getattr(stats, "amplitudes", None) if stats is not None else None
    if stat_amps is not None and len(stat_amps) == int(np.sum(valid_mask)):
        ev_amps = np.asarray(stat_amps, dtype=float).tolist()
    elif len(ev_peaks) > 0:
        valid_onsets = ev_locs[valid_mask]
        pre_n = max(5, int(round(0.005 / max(sampling_interval, 1e-6))))
        ev_amps = []
        for k, pk_val in enumerate(ev_peaks):
            on_i = int(valid_onsets[k]) if k < len(valid_onsets) else 0
            b0 = max(0, on_i - pre_n)
            base = float(np.median(data[b0 : max(b0 + 1, on_i)])) if len(data) > 0 else 0.0
            ev_amps.append(float(pk_val) - base)
    else:
        ev_amps = []
    return ev_times, ev_peaks, ev_amps


def _extract_optional_kinetics_ms(detector: Any) -> Tuple[Optional[float], Optional[float]]:
    """Extract mean rise time (ms) and mean half-decay time (ms) from ``detector.event_stats`` if present."""
    stats = getattr(detector, "event_stats", None)
    if stats is None:
        return None, None
    mean_rise_ms = None
    mean_halfdecay_ms = None
    for attr_name, target in (("risetimes", "rise"), ("halfdecays", "decay")):
        vals = getattr(stats, attr_name, None)
        if vals is not None and len(vals) > 0:
            arr = np.asarray(vals, dtype=float)
            finite = arr[np.isfinite(arr)]
            if finite.size > 0:
                val_ms = round(float(np.mean(finite)) * 1000.0, 4)
                if target == "rise":
                    mean_rise_ms = val_ms
                else:
                    mean_halfdecay_ms = val_ms
    return mean_rise_ms, mean_halfdecay_ms


def run_miniml_detection(  # noqa: C901
    data: np.ndarray,
    time: np.ndarray,
    sampling_rate: float,
    threshold: float = 0.5,
    direction: str = "negative",
    model_path: str = "",
    miniml_core_path: str = "",
    batch_size: int = 512,
    window_size: int = 600,
    rel_prom_cutoff: float = 0.25,
    convolve_win: int = 0,
    gradient_convolve_win: int = 0,
    channel_units: str = "pA",
) -> Dict[str, Any]:
    """Run miniML inference on a single trial and return baseline-subtracted event metrics."""
    validation_err = _validate_miniml_inputs(data, time, sampling_rate, model_path)
    if validation_err is not None:
        return {"error": validation_err}

    active_model = os.path.expanduser(model_path.strip())
    resolved_core = _normalize_core_dir(miniml_core_path)

    try:
        MiniTrace, EventDetection = _import_miniml(resolved_core)
    except ImportError as exc:
        return {"error": str(exc)}

    _save_miniml_paths(resolved_core, active_model)
    log.info("miniML: libraries imported from '%s'", resolved_core)

    try:
        sampling_interval = 1.0 / sampling_rate  # seconds per sample
        trace = _build_minitrace(MiniTrace, data, sampling_interval, y_unit=str(channel_units or ""))
        log.info(
            "miniML: trace - %.3f s at %.0f Hz (%d samples)",
            float(time[-1] - time[0]),
            sampling_rate,
            data.size,
        )
        detector = EventDetection(
            data=trace,
            event_direction=direction,
            model_path=active_model,
            model_threshold=threshold,
            batch_size=batch_size,
            window_size=window_size,
        )
        log.info(
            "miniML: running inference (batch=%d, threshold=%.2f, direction=%s)...",
            batch_size,
            threshold,
            direction,
        )
        _stdout_capture = _StreamToLogger(log, logging.INFO)
        _stderr_capture = _StreamToLogger(log, logging.WARNING)
        detect_kwargs: Dict[str, Any] = {
            "eval": True,
            "rel_prom_cutoff": rel_prom_cutoff,
        }
        if int(convolve_win) > 0:
            detect_kwargs["convolve_win"] = int(convolve_win)
        if int(gradient_convolve_win) > 0:
            detect_kwargs["gradient_convolve_win"] = int(gradient_convolve_win)
        with contextlib.redirect_stdout(_stdout_capture), contextlib.redirect_stderr(_stderr_capture):
            detector.detect_events(**detect_kwargs)
        _stdout_capture.flush()
        _stderr_capture.flush()
        log.info(
            "miniML: inference done - %d raw locations",
            len(getattr(detector, "event_locations", [])),
        )
    except Exception as e:
        log.error("miniML detection failed:\n%s", traceback.format_exc())
        return {"error": f"miniML inference error: {str(e)}"}

    raw_locs = getattr(detector, "event_locations", None)
    ev_locs = np.asarray(raw_locs if raw_locs is not None else [], dtype=np.int64)
    valid_mask = (ev_locs >= 0) & (ev_locs < len(data))
    ev_times, ev_peaks, ev_amps = _extract_event_positions_and_amplitudes(
        detector, data, time, ev_locs, valid_mask, direction, window_size, sampling_interval
    )
    mean_rise_ms, mean_halfdecay_ms = _extract_optional_kinetics_ms(detector)

    duration = float(time[-1] - time[0]) if len(time) > 1 else 0.0
    freq = float(len(ev_times)) / duration if duration > 0 else 0.0
    model_label = active_model.replace("\\", "/").split("/")[-1]

    if len(ev_amps) > 0:
        amps_arr = np.asarray(ev_amps, dtype=float)
        finite_amps = amps_arr[np.isfinite(amps_arr)]
        mean_amp = round(float(np.mean(finite_amps)), 4) if finite_amps.size > 0 else None
        std_amp = round(float(np.std(finite_amps)), 4) if finite_amps.size > 0 else None
    else:
        mean_amp = None
        std_amp = None

    if len(ev_times) >= 2:
        iei_arr = np.diff(np.array(ev_times)) * 1000.0
        mean_iei = round(float(np.mean(iei_arr)), 4)
        std_iei = round(float(np.std(iei_arr)), 4)
    else:
        mean_iei = None
        std_iei = None

    ev_scores, mean_score, min_score = _compute_event_scores(detector, ev_locs, valid_mask)
    u_norm = str(channel_units or "pA").strip().lower().replace("\u00b5", "u").replace("\u03bc", "u")
    amp_suffix = "mV" if u_norm in ("mv", "v", "uv") else "pA"

    metrics: Dict[str, Any] = {
        "Event_Count": len(ev_times),
        "Frequency_Hz": round(freq, 2),
        "Model_Used": model_label,
        f"Mean_Amplitude_{amp_suffix}": mean_amp,
        f"Std_Amplitude_{amp_suffix}": std_amp,
        "Mean_Rise_Time_ms": mean_rise_ms,
        "Mean_Half_Decay_ms": mean_halfdecay_ms,
        "Mean_IEI_ms": mean_iei,
        "Std_IEI_ms": std_iei,
        "Mean_Score": mean_score,
        "Min_Score": min_score,
    }
    warnings_list: List[str] = []
    if len(ev_times) == 0:
        warnings_list.append(
            "0 events detected above threshold. Verify Direction ('negative' for inward EPSC/IPSC, "
            "'positive' for depolarizing EPSP) and ensure the selected .h5 model matches this recording type."
        )

    return {
        "module_used": "miniml_events",
        "metrics": metrics,
        "warnings": warnings_list,
        "_event_times": ev_times,
        "_event_peaks": ev_peaks,
        "_event_scores": ev_scores,
        "_event_amplitudes": ev_amps,
    }


_DEFAULT_CORE_PATH, _DEFAULT_MODEL_PATH = _load_saved_miniml_paths()


@AnalysisRegistry.register(
    name="miniml_events",
    label="miniML Events",
    expects_list=False,
    supported_channel_units=("pA", "nA", "uA", "A", "mV", "V", "uV"),
    run_button=True,
    ui_params=[
        {
            "name": "miniml_core_path",
            "label": "miniML core/ Path:",
            "type": "dirpath",
            "default": _DEFAULT_CORE_PATH,
            "placeholder": "/path/to/miniML/core",
            "tooltip": (
                "Path to the miniML/core/ directory (or miniML repo root). "
                "Clone miniML from https://github.com/delvendahl/miniML"
            ),
        },
        {
            "name": "model_path",
            "label": "Model Path (.h5):",
            "type": "filepath",
            "default": _DEFAULT_MODEL_PATH,
            "placeholder": "/path/to/miniML/models/GC_lstm_model.h5",
            "tooltip": (
                "Path to the miniML Keras model file (.h5). "
                "Model files live in the miniML/models/ directory of the cloned repo."
            ),
        },
        {
            "name": "threshold",
            "label": "Prediction Threshold:",
            "type": "float",
            "default": 0.5,
            "min": 0.0,
            "max": 1.0,
            "decimals": 2,
            "tooltip": "miniML score cutoff [0, 1]. Higher = fewer false positives.",
        },
        {
            "name": "direction",
            "label": "Direction:",
            "type": "choice",
            "choices": ["negative", "positive"],
            "default": "negative",
            "default_by_clamp_mode": {"voltage_clamp": "negative", "current_clamp": "positive"},
            "tooltip": "negative = inward currents/IPSPs; positive = depolarizing EPSPs/outward currents.",
        },
        {
            "name": "batch_size",
            "label": "Batch Size:",
            "type": "int",
            "default": 512,
            "min": 1,
            "max": 4096,
            "tooltip": "Inference batch size (miniML default: 512). Reduce if out of memory.",
        },
        {
            "name": "window_size",
            "label": "Window Size (samples):",
            "type": "int",
            "default": 600,
            "min": 1,
            "max": 10000,
            "tooltip": "Detection window size",
        },
        {
            "name": "rel_prom_cutoff",
            "label": "Rel. Prominence Cutoff:",
            "type": "float",
            "default": 0.25,
            "min": 0.0,
            "max": 1.0,
            "decimals": 3,
            "tooltip": "Sensitivity for overlapping events (miniML default: 0.25)",
        },
        {
            "name": "convolve_win",
            "label": "Convolve Window:",
            "type": "int",
            "default": 0,
            "min": 0,
            "max": 1000,
            "tooltip": "Smoothing window in samples (0 = automatic miniML rate-adaptive filter).",
        },
        {
            "name": "gradient_convolve_win",
            "label": "Gradient Convolve Window:",
            "type": "int",
            "default": 0,
            "min": 0,
            "max": 1000,
            "tooltip": "Gradient smoothing window in samples (0 = automatic miniML rate-adaptive filter).",
        },
    ],
    plots=[
        {
            "type": "markers",
            "x": "_event_times",
            "y": "_event_peaks",
            "color": "r",
            "symbol": "o",
            "tooltip": "miniML Detected Events",
        }
    ],
)
def run_miniml_events_wrapper(
    data: np.ndarray,
    time: np.ndarray,
    sampling_rate: float,
    **kwargs: Any,
) -> Dict[str, Any]:
    """Synaptipy registry wrapper for miniML event detection."""
    core_path_str = str(kwargs.get("miniml_core_path", "") or "").strip()
    model_path_str = str(kwargs.get("model_path", "") or "").strip()
    if not core_path_str or not model_path_str:
        from synaptipy.application.gui.analysis_tabs.base import AnalysisNotConfigured

        missing_parts = []
        if not core_path_str:
            missing_parts.append("'miniML core/ Path'")
        if not model_path_str:
            missing_parts.append("'Model Path (.h5)'")
        raise AnalysisNotConfigured(
            f"miniML Events needs {' and '.join(missing_parts)} configured on the left before running."
        )

    return run_miniml_detection(
        data=data,
        time=time,
        sampling_rate=sampling_rate,
        threshold=kwargs.get("threshold", 0.5),
        direction=kwargs.get("direction", "negative"),
        batch_size=kwargs.get("batch_size", 512),
        model_path=model_path_str,
        miniml_core_path=core_path_str,
        window_size=kwargs.get("window_size", 600),
        rel_prom_cutoff=kwargs.get("rel_prom_cutoff", 0.25),
        convolve_win=int(kwargs.get("convolve_win", 0)),
        gradient_convolve_win=int(kwargs.get("gradient_convolve_win", 0)),
        channel_units=str(kwargs.get("channel_units", "pA") or "pA"),
    )
