# Algorithmic Definitions

This page provides formal mathematical definitions for all metrics computed by
Synaptipy's analysis modules.  Every formula below corresponds directly to the
implementation in `src/Synaptipy/core/analysis/`.  Parameter names in the
equations match the variable names in the source code.

---

## 1. Baseline / Resting Membrane Potential (RMP)

**Module:** `basic_features.py` · **Registry name:** `rmp_analysis`

$$
V_{\text{RMP}} = \frac{1}{N} \sum_{i \in \mathcal{W}} V_i
$$

where $\mathcal{W} = \{ i : t_{\text{start}} \le t_i < t_{\text{end}} \}$ is
the set of sample indices within the user-specified baseline window.

**Baseline standard deviation:**

$$
\sigma_{\text{RMP}} = \sqrt{ \frac{1}{N-1} \sum_{i \in \mathcal{W}} (V_i - V_{\text{RMP}})^2 }
$$

**Baseline drift** is the slope $\beta_1$ of the ordinary least-squares regression
$V_i = \beta_0 + \beta_1 \, t_i + \varepsilon_i$ fitted over $\mathcal{W}$, reported
in mV/s.

**Auto-detect baseline** selects the window $\mathcal{W}^*$ that minimises the
sliding-window variance:

$$
\mathcal{W}^* = \arg\min_{\mathcal{W}_k}
  \operatorname{Var}\!\bigl(V_{i \in \mathcal{W}_k}\bigr)
$$

where $\mathcal{W}_k$ slides in steps of `step_duration` with width
`window_duration`.

---

## 2. Input Resistance ($R_{\text{in}}$)

**Module:** `intrinsic_properties.py` · **Registry name:** `rin_analysis`

$$
R_{\text{in}} \;(\text{M}\Omega) = \frac{|\Delta V|}{|\Delta I|}
$$

where

$$
\Delta V = \bar{V}_{\text{response}} - \bar{V}_{\text{baseline}},
\qquad
\Delta I = I_{\text{step}} \;(\text{pA})
$$

$\bar{V}$ denotes the arithmetic mean over the respective time window.
Current is converted internally: $\Delta I_{\text{nA}} = |\Delta I_{\text{pA}}| / 1000$.

**Conductance:**

$$
G \;(\mu\text{S}) = \frac{1}{R_{\text{in}} \;(\text{M}\Omega)}
$$

---

## 3. Membrane Time Constant ($\tau$)

**Module:** `intrinsic_properties.py` · **Registry name:** `tau_analysis`

### 3.1 Mono-exponential model

$$
V(t) = V_{\text{ss}} + (V_0 - V_{\text{ss}}) \, e^{-t/\tau}
$$

Fitted via bounded non-linear least squares (`scipy.optimize.curve_fit`).
An initial artifact-blanking period of `artifact_blanking_ms` is excluded from
the fit window.

### 3.2 Bi-exponential model

$$
V(t) = V_{\text{ss}}
      + A_{\text{fast}} \, e^{-t/\tau_{\text{fast}}}
      + A_{\text{slow}} \, e^{-t/\tau_{\text{slow}}}
$$

Constraint: $\tau_{\text{fast}} < \tau_{\text{slow}}$ (swapped post-fit if
violated).

---

## 4. Sag Ratio

**Module:** `intrinsic_properties.py` · **Registry name:** `sag_ratio_analysis`

### 4.1 Ratio form (default)

$$
\text{Sag Ratio} = \frac{V_{\text{peak}} - V_{\text{baseline}}}{V_{\text{ss}} - V_{\text{baseline}}}
$$

A value > 1 indicates hyperpolarisation-activated sag (I_h current).
A value of 1 indicates no sag.

### 4.2 Percentage form

$$
\text{Sag} \;(\%) = 100 \times \frac{V_{\text{peak}} - V_{\text{ss}}}{V_{\text{peak}} - V_{\text{baseline}}}
$$

**$V_{\text{peak}}$** is the minimum of the Savitzky–Golay smoothed voltage in the
peak window (configurable `peak_smoothing_ms`, default 5 ms, polynomial order 3).

