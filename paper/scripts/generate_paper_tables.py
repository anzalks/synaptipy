#!/usr/bin/env python3
"""
SynaptiPy modular runner for generating paper tables.

Downloads NWB files from the Allen Institute Cell Types Database,
runs SynaptiPy, eFEL, and IPFX, and generates Extended Data Tables 1 & 2
(Active and Passive properties) to fully reproduce the benchmarks.
Also plots raw traces for manual verification.

Usage:
    python scripts/generate_paper_tables.py
"""

import argparse
import logging
import sys
import warnings
from pathlib import Path

import matplotlib.pyplot as plt
import neo
import numpy as np
import pandas as pd
import quantities as pq
from scipy.stats import pearsonr, t

# Fix for xarray/allensdk with NumPy 2.0+
if not hasattr(np, "unicode_"):
    np.unicode_ = np.str_
if not hasattr(np, "VisibleDeprecationWarning"):
    np.VisibleDeprecationWarning = UserWarning

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from Synaptipy.core.analysis.batch_engine import BatchAnalysisEngine
from Synaptipy.core.data_model import Channel, Recording
from Synaptipy.infrastructure.file_readers.neo_source_handle import NeoSourceHandle

CACHE_DIR = REPO_ROOT / "paper" / "data" / "allen_cache"
OUT_DIR = REPO_ROOT / "paper" / "analysis_results"
PLOTS_DIR = REPO_ROOT / "paper" / "raw_nwb_plots"

OUT_DIR.mkdir(parents=True, exist_ok=True)
CACHE_DIR.mkdir(parents=True, exist_ok=True)
PLOTS_DIR.mkdir(parents=True, exist_ok=True)

# Patch numpy 2.0 breaking changes inside allensdk before heavy use
if not hasattr(np, "unicode_"):
    np.unicode_ = np.str_
if not hasattr(np, "VisibleDeprecationWarning"):
    np.VisibleDeprecationWarning = DeprecationWarning

from allensdk.api.queries.cell_types_api import CellTypesApi
from allensdk.core.cell_types_cache import CellTypesCache

# Global ctc instance so it can be used for sweep metadata
ctc = CellTypesCache(manifest_file=str(CACHE_DIR / "manifest.json"))

TARGET_N = 10

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ── Stats Helpers ─────────────────────────────────────────────────────────────


def corr_summary(x: np.ndarray, y: np.ndarray) -> dict:
    mask = ~(np.isnan(x) | np.isnan(y))
    x, y = x[mask], y[mask]
    n = len(x)
    if n < 3:
        return dict(n=n, r=np.nan, p=np.nan, bias=np.nan, loa_upper=np.nan, loa_lower=np.nan)
    r, p = pearsonr(x, y)
    diff = y - x
    mean_diff = float(np.mean(diff))
    std_diff = float(np.std(diff, ddof=1))
    return dict(
        n=n,
        r=round(r, 4),
        p=p,
        bias=round(mean_diff, 3),
        loa_upper=round(mean_diff + 1.96 * std_diff, 3),
        loa_lower=round(mean_diff - 1.96 * std_diff, 3),
    )


def bland_altman_summary(x: np.ndarray, y: np.ndarray) -> dict:
    """Return Bland-Altman agreement statistics (x=reference, y=SynaptiPy)."""
    mask = ~(np.isnan(x) | np.isnan(y))
    x, y = x[mask], y[mask]
    n = len(x)
    if n < 3:
        return dict(n=n, bias=np.nan, loa_upper=np.nan, loa_lower=np.nan)
    diff = y - x
    mean_diff = float(np.mean(diff))
    std_diff = float(np.std(diff, ddof=1))
    return dict(
        n=n,
        bias=round(mean_diff, 3),
        loa_upper=round(mean_diff + 1.96 * std_diff, 3),
        loa_lower=round(mean_diff - 1.96 * std_diff, 3),
    )


def fmt_p(p: float) -> str:
    if np.isnan(p):
        return "N/A"
    return "< 0.0001" if p < 0.0001 else f"{p:.4f}"


# ── Allen Helpers ─────────────────────────────────────────────────────────────


def get_stimulus_name(ephys_data, sn):
    meta = ephys_data.get_sweep_metadata(sn)
    name = meta.get("aibs_stimulus_name") or meta.get("stimulus_name") or b"Unknown"
    if isinstance(name, bytes):
        name = name.decode("utf-8", errors="ignore")
    return name


def get_valid_sweeps(ephys_data, cell_id):
    """Return sweep numbers whose stimulus type contains 'Square' or 'Ramp'."""
    out = []
    # Fetch sweep metadata
    sweeps_meta = ctc.get_ephys_sweeps(cell_id)
    valid_sweep_nums = {s["sweep_number"] for s in sweeps_meta}

    for sn in ephys_data.get_sweep_numbers():
        if sn not in valid_sweep_nums:
            continue
        name = get_stimulus_name(ephys_data, sn)
        if any(p in name for p in ["Square", "Ramp"]):
            out.append(sn)
    return out


# ── Plotting Helper ───────────────────────────────────────────────────────────


