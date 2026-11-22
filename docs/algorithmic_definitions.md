# Algorithmic Definitions

This page provides formal mathematical definitions for all metrics computed by
Synaptipy's analysis modules. Every formula below corresponds directly to the
implementation in `src/synaptipy/core/analysis/`. Parameter names in the
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
| Temperature | Room temperature (20-25 degC) |
| Sampling rate | 10-50 kHz |
| Holding potential | -60 to -80 mV (current-clamp) |

**Users working outside these conditions** (e.g., invertebrate preparations,
cardiac myocytes, in vivo recordings, or temperatures > 30 degC) should
adjust threshold parameters according to their preparation's electrophysiological
characteristics. In particular:

- Fast-spiking interneurons may require raising `DVDT_ARTIFACT_CEILING_VS` above
  300 V/s (cortical fast-spiking cells can exceed 400 V/s at 34 degC)
- Slow-spiking cells (e.g., dopaminergic neurons) may need lower `dvdt_threshold`
  (10 V/s) and wider AHP windows
- High-temperature recordings accelerate kinetics by $Q_{10} \approx 2\text{-}3\times$

---

## 1. Baseline / Resting Membrane Potential (RMP)

**Module:** `passive_properties.py` | **Registry name:** `rmp_analysis`

$$
V_{\text{RMP}} = \frac{1}{N} \sum_{i \in \mathcal{W}} V_i
$$

where $\mathcal{W} = \{ i : t_{\text{start}} \le t_i \le t_{\text{end}} \}$ is
the set of sample indices within the baseline window (after optional
`rs_artifact_blanking_ms` offset and per-sweep `ljp_correction_mv` subtraction
$V_{\text{true}} = V_{\text{recorded}} - \text{LJP}$).

**Baseline standard deviation:**

$$
\sigma_{\text{RMP}} = \sqrt{ \frac{1}{N} \sum_{i \in \mathcal{W}} (V_i - V_{\text{RMP}})^2 }
$$

**Single-sweep baseline drift** (`RmpResult.drift`) is the slope $\beta_1$ of
the ordinary least-squares linear fit $V_i = \beta_0 + \beta_1 \, t_i + \varepsilon_i$
over $\mathcal{W}$ (`numpy.polyfit(..., 1)`), reported in mV/s. To prevent
high-frequency electronic noise from inflating the slope estimate, the voltage
slice is pre-smoothed with a **uniform moving average** of width
$w_{50} = \min\!\bigl(\max(3, \lfloor N/3 \rfloor),\; \max(3, \operatorname{round}(50\,\text{ms} / \Delta t))\bigr)$
samples using valid-mode convolution:

$$
\tilde{V}_i = \frac{1}{w_{50}} \sum_{k=0}^{w_{50}-1} V_{i+k},
\quad i = 0,\ldots, N - w_{50}
$$

Across multi-trial recordings, `run_rmp_analysis_wrapper` also fits OLS slope
across valid per-sweep RMP values to report `rmp_drift_rate_mv_per_sweep`.

**Auto-detect baseline** (`find_stable_baseline`) selects the window
$\mathcal{W}^*$ that minimises the sliding-window variance while rejecting
saturated/clipped rails ($\operatorname{Var} \le 10^{-15}$ far from the trace
median):

$$
\mathcal{W}^* = \arg\min_{\mathcal{W}_k}
 \operatorname{Var}\!\bigl(V_{i \in \mathcal{W}_k}\bigr)
$$

where $\mathcal{W}_k$ slides in steps of `step_duration_s` with width
`window_duration_s`.

---

## 2. Input Resistance ($R_{\text{in}}$)

**Module:** `passive_properties.py` | **Registry name:** `rin_analysis`

$$
R_{\text{in}} \;(\text{M}\Omega) = \frac{|\Delta V|}{|\Delta I_{\text{nA}}|}
$$

where

$$
\Delta V = \bar{V}_{\text{response}} - \bar{V}_{\text{baseline}},
\qquad
\Delta I_{\text{nA}} = \frac{|I_{\text{step}} \;(\text{pA})|}{1000}
$$

and $\bar{V}$ denotes the arithmetic mean over the respective time window.

**Conductance:**

$$
G \;(\mu\text{S}) = \frac{1}{R_{\text{in}} \;(\text{M}\Omega)}
$$

### 2.1 Series-Resistance Artifact Blanking

An uncompensated bridge balance produces an instantaneous voltage jump at
stimulus onset. To prevent this $R_s$ artifact from inflating $\Delta V$, the
first `rs_artifact_blanking_ms` milliseconds (default `0.5 ms`) of the response
window are excluded from all voltage measurements:

$$
\mathcal{W}_{\text{resp}}^{\text{blanked}} =
 \{ i : t_{\text{resp,start}} + t_{\text{blank}} \le t_i < t_{\text{resp,end}} \}
$$

where $t_{\text{blank}} = \texttt{rs\_artifact\_blanking\_ms} \times 10^{-3}$.

### 2.2 Peak $R_{\text{in}}$ and Steady-State $R_{\text{in}}$ ($I_h$ separation)

*(HCN channel physiology and $I_h$ current: Robinson & Siegelbaum, 2003.)*

Cells expressing HCN channels ($I_h$) exhibit a voltage sag during sustained
hyperpolarisation: the voltage first reaches a maximum deflection (Peak) and
then partially recovers toward a smaller steady-state deflection.

**Peak $R_{\text{in}}$** (`rin_peak_mohm`) uses the sample of maximum absolute
voltage deflection within the blanked response window:

$$
V_{\text{peak}} = V\!\left[\arg\max_{i \in \mathcal{W}_{\text{resp}}^{\text{blanked}}} |V_i - \bar{V}_{\text{baseline}}|\right],
\qquad
R_{\text{in,peak}} = \frac{|V_{\text{peak}} - \bar{V}_{\text{baseline}}|}{|\Delta I_{\text{nA}}|}
$$

**Steady-State $R_{\text{in}}$** (`rin_steady_state_mohm`) uses the mean voltage
over the **last 20%** of $\mathcal{W}_{\text{resp}}^{\text{blanked}}$,
reflecting the membrane resistance after $I_h$ sag settles:

$$
R_{\text{in,ss}} = \frac{|\bar{V}_{\text{last 20\%}} - \bar{V}_{\text{baseline}}|}{|\Delta I_{\text{nA}}|}
$$

---

## 3. Membrane Time Constant ($\tau$)

**Module:** `passive_properties.py` | **Registry name:** `tau_analysis`

### 3.1 Fit window, sag truncation, and initial-guess estimation

1. **Artifact blanking:** Fitting starts at
   $t_0 = \texttt{stim\_start\_time} + \texttt{artifact\_blanking\_ms} \times 10^{-3}$
   (default blanking `0.5 ms`) and extends to $\texttt{stim\_start\_time} + \texttt{fit\_duration}$.
2. **Dynamic sag-peak truncation:** If the voltage extremum within the fit
   window ($\arg\max V$ for depolarising steps where $V_{\text{end}} > V_0$, or
   $\arg\min V$ for hyperpolarising steps) occurs strictly inside the window
   ($2 < i_{\text{peak}} < N_{\text{fit}} - 1$) and leaves at least 3 samples,
   the fit window is truncated at $i_{\text{peak}}$ so post-peak $I_h$ sag
   rebound does not bias the passive charging time constant.
3. **Deterministic log-linear OLS initial seed:** Using $\hat{V}_{\text{ss}} = \bar{V}_{-5:}$,
   a first-degree polynomial (`numpy.polyfit`) is fitted to
   $\ln(|V(t) - \hat{V}_{\text{ss}}| + 10^{-10})$ versus $t$ across samples
   with $|V - \hat{V}_{\text{ss}}| > 10^{-6}$. When the slope $m < 0$,
   $\tau_{\text{est}} = \operatorname{clip}(-1 / m,\; \tau_{\min},\; \tau_{\max})$;
   otherwise $\tau_{\text{est}}$ falls back deterministically to $10\,\text{ms}$ (`0.01 s`).

### 3.2 Mono-exponential model (`tau_model = "mono"`)

$$
V(t) = V_{\text{ss}} + (V_0 - V_{\text{ss}}) \, e^{-t/\tau}
$$

Fitted via bounded Trust-Region Reflective non-linear least squares
(`scipy.optimize.curve_fit`, `maxfev=5000`, default $\tau \in [0.1\,\text{ms}, 1000\,\text{ms}]$).

### 3.3 Bi-exponential model (`tau_model = "bi"`)

$$
V(t) = V_{\text{ss}}
 + A_{\text{fast}} \, e^{-t/\tau_{\text{fast}}}
 + A_{\text{slow}} \, e^{-t/\tau_{\text{slow}}}
$$

Requires $\ge 6$ samples (`maxfev=10000`). Enforces $\tau_{\text{fast}} \le \tau_{\text{slow}}$
by swapping $(\tau_{\text{fast}}, A_{\text{fast}}, \text{SE}_{\text{fast}})$ and
$(\tau_{\text{slow}}, A_{\text{slow}}, \text{SE}_{\text{slow}})$ post-fit if needed.

### 3.4 Fit quality gate, 95% confidence intervals, and off-relaxation $\tau$

- **Fit Quality Gate (`min_r_squared`, default `0.80`):** Enforced on **both**
  `mono` and `bi` models. The coefficient of determination is
  $R^2 = 1 - \frac{\sum (V_i - \hat{V}_i)^2}{\sum (V_i - \bar{V})^2}$; if
  $R^2 < \texttt{min\_r\_squared}$, the fit is rejected and time constants
  (`tau_ms` or `tau_fast_ms`/`tau_slow_ms`) are returned as `NaN`.
- **95% Confidence Intervals:** Standard errors are computed from the diagonal
  of the parameter covariance matrix $\mathbf{P}_{\text{cov}}$:
  $$
  \text{SE}_{\tau} = \sqrt{[\mathbf{P}_{\text{cov}}]_{\tau\tau}},
  \qquad
  \text{CI}_{95\%} = \tau \pm 1.96 \, \text{SE}_{\tau}
  $$
  `calculate_tau` returns `tau_se_ms`, `tau_ci_lower`, and `tau_ci_upper` (and
  `tau_fast_ci_lower`/`upper`, `tau_slow_ci_lower`/`upper` for `bi`), while
  `run_tau_analysis_wrapper` exposes `tau_ci_95_low` and `tau_ci_95_high`.
- **Post-stimulus off-relaxation (`tau_decay_after_stimulus_ms`):**
  `run_tau_analysis_wrapper` additionally fits a mono-exponential model starting
  at `stim_end_time` (plus `artifact_blanking_ms`) over `fit_duration` to
  quantify membrane discharge after step offset.

---

## 4. Sag Ratio

**Module:** `passive_properties.py` | **Registry name:** `sag_ratio_analysis`

### 4.1 Ratio form (default)

