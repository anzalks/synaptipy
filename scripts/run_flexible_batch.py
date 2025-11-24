#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Demonstration script for the flexible batch analysis system.

This script shows how to use the registry-based pipeline architecture
to run multiple analyses on different data scopes.
"""
import sys
from pathlib import Path

# Add the src directory to the path so we can import Synaptipy
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from Synaptipy.core.analysis.batch_engine import BatchAnalysisEngine
from Synaptipy.core.analysis.registry import AnalysisRegistry

# Import analysis modules to trigger registration
import Synaptipy.core.analysis.spike_analysis  # noqa: F401


def main():
    """Run flexible batch analysis demonstration."""
    print("=" * 70)
    print("Flexible Batch Analysis Demonstration")
    print("=" * 70)
    
    # Show registered analysis functions
    print("\nRegistered analysis functions:")
    registered = AnalysisRegistry.list_registered()
    for name in registered:
        print(f"  - {name}")
    
    if not registered:
        print("  (No functions registered yet)")
        return
    
    # Define the pipeline configuration
    # This demonstrates running the same analysis (spike_detection) on different scopes
    # with different parameters
    pipeline_config = [
        {
            'analysis': 'spike_detection',
            'scope': 'all_trials',
            'params': {
                'threshold': -15.0,  # mV
                'refractory_ms': 2.0
            }
        },
        {
            'analysis': 'spike_detection',
            'scope': 'average',
            'params': {
                'threshold': -10.0,  # mV (different threshold for average)
                'refractory_ms': 2.0
            }
        }
    ]
    
    print("\nPipeline configuration:")
    for i, task in enumerate(pipeline_config, 1):
        print(f"  Task {i}:")
        print(f"    Analysis: {task['analysis']}")
        print(f"    Scope: {task['scope']}")
        print(f"    Parameters: {task['params']}")
    
    # Find all .abf files in examples/data/
    examples_dir = project_root / "examples" / "data"
    if not examples_dir.exists():
        print(f"\nError: Examples directory not found at {examples_dir}")
        print("Please ensure the examples/data directory exists and contains .abf files.")
        return
    
    abf_files = list(examples_dir.glob("*.abf"))
    if not abf_files:
        print(f"\nNo .abf files found in {examples_dir}")
        print("Please add some .abf files to the examples/data directory.")
        return
    
    print(f"\nFound {len(abf_files)} .abf file(s):")
    for f in abf_files:
        print(f"  - {f.name}")
    
    # Create engine and run batch analysis
    print("\n" + "=" * 70)
    print("Running batch analysis...")
    print("=" * 70)
    
    engine = BatchAnalysisEngine()
    
    def progress_callback(current, total, message):
        """Simple progress callback."""
        print(f"[{current}/{total}] {message}")
    
    # Run the batch analysis
    try:
        df = engine.run_batch(
            files=abf_files,
            pipeline_config=pipeline_config,
            progress_callback=progress_callback
        )
        
        print("\n" + "=" * 70)
        print("Results Summary")
        print("=" * 70)
        print(f"\nTotal result rows: {len(df)}")
        
        if len(df) > 0:
            print("\nColumn names:")
            print(f"  {', '.join(df.columns.tolist())}")
            
            print("\nFirst 10 rows:")
            print(df.head(10).to_string())
            
            # Show summary statistics if spike_count column exists
            if 'spike_count' in df.columns:
                print("\n" + "=" * 70)
                print("Spike Detection Summary Statistics")
                print("=" * 70)
                print(f"\nTotal spikes detected: {df['spike_count'].sum()}")
                print(f"Mean spikes per analysis: {df['spike_count'].mean():.2f}")
                print(f"Max spikes in single analysis: {df['spike_count'].max()}")
                
                # Group by scope
                if 'scope' in df.columns:
                    print("\nBy scope:")
                    scope_summary = df.groupby('scope')['spike_count'].agg(['count', 'sum', 'mean'])
                    print(scope_summary)
        else:
            print("\nNo results generated. Check logs for errors.")
            
    except Exception as e:
        print(f"\nError during batch analysis: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    print("\n" + "=" * 70)
    print("Batch analysis complete!")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())