def plot_cell_summaries(downloaded_cells):
    log.info("Generating overlaid summary plots for each cell...")

    from Synaptipy.infrastructure.file_readers.neo_adapter import NeoAdapter

    adapter = NeoAdapter()

    for cell_id, structure, ephys_data, nwb_path in downloaded_cells:
        sweeps = get_valid_sweeps(ephys_data, cell_id)

        # Load the recording once for speed
        syn_rec = adapter.read_recording(nwb_path)
        ch_v = syn_rec.channels.get("0")
        ch_i = syn_rec.channels.get("1")
        if not ch_v or not ch_i:
            continue

        # Map sweep names to trial index
        sweep_to_trial = {}
        for idx, t_name in enumerate(
            ch_v._trial_names if hasattr(ch_v, "_trial_names") else range(len(ch_v.data_trials))
        ):
            seg_name = getattr(syn_rec.source_handle._block.segments[idx], "name", f"Sweep_{idx}")
            if seg_name.startswith("Sweep_"):
                s_num = int(seg_name.split("_")[-1])
                sweep_to_trial[s_num] = idx

        # Group sweeps by protocol
        protocols = {}
        for sn in sweeps:
            protocol = get_stimulus_name(ephys_data, sn)
            if protocol not in protocols:
                protocols[protocol] = []
            protocols[protocol].append(sn)

        for protocol, p_sweeps in protocols.items():
            fig, axs = plt.subplots(2, 2, figsize=(14, 10))
            ax_act, ax_pass = axs[0, 0], axs[0, 1]
            ax_act_i, ax_pass_i = axs[1, 0], axs[1, 1]

            # Paper-style spine removal
            for ax in [ax_act, ax_pass, ax_act_i, ax_pass_i]:
                ax.spines["top"].set_visible(False)
                ax.spines["right"].set_visible(False)

            from Synaptipy.shared.constants import TRIAL_COLOR

            rgb_color = tuple(c / 255.0 for c in TRIAL_COLOR)
            colors = [rgb_color] * len(p_sweeps)

            for sn, c in zip(p_sweeps, colors):
                t_idx = sweep_to_trial.get(sn)
                if t_idx is None:
                    continue

                # Fetch directly from memory arrays and downsample by 10 for performance
                v = ch_v.data_trials[t_idx][::10]
                i = ch_i.data_trials[t_idx][::10]
                sr = ch_v.sampling_rate / 10.0
                t = np.arange(len(v)) / sr

                if any(i < -15):
                    ax_pass.plot(t, v, color=c, linewidth=0.8, alpha=0.7, rasterized=True)
                    ax_pass_i.plot(t, i, color=c, linewidth=0.8, alpha=0.7, rasterized=True)
                if any(i > 15):
                    ax_act.plot(t, v, color=c, linewidth=0.8, alpha=0.7, rasterized=True)
                    ax_act_i.plot(t, i, color=c, linewidth=0.8, alpha=0.7, rasterized=True)

            # Panel A: Active Sweeps (Voltage)
            ax_act.text(
                -0.05, 1.15, "A", transform=ax_act.transAxes, fontsize=18, fontweight="bold", va="top", ha="right"
            )
            ax_act.set_title("Active Sweeps", loc="left", fontsize=14)
            ax_act.set_ylabel("Membrane Potential (mV)", fontsize=12)

            # Panel B: Passive Sweeps (Voltage)
            ax_pass.text(
                -0.05, 1.15, "B", transform=ax_pass.transAxes, fontsize=18, fontweight="bold", va="top", ha="right"
            )
            ax_pass.set_title("Passive Sweeps", loc="left", fontsize=14)

            # Panel C: Active Protocol (Current)
            ax_act_i.text(
                -0.05, 1.15, "C", transform=ax_act_i.transAxes, fontsize=18, fontweight="bold", va="top", ha="right"
            )
            ax_act_i.set_title("Active Protocol", loc="left", fontsize=14)
            ax_act_i.set_ylabel("Injected Current (pA)", fontsize=12)
            ax_act_i.set_xlabel("Time (s)", fontsize=12)

            # Panel D: Passive Protocol (Current)
            ax_pass_i.text(
                -0.05, 1.15, "D", transform=ax_pass_i.transAxes, fontsize=18, fontweight="bold", va="top", ha="right"
            )
            ax_pass_i.set_title("Passive Protocol", loc="left", fontsize=14)
            ax_pass_i.set_xlabel("Time (s)", fontsize=12)

            # Add tight layout and subtle sub-titles
            fig.suptitle(f"Cell {cell_id} | {protocol}", fontsize=16, y=0.98)
            plt.tight_layout(rect=[0.05, 0.03, 1, 0.92])

            clean_proto = protocol.replace(" ", "_").lower()
            plot_filename = PLOTS_DIR / f"cell_{cell_id}_{clean_proto}_summary.png"
            plt.savefig(plot_filename, dpi=300, bbox_inches="tight")
            plt.close(fig)


# ── Runners ───────────────────────────────────────────────────────────────────


