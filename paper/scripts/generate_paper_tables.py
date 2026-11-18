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
import json
import logging
import platform
import subprocess
import sys
import warnings
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import pearsonr, shapiro, spearmanr

# Fix for xarray/allensdk with NumPy 2.0+
if not hasattr(np, "unicode_"):
    np.unicode_ = np.str_
if not hasattr(np, "VisibleDeprecationWarning"):
    np.VisibleDeprecationWarning = UserWarning

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from synaptipy.core.analysis.batch_engine import BatchAnalysisEngine
from synaptipy.core.data_model import Channel, Recording
from synaptipy.infrastructure.file_readers.neo_source_handle import NeoSourceHandle

CACHE_DIR = REPO_ROOT / "paper" / "data" / "allen_cache"
OUT_DIR = REPO_ROOT / "paper" / "analysis_results"
PLOTS_DIR = REPO_ROOT / "paper" / "raw_nwb_plots"
DEFAULT_MANIFEST = REPO_ROOT / "paper" / "data_manifest.json"

OUT_DIR.mkdir(parents=True, exist_ok=True)
CACHE_DIR.mkdir(parents=True, exist_ok=True)
PLOTS_DIR.mkdir(parents=True, exist_ok=True)

# Patch numpy 2.0 breaking changes inside allensdk before heavy use
if not hasattr(np, "unicode_"):
    np.unicode_ = np.str_
if not hasattr(np, "VisibleDeprecationWarning"):
    np.VisibleDeprecationWarning = DeprecationWarning

# Created lazily in main(). This lets --help and --check-only run without
# installing the heavy paper-only AllenSDK/IPFX/eFEL stack.
ctc = None

TARGET_N = 10

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# -- Reproduction Metadata ----------------------------------------------------


def load_data_manifest(path: Path) -> dict:
    """Load and validate the paper dataset manifest."""
    manifest = json.loads(path.read_text(encoding="utf-8"))
    cells = manifest.get("cells", [])
    if not cells:
        raise ValueError(f"No cells listed in data manifest: {path}")
    missing = [c for c in cells if "cell_id" not in c]
    if missing:
        raise ValueError(f"Every manifest cell entry must include cell_id: {path}")
    return manifest


def _git_commit() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        return result.stdout.strip() if result.returncode == 0 else "unknown"
    except Exception:
        return "unknown"


def _package_version(name: str) -> str:
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return "not-installed"


def write_run_provenance(manifest: dict, args: argparse.Namespace, downloaded_cells: list) -> None:
    """Write a machine-readable provenance sidecar for regenerated paper tables."""
    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "git_commit": _git_commit(),
        "python": sys.version,
        "platform": platform.platform(),
        "arguments": {
            "manifest": str(args.manifest),
            "force": bool(args.force),
            "skip_plots": bool(args.skip_plots),
            "no_paper_update": bool(args.no_paper_update),
            "cache_dir": str(args.cache_dir),
            "output_dir": str(args.output_dir),
            "plots_dir": str(args.plots_dir),
        },
        "manifest": manifest,
        "downloaded_cell_ids": [int(cell_id) for cell_id, *_ in downloaded_cells],
        "versions": {
            "synaptipy": _package_version("synaptipy"),
            "numpy": np.__version__,
            "pandas": pd.__version__,
            "scipy": _package_version("scipy"),
            "matplotlib": _package_version("matplotlib"),
            "allensdk": _package_version("allensdk"),
            "efel": _package_version("efel"),
            "ipfx": _package_version("ipfx"),
        },
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "paper_tables_provenance.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")


# -- Stats Helpers ------------------------------------------------------------


def corr_summary(x: np.ndarray, y: np.ndarray) -> dict:
    mask = ~(np.isnan(x) | np.isnan(y))
    x, y = x[mask], y[mask]
    n = len(x)
    if n < 3:
        return dict(
            n=n,
            r=np.nan,
            p=np.nan,
            rho=np.nan,
            p_rho=np.nan,
            shapiro_w=np.nan,
            shapiro_p=np.nan,
            bias=np.nan,
            loa_upper=np.nan,
            loa_lower=np.nan,
        )
    r, p = pearsonr(x, y)
    rho, p_rho = spearmanr(x, y)
    diff = y - x
    mean_diff = float(np.mean(diff))
    std_diff = float(np.std(diff, ddof=1))
    if n >= 3 and std_diff > 1e-12:
        shapiro_w, shapiro_p = shapiro(diff[:5000])
    else:
        shapiro_w, shapiro_p = np.nan, np.nan
    return dict(
        n=n,
        r=round(float(r), 4),
        p=float(p),
        rho=round(float(rho), 4),
        p_rho=float(p_rho),
        shapiro_w=round(float(shapiro_w), 4) if not np.isnan(shapiro_w) else np.nan,
        shapiro_p=float(shapiro_p) if not np.isnan(shapiro_p) else np.nan,
        bias=round(mean_diff, 3),
        loa_upper=round(mean_diff + 1.96 * std_diff, 3),
        loa_lower=round(mean_diff - 1.96 * std_diff, 3),
    )