**$V_{\text{ss}}$** is the arithmetic mean of the last portion of the
hyperpolarising step (`response_steady_state_window`).

### 4.3 Rebound depolarisation

$$
\Delta V_{\text{rebound}} = \max\bigl(V_{i \in \mathcal{R}}\bigr) - V_{\text{baseline}}
$$

where $\mathcal{R}$ is a configurable window (default 100 ms) immediately
following stimulus offset.

---

## 5. Capacitance ($C_m$)

**Module:** `capacitance.py` · **Registry name:** `capacitance_analysis`

### 5.1 Current-clamp mode

$$
C_m \;(\text{pF}) = \frac{\tau \;(\text{ms})}{R_{\text{in}} \;(\text{M}\Omega)}
$$

Both $\tau$ and $R_{\text{in}}$ are computed from the same trace.

### 5.2 Voltage-clamp mode

$$
C_m = \frac{Q}{\Delta V}
$$

where $Q = \int_0^T \bigl( I(t) - I_{\text{ss}} \bigr) \, dt$ is the charge
transfer of the capacitive transient, computed via trapezoidal integration
(`scipy.integrate.trapezoid`).

---

## 6. Spike Detection and Action Potential Features

**Module:** `spike_analysis.py` · **Registry name:** `spike_detection`

### 6.1 Threshold crossing

Spikes are detected where $V(t) > V_{\text{threshold}}$ with a minimum
refractory period between crossings.  The peak is the local maximum within
`peak_search_window` samples after each crossing.

### 6.2 Onset detection (dV/dt-based)

The action potential onset is defined as the first point where

$$
\frac{dV}{dt} > \theta_{dV/dt}
$$

in the `onset_lookback` window preceding the spike peak.  The derivative is
computed via `numpy.gradient(V) / dt` and reported in V/s.

### 6.3 Amplitude

$$
A_{\text{spike}} = V_{\text{peak}} - V_{\text{threshold}}
$$

### 6.4 Half-width

The half-amplitude level is

$$
V_{50} = V_{\text{threshold}} + 0.5 \times A_{\text{spike}}
$$

Half-width is the time interval between the two crossings of $V_{50}$ on the
rising and falling phases, computed with linear interpolation for sub-sample
precision.

### 6.5 Rise time (10–90%)

$$
t_{\text{rise}} = t_{V_{90}} - t_{V_{10}}
$$

where $V_{x} = V_{\text{threshold}} + (x/100) \times A_{\text{spike}}$.
Crossings are linearly interpolated.

### 6.6 Decay time (90–10%)

$$
t_{\text{decay}} = t_{V_{10,\text{fall}}} - t_{V_{90,\text{fall}}}
$$

on the falling phase of the action potential.

### 6.7 Afterhyperpolarisation (AHP)

$$
\text{AHP depth} = V_{\text{threshold}} - V_{\text{AHP,min}}
$$

where $V_{\text{AHP,min}}$ is the minimum voltage in the `ahp_window` following
the spike peak, smoothed with a Savitzky–Golay filter (window 5 ms, order 3).

**AHP duration** is the time from the repolarisation crossing of
$V_{\text{threshold}}$ to recovery back to $V_{\text{threshold}}$.

### 6.8 Afterdepolarisation (ADP)

$$
A_{\text{ADP}} = V_{\text{ADP,peak}} - V_{\text{fAHP,trough}}
$$

where $V_{\text{fAHP,trough}}$ is the fast AHP minimum within `fahp_window_ms`
(default 5 ms) after the action potential peak, and $V_{\text{ADP,peak}}$ is
the largest local maximum in the subsequent `adp_search_window_ms` (default
20 ms).  A point $V_i$ is a local maximum if $V_i > V_{i-1}$ and
$V_i > V_{i+1}$.

If no local maximum is found (monotonic recovery), $A_{\text{ADP}} = \text{NaN}$.

### 6.9 Maximum and minimum dV/dt

$$
\left(\frac{dV}{dt}\right)_{\max} = \max_{t \in [\text{onset}, \text{peak}]}
  \frac{dV}{dt}(t)
$$