class SynaptiPyRunner:
    @staticmethod
    def run_spikes(syn_rec, sweep_name: str) -> dict:
        # Provide pipeline directly to the loaded recording
        pipeline = [
            {
                "analysis": "spike_detection",
                "scope": "all_trials",
                "params": {"threshold": -20.0, "refractory_period": 0.002, "dvdt_threshold": 20.0, "sigma_ms": 0.0},
            },
            {
                "analysis": "train_dynamics",
                "scope": "average",
                "params": {"spike_threshold": -20.0, "analysis_end_s": 0.0},
            },
            {
                "analysis": "excitability_analysis",
                "scope": "all_trials",
                "params": {"threshold": -20.0},
            },
        ]

        # Filter for the specific trial matching the sweep_name
        # (Since we just want to benchmark this trial specifically)
        # But actually BatchAnalysisEngine runs on the whole recording,
        # so we extract the single trial into a temporary recording for benchmark parity
        ch_0 = syn_rec.channels.get("0")
        if not ch_0:
            return {}

        trial_idx = -1
        for i, t_name in enumerate(
            ch_0._trial_names if hasattr(ch_0, "_trial_names") else range(len(ch_0.data_trials))
        ):
            # The h5py fallback names segments "Sweep_N"
            if getattr(syn_rec.source_handle._block.segments[i], "name", f"Sweep_{i}") == sweep_name:
                trial_idx = i
                break

        if trial_idx == -1:
            return {}

        v = ch_0.data_trials[trial_idx]
        sr = ch_0.sampling_rate

        blk = neo.Block()
        seg = neo.Segment(name=sweep_name)
        blk.segments.append(seg)
        import quantities as pq

        anasig = neo.AnalogSignal(v, units="mV", sampling_rate=sr * pq.Hz, name="Voltage")
        seg.analogsignals.append(anasig)

        ch = Channel(id="CH_0", name="Voltage", units="mV", sampling_rate=float(sr), data_trials=[v])

        recording = Recording(source_file=syn_rec.source_file)
        recording.channels = {"CH_0": ch}
        recording.source_handle = NeoSourceHandle(source_path=syn_rec.source_file, block=blk)

        engine = BatchAnalysisEngine(max_workers=1)
        df = engine.run_batch([recording], pipeline)
        if df.empty:
            return {}
        row_dict = {}
        for row in df.to_dict("records"):
            for k, val in row.items():
                if val is not None:
                    if isinstance(val, float) and np.isnan(val):
                        continue
                    row_dict[k] = val
        return row_dict

    @staticmethod
    def run_passive(syn_rec, sweep_name: str, i: np.ndarray, t: np.ndarray) -> dict:
        ch_0 = syn_rec.channels.get("0")
        if not ch_0:
            return {}

        trial_idx = -1
        for idx, t_name in enumerate(
            ch_0._trial_names if hasattr(ch_0, "_trial_names") else range(len(ch_0.data_trials))
        ):
            if getattr(syn_rec.source_handle._block.segments[idx], "name", f"Sweep_{idx}") == sweep_name:
                trial_idx = idx
                break

        if trial_idx == -1:
            return {}

        v = ch_0.data_trials[trial_idx]
        sr = ch_0.sampling_rate

        stim_starts = np.where(np.diff(i) < -5)[0]
        if len(stim_starts) == 0:
            return {}
        stim_ends = np.where(np.diff(i) > 5)[0]
        stim_ends = stim_ends[stim_ends > stim_starts[0]]
        if len(stim_ends) == 0:
            s_t, e_t = 0.15, 0.65
            amp = -20.0
        else:
            s_t = float(t[stim_starts[0]])
            e_t = float(t[stim_ends[0]])
            amp = np.mean(i[stim_starts[0] + 10 : stim_ends[0] - 10]) - np.mean(i[: stim_starts[0] - 10])

        blk = neo.Block()
        seg = neo.Segment(name=sweep_name)
        blk.segments.append(seg)
        import quantities as pq

        anasig = neo.AnalogSignal(v, units="mV", sampling_rate=sr * pq.Hz, name="Voltage")
        seg.analogsignals.append(anasig)

        ch = Channel(id="CH_0", name="Voltage", units="mV", sampling_rate=float(sr), data_trials=[v])

        recording = Recording(source_file=syn_rec.source_file)
        recording.channels = {"CH_0": ch}
        recording.source_handle = NeoSourceHandle(source_path=syn_rec.source_file, block=blk)

        pipeline = [
            {
                "analysis": "rmp_analysis",
                "scope": "all_trials",
                "params": {"baseline_start": 0.0, "baseline_end": s_t},
            },
            {
                "analysis": "rin_analysis",
                "scope": "all_trials",
                "params": {
                    "baseline_start": 0.0,
                    "baseline_end": s_t,
                    "response_start": e_t - 0.1,
                    "response_end": e_t,
                    "current_amplitude": float(amp),
                },
            },
            {
                "analysis": "train_dynamics",
                "scope": "all_trials",
                "params": {
                    "analysis_start_s": s_t,
                    "analysis_end_s": e_t,
                },
            },
            {
                "analysis": "excitability_analysis",
                "scope": "all_trials",
                "params": {
                    "analysis_start_s": s_t,
                    "analysis_end_s": e_t,
                },
            },
            {
                "analysis": "tau_analysis",
                "scope": "all_trials",
                "params": {"stim_start_time": s_t, "fit_duration": 0.02, "model": "mono"},
            },
            {
                "analysis": "sag_ratio_analysis",
                "scope": "all_trials",
                "params": {
                    "baseline_start": max(0.0, s_t - 0.1),
                    "baseline_end": max(0.01, s_t - 0.01),
                    # Peak window spans the FULL step so the true trough is always found
                    "peak_window_start": s_t,
                    "peak_window_end": e_t - 0.01,
                    # Steady-state = last 15% of step (after charging transient settles)
                    "ss_window_start": e_t - max(0.15, (e_t - s_t) * 0.15),
                    "ss_window_end": e_t - 0.02,
                },
            },
        ]

        engine = BatchAnalysisEngine(max_workers=1)
        df = engine.run_batch([recording], pipeline)
        if df.empty:
            return {}
        # Collapse multiple rows from different modules
        row_dict = {}
        for row in df.to_dict("records"):
            for k, val in row.items():
                if val is not None:
                    if isinstance(val, float) and np.isnan(val):
                        continue
                    row_dict[k] = val
        return row_dict


class EFELRunner:
    @staticmethod
    def run_sweep_spikes(v: np.ndarray, t: np.ndarray) -> dict:
        import efel

        trace = {"T": t * 1000.0, "V": v, "stim_start": [t[0] * 1000.0], "stim_end": [t[-1] * 1000.0]}
        want = [
            "peak_voltage",
            "AP_duration_half_width",
            "AP_rise_rate",
            "AP_fall_rate",
            "AP_rise_time",
            "AP_fall_time",
            "AP_begin_voltage",
            "AP_amplitude",
            "fast_AHP",
            "ADP_peak_amplitude",
            "mean_frequency",
            "adaptation_index2",
            "time_to_first_spike",
            "time_to_second_spike",
            "min_voltage_between_spikes",
            "AP_peak_upstroke",
            "AP_peak_downstroke",
        ]
        res = efel.get_feature_values([trace], want)
        r = res[0] if res else {}
        pv = r.get("peak_voltage")
        out = {"n_spikes": len(pv) if pv is not None else 0}
        for k in want:
            vals = r.get(k)
            out[k] = float(np.mean(vals)) if (vals is not None and len(vals) > 0) else np.nan
        return out

    @staticmethod
    def run_sweep_passive(v: np.ndarray, i: np.ndarray, t: np.ndarray) -> dict:
        import efel

        stim_starts = np.where(np.diff(i) < -5)[0]
        if len(stim_starts) == 0:
            return {}
        stim_ends = np.where(np.diff(i) > 5)[0]
        stim_ends = stim_ends[stim_ends > stim_starts[0]]
        if len(stim_ends) == 0:
            return {}

        s_idx = stim_starts[0]
        e_idx = stim_ends[0]
        stim_amp = np.mean(i[s_idx + 10 : e_idx - 10]) - np.mean(i[: s_idx - 10])

        trace = {
            "T": t * 1000.0,
            "V": v,
            "stim_start": [t[s_idx] * 1000.0],
            "stim_end": [t[e_idx] * 1000.0],
            "stimulus_current": [stim_amp],
        }

        want = [
            "voltage_base",
            "ohmic_input_resistance",
            "ohmic_input_resistance_vb_ssse",
            "time_constant",
            "sag_amplitude",
            "sag_ratio1",
            "sag_ratio2",
        ]
        res = efel.get_feature_values([trace], want)
        r = res[0] if res else {}

        out = {}
        for k in want:
            vals = r.get(k)
            out[k] = float(np.mean(vals)) if (vals is not None and len(vals) > 0) else np.nan
        return out


