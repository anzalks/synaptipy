# Algorithmic Definitions

This page provides formal mathematical definitions for all metrics computed by
Synaptipy's analysis modules. Every formula below corresponds directly to the
implementation in `src/Synaptipy/core/analysis/`. Parameter names in the
equations match the variable names in the source code.

---

## Scope and Validated Conditions

All default parameter values in Synaptipy are calibrated for and validated
against the following experimental conditions:

| Parameter | Validated Range |
|-----------|----------------|
| Preparation | Acute brain slices, dissociated cultures |
| Species | Rodent (mouse, rat) |
| Cell types | Cortical/hippocampal pyramidal neurons, interneurons |
| Recording mode | Whole-cell patch-clamp (current-clamp, voltage-clamp) |
| Temperature | Room temperature (20–25 °C) |
| Sampling rate | 10–50 kHz |
| Holding potential | −60 to −80 mV (current-clamp) |

**Users working outside these conditions** (e.g., invertebrate preparations,
cardiac myocytes, in vivo recordings, or temperatures > 30 °C) should
adjust threshold parameters according to their preparation's electrophysiological
characteristics. In particular:

- Fast-spiking interneurons may require raising `dvdt_artifact_ceiling` above
  300 V/s (cortical FS cells can reach 400+ V/s at 34 °C)
- Slow-spiking cells (e.g., dopaminergic neurons) may need lower `dvdt_threshold`
  (10 V/s) and wider AHP windows
- High-temperature recordings accelerate kinetics by Q₁₀ ≈ 2–3×

---

## 1. Baseline / Resting Membrane Potential (RMP)

**Module:** `passive_properties.py` · **Registry name:** `rmp_analysis`

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

To prevent high-frequency electronic noise from inflating the slope estimate, the
voltage array is pre-smoothed with a **uniform moving average** of window
$w_{50} = \lfloor 50\,\text{ms} / \Delta t \rfloor$ samples before regression.
Only the *valid* (non-edge) portion of the convolution output is used:

$$
\tilde{V}_i = \frac{1}{w_{50}} \sum_{k=0}^{w_{50}-1} V_{i+k},
\quad i = 0,\ldots, N - w_{50}
$$

This attenuates noise components above $\approx 20\,\text{Hz}$ while preserving
sub-Hz biological drift.

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

**Module:** `passive_properties.py` · **Registry name:** `rin_analysis`

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

### 2.1 Series-Resistance Artifact Blanking

An uncompensated bridge balance produces an instantaneous voltage jump at
stimulus onset. To prevent this $R_s$ artifact from inflating $\Delta V$, the
first `rs_artifact_blanking_ms` milliseconds (default 0.5 ms) of the response
window are excluded from all voltage measurements:

$$
\mathcal{W}_{\text{resp}}^{\text{blanked}} =
 \{ i : t_{\text{resp,start}} + t_{\text{blank}} \le t_i < t_{\text{resp,end}} \}
$$

where $t_{\text{blank}} = \texttt{rs\_artifact\_blanking\_ms} \times 10^{-3}$.

The same blanking logic is available for the RMP baseline window via the
`rs_artifact_blanking_ms` parameter of `run_rmp_analysis_wrapper`.

### 2.2 Peak $R_{\text{in}}$ and Steady-State $R_{\text{in}}$ ($I_h$ correction)

*(HCN channel physiology and Ih current: Robinson & Siegelbaum, 2003.)*

Cells expressing HCN channels ($I_h$) exhibit a voltage "sag" during
sustained hyperpolarisation: the voltage first reaches a maximum deflection
(Peak) and then partially recovers toward a lower steady-state. A single
$R_{\text{in}}$ value is therefore biologically ambiguous.

**Peak $R_{\text{in}}$** uses the sample of maximum absolute voltage deflection
within the (blanked) response window:

$$
V_{\text{peak}} = V\!\left[\arg\max_i |V_i - \bar{V}_{\text{baseline}}|\right],
\quad i \in \mathcal{W}_{\text{resp}}^{\text{blanked}}
$$

$$
R_{\text{in,peak}} = \frac{|V_{\text{peak}} - \bar{V}_{\text{baseline}}|}{|\Delta I_{\text{nA}}|}
$$

**Steady-State $R_{\text{in}}$** uses the mean voltage over the last 20% of
the (blanked) response window, reflecting the membrane resistance after sag
recovery:

$$
R_{\text{in,ss}} = \frac{|\bar{V}_{\text{last 20\%}} - \bar{V}_{\text{baseline}}|}{|\Delta I_{\text{nA}}|}
$$

For a cell with strong $I_h$: $R_{\text{in,peak}} > R_{\text{in,ss}}$.
For a cell without sag: $R_{\text{in,peak}} \approx R_{\text{in,ss}}$.

Both metrics are returned by `calculate_rin` via `rin_peak_mohm` and
`rin_steady_state_mohm` on the `RinResult` object and are exposed as CSV
columns by the batch exporter.

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

**Numerical stability guard:** when $|V_{\text{ss}} - V_{\text{baseline}}| < 10^{-9}\,\text{mV}$ (effectively zero denominator, e.g. during a flat or noise-only trace), the ratio is set to `NaN` to prevent division by zero rather than returning an arbitrary large value. Similarly, the percentage form (Section 4.2) returns 0 % when $|V_{\text{peak}} - V_{\text{baseline}}| < 10^{-9}\,\text{mV}$.

### 4.2 Percentage form

*(Sag and rebound are hallmarks of HCN-mediated $I_h$; Robinson & Siegelbaum, 2003.)*

$$
\text{Sag} \;(\%) = 100 \times \frac{V_{\text{peak}} - V_{\text{ss}}}{V_{\text{peak}} - V_{\text{baseline}}}
$$

**$V_{\text{peak}}$** is the minimum of the Savitzky-Golay smoothed voltage in the
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

**Module:** `passive_properties.py` · **Registry name:** `capacitance_analysis`

### 5.1 Current-clamp mode

The preferred formula accounts for the series (access) resistance $R_s$,
which acts in series with $R_{\text{in}}$ and therefore carries part of the
RC time constant:

$$
C_m \;(\text{pF}) = \frac{\tau \;(\text{ms})}{R_{\text{in}} - R_s \;(\text{M}\Omega)}
$$

When $R_s$ is not available (e.g. the fast artifact window is too short to
resolve), the approximation $C_m = \tau / R_{\text{in}}$ is used and a
warning is logged, since this over-estimates $C_m$ by a factor of
$R_{\text{in}} / (R_{\text{in}} - R_s)$.

Both $\tau$ and $R_{\text{in}}$ are computed from the same hyperpolarising
current-step trace.  $R_s$ is estimated via `calculate_cc_series_resistance_fast`
(see Section 5.3).