$$
\text{Sag Ratio} = \frac{V_{\text{ss}} - V_{\text{baseline}}}{V_{\text{peak}} - V_{\text{baseline}}}
$$

A value $< 1$ indicates hyperpolarisation-activated sag ($I_h$ current).
A value of $1$ indicates no sag.

**Numerical stability guard:** when $|V_{\text{peak}} - V_{\text{baseline}}| < 10^{-9}\,\text{mV}$,
all sag metrics return `NaN` (via `_sag_nan_payload`) to prevent division by zero.

### 4.2 Percentage form

*(Sag and rebound are hallmarks of HCN-mediated $I_h$; Robinson & Siegelbaum, 2003.)*

$$
\text{Sag} \;(\%) = 100 \times \frac{V_{\text{peak}} - V_{\text{ss}}}{V_{\text{peak}} - V_{\text{baseline}}}
$$

**$V_{\text{peak}}$** is the minimum of the Savitzky-Golay smoothed voltage in
`response_peak_window` (`peak_smoothing_ms`, default `5.0 ms`, polynomial order 3,
odd window length $\ge 5$).

**$V_{\text{ss}}$** is the arithmetic mean of `response_steady_state_window`.

### 4.3 Rebound depolarisation

$$
\Delta V_{\text{rebound}} = \max_{i \in \mathcal{R}} \tilde{V}_i - V_{\text{baseline}}
$$

where $\mathcal{R}$ spans `rebound_window_ms` (default `100.0 ms`) immediately
following `response_steady_state_window[1]`, smoothed with the same
Savitzky-Golay window when sufficient samples are present.

---

## 5. Capacitance ($C_m$)

**Module:** `passive_properties.py` | **Registry name:** `capacitance_analysis`

### 5.1 Current-clamp mode

Accounts for the series (access) resistance $R_s$, which acts in series with
$R_{\text{in}}$:

$$
C_m \;(\text{pF}) = \frac{\tau \;(\text{ms})}{R_{\text{in}} - R_s \;(\text{M}\Omega)} \times 10^3
$$

When $R_s$ is unavailable or $R_s \ge R_{\text{in}}$, the fallback
$C_m = (\tau / R_{\text{in}}) \times 10^3\;\text{pF}$ is used and a warning is
logged (requiring effective resistance $\ge 0.1\,\text{M}\Omega$). Both $\tau$
and $R_{\text{in}}$ are computed from the same current-step trace, and
$R_s^{\text{CC}}$ (`rs_cc_mohm`) is estimated via
`calculate_cc_series_resistance_fast` (Section 5.3).

### 5.2 Voltage-clamp mode

*(Follows Hamill et al., 1981; see Section 15.1 for step-by-step derivation.)*

Given baseline-subtracted transient current $I_{\text{trans}}(t) = I(t) - \bar{I}_{\text{baseline}}$,
steady-state leak $I_{\text{ss}} = \bar{I}_{\text{trans, last 20\%}}$, and purely
capacitive component $\Delta I(t) = I_{\text{trans}}(t) - I_{\text{ss}}$,
`calculate_capacitance_vc` **always computes both** capacitance estimators
alongside series resistance:

1. **Series resistance (`series_resistance_mohm`):**
   $$
   R_s \;(\text{M}\Omega) = \frac{|\Delta V \;(\text{mV})|}{\max_t |\Delta I(t) \;(\text{pA})|} \times 10^3
   $$
2. **Exponential-fit capacitance (`capacitance_pf`):** Fits
   $|\Delta I(t)| = A e^{-t/\tau_{\text{trans}}}$ from the transient peak
   onward and computes
   $$
   C_m \;(\text{pF}) = \frac{\tau_{\text{trans}} \;(\text{s})}{R_s \;(\text{M}\Omega) \times 10^6} \times 10^{12}
   $$
   falling back to the charge-integral estimate if the mono-exponential fit
   fails or has fewer than 4 decay samples.
3. **Charge-integral capacitance (`capacitance_charge_pf`):** Computed
   unconditionally via trapezoidal integration (`numpy.trapezoid`):
   $$
   C_{m,\text{charge}} \;(\text{pF}) = \frac{\int_{t_0}^{t_1} |\Delta I(t)| \, dt \;(\text{pA}\cdot\text{s})}{|\Delta V \;(\text{mV})|} \times 10^3
   $$

### 5.3 Current-clamp series resistance ($R_s^{\text{CC}}$)

`calculate_cc_series_resistance_fast` evaluates the fast resistive voltage jump
at current-step onset over an initial window `artifact_window_ms` (default
**`0.5 ms`**). When the window contains $\ge 5$ samples, `_extrapolate_rs_at_t0`
fits $V_{\text{art}}(t) = A e^{-t/\tau} + C$ over $[0, \texttt{artifact\_window\_ms})$
and evaluates $\Delta V_{\text{fast}} = V_{\text{art}}(0) = A + C$ to recover
the instantaneous resistive drop before membrane RC charging; when fewer than 5
samples are present (or `curve_fit` does not converge), it falls back to
$\operatorname{mean}(V_{\text{art}})$:

$$
R_s^{\text{CC}} \;(\text{M}\Omega)
= \frac{|\Delta V_{\text{fast}} \;(\text{mV})|}{|I_{\text{step}} \;(\text{pA})|} \times 10^3
$$

> **Sampling-rate dependency note:** With the default `0.5 ms` window, the
> artifact slice contains **5 samples at 10 kHz** (the minimum threshold for
> exponential extrapolation to $t = 0$), **10 samples at 20 kHz**, and
> **25 samples at 50 kHz**. Recordings sampled below 10 kHz contain fewer than
> 5 samples in `0.5 ms` and therefore fall back to the window mean; for highest
> $R_s^{\text{CC}}$ and $C_m$ accuracy in current clamp, sampling at
> $\ge 20\,\text{kHz}$ (or using voltage-clamp transient analysis, Section 5.2)
> is recommended.

---

## 6. Spike Detection and Action Potential Features

**Module:** `single_spike.py` | **Registry name:** `spike_detection`

### 6.1 Two-stage $dV/dt$ + voltage threshold spike detection

`detect_spikes_threshold` identifies action potentials in four steps:

1. **5 kHz zero-phase Butterworth pre-filter:** When $5000\,\text{Hz} < f_{\text{Nyquist}}$,
   the trace is low-pass filtered with a 4th-order Butterworth SOS filter via
   `_sosfiltfilt_safe` (`scipy.signal.butter(4, 5000.0, btype="low", output="sos", fs=fs)`),
   suppressing high-frequency acquisition noise before differentiation.
2. **Upward $dV/dt$ crossing:** Computes $\frac{dV}{dt} = \frac{\nabla V_{\text{filt}}}{\Delta t}$
   (mV/s) and finds candidate onset indices where
   $\frac{dV}{dt}[i-1] < 1000\,\theta_{dV/dt}$ and
   $\frac{dV}{dt}[i] \ge 1000\,\theta_{dV/dt}$ (default $\theta_{dV/dt} = 20.0\,\text{V/s}$).
3. **Peak search and voltage gate:** Searches forward over
   `peak_search_window_samples` (default `5 ms`) for the local maximum
   $i_{\text{peak}} = \arg\max V$.
4. **Conditional refractory commit:** Accepts $i_{\text{peak}}$ and commits
   `refractory_samples` suppression **only** when $V[i_{\text{peak}}] \ge V_{\text{threshold}}$
   (default `-20.0 mV`), preventing sub-threshold $dV/dt$ glitches from masking
   subsequent genuine spikes.

### 6.2 Action potential onset / threshold (`calculate_spike_features`)

*(Default threshold $\theta_{dV/dt} = 20\,\text{V/s}$, Bean, 2007; artifact ceiling
`DVDT_ARTIFACT_CEILING_VS = 300 V/s`, Naundorf et al., 2006; minimum rising phase
`MIN_RISING_PHASE_MS = 0.2 ms`.)*

1. **9.9 kHz 4th-order Bessel pre-filter:** When $9900\,\text{Hz} < f_{\text{Nyquist}}$,
   `calculate_spike_features` filters the trace with a zero-phase 4th-order
   Bessel low-pass filter (`scipy.signal.bessel(4, 9900.0, btype="low", output="sos", fs=fs)`
   via `sosfiltfilt`), preserving linear phase across fast upstrokes before
   computing $\frac{dV}{dt} = \nabla V_{\text{filt}} / \Delta t$.
2. **Backward search from peak $dV/dt$:** Within the pre-peak `onset_lookback`
   window (default `10 ms`), Synaptipy locates the upstroke velocity maximum
   $k_{\max} = \arg\max_{k} \frac{dV}{dt}[k]$ and scans **backward** from
   $k_{\max}$ to find the last sample $k_{\text{below}} \le k_{\max}$ with
   $\frac{dV}{dt}[k_{\text{below}}] < 1000\,\theta_{dV/dt}$. Action potential
   onset is the next sample $k_{\text{thresh}} = \min(k_{\text{below}} + 1,\; N_{\text{lookback}} - 1)$
   (with a $2\,\text{ms}$ pre-peak fallback if no sample falls below threshold).
3. **Boundary artifact QC (`at_edge`):** When $k_{\text{thresh}} = 0$ (crossing
   pinned at the start edge of the lookback window) **and** either
   $\max \frac{dV}{dt} > 300\,\text{V/s}$ or $(i_{\text{peak}} - i_{\text{thresh}})\Delta t < 0.2\,\text{ms}$,
   `ap_threshold` is set to `NaN`.

### 6.3 Amplitude

$$
A_{\text{spike}} = V_{\text{peak}} - V_{\text{threshold}}
$$

### 6.4 Half-width

The half-amplitude voltage level is

$$
V_{50} = V_{\text{threshold}} + 0.5 \, A_{\text{spike}}
$$

Half-width (`half_width`, in ms) is the elapsed time between the upward and
downward crossings of $V_{50}$, computed via **sub-sample linear interpolation**
between the bracketing discrete samples on both the rising and falling phases.

### 6.5 Rise time (10-90%)

$$
t_{\text{rise}} = t_{V_{90,\text{rise}}} - t_{V_{10,\text{rise}}}
$$

where $V_x = V_{\text{threshold}} + (x/100) \, A_{\text{spike}}$, with both
$t_{V_{10}}$ and $t_{V_{90}}$ evaluated by sub-sample linear interpolation.

### 6.6 Decay time (90-10%)

$$
t_{\text{decay}} = t_{V_{10,\text{fall}}} - t_{V_{90,\text{fall}}}
$$

evaluated on the post-peak falling phase via sub-sample linear interpolation.

### 6.7 Afterhyperpolarisation (AHP)

*(Fast AHP: BK/Kv3 channel kinetics, 1-5 ms window, Storm, 1987; Medium AHP:
SK channel kinetics, 10-50 ms window, Sah & Faber, 2002; Savitzky-Golay filter:
Savitzky & Golay, 1964.)*