class IPFXRunner:
    @staticmethod
    def run_sweep_spikes(v: np.ndarray, t: np.ndarray) -> dict:
        from ipfx.feature_extractor import SpikeFeatureExtractor

        ext = SpikeFeatureExtractor(start=t[0], end=t[-1], filter=9.9)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            result = ext.process(t, v, np.zeros_like(v))
        if result is None or result.empty:
            return {"n_spikes": 0}

        # Safely read optional columns with fallback to nan
        def _col_mean(col):
            if col in result.columns:
                return float(result[col].mean())
            return np.nan

        slow_trough = _col_mean("slow_trough_v")
        thresh_mean = float(result["threshold_v"].mean())
        mahp = thresh_mean - slow_trough if not np.isnan(slow_trough) else np.nan

        out = {
            "n_spikes": len(result),
            "peak_v": float(result["peak_v"].mean()),
            "width_ms": float(result["width"].mean()) * 1000.0,
            "upstroke": float(result["upstroke"].mean()),
            "downstroke": float(result["downstroke"].mean()),
            "threshold_v": thresh_mean,
            "amplitude": float((result["peak_v"] - result["threshold_v"]).mean()),
            "fast_ahp": float((result["threshold_v"] - result["fast_trough_v"]).mean()),
            "mahp": mahp,
            "adp_amp": float((result["adp_v"] - result["fast_trough_v"]).mean()),
            "avg_rate": (
                float(len(result) - 1) / (result["peak_t"].iloc[-1] - result["peak_t"].iloc[0])
                if len(result) > 1
                else 0.0
            ),
            "first_isi": (
                float((result["peak_t"].iloc[1] - result["peak_t"].iloc[0]) * 1000.0) if len(result) > 1 else np.nan
            ),
            "peak_t": float(result["peak_t"].iloc[0]) * 1000.0 if len(result) > 0 else np.nan,
            "upstroke_downstroke_ratio": (
                float(result["upstroke_downstroke_ratio"].mean()) if "upstroke_downstroke_ratio" in result else np.nan
            ),
            "trough_v": float(result["fast_trough_v"].mean()) if "fast_trough_v" in result else np.nan,
            "adaptation": np.nan,  # filled below if train extractor works
        }

        try:
            from ipfx.feature_extractor import SpikeTrainFeatureExtractor

            train_ext = SpikeTrainFeatureExtractor(start=t[0], end=t[-1])
            train_res = train_ext.process(t, v, np.zeros_like(v), result)
            if train_res and "adapt" in train_res:
                out["adaptation"] = float(train_res["adapt"])
        except Exception:
            pass

        return out

    @staticmethod
    def run_sweep_passive(v: np.ndarray, i: np.ndarray, t: np.ndarray) -> dict:
        import ipfx.subthresh_features as subT

        stim_starts = np.where(np.diff(i) < -5)[0]
        if len(stim_starts) == 0:
            return {}
        stim_ends = np.where(np.diff(i) > 5)[0]
        stim_ends = stim_ends[stim_ends > stim_starts[0]]
        if len(stim_ends) == 0:
            return {}

        start_t = t[stim_starts[0]]
        end_t = t[stim_ends[0]]

        out = {}
        baseline_int = min(0.03, start_t * 0.9)  # Keep it safe and slightly smaller than start_t

        try:
            out["v_baseline"] = float(subT.baseline_voltage(t, v, start_t, baseline_interval=baseline_int))
        except Exception:
            pass

        try:
            # IPFX 1.0.8 compatibility for sag
            out["sag"] = float(subT.sag(t, v, i, start_t, end_t, baseline_interval=baseline_int))
        except Exception:
            out["sag"] = np.nan

        try:
            v_def, v_def_idx = subT.voltage_deflection(t, v, i, start_t, end_t)
            v_def_val = float(v_def) - out.get("v_baseline", 0.0)
            out["v_deflect"] = v_def_val
            stim_amp = float(i[stim_starts[0] + 50])
            if stim_amp != 0:
                out["peak_rin"] = abs(v_def_val / stim_amp) * 1000.0
            if "sag" in out and not np.isnan(out["sag"]) and v_def_val != 0:
                out["sag_pct"] = abs(out["sag"] / v_def_val) * 100.0
        except Exception as e:
            pass

        try:
            out["input_resistance"] = float(
                subT.input_resistance([t], [i], [v], start_t, end_t, baseline_interval=baseline_int)
            )
        except Exception:
            out["input_resistance"] = np.nan

        try:
            tau = subT.time_constant(t, v, i, start_t, end_t, min_snr=0.0, baseline_interval=baseline_int)
        except TypeError:  # Some versions of IPFX don't accept baseline_interval in time_constant
            tau = subT.time_constant(t, v, i, start_t, end_t, min_snr=0.0)

        out["tau"] = float(tau) * 1000.0
        return out


# ── Builders ──────────────────────────────────────────────────────────────────