$$
\left(\frac{dV}{dt}\right)_{\min} = \min_{t \in [\text{peak}, \text{AHP}]}
  \frac{dV}{dt}(t)
$$

---

## 7. Event Detection

### 7.1 Threshold-based detection

**Module:** `event_detection.py` · **Registry name:** `event_detection_threshold`

1. Rolling median subtraction (window = `rolling_baseline_window_ms`).
2. Noise estimate via Median Absolute Deviation:
   $\hat{\sigma} = 1.4826 \times \text{MAD}$.
3. Adaptive prominence: $p = \max(\text{threshold}, \, 2\hat{\sigma})$.
4. Peak detection via `scipy.signal.find_peaks` with the computed prominence,
   height, and refractory distance constraints.
5. Events with duration $< 0.2\,\text{ms}$ are rejected as non-physiological.

### 7.2 Template-match / deconvolution

**Registry name:** `event_detection_deconvolution`

Template kernel (bi-exponential):

$$
K(t) = e^{-t/\tau_{\text{decay}}} - e^{-t/\tau_{\text{rise}}}
$$

normalised to unit area.  Events are detected where the z-scored
matched-filter output exceeds `threshold_sd`:

$$
z(t) = \frac{(V \star K)(t) - \mu_{\text{MAD}}}{\hat{\sigma}_{\text{MAD}}}
$$

### 7.3 Baseline-peak detection

**Registry name:** `event_detection_baseline_peak`

Uses sliding-window variance minimisation to find the most stable baseline
segment, estimates noise as $\hat{\sigma} = 1.4826 \times \text{MAD}$ in that
region, and detects peaks with prominence $\ge 0.5 \times \text{threshold}$.

---

## 8. I-V Curve

**Module:** `intrinsic_properties.py` · **Registry name:** `iv_curve_analysis`

For each sweep $n$:

$$
I_n = I_{\text{start}} + n \times I_{\text{step}}, \qquad
\Delta V_n = \bar{V}_{\text{response},n} - \bar{V}_{\text{baseline},n}
$$

Aggregate input resistance is the slope of the linear regression
$\Delta V = R_{\text{in}} \cdot \Delta I_{\text{nA}} + b$:

$$
R_{\text{in}} = \frac{\sum (\Delta I - \overline{\Delta I})(\Delta V - \overline{\Delta V})}
                      {\sum (\Delta I - \overline{\Delta I})^2}
$$

reported with $R^2$ goodness-of-fit.

---

## 9. Burst Analysis

**Module:** `burst_analysis.py` · **Registry name:** `burst_analysis`

A burst begins when $\text{ISI}_k \le \text{max\_isi\_start}$ and continues
while $\text{ISI}_k \le \text{max\_isi\_end}$.  Groups with fewer than
`min_spikes` spikes are discarded.

$$
f_{\text{burst}} = \frac{N_{\text{bursts}}}{T_{\text{recording}}}
$$

---

## 10. Excitability (F-I Curve)

**Module:** `excitability.py` · **Registry name:** `excitability_analysis`

Per sweep $n$ with injected current $I_n$:

$$
f_n = \frac{N_{\text{spikes},n}}{T_{\text{sweep}}}
$$

**Rheobase** = minimum $I_n$ eliciting $\ge 1$ spike.

**F-I slope** from linear regression $f = \alpha \cdot I + \beta$ (Hz/pA).

**Spike Frequency Adaptation** per sweep:

$$
\text{SFA} = \frac{\text{ISI}_{\text{last}}}{\text{ISI}_{\text{first}}}
$$

---

## 11. Phase Plane Analysis

**Module:** `phase_plane.py` · **Registry name:** `phase_plane_analysis`

$$
\frac{dV}{dt}(t) = \text{gaussian\_filter1d}\!\left(
  \frac{\Delta V}{\Delta t}, \; \sigma
\right)
$$

where $\sigma$ is the Gaussian smoothing width.

**Kink detection:** the first point where $dV/dt > \kappa$ (kink slope) in the
lookback window preceding the spike peak, reflecting the axonal initiation site.

---

## 12. Spike Train Dynamics

**Module:** `train_dynamics.py` · **Registry name:** `train_dynamics`