def detect_sustained_step(
    i: np.ndarray,
    t: np.ndarray,
    polarity: str = "negative",
    min_duration_s: float = 0.2,
    threshold_pa: float = 10.0,
):
    """Detect the primary sustained Long Square current step, ignoring brief pre-sweep test pulses.

    Returns (s_idx, e_idx, s_t, e_t, step_amp_pa) or None if no sustained step is found.
    """
    if len(i) < 20 or len(t) != len(i):
        return None

    n_pre = max(5, int(0.01 * len(i)))
    n_post = max(5, int(0.05 * len(i)))
    pre_post = np.concatenate([i[:n_pre], i[len(i) - n_post :]])
    baseline_i = float(np.median(pre_post))

    if polarity == "negative":
        active = (i - baseline_i) < -abs(threshold_pa)
    else:
        active = (i - baseline_i) > abs(threshold_pa)

    if not np.any(active):
        return None

    padded = np.concatenate(([False], active, [False]))
    edges = np.diff(padded.astype(int))
    starts = np.where(edges == 1)[0]
    ends = np.where(edges == -1)[0] - 1

    best = None
    best_dur = 0.0
    for s_idx, e_idx in zip(starts, ends):
        if e_idx <= s_idx:
            continue
        dur = float(t[e_idx] - t[s_idx])
        if dur > best_dur:
            best_dur = dur
            best = (int(s_idx), int(e_idx), dur)

    if best is None or best_dur < min(min_duration_s, 0.05):
        return None
    if best_dur < min_duration_s and float(t[-1] - t[0]) > 1.0:
        return None

    s_idx, e_idx, _ = best
    s_t = float(t[s_idx])
    e_t = float(t[e_idx])

    margin = max(1, int(0.05 * (e_idx - s_idx)))
    step_slice = i[s_idx + margin : max(s_idx + margin + 1, e_idx - margin)]
    base_start_idx = int(np.searchsorted(t, max(0.0, s_t - 0.2)))
    base_end_idx = max(base_start_idx + 1, int(np.searchsorted(t, max(0.0, s_t - 0.005))))
    pre_step_base = float(np.mean(i[base_start_idx:base_end_idx]))
    step_amp = float(np.mean(step_slice)) - pre_step_base

    return s_idx, e_idx, s_t, e_t, step_amp


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
    if p < 1e-10:
        return f"{p:.2e}"
    if p < 0.0001:
        return f"{p:.2e}"
    return f"{p:.4f}"


# ── Allen Helpers ─────────────────────────────────────────────────────────────


def get_stimulus_name(ephys_data, sn):
    meta = ephys_data.get_sweep_metadata(sn)
    name = meta.get("aibs_stimulus_name") or meta.get("stimulus_name") or b"Unknown"
    if isinstance(name, bytes):
        name = name.decode("utf-8", errors="ignore")
    return name


def get_valid_sweeps(ephys_data, cell_id):
    """Return sweep numbers whose stimulus type contains 'Square' or 'Ramp'."""
    if ctc is None:
        raise RuntimeError("Allen CellTypesCache is not initialised. Run through main(), not this helper directly.")
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

    import matplotlib.pyplot as plt

    from synaptipy.infrastructure.file_readers.neo_adapter import NeoAdapter

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

            from synaptipy.shared.constants import TRIAL_COLOR

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


# -- Runners ------------------------------------------------------------------


class SynaptiPyRunner:
    @staticmethod
    def run_spikes(
        syn_rec,
        sweep_name: str,
        s_t: float = None,
        e_t: float = None,
        stim_amp: float = None,
    ) -> dict:
        import neo
        import quantities as pq

        spk_params = {
            "threshold": -20.0,
            "refractory_period": 0.002,
            "dvdt_threshold": 20.0,
            "sigma_ms": 0.0,
        }
        train_params = {"spike_threshold": -20.0, "analysis_end_s": 0.0}
        excit_params = {"threshold": -20.0}

        if s_t is not None and e_t is not None and e_t > s_t:
            spk_params["stim_onset_s"] = float(s_t)
            spk_params["stim_end_s"] = float(e_t)
            train_params["analysis_start_s"] = float(s_t)
            train_params["analysis_end_s"] = float(e_t)
            excit_params["analysis_start_s"] = float(s_t)
            excit_params["analysis_end_s"] = float(e_t)
        if stim_amp is not None:
            excit_params["current_steps"] = [float(stim_amp)]

        pipeline = [
            {
                "analysis": "spike_detection",
                "scope": "all_trials",
                "params": spk_params,
            },
            {
                "analysis": "train_dynamics",
                "scope": "average",
                "params": train_params,
            },
            {
                "analysis": "excitability_analysis",
                "scope": "all_trials",
                "params": excit_params,
            },
        ]

        ch_0 = syn_rec.channels.get("0")
        if not ch_0:
            return {}

        trial_idx = -1
        for i, t_name in enumerate(
            ch_0._trial_names if hasattr(ch_0, "_trial_names") else range(len(ch_0.data_trials))
        ):
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
        import neo
        import quantities as pq

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

        step_info = detect_sustained_step(i, t, polarity="negative", min_duration_s=0.2, threshold_pa=10.0)
        if step_info is None:
            return {}
        _, _, s_t, e_t, amp = step_info
        base_start = max(0.0, s_t - 0.2)
        base_end = max(base_start + 0.005, s_t - 0.005)
        step_dur = max(0.05, e_t - s_t)
        ss_win = min(0.1, step_dur * 0.2)

        blk = neo.Block()
        seg = neo.Segment(name=sweep_name)
        blk.segments.append(seg)
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
                "params": {"baseline_start": base_start, "baseline_end": base_end},
            },
            {
                "analysis": "rin_analysis",
                "scope": "all_trials",
                "params": {
                    "baseline_start": base_start,
                    "baseline_end": base_end,
                    "response_start": e_t - ss_win,
                    "response_end": e_t,
                    "current_amplitude": float(amp),
                    "auto_detect_pulse": False,
                },
            },
            {
                "analysis": "tau_analysis",
                "scope": "all_trials",
                "params": {
                    "stim_start_time": s_t,
                    "fit_duration": min(0.10, max(0.02, step_dur * 0.25)),
                    "pct_of_peak": 0.9,
                    "model": "mono",
                },
            },
            {
                "analysis": "sag_ratio_analysis",
                "scope": "all_trials",
                "params": {
                    "baseline_start": base_start,
                    "baseline_end": base_end,
                    "peak_window_start": s_t,
                    "peak_window_end": e_t - 0.005,
                    "ss_window_start": e_t - ss_win,
                    "ss_window_end": e_t - 0.005,
                },
            },
        ]

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