### 5.2 Voltage-clamp mode

*(Rs and Cm derivation follows Hamill et al., 1981; see §15.1 for full equations.)*

$$
C_m = \frac{Q}{\Delta V}
$$

where $Q = \int_0^T \bigl( I(t) - I_{\text{ss}} \bigr) \, dt$ is the charge
transfer of the capacitive transient, computed via trapezoidal integration
(`scipy.integrate.trapezoid`).

### 5.3 Current-clamp series resistance ($R_s^{\text{CC}}$)

The fast resistive voltage artifact at current-step onset, measured within
a **0.1 ms** window immediately after the step, reflects the series resistance
before the membrane has had time to charge:

$$
R_s^{\text{CC}} \;(\text{M}\Omega)
= \frac{|\Delta V_{\text{fast}} \;(\text{mV})|}{|I_{\text{step}} \;(\text{pA})|} \times 10^3
$$

The artifact window is intentionally kept to 0.1 ms (down from a previous
0.5 ms default) to avoid bleeding into the membrane-charging phase, which
would artifactually inflate the $R_s$ estimate.

> **Sampling-rate dependency and stability warning.**  This calculation
> resolves a 0.1 ms window to detect the fast resistive jump.
> At 10 kHz sampling the window contains only **one sample**, making the
> estimate highly unstable (a single noisy sample determines the entire
> $R_s^{\text{CC}}$ value).  At 20 kHz the window contains two samples;
> at 50 kHz, five samples.
> For reliable $R_s^{\text{CC}}$ and derived $C_m$ values, recordings
> should be sampled at $\ge 20$ kHz.  At 10 kHz, the VC transient method
> (Section 5.2) is more robust and should be preferred.
> The instability propagates directly into $C_m$ via
> $C_m = \tau / (R_{\text{in}} - R_s)$: an unreliable $R_s$ estimate
> can produce $C_m$ values that are biologically implausible.

---

## 6. Spike Detection and Action Potential Features

**Module:** `spike_analysis.py` · **Registry name:** `spike_detection`

### 6.1 Threshold crossing

Spikes are detected where $V(t) > V_{\text{threshold}}$ with a minimum
refractory period between crossings. The peak is the local maximum within
`peak_search_window` samples after each crossing.

### 6.2 Onset detection (dV/dt-based)

*(See also §15.2 for the full maximum-curvature method; cited in Sekerli et al., 2004.)*
*(Default threshold $\theta_{dV/dt}$ = 20 V/s, calibrated on rodent cortical pyramidal neurons; Bean, 2007.)*
*(Artifact ceiling: 300 V/s — above this value the rising phase is flagged as non-physiological; Naundorf et al., 2006.)*

The action potential onset is defined as the first point where

$$
\frac{dV}{dt} > \theta_{dV/dt}
$$

in the `onset_lookback` window preceding the spike peak. The derivative is
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

### 6.5 Rise time (10-90%)

$$
t_{\text{rise}} = t_{V_{90}} - t_{V_{10}}
$$

where $V_{x} = V_{\text{threshold}} + (x/100) \times A_{\text{spike}}$.
Crossings are linearly interpolated.

### 6.6 Decay time (90-10%)

$$
t_{\text{decay}} = t_{V_{10,\text{fall}}} - t_{V_{90,\text{fall}}}
$$

on the falling phase of the action potential.

### 6.6.1 Sub-Sample Feature Interpolation

Half-width, rise time (10–90%), and decay time (90–10%) measurements use
**linear interpolation** between the two samples bracketing the target
voltage level $V_{\text{target}}$:

$$
t_{\text{cross}} = t_i + \frac{V_{\text{target}} - V_i}{V_{i+1} - V_i} \cdot \Delta t
$$

When the denominator $|V_{i+1} - V_i| < 10^{-12}$ mV (numerically flat),
the interpolation is flagged as unreliable and the result is set to `NaN`
rather than returning an arbitrary midpoint estimate.

### 6.7 Afterhyperpolarisation (AHP)

*(Fast AHP: BK/Kv3 channel kinetics, 1-5 ms window; Storm, 1987.)*
*(Medium AHP: SK channel kinetics, 10-50 ms window; Sah & Faber, 2002.)*
*(Savitzky-Golay smoothing applied to AHP waveforms; filter derivation in Savitzky & Golay, 1964.)*

$$
\text{AHP depth} = V_{\text{threshold}} - V_{\text{AHP,min}}
$$

where $V_{\text{AHP,min}}$ is the minimum voltage in the `ahp_window` following
the spike peak, smoothed with a Savitzky-Golay filter using a **dynamic window**
$w = \max(5,\ \lfloor 5\,\text{ms} / \Delta t \rfloor)$ samples, order 3.
The window is rounded up to the nearest odd integer to satisfy the Savitzky-Golay
constraint, ensuring the filter width tracks the recording's sampling rate.

**AHP duration** is the time from the repolarisation crossing of
$V_{\text{threshold}}$ to recovery back to $V_{\text{threshold}}$.

### 6.8 Afterdepolarisation (ADP)

$$
A_{\text{ADP}} = V_{\text{ADP,peak}} - V_{\text{fAHP,trough}}
$$

where $V_{\text{fAHP,trough}}$ is the fast AHP minimum within `fahp_window_ms`
(default 5 ms) after the action potential peak, and $V_{\text{ADP,peak}}$ is
the largest local maximum in the subsequent `adp_search_window_ms` (default
20 ms). A point $V_i$ is a local maximum if $V_i > V_{i-1}$ and
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

### 6.10 Absolute Peak Voltage and Overshoot

Classical neurophysiology reports the raw membrane potential at the AP peak
and the extent to which it exceeds $0\,\text{mV}$ (overshoot):

$$
V_{\text{peak,abs}} = V\bigl[i_{\text{peak}}\bigr]
$$

$$
\text{Overshoot} \;(\text{mV}) = \max\!\bigl(0,\; V_{\text{peak,abs}}\bigr)
$$

An overshoot of 0 indicates the AP peaked below $0\,\text{mV}$ (e.g. in
immature neurons or under pharmacological block of Na$^+$ channels).
Both metrics are returned as `absolute_peak_mv` and `overshoot_mv` in the
per-spike feature dictionaries produced by `calculate_spike_features`.

---

## 7. Event Detection

### 7.1 Threshold-based detection

**Module:** `synaptic_events.py` · **Registry name:** `event_detection_threshold`

1. Rolling median subtraction (window = `rolling_baseline_window_ms`).
2. Noise estimate via Median Absolute Deviation (MAD; Hampel, 1974;
 Rousseeuw & Croux, 1993): $\hat{\sigma} = 1.4826 \times \text{MAD}$,
 where the constant 1.4826 is the consistency factor making the estimate
 equivalent to a standard deviation for Gaussian noise.