**ISI** = `numpy.diff(spike_times)`

**Coefficient of Variation (CV):**

$$
\text{CV} = \frac{\sigma_{\text{ISI}}}{\mu_{\text{ISI}}}
$$

$\text{CV} = 0$: perfectly regular; $\text{CV} = 1$: Poisson process.

**CV₂** (Holt et al., 1996):

$$
\text{CV}_2 = \frac{1}{N-1} \sum_{i=1}^{N-1}
  \frac{2 \,|\text{ISI}_{i+1} - \text{ISI}_i|}{\text{ISI}_{i+1} + \text{ISI}_i}
$$

Measures local variability; insensitive to slow firing-rate changes.

**Local Variation (LV)** (Shinomoto et al., 2003):

$$
\text{LV} = \frac{3}{N-1} \sum_{i=1}^{N-1}
  \left( \frac{\text{ISI}_i - \text{ISI}_{i+1}}{\text{ISI}_i + \text{ISI}_{i+1}} \right)^{\!2}
$$

$\text{LV} < 1$: regular; $\text{LV} \approx 1$: Poisson; $\text{LV} > 1$: bursty.

---

## 13. Optogenetic Synchronisation

**Module:** `optogenetics.py` · **Registry name:** `optogenetic_sync`

**TTL edge detection:** binarise the stimulus channel at `ttl_threshold`, then
find rising edges via `numpy.diff`.

**Optical latency:**

$$
\bar{L} = \frac{1}{N_{\text{resp}}} \sum_{j=1}^{N_{\text{resp}}}
  (t_{\text{event},j} - t_{\text{stim},j})
$$

**Response probability:**

$$
P_{\text{resp}} = \frac{N_{\text{stim with event}}}{N_{\text{stim}}}
$$

**Jitter:**

$$
\text{Jitter} = \sigma(L_j)
$$

---

## 14. Signal Preprocessing

### 14.1 Digital filters

All Butterworth IIR filters are applied as zero-phase via
`scipy.signal.sosfiltfilt` (second-order sections):

| Filter | Transfer function |
|--------|-------------------|
| Lowpass | $H(s) = \prod_{k=1}^{N/2} \frac{1}{s^2 + b_k s + 1}$ at cutoff $f_c$ |
| Highpass | Complement of lowpass at $f_c$ |
| Bandpass | Cascade of highpass at $f_L$ and lowpass at $f_H$ |
| Notch | $H(z)$ from `scipy.signal.iirnotch` at centre $f_0$, quality $Q$ |
| Comb | Cascaded notch at $f_0, 2f_0, \ldots, Nf_0$ |

### 14.2 Baseline subtraction

| Method | Formula |
|--------|---------|
| Mode | $V' = V - \text{mode}(V)$ (rounded to configured precision) |
| Mean | $V' = V - \bar{V}$ |
| Median | $V' = V - \tilde{V}$ |
| Linear detrend | $V' = V - (\beta_0 + \beta_1 t)$ via `scipy.signal.detrend` |
| Time window | $V' = V - \bar{V}_{\mathcal{W}}$ for user-specified $\mathcal{W}$ |

### 14.3 Artifact blanking

For stimulus artefact suppression, three interpolation modes are available:

| Method | Description |
|--------|-------------|
| `hold` | Replace artefact window with the last pre-artefact sample value |
| `zero` | Set artefact window to zero |
| `linear` | Linearly interpolate between the pre- and post-artefact boundary values |

### 14.4 Trace quality assessment

**SNR:** $\text{SNR} = P_{\text{signal}} / P_{\text{noise}}$

**Baseline drift:** slope $\beta_1$ of OLS regression over the full trace.

**Line noise:** Welch PSD amplitude at 50/60 Hz.

---

## References

- Holt, G. R., Softky, W. R., Koch, C., & Douglas, R. J. (1996). Comparison
  of discharge variability in vitro and in vivo in cat visual cortex neurons.
  *Journal of Neurophysiology*, 75(5), 1806–1814.
- Shinomoto, S., Shima, K., & Tanji, J. (2003). Differences in spiking
  patterns among cortical neurons. *Neural Computation*, 15(12), 2823–2842.
