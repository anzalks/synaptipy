import sys
import warnings
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.stats import pearsonr, t
import pyabf

# Provide access to src/
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from Synaptipy.core.analysis.batch_engine import BatchAnalysisEngine

DATA_DIR = REPO_ROOT / "examples" / "data"
OUT_DIR = REPO_ROOT / "paper" / "results"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ── Stats Helpers ─────────────────────────────────────────────────────────────

def corr_summary(x: np.ndarray, y: np.ndarray) -> dict:
    mask = ~(np.isnan(x) | np.isnan(y))
    x, y = x[mask], y[mask]
    n = len(x)
    if n < 3:
        return dict(n=n, r=np.nan, p=np.nan, bias=np.nan)
    r, p = pearsonr(x, y)
    return dict(n=n, r=round(r, 4), p=p, bias=round(float(np.mean(y - x)), 3))

def ci95_str(vals: np.ndarray) -> str:
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

# ── Runners ───────────────────────────────────────────────────────────────────

class SynaptiPyRunner:
    @staticmethod
    def run_spikes(file_path: Path) -> pd.DataFrame:
        engine = BatchAnalysisEngine(max_workers=1)
        pipeline = [{
            "analysis": "spike_detection",
            "scope": "all_trials",
            "params": {"threshold": -20.0, "refractory_period": 0.002, "dvdt_threshold": 20.0}
        }]
        return engine.run_batch([file_path], pipeline)

    @staticmethod
    def run_passive(file_path: Path) -> pd.DataFrame:
        abf = pyabf.ABF(file_path)
        abf.setSweep(0)
        i = abf.sweepC
        t = abf.sweepX
        stim_starts = np.where(np.diff(i) < -5)[0]
        stim_ends = np.where(np.diff(i) > 5)[0]
        
        if len(stim_starts) == 0 or len(stim_ends) == 0:
            s_t, e_t = 0.15, 0.65
        else:
            s_t = float(t[stim_starts[0]])
            e_t = float(t[stim_ends[0]])

        engine = BatchAnalysisEngine(max_workers=1)
        pipeline = [
            {
                "analysis": "rmp_analysis",
                "scope": "all_trials",
                "params": {"baseline_start": max(0.0, s_t - 0.2), "baseline_end": max(0.01, s_t - 0.01)},
            },
            {
                "analysis": "rin_analysis",
                "scope": "all_trials",
                "params": {
                    "baseline_start": max(0.0, s_t - 0.1),
                    "baseline_end": max(0.01, s_t - 0.01),
                    "response_start": max(s_t + 0.01, e_t - 0.15),
                    "response_end": max(s_t + 0.02, e_t - 0.01),
                    "current_amplitude": -20.0,
                },
            },
            {
                "analysis": "tau_analysis",
                "scope": "all_trials",
                "params": {"stim_start_time": s_t, "fit_duration": 0.05, "model": "mono"}
            }
        ]
        return engine.run_batch([file_path], pipeline)