3. Adaptive prominence: $p = \max(\text{threshold}, \, 2\hat{\sigma})$.
4. Peak detection via `scipy.signal.find_peaks` with the computed prominence,
 height, and refractory distance constraints.
5. Events with duration $< 0.2\,\text{ms}$ are rejected as non-physiological.

### 7.2 Template-match / matched-filter cross-correlation

**Registry name:** `event_detection_deconvolution`

A single bi-exponential kernel is constructed from the user-specified rise
and decay time constants:

$$
K(t) = e^{-t/\tau_{\text{decay}}} - e^{-t/\tau_{\text{rise}}}
$$

normalised to unit area. The kernel is **cross-correlated** (matched-filter)
with the baseline-corrected trace - this is not deconvolution. Events are
detected where the z-scored matched-filter output exceeds `threshold_sd`:

$$
z(t) = \frac{(V \star K)(t) - \mu_{\text{MAD}}}{\hat{\sigma}_{\text{MAD}}}
$$

:::{note}
**Template bank construction:** The filter scales a single user-defined decay
constant by user-configurable multipliers (default 1x, 2x, 3x) to create a
detection template bank.  The multipliers can be changed in the GUI via the
**Kernel Multipliers** field (comma-separated floats, e.g. ``1.0, 2.0, 3.0``).
The three default kernels provide tolerance for dendritic filtering without
requiring a representative example event from the recording.
:::

**Formal multi-scale matched filter specification:**

The kernel bank consists of $K=3$ biophysically motivated templates:

$$
h_k(t) = \left(1 - e^{-t/\tau_{\text{rise}}}\right) \cdot e^{-t/\tau_{k,\text{decay}}}
\quad \text{for } t \geq 0
$$

where $\tau_{k,\text{decay}} \in \{m_1 \cdot \tau_d,\; m_2 \cdot \tau_d,\; \ldots,\; m_K \cdot \tau_d\}$
and $\{m_k\}$ are the user-supplied **Kernel Multipliers** (default $\{1, 2, 3\}$),
reflecting cable-theory predictions of 2-3x slowing for distal synaptic
inputs (Rall, 1967; Major et al., 1994).

Convolution is computed via FFT: $c_k = \mathcal{F}^{-1}\{\mathcal{F}\{x\} \cdot \mathcal{F}\{h_k\}^*\}$.

Z-score normalisation per kernel:

$$
z_k[n] = \frac{c_k[n] - \mu_{c_k}}{\sigma_{c_k}}
$$

**Peak selection rule:** Events are detected at local maxima of
$\max_k z_k[n]$ exceeding $z_{\min}$ (default 3.5), subject to a minimum
inter-event interval of $\tau_{\text{rise}}$:

$$
n^* = \arg\max_{n \in \mathcal{N}} \max_k z_k[n], \quad \text{s.t. } \max_k z_k[n^*] \geq z_{\min}
$$

### 7.2.1 Adaptive Noise Floor Estimation

The quiescent noise floor is estimated via a sliding minimum-variance window:

$$
\hat{\sigma}_{\text{noise}} = \sqrt{\min_{j} \operatorname{Var}(\tilde{x}_{j:j+W})}
$$

where $\tilde{x}$ denotes the linearly detrended signal within each window
of $W = \lfloor 20\,\text{ms} / \Delta t \rfloor$ samples, with step size $W/2$.
Linear detrending (via `scipy.signal.detrend`) ensures that slow baseline
drift does not inflate the local variance estimate.

A floor of $10^{-6}$ (matching thermal noise) prevents division by zero
when the recording is digitally silent.

*(Standard signal detection criterion: 3× noise SD corresponds to
p < 0.003 under Gaussian noise assumption.)*

### 7.3 Baseline-peak detection

**Registry name:** `event_detection_baseline_peak`

Uses sliding-window variance minimisation to find the most stable baseline
segment, estimates noise as $\hat{\sigma} = 1.4826 \times \text{MAD}$
(Hampel, 1974; Rousseeuw & Croux, 1993) in that region, and detects peaks
with prominence $\ge 0.5 \times \text{threshold}$.

### 7.4 Local Pre-Event Baseline (Dynamic Amplitude for Summating Events)

Synaptic events that occur during the exponential decay of a preceding event
(summation) ride on a shifted baseline. Using the global resting potential as
the amplitude reference artificially inflates the measured amplitude of the
second event (or any subsequent event in a burst).

For each detected event peak index $i_k$, Synaptipy searches a window of
`pre_event_window_ms` (default 2 ms, valid range 1-3 ms) immediately
preceding the peak and computes a **local foot voltage** $V_{\text{foot},k}$:

$$
V_{\text{foot},k} =
\begin{cases}
\max_{j \in \mathcal{P}_k} V_j & \text{(negative polarity)} \\
\min_{j \in \mathcal{P}_k} V_j & \text{(positive polarity)}
\end{cases}
$$

where $\mathcal{P}_k = \{j : i_k - N_{\text{pre}} \le j < i_k\}$ and
$N_{\text{pre}} = \lfloor \texttt{pre\_event\_window\_ms} \times f_s / 1000 \rfloor$.

The **local amplitude** of event $k$ is then:

$$
A_{\text{local},k} =
\begin{cases}
V_{\text{foot},k} - V_k & \text{(negative polarity)} \\
V_k - V_{\text{foot},k} & \text{(positive polarity)}
\end{cases}
$$

This definition ensures that in a summating train, each event's amplitude
reflects the true biological quantal size rather than the accumulated
depolarisation from prior events. The values are returned as
`_local_baselines` and `_local_amplitudes` in the metrics dict, together
with the scalar summary `mean_local_amplitude`.

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

*(Criterion adapted from Grace & Bunney, 1984; dynamic ISI fraction (30% of mean ISI) motivated by Harris et al., 2001.)*

A burst begins when $\text{ISI}_k \le \text{max\_isi\_start}$ and continues
while $\text{ISI}_k \le \text{max\_isi\_end}$. Groups with fewer than
`min_spikes` spikes are discarded.

**Dynamic threshold mode:** when enabled, the ISI boundary is computed as
$\text{threshold} = 0.3 \times \overline{\text{ISI}}$ (the `burst_isi_fraction`
parameter), adapting to the train's own temporal structure.

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

**Module:** `firing_dynamics.py` · **Registry name:** `train_dynamics`

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