The post-peak search window `ahp_window_sec` (default `50 ms`) is bounded per
spike before the next spike peak ($N_{\text{AHP},i} = \min(N_{\text{AHP}},\; i_{\text{peak},i+1} - i_{\text{peak},i})$):

1. **Dynamic trough localisation (`ahp_time`, `trough_v`):** Searches for the
   first upward zero-crossing of $dV/dt$ ($dV/dt_{k-1} < 0$ and $dV/dt_k \ge 0$,
   marking the end of repolarisation), falling back to $\arg\min$ of the
   Savitzky-Golay-smoothed waveform (polynomial order 3, odd window
   $w = \max(5, \lfloor 5\,\text{ms}/\Delta t \rfloor)$). The trough voltage
   `trough_v` ($V_{\text{AHP,min}}$) is computed as the **raw voltage mean over
   a $\pm 1\,\text{ms}$ window** (`int(0.001 / dt)` samples on each side) around
   the detected trough index to suppress single-sample electronic noise.
2. **Component AHP depths (`fahp_depth`, `mahp_depth`):** Separate raw-voltage
   minima over `[1 ms, 5 ms)` and `[10 ms, 50 ms)` post-peak yield
   `fahp_depth` and `mahp_depth` relative to $V_{\text{threshold}}$ (Section 15.3).
3. **AHP duration (`ahp_duration_half`):** Time (ms) from the post-peak downward
   crossing below $V_{\text{threshold}}$ to post-trough recovery back to
   $\ge V_{\text{threshold}} - 0.1 \, A_{\text{spike}}$.

### 6.8 Afterdepolarisation (`adp_amplitude`)

To avoid Savitzky-Golay overshoot ringing while preserving genuine depolarising
humps:

1. **Variation-diminishing Gaussian smoothing:** The post-peak `ahp_window`
   waveform is smoothed with `scipy.ndimage.gaussian_filter1d` (`mode="nearest"`)
   using $\sigma = \max(1.0,\; 0.2\,\text{ms} / \Delta t)$ samples.
2. **Next-spike onset bound:** For spike trains, the search window for spike $i$
   is strictly bounded before the **onset** (`thresh_indices[i+1]`) of spike
   $i + 1$: $B_i = \min\bigl(N_{\text{AHP},i},\; \max(1,\; i_{\text{thresh},i+1} - i_{\text{peak},i})\bigr)$.
3. **Fast trough and prominence-gated peak:** Within $V_{\text{smooth}}[0:B_i]$,
   Synaptipy locates the first strict local minimum below $V_{\text{threshold}}$
   ($V_k \le V_{k-1}$, $V_k < V_{k+1}$, and $V_k < V_{\text{threshold}}$) as
   $i_{\text{trough}}$, then scans subsequent local maxima
   ($V_m > V_{m-1}$ and $V_m \ge V_{m+1}$) and accepts the first candidate
   satisfying **both** prominence conditions:
   $$
   A_{\text{ADP}} = V_m - V_{i_{\text{trough}}} > 0.25\,\text{mV}
   \quad \text{and} \quad
   V_m - \min_{j \in (m, B_i)} V_j \ge 0.20\,\text{mV}
   $$
   If no candidate satisfies both conditions, `adp_amplitude` is `NaN`.

### 6.9 Maximum and minimum $dV/dt$, ratio, and phase-plane area

Raw waveform derivatives ($\nabla V / \Delta t / 1000$, in V/s) are smoothed with
a uniform rolling-mean kernel (`scipy.ndimage.convolve1d`, `mode="nearest"`) of
odd width $w = \max(3, \lfloor 0.1\,\text{ms} / \Delta t \rfloor)$:

$$
\left(\frac{dV}{dt}\right)_{\max} = \max_{t \in [t_{\text{thresh}}, t_{\text{peak}})} \frac{dV}{dt}(t),
\qquad
\left(\frac{dV}{dt}\right)_{\min} = \min_{t > t_{\text{peak}}} \frac{dV}{dt}(t)
$$

$$
\text{Upstroke/Downstroke Ratio} = \frac{(dV/dt)_{\max}}{|(dV/dt)_{\min}|}
$$

**Phase-plane loop area (`phase_plane_area`):** Enclosed area of the $(V, dV/dt)$
loop from $i_{\text{thresh}}$ to post-peak threshold crossing via the Shoelace
formula:

$$
\text{Area} = \frac{1}{2} \left| \sum_k V_k \dot{V}_{k+1} - \sum_k V_{k+1} \dot{V}_k \right|
$$

### 6.10 Absolute Peak Voltage, Overshoot, and AP Delay

$$
V_{\text{peak,abs}} = V[i_{\text{peak}}],
\qquad
\text{Overshoot} \;(\text{mV}) = \max(0,\; V_{\text{peak,abs}}),
\qquad
t_{\text{delay}} = t[i_{\text{thresh}}]
$$

Together with `ap_width_arbitrary`, `SingleSpikeResult` provides 18 extracted
scalar features per action potential.

---

## 7. Synaptic Event Detection

**Module:** `synaptic_events.py`

### 7.1 Adaptive prominence threshold detection (`event_detection_threshold`)

1. **Rolling median baseline subtraction:** Subtracts a running median of odd
   window length $\lfloor \texttt{rolling\_baseline\_window\_ms} \cdot 10^{-3} f_s \rfloor$
   (default `100.0 ms`) when $\ge 3$ samples.
2. **Noise floor estimation (`use_quiescent_noise_floor=True` default):**
   - When `use_quiescent_noise_floor=True` (default), $\hat{\sigma}$ is computed
     by `find_quiescent_baseline_rms` over `quiescent_window_ms` (default `20.0 ms`;
     see Section 7.2.1 and Section 15.7).
   - When `use_quiescent_noise_floor=False`, $\hat{\sigma}$ falls back to the
     Gaussian-consistent Median Absolute Deviation (Hampel, 1974;
     Rousseeuw & Croux, 1993): $\hat{\sigma} = 1.4826 \times \text{MAD}$.