class EFELRunner:
    @staticmethod
    def run_sweep_spikes(v: np.ndarray, t: np.ndarray) -> dict:
        import efel
        trace = {"T": t * 1000.0, "V": v, "stim_start": [t[0] * 1000.0], "stim_end": [t[-1] * 1000.0]}
        want = ["peak_voltage", "AP_duration_half_width", "AP_rise_rate", "AP_fall_rate", "AP_begin_voltage", "AP_amplitude", "fast_AHP", "ADP_peak_amplitude"]
        res = efel.get_feature_values([trace], want)
        r = res[0] if res else {}
        out = {"n_spikes": len(r.get("peak_voltage", []))}
        for k in want:
            vals = r.get(k)
            out[k] = float(np.mean(vals)) if (vals is not None and len(vals) > 0) else np.nan
        return out

    @staticmethod
    def run_sweep_passive(v: np.ndarray, i: np.ndarray, t: np.ndarray) -> dict:
        import efel
        stim_starts = np.where(np.diff(i) < -5)[0]
        stim_ends = np.where(np.diff(i) > 5)[0]
        if len(stim_starts) == 0 or len(stim_ends) == 0:
            return {}
        
        s_idx = stim_starts[0]
        e_idx = stim_ends[0]
        stim_amp = np.mean(i[s_idx+10:e_idx-10]) - np.mean(i[:s_idx-10])
        
        trace = {
            "T": t * 1000.0,
            "V": v,
            "stim_start": [t[s_idx] * 1000.0],
            "stim_end": [t[e_idx] * 1000.0],
            "stimulus_current": [stim_amp]
        }
        
        want = ["voltage_base", "ohmic_input_resistance", "time_constant"]
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
            return {"n_spikes": 0, "peak_v": np.nan, "width_ms": np.nan, "upstroke": np.nan, "downstroke": np.nan, "threshold_v": np.nan, "amplitude": np.nan, "fast_ahp": np.nan, "adp_amp": np.nan}
        return {
            "n_spikes":    len(result),
            "peak_v":      float(result["peak_v"].mean()),
            "width_ms":    float(result["width"].mean()) * 1000.0,
            "upstroke":    float(result["upstroke"].mean()),
            "downstroke":  float(result["downstroke"].mean()),
            "threshold_v": float(result["threshold_v"].mean()),
            "amplitude":   float((result["peak_v"] - result["threshold_v"]).mean()),
            "fast_ahp":    float((result["threshold_v"] - result["fast_trough_v"]).mean()),
            "adp_amp":     float((result["adp_v"] - result["fast_trough_v"]).mean()),
        }

    @staticmethod
    def run_sweep_passive(v: np.ndarray, i: np.ndarray, t: np.ndarray) -> dict:
        import ipfx.subthresh_features as subT
        stim_starts = np.where(np.diff(i) < -5)[0]
        stim_ends = np.where(np.diff(i) > 5)[0]
        if len(stim_starts) == 0 or len(stim_ends) == 0:
            return {}
            
        start_t = t[stim_starts[0]]
        end_t = t[stim_ends[0]]
        
        out = {}
        try:
            out["v_baseline"] = float(subT.baseline_voltage(t, v, start_t))
            rin = subT.input_resistance([t], [i], [v], start_t, end_t)
            tau = subT.time_constant(t, v, i, start_t, end_t)
            out["input_resistance"] = float(rin)
            out["tau"] = float(tau) * 1000.0
        except Exception:
            pass
        return out

# ── Builders ──────────────────────────────────────────────────────────────────

def build_table1() -> pd.DataFrame:
    file_path = DATA_DIR / "2023_04_11_0021.abf"
    syn_df = SynaptiPyRunner.run_spikes(file_path)
    abf = pyabf.ABF(file_path)
    sr = abf.dataRate
    dt = 1.0 / sr

    rows = []
    for _, row in syn_df.iterrows():
        t_idx = int(row.get("trial_index", 0))
        n_syn = int(row.get("spike_count", 0))
        if n_syn == 0 or t_idx >= abf.sweepCount: continue
        
        abf.setSweep(t_idx)
        v = abf.sweepY
        t = np.arange(len(v)) * dt

        efel_r = EFELRunner.run_sweep_spikes(v, t)
        ipfx_r = IPFXRunner.run_sweep_spikes(v, t)
        if efel_r["n_spikes"] == 0 or ipfx_r["n_spikes"] == 0: continue

        rows.append({
            "trial": t_idx,
            "syn_peak_mV":   float(row.get("absolute_peak_mv_mean", np.nan)),
            "efel_peak_mV":  efel_r.get("peak_voltage", np.nan),
            "ipfx_peak_mV":  ipfx_r.get("peak_v", np.nan),
            "syn_thr_mV":    float(row.get("ap_threshold_mean", np.nan)),
            "efel_thr_mV":   efel_r.get("AP_begin_voltage", np.nan),
            "ipfx_thr_mV":   ipfx_r.get("threshold_v", np.nan),
            "syn_amp_mV":    float(row.get("amplitude_mean", np.nan)),
            "efel_amp_mV":   efel_r.get("AP_amplitude", np.nan),
            "ipfx_amp_mV":   ipfx_r.get("amplitude", np.nan),
            "syn_hw_ms":     float(row.get("half_width_mean", np.nan)),
            "efel_hw_ms":    efel_r.get("AP_duration_half_width", np.nan),
            "ipfx_hw_ms":    ipfx_r.get("width_ms", np.nan),
            "syn_maxdvdt":   float(row.get("max_dvdt_mean", np.nan)),
            "efel_maxdvdt":  efel_r.get("AP_rise_rate", np.nan),
            "ipfx_maxdvdt":  ipfx_r.get("upstroke", np.nan),
            "syn_mindvdt":   float(row.get("min_dvdt_mean", np.nan)),
            "efel_mindvdt":  efel_r.get("AP_fall_rate", np.nan),
            "ipfx_mindvdt":  ipfx_r.get("downstroke", np.nan),
            "syn_fahp_mV":   float(row.get("fahp_depth_mean", np.nan)),
            "efel_fahp_mV":  efel_r.get("fast_AHP", np.nan),
            "ipfx_fahp_mV":  ipfx_r.get("fast_ahp", np.nan),
            "syn_adp_mV":    float(row.get("adp_amplitude_mean", np.nan)),
            "efel_adp_mV":   efel_r.get("ADP_peak_amplitude", np.nan),
            "ipfx_adp_mV":   ipfx_r.get("adp_amp", np.nan),
        })
    df = pd.DataFrame(rows)
    df.to_csv(OUT_DIR / "benchmark_comparison.csv", index=False)
    return df

