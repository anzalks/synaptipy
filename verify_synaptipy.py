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
from Synaptipy.core.analysis.registry import AnalysisRegistry
from Synaptipy.infrastructure.exporters.csv_exporter import CSVExporter
from Synaptipy.application.gui.analysis_tabs.event_detection_tab import EventDetectionTab
from Synaptipy.application.gui.analysis_tabs.base import BaseAnalysisTab

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
log = logging.getLogger(__name__)

def verify_components():
    """Verify that new components are correctly integrated."""
    log.info("--- Verifying Components ---")
    
    # 1. Check Analysis Registry
    log.info("Checking AnalysisRegistry...")
    functions = AnalysisRegistry.list_registered()
    log.info(f"Registered functions: {functions}")
    expected_funcs = ["event_detection_threshold", "event_detection_deconvolution", "event_detection_baseline_peak"]
    for func in expected_funcs:
        if func not in functions:
            log.error(f"Missing registered function: {func}")
        else:
            log.info(f"Found registered function: {func}")
            
    # 2. Check CSVExporter
    log.info("Checking CSVExporter...")
    try:
        exporter = CSVExporter()
        log.info("CSVExporter instantiated successfully.")
    except Exception as e:
        log.error(f"Failed to instantiate CSVExporter: {e}")

    # 3. Check EventDetectionTab
    log.info("Checking EventDetectionTab...")
    if issubclass(EventDetectionTab, BaseAnalysisTab):
        log.info("EventDetectionTab is a subclass of BaseAnalysisTab.")
    else:
        log.error("EventDetectionTab is NOT a subclass of BaseAnalysisTab.")
        
    if hasattr(EventDetectionTab, 'ANALYSIS_TAB_CLASS') and EventDetectionTab.ANALYSIS_TAB_CLASS:
        log.info("EventDetectionTab has ANALYSIS_TAB_CLASS constant.")
    else:
        log.error("EventDetectionTab missing ANALYSIS_TAB_CLASS constant.")

    # 4. Check NeoAdapter Extensions
    log.info("Checking NeoAdapter extensions...")
    adapter = NeoAdapter()
    if hasattr(adapter, 'get_supported_extensions'):
        exts = adapter.get_supported_extensions()
        log.info(f"NeoAdapter supports {len(exts)} extensions: {exts[:5]}...")
        if 'abf' in exts and 'dat' in exts:
            log.info("Verified presence of common extensions (abf, dat).")
        else:
            log.warning("Common extensions missing from supported list.")
    else:
        log.error("NeoAdapter missing get_supported_extensions method.")

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
    verify_components()

    examples_dir = Path("examples/data")
    output_dir = Path("verification_output")
    output_dir.mkdir(exist_ok=True)
    
    files = list(examples_dir.glob("*.abf")) + list(examples_dir.glob("*.wcp"))
    
    if not files:
        log.warning("No example files found! Skipping batch analysis.")
        return
    
    log.info(f"Found {len(files)} files to verify.")
    
    # Initialize Engine
    engine = BatchAnalysisEngine()
    
    # Config
    # Config (New List Format)
    config = [
        {
            'analysis': 'spike_detection',
            'scope': 'all_trials',
            'params': {
                'threshold': -20.0,
                'refractory_ms': 2.0
            }
        }
    ]
    
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
        f.write(df.to_string(index=False))
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