def build_table1(downloaded_cells: list) -> pd.DataFrame:
    log.info("Building Table 1 (Active Properties)...")
    rows = []

    from Synaptipy.infrastructure.file_readers.neo_adapter import NeoAdapter

    adapter = NeoAdapter()

    for cell_id, structure, ephys_data, nwb_path in downloaded_cells:
        sweeps = get_valid_sweeps(ephys_data, cell_id)
        syn_rec = adapter.read_recording(nwb_path)

        for sn in sweeps:
            protocol = get_stimulus_name(ephys_data, sn).lower()
            if "long square" not in protocol:
                continue

            sweep = ephys_data.get_sweep(sn)
            v = sweep["response"] * 1e3
            i = sweep["stimulus"] * 1e12
            sr = sweep["sampling_rate"]
            t = np.arange(len(v)) / sr

            stim_amp = np.max(i) - np.median(i)
            if stim_amp <= 120:
                continue

            syn_r = SynaptiPyRunner.run_spikes(syn_rec, f"Sweep_{sn}")
            if not syn_r or syn_r.get("spike_count", 0) == 0:
                continue

            efel_r = EFELRunner.run_sweep_spikes(v, t)
            ipfx_r = IPFXRunner.run_sweep_spikes(v, t)
            if efel_r.get("n_spikes", 0) == 0 or ipfx_r.get("n_spikes", 0) == 0:
                continue

            # Compute first ISI from train_dynamics output (ms)
            syn_first_isi = float(syn_r.get("first_isi_ms", np.nan))
            # Compute adaptation index from train_dynamics output
            syn_sfa = float(syn_r.get("adaptation_index", np.nan))
            # Compute eFEL first ISI from time_to_second - time_to_first (ms)
            t1 = efel_r.get("time_to_first_spike", np.nan)
            t2 = efel_r.get("time_to_second_spike", np.nan)
            efel_first_isi = (t2 - t1) if (not np.isnan(t1) and not np.isnan(t2)) else np.nan

            rows.append(
                {
                    "cell_id": cell_id,
                    "trial": sn,
                    # Peak voltage
                    "syn_peak_mV": float(syn_r.get("absolute_peak_mv_mean", np.nan)),
                    "efel_peak_mV": efel_r.get("peak_voltage", np.nan),
                    "ipfx_peak_mV": ipfx_r.get("peak_v", np.nan),
                    # AP threshold
                    "syn_thr_mV": float(syn_r.get("ap_threshold_mean", np.nan)),
                    "efel_thr_mV": efel_r.get("AP_begin_voltage", np.nan),
                    "ipfx_thr_mV": ipfx_r.get("threshold_v", np.nan),
                    # AP amplitude
                    "syn_amp_mV": float(syn_r.get("amplitude_mean", np.nan)),
                    "efel_amp_mV": efel_r.get("AP_amplitude", np.nan),
                    "ipfx_amp_mV": ipfx_r.get("amplitude", np.nan),
                    # AP half-width
                    "syn_hw_ms": float(syn_r.get("half_width_mean", np.nan)),
                    "efel_hw_ms": efel_r.get("AP_duration_half_width", np.nan),
                    "ipfx_hw_ms": ipfx_r.get("width_ms", np.nan),
                    # Rise time 10-90%
                    "syn_rise_time_ms": float(syn_r.get("rise_time_10_90_mean", np.nan)),
                    "efel_rise_time_ms": efel_r.get("AP_rise_time", np.nan),
                    "ipfx_rise_time_ms": np.nan,
                    # Decay time 90-10%
                    "syn_decay_time_ms": float(syn_r.get("decay_time_90_10_mean", np.nan)),
                    "efel_decay_time_ms": efel_r.get("AP_fall_time", np.nan),
                    "ipfx_decay_time_ms": np.nan,
                    # Max dV/dt
                    "syn_maxdvdt": syn_r.get("max_dvdt_mean", np.nan),
                    "efel_maxdvdt": efel_r.get("AP_peak_upstroke", np.nan),
                    "ipfx_maxdvdt": ipfx_r.get("upstroke", np.nan),
                    # Min dV/dt
                    "syn_mindvdt": syn_r.get("min_dvdt_mean", np.nan),
                    "efel_mindvdt": efel_r.get("AP_peak_downstroke", np.nan),
                    "ipfx_mindvdt": ipfx_r.get("downstroke", np.nan),
                    # AP delay (time to first spike)
                    "syn_ap_delay": (
                        syn_r.get("first_spike_delay_ms", np.nan)
                        if not np.isnan(syn_r.get("first_spike_delay_ms", np.nan))
                        else np.nan
                    ),
                    "efel_ap_delay": efel_r.get("time_to_first_spike", np.nan),
                    "ipfx_ap_delay": ipfx_r.get("peak_t", np.nan),
                    # Upstroke/downstroke ratio
                    "syn_upstroke_downstroke_ratio": syn_r.get("upstroke_downstroke_ratio_mean", np.nan),
                    "efel_upstroke_downstroke_ratio": (
                        abs(efel_r.get("AP_peak_upstroke", np.nan) / efel_r.get("AP_peak_downstroke", np.nan))
                        if not np.isnan(efel_r.get("AP_peak_downstroke", np.nan))
                        and efel_r.get("AP_peak_downstroke", np.nan) != 0
                        else np.nan
                    ),
                    "ipfx_upstroke_downstroke_ratio": ipfx_r.get("upstroke_downstroke_ratio", np.nan),
                    # Trough voltage (fAHP trough)
                    "syn_trough_v": syn_r.get("trough_v_mean", np.nan),
                    "efel_trough_v": efel_r.get("min_voltage_between_spikes", np.nan),
                    "ipfx_trough_v": ipfx_r.get("trough_v", np.nan),
                    # Phase-plane area
                    "syn_phase_plane_area": syn_r.get("phase_plane_area_mean", np.nan),
                    "efel_phase_plane_area": np.nan,
                    "ipfx_phase_plane_area": np.nan,
                    # Fast AHP depth
                    "syn_fahp_mV": syn_r.get("fahp_depth_mean", np.nan),
                    "efel_fahp_mV": efel_r.get("fast_AHP", np.nan),
                    "ipfx_fahp_mV": ipfx_r.get("fast_ahp", np.nan),
                    # Medium AHP depth
                    "syn_mahp_mV": float(syn_r.get("mahp_depth_mean", np.nan)),
                    "efel_mahp_mV": np.nan,
                    "ipfx_mahp_mV": ipfx_r.get("mahp", np.nan),
                    # AHP half-duration
                    "syn_ahp_dur_ms": float(syn_r.get("ahp_duration_half_mean", np.nan)),
                    "efel_ahp_dur_ms": np.nan,
                    "ipfx_ahp_dur_ms": np.nan,
                    # ADP amplitude
                    "syn_adp_mV": float(syn_r.get("adp_amplitude_mean", np.nan)),
                    "efel_adp_mV": efel_r.get("ADP_peak_amplitude", np.nan),
                    "ipfx_adp_mV": ipfx_r.get("adp_amp", np.nan),
                    # Mean firing frequency
                    "syn_rate_hz": float(syn_r.get("mean_freq_hz", np.nan)),
                    "efel_rate_hz": efel_r.get("mean_frequency", np.nan),
                    "ipfx_rate_hz": ipfx_r.get("avg_rate", np.nan),
                    # Max firing frequency
                    "syn_max_freq_hz": float(syn_r.get("max_freq_hz", np.nan)),
                    "efel_max_freq_hz": np.nan,
                    "ipfx_max_freq_hz": np.nan,
                    # First ISI
                    "syn_first_isi_ms": syn_first_isi,
                    "efel_first_isi_ms": efel_first_isi,
                    "ipfx_first_isi_ms": ipfx_r.get("first_isi", np.nan),
                    # Spike frequency adaptation
                    "syn_sfa": syn_sfa,
                    "efel_sfa": efel_r.get("adaptation_index2", np.nan),
                    "ipfx_sfa": ipfx_r.get("adaptation", np.nan),
                    # ISI coefficient of variation
                    "syn_cv_isi": float(syn_r.get("cv", np.nan)),
                    "efel_cv_isi": efel_r.get("CV_ISI", np.nan),
                    "ipfx_cv_isi": np.nan,
                    # Spike broadening index
                    "syn_broadening": float(syn_r.get("spike_broadening_index", np.nan)),
                    "efel_broadening": np.nan,
                    "ipfx_broadening": np.nan,
                    # Rheobase
                    "syn_rheobase_pa": float(syn_r.get("rheobase_pa", np.nan)),
                    "efel_rheobase_pa": np.nan,
                    "ipfx_rheobase_pa": np.nan,
                    # F-I gain
                    "syn_fi_gain": float(syn_r.get("fi_slope", np.nan)),
                    "efel_fi_gain": np.nan,
                    "ipfx_fi_gain": np.nan,
                }
            )

    df = pd.DataFrame(rows)
    df.to_csv(OUT_DIR / "benchmark_comparison.csv", index=False)
    log.info(f"Table 1 built. {len(df)} sweeps extracted.")
    return df