def build_table2() -> pd.DataFrame:
    files = [DATA_DIR / "2023_04_11_0019.abf", DATA_DIR / "2023_04_11_0022.abf"]
    rows = []
    
    for file_path in files:
        syn_df = SynaptiPyRunner.run_passive(file_path)
        abf = pyabf.ABF(file_path)
        dt = 1.0 / abf.dataRate
        
        for _, row in syn_df.iterrows():
            t_idx = int(row.get("trial_index", 0))
            if t_idx >= abf.sweepCount: continue
            
            abf.setSweep(t_idx)
            v = abf.sweepY
            i = abf.sweepC
            t = np.arange(len(v)) * dt
            
            # Verify it's a -20pA step
            if not any(i < -15): continue
            
            efel_r = EFELRunner.run_sweep_passive(v, i, t)
            ipfx_r = IPFXRunner.run_sweep_passive(v, i, t)
            
            rows.append({
                "trial": t_idx,
                "file": file_path.name,
                "syn_rmp_mV": float(row.get("rmp_mv", np.nan)),
                "efel_rmp_mV": efel_r.get("voltage_base", np.nan),
                "ipfx_rmp_mV": ipfx_r.get("v_baseline", np.nan),
                
                "syn_rin_mohm": float(row.get("rin_mohm", np.nan)),
                "efel_rin_mohm": efel_r.get("ohmic_input_resistance", np.nan),
                "ipfx_rin_mohm": ipfx_r.get("input_resistance", np.nan),
                
                "syn_tau_ms": float(row.get("tau_ms", np.nan)),
                "efel_tau_ms": efel_r.get("time_constant", np.nan),
                "ipfx_tau_ms": ipfx_r.get("tau", np.nan),
            })
            
    df = pd.DataFrame(rows)
    df.to_csv(OUT_DIR / "passive_properties.csv", index=False)
    return df

# ── Render Markdown ───────────────────────────────────────────────────────────

def make_table1_md(cmp_df: pd.DataFrame) -> str:
    metrics = [
        ("Peak voltage (mV)", "syn_peak_mV",  "efel_peak_mV",  "ipfx_peak_mV",  "mV"),
        ("AP threshold (mV)", "syn_thr_mV",   "efel_thr_mV",   "ipfx_thr_mV",   "mV"),
        ("AP amplitude (mV)", "syn_amp_mV",   "efel_amp_mV",   "ipfx_amp_mV",   "mV"),
        ("AP half-width (ms)", "syn_hw_ms",   "efel_hw_ms",    "ipfx_hw_ms",    "ms"),
        ("Max dV/dt (V/s)",   "syn_maxdvdt",  "efel_maxdvdt",  "ipfx_maxdvdt",  "V/s"),
        ("Min dV/dt (V/s)",   "syn_mindvdt",  "efel_mindvdt",  "ipfx_mindvdt",  "V/s"),
        ("Fast AHP depth (mV)", "syn_fahp_mV",  "efel_fahp_mV",  "ipfx_fahp_mV",  "mV"),
        ("ADP amplitude (mV)", "syn_adp_mV",   "efel_adp_mV",   "ipfx_adp_mV",   "mV"),
    ]
    md = "**Extended Data Table 1: Statistical summary of SynaptiPy AP extraction vs. eFEL and IPFX benchmarks (file: `2023_04_11_0021.abf`, per-sweep means).**\n\n"
    md += "| Metric | n sweeps | SynaptiPy vs IPFX Pearson *r* | SynaptiPy vs eFEL Pearson *r* | Mean bias vs IPFX | Mean bias vs eFEL | Statistical approach |\n"
    md += "|--------|----------|-------------------------------|-------------------------------|-------------------|-------------------|----------------------|\n"
    for label, s_col, e_col, i_col, unit in metrics:
        s, e, i = cmp_df[s_col].values, cmp_df[e_col].values, cmp_df[i_col].values
        vs_i, vs_e = corr_summary(i, s), corr_summary(e, s)
        n = max(vs_i['n'], vs_e['n'])
        r_i = f"{vs_i['r']:.4f}" if not np.isnan(vs_i['r']) else "N/A"
        r_e = f"{vs_e['r']:.4f}" if not np.isnan(vs_e['r']) else "N/A"
        b_i = f"{vs_i['bias']:+.3f} {unit}" if not np.isnan(vs_i['bias']) else "N/A"
        b_e = f"{vs_e['bias']:+.3f} {unit}" if not np.isnan(vs_e['bias']) else "N/A"
        md += f"| {label} | {n} | {r_i} (*p* {fmt_p(vs_i['p'])}) | {r_e} (*p* {fmt_p(vs_e['p'])}) | {b_i} | {b_e} | Pearson correlation, two-sided *p* |\n"
    
    md += "\n*n sweeps = number of sweeps in which all three pipelines detected ≥1 action potential. Bias = mean signed difference (SynaptiPy − benchmark, per-sweep means). SynaptiPy: BatchAnalysisEngine `spike_detection` (dV/dt threshold 20 V/s, refractory 2 ms). eFEL: BlueBrain eFEL defaults. IPFX: Allen IPFX SpikeFeatureExtractor, 9.9 kHz Bessel filter.*"
    return md

