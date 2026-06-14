import numpy as np
import efel
import matplotlib.pyplot as plt
from scipy.stats import pearsonr
from pathlib import Path
import warnings

from ipfx.feature_extractor import SpikeFeatureExtractor
from Synaptipy.infrastructure.file_readers import NeoAdapter
from Synaptipy.core.analysis.single_spike import detect_spikes_threshold, calculate_spike_features

def main():
    warnings.filterwarnings("ignore")
    repo_root = Path(__file__).resolve().parent.parent
    abf_path = repo_root / "examples" / "data" / "2023_04_11_0021.abf"
    
    if not abf_path.exists():
        print(f"File not found: {abf_path}")
        return

    # 1. Load Data
    adapter = NeoAdapter()
    rec = adapter.read_recording(str(abf_path))
    ch = list(rec.channels.values())[0]
    
    fs = ch.sampling_rate
    dt = 1.0 / fs
    
    metrics = {
        'Peak Voltage': {'s': [], 'e': [], 'i': []},
        'Half-Width': {'s': [], 'e': [], 'i': []},
        'Max dV/dt': {'s': [], 'e': [], 'i': []},
        'Min dV/dt': {'s': [], 'e': [], 'i': []}
    }

    # IPFX initialization
    ipfx_ext = SpikeFeatureExtractor(start=0.01, end=0.49, filter=9.9)

    # Process each trial (sweep)
    for trial in ch.data_trials:
        v = np.asarray(trial, dtype=np.float64)
        t = np.arange(len(v)) * dt
        
        # --- SynaptiPy Analysis ---
        spikes = detect_spikes_threshold(v, t, threshold=-20.0, refractory_samples=int(0.005*fs))
        
        # --- eFEL Analysis ---
        trace = {
            'T': t * 1000.0,  # eFEL expects ms
            'V': v,           # mV
            'stim_start': [10.0],
            'stim_end': [490.0]
        }
        efel_features = ['peak_voltage', 'AP_duration_half_width', 'AP_rise_rate', 'AP_fall_rate']
        efel_res = efel.get_feature_values([trace], efel_features)
        
        # --- IPFX Analysis ---
        ipfx_res = ipfx_ext.process(t, v, np.zeros_like(v))
        
        if spikes.value > 0 and efel_res and efel_res[0] and not ipfx_res.empty:
            features_list = calculate_spike_features(v, t, spikes.spike_indices)
            r = efel_res[0]
            
            # eFEL
            e_peaks = r.get('peak_voltage', [])
            e_hws = r.get('AP_duration_half_width', [])
            e_maxdvs = r.get('AP_rise_rate', [])
            e_mindvs = r.get('AP_fall_rate', [])
            
            if e_peaks is None: e_peaks = []
            if e_hws is None: e_hws = []
            if e_maxdvs is None: e_maxdvs = []
            if e_mindvs is None: e_mindvs = []
            
            # IPFX
            i_peaks = ipfx_res['peak_v'].values
            i_hws = ipfx_res['width'].values * 1000.0  # s to ms
            i_maxdvs = ipfx_res['upstroke'].values
            i_mindvs = ipfx_res['downstroke'].values
            
            n_spikes = min(len(features_list), len(e_peaks), len(e_hws), len(e_maxdvs), len(e_mindvs), len(i_peaks))
            
            for i in range(n_spikes):
                s_peak = v[spikes.spike_indices[i]]
                s_hw = features_list[i].get('half_width', np.nan)
                s_maxdv = features_list[i].get('max_dvdt', np.nan)
                s_mindv = features_list[i].get('min_dvdt', np.nan)
                
                if not np.isnan(s_hw) and not np.isnan(s_maxdv) and not np.isnan(s_mindv):
                    # Peak V
                    metrics['Peak Voltage']['s'].append(s_peak)
                    metrics['Peak Voltage']['e'].append(e_peaks[i])
                    metrics['Peak Voltage']['i'].append(i_peaks[i])
                    
                    # Half-Width
                    metrics['Half-Width']['s'].append(s_hw)
                    metrics['Half-Width']['e'].append(e_hws[i])
                    metrics['Half-Width']['i'].append(i_hws[i])
                    
                    # Max dV/dt
                    metrics['Max dV/dt']['s'].append(s_maxdv)
                    metrics['Max dV/dt']['e'].append(e_maxdvs[i])
                    metrics['Max dV/dt']['i'].append(i_maxdvs[i])
                    
                    # Min dV/dt
                    metrics['Min dV/dt']['s'].append(s_mindv)
                    metrics['Min dV/dt']['e'].append(e_mindvs[i])
                    metrics['Min dV/dt']['i'].append(i_mindvs[i])

    if not metrics['Peak Voltage']['s']:
        print("No spikes detected for validation!")
        return

    from plot_utils import set_paper_styles, add_panel_label, COLORS
    set_paper_styles()

    fig, axes = plt.subplots(2, 2, figsize=(12, 11))
    axes = axes.flatten()
    
    panel_labels = ['A', 'B', 'C', 'D']
    units = ['mV', 'ms', 'V/s', 'V/s']
    
    stats_output = []

    def format_p(p):
        if p < 0.0001: return "< 0.0001"
        return f"= {p:.4f}"

    for i, (name, data) in enumerate(metrics.items()):
        ax = axes[i]
        
        y_syn = np.array(data['s'])
        x_efel = np.array(data['e'])
        x_ipfx = np.array(data['i'])
        
        # Calculate statistics
        r_e, p_e = pearsonr(x_efel, y_syn)
        mb_e = np.mean(y_syn - x_efel)
        
        r_i, p_i = pearsonr(x_ipfx, y_syn)
        mb_i = np.mean(y_syn - x_ipfx)
        
        stats_output.append(f"{name} (eFEL): r={r_e:.4f}, p={p_e:.4e}, Bias={mb_e:.4f}")
        stats_output.append(f"{name} (IPFX): r={r_i:.4f}, p={p_i:.4e}, Bias={mb_i:.4f}")

        # Scatter plot
        ax.scatter(x_efel, y_syn, color=COLORS["blue"], alpha=0.7, s=50, edgecolor='k', label='eFEL')
        ax.scatter(x_ipfx, y_syn, color=COLORS["orange"], alpha=0.7, s=50, edgecolor='k', label='IPFX', marker='^')
        
        # Unity line
        min_val = min(np.min(x_efel), np.min(x_ipfx), np.min(y_syn))
        max_val = max(np.max(x_efel), np.max(x_ipfx), np.max(y_syn))
        padding = (max_val - min_val) * 0.1
        min_val -= padding
        max_val += padding
        
        ax.plot([min_val, max_val], [min_val, max_val], 'k--', alpha=0.5)
        
        # Linear fits
        me, be = np.polyfit(x_efel, y_syn, 1)
        ax.plot([min_val, max_val], [me*min_val+be, me*max_val+be], color=COLORS["blue"], alpha=0.5)
        
        mi, bi = np.polyfit(x_ipfx, y_syn, 1)
        ax.plot([min_val, max_val], [mi*min_val+bi, mi*max_val+bi], color=COLORS["orange"], alpha=0.5)

        ax.set_xlabel(f"Benchmark {name} ({units[i]})", fontsize=11)
        ax.set_ylabel(f"SynaptiPy {name} ({units[i]})", fontsize=11)
        
        # Add Panel Label
        add_panel_label(ax, panel_labels[i])

        # Text box for stats
        stats_text = (
            f"eFEL: Pearson $r$ = {r_e:.4f} ($p$ = {format_p(p_e)}) | Bias = {mb_e:.2f} {units[i]}\n"
            f"IPFX: Pearson $r$ = {r_i:.4f} ($p$ = {format_p(p_i)}) | Bias = {mb_i:.2f} {units[i]}"
        )
        ax.text(0.05, 0.95, stats_text, transform=ax.transAxes, va='top', ha='left',
                bbox=dict(boxstyle='round', facecolor='white', alpha=0.8, edgecolor='#E0E0E0'), fontsize=9)
        
        ax.legend(loc='lower right')

    # Save
    out_path = repo_root / "paper" / "results" / "biological_validation.png"
    fig.tight_layout()
    fig.savefig(out_path, dpi=300)
    
    print("Validation Complete. Statistics:")
    for s in stats_output:
        print(s)
    print(f"\nSaved plot to {out_path}")

if __name__ == "__main__":
    main()
