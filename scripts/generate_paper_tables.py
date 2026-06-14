#!/usr/bin/env python3
"""
scripts/generate_paper_tables.py
=================================
Generates Extended Data Table 1 (SynaptiPy vs eFEL vs IPFX benchmark) and
Extended Data Table 2 (passive properties from real recordings) and writes
real values back into paper/paper.md.

SynaptiPy analysis is done exclusively via BatchAnalysisEngine.run_batch().
eFEL and IPFX are called as external pipelines for comparison.
All three tools are compared at the per-sweep mean level (the natural
output granularity for all three pipelines).

Usage:
    conda run -n synaptipy python scripts/generate_paper_tables.py

Outputs:
    paper/results/benchmark_comparison.csv  — per-sweep comparison
    paper/results/passive_properties.csv    — per-trial passive metrics
    paper/paper.md                          — Extended Data Tables filled with real values
"""

import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import pearsonr

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

OUT_DIR = REPO_ROOT / "paper" / "results"
OUT_DIR.mkdir(parents=True, exist_ok=True)

BENCHMARK_FILE = REPO_ROOT / "examples" / "data" / "2023_04_11_0021.abf"
ALL_FILES = [
    REPO_ROOT / "examples" / "data" / "2023_04_11_0018.abf",
    REPO_ROOT / "examples" / "data" / "2023_04_11_0019.abf",
    REPO_ROOT / "examples" / "data" / "2023_04_11_0021.abf",
]

# ── SynaptiPy public API ──────────────────────────────────────────────────────
from Synaptipy.core.analysis.batch_engine import BatchAnalysisEngine
from Synaptipy.infrastructure.file_readers.neo_adapter import NeoAdapter


# ── External pipeline helpers ─────────────────────────────────────────────────
def run_efel_sweep(v: np.ndarray, t: np.ndarray) -> dict:
    """Run eFEL on one sweep. Returns per-sweep means of spike features."""
    import efel
    trace = {
        "T": t * 1000.0,
        "V": v,
        "stim_start": [t[0] * 1000.0],
        "stim_end":   [t[-1] * 1000.0],
    }
    want = ["peak_voltage", "AP_duration_half_width", "AP_rise_rate", "AP_fall_rate"]
    res = efel.get_feature_values([trace], want)
    r = res[0] if res else {}
    out = {}
    pv = r.get("peak_voltage")
    out["n_spikes"] = len(pv) if pv is not None else 0
    for k in want:
        vals = r.get(k)
        out[k] = float(np.mean(vals)) if (vals is not None and len(vals) > 0) else np.nan
    return out


def run_ipfx_sweep(v: np.ndarray, t: np.ndarray) -> dict:
    """Run IPFX on one sweep. Returns per-sweep means of spike features."""
    from ipfx.feature_extractor import SpikeFeatureExtractor
    ext = SpikeFeatureExtractor(start=t[0], end=t[-1], filter=9.9)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        result = ext.process(t, v, np.zeros_like(v))

    if result is None or result.empty:
        return {"n_spikes": 0, "peak_v": np.nan, "width_ms": np.nan,
                "upstroke": np.nan, "downstroke": np.nan}
    return {
        "n_spikes":    len(result),
        "peak_v":      float(result["peak_v"].mean()),
        "width_ms":    float(result["width"].mean()) * 1000.0,  # s → ms
        "upstroke":    float(result["upstroke"].mean()),
        "downstroke":  float(abs(result["downstroke"]).mean()),  # sign convention
    }