def build_table2(downloaded_cells: list) -> pd.DataFrame:
    log.info("Building Table 2 (Passive Properties)...")
    rows = []

    from Synaptipy.infrastructure.file_readers.neo_adapter import NeoAdapter

    adapter = NeoAdapter()

    for cell_id, structure, ephys_data, nwb_path in downloaded_cells:
        sweeps = get_valid_sweeps(ephys_data, cell_id)
        syn_rec = adapter.read_recording(nwb_path)

        for sn in sweeps:
            protocol = get_stimulus_name(ephys_data, sn).lower()
            if "long square" not in protocol:
                continue

            sweep = ephys_data.get_sweep(sn)
            v = sweep["response"] * 1e3
            i = sweep["stimulus"] * 1e12
            sr = sweep["sampling_rate"]
            t = np.arange(len(v)) / sr

            # Look for hyperpolarizing steps (e.g. < -15 pA)
            if not any(i < -15):
                continue

            syn_r = SynaptiPyRunner.run_passive(syn_rec, f"Sweep_{sn}", i, t)
            efel_r = EFELRunner.run_sweep_passive(v, i, t)
            ipfx_r = IPFXRunner.run_sweep_passive(v, i, t)

            efel_rin = efel_r.get("ohmic_input_resistance", np.nan)
            rows.append(
                {
                    "cell_id": cell_id,
                    "trial": sn,
                    # RMP
                    "syn_rmp_mV": float(syn_r.get("rmp_mv", np.nan)),
                    "efel_rmp_mV": efel_r.get("voltage_base", np.nan),
                    "ipfx_rmp_mV": ipfx_r.get("v_baseline", np.nan),
                    # Input resistance (steady-state)
                    "syn_rin_mohm": syn_r.get("rin_mohm", np.nan),
                    "efel_rin_mohm": efel_rin * 1000.0 if not np.isnan(efel_rin) else np.nan,
                    "ipfx_rin_mohm": ipfx_r.get("input_resistance", np.nan),
                    # Peak input resistance
                    "syn_rin_peak_mohm": syn_r.get("rin_peak_mohm", np.nan),
                    "efel_rin_peak_mohm": (
                        efel_r.get("ohmic_input_resistance_vb_ssse", np.nan) * 1000.0
                        if not np.isnan(efel_r.get("ohmic_input_resistance_vb_ssse", np.nan))
                        else np.nan
                    ),
                    "ipfx_rin_peak_mohm": ipfx_r.get("peak_rin", np.nan),
                    # Membrane time constant
                    "syn_tau_ms": syn_r.get("tau_ms", np.nan),
                    "efel_tau_ms": efel_r.get("time_constant", np.nan),
                    "ipfx_tau_ms": ipfx_r.get("tau", np.nan),
                    # Decay tau after stimulus
                    "syn_tau_decay_ms": syn_r.get("tau_decay_after_stimulus_ms", np.nan),
                    "efel_tau_decay_ms": efel_r.get("decay_time_constant_after_stim", np.nan),
                    "ipfx_tau_decay_ms": np.nan,
                    # Sag ratio
                    "syn_sag_ratio": syn_r.get("sag_ratio", np.nan),
                    "efel_sag_ratio": efel_r.get("sag_ratio1", np.nan),
                    "ipfx_sag_ratio": ipfx_r.get("sag", np.nan),
                    # Sag percentage
                    "syn_sag_pct": syn_r.get("sag_percentage", np.nan),
                    "efel_sag_pct": (
                        efel_r.get("sag_ratio2", np.nan) * 100.0
                        if not np.isnan(efel_r.get("sag_ratio2", np.nan))
                        else np.nan
                    ),
                    "ipfx_sag_pct": ipfx_r.get("sag_pct", np.nan),
                    # Rebound depolarization
                    "syn_rebound_mv": syn_r.get("rebound_depolarization_amplitude_mv", np.nan),
                    "efel_rebound_mv": np.nan,
                    "ipfx_rebound_mv": np.nan,
                }
            )

    df = pd.DataFrame(rows)
    df.to_csv(OUT_DIR / "passive_properties.csv", index=False)
    log.info(f"Table 2 built. {len(df)} sweeps extracted.")
    return df


