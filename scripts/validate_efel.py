import numpy as np
import efel
import matplotlib.pyplot as plt
from scipy.stats import pearsonr
from pathlib import Path

from Synaptipy.infrastructure.file_readers import NeoAdapter
from Synaptipy.core.analysis.single_spike import detect_spikes_threshold, calculate_spike_features

def main():
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
        'Peak Voltage': {'s': [], 'e': []},
        'Half-Width': {'s': [], 'e': []},
        'Max dV/dt': {'s': [], 'e': []},
        'Min dV/dt': {'s': [], 'e': []}
    }

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
            'stim_start': [100.0],
            'stim_end': [900.0]
        }
        efel_features = ['peak_voltage', 'AP_duration_half_width', 'AP_rise_rate', 'AP_fall_rate']
        efel_res = efel.get_feature_values([trace], efel_features)
        
        if spikes.value > 0 and efel_res and efel_res[0]:
            features_list = calculate_spike_features(v, t, spikes.spike_indices)
            r = efel_res[0]
            
            # Match spikes between SynaptiPy and eFEL
            # They should detect the same number of spikes, but let's be safe and zip up to min count
            e_peaks = r.get('peak_voltage', [])
            e_hws = r.get('AP_duration_half_width', [])
            e_maxdvs = r.get('AP_rise_rate', [])
            e_mindvs = r.get('AP_fall_rate', [])
            
            if e_peaks is None: e_peaks = []
            if e_hws is None: e_hws = []
            if e_maxdvs is None: e_maxdvs = []
            if e_mindvs is None: e_mindvs = []
            
            n_spikes = min(len(features_list), len(e_peaks), len(e_hws), len(e_maxdvs), len(e_mindvs))
            
            for i in range(n_spikes):
                s_peak = v[spikes.spike_indices[i]]
                s_hw = features_list[i].get('half_width', np.nan)
                s_maxdv = features_list[i].get('max_dvdt', np.nan)
                s_mindv = features_list[i].get('min_dvdt', np.nan)
                
                if not np.isnan(s_hw) and not np.isnan(s_maxdv) and not np.isnan(s_mindv):
                    metrics['Peak Voltage']['e'].append(e_peaks[i])
                    metrics['Peak Voltage']['s'].append(s_peak)
                    
                    metrics['Half-Width']['e'].append(e_hws[i])
                    metrics['Half-Width']['s'].append(s_hw)
                    
                    metrics['Max dV/dt']['e'].append(e_maxdvs[i])
                    metrics['Max dV/dt']['s'].append(s_maxdv)
                    
                    metrics['Min dV/dt']['e'].append(e_mindvs[i])
                    metrics['Min dV/dt']['s'].append(s_mindv)

    if not metrics['Peak Voltage']['s']:
        print("No spikes detected for validation!")
        return

    # Apply eNeuro plotting styles
    plt.rcParams['font.family'] = 'sans-serif'
    plt.rcParams['font.sans-serif'] = ['Arial', 'Helvetica', 'DejaVu Sans']
    plt.rcParams['axes.spines.top'] = False
    plt.rcParams['axes.spines.right'] = False

    fig, axes = plt.subplots(2, 2, figsize=(10, 10))
    axes = axes.flatten()
    
    panel_labels = ['A', 'B', 'C', 'D']
    units = ['mV', 'ms', 'V/s', 'V/s']
    
    stats_output = []

    for i, (name, data) in enumerate(metrics.items()):
        ax = axes[i]
        
        x = np.array(data['e'])
        y = np.array(data['s'])
        
        # Calculate statistics
        r, p = pearsonr(x, y)
        mean_bias = np.mean(y - x)
        std_bias = np.std(y - x)
        
        stats_output.append(f"{name}: Pearson r={r:.4f}, p={p:.4e}, Bias={mean_bias:.4f} {units[i]}")

        # Scatter plot
        ax.scatter(x, y, color='#1565C0', alpha=0.7, s=50, edgecolor='k')
        
        # Unity line
        min_val = min(np.min(x), np.min(y))
        max_val = max(np.max(x), np.max(y))
        padding = (max_val - min_val) * 0.1
        min_val -= padding
        max_val += padding
        
        ax.plot([min_val, max_val], [min_val, max_val], 'k--', alpha=0.5)
        
        # Linear fit
        m, b = np.polyfit(x, y, 1)
        ax.plot([min_val, max_val], [m*min_val+b, m*max_val+b], color='#B71C1C')

        ax.set_xlabel(f"eFEL {name} ({units[i]})", fontsize=11)
        ax.set_ylabel(f"SynaptiPy {name} ({units[i]})", fontsize=11)
        
        # Add Panel Label (A, B, C, D)
        ax.text(-0.15, 1.05, panel_labels[i], transform=ax.transAxes, 
                fontsize=16, fontweight='bold', va='top', ha='right')

        # Format p-value to decimal notation
        if p < 0.0001:
            p_str = "< 0.0001"
        else:
            p_str = f"= {p:.4f}"

        # Text box for stats
        stats_text = f"$r$ = {r:.4f} ($p {p_str}$)\nBias = {mean_bias:.2f} {units[i]}"
        ax.text(0.05, 0.95, stats_text, transform=ax.transAxes, va='top', ha='left',
                bbox=dict(boxstyle='round', facecolor='white', alpha=0.8, edgecolor='#E0E0E0'))

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