# ── Table 1: per-sweep benchmark comparison ───────────────────────────────────
def build_table1() -> pd.DataFrame:
    """
    Run SynaptiPy (via engine) + eFEL + IPFX on the benchmark file,
    aligned per sweep. Returns tidy comparison DataFrame.
    """
    print(f"\n── Table 1: benchmark comparison ({BENCHMARK_FILE.name}) ──")

    # ── SynaptiPy via engine API ──
    engine = BatchAnalysisEngine(max_workers=1)
    pipeline = [
        {
            "analysis": "spike_detection",
            "scope": "all_trials",
            "params": {
                "threshold":         -20.0,
                "refractory_period":  0.002,
                "dvdt_threshold":    20.0,
            },
        }
    ]
    syn_df = engine.run_batch([BENCHMARK_FILE], pipeline)
    print(f"  SynaptiPy engine: {len(syn_df)} sweep rows")

    # ── Load raw traces for eFEL and IPFX ──
    adapter = NeoAdapter()
    rec = adapter.read_recording(BENCHMARK_FILE)
    ch = list(rec.channels.values())[0]
    sr = ch.sampling_rate
    dt = 1.0 / sr

    rows = []
    for _, row in syn_df.iterrows():
        t_idx = int(row.get("trial_index", 0))
        n_syn = int(row.get("spike_count", 0))
        if n_syn == 0:
            continue
        if t_idx >= len(ch.data_trials):
            continue

        v = np.asarray(ch.data_trials[t_idx], dtype=np.float64)
        t = np.arange(len(v)) * dt

        efel_r = run_efel_sweep(v, t)
        ipfx_r = run_ipfx_sweep(v, t)

        # Only keep sweeps where all three pipelines detected ≥1 spike
        if efel_r["n_spikes"] == 0 or ipfx_r["n_spikes"] == 0:
            continue

        # SynaptiPy: peak voltage from absolute_peak_mv_mean
        s_peak = float(row.get("absolute_peak_mv_mean", np.nan))

        rows.append({
            "trial":         t_idx,
            "n_syn":         n_syn,
            "n_efel":        efel_r["n_spikes"],
            "n_ipfx":        ipfx_r["n_spikes"],
            # Peak voltage
            "syn_peak_mV":   s_peak,
            "efel_peak_mV":  efel_r.get("peak_voltage", np.nan),
            "ipfx_peak_mV":  ipfx_r.get("peak_v", np.nan),
            # Half-width
            "syn_hw_ms":     float(row.get("half_width_mean", np.nan)),
            "efel_hw_ms":    efel_r.get("AP_duration_half_width", np.nan),
            "ipfx_hw_ms":    ipfx_r.get("width_ms", np.nan),
            # Max dV/dt
            "syn_maxdvdt":   float(row.get("max_dvdt_mean", np.nan)),
            "efel_maxdvdt":  efel_r.get("AP_rise_rate", np.nan),
            "ipfx_maxdvdt":  ipfx_r.get("upstroke", np.nan),
            # Min dV/dt
            "syn_mindvdt":   float(row.get("min_dvdt_mean", np.nan)),
            "efel_mindvdt":  efel_r.get("AP_fall_rate", np.nan),
            "ipfx_mindvdt":  ipfx_r.get("downstroke", np.nan),
        })

    cmp_df = pd.DataFrame(rows)
    csv_path = OUT_DIR / "benchmark_comparison.csv"
    cmp_df.to_csv(csv_path, index=False)
    print(f"  Saved {len(cmp_df)} sweep rows → {csv_path}")
    return cmp_df


# ── Table 2: passive properties across all ABF files ─────────────────────────
def build_table2() -> pd.DataFrame:
    """Run BatchAnalysisEngine on all ABF files. Returns per-trial summary."""
    print("\n── Table 2: passive properties (all files) ──")

    engine = BatchAnalysisEngine(max_workers=1)
    pipeline = [
        {
            "analysis": "rmp_analysis",
            "scope": "all_trials",
            "params": {"baseline_start": 0.0, "baseline_end": 0.2},
        },
        {
            "analysis": "rin_analysis",
            "scope": "all_trials",
            "params": {
                "baseline_start": 0.0,
                "baseline_end":   0.15,
                "response_start": 0.6,
                "response_end":   0.75,
            },
        },
        {
            "analysis": "spike_detection",
            "scope": "all_trials",
            "params": {
                "threshold":         -20.0,
                "refractory_period":  0.002,
                "dvdt_threshold":    20.0,
            },
        },
    ]

    existing = [p for p in ALL_FILES if p.exists()]
    df = engine.run_batch(existing, pipeline)
    print(f"  Engine returned {len(df)} trial rows from {len(existing)} files")

    csv_path = OUT_DIR / "passive_properties.csv"
    df.to_csv(csv_path, index=False)
    print(f"  Saved raw results → {csv_path}")
    return df


