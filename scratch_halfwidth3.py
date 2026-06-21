import numpy as np

dt = 0.05
n_spikes = 1
waveforms = np.array([[0, 25, 50, 75, 100, 75, 50, 25, 0]])
amp_50 = np.array([50.0])
idx_rise_50_rel = np.array([1]) # y=25
idx_fall_50_rel = np.array([6]) # y=50

y0_rise = waveforms[np.arange(n_spikes), idx_rise_50_rel]
y1_rise = waveforms[np.arange(n_spikes), idx_rise_50_rel + 1]
dy_rise = y1_rise - y0_rise
print("dy_rise", dy_rise)
dy_rise[dy_rise == 0] = 1e-9
frac_rise = (amp_50 - y0_rise) / dy_rise
x_rise = idx_rise_50_rel + frac_rise
print("x_rise", x_rise)

y0_fall = waveforms[np.arange(n_spikes), idx_fall_50_rel - 1]
y1_fall = waveforms[np.arange(n_spikes), idx_fall_50_rel]
dy_fall = y1_fall - y0_fall
dy_fall[dy_fall == 0] = -1e-9
frac_fall = (amp_50 - y0_fall) / dy_fall
x_fall = (idx_fall_50_rel - 1) + frac_fall
print("x_fall", x_fall)

hw = (x_fall - x_rise) * dt * 1000.0
print("HW", hw)

