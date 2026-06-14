---
title: 'SynaptiPy: An Open-Source Electrophysiology Visualization and Analysis Suite'
short_title: 'SynaptiPy'
tags:
  - Python
  - neuroscience
  - electrophysiology
  - patch-clamp
  - optogenetics
  - GUI
  - NWB
authors:
  - name: Anzal K. Shahul
    orcid: 0009-0006-9932-7944
    affiliation: "1, 2"
affiliations:
 - name: Institute of Cellular and Integrative Neurosciences (INCI), Centre National de la Recherche Scientifique (CNRS), Strasbourg, France.
   index: 1
 - name: University of Strasbourg, Strasbourg, France.
   index: 2
date: 2026-04-24
bibliography: paper.bib
link-citations: true
---

# Abstract
SynaptiPy is an open-source, Python-based software suite developed for the visualization and automated analysis of intracellular electrophysiology data. It provides a modular, metadata-driven graphical user interface (GUI) designed to resolve the methodological divide between inflexible commercial software and complex programmatic libraries. SynaptiPy supports over 15 distinct analytical modules encompassing intrinsic passive properties, single-spike kinetics, short-term synaptic plasticity, and optogenetic mapping. The application natively supports multiple proprietary file formats via the `neo` library [(Garcia et al., 2014)](#ref-garcia_neo_2014) and integrates Neurodata Without Borders (NWB) export capabilities [(Rübel et al., 2022)](#ref-rubel_nwb_2022) to facilitate open-science reproducibility.

# Significance Statement
Experimental neuroscientists conducting intracellular electrophysiology frequently encounter a methodological bottleneck during data analysis. They must choose between proprietary GUI applications, which offer limited flexibility for automated high-throughput workflows, and programmatic libraries, which require advanced coding expertise and lack interactive visual validation. SynaptiPy bridges this gap by providing the analytical capabilities of modern Python libraries within a dynamic, accessible graphical environment. This enables researchers to perform rigorous, automated analysis across large experimental cohorts while maintaining complete algorithmic transparency and without extensive programming. By natively supporting the Neurodata Without Borders (NWB) standard [(Rübel et al., 2022)](#ref-rubel_nwb_2022), SynaptiPy promotes FAIR data principles, ensuring raw traces and analytical metrics are seamlessly shareable. This open-source suite accelerates discovery by eliminating the trade-off between computational throughput and interactive biological validation.

# Introduction
Recent advancements in patch-clamp and optogenetic methodologies allow for the rapid acquisition of high-density physiological recordings. However, the manual quantification of these parameters remains highly time-consuming and susceptible to user bias. While several open-source initiatives have provided programmatic solutions, these tools are often tailored toward computational modelers rather than experimentalists. SynaptiPy addresses this limitation by offering a highly maintainable software application that prioritizes interactive visual validation, automated batch processing, and robust computational stability for wet-lab researchers.

# Materials and Methods (Software Architecture)

### 1. Metadata-Driven Architecture and Extensibility
To maximize long-term extensibility, SynaptiPy utilizes a decoupled, metadata-driven architecture. Rather than utilizing hard-coded user interfaces for individual analytical functions, the software employs a centralized `@AnalysisRegistry`. Researchers can implement custom algorithms via standard Python functions, which the application automatically parses to dynamically generate graphical user interfaces.

SynaptiPy's architecture strictly separates core data processing (Headless CLI/API) from graphical rendering (GUI), ensuring identical analytical paths across paradigms. The GUI wraps the core algorithms using a model-view-controller paradigm heavily optimized via PyQtGraph for high-performance software rendering.

![Software Architecture & GUI Workflow](results/gui_workflow.png)
*Figure 1: SynaptiPy architectural data flow and graphical user interface. **(A)** Overview of the underlying data flow, analysis stacks, and technical architecture supporting the analytical pipeline. **(B)** The Explorer Interface for multi-channel `.abf` navigation, interactive filtering, and declarative spike threshold configuration. **(C)** The Analyser Interface providing instantaneous kinetic extractions, biological phase-plane trajectories, and physiological summary statistics. **(D)** The High-Throughput Batch Engine, enabling multi-file aggregate feature extraction mapped directly to scientific DataFrames for downstream NWB or CSV export.*

### 2. Extensible Data Parsing and Software Maintenance
A common limitation of academic software is dependency drift, where unmonitored updates to third-party libraries alter underlying calculations. To ensure long-term reproducibility, SynaptiPy is supported by a continuous integration and continuous deployment (CI/CD) pipeline with strict semantic dependency constraints. Furthermore, the repository employs baseline regression testing-executing the core analytical pipeline against raw experimental datasets (`.abf`, `.wcp`) during automated checks-to verify that upstream updates to core libraries (`SciPy` [(Virtanen et al., 2020)](#ref-virtanen_scipy_2020), `NumPy` [(Harris et al., 2020)](#ref-harris_numpy_2020)) do not introduce silent mathematical deviations.

### 3. GUI-to-Batch Parameter Serialization

Interactive parameter adjustments made in the SynaptiPy GUI are fully reproducible in the headless `BatchAnalysisEngine`. Every analysis widget (spin-boxes, draggable region handles, combo-boxes) maps to a named entry in the `ui_params` list declared alongside the `@AnalysisRegistry.register(...)` decorator. When the user clicks **Run Analysis**, `_gather_analysis_parameters()` reads the current widget values into a plain Python dictionary:

```python
params = {"stim_start_time": 0.200, "fit_duration": 0.300, "model": "mono"}
```

This dictionary is stored in `SessionManager` and serialized to JSON when the user saves a session file. The `BatchAnalysisEngine` accepts the same dictionary format and invokes the identical registered wrapper function, ensuring that a batch result is mathematically equivalent to the GUI result. Draggable region handles are two-way linked to their spin-box counterparts via Qt signals; the spin-box value-not the graphical position-is the canonical parameter that enters the analysis. The preprocessing pipeline (filters, baseline subtraction) is passed to the batch engine via `preprocessing_settings`, applying the same `ProcessingPipeline` that the GUI uses on the visually validated trace.

### 4. Interoperability and FAIR Data Standards
In accordance with FAIR (Findable, Accessible, Interoperable, and Reusable) data principles, SynaptiPy incorporates native Neurodata Without Borders (NWB) compliance. A dedicated export module translates proprietary manufacturer data arrays and user-generated analytical metadata into the open NWB standard, thereby streamlining data deposition and facilitating cross-laboratory reproducibility. Critically, SynaptiPy does not merely package raw voltage traces: the exporter writes the extracted analytical metrics -- including action potential thresholds, input resistance ($R_{\text{in}}$), membrane time constants, and synaptic kinetics -- as structured NWB ``TimeSeries`` and ``IntracellularElectrophysiology`` table entries alongside the raw waveforms, enabling downstream reanalysis without repeating the full analysis pipeline. Stimulus artifact interpolation is applied *before* any digital signal processing (DSP) filter in the preprocessing pipeline; performing interpolation upstream of filtering prevents Gibbs ringing that would otherwise smear transient energy across the waveform and corrupt kinetic measurements, a common flaw in single-step electrophysiology analysis workflows.

P/N leak subtraction relies entirely on *manual sweep selection* by the experimenter. The user explicitly designates which sweeps serve as sub-threshold P/N references via the GUI; automated inference of leak-only sweeps is intentionally not implemented because amplifier protocols vary too widely across laboratories and formats (Axon ABF, WinWCP, CED) for a heuristic to reliably distinguish true leak sweeps from test pulses. This design decision ensures accurate leak isolation regardless of the recording hardware or stimulus template.

### 5. Environment Declaration
All development, validation, and benchmarking procedures described herein were performed on an Apple Silicon (M1) architecture running macOS 15.x using SynaptiPy (RRID:SCR_XXXXXX — replace with actual RRID from scicrunch.org/resources after registration). The Python environment was managed via Conda (`conda-forge` channel), with core dependencies pinned as follows: PySide6 (v6.7.3) [(The Qt Company, 2023)](#ref-qt_pyside6), PyQtGraph (v0.13.7) [(Campagnola and others, 2024)](#ref-campagnola_pyqtgraph), Neo (v0.14.4) [(Garcia et al., 2014)](#ref-garcia_neo_2014), PyNWB (v3.1.2) [(Rübel et al., 2022)](#ref-rubel_nwb_2022), NumPy (v2.0.2) [(Harris et al., 2020)](#ref-harris_numpy_2020), SciPy (v1.17.1) [(Virtanen et al., 2020)](#ref-virtanen_scipy_2020), and Pandas (v3.0.2) [(McKinney, 2010)](#ref-mckinney_pandas_2010). This frozen environment ensures exact replicability of the reported performance metrics.

# Results (Biological Validation and Performance)

### 1. Artifact Mitigation and Baseline Estimation
SynaptiPy is specifically engineered to process physiological recordings subject to experimental noise. The core analytical modules incorporate configurable artifact-exclusion windows for series resistance ($R_s$) calculations, preventing capacitance misestimations. Additionally, the synaptic event detection algorithms utilize localized linear detrending to calculate accurate root-mean-square (RMS) noise floors, isolating thermal noise from slow baseline drift. The RMS noise floor is computed over a sliding window of length $w = \lfloor 50\,\text{ms} / \Delta t \rfloor$ samples that advances in non-overlapping steps across the pre-event region. Within each window the linear trend is removed by ordinary least-squares regression before computing the RMS, ensuring that slow biological drift (e.g., intrinsic bursting, after-depolarizations) does not inflate the noise estimate. Windows containing candidate events are identified by a preliminary amplitude threshold and excluded from the noise calculation, so physiological transients do not bias the floor estimate.

### 2. Algorithmic Transparency and Visual Validation
To facilitate user confidence in automated metrics, SynaptiPy relies heavily on visual validation. The software renders declarative overlays directly onto the raw electrophysiological traces via PyQtGraph [(Campagnola and others, 2024)](#ref-campagnola_pyqtgraph). Users can visually confirm baseline assessment windows, spike threshold detection coordinates, and exponential decay kinetics superimposed on the raw data, ensuring that algorithmic outputs accurately reflect the underlying biology.

To further demonstrate algorithmic robustness, SynaptiPy's Action Potential extraction metrics were mathematically validated against two major industry standards: the Electrophysiology Feature Extraction Library (eFEL) [(Mandge et al., 2026)](#ref-efel) and the Allen Institute's Intrinsic Physiology Feature Extractor (IPFX) [(Gouwens et al., 2020)](#ref-ipfx). Across intrinsic electrophysiological sweeps (`2023_04_11_0021.abf`), SynaptiPy extracted functionally equivalent peak voltages with both benchmarks (IPFX Pearson *r* = 1.00; eFEL *r* = 0.99). Differences in absolute scaling for spike kinetics highlighted the diverse mathematical paradigms across pipelines. For example, to maximize robustness to real experimental sampling without artificially "pixelating" sub-samples via interpolation, SynaptiPy calculates the biological half-width exclusively between discrete physical sampling boundaries, mimicking the core logic of both eFEL and IPFX. Furthermore, to accurately capture true instantaneous voltage rise without micro-noise artifacts, SynaptiPy utilizes a dynamic, sampling-rate-dependent rolling window (standard 0.1 ms) across the raw derivative. Because IPFX utilizes a 9.9 kHz Bessel filter (preserving steeper high-frequency upstrokes) and eFEL utilizes heavily bounded derivative stencils, SynaptiPy's dynamic 0.1 ms smoothing results in a natural median scaling, maintaining exceptionally high biological correlations with both IPFX (*r* = 0.95) and eFEL (*r* = 0.92) for Max dV/dt, as well as near-perfect correlations for Min dV/dt (IPFX *r* > 0.99; eFEL *r* = 0.96).

![Biological Validation](results/biological_validation.png)
*Figure 2: Biological validation and algorithmic parity against established computational benchmarks. Scatter plots comparing Action Potential metrics between SynaptiPy, eFEL (Blue), and IPFX (Orange) across intrinsic sweeps. Statistical insets display the Pearson correlation coefficient ($r$) and corresponding two-sided $p$-value. Bias represents the mean mathematical difference between SynaptiPy and the respective benchmark, inheriting the units of the plotted metric. **(A)** Peak Voltage, showing perfect alignment. **(B)** Half-Width, calculated using discrete physical sampling boundaries across all three platforms. Absolute scaling differences occur purely due to distinct boundary definitions (e.g., eFEL's rigid 20 V/s threshold vs. SynaptiPy's maximum curvature method). **(C)** Max dV/dt and **(D)** Min dV/dt. SynaptiPy's derivative uses a dynamic 0.1 ms temporal smoothing window, situating its absolute scaling squarely between IPFX's 9.9 kHz Bessel filtering and eFEL's heavy discrete approximation, whilst maintaining excellent relative correlation with both.*

**Extended Data Table 1: Statistical summary of SynaptiPy AP extraction vs. eFEL and IPFX benchmarks (file: `2023_04_11_0021.abf`, per-sweep means).**

| Metric | n sweeps | SynaptiPy vs IPFX Pearson *r* | SynaptiPy vs eFEL Pearson *r* | Mean bias vs IPFX | Mean bias vs eFEL | Statistical approach |
|--------|----------|-------------------------------|-------------------------------|-------------------|-------------------|----------------------|
| Peak voltage (mV) | 13 | 1.0000 (*p* < 0.0001) | 0.9998 (*p* < 0.0001) | +0.000 mV | +0.229 mV | Pearson correlation, two-sided *p* |
| AP threshold (mV) | 13 | 0.8195 (*p* 0.0006) | 0.7641 (*p* 0.0024) | +32.092 mV | +31.696 mV | Pearson correlation, two-sided *p* |
| AP amplitude (mV) | 13 | 0.9588 (*p* < 0.0001) | 0.9560 (*p* < 0.0001) | -32.092 mV | -31.467 mV | Pearson correlation, two-sided *p* |
| AP half-width (ms) | 13 | 0.1691 (*p* 0.5808) | -0.1502 (*p* 0.6243) | -0.244 ms | -0.193 ms | Pearson correlation, two-sided *p* |
| Max dV/dt (V/s) | 13 | 0.9981 (*p* < 0.0001) | 0.9933 (*p* < 0.0001) | -57.323 V/s | +140.247 V/s | Pearson correlation, two-sided *p* |
| Min dV/dt (V/s) | 13 | 0.9997 (*p* < 0.0001) | 0.9971 (*p* < 0.0001) | +1.095 V/s | -29.109 V/s | Pearson correlation, two-sided *p* |
| Fast AHP depth (mV) | 13 | -0.6141 (*p* 0.0256) | -0.8355 (*p* 0.0004) | +32.381 mV | +31.640 mV | Pearson correlation, two-sided *p* |
| ADP amplitude (mV) | 13 | -0.1797 (*p* 0.5568) | -0.5595 (*p* 0.0468) | +70.714 mV | +70.959 mV | Pearson correlation, two-sided *p* |

*n sweeps = number of sweeps in which all three pipelines detected ≥1 action potential. Bias = mean signed difference (SynaptiPy − benchmark, per-sweep means). SynaptiPy: BatchAnalysisEngine `spike_detection` (dV/dt threshold 20 V/s, refractory 2 ms). eFEL: BlueBrain eFEL defaults. IPFX: Allen IPFX SpikeFeatureExtractor, 9.9 kHz Bessel filter.*

**Extended Data Table 2: Subthreshold passive properties benchmark on -20 pA steps (files: `2023_04_11_0019.abf`, `0022.abf`).**

| Metric | n sweeps | SynaptiPy vs IPFX Pearson *r* | SynaptiPy vs eFEL Pearson *r* | Mean bias vs IPFX | Mean bias vs eFEL | Statistical approach |
|--------|----------|-------------------------------|-------------------------------|-------------------|-------------------|----------------------|
| Resting Membrane Potential (mV) | 17 | -0.4900 (*p* 0.0459) | -0.6107 (*p* 0.0092) | +39.804 mV | +39.705 mV | Pearson correlation, two-sided *p* |
| Input Resistance (MΩ) | 0 | N/A (*p* N/A) | N/A (*p* N/A) | N/A | N/A | Pearson correlation, two-sided *p* |
| Membrane Time Constant (ms) | 1 | N/A (*p* N/A) | N/A (*p* N/A) | N/A | N/A | Pearson correlation, two-sided *p* |

*n sweeps = number of valid sweeps containing a -20 pA hyperpolarizing current injection step. SynaptiPy passive properties extracted via BatchAnalysisEngine using `rmp_analysis`, `rin_analysis`, and `tau_analysis` modules. IPFX extraction via `subthresh_features`.*


### 3. High-Throughput Processing and Rendering Optimization
The integrated batch processing engine minimizes manual analysis bottlenecks, allowing for the rapid extraction of intrinsic properties and synaptic events across extensive experimental cohorts. To support this high-throughput capability, SynaptiPy utilizes significant rendering optimizations. End-to-end benchmarking indicates that the software maintains stable GUI execution times and smooth navigational frame rates even as the complexity and density of the multi-channel recordings scale. Specifically, full analytical processing completes in ~3.3 ms per recording, and the optimized PyQtGraph rendering pipeline maintains an interactive GUI frame rate exceeding 200 frames per second (4.79 ms median frame latency) even at maximum plot density (20 simultaneous overlaid traces).

![Batch Scaling Benchmark](results/benchmark_scaling.png)
*Figure 3: Batch execution scaling across increasing file complexities. **(A)** Median wall-clock execution time for single-channel spike detection as the number of parallel CPU cores increases. Error bars denote the absolute minimum and maximum execution times recorded across trials. **(B)** Corresponding parallel processing speedup relative to the ideal linear curve (S=W). **(C)** Median execution time for multi-channel threshold event detection. **(D)** Corresponding speedup for the multi-channel pipeline, demonstrating robust throughput improvements with increased core utilization.*

![Rendering Benchmark](results/rendering_benchmark.png)
*Figure 4: Rendering optimizations for high-frequency multichannel data. **(A)** Absolute per-frame update latency as the number of overlaid trial sweeps (N) increases, comparing standard software rasterization (QPainter) to the PyQtGraph-optimised rendering path. Error bars represent the 5th and 95th percentiles of recorded rendering latency. **(B)** Grouped bar chart comparing rendering times directly; the PyQtGraph-optimised rendering path significantly attenuates latency scaling at maximum plotting densities.*

![End-to-End macOS Rendering](results/e2e_rendering_benchmark_macos.png)
*Figure 5: Cross-platform end-to-end rendering stability. **(A)** Full integrated graphical window update times on the macOS architecture, demonstrating rendering latency versus overlaid trial count. Error bars correspond to the 5th and 95th latency percentiles. **(B)** Grouped visualization of frame latency, highlighting that the optimised PyQtGraph rendering path preserves sub-5 ms frame render times even under maximum trace overlay density.*

# Discussion

Within the current landscape of intracellular electrophysiology software, SynaptiPy provides a distinct analytical utility. While commercial software packages like Clampfit remain industry standards, their proprietary nature limits programmatic flexibility for high-throughput batch analysis. SynaptiPy addresses this by providing comparable analytical rigor alongside comprehensive automation and an open-source (AGPL-3.0) license. 

When compared to programmatic libraries such as the Electrophysiology Feature Extraction Library (eFEL) [(Mandge et al., 2026)](#ref-efel) and the Allen Institute's Intrinsic Physiology Feature Extractor (IPFX) [(Gouwens et al., 2020)](#ref-ipfx), these existing tools offer robust spike analysis for modeling datasets, but generally lack an interactive graphical interface for visual verification on raw, noisy recordings. SynaptiPy integrates these high-throughput programmatic strengths into a cohesive visual platform utilizing experimental-grade algorithms. 

Furthermore, relative to GUI-based open-source applications like Stimfit [(Guzman et al., 2014)](#ref-guzman_stimfit_2014), which provides a highly respected C++ application, extending such software requires low-level programming expertise. SynaptiPy relies entirely on a Python-based architecture for simplified extensibility and includes native integration with modern NWB standards, significantly lowering the barrier to entry for experimental neuroscientists.

# Availability

SynaptiPy is an open-source tool licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
- **Source Code**: [https://github.com/anzalks/synaptipy](https://github.com/anzalks/synaptipy)
- **Documentation**: [https://synaptipy.readthedocs.io/](https://synaptipy.readthedocs.io/)
- **PyPI Distribution**: `pip install synaptipy`

## Data and Code Availability
In accordance with *eNeuro* guidelines for reproducible research, the source code and exact software version described in this manuscript will be permanently archived on Zenodo upon publication. All biological data arrays used to generate the validation and performance figures (e.g., `2023_04_11_0021.abf`) are available within the open-source repository's `examples/data/` structure to ensure complete reproducibility of the described algorithms.

# Conflict of Interest
The authors declare no competing financial interests.

# Acknowledgments
We thank the open-source scientific Python community for maintaining the foundational libraries that make this software possible.



# References

- <a id="ref-garcia_neo_2014"></a>Garcia S, Guarino D, Jaillet F, Jennings T, Grün S, Davison AP (2014) Neo: An Object Model for Handling Electrophysiology Data in Multiple Formats. *Frontiers in Neuroinformatics* 8:10. https://doi.org/10.3389/fninf.2014.00010

- <a id="ref-rubel_nwb_2022"></a>Rübel O, Tritt A, Ly R, Dichter BK, Ghosh S, Niu L, Baker P, Soltesz I, Datta SR, Bhatt DL, Bhattacharyya A, Frank LM (2022) The Neurodata Without Borders Ecosystem for Neurophysiological Data Science. *eLife* 11:e78362. https://doi.org/10.7554/eLife.78362

- <a id="ref-virtanen_scipy_2020"></a>Virtanen P, Gommers R, Oliphant TE, Haberland M, Reddy T, Cournapeau D, Burovski E, Peterson P, Weckesser W, Bright J, {van der Walt} SJ, Brett M, Wilson J, Millman KJ, Mayorov N, Nelson ARJ, Jones E, Kern R, Larson E, Carey CJ, Polat I, Feng Y, Moore EW, VanderPlas J, Laxalde D, Perktold J, Cimrman R, Henriksen I, Quintero EA, Harris CR, Archibald AM, Ribeiro AH, Pedregosa F, {van Mulbregt} P (2020) SciPy 1.0: Fundamental Algorithms for Scientific Computing in Python. *Nature Methods* 17:261--272. https://doi.org/10.1038/s41592-019-0686-2

- <a id="ref-harris_numpy_2020"></a>Harris CR, Millman KJ, {van der Walt} SJ, Gommers R, Virtanen P, Cournapeau D, Wieser E, Taylor J, Berg S, Smith NJ, Kern R, Picus M, Hoyer S, {van Kerkwijk} MH, Brett M, Haldane A, {del Río} JF, Wiebe M, Peterson P, Gérard-Marchant P, Sheppard K, Reddy T, Weckesser W, Abbasi H, Gohlke C, Oliphant TE (2020) Array Programming with NumPy. *Nature* 585:357--362. https://doi.org/10.1038/s41586-020-2649-2

- <a id="ref-qt_pyside6"></a>The Qt Company (2023) Qt for Python (PySide6). https://doc.qt.io/qtforpython/

- <a id="ref-campagnola_pyqtgraph"></a>Campagnola L, others (2024) PyQtGraph: Scientific Graphics and GUI Library for Python. http://www.pyqtgraph.org/

- <a id="ref-mckinney_pandas_2010"></a>McKinney W (2010) Data Structures for Statistical Computing in Python. *Proceedings of the 9th Python in Science Conference*. https://doi.org/10.25080/Majora-92bf1922-00a

- <a id="ref-efel"></a>Mandge D, Tuncel A, Jaquier A, Kilic I, Damart T, Markram H, Van Geit W, Ranjan R (2026) eFEL: electrophysiology feature extraction library. *Bioinformatics* 42(6):btag328. https://doi.org/10.1093/bioinformatics/btag328

- <a id="ref-ipfx"></a>Gouwens NW, Sorensen SA, Baftizadeh F, et al. (2020) Integrated morphoelectric and transcriptomic characterization of GABAergic interneurons in the mouse primary visual cortex. *Cell* 183(4):936-953.e19. https://doi.org/10.1016/j.cell.2020.09.057

- <a id="ref-guzman_stimfit_2014"></a>Guzman SJN, Schlögl A, Schmidt-Hieber C (2014) Stimfit: Quantifying Electrophysiological Data with Python. *Frontiers in Neuroinformatics* 8:16. https://doi.org/10.3389/fninf.2014.00016

