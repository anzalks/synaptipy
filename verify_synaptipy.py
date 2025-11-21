"""
Verification script for Synaptipy.
Runs batch analysis on example data and generates a report.
"""
import logging
import sys
import os
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

# Add src to path
sys.path.append(os.path.abspath("src"))

from Synaptipy.core.analysis.batch_engine import BatchAnalysisEngine
from Synaptipy.infrastructure.file_readers import NeoAdapter

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
log = logging.getLogger(__name__)

def generate_plots(file_path, output_dir):
    """Generate plots for a file to simulate screen grabs."""
    adapter = NeoAdapter()
    recording = adapter.read_recording(file_path)
    
    if not recording:
        return []
    
    plot_paths = []
    
    for i, (name, channel) in enumerate(recording.channels.items()):
        if i > 0: break # Just plot first channel
        
        plt.figure(figsize=(10, 6))
        
        # Plot first trial
        if channel.data_trials:
            data = channel.data_trials[0]
            time = channel.get_time_vector(0)
            
            plt.plot(time, data, label=f"Sweep 1")
            plt.title(f"Trace: {file_path.name} - {name}")
            plt.xlabel("Time (s)")
            plt.ylabel(f"Signal ({channel.units})")
            plt.legend()
            plt.grid(True, alpha=0.3)
            
            out_name = f"plot_{file_path.stem}_{name}.png"
            out_path = output_dir / out_name
            plt.savefig(out_path)
            plt.close()
            plot_paths.append(out_path)
            
    return plot_paths

def main():
    examples_dir = Path("examples/data")
    output_dir = Path("verification_output")
    output_dir.mkdir(exist_ok=True)
    
    files = list(examples_dir.glob("*.abf")) + list(examples_dir.glob("*.wcp"))
    
    if not files:
        log.error("No example files found!")
        return
    
    log.info(f"Found {len(files)} files to verify.")
    
    # Initialize Engine
    engine = BatchAnalysisEngine()
    
    # Config
    config = {
        'spike_detection': {
            'enabled': True,
            'threshold': -20.0, # Guessing a threshold
            'refractory_ms': 2.0
        },
        'rin': {
            'enabled': False # Rin needs specific windows, hard to automate without metadata
        }
    }
    
    # Run Batch
    log.info("Running batch analysis...")
    df = engine.run_batch(files, config, progress_callback=lambda c, t, m: print(f"[{c}/{t}] {m}"))
    
    # Generate Plots for first file
    log.info("Generating plots...")
    plot_files = generate_plots(files[0], output_dir)
    
    # Write Report
    report_path = output_dir / "verification_report.md"
    with open(report_path, "w") as f:
        f.write("# Synaptipy Verification Report\n\n")
        f.write(f"**Date:** {pd.Timestamp.now()}\n\n")
        f.write("## Analysis Results\n\n")
        f.write(df.to_markdown(index=False))
        f.write("\n\n")
        
        f.write("## Visualizations\n\n")
        for p in plot_files:
            # Use relative path for markdown
            rel_path = p.name
            f.write(f"![{rel_path}]({rel_path})\n\n")
            
    log.info(f"Verification complete. Report saved to {report_path}")
    print(f"REPORT_PATH:{report_path}")

if __name__ == "__main__":
    main()