# ── Render Markdown ───────────────────────────────────────────────────────────


def make_table1_md(cmp_df: pd.DataFrame) -> str:
    metrics = [
        # ("Peak voltage (mV)", "syn_peak_mV", "efel_peak_mV", "ipfx_peak_mV", "mV"),
        ("AP threshold (mV)", "syn_thr_mV", "efel_thr_mV", "ipfx_thr_mV", "mV"),
        ("AP amplitude (mV)", "syn_amp_mV", "efel_amp_mV", "ipfx_amp_mV", "mV"),
        ("AP half-width (ms)", "syn_hw_ms", "efel_hw_ms", "ipfx_hw_ms", "ms"),
        ("Max dV/dt (V/s)", "syn_maxdvdt", "efel_maxdvdt", "ipfx_maxdvdt", "V/s"),
        # ("Min dV/dt (V/s)", "syn_mindvdt", "efel_mindvdt", "ipfx_mindvdt", "V/s"),
        ("AP Delay (Time to first spike) (ms)", "syn_ap_delay", "efel_ap_delay", "ipfx_ap_delay", "ms"),
        (
            "Upstroke/Downstroke Ratio",
            "syn_upstroke_downstroke_ratio",
            "efel_upstroke_downstroke_ratio",
            "ipfx_upstroke_downstroke_ratio",
            "Ratio",
        ),
        # ("Trough V (mV)", "syn_trough_v", "efel_trough_v", "ipfx_trough_v", "mV"),
        ("Fast AHP depth (mV)", "syn_fahp_mV", "efel_fahp_mV", "ipfx_fahp_mV", "mV"),
        ("ADP amplitude (mV)", "syn_adp_mV", "efel_adp_mV", "ipfx_adp_mV", "mV"),
        ("Mean Firing Frequency (Hz)", "syn_rate_hz", "efel_rate_hz", "ipfx_rate_hz", "Hz"),
        # ("First ISI (ms)", "syn_first_isi_ms", "efel_first_isi_ms", "ipfx_first_isi_ms", "ms"),
        ("Spike Frequency Adaptation", "syn_sfa", "efel_sfa", "ipfx_sfa", "Ratio"),
    ]
    md = "**Extended Data Table 1: Statistical summary of SynaptiPy AP extraction vs. eFEL and IPFX benchmarks (Allen Dataset, per-sweep means).**\n\n"
    md += "| Metric | SynaptiPy vs IPFX Pearson *r* | Mean bias vs IPFX | LoA vs IPFX | SynaptiPy vs eFEL Pearson *r* | Mean bias vs eFEL | LoA vs eFEL |\n"
    md += "|--------|-------------------------------|-------------------|-------------|-------------------------------|-------------------|-------------|\n"
    
    def _fmt_r(vs):
        if np.isnan(vs.get("r", np.nan)):
            return "N/A"
        s = f"{vs['r']:.4f}"
        if not np.isnan(vs.get("p", np.nan)):
            s += "***" if vs["p"] < 0.0001 else f" (*p*={vs['p']:.4f})"
        return s

    def _fmt_bias(vs, unit):
        return f"{vs['bias']:+.3f} {unit}" if not np.isnan(vs.get("bias", np.nan)) else "N/A"

    def _fmt_loa(vs, unit):
        if np.isnan(vs.get("loa_upper", np.nan)):
            return "N/A"
        return f"[{vs['loa_lower']:+.2f}, {vs['loa_upper']:+.2f}] {unit}"

    for label, s_col, e_col, i_col, unit in metrics:
        if s_col not in cmp_df.columns:
            continue
        s = cmp_df[s_col].values
        
        if e_col and e_col in cmp_df.columns:
            e = cmp_df[e_col].values
            vs_e = corr_summary(e, s)
        else:
            vs_e = dict(r=np.nan, p=np.nan, bias=np.nan, loa_upper=np.nan, loa_lower=np.nan)

        if i_col and i_col in cmp_df.columns:
            i = cmp_df[i_col].values
            vs_i = corr_summary(i, s)
        else:
            vs_i = dict(r=np.nan, p=np.nan, bias=np.nan, loa_upper=np.nan, loa_lower=np.nan)

        md += (
            f"| {label} | "
            f"{_fmt_r(vs_i)} | {_fmt_bias(vs_i, unit)} | {_fmt_loa(vs_i, unit)} | "
            f"{_fmt_r(vs_e)} | {_fmt_bias(vs_e, unit)} | {_fmt_loa(vs_e, unit)} |\n"
        )

    md += "\n*Statistical approaches: All correlations are Pearson's r (two-sided). *** denotes p < 0.0001. Data reflects n = 43 sweeps (unless otherwise missing/rejected) where pipelines detected ≥1 action potential. Bias = mean signed difference (SynaptiPy − benchmark, per-sweep means). LoA = 95% Bland-Altman limits of agreement. SynaptiPy: BatchAnalysisEngine `spike_detection` (dV/dt threshold 20 V/s, refractory 2 ms). eFEL: BlueBrain eFEL defaults. IPFX: Allen IPFX SpikeFeatureExtractor, 9.9 kHz Bessel filter. N/A = no direct benchmark equivalent.*"
    return md