class EFELRunner:
    @staticmethod
    def run_sweep_spikes(v: np.ndarray, t: np.ndarray, s_t: float = None, e_t: float = None) -> dict:
        import efel

        efel.reset()
        set_double = getattr(efel, "set_double_setting", efel.setDoubleSetting)
        set_double("DerivativeThreshold", 20.0)
        if len(t) > 1:
            dt_ms = float((t[1] - t[0]) * 1000.0)
            if dt_ms > 0:
                # Cap resampling no finer than 0.02 ms (50 kHz) to avoid single-bit 200 kHz ADC
                # quantization spikes while preserving full 10 kHz hardware-filtered upstroke kinetics.
                set_double("interp_step", max(dt_ms, 0.02))

        stim_start_ms = float((s_t if s_t is not None else t[0]) * 1000.0)
        stim_end_ms = float((e_t if e_t is not None else t[-1]) * 1000.0)
        trace = {"T": t * 1000.0, "V": v, "stim_start": [stim_start_ms], "stim_end": [stim_end_ms]}
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
            "ISI_CV",
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

        step_info = detect_sustained_step(i, t, polarity="negative", min_duration_s=0.2, threshold_pa=10.0)
        if step_info is None:
            return {}
        _, _, s_t, e_t, stim_amp = step_info

        efel.reset()
        set_double = getattr(efel, "set_double_setting", efel.setDoubleSetting)
        set_double("DerivativeThreshold", 20.0)
        if len(t) > 1:
            dt_ms = float((t[1] - t[0]) * 1000.0)
            if dt_ms > 0:
                # Cap resampling no finer than 0.02 ms (50 kHz) to avoid single-bit 200 kHz ADC
                # quantization spikes while preserving full 10 kHz hardware-filtered upstroke kinetics.
                set_double("interp_step", max(dt_ms, 0.02))

        trace = {
            "T": t * 1000.0,
            "V": v,
            "stim_start": [s_t * 1000.0],
            "stim_end": [e_t * 1000.0],
            "stimulus_current": [stim_amp],
        }

        want = [
            "voltage_base",
            "ohmic_input_resistance",
            "ohmic_input_resistance_vb_ssse",
            "time_constant",
            "decay_time_constant_after_stim",
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
    def run_sweep_spikes(
        v: np.ndarray,
        t: np.ndarray,
        i: np.ndarray = None,
        s_t: float = None,
        e_t: float = None,
    ) -> dict:
        from ipfx.feature_extractor import SpikeFeatureExtractor

        start_s = float(s_t) if s_t is not None else float(t[0])
        end_s = float(e_t) if e_t is not None else float(t[-1])
        stim_arr = i if i is not None else np.zeros_like(v)

        ext = SpikeFeatureExtractor(start=start_s, end=end_s, filter=9.9)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            result = ext.process(t, v, stim_arr)
        if result is None or result.empty:
            return {"n_spikes": 0}

        def _col_mean(col):
            if col in result.columns:
                return float(result[col].mean())
            return np.nan

        slow_trough = _col_mean("slow_trough_v")
        thresh_mean = float(result["threshold_v"].mean())
        mahp = thresh_mean - slow_trough if not np.isnan(slow_trough) else np.nan
        stim_dur = max(1e-6, end_s - start_s)

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
            "avg_rate": float(len(result)) / stim_dur,
            "first_isi": (
                float((result["peak_t"].iloc[1] - result["peak_t"].iloc[0]) * 1000.0) if len(result) > 1 else np.nan
            ),
            "peak_t": float(result["peak_t"].iloc[0] - start_s) * 1000.0 if len(result) > 0 else np.nan,
            "upstroke_downstroke_ratio": (
                float(result["upstroke_downstroke_ratio"].mean()) if "upstroke_downstroke_ratio" in result else np.nan
            ),
            "trough_v": float(result["fast_trough_v"].mean()) if "fast_trough_v" in result else np.nan,
            "adaptation": np.nan,
        }

        try:
            from ipfx.feature_extractor import SpikeTrainFeatureExtractor

            train_ext = SpikeTrainFeatureExtractor(start=start_s, end=end_s)
            train_res = train_ext.process(t, v, stim_arr, result)
            if train_res:
                if "adapt" in train_res and train_res["adapt"] is not None:
                    out["adaptation"] = float(train_res["adapt"])
                if "avg_rate" in train_res and train_res["avg_rate"] is not None:
                    out["avg_rate"] = float(train_res["avg_rate"])
        except Exception:
            pass

        return out

    @staticmethod
    def run_sweep_passive(v: np.ndarray, i: np.ndarray, t: np.ndarray) -> dict:
        import ipfx.subthresh_features as subT

        step_info = detect_sustained_step(i, t, polarity="negative", min_duration_s=0.2, threshold_pa=10.0)
        if step_info is None:
            return {}
        _, _, start_t, end_t, stim_amp = step_info

        out = {}
        baseline_int = min(0.2, start_t * 0.8)

        try:
            out["v_baseline"] = float(subT.baseline_voltage(t, v, start_t, baseline_interval=baseline_int))
        except Exception:
            pass

        try:
            # IPFX subT.sag returns the dimensionless sag fraction (V_peak - V_ss) / (V_peak - V_base)
            sag_frac = float(subT.sag(t, v, i, start_t, end_t, baseline_interval=baseline_int))
            out["sag"] = sag_frac
            if not np.isnan(sag_frac):
                out["sag_pct"] = sag_frac * 100.0
                out["sag_ratio"] = 1.0 - sag_frac
        except Exception:
            out["sag"] = np.nan

        try:
            v_def, _ = subT.voltage_deflection(t, v, i, start_t, end_t)
            v_def_val = float(v_def) - out.get("v_baseline", 0.0)
            out["v_deflect"] = v_def_val
            if stim_amp != 0:
                out["peak_rin"] = abs(v_def_val / stim_amp) * 1000.0
        except Exception:
            pass

        try:
            out["input_resistance"] = float(
                subT.input_resistance([t], [i], [v], start_t, end_t, baseline_interval=baseline_int)
            )
        except Exception:
            out["input_resistance"] = np.nan

        try:
            tau = subT.time_constant(t, v, i, start_t, end_t, min_snr=0.0, baseline_interval=baseline_int)
        except TypeError:
            tau = subT.time_constant(t, v, i, start_t, end_t, min_snr=0.0)

        out["tau"] = float(tau) * 1000.0
        return out