**Numerical stability guard (CV₂):** each term is computed only when
$\text{ISI}_{i+1} + \text{ISI}_i > \varepsilon_{\text{ISI}} = 10^{-9}\,\text{s}$.
Pairs that do not satisfy this condition (e.g. duplicate spike-time entries)
contribute `NaN` to the sum and are excluded via `numpy.nanmean`.

**Local Variation (LV)** (Shinomoto et al., 2003):

$$
\text{LV} = \frac{3}{N-1} \sum_{i=1}^{N-1}
 \left( \frac{\text{ISI}_i - \text{ISI}_{i+1}}{\text{ISI}_i + \text{ISI}_{i+1}} \right)^{\!2}
$$

$\text{LV} < 1$: regular; $\text{LV} \approx 1$: Poisson; $\text{LV} > 1$: bursty.

**Numerical stability guard (LV):** each squared term is computed only when
$(\text{ISI}_i + \text{ISI}_{i+1})^2 > \varepsilon_{\text{ISI}}^{2} = 10^{-15}\,\text{s}^2$,
where $\varepsilon_{\text{ISI}} = 10^{-9}\,\text{s}$ matches the CV₂ guard.
Terms failing this check contribute `NaN` and are excluded via `numpy.nanmean`.

---

## 13. Optogenetic Synchronisation

**Module:** `evoked_responses.py` · **Registry name:** `optogenetic_sync`

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

All Butterworth IIR filters (Butterworth, 1930) are applied as zero-phase via
`scipy.signal.sosfiltfilt` (second-order sections). The Butterworth design
maximally flat magnitude in the passband with monotonic roll-off. Zero-phase
filtration via `sosfiltfilt` applies the filter twice (forward and reverse),
eliminating group delay distortion critical for preserving AP waveform timing:

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

**Line noise:** Welch PSD amplitude at 50/60 Hz (Welch, 1967). The PSD is
estimated via `scipy.signal.welch` using the modified periodogram method
(Hann window, segment length = min(4096, N)). The power ratio at 50/60 Hz
relative to the neighboring baseline band identifies mains interference.

---

## References

### Spike detection and AP threshold