def make_table2_md(cmp_df: pd.DataFrame) -> str:
    metrics = [
        ("Resting Membrane Potential (mV)", "syn_rmp_mV",  "efel_rmp_mV",  "ipfx_rmp_mV",  "mV"),
        ("Input Resistance (MΩ)",           "syn_rin_mohm", "efel_rin_mohm","ipfx_rin_mohm", "MΩ"),
        ("Membrane Time Constant (ms)",     "syn_tau_ms",   "efel_tau_ms",  "ipfx_tau_ms",   "ms"),
    ]
    md = "**Extended Data Table 2: Subthreshold passive properties benchmark on -20 pA steps (files: `2023_04_11_0019.abf`, `0022.abf`).**\n\n"
    md += "| Metric | n sweeps | SynaptiPy vs IPFX Pearson *r* | SynaptiPy vs eFEL Pearson *r* | Mean bias vs IPFX | Mean bias vs eFEL | Statistical approach |\n"
    md += "|--------|----------|-------------------------------|-------------------------------|-------------------|-------------------|----------------------|\n"
    for label, s_col, e_col, i_col, unit in metrics:
        s, e, i = cmp_df[s_col].values, cmp_df[e_col].values, cmp_df[i_col].values
        vs_i, vs_e = corr_summary(i, s), corr_summary(e, s)
        n = len(s[~np.isnan(s)])
        r_i = f"{vs_i['r']:.4f}" if not np.isnan(vs_i['r']) else "N/A"
        r_e = f"{vs_e['r']:.4f}" if not np.isnan(vs_e['r']) else "N/A"
        b_i = f"{vs_i['bias']:+.3f} {unit}" if not np.isnan(vs_i['bias']) else "N/A"
        b_e = f"{vs_e['bias']:+.3f} {unit}" if not np.isnan(vs_e['bias']) else "N/A"
        md += f"| {label} | {n} | {r_i} (*p* {fmt_p(vs_i['p'])}) | {r_e} (*p* {fmt_p(vs_e['p'])}) | {b_i} | {b_e} | Pearson correlation, two-sided *p* |\n"
    
    md += "\n*n sweeps = number of valid sweeps containing a -20 pA hyperpolarizing current injection step. SynaptiPy passive properties extracted via BatchAnalysisEngine using `rmp_analysis`, `rin_analysis`, and `tau_analysis` modules. IPFX extraction via `subthresh_features`.*"
    return md

def main():
    print("=" * 60)
    print("SynaptiPy — generate_paper_tables.py (Modular Runner)")
    print("Computes Extended Data Tables 1 (Active) & 2 (Passive)")
    print("=" * 60)
    
    t1_df = build_table1()
    t1_md = make_table1_md(t1_df)
    print("Generated Table 1 Markdown.")
    
    t2_df = build_table2()
    t2_md = make_table2_md(t2_df)
    print("Generated Table 2 Markdown.")
    
    paper_path = REPO_ROOT / "paper" / "paper.md"
    text = paper_path.read_text(encoding="utf-8")
    
    T1_START = "**Extended Data Table 1:"
    idx1s = text.find(T1_START)
    import re
    match = re.search(r'\n#{1,3}\s', text[idx1s:])
    end_idx = idx1s + match.start() if match else len(text)
    
    new_text = text[:idx1s] + t1_md + "\n\n" + t2_md + "\n\n" + text[end_idx:]
    paper_path.write_text(new_text, encoding="utf-8")
    print(f"Success! Updated paper at {paper_path}")

if __name__ == "__main__":
    main()
