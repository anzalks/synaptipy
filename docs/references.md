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
> Default dV/dt threshold (20 V/s) for spike onset detection in
> `single_spike.py`; reference for cortical pyramidal neuron AP kinetics.

**Hodgkin, A. L., & Huxley, A. F. (1952).** A quantitative description of
membrane current and its application to conduction and excitation in nerve.
*Journal of Physiology*, 117(4), 500-544.
[doi:10.1113/jphysiol.1952.sp004764](https://doi.org/10.1113/jphysiol.1952.sp004764)
> Foundational AP model. Basis for dV/dt-threshold detection, Na⁺ channel
> inactivation, and the separation of fast/medium AHP windows
> (`single_spike.py`, `firing_dynamics.py`).

**Naundorf, B., Wolf, F., & Volgushev, M. (2006).** Unique features of action
potential initiation in cortical neurons. *Nature*, 440(7087), 1060-1063.
[doi:10.1038/nature04610](https://doi.org/10.1038/nature04610)
> Artifact ceiling constant 300 V/s in `single_spike.py` — above this rate the
> rising phase is flagged as non-physiological.

**Sekerli, M., Del Negro, C. A., Lee, R. H., & Bhatt, D. L. (2004).**
Estimating action potential thresholds from neuronal time-series: new metrics
and evaluation of methodologies. *IEEE Transactions on Biomedical Engineering*,
51(9), 1665-1672.
[doi:10.1109/TBME.2004.827827](https://doi.org/10.1109/TBME.2004.827827)
> Maximum-curvature (d²V/dt²) AP threshold method in `single_spike.py` §6.2
> and §15.2.

**Henze, D. A., & Buzsaki, G. (2001).** Action potential threshold of
hippocampal pyramidal cells in vivo is increased by recent spiking activity.
*Neuroscience*, 105(1), 121-130.
[doi:10.1016/S0306-4522(01)00167-1](https://doi.org/10.1016/S0306-4522(01)00167-1)
> Motivation for per-spike dynamic threshold to accommodate Na⁺ channel
> inactivation across a spike train (`single_spike.py` §15.2).

---

## After-Hyperpolarisation (AHP)

**Storm, J. F. (1987).** Action potential repolarization and a fast
after-hyperpolarization in rat hippocampal pyramidal cells.
*Journal of Physiology*, 385, 733-759.
[doi:10.1113/jphysiol.1987.sp016517](https://doi.org/10.1113/jphysiol.1987.sp016517)
> Fast AHP window (1-5 ms) calibration — BK/Kv3 channel kinetics
> (`single_spike.py`).

**Sah, P., & Faber, E. S. L. (2002).** Channels underlying neuronal
calcium-activated potassium currents. *Progress in Neurobiology*, 66(5),
345-353.
[doi:10.1016/S0301-0082(02)00004-7](https://doi.org/10.1016/S0301-0082(02)00004-7)
> Medium AHP window (10-50 ms) calibration — SK/IK Ca²⁺-activated K⁺ channels
> (`single_spike.py`).

---

## Passive Membrane Properties

**Hamill, O. P., Marty, A., Neher, E., Sakmann, B., & Sigworth, F. J. (1981).**
Improved patch-clamp techniques for high-resolution current recording from cells
and cell-free membrane patches. *Pflugers Archiv*, 391(2), 85-100.
[doi:10.1007/BF00656997](https://doi.org/10.1007/BF00656997)
> Series-resistance measurement and whole-cell capacitance estimation
> (`passive_properties.py` §5.2 and §15.1). Seminal paper describing the
> whole-cell configuration of the patch-clamp technique.

**Neher, E., & Sakmann, B. (1976).** Single-channel currents recorded from
membrane of denervated frog muscle fibres. *Nature*, 260(5554), 799-802.
[doi:10.1038/260799a0](https://doi.org/10.1038/260799a0)
> Foundation for the patch-clamp method; provides the biophysical basis for
> passive-property analysis in `passive_properties.py`.

**Robinson, R. B., & Siegelbaum, S. A. (2003).** Hyperpolarization-activated
cation currents: From molecules to physiological function.
*Annual Review of Physiology*, 65, 453-480.
[doi:10.1146/annurev.physiol.65.092101.142734](https://doi.org/10.1146/annurev.physiol.65.092101.142734)
> HCN channel physiology — basis for peak vs. steady-state Rᵢₙ distinction
> (§2.2) and sag ratio interpretation (§4, `passive_properties.py`).

---

## Electrode Corrections

**Barry, P. H., & Lynch, J. W. (1991).** Liquid junction potentials and small
cell effects in patch-clamp analysis. *Journal of Membrane Biology*, 121(2),
101-117.
[doi:10.1007/BF01870526](https://doi.org/10.1007/BF01870526)
> Liquid Junction Potential correction procedure — §16 Step A,
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
> Original P/N subtraction protocol — §16 Step B, `processing_pipeline.py`.

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
> Savitzky-Golay filter used for AHP waveform smoothing (§6.7) and dV/dt
> computation (§6.9, §15.2) in `single_spike.py`.

**Butterworth, S. (1930).** On the Theory of Filter Amplifiers.
*Wireless Engineer*, 7, 536-541. (Original publication; no formal DOI.)
> Butterworth IIR filter design — basis for all lowpass, highpass, and bandpass
> filters in §14.1 (`signal_processor.py`), applied zero-phase via
> `scipy.signal.sosfiltfilt`.

**Welch, P. D. (1967).** The use of fast Fourier transform for the estimation
of power spectra: A method based on time averaging over short, modified
periodograms. *IEEE Transactions on Audio and Electroacoustics*, 15(2), 70-73.
[doi:10.1109/TAU.1967.1161901](https://doi.org/10.1109/TAU.1967.1161901)
> Welch's modified periodogram method for PSD estimation — §14.4 line noise
> detection and `compute_psd()` in `signal_processor.py` via
> `scipy.signal.welch`.

---

## Robust Noise Estimation

**Hampel, F. R. (1974).** The influence curve and its role in robust
estimation. *Journal of the American Statistical Association*, 69(346), 383-393.
[doi:10.1080/01621459.1974.10482962](https://doi.org/10.1080/01621459.1974.10482962)
> Median Absolute Deviation (MAD) with 1.4826 consistency factor for
> Gaussian-equivalent standard deviation; used in all three event-detection
> methods (§7.1, §7.2, §7.3, `synaptic_events.py`).

**Rousseeuw, P. J., & Croux, C. (1993).** Alternatives to the median absolute
deviation. *Journal of the American Statistical Association*, 88(424),
1273-1283.
[doi:10.1080/01621459.1993.10476408](https://doi.org/10.1080/01621459.1993.10476408)
> Robustness properties and 50% breakdown point of the MAD scale estimator;
> justification for use in contaminated electrophysiology traces
> (`synaptic_events.py`).

---

## Synaptic Event Detection

**Rall, W. (1967).** Distinguishing theoretical synaptic potentials computed
for different soma-dendritic distributions of synaptic input.
*Journal of Neurophysiology*, 30(5), 1138-1168.
[doi:10.1152/jn.1967.30.5.1138](https://doi.org/10.1152/jn.1967.30.5.1138)
> Cable-theory prediction of 2-3x kinetic slowing for distal dendritic inputs;
> justification for three-kernel template bank in §7.2 and §15.4
> (`synaptic_events.py`).

**Major, G., Larkman, A. U., Jonas, P., Sakmann, B., & Jack, J. J. B.
(1994).** Detailed passive cable models of whole-cell recorded CA3 pyramidal
neurons in rat hippocampal slices. *Journal of Neuroscience*, 14(8),
4613-4638.
[doi:10.1523/JNEUROSCI.14-08-04613.1994](https://doi.org/10.1523/JNEUROSCI.14-08-04613.1994)
> Quantitative validation of dendritic filtering (2-3x tau slowing) underlying
> the template bank in §15.4 (`synaptic_events.py`).

---

## Paired-Pulse Ratio and Short-Term Plasticity

**Zucker, R. S., & Regehr, W. G. (2002).** Short-term synaptic plasticity.
*Annual Review of Physiology*, 64, 355-405.
[doi:10.1146/annurev.physiol.64.092501.114547](https://doi.org/10.1146/annurev.physiol.64.092501.114547)
> PPR R2 baseline correction methodology (§15.5); referencing R2 amplitude to
> the pre-stimulus resting baseline (`evoked_responses.py`).

**Regehr, W. G. (2012).** Short-term presynaptic plasticity.
*Cold Spring Harbor Perspectives in Biology*, 4(7), a005702.
[doi:10.1101/cshperspect.a005702](https://doi.org/10.1101/cshperspect.a005702)
> Conceptual framework for PPR interpretation — facilitation (PPR > 1) and
> depression (PPR < 1) classification (`evoked_responses.py`).

---

## Spike-Train Statistics

**Holt, G. R., Softky, W. R., Koch, C., & Douglas, R. J. (1996).** Comparison
of discharge variability in vitro and in vivo in cat visual cortex neurons.
*Journal of Neurophysiology*, 75(5), 1806-1814.
[doi:10.1152/jn.1996.75.5.1806](https://doi.org/10.1152/jn.1996.75.5.1806)
> CV and CV₂ computation (`firing_dynamics.py` §12).

**Shinomoto, S., Shima, K., & Tanji, J. (2003).** Differences in spiking
patterns among cortical neurons. *Neural Computation*, 15(12), 2823-2842.
[doi:10.1162/089976603322518759](https://doi.org/10.1162/089976603322518759)
> Local Variation (LV) metric (`firing_dynamics.py` §12).

---

## Burst Detection

**Grace, A. A., & Bunney, B. S. (1984).** The control of firing pattern in
nigral dopamine neurons: burst firing. *Journal of Neuroscience*, 4(11),
2877-2890.
[doi:10.1523/JNEUROSCI.04-11-02877.1984](https://doi.org/10.1523/JNEUROSCI.04-11-02877.1984)
> Original ISI-criterion burst detection; adapted for cortical neurons in §9
> (`firing_dynamics.py`).

**Harris, K. D., Hirase, H., Leinekugel, X., Henze, D. A., & Buzsáki, G.
(2001).** Temporal interaction between single spikes and complex spike bursts
in hippocampal pyramidal cells. *Neuron*, 32(1), 141-149.
[doi:10.1016/S0896-6273(01)00447-0](https://doi.org/10.1016/S0896-6273(01)00447-0)
> Dynamic ISI fraction (30% of mean ISI) for burst detection in §9
> (`firing_dynamics.py`).

---

## Data Standards

**Garcia, S., Guarino, D., Jaillet, F., et al. (2014).** Neo: an object model
for handling electrophysiology data in multiple formats. *Frontiers in
Neuroinformatics*, 8, 10.
[doi:10.3389/fninf.2014.00010](https://doi.org/10.3389/fninf.2014.00010)
> Electrophysiology I/O layer — all file format reading (ABF, WinWCP, CED,
> Intan, Igor, NWB, Open Ephys, and 30+ more) via `neo` in
> `infrastructure/`.

**Rubel, O., Tritt, A., Ly, R., et al. (2022).** The Neurodata Without
Borders ecosystem for neurophysiological data science. *eLife*, 11:e78362.
[doi:10.7554/eLife.78362](https://doi.org/10.7554/eLife.78362)
> NWB 2.x export and FAIR metadata compliance; `CurrentClampSeries`,
> `VoltageClampSeries`, `IntracellularRecordingsTable`, `ProcessingModule`
> containers (`infrastructure/nwb_exporter.py`).

---

## Scientific Python Ecosystem

**Virtanen, P., Gommers, R., Oliphant, T. E., et al. (2020).** SciPy 1.0:
Fundamental algorithms for scientific computing in Python.
*Nature Methods*, 17, 261-272.
[doi:10.1038/s41592-019-0686-2](https://doi.org/10.1038/s41592-019-0686-2)
> `scipy.optimize.curve_fit` — tau (§3), capacitance (§5.2, §15.1), PPR
>   decay fitting (§15.5, §15.6)
> `scipy.signal.sosfiltfilt` / `butter` / `iirnotch` — all digital filters (§14.1)
> `scipy.signal.welch` — PSD / line noise assessment (§14.4)
> `scipy.signal.savgol_filter` — AHP smoothing (§6.7)
> `scipy.signal.detrend` — baseline detrending (§14.2, §15.7)
> `scipy.signal.find_peaks` — event detection (§7.1)
> `scipy.stats.linregress` — I-V regression (§8), F-I slope (§10), drift (§1)
> `scipy.stats.median_abs_deviation` — MAD noise floor (§7)
> `scipy.integrate.trapezoid` — capacitive charge integration (§5.2)

**Harris, C. R., Millman, K. J., van der Walt, S. J., et al. (2020).**
Array programming with NumPy. *Nature*, 585, 357-362.
[doi:10.1038/s41586-020-2649-2](https://doi.org/10.1038/s41586-020-2649-2)
> All numerical array operations: `numpy.gradient` (dV/dt), `numpy.diff`
> (ISI), `numpy.trapezoid` (charge), `numpy.nanmean` (robust mean for CV₂/LV).

**McKinney, W. (2010).** Data structures for statistical computing in Python.
*Proceedings of the 9th Python in Science Conference* (SciPy 2010), 51-56.
[doi:10.25080/Majora-92bf1922-00a](https://doi.org/10.25080/Majora-92bf1922-00a)
> `pandas.DataFrame` — batch-engine CSV output, wide and long format tables
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

**O'Neill, P. S., Baccino-Calace, M., Rupprecht, P., Lee, S., Hao, Y. A., Lin, M. Z., Friedrich, R. W., Müller, M., & Delvendahl, I. (2025).**
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
using the metadata in [`CITATION.cff`](https://github.com/anzalks/synaptipy/blob/main/CITATION.cff):

```
Shahul, A. K. (2026). SynaptiPy: An Open-Source Electrophysiology
Visualization and Analysis Suite (v0.1.6.1).
https://github.com/anzalks/synaptipy
```

In addition, please consider citing the upstream libraries your analysis
depends on (Neo, PyNWB, SciPy, NumPy, pandas) as listed in the
[Dependencies and Citations](https://github.com/anzalks/synaptipy#dependencies-and-citations)
section of the README.