# -- Builders -----------------------------------------------------------------


def build_table1(downloaded_cells: list) -> pd.DataFrame:
    log.info("Building Table 1 (Active Properties)...")
    rows = []

    from synaptipy.infrastructure.file_readers.neo_adapter import NeoAdapter

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

            step_info = detect_sustained_step(i, t, polarity="positive", min_duration_s=0.2, threshold_pa=10.0)
            if step_info is None:
                continue
            _, _, s_t, e_t, stim_amp = step_info
            if stim_amp <= 120:
                continue

            syn_r = SynaptiPyRunner.run_spikes(syn_rec, f"Sweep_{sn}", s_t=s_t, e_t=e_t, stim_amp=stim_amp)
            if not syn_r or syn_r.get("spike_count", 0) == 0:
                continue

            efel_r = EFELRunner.run_sweep_spikes(v, t, s_t=s_t, e_t=e_t)
            ipfx_r = IPFXRunner.run_sweep_spikes(v, t, i=i, s_t=s_t, e_t=e_t)
            if efel_r.get("n_spikes", 0) == 0 or ipfx_r.get("n_spikes", 0) == 0:
                continue

            syn_first_isi = float(syn_r.get("first_isi_ms", np.nan))
            syn_sfa = float(syn_r.get("adaptation_index", np.nan))
            t1 = efel_r.get("time_to_first_spike", np.nan)
            t2 = efel_r.get("time_to_second_spike", np.nan)
            efel_first_isi = (t2 - t1) if (not np.isnan(t1) and not np.isnan(t2)) else np.nan

            syn_delay_ms = syn_r.get("first_spike_delay_ms", np.nan)
            if np.isnan(syn_delay_ms) and not np.isnan(syn_r.get("first_spike_latency_s", np.nan)):
                syn_delay_ms = float(syn_r["first_spike_latency_s"]) * 1000.0

            rows.append(
                {
                    "cell_id": cell_id,
                    "trial": sn,
                    "syn_peak_mV": float(syn_r.get("absolute_peak_mv_mean", np.nan)),
                    "efel_peak_mV": efel_r.get("peak_voltage", np.nan),
                    "ipfx_peak_mV": ipfx_r.get("peak_v", np.nan),
                    "syn_thr_mV": float(syn_r.get("ap_threshold_mean", np.nan)),
                    "efel_thr_mV": efel_r.get("AP_begin_voltage", np.nan),
                    "ipfx_thr_mV": ipfx_r.get("threshold_v", np.nan),
                    "syn_amp_mV": float(syn_r.get("amplitude_mean", np.nan)),
                    "efel_amp_mV": efel_r.get("AP_amplitude", np.nan),
                    "ipfx_amp_mV": ipfx_r.get("amplitude", np.nan),
                    "syn_hw_ms": float(syn_r.get("half_width_mean", np.nan)),
                    "efel_hw_ms": efel_r.get("AP_duration_half_width", np.nan),
                    "ipfx_hw_ms": ipfx_r.get("width_ms", np.nan),
                    "syn_rise_time_ms": float(syn_r.get("rise_time_10_90_mean", np.nan)),
                    "efel_rise_time_ms": efel_r.get("AP_rise_time", np.nan),
                    "ipfx_rise_time_ms": np.nan,
                    "syn_decay_time_ms": float(syn_r.get("decay_time_90_10_mean", np.nan)),
                    "efel_decay_time_ms": efel_r.get("AP_fall_time", np.nan),
                    "ipfx_decay_time_ms": np.nan,
                    "syn_maxdvdt": syn_r.get("max_dvdt_mean", np.nan),
                    "efel_maxdvdt": efel_r.get("AP_peak_upstroke", np.nan),
                    "ipfx_maxdvdt": ipfx_r.get("upstroke", np.nan),
                    "syn_mindvdt": syn_r.get("min_dvdt_mean", np.nan),
                    "efel_mindvdt": efel_r.get("AP_peak_downstroke", np.nan),
                    "ipfx_mindvdt": ipfx_r.get("downstroke", np.nan),
                    "syn_ap_delay": float(syn_delay_ms) if not np.isnan(syn_delay_ms) else np.nan,
                    "efel_ap_delay": efel_r.get("time_to_first_spike", np.nan),
                    "ipfx_ap_delay": ipfx_r.get("peak_t", np.nan),
                    "syn_upstroke_downstroke_ratio": syn_r.get("upstroke_downstroke_ratio_mean", np.nan),
                    "efel_upstroke_downstroke_ratio": (
                        abs(efel_r.get("AP_peak_upstroke", np.nan) / efel_r.get("AP_peak_downstroke", np.nan))
                        if not np.isnan(efel_r.get("AP_peak_downstroke", np.nan))
                        and efel_r.get("AP_peak_downstroke", np.nan) != 0
                        else np.nan
                    ),
                    "ipfx_upstroke_downstroke_ratio": ipfx_r.get("upstroke_downstroke_ratio", np.nan),
                    "syn_trough_v": syn_r.get("trough_v_mean", np.nan),
                    "efel_trough_v": efel_r.get("min_voltage_between_spikes", np.nan),
                    "ipfx_trough_v": ipfx_r.get("trough_v", np.nan),
                    "syn_phase_plane_area": syn_r.get("phase_plane_area_mean", np.nan),
                    "efel_phase_plane_area": np.nan,
                    "ipfx_phase_plane_area": np.nan,
                    "syn_fahp_mV": syn_r.get("fahp_depth_mean", np.nan),
                    "efel_fahp_mV": efel_r.get("fast_AHP", np.nan),
                    "ipfx_fahp_mV": ipfx_r.get("fast_ahp", np.nan),
                    "syn_mahp_mV": float(syn_r.get("mahp_depth_mean", np.nan)),
                    "efel_mahp_mV": np.nan,
                    "ipfx_mahp_mV": ipfx_r.get("mahp", np.nan),
                    "syn_ahp_dur_ms": float(syn_r.get("ahp_duration_half_mean", np.nan)),
                    "efel_ahp_dur_ms": np.nan,
                    "ipfx_ahp_dur_ms": np.nan,
                    "syn_adp_mV": float(syn_r.get("adp_amplitude_mean", np.nan)),
                    "efel_adp_mV": efel_r.get("ADP_peak_amplitude", np.nan),
                    "ipfx_adp_mV": ipfx_r.get("adp_amp", np.nan),
                    "syn_rate_hz": float(syn_r.get("window_frequency_hz", syn_r.get("mean_freq_hz", np.nan))),
                    "syn_inst_rate_hz": float(syn_r.get("mean_freq_hz", np.nan)),
                    "efel_rate_hz": efel_r.get("mean_frequency", np.nan),
                    "ipfx_rate_hz": ipfx_r.get("avg_rate", np.nan),
                    "syn_max_freq_hz": float(syn_r.get("max_freq_hz", np.nan)),
                    "efel_max_freq_hz": np.nan,
                    "ipfx_max_freq_hz": np.nan,
                    "syn_first_isi_ms": syn_first_isi,
                    "efel_first_isi_ms": efel_first_isi,
                    "ipfx_first_isi_ms": ipfx_r.get("first_isi", np.nan),
                    "syn_sfa": syn_sfa,
                    "efel_sfa": efel_r.get("adaptation_index2", np.nan),
                    "ipfx_sfa": ipfx_r.get("adaptation", np.nan),
                    "syn_cv_isi": float(syn_r.get("cv", np.nan)),
                    "efel_cv_isi": efel_r.get("ISI_CV", np.nan),
                    "ipfx_cv_isi": np.nan,
                    "syn_broadening": float(syn_r.get("spike_broadening_index", np.nan)),
                    "efel_broadening": np.nan,
                    "ipfx_broadening": np.nan,
                    "syn_rheobase_pa": float(syn_r.get("rheobase_pa", np.nan)),
                    "efel_rheobase_pa": np.nan,
                    "ipfx_rheobase_pa": np.nan,
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

    from synaptipy.infrastructure.file_readers.neo_adapter import NeoAdapter

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

            step_info = detect_sustained_step(i, t, polarity="negative", min_duration_s=0.2, threshold_pa=10.0)
            if step_info is None or step_info[4] >= -15.0:
                continue

            syn_r = SynaptiPyRunner.run_passive(syn_rec, f"Sweep_{sn}", i, t)
            efel_r = EFELRunner.run_sweep_passive(v, i, t)
            ipfx_r = IPFXRunner.run_sweep_passive(v, i, t)

            efel_rin = efel_r.get("ohmic_input_resistance", np.nan)
            efel_sag_r1 = efel_r.get("sag_ratio1", np.nan)
            efel_sag_r2 = efel_r.get("sag_ratio2", np.nan)
            rows.append(
                {
                    "cell_id": cell_id,
                    "trial": sn,
                    "syn_rmp_mV": float(syn_r.get("rmp_mv", np.nan)),
                    "efel_rmp_mV": efel_r.get("voltage_base", np.nan),
                    "ipfx_rmp_mV": ipfx_r.get("v_baseline", np.nan),
                    "syn_rin_mohm": syn_r.get("rin_mohm", np.nan),
                    "efel_rin_mohm": efel_rin * 1000.0 if not np.isnan(efel_rin) else np.nan,
                    "ipfx_rin_mohm": ipfx_r.get("input_resistance", np.nan),
                    "syn_rin_peak_mohm": syn_r.get("rin_peak_mohm", np.nan),
                    "efel_rin_peak_mohm": (
                        efel_r.get("ohmic_input_resistance_vb_ssse", np.nan) * 1000.0
                        if not np.isnan(efel_r.get("ohmic_input_resistance_vb_ssse", np.nan))
                        else np.nan
                    ),
                    "ipfx_rin_peak_mohm": ipfx_r.get("peak_rin", np.nan),
                    "syn_tau_ms": syn_r.get("tau_ms", np.nan),
                    "efel_tau_ms": efel_r.get("time_constant", np.nan),
                    "ipfx_tau_ms": ipfx_r.get("tau", np.nan),
                    "syn_tau_decay_ms": syn_r.get("tau_decay_after_stimulus_ms", np.nan),
                    "efel_tau_decay_ms": efel_r.get("decay_time_constant_after_stim", np.nan),
                    "ipfx_tau_decay_ms": np.nan,
                    # eFEL sag_ratio2 = (V_ss - V_base) / (V_peak - V_base) matches SynaptiPy sag_ratio
                    "syn_sag_ratio": syn_r.get("sag_ratio", np.nan),
                    "efel_sag_ratio": efel_sag_r2,
                    "ipfx_sag_ratio": ipfx_r.get("sag_ratio", np.nan),
                    # eFEL sag_ratio1 = (V_ss - V_peak) / (V_base - V_peak) matches SynaptiPy sag_percentage / 100
                    "syn_sag_pct": syn_r.get("sag_percentage", np.nan),
                    "efel_sag_pct": efel_sag_r1 * 100.0 if not np.isnan(efel_sag_r1) else np.nan,
                    "ipfx_sag_pct": ipfx_r.get("sag_pct", np.nan),
                    "syn_rebound_mv": syn_r.get("rebound_depolarization_amplitude_mv", np.nan),
                    "efel_rebound_mv": np.nan,
                    "ipfx_rebound_mv": np.nan,
                }
            )

    df = pd.DataFrame(rows)
    df.to_csv(OUT_DIR / "passive_properties.csv", index=False)
    log.info(f"Table 2 built. {len(df)} sweeps extracted.")
    return df


# -- Render Markdown ----------------------------------------------------------


def _format_stat_entry(vs: dict, cell_r: float = np.nan) -> tuple:
    """Build (data_structure_desc, stat_value_str) for the statistical table."""
    sw_w = vs.get("shapiro_w", np.nan)
    sw_p = vs.get("shapiro_p", np.nan)
    n = vs.get("n", 0)
    if not np.isnan(sw_p) and n >= 8:
        norm_label = "Normal paired differences" if sw_p > 0.05 else "Non-normal paired differences"
        sw_str = f"Shapiro-Wilk *W* = {sw_w:.4f} (*p* = {fmt_p(sw_p)})"
    elif n >= 8:
        norm_label = "Zero-variance paired differences"
        sw_str = "Shapiro-Wilk N/A (exact identity)"
    else:
        norm_label = "Small sample (*n* < 8)"
        sw_str = "Shapiro-Wilk N/A"

    parts = [f"*r* = {vs['r']:.4f} (*p* = {fmt_p(vs['p'])})"]
    if not np.isnan(vs.get("rho", np.nan)):
        parts.append(f"Spearman *rho* = {vs['rho']:.4f} (*p* = {fmt_p(vs['p_rho'])})")
    parts.append(sw_str)
    if not np.isnan(cell_r):
        parts.append(f"cell-mean *r* = {cell_r:.4f}")
    return norm_label, "; ".join(parts)


def _cell_level_r(cmp_df: pd.DataFrame, x_col: str, y_col: str) -> float:
    """Compute cell-clustered Pearson r across per-cell means to guard against pseudoreplication."""
    if "cell_id" not in cmp_df.columns or x_col not in cmp_df.columns or y_col not in cmp_df.columns:
        return np.nan
    grouped = cmp_df.groupby("cell_id")[[x_col, y_col]].mean(numeric_only=True).dropna()
    if len(grouped) < 3:
        return np.nan
    xv = grouped[x_col].values
    yv = grouped[y_col].values
    if np.std(xv) < 1e-12 or np.std(yv) < 1e-12:
        return np.nan
    r_val, _ = pearsonr(xv, yv)
    return float(r_val)


def make_table1_md(cmp_df: pd.DataFrame, stat_table_rows: list, stat_letter_idx: list) -> str:
    metrics = [
        ("AP threshold (mV)", "syn_thr_mV", "efel_thr_mV", "ipfx_thr_mV", "mV"),
        ("AP amplitude (mV)", "syn_amp_mV", "efel_amp_mV", "ipfx_amp_mV", "mV"),
        ("AP half-width (ms)", "syn_hw_ms", "efel_hw_ms", "ipfx_hw_ms", "ms"),
        ("Max dV/dt (V/s)", "syn_maxdvdt", "efel_maxdvdt", "ipfx_maxdvdt", "V/s"),
        ("AP Delay (Time to first spike) (ms)", "syn_ap_delay", "efel_ap_delay", "ipfx_ap_delay", "ms"),
        (
            "Upstroke/Downstroke Ratio",
            "syn_upstroke_downstroke_ratio",
            "efel_upstroke_downstroke_ratio",
            "ipfx_upstroke_downstroke_ratio",
            "Ratio",
        ),
        ("Fast AHP depth (mV)", "syn_fahp_mV", "efel_fahp_mV", "ipfx_fahp_mV", "mV"),
        ("ADP amplitude (mV)", "syn_adp_mV", "efel_adp_mV", "ipfx_adp_mV", "mV"),
        ("Mean Firing Frequency (Hz)", "syn_rate_hz", "efel_rate_hz", "ipfx_rate_hz", "Hz"),
        ("Spike Frequency Adaptation", "syn_sfa", "efel_sfa", "ipfx_sfa", "Ratio"),
    ]
    md = (
        "**Table 2-1: Statistical summary of SynaptiPy AP extraction vs. eFEL and IPFX "
        "benchmarks (Allen Dataset, per-sweep means).**\n\n"
    )
    md += (
        "| Metric | SynaptiPy vs IPFX Pearson *r* | Mean bias vs IPFX | LoA vs IPFX | "
        "SynaptiPy vs eFEL Pearson *r* | Mean bias vs eFEL | LoA vs eFEL |\n"
    )
    md += (
        "|--------|-------------------------------|-------------------|-------------|"
        "-------------------------------|-------------------|-------------|\n"
    )

    def _next_letter():
        idx = stat_letter_idx[0]
        stat_letter_idx[0] += 1
        if idx < 26:
            return chr(ord("a") + idx)
        return chr(ord("a") + (idx // 26) - 1) + chr(ord("a") + (idx % 26))

    def _fmt_r_with_letter(vs, cell_r=np.nan):
        if np.isnan(vs.get("r", np.nan)):
            return "N/A"
        letter = _next_letter()
        p = vs.get("p", np.nan)
        n = vs.get("n", 0)
        s = f"{vs['r']:.4f} (*p* = {fmt_p(p)}, *n* = {n})<sup>{letter}</sup>"
        data_desc, stat_val = _format_stat_entry(vs, cell_r=cell_r)
        test_name = (
            f"Pearson + Spearman correlation (two-sided, *n* = {n} sweeps)"
            if "Non-normal" in data_desc
            else f"Pearson correlation (two-sided, *n* = {n} sweeps)"
        )
        stat_table_rows.append(
            {
                "letter": letter,
                "data_structure": data_desc,
                "test": test_name,
                "power": stat_val,
            }
        )
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
            cell_r_e = _cell_level_r(cmp_df, e_col, s_col)
        else:
            vs_e = dict(r=np.nan, p=np.nan, bias=np.nan, loa_upper=np.nan, loa_lower=np.nan, n=0)
            cell_r_e = np.nan

        if i_col and i_col in cmp_df.columns:
            iv = cmp_df[i_col].values
            vs_i = corr_summary(iv, s)
            cell_r_i = _cell_level_r(cmp_df, i_col, s_col)
        else:
            vs_i = dict(r=np.nan, p=np.nan, bias=np.nan, loa_upper=np.nan, loa_lower=np.nan, n=0)
            cell_r_i = np.nan

        fmt_ipfx = _fmt_r_with_letter(vs_i, cell_r=cell_r_i) if not np.isnan(vs_i.get("r", np.nan)) else "N/A"
        fmt_efel = _fmt_r_with_letter(vs_e, cell_r=cell_r_e) if not np.isnan(vs_e.get("r", np.nan)) else "N/A"

        md += (
            f"| {label} | "
            f"{fmt_ipfx} | {_fmt_bias(vs_i, unit)} | {_fmt_loa(vs_i, unit)} | "
            f"{fmt_efel} | {_fmt_bias(vs_e, unit)} | {_fmt_loa(vs_e, unit)} |\n"
        )

    n_sweeps = len(cmp_df)
    n_cells = int(cmp_df["cell_id"].nunique()) if "cell_id" in cmp_df.columns and not cmp_df.empty else 0
    md += (
        f"\n*All correlations are Pearson's r (two-sided) with exact *p*-values and valid pair counts reported "
        f"across *n* = {n_sweeps} sweeps nested within *N* = {n_cells} independent cells "
        f"(cell-clustered mean correlations and non-parametric Spearman *rho* are reported in the Statistical Table). "
        f"Bias = mean signed difference (SynaptiPy minus benchmark, per-sweep means). "
        f"LoA = 95% Bland-Altman limits of agreement. "
        f"SynaptiPy: BatchAnalysisEngine spike_detection (dV/dt threshold 20 V/s, refractory 2 ms). "
        f"eFEL: BlueBrain eFEL at native sampling interval. "
        f"IPFX: Allen IPFX SpikeFeatureExtractor, 9.9 kHz Bessel filter. "
        f"Superscript letters refer to the statistical table. N/A = no direct benchmark equivalent.*"
    )
    return md


def make_table2_md(cmp_df: pd.DataFrame, stat_table_rows: list, stat_letter_idx: list) -> str:
    metrics = [
        ("Resting Membrane Potential (mV)", "syn_rmp_mV", "efel_rmp_mV", "ipfx_rmp_mV", "mV"),
        ("Input Resistance - Steady-State (MOhm)", "syn_rin_mohm", "efel_rin_mohm", "ipfx_rin_mohm", "MOhm"),
        ("Input Resistance - Peak (MOhm)", "syn_rin_peak_mohm", "efel_rin_peak_mohm", "ipfx_rin_peak_mohm", "MOhm"),
        ("Membrane Time Constant (ms)", "syn_tau_ms", "efel_tau_ms", "ipfx_tau_ms", "ms"),
        ("Sag Percentage (%)", "syn_sag_pct", "efel_sag_pct", "ipfx_sag_pct", "%"),
    ]
    md = "**Table 2-2: Subthreshold passive properties benchmark on hyperpolarizing steps (Allen Dataset).**\n\n"
    md += (
        "| Metric | Valid *N* (eFEL / IPFX) | "
        "SynaptiPy vs eFEL Pearson *r* | Mean bias vs eFEL | LoA vs eFEL | "
        "SynaptiPy vs IPFX Pearson *r* | Mean bias vs IPFX | LoA vs IPFX |\n"
    )
    md += (
        "|--------|-------------------------|-------------------------------|-------------------"
        "|-------------|-------------------------------|-------------------|-------------|\n"
    )

    def _next_letter():
        idx = stat_letter_idx[0]
        stat_letter_idx[0] += 1
        if idx < 26:
            return chr(ord("a") + idx)
        return chr(ord("a") + (idx // 26) - 1) + chr(ord("a") + (idx % 26))

    def _fmt_r_with_letter(vs, cell_r=np.nan):
        if np.isnan(vs.get("r", np.nan)):
            return "N/A"
        letter = _next_letter()
        p = vs.get("p", np.nan)
        n = vs.get("n", 0)
        s = f"{vs['r']:.4f} (*p* = {fmt_p(p)})<sup>{letter}</sup>"
        data_desc, stat_val = _format_stat_entry(vs, cell_r=cell_r)
        test_name = (
            f"Pearson + Spearman correlation (two-sided, *n* = {n} sweeps)"
            if "Non-normal" in data_desc
            else f"Pearson correlation (two-sided, *n* = {n} sweeps)"
        )
        stat_table_rows.append(
            {
                "letter": letter,
                "data_structure": data_desc,
                "test": test_name,
                "power": stat_val,
            }
        )
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
            cell_r_e = _cell_level_r(cmp_df, e_col, s_col)
        else:
            vs_e = dict(r=np.nan, p=np.nan, bias=np.nan, loa_upper=np.nan, loa_lower=np.nan, n=0)
            cell_r_e = np.nan

        if i_col and i_col in cmp_df.columns:
            iv = cmp_df[i_col].values
            vs_i = corr_summary(iv, s)
            cell_r_i = _cell_level_r(cmp_df, i_col, s_col)
        else:
            vs_i = dict(r=np.nan, p=np.nan, bias=np.nan, loa_upper=np.nan, loa_lower=np.nan, n=0)
            cell_r_i = np.nan

        n_str = f"{vs_e['n']} / {vs_i['n']}" if vs_e["n"] != vs_i["n"] else f"{vs_e['n']}"

        fmt_efel = _fmt_r_with_letter(vs_e, cell_r=cell_r_e) if not np.isnan(vs_e.get("r", np.nan)) else "N/A"
        fmt_ipfx = _fmt_r_with_letter(vs_i, cell_r=cell_r_i) if not np.isnan(vs_i.get("r", np.nan)) else "N/A"

        md += (
            f"| {label} | {n_str} | "
            f"{fmt_efel} | {_fmt_bias(vs_e, unit)} | {_fmt_loa(vs_e, unit)} | "
            f"{fmt_ipfx} | {_fmt_bias(vs_i, unit)} | {_fmt_loa(vs_i, unit)} |\n"
        )

    n_cells = int(cmp_df["cell_id"].nunique()) if "cell_id" in cmp_df.columns and not cmp_df.empty else 0
    md += (
        f"\n*All correlations are Pearson's r (two-sided) with exact *p*-values reported across sweeps "
        f"from *N* = {n_cells} independent cells (cell-clustered mean correlations and Spearman *rho* "
        "are reported in the Statistical Table). "
        "LoA = 95% Bland-Altman limits of agreement (mean +/- 1.96 SD of sweep-level differences). "
        "Steady-State Rin uses the terminal step steady-state deflection; Peak Rin uses maximum hyperpolarizing "
        "deflection. Superscript letters refer to the statistical table. N/A = no direct benchmark equivalent.*"
    )
    return md


def make_stat_table_md(stat_table_rows: list) -> str:
    md = "\n\n**Statistical Table**\n\n"
    md += "| | Data structure | Type of test | Statistical value |\n"
    md += "|---|---|---|---|\n"
    for row in stat_table_rows:
        md += f"| {row['letter']} | {row['data_structure']} | {row['test']} | {row['power']} |\n"
    return md


def main(argv=None):
    global CACHE_DIR, OUT_DIR, PLOTS_DIR, ctc

    parser = argparse.ArgumentParser(description="Generate SynaptiPy paper benchmark tables.")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST, help="Dataset manifest JSON.")
    parser.add_argument("--force", action="store_true", help="Regenerate CSV tables even if cached outputs exist.")
    parser.add_argument("--skip-plots", action="store_true", help="Skip raw per-cell verification plots.")
    parser.add_argument(
        "--no-paper-update", action="store_true", help="Do not rewrite the TABLES block in paper/paper.md."
    )
    parser.add_argument(
        "--check-only", action="store_true", help="Validate manifest and paths without downloading data."
    )
    parser.add_argument("--cache-dir", type=Path, default=CACHE_DIR, help="Allen NWB cache directory.")
    parser.add_argument("--output-dir", type=Path, default=OUT_DIR, help="Directory for generated CSV/JSON outputs.")
    parser.add_argument("--plots-dir", type=Path, default=PLOTS_DIR, help="Directory for raw verification plots.")
    args = parser.parse_args(argv)

    CACHE_DIR = args.cache_dir
    OUT_DIR = args.output_dir
    PLOTS_DIR = args.plots_dir

    manifest = load_data_manifest(args.manifest)
    manifest_cells = manifest["cells"]
    manifest_cell_targets = [(int(cell["cell_id"]), cell.get("structure", "unknown")) for cell in manifest_cells]

    print("=" * 60)
    print("SynaptiPy — generate_paper_tables.py (Unified Benchmark)")
    print(f"Targeting {len(manifest_cell_targets)} Allen Institute cells")
    print(f"Manifest: {args.manifest}")
    print("=" * 60)

    if args.check_only:
        missing_dirs = [p for p in [CACHE_DIR.parent, OUT_DIR.parent, PLOTS_DIR.parent] if not p.exists()]
        if missing_dirs:
            for path in missing_dirs:
                log.warning("Parent directory does not exist yet: %s", path)
        log.info("Manifest check passed for %d cells.", len(manifest_cell_targets))
        return 0

    from allensdk.core.cell_types_cache import CellTypesCache

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    PLOTS_DIR.mkdir(parents=True, exist_ok=True)
    ctc = CellTypesCache(manifest_file=str(CACHE_DIR / "manifest.json"))

    log.info("Targeting %d manifest-listed high-quality cells...", len(manifest_cell_targets))

    downloaded_cells = []
    for cell_id, structure in manifest_cell_targets:
        nwb_path = CACHE_DIR / f"cell_{cell_id}.nwb"

        try:
            if not nwb_path.exists():
                log.info(
                    f"[Download {len(downloaded_cells) + 1}/{len(manifest_cell_targets)}] "
                    f"Fetching Cell {cell_id} ..."
                )
            ephys_data = ctc.get_ephys_data(cell_id, file_name=str(nwb_path))
            downloaded_cells.append((cell_id, structure, ephys_data, nwb_path))
        except Exception as exc:
            log.warning(f"  Failed to download Cell {cell_id}: {exc}")

    log.info("Phase 2: Analysis")

    stat_table_rows = []
    stat_letter_idx = [0]

    t1_csv = OUT_DIR / "benchmark_comparison.csv"
    if args.force or not t1_csv.exists():
        t1_df = build_table1(downloaded_cells)
    else:
        t1_df = pd.read_csv(t1_csv)
    t1_md = make_table1_md(t1_df, stat_table_rows, stat_letter_idx)

    t2_csv = OUT_DIR / "passive_properties.csv"
    if args.force or not t2_csv.exists():
        t2_df = build_table2(downloaded_cells)
    else:
        t2_df = pd.read_csv(t2_csv)
    t2_md = make_table2_md(t2_df, stat_table_rows, stat_letter_idx)

    stat_md = make_stat_table_md(stat_table_rows)

    if not args.skip_plots:
        plot_cell_summaries(downloaded_cells)

    write_run_provenance(manifest, args, downloaded_cells)

    if args.no_paper_update:
        log.info("Skipping paper.md table-block update (--no-paper-update).")
        return 0

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

    new_text = text[: idx1s + len(T1_START)] + "\n\n" + t1_md + "\n\n" + t2_md + "\n" + stat_md + "\n" + text[idx1e:]
    paper_path.write_text(new_text, encoding="utf-8")
    log.info(f"Success! Updated paper at {paper_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