# ── Statistics helpers ────────────────────────────────────────────────────────
def corr_summary(x: np.ndarray, y: np.ndarray) -> dict:
    mask = ~(np.isnan(x) | np.isnan(y))
    x, y = x[mask], y[mask]
    n = len(x)
    if n < 3:
        return dict(n=n, r=np.nan, p=np.nan, bias=np.nan)
    r, p = pearsonr(x, y)
    return dict(n=n, r=round(r, 4), p=p, bias=round(float(np.mean(y - x)), 3))


def ci95_str(vals: np.ndarray) -> str:
    from scipy.stats import t
    vals = vals[~np.isnan(vals)]
    n = len(vals)
    if n < 2:
        return "N/A"
    se = np.std(vals, ddof=1) / np.sqrt(n)
    t_crit = t.ppf(0.975, n - 1)
    mean_val = np.mean(vals)
    return f"[{mean_val - t_crit * se:.2f}, {mean_val + t_crit * se:.2f}]"


def fmt_p(p: float) -> str:
    if np.isnan(p):
        return "N/A"
    return "< 0.0001" if p < 0.0001 else f"{p:.4f}"


# ── Markdown table builders ───────────────────────────────────────────────────
def make_table1_md(cmp_df: pd.DataFrame) -> str:
    if cmp_df.empty:
        return ""

    metrics = [
        ("Peak voltage (mV)", "syn_peak_mV",  "efel_peak_mV",  "ipfx_peak_mV",  "mV"),
        ("AP half-width (ms)", "syn_hw_ms",   "efel_hw_ms",    "ipfx_hw_ms",    "ms"),
        ("Max dV/dt (V/s)",   "syn_maxdvdt",  "efel_maxdvdt",  "ipfx_maxdvdt",  "V/s"),
        ("Min dV/dt (V/s)",   "syn_mindvdt",  "efel_mindvdt",  "ipfx_mindvdt",  "V/s"),
    ]

    header = (
        "**Extended Data Table 1: Statistical summary of SynaptiPy AP extraction "
        "vs. eFEL and IPFX benchmarks (file: `2023_04_11_0021.abf`, per-sweep means).**\n\n"
        "| Metric | n sweeps | SynaptiPy vs IPFX Pearson *r* | SynaptiPy vs eFEL Pearson *r* "
        "| Mean bias vs IPFX | Mean bias vs eFEL | Statistical approach |\n"
        "|--------|----------|-------------------------------|-------------------------------|"
        "-------------------|-------------------|----------------------|\n"
    )
    rows_md = ""
    for label, s_col, e_col, i_col, unit in metrics:
        s = cmp_df[s_col].values.astype(float)
        e = cmp_df[e_col].values.astype(float)
        i = cmp_df[i_col].values.astype(float)

        vs_i = corr_summary(i, s)
        vs_e = corr_summary(e, s)

        r_i  = f"{vs_i['r']:.4f}" if not np.isnan(vs_i['r']) else "N/A"
        r_e  = f"{vs_e['r']:.4f}" if not np.isnan(vs_e['r']) else "N/A"
        b_i  = f"{vs_i['bias']:+.3f} {unit}"
        b_e  = f"{vs_e['bias']:+.3f} {unit}"
        n    = vs_i['n']

        rows_md += (
            f"| {label} | {n} | {r_i} (*p* {fmt_p(vs_i['p'])}) | "
            f"{r_e} (*p* {fmt_p(vs_e['p'])}) | {b_i} | {b_e} | "
            "Pearson correlation, two-sided *p* |\n"
        )

    footer = (
        "\n*n sweeps = number of sweeps in which all three pipelines detected ≥1 action potential. "
        "Bias = mean signed difference (SynaptiPy − benchmark, per-sweep means). "
        "SynaptiPy: BatchAnalysisEngine `spike_detection` (dV/dt threshold 20 V/s, refractory 2 ms). "
        "eFEL: BlueBrain eFEL defaults. IPFX: Allen IPFX SpikeFeatureExtractor, 9.9 kHz Bessel filter.*"
    )
    return header + rows_md + footer


