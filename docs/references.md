# Scientific References

This page collects all scientific publications, methods, and software libraries
that Synaptipy implements or builds upon. References are grouped by topic. Each
entry identifies the specific module or section where it is used.

For full mathematical derivations see [Algorithmic Definitions](algorithmic_definitions.md).

---

## Action Potential Detection and Kinetics

**Bean, B. P. (2007).** The action potential in mammalian central neurons.
*Nature Reviews Neuroscience*, 8(6), 451-465.
[doi:10.1038/nrn2148](https://doi.org/10.1038/nrn2148)
> Default $dV/dt$ threshold (20 V/s) for spike onset detection in
> `single_spike.py`; reference for cortical pyramidal neuron AP kinetics.

**Hodgkin, A. L., & Huxley, A. F. (1952).** A quantitative description of
membrane current and its application to conduction and excitation in nerve.
*Journal of Physiology*, 117(4), 500-544.
[doi:10.1113/jphysiol.1952.sp004764](https://doi.org/10.1113/jphysiol.1952.sp004764)
> Foundational AP model. Basis for $dV/dt$-threshold detection, $\text{Na}^+$ channel
> inactivation, and the separation of fast/medium AHP windows
> (`single_spike.py`, `firing_dynamics.py`).

**Naundorf, B., Wolf, F., & Volgushev, M. (2006).** Unique features of action
potential initiation in cortical neurons. *Nature*, 440(7087), 1060-1063.
[doi:10.1038/nature04610](https://doi.org/10.1038/nature04610)
> Artifact ceiling constant 300 V/s in `single_spike.py` - above this rate at
> the lookback boundary the rising phase is flagged as non-physiological.

**Sekerli, M., Del Negro, C. A., Lee, R. H., & Butera, R. J. (2004).**
Estimating action potential thresholds from neuronal time-series: new metrics
and evaluation of methodologies. *IEEE Transactions on Biomedical Engineering*,
51(9), 1665-1672.
[doi:10.1109/TBME.2004.827827](https://doi.org/10.1109/TBME.2004.827827)
> Cited for methodological context and contrast in Section 6.2 and Section 15.2.
> `single_spike.py` intentionally uses strict backward $dV/dt$ threshold
> crossing on a Bessel-filtered trace rather than $d^2V/dt^2$ maximum curvature
> to avoid sampling-rate-dependent second-derivative noise artifacts.

**Henze, D. A., & Buzsaki, G. (2001).** Action potential threshold of
hippocampal pyramidal cells in vivo is increased by recent spiking activity.
*Neuroscience*, 105(1), 121-130.
[doi:10.1016/S0306-4522(01)00167-1](https://doi.org/10.1016/S0306-4522(01)00167-1)
> Motivation for per-spike dynamic threshold determination to accommodate
> $\text{Na}^+$ channel inactivation across a spike train (`single_spike.py`,
> Section 15.2).

**Jenerick, H. (1963).** Phase plane trajectories of the muscle spike potential.
*Biophysical Journal*, 3(5), 363-377.
[doi:10.1016/S0006-3495(63)86827-7](https://doi.org/10.1016/S0006-3495(63)86827-7)
> Foundational $(V, dV/dt)$ phase-plane trajectory and closed-loop area
> analysis (`single_spike.py`, Section 6.9 and Section 11).

**Azouz, R., Jensen, M. S., & Yaari, Y. (1996).** Ionic basis of spike
after-depolarization and burst generation in adult rat hippocampal CA1 pyramidal
cells. *Journal of Physiology*, 492(1), 211-223.
[doi:10.1113/jphysiol.1996.sp021302](https://doi.org/10.1113/jphysiol.1996.sp021302)
> Biophysical characterisation of spike afterdepolarisation (`adp_amplitude`
> prominence-gated detection in `single_spike.py`, Section 6.8).

**Gouwens, N. W., Sorensen, S. A., Berg, J., et al. (2019).** Classification of
electrophysiological and morphological neuron types in the mouse visual cortex.
*Nature Neuroscience*, 22(7), 1182-1195.
[doi:10.1038/s41593-019-0417-0](https://doi.org/10.1038/s41593-019-0417-0)
> Standardised intracellular feature definitions (9.9 kHz 4-pole Bessel
> derivative pre-filter, $dV/dt$ threshold crossing, upstroke/downstroke ratio,
> and adaptation index) benchmarked in `single_spike.py` and `firing_dynamics.py`.

---

## After-Hyperpolarisation (AHP)

**Storm, J. F. (1987).** Action potential repolarization and a fast
after-hyperpolarization in rat hippocampal pyramidal cells.
*Journal of Physiology*, 385, 733-759.
[doi:10.1113/jphysiol.1987.sp016517](https://doi.org/10.1113/jphysiol.1987.sp016517)
> Fast AHP window (1-5 ms) calibration - BK/Kv3 channel kinetics
> (`single_spike.py`).

**Sah, P., & Faber, E. S. L. (2002).** Channels underlying neuronal
calcium-activated potassium currents. *Progress in Neurobiology*, 66(5),
345-353.
[doi:10.1016/S0301-0082(02)00004-7](https://doi.org/10.1016/S0301-0082(02)00004-7)
> Medium AHP window (10-50 ms) calibration - SK/IK $\text{Ca}^{2+}$-activated
> $\text{K}^+$ channels (`single_spike.py`).

---

## Passive Membrane Properties

**Hamill, O. P., Marty, A., Neher, E., Sakmann, B., & Sigworth, F. J. (1981).**
Improved patch-clamp techniques for high-resolution current recording from cells
and cell-free membrane patches. *Pflugers Archiv*, 391(2), 85-100.
[doi:10.1007/BF00656997](https://doi.org/10.1007/BF00656997)
> Series-resistance measurement and whole-cell capacitance estimation
> (`passive_properties.py`, Section 5.2 and Section 15.1). Seminal paper
> describing the whole-cell configuration of the patch-clamp technique.

**Neher, E., & Sakmann, B. (1976).** Single-channel currents recorded from
membrane of denervated frog muscle fibres. *Nature*, 260(5554), 799-802.
[doi:10.1038/260799a0](https://doi.org/10.1038/260799a0)
> Foundation for the patch-clamp method; provides the biophysical basis for
> passive-property analysis in `passive_properties.py`.

**Robinson, R. B., & Siegelbaum, S. A. (2003).** Hyperpolarization-activated
cation currents: From molecules to physiological function.
*Annual Review of Physiology*, 65, 453-480.
[doi:10.1146/annurev.physiol.65.092101.142734](https://doi.org/10.1146/annurev.physiol.65.092101.142734)
> HCN channel physiology - basis for peak vs. steady-state $R_{\text{in}}$
> distinction (Section 2.2) and sag ratio interpretation (Section 4,
> `passive_properties.py`).

**Rall, W. (1969).** Time constants and electrotonic length of membrane
cylinders and neurons. *Biophysical Journal*, 9(12), 1483-1508.
[doi:10.1016/S0006-3495(69)86467-2](https://doi.org/10.1016/S0006-3495(69)86467-2)
> Multi-exponential cable charging theory underlying mono- and bi-exponential
> membrane time-constant ($\tau_m$, $\tau_{\text{fast}}$, $\tau_{\text{slow}}$)
> fitting in `passive_properties.py` (Section 3).

**Spruston, N., & Johnston, D. (1992).** Perforated patch-clamp analysis of the
passive membrane properties of three classes of hippocampal neurons.
*Journal of Neurophysiology*, 67(3), 508-529.
[doi:10.1152/jn.1992.67.3.508](https://doi.org/10.1152/jn.1992.67.3.508)
> Subthreshold current-step estimation of passive $\tau_m$ and $R_{\text{in}}$
> while avoiding $I_h$ sag contamination (`passive_properties.py`, Section 3).

**Lindau, M., & Neher, E. (1988).** Patch-clamp techniques for time-resolved
capacitance measurements in single cells. *Pflugers Archiv*, 411(2), 137-146.
[doi:10.1007/BF00582306](https://doi.org/10.1007/BF00582306)
> Equivalent whole-cell $R_s$-$C_m$-$R_m$ circuit analysis for voltage-clamp
> capacitive transient measurements (`passive_properties.py`, Section 5.2).

**Marty, A., & Neher, E. (1995).** Tight-seal whole-cell recording. In B. Sakmann
& E. Neher (Eds.), *Single-Channel Recording* (2nd ed., pp. 31-52). Springer.
[doi:10.1007/978-1-4419-1229-9_2](https://doi.org/10.1007/978-1-4419-1229-9_2)
> Series-resistance estimation via initial capacitive current back-extrapolation
> to step onset and signed capacitive charge integration (`passive_properties.py`,
> Section 5.2 and Section 15.1).

**Golowasch, J., Thomas, G., Taylor, A. L., Patel, A., Pineda, A., Khalil, C.,
& Nadim, F. (2009).** Membrane capacitance measurements revisited: dependence of
capacitance value on measurement method in nonisopotential neurons.
*Journal of Neurophysiology*, 102(4), 2161-2175.
[doi:10.1152/jn.00160.2009](https://doi.org/10.1152/jn.00160.2009)
> Comparison of current-clamp ($\tau_m / R_{\text{in}}$) and voltage-clamp step
> capacitance estimators in branched neurons (`passive_properties.py`, Section 5).

**Taylor, A. L. (2012).** What we talk about when we talk about capacitance
measured with the voltage-clamp step method. *Journal of Computational
Neuroscience*, 32(1), 167-175.
[doi:10.1007/s10827-011-0346-8](https://doi.org/10.1007/s10827-011-0346-8)
> Theoretical analysis of exponential-fit vs. signed charge-integral ($Q / \Delta V$)
> whole-cell capacitance estimators reported side by side by
> `calculate_capacitance_vc` (`passive_properties.py`, Section 5.2 and Section 15.1).

---

## Electrode Corrections

**Barry, P. H., & Lynch, J. W. (1991).** Liquid junction potentials and small
cell effects in patch-clamp analysis. *Journal of Membrane Biology*, 121(2),
101-117.
[doi:10.1007/BF01870526](https://doi.org/10.1007/BF01870526)
> Liquid Junction Potential correction procedure - Section 16 Step A,
> `processing_pipeline.py`.

**Neher, E. (1992).** Correction for liquid junction potentials in patch clamp
experiments. *Methods in Enzymology*, 207, 123-131.
[doi:10.1016/0076-6879(92)07008-C](https://doi.org/10.1016/0076-6879(92)07008-C)
> Accepted standard reference for LJP correction in whole-cell patch-clamp
> (`processing_pipeline.py`).

**Armstrong, C. M., & Bezanilla, F. (1977).** Inactivation of the sodium
channel. II. Gating current experiments. *Journal of General Physiology*,
70(5), 567-590.
[doi:10.1085/jgp.70.5.567](https://doi.org/10.1085/jgp.70.5.567)
> Original P/N subtraction protocol - Section 16 Step B,
> `processing_pipeline.py`.

**Bezanilla, F., & Armstrong, C. M. (1977).** Inactivation of the sodium
channel. I. Sodium current experiments. *Journal of General Physiology*,
70(5), 549-566.
[doi:10.1085/jgp.70.5.549](https://doi.org/10.1085/jgp.70.5.549)
> Companion paper establishing P/N leak subtraction (`processing_pipeline.py`).

---

## Signal Processing

**Savitzky, A., & Golay, M. J. E. (1964).** Smoothing and differentiation of
data by simplified least squares procedures. *Analytical Chemistry*, 36(8),
1627-1639.
[doi:10.1021/ac60214a047](https://doi.org/10.1021/ac60214a047)
> Savitzky-Golay polynomial filter used for sag/rebound peak smoothing
> (`passive_properties.py`, Section 4.2), AHP waveform smoothing (Section 6.7),
> and phase-plane $dV/dt$ smoothing (`calculate_dvdt` in `single_spike.py`,
> Section 11).

**Butterworth, S. (1930).** On the Theory of Filter Amplifiers.
*Wireless Engineer*, 7, 536-541. (Original publication; no formal DOI.)
> Maximally flat Butterworth IIR filter design (`scipy.signal.butter`) - default
> topology for lowpass, highpass, and bandpass filters in Section 14.1
> (`signal_processor.py`, `core/analysis/preprocessing.py`) and the 5 kHz spike
> detection pre-filter (`single_spike.py`, Section 6.1). `signal_processor.py`
> also provides $-3\,\text{dB}$ magnitude-normalised Bessel
> (`scipy.signal.bessel(..., norm="mag")`), $-3\,\text{dB}$ Gaussian
> (`scipy.ndimage.gaussian_filter1d`), notch (`scipy.signal.iirnotch`), and
> DC-preserving sparse harmonic comb (`scipy.signal.iircomb`) filters.

**Thomson, W. E. (1949).** Delay networks having maximally flat frequency
characteristics. *Proceedings of the IEE - Part III: Radio and Communication
Engineering*, 96(44), 487-490.
[doi:10.1049/pi-3.1949.0101](https://doi.org/10.1049/pi-3.1949.0101)
> Bessel-Thomson linear-phase filter design (`scipy.signal.bessel`), used for
> zero-overshoot transient filtering in `signal_processor.py` (Section 14.1) and
> the 4th-order 9.9 kHz derivative pre-filter in `calculate_spike_features`
> (`single_spike.py`, Section 6.2).

**Colquhoun, D., & Sigworth, F. J. (1995).** Fitting and statistical analysis of
single-channel records. In B. Sakmann & E. Neher (Eds.), *Single-Channel
Recording* (2nd ed., Ch. 19, pp. 483-587). Springer.
[doi:10.1007/978-1-4419-1229-9_19](https://doi.org/10.1007/978-1-4419-1229-9_19)
> Patch-clamp $-3\,\text{dB}$ Gaussian digital filter $\sigma$ derivation and
> $-3\,\text{dB}$ Bessel filter cutoff convention (`signal_processor.py`,
> Section 14.1).

**Gustafsson, F. (1996).** Determining the initial states in forward-backward
filtering. *IEEE Transactions on Signal Processing*, 44(4), 988-992.
[doi:10.1109/78.492552](https://doi.org/10.1109/78.492552)
> Steady-state initial-condition formulation for zero-phase forward-backward IIR
> filtering (`_compute_sos_zi_safe` and `_sosfiltfilt_safe` in
> `signal_processor.py`, Section 14.1).

**Widmann, A., Schroger, E., & Maess, B. (2015).** Digital filter design for
electrophysiological data: a practical approach. *Journal of Neuroscience
Methods*, 250, 34-46.
[doi:10.1016/j.jneumeth.2014.08.002](https://doi.org/10.1016/j.jneumeth.2014.08.002)
> Zero-phase filtering best practices, cutoff definitions, and step/impulse
> artifact prevention in electrophysiological recordings (`signal_processor.py`
> and `processing_pipeline.py`, Section 14.1 and Section 16).

**Welch, P. D. (1967).** The use of fast Fourier transform for the estimation
of power spectra: A method based on time averaging over short, modified
periodograms. *IEEE Transactions on Audio and Electroacoustics*, 15(2), 70-73.
[doi:10.1109/TAU.1967.1161901](https://doi.org/10.1109/TAU.1967.1161901)
> Welch's modified periodogram method for PSD estimation - Section 14.4 line
> noise detection and `compute_psd()` in `signal_processor.py` via
> `scipy.signal.welch`.

---

## Robust Noise Estimation

**Hampel, F. R. (1974).** The influence curve and its role in robust
estimation. *Journal of the American Statistical Association*, 69(346), 383-393.
[doi:10.1080/01621459.1974.10482962](https://doi.org/10.1080/01621459.1974.10482962)
> Median Absolute Deviation (MAD) with 1.4826 consistency factor for
> Gaussian-equivalent standard deviation across Synaptipy's two synaptic event
> detection methods (`synaptic_events.py`): `detect_events_template` uses MAD to
> z-score each matched-filter output trace (Section 7.2), while
> `detect_events_threshold` defaults to `find_quiescent_baseline_rms` (20 ms
> detrended minimum-variance window, Section 7.2.1) with MAD available when
> `use_quiescent_noise_floor=False` (Section 7.1).

**Rousseeuw, P. J., & Croux, C. (1993).** Alternatives to the median absolute
deviation. *Journal of the American Statistical Association*, 88(424),
1273-1283.
[doi:10.1080/01621459.1993.10476408](https://doi.org/10.1080/01621459.1993.10476408)
> 50% breakdown point properties of the MAD scale estimator; justification for
> z-scoring matched-filter outputs in event-dense electrophysiology traces
> (`synaptic_events.py`).

---

## Synaptic Event Detection

**Clements, J. D., & Bekkers, J. M. (1997).** Detection of spontaneous synaptic
events with an optimally scaled template. *Biophysical Journal*, 73(1), 220-229.
[doi:10.1016/S0006-3495(97)78062-7](https://doi.org/10.1016/S0006-3495(97)78062-7)
> Canonical zero-mean sliding template-matching detection of spontaneous miniature
> EPSCs/IPSCs (`detect_events_template` in `synaptic_events.py`, Section 7.2).

**Pernia-Andrade, A. J., Goswami, S. P., Stickler, Y., Frobe, U., Schlogl, A.,
& Jonas, P. (2012).** A deconvolution-based method with high sensitivity and
temporal resolution for detection of spontaneous synaptic currents in vitro and
in vivo. *Biophysical Journal*, 103(7), 1429-1439.
[doi:10.1016/j.bpj.2012.08.039](https://doi.org/10.1016/j.bpj.2012.08.039)
> Bi-exponential synaptic kernel parameterisation and z-scored detection
> threshold (`threshold_sd`, default `4.0`) in `synaptic_events.py` (Section 7.2).

**Jonas, P., Major, G., & Sakmann, B. (1993).** Quantal components of unitary
EPSCs at the mossy fibre synapse on CA3 pyramidal cells of rat hippocampus.
*Journal of Physiology*, 472(1), 615-663.
[doi:10.1113/jphysiol.1993.sp019965](https://doi.org/10.1113/jphysiol.1993.sp019965)
> Bi-exponential EPSC decay fitting (`fit_biexponential_decay`) and synaptic
> charge transfer integration (`calculate_event_charge_dynamic` and
> `examples/plugins/synaptic_charge.py`, Section 7.1).

**Rall, W. (1967).** Distinguishing theoretical synaptic potentials computed
for different soma-dendritic distributions of synaptic input.
*Journal of Neurophysiology*, 30(5), 1138-1168.
[doi:10.1152/jn.1967.30.5.1138](https://doi.org/10.1152/jn.1967.30.5.1138)
> Cable-theory prediction of 2-3x kinetic slowing for distal dendritic inputs;
> justification for the multi-kernel template bank (default multipliers
> `1.0, 2.0, 3.0`) in Section 7.2 and Section 15.4 (`synaptic_events.py`).

**Major, G., Larkman, A. U., Jonas, P., Sakmann, B., & Jack, J. J. B.
(1994).** Detailed passive cable models of whole-cell recorded CA3 pyramidal
neurons in rat hippocampal slices. *Journal of Neuroscience*, 14(8),
4613-4638.
[doi:10.1523/JNEUROSCI.14-08-04613.1994](https://doi.org/10.1523/JNEUROSCI.14-08-04613.1994)
> Quantitative validation of dendritic filtering (2-3x tau slowing) underlying
> the multi-scale template bank in Section 15.4 (`synaptic_events.py`).

---

## Paired-Pulse Ratio and Short-Term Plasticity

**Zucker, R. S., & Regehr, W. G. (2002).** Short-term synaptic plasticity.
*Annual Review of Physiology*, 64, 355-405.
[doi:10.1146/annurev.physiol.64.092501.114547](https://doi.org/10.1146/annurev.physiol.64.092501.114547)
> PPR baseline correction methodology (Section 13.2, Section 15.5); referencing
> amplitude to the pre-stimulus resting baseline and subtracting prior decay
> tails at subsequent response peaks (`evoked_responses.py`).

**Regehr, W. G. (2012).** Short-term presynaptic plasticity.
*Cold Spring Harbor Perspectives in Biology*, 4(7), a005702.
[doi:10.1101/cshperspect.a005702](https://doi.org/10.1101/cshperspect.a005702)
> Conceptual framework for PPR and stimulus-train STP interpretation -
> facilitation, depression, and biphasic plasticity classification
> (`evoked_responses.py`).

**Thanawala, M. S., & Regehr, W. G. (2013).** Presynaptic calcium influx
controls neurotransmitter release in part by regulating the effective size of
the readily releasable pool. *Journal of Neuroscience*, 33(11), 4625-4633.
[doi:10.1523/JNEUROSCI.4031-12.2013](https://doi.org/10.1523/JNEUROSCI.4031-12.2013)
> Iterative decay subtraction methodology (Section 15.5): for each pulse, the
> cumulative residual from all prior fitted decays is subtracted before
> measuring amplitude and fitting the current pulse's isolated decay.

**Wesseling, J. F., & Lo, D. C. (2002).** Limit on the role of activity in
controlling the release-ready supply of synaptic vesicles.
*Journal of Neuroscience*, 22(22), 9708-9720.
[doi:10.1523/JNEUROSCI.22-22-09708.2002](https://doi.org/10.1523/JNEUROSCI.22-22-09708.2002)
> Cumulative amplitude analysis with iterative decay correction for
> stimulus trains (`evoked_responses.py`).

**Kim, J., & Alger, B. E. (2001).** Random response fluctuations lead to
spurious paired-pulse facilitation. *Journal of Neuroscience*, 21(24),
9608-9618.
[doi:10.1523/JNEUROSCI.21-24-09608.2001](https://doi.org/10.1523/JNEUROSCI.21-24-09608.2001)
> Statistical motivation for reporting individual $R_1$ and $R_2$ amplitudes
> alongside sweep-level ratios so ratio-of-means ($\overline{R}_2 / \overline{R}_1$)
> can be evaluated free of Jensen's-inequality small-denominator bias
> (`evoked_responses.py`, Section 13.2).

**Sabatini, B. L., & Regehr, W. G. (1999).** Timing of synaptic transmission.
*Annual Review of Physiology*, 61, 521-542.
[doi:10.1146/annurev.physiol.61.1.521](https://doi.org/10.1146/annurev.physiol.61.1.521)
> Synaptic latency and trial-to-trial latency standard deviation (jitter)
> definitions in `calculate_optogenetic_sync` (`evoked_responses.py`,
> Section 13.1) and `examples/plugins/opto_jitter.py`.

**Boyden, E. S., Zhang, F., Bamberg, E., Nagel, G., & Deisseroth, K. (2005).**
Millisecond-timescale, genetically targeted optical control of neural activity.
*Nature Neuroscience*, 8(9), 1263-1268.
[doi:10.1038/nn1525](https://doi.org/10.1038/nn1525)
> Foundational optogenetic photostimulation paradigm (TTL-locked optical latency,
> spike fidelity/probability, and sub-millisecond spike jitter) implemented in
> `evoked_responses.py` and `examples/plugins/opto_jitter.py`.

---

## Excitability and Spike-Train Statistics

**Connors, B. W., & Gutnick, M. J. (1990).** Intrinsic firing patterns of
diverse neocortical neurons. *Trends in Neurosciences*, 13(3), 99-104.
[doi:10.1016/0166-2236(90)90185-D](https://doi.org/10.1016/0166-2236(90)90185-D)
> F-I slope gain, rheobase, and spike-frequency adaptation classification
> (`calculate_fi_curve` in `firing_dynamics.py`, Section 10).

**Shao, L.-R., Halvorsrud, R., Borg-Graham, L., & Storm, J. F. (1999).** The
role of BK-type $\text{Ca}^{2+}$-dependent $\text{K}^+$ channels in spike
broadening during repetitive firing in rat hippocampal pyramidal cells.
*Journal of Physiology*, 521(1), 135-146.
[doi:10.1111/j.1469-7793.1999.00135.x](https://doi.org/10.1111/j.1469-7793.1999.00135.x)
> Cumulative action-potential half-width broadening (`broadening_indices` and
> `spike_broadening_index` in `firing_dynamics.py`, Section 10 and Section 12).

**Holt, G. R., Softky, W. R., Koch, C., & Douglas, R. J. (1996).** Comparison
of discharge variability in vitro and in vivo in cat visual cortex neurons.
*Journal of Neurophysiology*, 75(5), 1806-1814.
[doi:10.1152/jn.1996.75.5.1806](https://doi.org/10.1152/jn.1996.75.5.1806)
> CV and $\text{CV}_2$ computation (`firing_dynamics.py`, Section 12).

**Shinomoto, S., Shima, K., & Tanji, J. (2003).** Differences in spiking
patterns among cortical neurons. *Neural Computation*, 15(12), 2823-2842.
[doi:10.1162/089976603322518759](https://doi.org/10.1162/089976603322518759)
> Local Variation (LV) metric (`firing_dynamics.py`, Section 12).

---

## Burst Detection

**Grace, A. A., & Bunney, B. S. (1984).** The control of firing pattern in
nigral dopamine neurons: burst firing. *Journal of Neuroscience*, 4(11),
2877-2890.
[doi:10.1523/JNEUROSCI.04-11-02877.1984](https://doi.org/10.1523/JNEUROSCI.04-11-02877.1984)
> Original ISI-criterion burst detection; adapted for cortical neurons in
> Section 9 (`firing_dynamics.py`).

**Harris, K. D., Hirase, H., Leinekugel, X., Henze, D. A., & Buzsaki, G.
(2001).** Temporal interaction between single spikes and complex spike bursts
in hippocampal pyramidal cells. *Neuron*, 32(1), 141-149.
[doi:10.1016/S0896-6273(01)00447-0](https://doi.org/10.1016/S0896-6273(01)00447-0)
> Dynamic ISI fraction (30% of mean ISI) for burst detection in Section 9
> (`firing_dynamics.py`).

---

## Data Standards

**Garcia, S., Guarino, D., Jaillet, F., et al. (2014).** Neo: an object model
for handling electrophysiology data in multiple formats. *Frontiers in
Neuroinformatics*, 8, 10.
[doi:10.3389/fninf.2014.00010](https://doi.org/10.3389/fninf.2014.00010)
> Electrophysiology I/O layer - all file format reading (ABF, WinWCP, CED,
> Intan, Igor, NWB, Open Ephys, and 30+ more) via `neo` in
> `infrastructure/file_readers/`.

**Rubel, O., Tritt, A., Ly, R., et al. (2022).** The Neurodata Without
Borders ecosystem for neurophysiological data science. *eLife*, 11:e78362.
[doi:10.7554/eLife.78362](https://doi.org/10.7554/eLife.78362)
> NWB 2.x export and FAIR metadata compliance; `CurrentClampSeries`,
> `VoltageClampSeries`, `IntracellularRecordingsTable`, and `ProcessingModule`
> containers (`infrastructure/exporters/nwb_exporter.py`).

---

## Scientific Python Ecosystem

**Virtanen, P., Gommers, R., Oliphant, T. E., et al. (2020).** SciPy 1.0:
Fundamental algorithms for scientific computing in Python.
*Nature Methods*, 17, 261-272.
[doi:10.1038/s41592-019-0686-2](https://doi.org/10.1038/s41592-019-0686-2)
> - `scipy.optimize.curve_fit` - tau (Section 3), capacitance (Section 5.2, Section 15.1), synaptic decay kinetics, and PPR decay fitting (Section 15.5, Section 15.6)
> - `scipy.signal.butter` / `bessel` / `iirnotch` / `iircomb` / `sosfilt` / `sosfiltfilt` - Butterworth, Bessel, notch, and harmonic comb digital filters via `_sosfiltfilt_safe` (`signal_processor.py`, Section 14.1) and derivative pre-filters (`single_spike.py`, Section 6.1, Section 6.2)
> - `scipy.ndimage.gaussian_filter1d` - Gaussian lowpass/highpass filters (`signal_processor.py`, Section 14.1) and variation-diminishing ADP waveform smoothing (`single_spike.py`, Section 6.8)
> - `scipy.signal.welch` - PSD and 50/60 Hz line noise assessment (Section 14.4)
> - `scipy.signal.savgol_filter` - sag smoothing (Section 4), AHP smoothing (Section 6.7), and phase-plane $dV/dt$ smoothing (Section 11)
> - `scipy.signal.detrend` - baseline detrending (Section 14.2) and quiescent baseline RMS window detrending (Section 7.2.1, Section 15.7)
> - `scipy.signal.find_peaks` - threshold and template synaptic event detection (Section 7.1, Section 7.2)
> - `scipy.stats.linregress` - I-V regression (Section 8), F-I slope (Section 10), and drift estimation (Section 1, Section 14.4)
> - `scipy.stats.median_abs_deviation` - MAD noise scale estimator (Section 7.1, Section 7.2)
> - `scipy.integrate.trapezoid` - capacitive charge integration (Section 5.2, Section 15.1)

**Harris, C. R., Millman, K. J., van der Walt, S. J., et al. (2020).**
Array programming with NumPy. *Nature*, 585, 357-362.
[doi:10.1038/s41586-020-2649-2](https://doi.org/10.1038/s41586-020-2649-2)
> All numerical array operations: `numpy.gradient` ($dV/dt$), `numpy.diff`
> (ISI), `numpy.trapezoid` (charge), `numpy.polyfit` (RMP drift and log-linear
> tau seed), and `numpy.nanmean` (guarded mean for $\text{CV}_2$, LV, and
> adaptation index).

**McKinney, W. (2010).** Data structures for statistical computing in Python.
*Proceedings of the 9th Python in Science Conference* (SciPy 2010), 56-61.
[doi:10.25080/Majora-92bf1922-00a](https://doi.org/10.25080/Majora-92bf1922-00a)
> `pandas.DataFrame` - batch-engine CSV output, wide and long format tables
> compatible with Python, R, and MATLAB downstream workflows.

---

## Visualization

**Wong, B. (2011).** Points of view: Color blindness.
*Nature Methods*, 8(6), 441.
[doi:10.1038/nmeth.1618](https://doi.org/10.1038/nmeth.1618)
> Colorblind-safe palette for all Synaptipy plot colors
> (`application/gui/`).

---

## Plugin Integrations

**O'Neill, P. S., Baccino-Calace, M., Rupprecht, P., Lee, S., Hao, Y. A., Lin, M. Z., Friedrich, R. W., Muller, M., & Delvendahl, I. (2025).**
A deep learning framework for automated and generalized synaptic event analysis. *eLife*, 13:RP98485.
[doi:10.7554/eLife.98485](https://doi.org/10.7554/eLife.98485)
> Citation for the deep-learning event detection used in the `miniml_integration.py` plugin.

**Buccino, A. P., Hurwitz, C. L., Garcia, S., Magland, J., Siegle, J. H., Hurwitz, R., & Hennig, M. H. (2020).**
SpikeInterface, a unified framework for spike sorting. *eLife*, 9:e61834.
[doi:10.7554/eLife.61834](https://doi.org/10.7554/eLife.61834)
> Citation for the spike sorting pipeline used in the `spike_interface_integration.py` plugin.

---

## How to Cite Synaptipy

If you use Synaptipy in published research, please cite the software directly
using the metadata in the repository `CITATION.cff` file:

```text
Shahul, A. K. (2026). Synaptipy: An Open-Source Electrophysiology
Visualization and Analysis Suite (v0.1.8).
https://github.com/anzalks/synaptipy
```

In addition, please consider citing the upstream libraries your analysis
depends on (Neo, PyNWB, SciPy, NumPy, pandas) as listed in the
[Dependencies and Citations](https://github.com/anzalks/synaptipy#dependencies-and-citations)
section of the README.
