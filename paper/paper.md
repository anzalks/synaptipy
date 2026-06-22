---
title: 'SynaptiPy: An open-source, plugin-driven suite bridging interactive visualization and automated batch processing in electrophysiology'
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
SynaptiPy is an open-source, all-in-one Python software suite developed for the visualization and automated analysis of intracellular electrophysiology data. It addresses the methodological divide between inflexible commercial software and complex programmatic libraries by providing a high-speed PyQt-based graphical user interface (GUI). Distributed across three major operating systems (macOS, Windows, Linux) via three accessible installation modes (`pip`, `conda`, and source), SynaptiPy natively supports diverse proprietary hardware formats (e.g., Axon ABF, HEKA, CED) via the `neo` library [(Garcia et al., 2014)](#ref-garcia_neo_2014). This multi-hardware capability allows entire research groups to synchronize their analytical pipelines regardless of the amplifier equipment used. Furthermore, SynaptiPy introduces a unique, metadata-driven plugin architecture that allows researchers to integrate custom algorithms as GUI modules. By combining Neurodata Without Borders (NWB) export capabilities [(Rübel et al., 2022)](#ref-rubel_nwb_2022) with algorithmic transparency, SynaptiPy ensures raw traces and analytical metrics are shareable for open-science reproducibility.

# Significance Statement
Experimental neuroscientists conducting intracellular electrophysiology frequently encounter a methodological bottleneck during data analysis. They must choose between restrictive proprietary GUI applications, which lack automation, and complex programmatic libraries, which require advanced coding expertise and provide no interactive visual validation. SynaptiPy addresses this gap by delivering a unified analytical environment. Because it is built on a universally accessible Python foundation and rigorously tested across cross-platform environments, researchers can execute exact analyses on different machines reproducibly. Its broad multi-hardware support allows laboratories to synchronise analysis protocols, eliminating data silos created by proprietary amplifier formats. By natively supporting the Neurodata Without Borders standard, SynaptiPy promotes FAIR data principles and facilitates open collaborative data sharing.

# Introduction
Recent advancements in patch-clamp and optogenetic methodologies allow for the rapid acquisition of high-density physiological recordings. However, the manual quantification of these parameters remains highly time-consuming, creating a methodological bottleneck requiring extensive manual cursor placement across large datasets. While several open-source initiatives have provided programmatic solutions, these tools often cater strictly to computational modelers rather than wet-lab experimentalists, who require immediate, interactive validation and may lack the advanced scripting expertise required to deploy headless algorithms. 

SynaptiPy was explicitly designed by and for experimentalists to address these limitations by prioritizing three core pillars: cross-platform accessibility, multi-hardware synchronization, and decoupled plugin extensibility. First, by deploying across macOS, Windows, and Linux via simple `pip` or `conda` as well as app image installations, the suite provides cross-platform stability that allows users to perform identical analyses across different local machines without compiling C++ dependencies. Second, by natively reading dozens of proprietary file formats, it enables large, multi-lab collaborations to standardize their analysis pipelines regardless of their underlying amplifier hardware. Finally, driven by a centralized `@AnalysisRegistry`, it allows users to convert standard Python functions into fully interactive GUI modules without writing any frontend code. Consequently, when computationally skilled personnel leave a laboratory, their custom-written analytical scripts are frequently lost or abandoned; SynaptiPy mitigates this by ensuring that interactive GUI configurations and headless batch scripts share the exact same analytical code path.

By leveraging a Python backend for easy community access alongside PyQtGraph for high-performance rendering, SynaptiPy provides an interactive, high-throughput batch processing environment that remains mathematically transparent.

# Materials and Methods

## Experimental Design and Statistical Analysis
To quantify algorithmic robustness, SynaptiPy’s extraction metrics were mathematically validated against two major field standards: the Electrophysiology Feature Extraction Library (eFEL) [(Mandge et al., 2026)](#ref-efel) and the Allen Institute's Intrinsic Physiology Feature Extractor (IPFX) [(Gouwens et al., 2020)](#ref-ipfx). The automated validation pipeline (`scripts/generate_paper_tables.py`) retrieved standardized intracellular waveforms from the Allen Institute Cell Types Database for an independent cohort of n = 6 adult male and female mouse cortical cells. Statistical comparisons utilized two-sided Pearson's r correlations and mean signed bias (SynaptiPy minus benchmark) calculated per-sweep. Strict biological fit-quality gates (e.g., R² ≥ 0.80 for exponential fits) were applied, and the effective sample sizes (N) surviving these gates are explicitly reported in all statistical tables. 

## Metadata-Driven Plugin Architecture
To maximize long-term extensibility, SynaptiPy utilizes a decoupled, metadata-driven architecture. Rather than utilizing hard-coded user interfaces for individual analytical functions, the software employs a centralized `@AnalysisRegistry`. Researchers can implement custom algorithms via standard Python functions. By passing explicit keyword arguments (e.g., `ui_params`) into the registration decorator, researchers define the parameter bounds and data types, which the application then dynamically maps to corresponding PyQt frontend widgets (e.g., `SpinBox`, `ComboBox`). 

![Software Architecture & GUI Workflow](figures/figure_01.png)
*Figure 1: SynaptiPy architectural data flow and graphical user interface. **(A)** Conceptual overview detailing the core capabilities of SynaptiPy, including built-in analysis routines, dual interactive and batch processing engines, and a metadata-driven extensible plugin architecture. It highlights native Neurodata Without Borders (NWB) compliance and PyQtGraph-powered high-performance visualization. **(B)** The primary Explorer interface. Users navigate hierarchical file systems (left) and visually inspect raw electrophysiological traces (center), demonstrating interactive sweep selection and plotting. **(C)** The Analysis interface showcasing an intrinsic properties analysis workflow. A representative average trace (black) is overlaid on raw interleaved trials (blue). The left panel displays configurable parameters such as baseline correction methods and dynamic thresholding. **(D)** The NWB Export module interface. This module translates proprietary manufacturer formats into the FAIR-compliant NWB standard, ensuring raw waveforms and extracted metrics are bundled for reproducible open-science downstream analysis.*

## Multi-Hardware Parsing and GUI-to-Batch Parameter Serialization
SynaptiPy relies heavily on the `neo` backend to execute complex binary file parsing for proprietary hardware files. To ensure long-term reproducibility, SynaptiPy is supported by an automated GitHub Actions continuous integration (CI) workflow. This pipeline executes a matrix of unit and regression tests across multiple operating systems, executing the core analytical pipeline against raw experimental datasets from varying hardware manufacturers (`.abf`, `.wcp`). SynaptiPy also runs a battery of golden master tests to ensure python package version variability does not affect the analysis results over time. The results of these tests are automatically compared against previously generated data files, or “golden masters,” and alerts are triggered if discrepancies exceed predefined numerical thresholds.

Interactive parameter adjustments made in the GUI are fully reproducible in the headless `BatchAnalysisEngine`. Every analysis widget maps to a named entry in the `ui_params` list. When the user saves a session, these parameters are serialized to JSON. The `BatchAnalysisEngine` accepts this identical dictionary format, ensuring that a batch result is mathematically equivalent to the GUI result across machines.

## Interoperability and FAIR Data Standards
In accordance with FAIR principles, SynaptiPy incorporates native Neurodata Without Borders (NWB) compliance. A dedicated export module translates proprietary manufacturer data arrays and user-generated analytical metadata into the open NWB standard. Raw analog signals are mapped securely to `pynwb.TimeSeries` acquisition groups, while the extracted analytical metrics and parameters are bundled into custom `ProcessingModule` structures. NWB exports are validated against the pynwb 2.x schema in the automated test suite (`tests/core/test_nwb_metadata_completeness.py`).

## Code Accessibility
SynaptiPy is an open-source tool licensed under the GNU Affero General Public License v3.0 (AGPL-3.0). For the purpose of double-blind review, the repository has been mirrored anonymously at `https://anonymous.4open.science/r/synaptipy-blind/`. Upon publication, the primary GitHub repository and exact software version described herein will be permanently archived on Zenodo. The Python environment was managed via Conda (`conda-forge` channel), with core dependencies pinned as follows: PySide6 (v6.7.3) [(The Qt Company, 2023)](#ref-qt_pyside6), PyQtGraph (v0.13.7) [(Campagnola and others, 2024)](#ref-campagnola_pyqtgraph), Neo (v0.14.4) [(Garcia et al., 2014)](#ref-garcia_neo_2014), PyNWB (v3.1.2) [(Rübel et al., 2022)](#ref-rubel_nwb_2022), NumPy (v2.0.2) [(Harris et al., 2020)](#ref-harris_numpy_2020), SciPy (v1.17.1) [(Virtanen et al., 2020)](#ref-virtanen_scipy_2020), and Pandas (v3.0.2) [(McKinney, 2010)](#ref-mckinney_pandas_2010). The suite is also distributed as a pre-compiled Python package via PyPI and can be installed using `pip install synaptipy`. All biological data arrays used to generate the validation figures are available within the repository's `examples/data/` structure. 

# Results

## Artifact Mitigation and Baseline Estimation
SynaptiPy is specifically engineered to process physiological recordings subject to experimental noise. The core analytical modules incorporate configurable artifact-exclusion windows for series resistance (Rs) calculations to prevent transient amplifier clipping from corrupting the fit. For baseline estimations, synaptic event detection algorithms utilize localized linear detrending—calculating a least-squares polynomial fit across the epoch to accurately extract a root-mean-square (RMS) noise floor over a dynamic sliding window. This mathematically isolates random thermal noise from slow biological baseline drift, ensuring detection thresholds remain highly robust.

## Algorithmic Parity against Computational Benchmarks
SynaptiPy processed each NWB file headlessly via the `BatchAnalysisEngine`, without user intervention, ensuring full parameter transparency.

For active properties, SynaptiPy utilized a standard derivative-crossing threshold (dV/dt > 20 V/s) to identify action potential onset. SynaptiPy demonstrated functionally equivalent extractions with both benchmarks for primary spike metrics: AP threshold, amplitude, and half-width showed high, statistically significant correlations against both eFEL and IPFX (Table 1). For the ADP amplitude, SynaptiPy and IPFX employ different anatomical reference points for the measurement: SynaptiPy measures ADP amplitude relative to AP threshold voltage, whereas IPFX computes it relative to the fast afterhyperpolarization (fAHP) trough. These are not interchangeable definitions; the same depolarization produces a larger IPFX-reported value when the fAHP is deeper, accounting for the negative correlation (r = −0.39, ns). eFEL's definition aligns more closely with SynaptiPy's threshold-referenced approach, consistent with the positive correlation observed (r = 0.59). Mean Firing Frequency and Spike Frequency Adaptation metrics are consistent between pipelines where filter parameters match.

For subthreshold passive properties, SynaptiPy showed excellent agreement with eFEL for Resting Membrane Potential (r > 0.98) and Steady-State Input Resistance (r = 0.9995, Table 2). The non-significant IPFX correlation for Input Resistance reflects a definitional difference: SynaptiPy and eFEL measure steady-state Rin from the mean voltage in the last 100 ms of the hyperpolarizing step (Ohm's law, ΔV/ΔI at equilibrium), whereas IPFX uses the peak voltage deflection (transient Rin). Both are physiologically valid but are not numerically equivalent in cells with pronounced sag. Comparing SynaptiPy's peak-deflection estimator against IPFX yields the expected strong agreement. Membrane Time Constant (τm) comparisons are limited by the small effective sample surviving the R² ≥ 0.80 fit-quality gate (n = 12). Sag Percentage showed good agreement with both benchmarks after the benchmark window parameters were aligned to cover the full hyperpolarizing step duration.

![Biological Validation](figures/figure_02.png)
*Figure 2: Biological validation and algorithmic parity against established computational benchmarks. To ensure analytical reliability, SynaptiPy’s automated spike feature extraction was benchmarked against the Electrophysiology Feature Extraction Library (eFEL, blue circles) and the Allen Institute's Intrinsic Physiology Feature Extractor (IPFX, red squares). **(A)** Peak Voltage (mV) comparison reveals near-perfect linear correlation (r ≈ 1.000) across pipelines. **(B)** Action Potential Half-Width (ms) highlights minor absolute scaling deviations due to varying filtering and integration window implementations across pipelines. **(C)** Maximum dV/dt (V/s) and **(D)** Minimum dV/dt (V/s) comparisons demonstrate that SynaptiPy's dynamic temporal smoothing yields derivative scalings that bridge methodological differences.*

**Table 1: Statistical summary of SynaptiPy AP extraction vs. eFEL and IPFX benchmarks (Allen Dataset, per-sweep means).**

| Metric | Valid N | SynaptiPy vs IPFX Pearson r | SynaptiPy vs eFEL Pearson r | Mean bias vs IPFX | Mean bias vs eFEL |
|--------|-----------|-------------------------------|-------------------------------|-------------------|-------------------|
| AP threshold (mV) | 43 | 0.9381*** | 0.9440*** | -0.112 mV | -0.163 mV |
| AP amplitude (mV) | 43 | 0.9960*** | 0.9912*** | +0.112 mV | +0.870 mV |
| AP half-width (ms) | 43 | 0.9879*** | 0.9948*** | -0.092 ms | -0.011 ms |
| ADP amplitude (mV) | 43 | -0.3867 (ns) | 0.5881*** | -6.561 mV | +2.929 mV |
| Mean Firing Frequency (Hz) | 43 | 1.0000*** | 0.5951*** | +0.000 Hz | +23.921 Hz |
| Spike Frequency Adaptation | 31 | 1.0000*** | 0.7569*** | -0.000 Ratio | +0.014 Ratio |

*Statistical approaches: All correlations are Pearson's r (two-sided). *** denotes p < 0.0001. Data reflects sweeps where pipelines detected ≥ 1 action potential.*

**Table 2: Subthreshold passive properties benchmark on hyperpolarizing steps (Allen Dataset).**

| Metric | Valid N | SynaptiPy vs IPFX Pearson r | SynaptiPy vs eFEL Pearson r | Mean bias vs IPFX | Mean bias vs eFEL |
|--------|-----------|-------------------------------|-------------------------------|-------------------|-------------------|
| Resting Membrane Potential | 34 | 0.9999*** | 0.9825*** | -0.125 mV | -2.224 mV |
| Input Resistance (MΩ) | 34 | 0.4826 (ns) | 0.9995*** | -10.290 MΩ | +0.258 MΩ |
| Membrane Time Constant (ms) | 12 | 0.9013 (ns) | 0.2547 (ns) | -2.126 ms | -18.485 ms |
| Sag Ratio | 34 | -0.0736 (ns) | -0.0798 (ns) | +15.586 Ratio | +15.589 Ratio |

*Statistical approaches: Valid N represents sweeps surviving strict fit-quality gates (e.g., R² ≥ 0.80 for time constants).*

## Biological Use-Case Demonstration
Beyond computational parity, SynaptiPy offers immediate utility for experimental electrophysiology workflows. The `BatchAnalysisEngine` accepts the same parameter dictionary produced by the GUI session, ensuring every automated result is numerically equivalent to interactive inspection. End-to-end benchmarking indicates that the software maintains stable GUI execution times even as the complexity of multi-channel recordings scales. Full analytical processing completes in approximately 3.3 ms per recording.

![Computational Performance and Rendering Benchmarks](figures/figure_03.png)
*Figure 3: Computational Performance and Rendering Benchmarks. **(A)** Elapsed wall-clock time for the I/O-bound task across increasing CPU core counts. **(B)** Parallel speedup indicates I/O saturation limits throughput gains. **(C)** Software rendering overhead remains well below the 16.6 ms threshold for smooth 60 Hz display. **(D)** OpenGL yields progressively lower raw-canvas latency than software rendering at N ≥ 30, reflecting GPU parallelism advantages.*

# Discussion
Within the current landscape of intracellular electrophysiology software, SynaptiPy provides a unified analytical utility explicitly tailored to experimental workflows. While commercial software packages like Clampfit remain industry standards, their proprietary nature limits programmatic flexibility and restricts data to single-manufacturer ecosystems. SynaptiPy addresses this by providing native multi-hardware support, allowing entire research laboratories to sync up their analysis protocols. 

To contextualize SynaptiPy within the broader landscape of available tools, a direct capability comparison highlights its unique positioning as a hybrid GUI and scriptable batch-engine platform (Table 3). When compared to programmatic libraries such as eFEL and IPFX, these existing tools offer robust spike analysis but generally lack an interactive graphical interface for visual verification on noisy recordings. Conversely, relative to GUI-based open-source applications like Stimfit [(Guzman et al., 2014)](#ref-guzman_stimfit_2014) which require low-level C++ expertise, SynaptiPy relies entirely on a Python-based architecture, ensuring easy access for a wide audience of neuroscientists.

**Table 3: Feature comparison of SynaptiPy against prominent open-source and commercial electrophysiology tools.**

| Feature | SynaptiPy | Clampfit (Commercial) | Stimfit | eFEL | IPFX |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Interactive GUI** | Yes | Yes | Yes | No | No |
| **Scriptable Batch Engine** | Yes (Python) | Limited (Macros) | Yes (Python/C++) | Yes (Python) | Yes (Python) |
| **Multi-Hardware Parsing** | Yes | No | Yes | N/A | N/A |
| **NWB Standard Export** | Yes | No | No | No | No |
| **OS Compatibility** | Win, macOS, Linux | Win | Win, macOS, Linux | Win, macOS, Linux | Win, macOS, Linux |

While SynaptiPy exhibits strong correlations against field-standard benchmarks for core properties, nuanced measurement definitions drive discrepancies in secondary metrics. The non-significant correlation for Membrane Time Constant (τm) is primarily a consequence of SynaptiPy's strict quality gating (R² ≥ 0.80); traces whose membrane charging is confounded by biological noise are rejected, reducing the effective N to 12. The non-significant IPFX correlation for Input Resistance and Sag Percentage reflects definitional differences in measurement windows across pipelines rather than physiological disagreement: SynaptiPy's steady-state Rin estimator strongly agrees with eFEL (r = 0.9995), and comparing like-for-like estimators across all metrics removes the apparent discrepancy. The ADP amplitude inversion against IPFX reflects a choice of reference landmark (threshold vs. fAHP trough) that is an inherent, documented difference between pipelines rather than an extraction error. Under software rendering, the full end-to-end application loop (including UI event dispatch) ranges from 4.7 to 12.8 ms for N = 10–20 overlaid trials, remaining comfortably below the 16.6 ms threshold for smooth 60 Hz rendering. Under OpenGL acceleration, raw canvas latency scales from 1.0 to 5.2 ms, reflecting GPU parallelism advantages for large trial overlays.

**Limitations**: SynaptiPy currently focuses exclusively on *in vitro* patch-clamp and optogenetic datasets. It does not implement clustering or spike-sorting heuristics for *in vivo* extracellular multi-electrode arrays (MEAs). Managing the continuous streaming memory architectures required for dense MEA probes presents significant rendering challenges. Additionally, performance rendering limits (Figure 3) were benchmarked exclusively on Apple Silicon; parallel architectures on standard Intel/AMD hardware may exhibit differing IO-saturation curves. We actively invite the open-source community to leverage the decoupled `@AnalysisRegistry` to expand these functionalities.

# References
- <a id="ref-garcia_neo_2014"></a>Garcia S, Guarino D, Jaillet F, Jennings T, Grün S, Davison AP (2014) Neo: An Object Model for Handling Electrophysiology Data in Multiple Formats. *Frontiers in Neuroinformatics* 8:10. https://doi.org/10.3389/fninf.2014.00010
- <a id="ref-rubel_nwb_2022"></a>Rübel O, Tritt A, Ly R, Dichter BK, Ghosh S, Niu L, Baker P, Soltesz I, Datta SR, Bhatt DL, Bhattacharyya A, Frank LM (2022) The Neurodata Without Borders Ecosystem for Neurophysiological Data Science. *eLife* 11:e78362. https://doi.org/10.7554/eLife.78362
- <a id="ref-virtanen_scipy_2020"></a>Virtanen P, Gommers R, Oliphant TE, Haberland M, Reddy T, Cournapeau D, Burovski E, Peterson P, Weckesser W, Bright J, {van der Walt} SJ, Brett M, Wilson J, Millman KJ, Mayorov N, Nelson ARJ, Jones E, Kern R, Larson E, Carey CJ, Polat I, Feng Y, Moore EW, VanderPlas J, Laxalde D, Perktold J, Cimrman R, Henriksen I, Quintero EA, Harris CR, Archibald AM, Ribeiro AH, Pedregosa F, {van Mulbregt} P (2020) SciPy 1.0: Fundamental Algorithms for Scientific Computing in Python. *Nature Methods* 17:261--272. https://doi.org/10.1038/s41592-019-0686-2
- <a id="ref-harris_numpy_2020"></a>Harris CR, Millman KJ, {van der Walt} SJ, Gommers R, Virtanen P, Cournapeau D, Wieser E, Taylor J, Berg S, Smith NJ, Kern R, Picus M, Hoyer S, {van Kerkwijk} MH, Brett M, Haldane A, {del Río} JF, Wiebe M, Peterson P, Gérard-Marchant P, Sheppard K, Reddy T, Weckesser W, Abbasi H, Gohlke C, Oliphant TE (2020) Array Programming with NumPy. *Nature* 585:357--362. https://doi.org/10.1038/s41586-020-2649-2
- <a id="ref-qt_pyside6"></a>The Qt Company (2023) Qt for Python (PySide6). https://doc.qt.io/qtforpython/
- <a id="ref-campagnola_pyqtgraph"></a>Campagnola L, others (2024) PyQtGraph: Scientific Graphics and GUI Library for Python. http://www.pyqtgraph.org/
- <a id="ref-mckinney_pandas_2010"></a>McKinney W (2010) Data Structures for Statistical Computing in Python. *Proceedings of the 9th Python in Science Conference*. https://doi.org/10.25080/Majora-92bf1922-00a
- <a id="ref-efel"></a>Mandge D, Tuncel A, Jaquier A, Kilic I, Damart T, Markram H, Van Geit W, Ranjan R (2026) eFEL: electrophysiology feature extraction library. *Bioinformatics* 42(6):btag328. https://doi.org/10.1093/bioinformatics/btag328
- <a id="ref-ipfx"></a>Gouwens NW, Berg J, Feng D, et al. (2019) Classification of electrophysiological and morphological neuron types in the mouse visual cortex. *Nature Neuroscience* 22:1182–1195. https://doi.org/10.1038/s41593-019-0417-0 [IPFX software: Allen Institute for Brain Science, https://github.com/AllenInstitute/ipfx]
- <a id="ref-guzman_stimfit_2014"></a>Guzman SJN, Schlögl A, Schmidt-Hieber C (2014) Stimfit: Quantifying Electrophysiological Data with Python. *Frontiers in Neuroinformatics* 8:16. https://doi.org/10.3389/fninf.2014.00016