def make_table2_md(df: pd.DataFrame) -> str:
    def stat_row(label: str, vals: np.ndarray, unit: str) -> str:
        vals = vals[~np.isnan(vals)]
        if len(vals) == 0:
            return f"| {label} | 0 | N/A | N/A | N/A | Descriptive only |\n"
        mean = np.mean(vals)
        sd   = np.std(vals, ddof=1) if len(vals) > 1 else 0.0
        ci   = ci95_str(vals)
        return (
            f"| {label} | {len(vals)} | {mean:.2f} {unit} "
            f"| {sd:.2f} {unit} | {ci} {unit} | Descriptive only |\n"
        )

    def numeric(col):
        return pd.to_numeric(df.get(col, pd.Series([])), errors="coerce").values

    rmp    = numeric("rmp_mv")
    ap_thr = numeric("ap_threshold_mean")
    ap_amp = numeric("amplitude_mean")
    ap_hw  = numeric("half_width_mean")

    header = (
        "**Extended Data Table 2: Passive membrane and AP properties from real recordings "
        "(examples/data/ ABF files, this study).**\n\n"
        "| Parameter | n trials | Mean | SD | 95% CI | Statistical approach |\n"
        "|-----------|---------|------|-----|--------|----------------------|\n"
    )
    rows_md = (
        stat_row("RMP (mV)",            rmp,    "mV")
        + stat_row("AP threshold (mV)", ap_thr, "mV")
        + stat_row("AP amplitude (mV)", ap_amp, "mV")
        + stat_row("AP half-width (ms)", ap_hw, "ms")
    )
    footer = (
        "\n*Values from BatchAnalysisEngine `rmp_analysis` + `spike_detection` "
        "on real patch-clamp ABF files (macOS M1, SynaptiPy v0.1.5b7). "
        "n trials = number of sweeps with valid measurements. "
        "95% CI = mean ± t × (SD / √n) computed using Student's t-distribution.*"
    )
    return header + rows_md + footer


# ── Write tables back into paper.md ──────────────────────────────────────────
def update_paper_md(t1_md: str, t2_md: str) -> None:
    paper_path = REPO_ROOT / "paper" / "paper.md"
    text = paper_path.read_text(encoding="utf-8")

    T1_START = "**Extended Data Table 1:"
    T1_START = "**Extended Data Table 1:"

    idx1s = text.find(T1_START)
    if idx1s == -1:
        print("  WARNING: Could not locate Table 1 placeholder in paper.md.")
        return

    import re
    # Find the next section heading (### or #) after T1_START
    match = re.search(r'\n#{1,3}\s', text[idx1s:])
    if match:
        end_idx = idx1s + match.start()
    else:
        end_idx = len(text)
        
    # Replace the chunk with both tables
    new_text = text[:idx1s] + t1_md + "\n\n" + t2_md + "\n" + text[end_idx:]
    paper_path.write_text(new_text, encoding="utf-8")
    print(f"  paper.md updated → {paper_path}")


# ── Main ──────────────────────────────────────────────────────────────────────
def main() -> None:
    print("=" * 60)
    print("SynaptiPy — generate_paper_tables.py")
    print("Computes real values for Extended Data Tables 1 & 2")
    print("=" * 60)

    cmp_df  = build_table1()
    prop_df = build_table2()

    t1_md = make_table1_md(cmp_df)
    t2_md = make_table2_md(prop_df)

    print("\n── Generated Table 1 Markdown ──")
    print(t1_md)
    print("\n── Generated Table 2 Markdown ──")
    print(t2_md)

    update_paper_md(t1_md, t2_md)
    print("\nDone.")


if __name__ == "__main__":
    main()
