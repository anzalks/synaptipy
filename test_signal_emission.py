#!/usr/bin/env python3
"""
Test script to verify plot customization signal emission
"""

import sys
import os
sys.path.insert(0, 'src')

def test_signal_emission():
    """Test if plot customization signals are working."""
    try:
        print("Testing plot customization signal emission...")
        
        # Import the modules
        from Synaptipy.shared.plot_customization import (
            PlotCustomizationManager, 
            get_plot_customization_signals,
            _debounced_emit_preferences_updated
        )
        
        print("✓ Imports successful")
        
        # Create manager
        manager = PlotCustomizationManager()
        print("✓ Manager created")
        
        # Get signals
        signals = get_plot_customization_signals()
        print("✓ Signals accessible")
        
        # Test signal connection
        signal_received = False
        def on_signal():
            nonlocal signal_received
            signal_received = True
            print("✓ Signal received!")
        
        signals.preferences_updated.connect(on_signal)
        print("✓ Signal connected")
        
        # Test signal emission
        print("Testing signal emission...")
        _debounced_emit_preferences_updated()
        
        # Wait a bit for the timer
        import time
        time.sleep(0.2)
        
        if signal_received:
            print("✓ Signal emission working!")
        else:
            print("✗ Signal emission failed!")
            
        return signal_received
        
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_signal_emission()
    if success:
        print("\n🎉 All tests passed!")
    else:
        print("\n❌ Tests failed!")