3. **Peak detection and refinement:** `scipy.signal.find_peaks` runs on the
   polarity-oriented trace with prominence $p = \max(|\text{threshold}|, 2\hat{\sigma})$,
   height $|\text{threshold}|$, minimum separation $\max(1, \lfloor \texttt{refractory\_period} \cdot f_s \rfloor)$,
   and minimum width $\max(2, \lfloor 0.2\,\text{ms} \cdot f_s \rfloor)$ samples,
   followed by optional slope-artifact masking and local raw-peak refinement
   within $\pm \max(10, d_{\text{min}} // 2)$ samples.
4. **Dynamic charge and optional decay kinetics:** Each event's area under the
   curve (`calculate_event_charge_dynamic`) is integrated via `numpy.trapezoid`
   up to baseline return or the $3\sigma_{dV/dt}$ onset of a subsequent summating
   event; when `compute_kinetics=True`, `fit_biexponential_decay` fits mono- and
   bi-exponential decay time constants (`tau_mono_ms`, `tau_fast_ms`, `tau_slow_ms`).
5. **Zero-event `NaN` convention:** When zero events are detected
   (`event_count == 0`), `frequency_hz` is `0.0` while all amplitude, charge,
   and kinetic summaries (`mean_amplitude`, `amplitude_sd`,
   `mean_local_amplitude`, `mean_event_charge`, `tau_mono_ms`, `tau_fast_ms`,
   `tau_slow_ms`) return `NaN` rather than `0.0`.

### 7.2 Multi-scale matched-filter template detection (`event_detection_deconvolution`)

Synaptipy builds a bank of $K$ templates scaled by user-configurable
`kernel_multipliers` $\{m_1, \ldots, m_K\}$ (default `[1.0, 2.0, 3.0]`, UI string
`"1.0, 2.0, 3.0"`) and user-configurable `kernel_shape` (`"bi-exponential"`
default or `"mono-exponential"`):

$$
\tilde{k}_s(t) =
\begin{cases}
e^{-t/(s \cdot \tau_{\text{decay}})} - e^{-t/\tau_{\text{rise}}} & \text{bi-exponential } (s\tau_{\text{decay}} \neq \tau_{\text{rise}}) \\
t \, e^{-t/\tau_{\text{rise}}} & \text{alpha limit } (s\tau_{\text{decay}} = \tau_{\text{rise}}) \\
e^{-t/(s \cdot \tau_{\text{decay}})} & \text{mono-exponential}
\end{cases}
$$

sampled over $t \in [0, 5 \max(s\tau_{\text{decay}}, \tau_{\text{rise}}))$ and
normalised to **unit peak amplitude**:

$$
k_s(t) = \frac{\tilde{k}_s(t)}{\max_t |\tilde{k}_s(t)|}
$$

Each kernel is **cross-correlated** (matched-filtered, not deconvolved) with the
polarity-oriented baseline-corrected signal $x[n]$ via FFT convolution with the
time-reversed kernel $k_s[-n]$ (`scipy.signal.fftconvolve(x, k_s[::-1], mode="same")`),
then z-scored using its own Gaussian-scaled MAD:

$$
c_s[n] = (x \star k_s)[n],
\qquad
z_s[n] = \frac{c_s[n] - \operatorname{median}(c_s)}{1.4826 \times \operatorname{MAD}(c_s)}
$$

Each $z_s$ trace is circularly shifted (with zero-fill at boundaries) so its
template peak aligns with the primary ($m_1$) kernel reference, and combined
pointwise across scales:

$$
z_{\text{combined}}[n] = \max_{s \in \{m_1, \ldots, m_K\}} z_{s,\text{aligned}}[n]
$$

**Peak selection and minimum distance rule:** Peaks are detected on
$z_{\text{combined}}$ where $z_{\text{combined}}[n] \ge \texttt{threshold\_sd}$
(default `4.0`) with minimum inter-event separation:

$$
d_{\min} =
\begin{cases}
\max\!\bigl(1,\; \lfloor \texttt{min\_event\_distance\_ms} \cdot 10^{-3} f_s \rfloor\bigr) & \text{if } \texttt{min\_event\_distance\_ms} > 0 \\
\max\!\bigl(1,\; \lfloor \tau_{\text{decay}} \cdot f_s \rfloor\bigr) & \text{if } \texttt{min\_event\_distance\_ms} = 0
\end{cases}
$$

Detected peaks are refined to the local raw extremum within a Voronoi-bounded
radius $\max(20, \lfloor \tau_{\text{decay}} f_s \max_k m_k \rfloor)$. When
`event_count == 0`, `mean_amplitude`, `amplitude_sd`, and `mean_local_amplitude`
return `NaN`.

### 7.2.1 Quiescent Baseline Noise Floor (`find_quiescent_baseline_rms`)

The quiescent noise floor is estimated via a sliding minimum-variance window of
length $W = \max(2, \lfloor \texttt{window\_ms} \cdot 10^{-3} f_s \rfloor)$
samples (default `window_ms = 20.0 ms`) advancing in **50%-overlapping steps**
$S = \max(1, \lfloor W / 2 \rfloor)$ across the entire trace:

$$
k^* = \arg\min_{k} \operatorname{Var}\!\bigl(\tilde{x}_{kS : kS + W}\bigr),
\qquad
\hat{\sigma}_{\text{noise}} = \max\!\left(10^{-6},\; \sqrt{\frac{1}{W} \sum_{i=0}^{W-1} \tilde{x}_{k^* S + i}^{\,2}}\right)
$$

where $\tilde{x}$ is the linearly detrended chunk
(`scipy.signal.detrend(chunk, type="linear")`). Detrending removes slow
electrode drift before computing variance, while minimum-variance selection
across the full trace automatically avoids spontaneous bursts regardless of when
they occur.

### 7.3 Local Pre-Event Baseline (Dynamic Amplitude for Summating Events)

For each detected event peak index $i_k$, `compute_local_pre_event_baseline`
searches `pre_event_window_ms` (default `2.0 ms`) immediately preceding $i_k$:

$$
V_{\text{foot},k} =
\begin{cases}
\max_{j \in \mathcal{P}_k} V_j & \text{(negative polarity, } \texttt{baseline\_method="local\_extrema"}\text{)} \\
\min_{j \in \mathcal{P}_k} V_j & \text{(positive polarity, } \texttt{baseline\_method="local\_extrema"}\text{)} \\
\bar{V}_{\mathcal{P}_k} & \text{(}\texttt{baseline\_method="mean"}\text{)}
\end{cases}
$$

where $\mathcal{P}_k = \{j : \max(0, i_k - N_{\text{pre}}) \le j < i_k\}$. The
local amplitude (`_local_amplitudes`, summarised by `mean_local_amplitude`) is:

$$
A_{\text{local},k} =
\begin{cases}
V_{\text{foot},k} - V_{i_k} & \text{(negative polarity)} \\
V_{i_k} - V_{\text{foot},k} & \text{(positive polarity)}
\end{cases}
$$

---

## 8. I-V Curve

**Module:** `passive_properties.py` | **Registry name:** `iv_curve_analysis`

For each sweep $n$:

$$
I_n = I_{\text{start}} + n \times I_{\text{step}}, \qquad
\Delta V_n = \bar{V}_{\text{response},n} - \bar{V}_{\text{baseline},n}
$$

**Subthreshold Ohmic sweep selection:** To prevent active action potentials on
depolarising steps from distorting the passive slope resistance, sweeps whose
maximum response-window voltage reaches or exceeds $-15.0\,\text{mV}$
($\max_{t \in \mathcal{W}_{\text{resp}}} V_n(t) \ge -15.0\,\text{mV}$) are
excluded from linear regression whenever at least two subthreshold sweeps
($\max V_n < -15.0\,\text{mV}$) exist:

$$
R_{\text{in,aggregate}} \;(\text{M}\Omega) =
\frac{\sum_{n \in \mathcal{S}} (\Delta I_{\text{nA},n} - \overline{\Delta I}_{\text{nA}})(\Delta V_n - \overline{\Delta V})}
     {\sum_{n \in \mathcal{S}} (\Delta I_{\text{nA},n} - \overline{\Delta I}_{\text{nA}})^2}
$$

reported alongside `iv_intercept` and `iv_r_squared`.

**Dynamic Rectification Index (`rectification_index`):** When at least two
hyperpolarising sweeps ($I_n < 0$ and $\Delta V_n \neq 0$) are present, let
$(I_{\min}, \Delta V_{\min})$ be the most hyperpolarised step and
$(I_{\max < 0}, \Delta V_{\max < 0})$ be the smallest negative step. Their chord
conductances ($G = |I| / |\Delta V|$) define:

$$
\text{Rectification Index} =
\frac{|I_{\min}| / |\Delta V_{\min}|}{|I_{\max < 0}| / |\Delta V_{\max < 0}|}
$$

Values $> 1$ indicate inward rectification (e.g. $I_h$ or Kir conductances);
$1.0$ indicates a linear Ohmic I-V relationship.

---

## 9. Burst Analysis

**Module:** `firing_dynamics.py` | **Registry name:** `burst_analysis`

*(Criterion adapted from Grace & Bunney, 1984; dynamic ISI fraction motivated by
Harris et al., 2001.)*

A burst begins when $\text{ISI}_k \le \texttt{max\_isi\_start}$ and continues
while $\text{ISI}_k \le \texttt{max\_isi\_end}$. Groups with fewer than
`min_spikes` spikes are discarded.

**Dynamic threshold mode (`dynamic_burst=True`):** Both start and end ISI
boundaries are set to $\texttt{burst\_isi\_fraction} \times \overline{\text{ISI}}$
(default `0.3`, i.e., 30% of the train's mean ISI).

$$
f_{\text{burst}} = \frac{N_{\text{bursts}}}{T_{\text{window}}}
$$

---

## 10. Excitability (F-I Curve)

**Module:** `firing_dynamics.py` | **Registry name:** `excitability_analysis`

For each sweep $n$ (optionally clipped to `[analysis_start_s, analysis_end_s]`)
with injected current $I_n$ and window duration $T_{\text{window},n}$, let
$N_n$ be the detected spike count and $t_1, \ldots, t_{N_n}$ the spike peak
timestamps:

$$
f_n =
\begin{cases}
0 & N_n = 0 \\
\dfrac{N_n}{T_{\text{window},n}} & N_n = 1 \;\text{(single-spike censorship guard)} \\[8pt]
\dfrac{N_n}{T_{\text{window},n}} & 2 \le N_n \le 3 \text{ and } (t_{N_n} - t_1) < 0.25\,T_{\text{window},n} \;\text{(early depolarisation block)} \\[8pt]
\dfrac{N_n - 1}{t_{N_n} - t_1} & \text{otherwise (mean instantaneous firing rate)}
\end{cases}
$$

The sustained window rate $N_n / T_{\text{window},n}$ is also retained for all
sweeps in `window_frequencies`.

- **Rheobase (`rheobase_pa`):** Minimum current $I_n$ (after sorting sweeps by
  ascending $I_n$) eliciting $N_n \ge 1$ spike ($i_{\text{rheo}}$).
- **Depolarisation-block-aware F-I slope (`fi_slope`):** Ordinary least-squares
  regression $f = \alpha I + \beta$ (Hz/pA) fitted from $i_{\text{rheo}}$ **up
  to and including the sweep of maximum firing rate**
  $i_{\text{peak}} = \arg\max_{i \ge i_{\text{rheo}}} f_i$, excluding post-peak
  depolarisation-block sweeps where frequency collapses. Reports `fi_slope`,
  `fi_r_squared`, `fi_p_value`, and `fi_slope_se`.
- **Per-sweep Adaptation Ratio (`adaptation_ratios`):** For sweeps with
  $N_n \ge 3$ spikes and $\text{ISI}_{\text{first}} > 1\,\mu\text{s}$:
  $$
  \text{Adaptation Ratio}_n = \operatorname{clip}\!\left(\frac{\text{ISI}_{\text{last}}}{\text{ISI}_{\text{first}}},\; 0,\; 1000\right)
  $$
  *(Note: this last-to-first ISI ratio is distinct from the normalised
  consecutive ISI-difference `adaptation_index` computed by `train_dynamics` in
  Section 12.)*
- **Per-sweep Spike Broadening Index (`broadening_indices`):**
  $\text{HW}_{\text{last}} / \text{HW}_{\text{first}}$ for sweeps with $\ge 2$
  valid spike half-widths.

---

## 11. Phase Plane Analysis

**Module:** `single_spike.py` | **Registry name:** `phase_plane_analysis`

`calculate_dvdt` computes the discrete voltage derivative in V/s via
`numpy.gradient` and applies a 3rd-order **Savitzky-Golay filter**
(`scipy.signal.savgol_filter`) directly to the derivative array rather than
pre-smoothing voltage with a Gaussian (which would attenuate peak upstroke
velocity):

$$
\left(\frac{dV}{dt}\right)_{\text{raw}} = \frac{\nabla V}{1000 \, \Delta t},
\qquad
\frac{dV}{dt}(t) = \operatorname{SavGol}_3\!\left(\left(\frac{dV}{dt}\right)_{\text{raw}},\; w_{\sigma}\right)
$$

where $w_{\sigma} = \max(5, \lfloor \sigma_{\text{ms}} \cdot 10^{-3} f_s \rfloor)$
rounded up to the next odd integer (unsmoothed when $\sigma_{\text{ms}} = 0$).

**Inter-spike trough windowing and threshold kink detection (`detect_threshold_kink`):**
For each detected spike peak $i_{\text{peak},m}$, the lookback start index is
bounded both by `search_window_ms` (default `5.0 ms`) and, for $m > 0$, by the
inter-spike voltage minimum following the preceding spike peak
$i_{\text{peak},m-1}$:

$$
i_{\text{low},m} = \max\!\left(
  0,\;
  i_{\text{peak},m} - N_{\text{search}},\;
  i_{\text{peak},m-1} + \arg\min_{j \in [i_{\text{peak},m-1},\, i_{\text{peak},m})} V_j
\right)
$$

Within $[i_{\text{low},m}, i_{\text{peak},m})$, `_resolve_single_kink_index`
selects:
1. The sample immediately following the last sample with $dV/dt \le \theta_{dV/dt}$
   (default `20.0 V/s`), or the first sample $> \theta_{dV/dt}$;
2. **Phase-slope fallback:** if $dV/dt$ does not cross $\theta_{dV/dt}$ and
   `kink_slope` ($\kappa$, default `10.0`) $> 0$, the first sample where phase
   slope $\frac{\Delta(dV/dt)}{\Delta V} \ge \kappa$ (with $|\Delta V| > 10^{-6}\,\text{mV}$
   and $dV/dt > 0$).

---

## 12. Spike Train Dynamics

**Module:** `firing_dynamics.py` | **Registry name:** `train_dynamics`

Given $N$ spike timestamps $t_1 < t_2 < \cdots < t_N$ (within optional
`[analysis_start_s, analysis_end_s]`), let $\text{ISI}_i = t_{i+1} - t_i$ for
$i = 1, \ldots, M$ ($M = N - 1$):

- **First-spike delay (`first_spike_delay_ms`):** $(t_1 - t_{\text{analysis,start}}) \times 10^3$ (for $N \ge 1$).
- **First ISI (`first_isi_ms`):** $\text{ISI}_1 \times 10^3$ (for $N \ge 2$).
- **Coefficient of Variation (`cv`):**
  $$
  \text{CV} = \frac{\sigma_{\text{ISI}}}{\mu_{\text{ISI}}}
  $$
  ($\text{CV} = 0$: regular; $\text{CV} = 1$: Poisson).

For trains with $N \ge 3$ spikes ($M \ge 2$ positive ISIs):

- **Local $\text{CV}_2$ (`cv2`, Holt et al., 1996):**
  $$
  \text{CV}_2 = \frac{1}{M-1} \sum_{i=1}^{M-1}
   \frac{2 \,|\text{ISI}_{i+1} - \text{ISI}_i|}{\text{ISI}_{i+1} + \text{ISI}_i}
  $$
  Each pair is evaluated only when $\text{ISI}_{i+1} + \text{ISI}_i > \varepsilon_{\text{ISI}} = 10^{-9}\,\text{s}$,
  with guarded pairs set to `NaN` and excluded via `numpy.nanmean`.

- **Local Variation (`lv`, Shinomoto et al., 2003):**
  $$
  \text{LV} = \frac{3}{M-1} \sum_{i=1}^{M-1}
   \left( \frac{\text{ISI}_i - \text{ISI}_{i+1}}{\text{ISI}_i + \text{ISI}_{i+1}} \right)^{\!2}
  $$
  Evaluated when $(\text{ISI}_i + \text{ISI}_{i+1})^2 > \varepsilon_{\text{ISI}}^2 = 10^{-15}\,\text{s}^2$
  and aggregated via `numpy.nanmean` ($\text{LV} < 1$: regular; $\text{LV} \approx 1$: Poisson; $\text{LV} > 1$: bursty).

- **Spike Frequency Adaptation Index (`adaptation_index`):**
  $$
  \text{Adaptation Index} = \frac{1}{M-1} \sum_{i=1}^{M-1}
    \frac{\text{ISI}_{i+1} - \text{ISI}_i}{\text{ISI}_{i+1} + \text{ISI}_i}
  $$
  Guarded by $\text{ISI}_{i+1} + \text{ISI}_i > 10^{-9}\,\text{s}$ and aggregated
  via `numpy.nanmean`. A value of $0$ indicates stationary regular firing,
  $> 0$ indicates spike-frequency adaptation (slowing), and $< 0$ indicates
  acceleration.

- **Spike Broadening Index (`spike_broadening_index`):**
  $\text{HW}_{\text{last}} / \text{HW}_{\text{first}}$ when $\ge 3$ spikes yield
  finite half-widths.

---

## 13. Evoked Responses and Short-Term Plasticity

**Module:** `evoked_responses.py`

### 13.1 Evoked / Optogenetic Synchronisation (`optogenetic_sync`)

**TTL edge detection (`extract_ttl_epochs`):** Binarises the TTL trace at
`ttl_threshold` (with automatic midpoint fallback when range $> 0.3\,\text{V}$
and fixed threshold yields zero edges) and locates rising edges via `numpy.diff`.

Over stimuli $j = 1, \ldots, N_{\text{stim}}$ that elicit at least one detected
spike or synaptic event within $[t_{\text{stim},j},\; t_{\text{stim},j} + T_{\text{resp}}]$
($N_{\text{resp}}$ successful trials, first-event latency
$L_j = (t_{\text{event},j,1} - t_{\text{stim},j}) \times 10^3\,\text{ms}$):

$$
\bar{L} = \frac{1}{N_{\text{resp}}} \sum_{j=1}^{N_{\text{resp}}} L_j,
\qquad
P_{\text{resp}} = \frac{N_{\text{resp}}}{N_{\text{stim}}},
\qquad
\text{Jitter} = \sigma(L_j)
$$

Peak evoked amplitude (`mean_response_amplitude`) is measured per stimulus over
`[t_stim + t_blank, t_stim + amplitude_window_ms]` relative to the preceding
`baseline_window_ms` mean.

### 13.2 Two-Pulse and N-Pulse Paired-Pulse Ratio (`paired_pulse_ratio`)

Both two-pulse `calculate_paired_pulse_ratio` and general $N$-pulse
`calculate_n_pulse_ratio` (`run_ppr_wrapper`) correct for temporal summation by
evaluating the fitted exponential decay tail of preceding response(s) **at the
subsequent response's actual peak timestamp $t_{\text{peak},i}$** rather than at
stimulus onset $t_{\text{stim},i}$. In the two-pulse function, $R_1$'s tail is
fitted with a bi-exponential model (falling back to mono-exponential) over
`[stim1 + fit_decay_from_ms, min(stim1 + fit_decay_from_ms + fit_decay_window_ms, stim2)]`,
evaluated at $t_{\text{peak},2}$ to obtain $V_{\text{tail}}(t_{\text{peak},2})$,
and subtracted from $V(t_{\text{peak},2})$ (while also reporting diagnostic
`residual_at_stim2`; see Section 15.5 and Section 15.6 for the full $N$-pulse
formulation).

### 13.3 Stimulus Train Short-Term Plasticity (`stimulus_train_stp`)

For chronologically ordered stimulus onsets $t_{\text{stim},1}, \ldots, t_{\text{stim},N}$,
`calculate_stimulus_train_stp` computes for each pulse $k \in \{1, \ldots, N\}$
the pre-pulse baseline $\text{bl}_k = \bar{V}_{[t_{\text{stim},k} - T_{\text{bl}},\, t_{\text{stim},k})}$
and artifact-blanked peak amplitude over
$\mathcal{W}_k = [t_{\text{stim},k} + t_{\text{blank}},\; t_{\text{stim},k} + T_{\text{resp}}]$:

$$
R_k =
\begin{cases}
\text{bl}_k - \min_{t \in \mathcal{W}_k} V(t) & \text{(negative polarity)} \\
\max_{t \in \mathcal{W}_k} V(t) - \text{bl}_k & \text{(positive polarity)}
\end{cases},
\qquad
r_k = \frac{R_k}{R_1} \quad (|R_1| > 10^{-12})
$$

**Steady-state ratio (`steady_state_ratio`):** Arithmetic mean of normalised
amplitudes over the terminal $m = \min(3, N)$ pulses (for $N \ge 2$, else `NaN`):

$$
\text{SSR} = \frac{1}{\min(3, N)} \sum_{k = N - \min(3, N) + 1}^{N} r_k
$$

**Short-term plasticity classification (`stp_type`):** Compares initial
paired-pulse direction ($R_2$ vs. $R_1$) against late-train direction
($R_N$ vs. $R_1$):

$$
\text{stp\_type} =
\begin{cases}
\texttt{"none"} & N < 2 \\
\texttt{"biphasic"} & N \ge 4 \text{ and } (R_2 > R_1) \neq (R_N > R_1) \\
\texttt{"facilitation"} & R_2 > R_1 \text{ (otherwise)} \\
\texttt{"depression"} & R_2 \le R_1 \text{ (otherwise)}
\end{cases}
$$

For example, a synapse that facilitates on pulse 2 ($R_2 > R_1$) before
depleting below baseline at the end of a $\ge 4$-pulse train ($R_N \le R_1$) is
classified as `"biphasic"`.

---

## 14. Signal Preprocessing

**Modules:** `core/signal_processor.py`, `core/processing_pipeline.py`, `core/analysis/preprocessing.py`

### 14.1 Digital filters and zero-phase execution

`signal_processor.py` supports three selectable `filter_type` topologies for
lowpass and highpass filtering (`butterworth` and `bessel` for bandpass), plus
notch and harmonic comb line-noise filters:

| Filter / Topology | Design Formulation |
|-------------------|--------------------|
| **Butterworth** (`filter_type="butterworth"`, default) | Maximally flat passband magnitude IIR (`scipy.signal.butter(order, Wn, output="sos")`, order clamped to $[1, 10]$; Butterworth, 1930) |
| **Bessel** (`filter_type="bessel"`) | Phase-matched linear-phase IIR (`scipy.signal.bessel(order, Wn, norm="phase", output="sos")`; Thomson, 1949) preserving step and AP waveforms without ringing |
| **Gaussian** (`filter_type="gaussian"`, lowpass/highpass) | Symmetric time-domain Gaussian kernel (`scipy.ndimage.gaussian_filter1d`) with $-3\,\text{dB}$ width $\sigma_{\text{samples}} = \frac{f_s}{2\pi f_c}\sqrt{\ln 2}$; Gaussian highpass returns $x - \text{LP}_{\text{Gaussian}}(x)$ |
| **Notch** (`notch_filter`) | Narrowband IIR notch (`scipy.signal.iirnotch(f_0 / f_{\text{Nyq}}, Q)`) converted via `tf2zpk` -> `zpk2sos` |
| **Comb** (`comb_filter` / `multi_harmonic_notch`) | Harmonic notch comb (`scipy.signal.iircomb(f_0, Q, ftype="notch", fs=fs)` -> `tf2zpk` -> `zpk2sos`), with cascaded `notch_filter` fallback across $f_0, 2f_0, \ldots < f_{\text{Nyq}}$ (up to optional `max_harmonics`) |

**BLAS-safe zero-phase SOS filtering (`_sosfiltfilt_safe`):** All SOS IIR filters
execute forward-backward zero-phase filtering without calling
`scipy.signal.sosfilt_zi` / `numpy.linalg.solve` (preventing misaligned-buffer
BLAS `SIGBUS` faults on macOS ARM64). `_compute_sos_zi_safe` solves each
Direct-Form II Transposed biquad's steady-state state vector $\mathbf{z}_i$ in
closed form:

$$
y_{\text{ss}} = s \cdot \frac{b_0 + b_1 + b_2}{1 + a_1 + a_2},
\qquad
z_1 = b_2 s - a_2 y_{\text{ss}},
\qquad
z_0 = b_1 s - a_1 y_{\text{ss}} + z_1
$$

The signal is padded at both ends by odd reflection of length
$L_{\text{pad}} = \min\bigl(3(2 N_{\text{sections}} + 1),\; N - 1\bigr)$
($x_{\text{left}} = 2x_0 - x_{L_{\text{pad}}:0:-1}$,
$x_{\text{right}} = 2x_{N-1} - x_{N-2:N-L_{\text{pad}}-2:-1}$), filtered forward
and backward via `scipy.signal.sosfilt` seeded with $\mathbf{z}_{\text{ss}} x_{\text{pad}}[0]$,
and trimmed back to $N$ samples, eliminating boundary step transients on
non-zero resting potentials (e.g., $-70\,\text{mV}$).

**Registered batch/CLI preprocessors (`core/analysis/preprocessing.py`):** Seven
processors are registered via `@AnalysisRegistry.register_processor` so
`BatchAnalysisEngine` and `synaptipy-batch` execute identical preprocessing
pipelines: `baseline_subtraction`, `lowpass_filter`, `highpass_filter`,
`bandpass_filter`, `notch_filter`, `comb_filter`, and `detrend_filter`.

### 14.2 Baseline subtraction

| Method | Formula |
|--------|---------|
| `mode` | $V' = V - \operatorname{mode}(\operatorname{round}(V_{\mathcal{W}}, d))$ (full trace or optional window $\mathcal{W}$) |
| `mean` | $V' = V - \bar{V}$ (full trace or optional window $\mathcal{W}$) |
| `median` | $V' = V - \operatorname{median}(V_{\mathcal{W}})$ (full trace or optional window $\mathcal{W}$) |
| `linear` / `detrend` | $V' = V - (\beta_0 + \beta_1 t)$ via `scipy.signal.detrend(..., type="linear")` |
| `region` | $V' = V - \bar{V}_{\mathcal{W}}$ for user-specified $[t_{\text{start}}, t_{\text{end}}]$ |
| `constant` | $V' = V - c$ (`offset_value`, in `baseline_subtraction` batch processor) |

### 14.3 Artifact blanking (`blank_artifact`)

For stimulus artifact suppression over $[t_{\text{onset}}, t_{\text{onset}} + \text{duration\_ms}/1000)$,
three replacement modes are available:

| Method | Description |
|--------|-------------|
| `hold` | Replace artifact window with the last pre-artifact sample value $V[i_{\text{start}} - 1]$ |
| `zero` | Set all samples in the artifact window to `0.0` |
| `linear` | Linearly interpolate (`numpy.linspace`) between $V[i_{\text{start}} - 1]$ and $V[i_{\text{end}}]$ |

### 14.4 Trace quality assessment (`check_trace_quality`)

- **Baseline drift:** OLS regression slope over the full trace (`scipy.stats.linregress`), flagged when total drift exceeds `5.0 * std(data)`.
- **RMS noise:** Root-mean-square of the linearly detrended trace.
- **Line noise (50/60 Hz):** Welch PSD (`scipy.signal.welch`, Hann window, `nperseg = min(N, 4096)`; Welch, 1967) comparing mean power within $\pm 2\,\text{Hz}$ of 50 Hz and 60 Hz against flanking $[f_0 - 10, f_0 - 2) \cup (f_0 + 2, f_0 + 10]\,\text{Hz}$ reference bands (flagged when ratio $> 10$).
- **Low-frequency instability:** Forward 2nd-order `< 1 Hz` Butterworth SOS filter (`sosfilt`), flagged when low-frequency variance exceeds $2\times$ high-frequency variance.

---

## 15. Advanced Biophysics (Publication Audit)

### 15.1 Voltage-Clamp Series Resistance and Dual Membrane Capacitance

Classical area-under-the-curve (AUC) $C_m$ estimation can deviate under
uncompensated series resistance or slow leak currents. `calculate_capacitance_vc`
extracts both exponential-fit and charge-integral estimates from the baseline-
and steady-state-subtracted transient $\Delta I(t)$:

**Step 1 - Series Resistance (Ohm's law at the transient peak):**

$$
R_s \;[\text{M}\Omega] = \frac{|\Delta V \;[\text{mV}]|}{\max_t |\Delta I(t) \;[\text{pA}]|} \times 10^{3}
$$

**Step 2 - Transient decay fit (`capacitance_pf`):**

A mono-exponential $|\Delta I(t)| = A \exp(-t / \tau_{\text{trans}})$ is fitted
from the transient peak onward (`scipy.optimize.curve_fit`, `maxfev=2000`, using
the last 20% of the transient window for steady-state subtraction $I_{\text{ss}}$):

$$
C_m \;[\text{pF}] = \frac{\tau_{\text{trans}} \;[\text{s}]}{R_s \;[\text{M}\Omega] \times 10^{6}} \times 10^{12}
$$

If the exponential fit fails or fewer than 4 decay samples are available,
`capacitance_pf` falls back automatically to the trapezoidal charge integral.

**Step 3 - Unconditional charge-integral capacitance (`capacitance_charge_pf`):**

$$
C_{m,\text{charge}} \;[\text{pF}] =
\frac{\int_{t_0}^{t_1} |\Delta I(t)| \cdot 10^{-12}\,dt}{|\Delta V| \cdot 10^{-3}} \times 10^{12}
$$

Both `capacitance_pf` and `capacitance_charge_pf` are always returned alongside
`series_resistance_mohm` so analysts can cross-check single-compartment fit
assumptions against total capacitive charge transfer.

### 15.2 AP Threshold: Backward $dV/dt$ Crossing on Bessel-Filtered Voltage

*(Default threshold $\theta_{dV/dt} = 20\,\text{V/s}$, Bean, 2007; artifact ceiling
`300 V/s`, Naundorf et al., 2006.)*

Synaptipy filters the trace with a 4th-order 9.9 kHz zero-phase Bessel low-pass
filter (when $9.9\,\text{kHz} < f_{\text{Nyquist}}$), computes
$dV/dt = \nabla V_{\text{filt}} / \Delta t$, locates the upstroke velocity
maximum $k_{\max} = \arg\max (dV/dt)$ within `onset_lookback`, and scans
**backward** from $k_{\max}$ to the last sample strictly below $\theta_{dV/dt}$,
selecting the next sample ($\ge \theta_{dV/dt}$) as action potential onset:

$$
k_{\text{thresh}} = \min\!\Bigl(N_{\text{lookback}} - 1,\; 1 + \max\bigl\{ k \le k_{\max} : \tfrac{dV}{dt}[k] < \theta_{dV/dt} \bigr\}\Bigr)
$$

Scanning backward from $k_{\max}$ (rather than forward from the start of the
lookback window) prevents pre-spike noise or preceding repolarisation transients
from triggering premature threshold crossings. Second-derivative curvature
methods ($d^2V/dt^2$, Sekerli et al., 2004) are intentionally not used in
Synaptipy because double differentiation amplifies high-frequency discretisation
noise and shifts apparent threshold during $\text{Na}^+$ channel inactivation
(Henze & Buzsaki, 2001).

### 15.3 Separation of Fast AHP and Medium AHP

A single AHP measurement conflates fast ($\text{K}_V$, BK channels) and medium
($\text{K}_{\text{Ca}}$, SK channels) repolarisation dynamics. Two independent
window minima are evaluated on raw voltage:

| Metric | Window | Dominant channel |
|---|---|---|
| `fahp_depth` | 1-5 ms post-peak | $\text{Na}^+$ inactivation / $\text{K}_V3$ / BK channels |
| `mahp_depth` | 10-50 ms post-peak | SK / IK $\text{Ca}^{2+}$-activated $\text{K}^+$ channels |

$$
\text{fAHP depth} = V_{\text{threshold}} - \min_{t \in [t_{\text{peak}}+1\text{ ms},\; t_{\text{peak}}+5\text{ ms})} V(t)
$$

$$
\text{mAHP depth} = V_{\text{threshold}} - \min_{t \in [t_{\text{peak}}+10\text{ ms},\; t_{\text{peak}}+50\text{ ms})} V(t)
$$

Positive depth indicates hyperpolarisation below AP threshold.

### 15.4 Multi-Kernel Dendritic Tolerance in Template Matching

Cable theory predicts that synaptic currents arriving at distal dendrites appear
2-3x slower at the soma due to passive RC cable filtering (Rall, 1967;
Major et al., 1994). `detect_events_template` generates a bank of kernels (either
`"bi-exponential"` or `"mono-exponential"` via `kernel_shape`) by scaling
$\tau_{\text{decay}}$ across user-configurable `kernel_multipliers`
$\{m_1, \ldots, m_K\}$ (default `[1.0, 2.0, 3.0]`):

$$
\tilde{k}_s(t) = \exp\!\bigl(-t / (s \cdot \tau_{\text{decay}})\bigr) - \exp\!\bigl(-t / \tau_{\text{rise}}\bigr),
\qquad
k_s(t) = \frac{\tilde{k}_s(t)}{\max_t |\tilde{k}_s(t)|},
\quad s \in \{m_1, \ldots, m_K\}
$$

Each **unit-peak-normalised** kernel is cross-correlated (`fftconvolve` with
$k_s[::-1]$) against the baseline-corrected trace, z-scored independently via
`1.4826 * MAD`, peak-aligned to the primary ($m_1$) kernel offset, and combined
pointwise:

$$
z_{\text{combined}}(t) = \max_{s \in \{m_1, \ldots, m_K\}} z_{s,\text{aligned}}(t)
$$

Peak detection runs on $z_{\text{combined}}$ at `threshold_sd` (default `4.0`)
with minimum distance `min_event_distance_ms` (defaulting to $\tau_{\text{decay}}$
when `0.0`), capturing both fast somatic and slowed distal dendritic events in a
single pass.

### 15.5 N-Pulse PPR with Iterative Cumulative Decay Subtraction

*(Zucker & Regehr, 2002; Regehr, 2012; Thanawala & Regehr, 2013;
Wesseling & Lo, 2002.)*

`calculate_n_pulse_ratio` supports $N \ge 2$ stimulus pulses:

1. Measure $\text{bl}_1$ (mean resting baseline over `baseline_window_ms` before
   stimulus 1).
2. For pulse $i = 1, \ldots, N$:
   - Locate raw extremum $V_{i,\text{peak}}$ at timestamp $t_{\text{peak},i}$ in
     $[t_{\text{stim},i} + t_{\text{blank}},\; t_{\text{stim},i} + T_{\text{resp}}]$.
   - Evaluate the cumulative residual from all prior fitted decays **at
     $t_{\text{peak},i}$**:
     $$
     \rho_i(t_{\text{peak},i}) = \sum_{j=1}^{i-1} \bigl[f_j(t_{\text{peak},i}) - \text{bl}_1\bigr]
     $$
   - Compute the corrected amplitude:
     $$
     R_{i,\text{corrected}} =
     \begin{cases}
       (\text{bl}_1 - V_{i,\text{peak}}) + \rho_i(t_{\text{peak},i}) & \text{(negative polarity)} \\
       (V_{i,\text{peak}} - \text{bl}_1) - \rho_i(t_{\text{peak},i}) & \text{(positive polarity)}
     \end{cases}
     $$
   - Subtract $\rho_i(t)$ from the raw trace over the decay-fit window
     $[t_{\text{stim},i} + t_{\text{fit,from}},\; \min(t_{\text{stim},i+1},\, t_{\text{end}}))$
     and fit $f_i(t)$ (Section 15.6).
3. Normalise all corrected amplitudes to pulse 1:
   $$
   \text{ratio}_i = \frac{R_{i,\text{corrected}}}{R_{1,\text{corrected}}}
   $$

### 15.6 Decay Fitting - Bi-Exponential with Mono-Exponential Fallback

Each pulse's isolated decay tail ($\ge 8$ samples) is first fitted with a
5-parameter **bi-exponential** model (`curve_fit`, `maxfev=4000`):

$$
f(t) = A_f \exp(-t / \tau_f) + A_s \exp(-t / \tau_s) + c
$$

If convergence fails, covariance is non-finite, or fewer than 8 samples span the
window ($\ge 4$ samples), the implementation falls back to the mono-exponential
model $A \exp(-t/\tau) + c$ (`maxfev=3000`). For bi-exponential fits, the
reported dominant $\tau$ is the amplitude-weighted mean time constant:

$$
\tau_{\text{dominant}} = \frac{|A_f| \tau_f + |A_s| \tau_s}{|A_f| + |A_s|}
$$

### 15.7 Quiescent Baseline RMS Detrending (`find_quiescent_baseline_rms`)

`find_quiescent_baseline_rms` estimates the thermal/electronic background noise
floor for `detect_events_threshold` (`use_quiescent_noise_floor=True` default)
without requiring a manually selected event-free pre-window:

1. **20 ms 50%-overlapping sliding windows:** Advances a window of length
   $W = \max(2, \lfloor \texttt{window\_ms} \cdot 10^{-3} f_s \rfloor)$ samples
   (default `window_ms = 20.0 ms`, i.e., 200-1,000 samples at 10-50 kHz) in
   steps of $S = \max(1, \lfloor W / 2 \rfloor)$ across the **entire** trace:
   $\mathcal{W}_k = \{i : kS \le i < kS + W\}$.
2. **Per-window linear detrending:** Applies
   `scipy.signal.detrend(data[W_k], type="linear")` to each candidate window
   before evaluating variance, removing slow baseline drift (pipette drift,
   bath wash-in ramps) so low-frequency ramps do not inflate local variance.
3. **Global minimum-variance selection and RMS floor:** Selects the single
   quietest detrended window $k^* = \arg\min_k \operatorname{Var}(\tilde{x}_k)$
   across the recording and returns its root-mean-square, floored at
   `NOISE_FLOOR_MIN_RMS = 1e-6`:
   $$
   \hat{\sigma}_{\text{noise}} = \max\!\left(10^{-6},\; \sqrt{\frac{1}{W} \sum_{i \in \mathcal{W}_{k^*}} \tilde{x}_i^{\,2}}\right)
   $$

Because a 20 ms window fits cleanly inside inter-event intervals even during
moderate spontaneous miniature synaptic activity, selecting $\arg\min_k \operatorname{Var}(\tilde{x}_k)$
isolates quiescent baseline thermal noise without iterative peak-to-peak
rejection thresholds.

---

## 16. Immutable Trace Correction Pipeline

**Module:** `core/processing_pipeline.py` | **Function:** `apply_trace_corrections`

To prevent order-dependent preprocessing artifacts, `apply_trace_corrections()`
enforces a strict **five-step sequence (Steps A -> B -> C -> D -> E)**
unconditionally:

### Step A - Unit-Aware Liquid Junction Potential (LJP) Subtraction

Applied only to voltage channels (skipped with a warning if `units` indicates a
current channel such as `pA`, `nA`, or `A`), scaling `ljp_mv` to match the
channel's voltage unit:

$$
V_{\text{true}}(t) =
\begin{cases}
V_{\text{recorded}}(t) - \text{LJP}_{\text{mV}} & \text{if units in } \{\texttt{mV}\} \\
V_{\text{recorded}}(t) - 10^{-3}\,\text{LJP}_{\text{mV}} & \text{if units in } \{\texttt{V}\} \\
V_{\text{recorded}}(t) - 10^{3}\,\text{LJP}_{\text{mV}} & \text{if units in } \{\texttt{uV}\}
\end{cases}
$$

> **Biophysical limitations of post-hoc LJP subtraction:** Subtracting a scalar
> LJP corrects reported passive membrane potentials (RMP, $R_{\text{in}}$,
> $\tau$), but does **not** retroactively alter the transmembrane voltage that
> voltage-gated channels ($\text{Na}^+$, $\text{K}^+$, $\text{Ca}^{2+}$)
> experienced during acquisition. Large uncorrected LJPs ($> 10\,\text{mV}$) or
> conductance calculations $I = g(V - E_{\text{rev}})$ must account for LJP in
> experimental interpretation (Barry & Lynch, 1991; Neher, 1992).

### Step B - P/N Leak Subtraction

*(Armstrong & Bezanilla, 1977; Bezanilla & Armstrong, 1977.)*

$$
I_{\text{corrected}}(t) = I_{\text{signal}}(t)
 - p \cdot \frac{1}{K} \sum_{k=1}^{K} I_{\text{leak},k}(t)
$$

where $K$ is the number of sub-threshold P/N sweeps (`pn_traces`) and $p$ is
`pn_scale` (default `1.0`).

### Step C - Pre-Event Scalar Noise-Floor Zeroing

$$
V'(t) = V_{\text{corrected}}(t) - \operatorname{median}_{t \in \mathcal{W}_{\text{pre}}} V_{\text{corrected}}(t)
$$

Subtracts the scalar median over `pre_event_window_s = (t_start, t_end)` after
Steps A and B.

### Step D - Pre-Filter Artifact Interpolation

For each stimulus artifact descriptor `{"onset_time": t0, "duration_ms": d}` in
`artifact_interp_steps`, `signal_processor.blank_artifact(..., method="linear")`
linearly interpolates across $[t_0, t_0 + d/1000)$. Executing linear artifact
interpolation **after** baseline zeroing (Step C) and **before** digital
filtering (Step E) removes sharp stimulus discontinuities prior to convolution,
preventing Gibbs ringing in IIR filters.

### Step E - Signal Filtering

Applies any filter steps in `filter_steps` via `SignalProcessingPipeline`.
Running DSP filters last prevents step transients from leak subtraction or
stimulus artifacts from smearing into biological waveforms.

---

## 17. 5-Pillar Analyser Architecture

The Synaptipy Analyser UI is structured around **five primary tabs**, each
corresponding to a module-level aggregator entry in `AnalysisRegistry`:

| Pillar | Registry name | Label | Sub-analyses (16 total) |
|--------|--------------|-------|-------------------------|
| 1 | `passive_properties` | Intrinsic Properties | Baseline (RMP), Input Resistance, Tau (Time Constant), Sag Ratio (Ih), I-V Curve, Capacitance |
| 2 | `single_spike` | Spike Analysis | Spike Detection, Phase Plane |
| 3 | `firing_dynamics` | Excitability | Excitability, Burst Analysis, Spike Train Dynamics |
| 4 | `synaptic_events` | Synaptic Events | Event (Amplitude), Event (Template) |
| 5 | `evoked_responses` | Evoked Responses | Evoked Sync, Paired-Pulse Ratio, Stimulus Train (STP) |

Leaf registrations (e.g. `spike_detection`, `phase_plane_analysis`) are covered
by their parent module tab via `MetadataDrivenAnalysisTab.get_covered_analysis_names()`
and do not appear as independent top-level tabs. Custom user plugins are
appended after the five core pillars in alphabetical order.

---

## References

### Spike detection and AP threshold

- **Bean, B. P. (2007).** The action potential in mammalian central neurons.
  *Nature Reviews Neuroscience*, 8(6), 451-465.
  [doi:10.1038/nrn2148](https://doi.org/10.1038/nrn2148)
  - **Used in:** Default $dV/dt$ threshold (`20.0 V/s`) for spike detection and
    onset determination (Section 6.1, Section 6.2, Section 15.2).

- **Hodgkin, A. L., & Huxley, A. F. (1952).** A quantitative description of
  membrane current and its application to conduction and excitation in nerve.
  *Journal of Physiology*, 117(4), 500-544.
  [doi:10.1113/jphysiol.1952.sp004764](https://doi.org/10.1113/jphysiol.1952.sp004764)
  - **Used in:** Foundational biophysical basis for AP threshold detection,
    $dV/dt$ kinetics, and $\text{Na}^+$/$\text{K}^+$ conductance dynamics
    (Section 6, Section 15.2).

- **Naundorf, B., Wolf, F., & Volgushev, M. (2006).** Unique features of action
  potential initiation in cortical neurons. *Nature*, 440(7087), 1060-1063.
  [doi:10.1038/nature04610](https://doi.org/10.1038/nature04610)
  - **Used in:** Artifact ceiling (`DVDT_ARTIFACT_CEILING_VS = 300.0 V/s`,
    Section 6.2).

- **Sekerli, M., Del Negro, C. A., Lee, R. H., & Butera, R. J. (2004).**
  Estimating action potential thresholds from neuronal time-series: new metrics
  and evaluation of methodologies. *IEEE Transactions on Biomedical Engineering*,
  51(9), 1665-1672.
  [doi:10.1109/TBME.2004.827827](https://doi.org/10.1109/TBME.2004.827827)
  - **Referenced in:** Section 15.2 - methodological contrast for the
    $d^2V/dt^2$ maximum-curvature method that Synaptipy intentionally avoids in
    favour of backward $dV/dt$ crossing.

- **Henze, D. A., & Buzsaki, G. (2001).** Action potential threshold of
  hippocampal pyramidal cells in vivo is increased by recent spiking activity.
  *Neuroscience*, 105(1), 121-130.
  [doi:10.1016/S0306-4522(01)00167-1](https://doi.org/10.1016/S0306-4522(01)00167-1)
  - **Used in:** Motivation for per-spike dynamic threshold determination
    (Section 15.2).

### AHP, passive properties, and electrode corrections

- **Storm, J. F. (1987).** Action potential repolarization and a fast
  after-hyperpolarization in rat hippocampal pyramidal cells. *Journal of
  Physiology*, 385, 733-759.
  [doi:10.1113/jphysiol.1987.sp016517](https://doi.org/10.1113/jphysiol.1987.sp016517)
  - **Used in:** Fast AHP window (`1-5 ms`), BK/Kv3 channel kinetics
    (Section 6.7, Section 15.3).

- **Sah, P., & Faber, E. S. L. (2002).** Channels underlying neuronal
  calcium-activated potassium currents. *Progress in Neurobiology*, 66(5),
  345-353.
  [doi:10.1016/S0301-0082(02)00004-7](https://doi.org/10.1016/S0301-0082(02)00004-7)
  - **Used in:** Medium AHP window (`10-50 ms`), SK channel kinetics
    (Section 6.7, Section 15.3).

- **Hamill, O. P., Marty, A., Neher, E., Sakmann, B., & Sigworth, F. J. (1981).**
  Improved patch-clamp techniques for high-resolution current recording from
  cells and cell-free membrane patches. *Pflugers Archiv*, 391(2), 85-100.
  [doi:10.1007/BF00656997](https://doi.org/10.1007/BF00656997)
  - **Used in:** Series-resistance measurement and whole-cell capacitance
    estimation (Section 5.2, Section 15.1).

- **Neher, E., & Sakmann, B. (1976).** Single-channel currents recorded from
  membrane of denervated frog muscle fibres. *Nature*, 260(5554), 799-802.
  [doi:10.1038/260799a0](https://doi.org/10.1038/260799a0)
  - **Used in:** Foundation for whole-cell patch-clamp passive-property analysis.

- **Robinson, R. B., & Siegelbaum, S. A. (2003).** Hyperpolarization-activated
  cation currents: From molecules to physiological function. *Annual Review of
  Physiology*, 65, 453-480.
  [doi:10.1146/annurev.physiol.65.092101.142734](https://doi.org/10.1146/annurev.physiol.65.092101.142734)
  - **Used in:** Peak vs. steady-state $R_{\text{in}}$ separation (Section 2.2)
    and HCN/$I_h$ sag ratio analysis (Section 4).

- **Barry, P. H., & Lynch, J. W. (1991).** Liquid junction potentials and small
  cell effects in patch-clamp analysis. *Journal of Membrane Biology*, 121(2),
  101-117.
  [doi:10.1007/BF01870526](https://doi.org/10.1007/BF01870526)
  - **Used in:** Section 16 Step A - unit-aware liquid junction potential
    subtraction and biophysical interpretation.

- **Neher, E. (1992).** Correction for liquid junction potentials in patch clamp
  experiments. *Methods in Enzymology*, 207, 123-131.
  [doi:10.1016/0076-6879(92)07008-C](https://doi.org/10.1016/0076-6879(92)07008-C)
  - **Used in:** Section 16 Step A - standard reference for whole-cell LJP
    offset correction.

- **Armstrong, C. M., & Bezanilla, F. (1977).** Inactivation of the sodium
  channel. II. Gating current experiments. *Journal of General Physiology*,
  70(5), 567-590.
  [doi:10.1085/jgp.70.5.567](https://doi.org/10.1085/jgp.70.5.567)
  - **Used in:** Section 16 Step B - P/N leak subtraction protocol.

- **Bezanilla, F., & Armstrong, C. M. (1977).** Inactivation of the sodium
  channel. I. Sodium current experiments. *Journal of General Physiology*,
  70(5), 549-566.
  [doi:10.1085/jgp.70.5.549](https://doi.org/10.1085/jgp.70.5.549)
  - **Used in:** Section 16 Step B - companion P/N leak subtraction study.

### Signal processing and noise estimation

- **Savitzky, A., & Golay, M. J. E. (1964).** Smoothing and differentiation of
  data by simplified least squares procedures. *Analytical Chemistry*, 36(8),
  1627-1639.
  [doi:10.1021/ac60214a047](https://doi.org/10.1021/ac60214a047)
  - **Used in:** Sag/rebound smoothing (Section 4), AHP fallback smoothing
    (Section 6.7), and phase-plane $dV/dt$ smoothing (Section 11).

- **Butterworth, S. (1930).** On the Theory of Filter Amplifiers.
  *Wireless Engineer*, 7, 536-541.
  - **Used in:** Default Butterworth SOS filters in `signal_processor.py`
    (Section 14.1) and the 5 kHz spike detection pre-filter (Section 6.1).

- **Thomson, W. E. (1949).** Delay networks having maximally flat frequency
  characteristics. *Proceedings of the IEE - Part III*, 96(44), 487-490.
  [doi:10.1049/pi-3.1949.0101](https://doi.org/10.1049/pi-3.1949.0101)
  - **Used in:** Phase-matched Bessel IIR filters (Section 14.1) and the 9.9 kHz
    AP onset derivative pre-filter (Section 6.2).

- **Welch, P. D. (1967).** The use of fast Fourier transform for the estimation
  of power spectra: A method based on time averaging over short, modified
  periodograms. *IEEE Transactions on Audio and Electroacoustics*, 15(2), 70-73.
  [doi:10.1109/TAU.1967.1161901](https://doi.org/10.1109/TAU.1967.1161901)
  - **Used in:** Section 14.4 trace quality line-noise assessment and
    `compute_psd()`.

- **Hampel, F. R. (1974).** The influence curve and its role in robust
  estimation. *Journal of the American Statistical Association*, 69(346),
  383-393.
  [doi:10.1080/01621459.1974.10482962](https://doi.org/10.1080/01621459.1974.10482962)
  - **Used in:** Gaussian-consistent MAD scale estimator ($1.4826 \times \text{MAD}$)
    for matched-filter z-scoring (Section 7.2) and optional threshold event
    detection when `use_quiescent_noise_floor=False` (Section 7.1).

- **Rousseeuw, P. J., & Croux, C. (1993).** Alternatives to the median absolute
  deviation. *Journal of the American Statistical Association*, 88(424),
  1273-1283.
  [doi:10.1080/01621459.1993.10476408](https://doi.org/10.1080/01621459.1993.10476408)
  - **Used in:** Breakdown-point justification for MAD scale estimation in
    event-contaminated traces (Section 7.1, Section 7.2).

### Synaptic plasticity, bursts, and spike-train statistics

- **Rall, W. (1967).** Distinguishing theoretical synaptic potentials computed
  for different soma-dendritic distributions of synaptic input. *Journal of
  Neurophysiology*, 30(5), 1138-1168.
  [doi:10.1152/jn.1967.30.5.1138](https://doi.org/10.1152/jn.1967.30.5.1138)
  - **Used in:** Multi-scale template bank (default 1x, 2x, 3x decay slowing,
    Section 7.2, Section 15.4).

- **Major, G., Larkman, A. U., Jonas, P., Sakmann, B., & Jack, J. J. B.
  (1994).** Detailed passive cable models of whole-cell recorded CA3 pyramidal
  neurons in rat hippocampal slices. *Journal of Neuroscience*, 14(8),
  4613-4638.
  [doi:10.1523/JNEUROSCI.14-08-04613.1994](https://doi.org/10.1523/JNEUROSCI.14-08-04613.1994)
  - **Used in:** Quantitative validation of dendritic cable filtering in
    template matching (Section 15.4).

- **Zucker, R. S., & Regehr, W. G. (2002).** Short-term synaptic plasticity.
  *Annual Review of Physiology*, 64, 355-405.
  [doi:10.1146/annurev.physiol.64.092501.114547](https://doi.org/10.1146/annurev.physiol.64.092501.114547)
  - **Used in:** Pre-stimulus baseline referencing and decay-tail subtraction in
    PPR (Section 13.2, Section 15.5).

- **Regehr, W. G. (2012).** Short-term presynaptic plasticity. *Cold Spring
  Harbor Perspectives in Biology*, 4(7), a005702.
  [doi:10.1101/cshperspect.a005702](https://doi.org/10.1101/cshperspect.a005702)
  - **Used in:** Facilitation, depression, and biphasic STP classification
    (Section 13.3, Section 15.5).

- **Thanawala, M. S., & Regehr, W. G. (2013).** Presynaptic calcium influx
  controls neurotransmitter release in part by regulating the effective size of
  the readily releasable pool. *Journal of Neuroscience*, 33(11), 4625-4633.
  [doi:10.1523/JNEUROSCI.4031-12.2013](https://doi.org/10.1523/JNEUROSCI.4031-12.2013)
  - **Used in:** Iterative cumulative decay subtraction across $N$-pulse trains
    (Section 15.5).

- **Wesseling, J. F., & Lo, D. C. (2002).** Limit on the role of activity in
  controlling the release-ready supply of synaptic vesicles. *Journal of
  Neuroscience*, 22(22), 9708-9720.
  [doi:10.1523/JNEUROSCI.22-22-09708.2002](https://doi.org/10.1523/JNEUROSCI.22-22-09708.2002)
  - **Used in:** Cumulative amplitude analysis with residual decay correction
    (Section 15.5).

- **Grace, A. A., & Bunney, B. S. (1984).** The control of firing pattern in
  nigral dopamine neurons: burst firing. *Journal of Neuroscience*, 4(11),
  2877-2890.
  [doi:10.1523/JNEUROSCI.04-11-02877.1984](https://doi.org/10.1523/JNEUROSCI.04-11-02877.1984)
  - **Used in:** ISI-criterion burst detection (Section 9).

- **Harris, K. D., Hirase, H., Leinekugel, X., Henze, D. A., & Buzsaki, G.
  (2001).** Temporal interaction between single spikes and complex spike bursts
  in hippocampal pyramidal cells. *Neuron*, 32(1), 141-149.
  [doi:10.1016/S0896-6273(01)00447-0](https://doi.org/10.1016/S0896-6273(01)00447-0)
  - **Used in:** Dynamic ISI fraction (`0.3` of mean ISI) for burst detection
    (Section 9).

- **Holt, G. R., Softky, W. R., Koch, C., & Douglas, R. J. (1996).** Comparison
  of discharge variability in vitro and in vivo in cat visual cortex neurons.
  *Journal of Neurophysiology*, 75(5), 1806-1814.
  [doi:10.1152/jn.1996.75.5.1806](https://doi.org/10.1152/jn.1996.75.5.1806)
  - **Used in:** CV and $\text{CV}_2$ computation (Section 12).

- **Shinomoto, S., Shima, K., & Tanji, J. (2003).** Differences in spiking
  patterns among cortical neurons. *Neural Computation*, 15(12), 2823-2842.
  [doi:10.1162/089976603322518759](https://doi.org/10.1162/089976603322518759)
  - **Used in:** Local Variation (LV) metric (Section 12).

### Data standards, ecosystem, and visualization

- **Rubel, O., Tritt, A., Ly, R., et al. (2022).** The Neurodata Without Borders
  ecosystem for neurophysiological data science. *eLife*, 11:e78362.
  [doi:10.7554/eLife.78362](https://doi.org/10.7554/eLife.78362)
  - **Used in:** NWB 2.x export and FAIR provenance compliance.

- **Garcia, S., Guarino, D., Jaillet, F., et al. (2014).** Neo: an object model
  for handling electrophysiology data in multiple formats. *Frontiers in
  Neuroinformatics*, 8, 10.
  [doi:10.3389/fninf.2014.00010](https://doi.org/10.3389/fninf.2014.00010)
  - **Used in:** Multi-format electrophysiology file I/O layer.

- **Virtanen, P., Gommers, R., Oliphant, T. E., et al. (2020).** SciPy 1.0:
  Fundamental algorithms for scientific computing in Python. *Nature Methods*,
  17, 261-272.
  [doi:10.1038/s41592-019-0686-2](https://doi.org/10.1038/s41592-019-0686-2)
  - **Used in:** Non-linear curve fitting, digital filters, Savitzky-Golay and
    Gaussian smoothing, Welch PSD, peak detection, linear regression, and MAD.

- **Harris, C. R., Millman, K. J., van der Walt, S. J., et al. (2020).** Array
  programming with NumPy. *Nature*, 585, 357-362.
  [doi:10.1038/s41586-020-2649-2](https://doi.org/10.1038/s41586-020-2649-2)
  - **Used in:** Vectorised array computation across all analysis modules.

- **McKinney, W. (2010).** Data structures for statistical computing in Python.
  *Proceedings of the 9th Python in Science Conference* (SciPy 2010), 51-56.
  [doi:10.25080/Majora-92bf1922-00a](https://doi.org/10.25080/Majora-92bf1922-00a)
  - **Used in:** `pandas.DataFrame` batch engine tabulation and CSV export.

- **Wong, B. (2011).** Points of view: Color blindness. *Nature Methods*, 8(6),
  441.
  [doi:10.1038/nmeth.1618](https://doi.org/10.1038/nmeth.1618)
  - **Used in:** Colorblind-safe plot palette.
