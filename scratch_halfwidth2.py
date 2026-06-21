import numpy as np

def test_interp():
    waveforms = np.array([
        [0, 10, 50, 90, 100, 80, 40, 10, 0],
    ])
    dt = 0.1 # ms
    lev_50 = np.array([[50.0]])
    idx_rise = np.array([1]) # y=10
    idx_fall = np.array([6]) # y=40

    y0_rise = waveforms[0, idx_rise[0]] # 10
    y1_rise = waveforms[0, idx_rise[0] + 1] # 50
    frac_rise = (lev_50[0, 0] - y0_rise) / (y1_rise - y0_rise) # (50 - 10) / 40 = 1.0
    x_rise = idx_rise[0] + frac_rise # 1 + 1.0 = 2.0 (correct, index 2 is exactly 50)

    y0_fall = waveforms[0, idx_fall[0] - 1] # 80
    y1_fall = waveforms[0, idx_fall[0]] # 40
    frac_fall = (lev_50[0, 0] - y0_fall) / (y1_fall - y0_fall) # (50 - 80) / (40 - 80) = -30 / -40 = 0.75
    x_fall = (idx_fall[0] - 1) + frac_fall # 5 + 0.75 = 5.75
    
    # Check manual: index 5 is 80, index 6 is 40. We want 50.
    # 80 -> 40 is a drop of 40 over 1 unit. We want a drop of 30.
    # 30 / 40 = 0.75 of the way from index 5 to 6. Correct!
    
    hw = (x_fall - x_rise) * dt
    print("HW:", hw)

test_interp()