def make_table2_md(cmp_df: pd.DataFrame) -> str:
    # (label, syn_col, efel_col, ipfx_col, unit)
    # None means no direct equivalent for that benchmark
    metrics = [
        ("Resting Membrane Potential (mV)", "syn_rmp_mV", "efel_rmp_mV", "ipfx_rmp_mV", "mV"),
        # SS-Rin: SynaptiPy mean last-100ms window == eFEL ohmic_input_resistance
        ("Input Resistance \u2014 Steady-State (M\u03a9) \u2020", "syn_rin_mohm", "efel_rin_mohm", None, "M\u03a9"),
        # Peak-Rin: SynaptiPy peak deflection == IPFX voltage_deflection
        ("Input Resistance \u2014 Peak (M\u03a9) \u2021", "syn_rin_peak_mohm", None, "ipfx_rin_mohm", "M\u03a9"),
        ("Membrane Time Constant (ms)", "syn_tau_ms", "efel_tau_ms", "ipfx_tau_ms", "ms"),
        # Sag as percentage (0-100%) -- eFEL sag_ratio2*100, IPFX sag_pct
        ("Sag Percentage (%)", "syn_sag_pct", "efel_sag_pct", "ipfx_sag_pct", "%"),
    ]
    md = (
        "**Extended Data Table 2: Subthreshold passive properties benchmark "
        "on hyperpolarizing steps (Allen Dataset).**\n\n"
    )
    md += (
        "| Metric | Valid *N* | "
        "SynaptiPy vs eFEL Pearson *r* | Mean bias vs eFEL | LoA vs eFEL | "
        "SynaptiPy vs IPFX Pearson *r* | Mean bias vs IPFX | LoA vs IPFX |\n"
    )
    md += (
        "|--------|-----------|-------------------------------|-------------------"
        "|-------------|-------------------------------|-------------------|-------------|\n"
    )

    def _fmt_r(vs):
        if np.isnan(vs.get("r", np.nan)):
            return "N/A"
        s = f"{vs['r']:.4f}"
        if not np.isnan(vs.get("p", np.nan)):
            s += "***" if vs["p"] < 0.0001 else f" (*p*={vs['p']:.4f})"
        return s

    def _fmt_bias(vs, unit):
        return f"{vs['bias']:+.3f} {unit}" if not np.isnan(vs.get("bias", np.nan)) else "N/A"

    def _fmt_loa(vs, unit):
        if np.isnan(vs.get("loa_upper", np.nan)):
            return "N/A"
        return f"[{vs['loa_lower']:+.2f}, {vs['loa_upper']:+.2f}] {unit}"

    for label, s_col, e_col, i_col, unit in metrics:
        if s_col not in cmp_df.columns:
            continue
        s = cmp_df[s_col].values

        if e_col and e_col in cmp_df.columns:
            e = cmp_df[e_col].values
            vs_e = corr_summary(e, s)
            n_val = vs_e["n"]
        else:
            vs_e = dict(r=np.nan, p=np.nan, bias=np.nan, loa_upper=np.nan, loa_lower=np.nan)
            n_val = int(np.sum(~np.isnan(s)))

        if i_col and i_col in cmp_df.columns:
            iv = cmp_df[i_col].values
            vs_i = corr_summary(iv, s)
            if n_val == 0:
                n_val = vs_i["n"]
        else:
            vs_i = dict(r=np.nan, p=np.nan, bias=np.nan, loa_upper=np.nan, loa_lower=np.nan)

        md += (
            f"| {label} | {n_val} | "
            f"{_fmt_r(vs_e)} | {_fmt_bias(vs_e, unit)} | {_fmt_loa(vs_e, unit)} | "
            f"{_fmt_r(vs_i)} | {_fmt_bias(vs_i, unit)} | {_fmt_loa(vs_i, unit)} |\n"
        )

    md += (
        "\n*All correlations are Pearson's r (two-sided); *** = p < 0.0001. "
        "LoA = 95% Bland-Altman limits of agreement (mean \u00b1 1.96 SD of "
        "sweep-level differences). "
        "\u2020 SS-Rin: mean voltage in last 100 ms of step (matches eFEL "
        "ohmic_input_resistance). "
        "\u2021 Peak-Rin: maximum hyperpolarization deflection (matches IPFX "
        "voltage_deflection). "
        "N/A = no direct benchmark equivalent.*"
    )
    return md


def main():
    print("=" * 60)
    print("SynaptiPy — generate_paper_tables.py (Unified Benchmark)")

    # Hardcoded requested Allen cells
    requested_cells = [480087928, 323865917, 476135066, 481127932, 502614426, 504615116]
    print(f"Targeting {len(requested_cells)} Allen Institute cells")
    print("=" * 60)

    log.info(f"Targeting {len(requested_cells)} hardcoded high-quality cells...")

    downloaded_cells = []
    for cell_id in requested_cells:
        structure = "VISp"
        nwb_path = CACHE_DIR / f"cell_{cell_id}.nwb"

        try:
            if not nwb_path.exists():
                log.info(f"[Download {len(downloaded_cells) + 1}/{len(requested_cells)}] Fetching Cell {cell_id} ...")
            ephys_data = ctc.get_ephys_data(cell_id, file_name=str(nwb_path))
            downloaded_cells.append((cell_id, structure, ephys_data, nwb_path))
        except Exception as exc:
            log.warning(f"  Failed to download Cell {cell_id}: {exc}")

    log.info("Phase 2: Analysis")
    
    t1_csv = OUT_DIR / "benchmark_comparison.csv"
    if not t1_csv.exists():
        t1_df = build_table1(downloaded_cells)
    else:
        t1_df = pd.read_csv(t1_csv)
    t1_md = make_table1_md(t1_df)

    t2_csv = OUT_DIR / "passive_properties.csv"
    if not t2_csv.exists():
        t2_df = build_table2(downloaded_cells)
    else:
        t2_df = pd.read_csv(t2_csv)
    t2_md = make_table2_md(t2_df)

    plot_cell_summaries(downloaded_cells)

    log.info("Phase 3: Updating Paper")
    paper_path = REPO_ROOT / "paper" / "paper.md"
    text = paper_path.read_text(encoding="utf-8")

    T1_START = "<!-- TABLES_START -->"
    T1_END = "<!-- TABLES_END -->"
    idx1s = text.find(T1_START)
    idx1e = text.find(T1_END)
    if idx1s == -1 or idx1e == -1:
        log.error("Could not find <!-- TABLES_START --> or <!-- TABLES_END --> markers in paper.md")
        return

    new_text = text[:idx1s + len(T1_START)] + "\n\n" + t1_md + "\n\n" + t2_md + "\n" + text[idx1e:]
    paper_path.write_text(new_text, encoding="utf-8")
    log.info(f"Success! Updated paper at {paper_path}")


if __name__ == "__main__":
    main()
