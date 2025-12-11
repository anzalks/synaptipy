# tests/core/test_phase_plane.py
import pytest
import numpy as np
from Synaptipy.core.analysis.phase_plane import calculate_dvdt, get_phase_plane_trajectory, detect_threshold_kink

def test_calculate_dvdt_simple():
    # Linear voltage rise: V = 10 * t
    # dV/dt should be 10 V/s
    fs = 10000.0 # 10 kHz
    t = np.arange(100) / fs
    v = 10.0 * t * 1000.0 # mV (10 V/s)
    
    dvdt = calculate_dvdt(v, fs, sigma_ms=0)
    
    # Check middle values to avoid edge effects of gradient
    expected = 10.0 # V/s
    assert np.allclose(dvdt[1:-1], expected, atol=1e-5)

def test_calculate_dvdt_smoothing():
    fs = 10000.0
    t = np.arange(1000) / fs
    # Noisy signal
    v = 10.0 * t * 1000.0 + np.random.normal(0, 1.0, len(t))
    
    dvdt_raw = calculate_dvdt(v, fs, sigma_ms=0)
    dvdt_smooth = calculate_dvdt(v, fs, sigma_ms=1.0)
    
    # Smoothed should have lower variance
    assert np.std(dvdt_smooth) < np.std(dvdt_raw)

def test_detect_threshold_kink():
    fs = 20000.0
    t = np.arange(2000) / fs
    
    # Simulate an AP
    # Baseline -70mV
    # Rise starts at 10ms (index 200)
    # Rapid rise to +30mV
    
    v = np.full_like(t, -70.0)
    
    # Simple AP shape
    start_idx = 200
    peak_idx = 250
    
    # Linear rise for simplicity of dV/dt control
    # Rise from -70 to -50 (subthreshold) slowly
    v[100:200] = np.linspace(-70, -50, 100)
    
    # Fast rise from -50 to +30 (AP)
    # dV = 80mV, dt = 50 samples = 2.5ms. dV/dt = 80/2.5 = 32 V/s
    v[200:250] = np.linspace(-50, 30, 50)
    
    # Decay
    v[250:350] = np.linspace(30, -70, 100)
    
    # Threshold detection
    # We expect detection around index 200 where dV/dt jumps
    
    indices = detect_threshold_kink(v, fs, dvdt_threshold=20.0, search_window_ms=5.0)
    
    assert len(indices) == 1
    # Should be close to 200
    assert abs(indices[0] - 200) < 5 # Allow some margin due to smoothing/gradient