- **Sekerli, M., Del Negro, C. A., Lee, R. H., & Bhatt, D. L. (2004).** Estimating
  action potential thresholds from neuronal time-series: new metrics and evaluation of
  methodologies. *IEEE Transactions on Biomedical Engineering*, 51(9), 1665-1672.
  [doi:10.1109/TBME.2004.827827](https://doi.org/10.1109/TBME.2004.827827)
  - **Used in:** §6.2 (onset detection via $d^2V/dt^2$ maximum curvature) and
    §15.2 (dynamic AP threshold fallback).

- **Henze, D. A., & Buzsaki, G. (2001).** Action potential threshold of hippocampal
  pyramidal cells in vivo is increased by recent spiking activity. *Neuroscience*,
  105(1), 121-130.
  [doi:10.1016/S0306-4522(01)00167-1](https://doi.org/10.1016/S0306-4522(01)00167-1)
  - **Used in:** motivation for per-spike dynamic threshold (§15.2).

### Patch-clamp methodology

- **Hamill, O. P., Marty, A., Neher, E., Sakmann, B., & Sigworth, F. J. (1981).**
  Improved patch-clamp techniques for high-resolution current recording from cells and
  cell-free membrane patches. *Pflugers Archiv*, 391(2), 85-100.
  [doi:10.1007/BF00656997](https://doi.org/10.1007/BF00656997)
  - **Used in:** series-resistance measurement (§5.2, §15.1) and whole-cell
    capacitance estimation.

- **Neher, E., & Sakmann, B. (1976).** Single-channel currents recorded from membrane
  of denervated frog muscle fibres. *Nature*, 260(5554), 799-802.
  [doi:10.1038/260799a0](https://doi.org/10.1038/260799a0)
  - Foundation for whole-cell patch-clamp passive-property analysis.

### Signal processing

- **Savitzky, A., & Golay, M. J. E. (1964).** Smoothing and differentiation of data
  by simplified least squares procedures. *Analytical Chemistry*, 36(8), 1627-1639.
  [doi:10.1021/ac60214a047](https://doi.org/10.1021/ac60214a047)
  - **Used in:** Savitzky-Golay smoothing of AHP waveforms (§6.7), dV/dt
    computation (§6.9, §15.2).

- **Virtanen, P., Gommers, R., Oliphant, T. E., et al. (2020).** SciPy 1.0:
  Fundamental algorithms for scientific computing in Python. *Nature Methods*, 17,
  261-272. [doi:10.1038/s41592-019-0686-2](https://doi.org/10.1038/s41592-019-0686-2)
  - Provides `scipy.optimize.curve_fit` used in tau (§3), capacitance (§5.2),
    and PPR decay fitting (§15.5).

### Spike-train statistics

- **Holt, G. R., Softky, W. R., Koch, C., & Douglas, R. J. (1996).** Comparison
  of discharge variability in vitro and in vivo in cat visual cortex neurons.
  *Journal of Neurophysiology*, 75(5), 1806-1814.
  [doi:10.1152/jn.1996.75.5.1806](https://doi.org/10.1152/jn.1996.75.5.1806)
  - **Used in:** CV and CV2 computation (§12).

- **Shinomoto, S., Shima, K., & Tanji, J. (2003).** Differences in spiking
  patterns among cortical neurons. *Neural Computation*, 15(12), 2823-2842.
  [doi:10.1162/089976603322518759](https://doi.org/10.1162/089976603322518759)
  - **Used in:** local variation (LV) metric (§12).

### NWB / FAIR data

- **Rubel, O., Tritt, A., Ly, R., et al. (2022).** The Neurodata Without Borders
  ecosystem for neurophysiological data science. *eLife*, 11:e78362.
  [doi:10.7554/eLife.78362](https://doi.org/10.7554/eLife.78362)
  - Standard used for NWB export and FAIR metadata compliance.

- **Garcia, S., Guarino, D., Jaillet, F., et al. (2014).** Neo: an object model
  for handling electrophysiology data in multiple formats. *Frontiers in
  Neuroinformatics*, 8, 10.
  [doi:10.3389/fninf.2014.00010](https://doi.org/10.3389/fninf.2014.00010)
  - Provides the I/O layer for all supported file formats.

### Default parameter justification

- **Bean, B. P. (2007).** The action potential in mammalian central neurons.
  *Nature Reviews Neuroscience*, 8(6), 451-465.
  [doi:10.1038/nrn2148](https://doi.org/10.1038/nrn2148)
  - **Used in:** Default dV/dt threshold (20 V/s) for spike onset detection;
    cortical pyramidal neuron AP kinetics reference.

- **Naundorf, B., Wolf, F., & Volgushev, M. (2006).** Unique features of action
  potential initiation in cortical neurons. *Nature*, 440(7087), 1060-1063.
  [doi:10.1038/nature04610](https://doi.org/10.1038/nature04610)
  - **Used in:** Artifact ceiling (300 V/s) for the fastest cortical APs.

- **Storm, J. F. (1987).** Action potential repolarization and a fast
  after-hyperpolarization in rat hippocampal pyramidal cells. *Journal of
  Physiology*, 385, 733-759.
  [doi:10.1113/jphysiol.1987.sp016517](https://doi.org/10.1113/jphysiol.1987.sp016517)
  - **Used in:** Fast AHP window (1-5 ms), BK channel kinetics.

- **Sah, P., & Faber, E. S. L. (2002).** Channels underlying neuronal
  calcium-activated potassium currents. *Progress in Neurobiology*, 66(5),
  345-353.
  [doi:10.1016/S0301-0082(02)00004-7](https://doi.org/10.1016/S0301-0082(02)00004-7)
  - **Used in:** Medium AHP window (10-50 ms), SK channel kinetics.

- **Grace, A. A., & Bunney, B. S. (1984).** The control of firing pattern in
  nigral dopamine neurons: burst firing. *Journal of Neuroscience*, 4(11),
  2877-2890.
  [doi:10.1523/JNEUROSCI.04-11-02877.1984](https://doi.org/10.1523/JNEUROSCI.04-11-02877.1984)
  - **Used in:** Burst detection ISI criterion (adapted for cortical neurons).

- **Harris, K. D., Hirase, H., Leinekugel, X., Henze, D. A., & Buzsáki, G.
  (2001).** Temporal interaction between single spikes and complex spike bursts
  in hippocampal pyramidal cells. *Neuron*, 32(1), 141-149.
  [doi:10.1016/S0896-6273(01)00447-0](https://doi.org/10.1016/S0896-6273(01)00447-0)
  - **Used in:** Burst ISI fraction (30% of mean ISI) for cortical neurons.

- **Rall, W. (1967).** Distinguishing theoretical synaptic potentials computed
  for different soma-dendritic distributions of synaptic input. *Journal of
  Neurophysiology*, 30(5), 1138-1168.
  [doi:10.1152/jn.1967.30.5.1138](https://doi.org/10.1152/jn.1967.30.5.1138)
  - **Used in:** Multi-scale template bank (2-3× tau slowing for distal inputs).

- **Major, G., Larkman, A. U., Jonas, P., Sakmann, B., & Jack, J. J. B.
  (1994).** Detailed passive cable models of whole-cell recorded CA3 pyramidal
  neurons in rat hippocampal slices. *Journal of Neuroscience*, 14(8),
  4613-4638.
  - **Used in:** Cable-theory prediction of dendritic filtering (template bank).

### Paired-pulse ratio and short-term plasticity

- **Zucker, R. S., & Regehr, W. G. (2002).** Short-term synaptic plasticity.
  *Annual Review of Physiology*, 64, 355-405.
  [doi:10.1146/annurev.physiol.64.092501.114547](https://doi.org/10.1146/annurev.physiol.64.092501.114547)
  - **Used in:** PPR R2 baseline correction methodology (Section 15.5); direct
    referencing of R2 amplitude to the pre-stimulus resting baseline (bl1).

- **Regehr, W. G. (2012).** Short-term presynaptic plasticity.
  *Cold Spring Harbor Perspectives in Biology*, 4(7), a005702.
  [doi:10.1101/cshperspect.a005702](https://doi.org/10.1101/cshperspect.a005702)
  - **Used in:** Conceptual framework for PPR interpretation (Section 15.5);
    facilitation (PPR > 1) and depression (PPR < 1) classification.

### Visualization and accessibility

- **Wong, B. (2011).** Points of view: Color blindness. *Nature Methods*,
  8(6), 441.
  [doi:10.1038/nmeth.1618](https://doi.org/10.1038/nmeth.1618)
  - **Used in:** Colorblind-safe palette for plot colors.

### Array computation

- **Harris, C. R., Millman, K. J., van der Walt, S. J., et al. (2020).**
  Array programming with NumPy. *Nature*, 585, 357-362.
  [doi:10.1038/s41586-020-2649-2](https://doi.org/10.1038/s41586-020-2649-2)
  - **Used in:** All numerical array operations throughout the codebase:
    `numpy.gradient` for dV/dt (§6.2, §6.9, §11, §15.2), `numpy.diff` for ISI
    (§12), `numpy.trapezoid` for charge integration (§5.2), and `numpy.nanmean`
    for numerically stable CV2/LV computations (§12).

### Signal processing methods

- **Butterworth, S. (1930).** On the Theory of Filter Amplifiers.
  *Wireless Engineer*, 7, 536-541. (No formal DOI; original publication.)
  - **Used in:** All IIR digital filters in §14.1: lowpass, highpass,
    bandpass Butterworth designs implemented via `scipy.signal.butter` with
    zero-phase forward-reverse application (`sosfiltfilt`).

- **Welch, P. D. (1967).** The use of fast Fourier transform for the
  estimation of power spectra: A method based on time averaging over short,
  modified periodograms. *IEEE Transactions on Audio and Electroacoustics*,
  15(2), 70-73.
  [doi:10.1109/TAU.1967.1161901](https://doi.org/10.1109/TAU.1967.1161901)
  - **Used in:** §14.4 trace quality assessment — line noise detection at
    50/60 Hz via `scipy.signal.welch`; also used in the `compute_psd` utility
    in `signal_processor.py`.

### Robust noise estimation

- **Hampel, F. R. (1974).** The influence curve and its role in robust
  estimation. *Journal of the American Statistical Association*, 69(346),
  383-393.
  [doi:10.1080/01621459.1974.10482962](https://doi.org/10.1080/01621459.1974.10482962)
  - **Used in:** §7.1, §7.2, §7.3 — the 1.4826 consistency factor applied to
    the Median Absolute Deviation (MAD) to obtain a Gaussian-consistent
    standard deviation estimate: $\hat{\sigma} = 1.4826 \times \text{MAD}$.
    The factor 1.4826 = $1 / \Phi^{-1}(0.75)$ ensures the estimator is
    equivalent to the sample SD for Gaussian distributions.

- **Rousseeuw, P. J., & Croux, C. (1993).** Alternatives to the median
  absolute deviation. *Journal of the American Statistical Association*,
  88(424), 1273-1283.
  [doi:10.1080/01621459.1993.10476408](https://doi.org/10.1080/01621459.1993.10476408)
  - **Used in:** MAD noise estimator (§7.1, §7.2, §7.3) — robustness
    properties and breakdown point of the MAD as a scale estimator for
    contaminated electrophysiology data.

### Preprocessing and electrode correction

- **Barry, P. H., & Lynch, J. W. (1991).** Liquid junction potentials
  and small cell effects in patch-clamp analysis. *Journal of Membrane
  Biology*, 121(2), 101-117.
  [doi:10.1007/BF01870526](https://doi.org/10.1007/BF01870526)
  - **Used in:** §16 Step A — liquid junction potential subtraction
    $V_{\text{true}} = V_{\text{recorded}} - \text{LJP}$. Defines the
    correction procedure and its biophysical limitations for voltage-dependent
    analyses.

- **Armstrong, C. M., & Bezanilla, F. (1977).** Inactivation of the sodium
  channel. II. Gating current experiments. *Journal of General Physiology*,
  70(5), 567-590.
  [doi:10.1085/jgp.70.5.567](https://doi.org/10.1085/jgp.70.5.567)
  - **Used in:** §16 Step B — P/N leak subtraction protocol. Armstrong and
    Bezanilla introduced the P/N subtraction technique for isolating
    non-linear gating currents by scaling and subtracting linear leak sweeps.

- **Bezanilla, F., & Armstrong, C. M. (1977).** Inactivation of the sodium
  channel. I. Sodium current experiments. *Journal of General Physiology*,
  70(5), 549-566.
  [doi:10.1085/jgp.70.5.549](https://doi.org/10.1085/jgp.70.5.549)
  - **Used in:** §16 Step B — companion paper establishing the P/N
    subtraction protocol for leak correction in voltage-clamp recordings.

### Foundational neuroscience

- **Hodgkin, A. L., & Huxley, A. F. (1952).** A quantitative description
  of membrane current and its application to conduction and excitation in
  nerve. *Journal of Physiology*, 117(4), 500-544.
  [doi:10.1113/jphysiol.1952.sp004764](https://doi.org/10.1113/jphysiol.1952.sp004764)
  - **Used in:** §15.2 — foundational mathematical model of action potential
    generation via voltage-gated Na$^+$ and K$^+$ conductances. Provides the
    biophysical basis for AP threshold detection, dV/dt methods, and Na$^+$
    channel inactivation effects on spike trains.

- **Robinson, R. B., & Siegelbaum, S. A. (2003).** Hyperpolarization-activated
  cation currents: From molecules to physiological function. *Annual Review of
  Physiology*, 65, 453-480.
  [doi:10.1146/annurev.physiol.65.092101.142734](https://doi.org/10.1146/annurev.physiol.65.092101.142734)
  - **Used in:** §2.2 and §4 — physiological context for HCN channel-mediated
    $I_h$ current, voltage sag during hyperpolarisation, and the distinction
    between peak and steady-state input resistance as a diagnostic for $I_h$.

- **Neher, E. (1992).** Correction for liquid junction potentials in patch
  clamp experiments. *Methods in Enzymology*, 207, 123-131.
  [doi:10.1016/0076-6879(92)07008-C](https://doi.org/10.1016/0076-6879(92)07008-C)
  - **Used in:** §16 Step A — standard reference for LJP correction in
    whole-cell patch-clamp. Provides the accepted procedure for calculating
    and applying the junction potential offset.

### Data handling and tabular output

- **McKinney, W. (2010).** Data structures for statistical computing in
  Python. *Proceedings of the 9th Python in Science Conference* (SciPy 2010),
  51-56.
  [doi:10.25080/Majora-92bf1922-00a](https://doi.org/10.25080/Majora-92bf1922-00a)
  - **Used in:** Batch engine CSV export and result tabulation. The
    `pandas.DataFrame` API is used to assemble wide-format (scalar metrics)
    and long-format (event arrays) output tables compatible with Python/Pandas,
    R, and MATLAB downstream workflows.


## 15. Advanced Biophysics (Publication Audit)

### 15.1 Voltage-Clamp Series Resistance and True Membrane Capacitance

Classical area-under-the-curve (AUC) Cm estimation is biologically invalid
without Rs compensation.  The implementation uses:

**Step 1 - Series Resistance (Ohm's law at the instant of the voltage step):**

$$
R_s \;[\text{MOhm}] = \frac{|\Delta V \;[\text{mV}]|}{|I_{\text{peak}} \;[\text{pA}]|} \times 10^{3}
$$

where $I_{\text{peak}}$ is the baseline-subtracted transient peak and
$\Delta V$ is the command voltage step amplitude.

**Step 2 - Transient time constant (mono-exponential fit):**

A mono-exponential $I(t) = A \exp(-t / \tau)$ is fitted to the decaying phase
of the transient using `scipy.optimize.curve_fit`.  The fit starts at the
transient peak and uses the last 20% of the transient window as a steady-state
reference.

**Step 3 - Membrane Capacitance:**

$$
C_m \;[\text{pF}] = \frac{\tau \;[\text{s}]}{R_s \;[\Omega]} \times 10^{12}
= \frac{\tau \;[\text{s}]}{R_s \;[\text{MOhm}] \times 10^{6}} \times 10^{12}
$$

If the exponential fit fails (insufficient samples or poor convergence), the
function falls back to the charge-integral (AUC) method for $C_m$ while still
reporting the Ohm's-law $R_s$.

### 15.2 Dynamic AP Threshold via Maximum Curvature ($d^2V/dt^2$)

*(Method described in Sekerli et al., 2004; dynamic threshold motivated by Henze & Buzsaki, 2001.
Foundational AP model: Hodgkin & Huxley, 1952.)*

A fixed dV/dt threshold fails during spike trains because Na$^+$ channel
inactivation progressively slows the AP upstroke.  The physiological onset is
instead defined as the point of **maximum curvature** of the voltage trace:

$$
\text{threshold index} = \operatorname{argmax}_{j \in \mathcal{W}} \frac{d^2V}{dt^2}(j)
$$

where $\mathcal{W}$ is a lookback window of `onset_lookback` seconds immediately
before each spike peak.  Both $dV/dt$ and $d^2V/dt^2$ are computed via
`numpy.gradient` on the voltage array.

**Fallback rule:** if the $d^2V/dt^2$ maximum lies at the edge of $\mathcal{W}$
(index 0 or $|\mathcal{W}|-1$), the estimate is unreliable (boundary artefact).
In that case the algorithm uses a **dynamic per-spike threshold**: the first
$dV/dt$ crossing above $\theta_{\text{dyn}}$ within $\mathcal{W}$, where

$$
\theta_{\text{dyn}} = \max\!\left(0.20 \cdot \max_{j \in \mathcal{W}}
  \frac{dV}{dt}(j),\ \ 2{,}000\,\text{mV/s}\right)
$$

The 20 % fraction of the spike-specific peak rising rate captures onset
consistently across spikes with attenuated upstrokes (Na$^+$ inactivation in
high-frequency trains). The 2,000 mV/s floor prevents false triggering during
subthreshold depolarisations at rest. A hardcoded 20 V/s absolute threshold is
**not** used.

### 15.3 Separation of Fast AHP and Medium AHP

A single AHP measurement conflates fast ($\text{K}_V$, BK channels) and medium
($\text{K}_{Ca}$, SK channels) dynamics.  Two independent searches are made:

| Metric | Window | Dominant channel |
|---|---|---|
| $\text{fAHP depth}$ | 1-5 ms post-peak | Na$^+$ channel-mediated repolarisation overshoot, BK |
| $\text{mAHP depth}$ | 10-50 ms post-peak | SK/IK Ca$^{2+}$-activated K$^+$ |

$$
\text{fAHP depth} = V_{\text{threshold}} - \min_{t \in [t_{\text{peak}}+1\text{ ms},\; t_{\text{peak}}+5\text{ ms}]} V(t)
$$

$$
\text{mAHP depth} = V_{\text{threshold}} - \min_{t \in [t_{\text{peak}}+10\text{ ms},\; t_{\text{peak}}+50\text{ ms}]} V(t)
$$

Positive depth = hyperpolarisation relative to AP threshold.

### 15.4 Multi-Kernel Dendritic Tolerance in Template Matching

Cable theory predicts that synaptic currents arriving at distal dendrites
appear 2-3x slower at the soma due to RC filtering.  A bank of **three
bi-exponential kernels** is generated by scaling the user-specified decay
constant by **fixed multipliers 1x, 2x, and 3x**:

$$
k_s(t) = \exp\!\left(-t / (s \cdot \tau_{\text{decay}})\right) - \exp\!\left(-t / \tau_{\text{rise}}\right),
\quad s \in \{1, 2, 3\}
$$

These are **not** data-driven or dynamically fitted templates - the
multipliers are fixed constants that approximate the somatic, proximal-
dendrite, and distal-dendrite filtering regimes.  Each kernel is
normalised to unit peak amplitude and **cross-correlated** (matched-
filter) with the baseline-corrected data.  The three filtered traces are
z-scored independently using the median absolute deviation (MAD), then
combined pointwise by taking the maximum:

$$
z_{\text{combined}}(t) = \max_{s \in \{1,2,3\}} z_s(t)
$$

Peak detection is then applied to $z_{\text{combined}}$ at the user-specified
threshold.  This ensures that both fast somatic (narrow) and slow dendritic
(broadened) events cross the detection threshold, without requiring the user
to re-tune $\tau_{\text{decay}}$ for distal inputs.

### 15.5 PPR R2 Amplitude: Direct Baseline Correction

*(Zucker & Regehr, 2002; Regehr, 2012)*

The amplitude of the second response ($R_2$) must be measured from a reference
that is uncontaminated by the decaying tail of the first response ($R_1$).
When the inter-stimulus interval is short relative to the $R_1$ decay constant,
the local baseline immediately preceding the second stimulus ($\text{bl}_2$)
lies above (or below) the true resting potential, causing a systematic
underestimate (or overestimate) of $R_2$.

The corrected $R_2$ amplitude is obtained by referencing the raw $R_2$ peak
voltage directly to $\text{bl}_1$ (the pre-stimulus resting baseline measured
before the first pulse):

$$
R_{2,\text{corrected}} =
\begin{cases}
  \text{bl}_1 - V_{R_2,\text{peak}} & \text{(inward / negative polarity)} \\
  V_{R_2,\text{peak}} - \text{bl}_1 & \text{(outward / positive polarity)}
\end{cases}
$$

where $V_{R_2,\text{peak}}$ is the minimum (negative polarity) or maximum
(positive polarity) voltage in the $R_2$ response window, and $\text{bl}_1$
is the mean voltage in the user-specified pre-stimulus baseline window.

This formulation is equivalent to $R_{2,\text{raw}} + (\text{bl}_2 - \text{bl}_1)$:
the correction term $(\text{bl}_2 - \text{bl}_1)$ equals the measured baseline
contamination from the $R_1$ decay tail.  When the decay has fully returned to
baseline ($\text{bl}_2 \approx \text{bl}_1$), $R_{2,\text{corrected}} \approx
R_{2,\text{raw}}$, so equal-amplitude paired events yield $\text{PPR} = 1$.

The raw amplitude $R_{2,\text{raw}}$ (measured from $\text{bl}_2$) and the
residual at stimulus 2 ($\text{residual\_at\_stim2}$, from the exponential
decay fit) are retained as diagnostic output fields. The decay-fit residual
is **not** used as the reference for $R_{2,\text{corrected}}$ because the
exponential extrapolation can be unreliable when the fit window partially
overlaps the $R_1$ alpha-function rise phase.

**Paired-pulse ratio:**

$$
\text{PPR} = \frac{R_{2,\text{corrected}}}{R_{1,\text{amplitude}}}
$$

Values $> 1$ indicate short-term facilitation; values $< 1$ indicate
short-term depression.

---

### 15.6 PPR Residual Fitting - Bi-Exponential Upgrade

The P1 decay tail is now first fitted with a **bi-exponential** model before
falling back to a mono-exponential.  Bi-exponential fits capture mixed
conductance kinetics (e.g. AMPA fast-deactivation + NMDA slow-deactivation):

$$
I_{\text{decay}}(t) = A_f \exp\!\left(-t / \tau_f\right) + A_s \exp\!\left(-t / \tau_s\right)
$$

The fitting uses `scipy.optimize.curve_fit` with `maxfev=4000`.  If convergence
fails (typically when fewer than 8 samples span the decay window), the
implementation falls back to the mono-exponential $A \exp(-t/\tau)$.

The reported dominant $\tau$ for the bi-exponential case is the
**amplitude-weighted mean time constant**:

$$
\tau_{\text{dominant}} = \frac{|A_f| \tau_f + |A_s| \tau_s}{|A_f| + |A_s|}
$$

### 15.7 Noise Floor Detrending in Quiescent Baseline RMS

`find_quiescent_baseline_rms` applies `scipy.signal.detrend(chunk, type="linear")`
to each candidate window **before** computing variance.  This removes slow
drift (electrode drift, drug wash-in ramps) from the variance estimate so
that only high-frequency thermal noise is captured.  Without detrending, a
recording with a slowly drifting baseline can report an inflated RMS noise
floor that suppresses legitimate small-amplitude events.

#### Sliding-window algorithm and event exclusion

The RMS noise floor is computed by advancing a window of fixed length
$w = \lfloor 50\,\text{ms} \times f_s \rfloor$ samples across the
pre-event region in non-overlapping steps.  For each candidate window
$\mathcal{W}_k = \{i : k \cdot w \le i < (k+1) \cdot w\}$:

1. **Preliminary event screen:** the window is rejected if its peak-to-peak
   amplitude exceeds a detection threshold $\theta_{\text{pp}}$
   (default $= 2 \times$ the current RMS estimate, updated iteratively).
   This prevents biological transients -- action potential bursts,
   large EPSPs, stimulus artefacts -- from entering the noise calculation.

2. **Local linear detrend:** `scipy.signal.detrend(V[\mathcal{W}_k], type="linear")`
   removes the first-order trend $\hat{V}_i = \beta_0 + \beta_1 t_i$
   from the window, estimated via OLS on the window samples.

3. **RMS of the detrended residuals:**

$$
\sigma_k = \sqrt{ \frac{1}{w} \sum_{i \in \mathcal{W}_k} \bigl(V_i - \hat{V}_i\bigr)^2 }
$$

4. The final noise floor is the **median** of all accepted $\sigma_k$ values:

$$
\hat{\sigma}_{\text{noise}} = \operatorname{median}_k \sigma_k
$$

   Median aggregation is used rather than mean because the preliminary screen
   may still admit occasional windows containing the tail of a burst; the
   median is resistant to such outliers.

> **Why 50 ms windows?**  At typical patch-clamp sampling rates (10-50 kHz)
> a 50 ms window contains 500-2,500 samples -- enough to robustly estimate
> a linear trend and its residuals while remaining short enough to stay within
> a quiescent inter-burst interval in most in vitro preparations.

---

## 16. Immutable Trace Correction Pipeline

**Module:** `core/processing_pipeline.py` · **Function:** `apply_trace_corrections`

To prevent math artefacts caused by order-dependent GUI interactions, all
backend analysis **must** pass raw data through `apply_trace_corrections()`
before feature extraction.  The function enforces the following four-step
sequence unconditionally:

### Step A - Liquid Junction Potential (LJP) Subtraction

$$
V_{\text{true}}(t) = V_{\text{recorded}}(t) - \text{LJP}
$$

The LJP arises from the electrochemical potential difference between the patch
pipette solution and the bath.  Correcting it is mandatory for any
voltage-dependent analysis (AP threshold, RMP, I-V curve).

> **Biophysical limitations of post-hoc LJP subtraction.**  Subtracting
> a scalar LJP from a recorded voltage trace corrects the *reported*
> membrane potential for passive properties (RMP, $R_{\text{in}}$, $\tau$).
> However, it does **not** retroactively correct the driving forces that
> voltage-gated channels experienced during the recording itself.
>
> During the experiment, the actual transmembrane voltage at every time
> point was $V_{\text{recorded}}(t) + V_{\text{patch}}$, where
> $V_{\text{patch}}$ includes the uncorrected LJP offset.  Ion channels
> that gate as a function of voltage (Na$^+$, K$^+$, Ca$^{2+}$ channels)
> activated, inactivated, and determined their driving forces at these
> uncorrected voltages.  Therefore:
>
> 1. **AP threshold and waveform** are minimally affected by small
>    LJPs ($< 5$ mV) because the absolute voltage error is the same
>    at every sample and threshold detection is differential.
>    Larger LJPs ($> 10$ mV) produce systematic errors in
>    reported threshold and half-width.
> 2. **Current amplitudes and conductances** computed from $I = g(V - E_\text{rev})$
>    use the corrected $V$ but the reversal potential $E_\text{rev}$ was
>    set relative to the uncorrected voltage during the experiment.  Post-hoc
>    LJP correction changes the apparent driving force and therefore alters
>    any reported conductance derived from current measurements.
> 3. **Pharmacological and modulation studies** that depend on absolute
>    channel open probability at a specified voltage should account for
>    the LJP when comparing across preparations or to published data.
>
> In summary: post-hoc LJP subtraction is the accepted standard for
> reporting passive membrane properties in the literature, but its
> limitation must be acknowledged in any analysis that draws conclusions
> about the voltage-dependence of active conductances.

### Step B - P/N Leak Subtraction

*(Armstrong & Bezanilla, 1977; Bezanilla & Armstrong, 1977. The P/N subtraction
protocol scales sub-threshold "leak" sweeps by 1/N and subtracts them from the
test sweep to cancel linear leak current and capacitive transients.)*

$$
I_{\text{corrected}}(t) = I_{\text{signal}}(t)
 - \frac{1}{K} \sum_{k=1}^{K} I_{\text{leak},k}(t) \cdot p
$$

where $K$ is the number of sub-threshold P/N repetitions and $p = 1/N$ is
the scaling factor (default $p=1$).  This removes capacitive transients and
steady-state leak currents before any further correction.

### Step C - Pre-Event Noise Floor Zeroing

$$
V'(t) = V_{\text{corrected}}(t) - \operatorname{median}_{t \in \mathcal{W}_{\text{pre}}} V_{\text{corrected}}(t)
$$

The median of the immediate pre-event window $\mathcal{W}_{\text{pre}}$ is
subtracted as a scalar.  Because Steps A and B have already been applied, this
median reflects only the residual noise floor.

### Step D - Signal Filtering

Any user-requested digital filters (low-pass, notch, etc.) are applied
**after** Steps A-C.  Filtering first would smear step-transients from leak
subtraction across the waveform and corrupt the P/N correction.

> **Immutability guarantee:** regardless of the order in which the user toggles
> preprocessing options in the GUI, the execution order A → B → C → D is always
> enforced by `apply_trace_corrections()`.

---

## 17. 5-Pillar Analyser Architecture

The Synaptipy Analyser UI is structured around exactly **five primary tabs**,
each corresponding to a module-level aggregator entry in the `AnalysisRegistry`:

| Pillar | Registry name | Label | Sub-analyses |
|--------|--------------|-------|--------------|
| 1 | `passive_properties` | Intrinsic Properties | RMP, Rin, Tau, Sag, I-V, Capacitance |
| 2 | `single_spike` | Spike Analysis | Spike Detection, Phase Plane |
| 3 | `firing_dynamics` | Excitability | Excitability, Burst Analysis, Spike Train Dynamics |
| 4 | `synaptic_events` | Synaptic Events | Threshold, Deconvolution, Baseline+Peak+Kinetics |
| 5 | `evoked_responses` | Optogenetics | Optogenetic Sync, Paired-Pulse Ratio |

Leaf registrations (e.g. `spike_detection`, `phase_plane_analysis`) are covered
by their parent module tab via `MetadataDrivenAnalysisTab.get_covered_analysis_names()`
and do not appear as independent top-level tabs.

Custom plugin analyses registered by the user are appended after the five core
pillars in alphabetical order.