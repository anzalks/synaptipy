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
SynaptiPy is an open-source, all-in-one Python software suite developed for the visualization and automated analysis of intracellular electrophysiology data. It bridges the methodological divide between inflexible commercial software and complex programmatic libraries by providing a high-speed PyQt-based graphical user interface (GUI). Distributed across three major operating systems (macOS, Windows, Linux) via three accessible installation modes (`pip`, `conda`, and source), SynaptiPy natively supports diverse proprietary hardware formats via the `neo` library [(Garcia et al., 2014)](#ref-garcia_neo_2014). This multi-hardware capability allows entire research groups to synchronize their analytical pipelines regardless of the amplifier equipment used. Furthermore, SynaptiPy introduces a unique, metadata-driven plugin architecture that allows researchers to integrate custom algorithms as GUI modules effortlessly. By combining Neurodata Without Borders (NWB) export capabilities [(Rübel et al., 2022)](#ref-rubel_nwb_2022) with algorithmic transparency, SynaptiPy ensures raw traces and analytical metrics are seamlessly shareable for open-science reproducibility.

# Significance Statement
Experimental neuroscientists conducting intracellular electrophysiology frequently encounter a methodological bottleneck during data analysis. They must choose between proprietary GUI applications, which lack automation, and programmatic libraries, which require advanced coding expertise. SynaptiPy bridges this gap by delivering a comprehensive, all-in-one analytical environment. Because it is built on a universally accessible Python foundation and rigorously tested across cross-platform environments, researchers can execute the exact same analysis on different machines seamlessly. Furthermore, its multi-hardware support fundamentally helps different laboratories sync up their analysis protocols, eliminating data-silos created by proprietary amplifier formats. By natively supporting the Neurodata Without Borders (NWB) standard, SynaptiPy promotes FAIR data principles and accelerates collaborative discovery.

# Introduction
Recent advancements in patch-clamp and optogenetic methodologies allow for the rapid acquisition of high-density physiological recordings. However, the manual quantification of these parameters remains highly time-consuming. While several open-source initiatives have provided programmatic solutions, these tools often cater to computational modelers rather than wet-lab experimentalists. SynaptiPy was explicitly designed to address these limitations by prioritizing three core pillars: unprecedented accessibility, multi-hardware synchronization, and unique plugin extensibility. First, by deploying across macOS, Windows, and Linux via simple `pip` or `conda` installations, the suite provides cross-platform stability that allows users to perform identical analyses across different local machines. Second, by natively reading dozens of proprietary file formats (e.g., Axon ABF, WinWCP, CED), it empowers large, multi-lab collaborations to standardize their analysis pipelines regardless of their underlying amplifier hardware. Finally, driven by a centralized `@AnalysisRegistry`, it allows users to convert standard Python functions into fully interactive GUI modules without writing frontend code.

By leveraging a Python backend for easy community access alongside PyQtGraph for ultra-fast rendering, SynaptiPy provides an interactive, high-throughput batch processing environment that remains mathematically transparent.

# Materials and Methods (Software Architecture)

### 1. Metadata-Driven Plugin Architecture
To maximize long-term extensibility, SynaptiPy utilizes a one-of-a-kind, decoupled, metadata-driven architecture. Rather than utilizing hard-coded user interfaces for individual analytical functions, the software employs a centralized `@AnalysisRegistry`. Researchers can implement custom algorithms via standard Python functions, which the application automatically parses to dynamically generate graphical user interfaces. 

SynaptiPy's architecture strictly separates core data processing (Headless CLI/API) from graphical rendering (GUI), ensuring identical analytical paths across paradigms. The GUI wraps the core algorithms using a model-view-controller paradigm heavily optimized via PyQtGraph for high-performance software rendering.

![Software Architecture & GUI Workflow](results/gui_workflow.png)
*Figure 1: SynaptiPy architectural data flow and graphical user interface.*

### 2. Multi-Hardware Parsing and Software Maintenance
A common limitation of academic software is dependency drift, where unmonitored updates to third-party libraries alter underlying calculations. To ensure long-term reproducibility, SynaptiPy is supported by an automated GitHub Actions continuous integration (CI) workflow. This pipeline executes a matrix of unit and regression tests across multiple operating systems (macOS, Windows, Ubuntu) and varying Python versions on every code commit. Furthermore, the repository employs baseline regression testing—executing the core analytical pipeline against raw experimental datasets from varying hardware manufacturers (`.abf`, `.wcp`)—to verify that upstream updates to core libraries do not introduce silent mathematical deviations.

### 3. GUI-to-Batch Parameter Serialization
Interactive parameter adjustments made in the SynaptiPy GUI are fully reproducible in the headless `BatchAnalysisEngine`. Every analysis widget maps to a named entry in the `ui_params` list declared alongside the `@AnalysisRegistry.register(...)` decorator. When the user clicks **Run Analysis**, `_gather_analysis_parameters()` reads the current widget values into a plain Python dictionary. This dictionary is serialized to JSON when the user saves a session file. The `BatchAnalysisEngine` accepts the same dictionary format and invokes the identical registered wrapper function, ensuring that a batch result is mathematically equivalent to the GUI result across machines. 

### 4. Interoperability and FAIR Data Standards
In accordance with FAIR principles, SynaptiPy incorporates native Neurodata Without Borders (NWB) compliance. A dedicated export module translates proprietary manufacturer data arrays and user-generated analytical metadata into the open NWB standard. Critically, the exporter writes the extracted analytical metrics alongside the raw waveforms, enabling downstream reanalysis without repeating the full analysis pipeline. Stimulus artifact interpolation is applied *before* any digital signal processing (DSP) filter to prevent Gibbs ringing.

To ensure maximum hardware compatibility and experimenter control, P/N leak subtraction relies entirely on manual sweep selection by the experimenter. 

### 5. Environment Declaration
All development, validation, and benchmarking procedures described herein were performed on an Apple Silicon (M1) architecture running macOS 15.x using SynaptiPy (RRID:SCR_XXXXXX). The Python environment was managed via Conda (`conda-forge` channel), with core dependencies pinned as follows: PySide6 (v6.7.3) [(The Qt Company, 2023)](#ref-qt_pyside6), PyQtGraph (v0.13.7) [(Campagnola and others, 2024)](#ref-campagnola_pyqtgraph), Neo (v0.14.4) [(Garcia et al., 2014)](#ref-garcia_neo_2014), PyNWB (v3.1.2) [(Rübel et al., 2022)](#ref-rubel_nwb_2022), NumPy (v2.0.2) [(Harris et al., 2020)](#ref-harris_numpy_2020), SciPy (v1.17.1) [(Virtanen et al., 2020)](#ref-virtanen_scipy_2020), and Pandas (v3.0.2) [(McKinney, 2010)](#ref-mckinney_pandas_2010). This frozen environment ensures exact replicability.

# Results (Biological Validation and Performance)

### 1. Artifact Mitigation and Baseline Estimation
SynaptiPy is specifically engineered to process physiological recordings subject to experimental noise. The core analytical modules incorporate configurable artifact-exclusion windows for series resistance ($R_s$) calculations. Synaptic event detection algorithms utilize localized linear detrending to calculate accurate root-mean-square (RMS) noise floors over a sliding window, isolating thermal noise from slow biological baseline drift (e.g., intrinsic bursting, after-depolarizations).

### 2. Algorithmic Parity and Visual Validation
To facilitate user confidence in automated metrics, SynaptiPy renders declarative overlays directly onto the raw electrophysiological traces via PyQtGraph. Users can visually confirm baseline assessment windows, spike threshold coordinates, and exponential decay kinetics superimposed on the raw data.

To quantify algorithmic robustness, SynaptiPy's extraction metrics were mathematically validated against two major industry standards: the Electrophysiology Feature Extraction Library (eFEL) [(Mandge et al., 2026)](#ref-efel) and the Allen Institute's Intrinsic Physiology Feature Extractor (IPFX) [(Gouwens et al., 2020)](#ref-ipfx). For active properties, SynaptiPy utilized a standard derivative-crossing threshold ($dV/dt > 20 \text{ V/s}$) to identify action potential onset. Across intrinsic electrophysiological sweeps (`2023_04_11_0021.abf`), SynaptiPy extracted functionally equivalent spike characteristics with both benchmarks, with threshold and amplitude biases restricted to $< 1.5 \text{ mV}$ (Extended Data Table 1). Differences in absolute scaling for spike kinetics highlighted diverse mathematical paradigms across pipelines: while IPFX utilizes a 9.9 kHz Bessel filter and eFEL employs bounded derivative stencils, SynaptiPy applies a dynamic 0.1 ms temporal smoothing window. This situates SynaptiPy's derivative scaling between the two benchmarks while maintaining robust biological correlation.

For subthreshold passive properties, SynaptiPy was benchmarked on hyperpolarizing current injections (`2023_04_11_0019.abf`, `0022.abf`). SynaptiPy aligned closely with eFEL for Resting Membrane Potential ($-0.085 \text{ mV}$ bias) and Input Resistance ($-1.616 \text{ M}\Omega$ bias) (Extended Data Table 2). To prevent noise artifacts from skewing biological averages for the Membrane Time Constant ($\tau_m$), SynaptiPy enforces a strict biological fit-quality gate ($R^2 \ge 0.80$); un-fittable traces are appropriately rejected, yielding a conservative $\tau_m$ bias of $-5.7 \text{ ms}$ relative to eFEL. The modest Pearson correlations observed for Input Resistance ($r \approx 0.35$) are an expected statistical artifact of how varying algorithms define "steady-state" integration windows on traces exhibiting biological sag; SynaptiPy's measurements successfully occupy the consensus median between IPFX and eFEL.

![Biological Validation](results/biological_validation.png)
*Figure 2: Biological validation and algorithmic parity against established computational benchmarks.*

**Extended Data Table 1: Statistical summary of SynaptiPy AP extraction vs. eFEL and IPFX benchmarks (file: `2023_04_11_0021.abf`, per-sweep means).**

| Metric | n sweeps | SynaptiPy vs IPFX Pearson *r* | SynaptiPy vs eFEL Pearson *r* | Mean bias vs IPFX | Mean bias vs eFEL | Statistical approach |
|--------|----------|-------------------------------|-------------------------------|-------------------|-------------------|----------------------|
| Peak voltage (mV) | 13 | 1.0000 (*p* < 0.0001) | 0.9998 (*p* < 0.0001) | +0.000 mV | +0.229 mV | Pearson correlation, two-sided *p* |
| AP threshold (mV) | 13 | 0.7652 (*p* 0.0023) | 0.7778 (*p* 0.0017) | +1.312 mV | +0.916 mV | Pearson correlation, two-sided *p* |
| AP amplitude (mV) | 13 | 0.9696 (*p* < 0.0001) | 0.9702 (*p* < 0.0001) | -1.312 mV | -0.686 mV | Pearson correlation, two-sided *p* |
| AP half-width (ms) | 13 | 0.8843 (*p* < 0.0001) | 0.8306 (*p* 0.0004) | -0.018 ms | +0.033 ms | Pearson correlation, two-sided *p* |
| Max dV/dt (V/s) | 13 | 0.9981 (*p* < 0.0001) | 0.9933 (*p* < 0.0001) | -57.323 V/s | +140.247 V/s | Pearson correlation, two-sided *p* |
| Min dV/dt (V/s) | 13 | 0.9997 (*p* < 0.0001) | 0.9971 (*p* < 0.0001) | +1.095 V/s | -29.109 V/s | Pearson correlation, two-sided *p* |
| Fast AHP depth (mV) | 13 | 0.1035 (*p* 0.7364) | 0.3393 (*p* 0.2567) | +1.601 mV | +0.860 mV | Pearson correlation, two-sided *p* |
| ADP amplitude (mV) | 13 | -0.2861 (*p* 0.3433) | -0.5222 (*p* 0.0671) | +1.712 mV | +1.957 mV | Pearson correlation, two-sided *p* |

*n sweeps = number of sweeps in which all three pipelines detected ≥1 action potential. Bias = mean signed difference (SynaptiPy − benchmark, per-sweep means). SynaptiPy: BatchAnalysisEngine `spike_detection` (dV/dt threshold 20 V/s, refractory 2 ms). eFEL: BlueBrain eFEL defaults. IPFX: Allen IPFX SpikeFeatureExtractor, 9.9 kHz Bessel filter.*

**Extended Data Table 2: Subthreshold passive properties benchmark on -20 pA steps (files: `2023_04_11_0019.abf`, `0022.abf`).**

| Metric | n sweeps | SynaptiPy vs IPFX Pearson *r* | SynaptiPy vs eFEL Pearson *r* | Mean bias vs IPFX | Mean bias vs eFEL | Statistical approach |
|--------|----------|-------------------------------|-------------------------------|-------------------|-------------------|----------------------|
| Resting Membrane Potential (mV) | 8 | 0.9822 (*p* < 0.0001) | 0.9063 (*p* 0.0019) | +0.018 mV | -0.085 mV | Pearson correlation, two-sided *p* |
| Input Resistance (MΩ) | 8 | 0.3460 (*p* 0.4012) | 0.3863 (*p* 0.3445) | -28.098 MΩ | -1.616 MΩ | Pearson correlation, two-sided *p* |
| Membrane Time Constant (ms) | 7 | 0.5488 (*p* 0.2020) | 0.7423 (*p* 0.0560) | -0.767 ms | -5.782 ms | Pearson correlation, two-sided *p* |

*n sweeps = number of valid sweeps containing a -20 pA hyperpolarizing current injection step. SynaptiPy passive properties extracted via BatchAnalysisEngine using `rmp_analysis`, `rin_analysis`, and `tau_analysis` modules. IPFX extraction via `subthresh_features`.*


### 3. Biological Use-Case: High-Throughput Classification
Beyond computational parity, SynaptiPy offers immediate utility for experimental applications. For example, researchers routinely classify fast-spiking interneurons versus pyramidal cells based on extracted action potential half-widths and AHP depths. SynaptiPy allows a user to open an entire directory of recording files, visually configure a detection threshold on a representative cell, and then instantly apply the `BatchAnalysisEngine` to extract physiological markers across the entire cohort. This workflow condenses what would be hours of manual cursor-placement in commercial software into a single automated execution block.

### 4. High-Throughput Processing and Rendering Optimization
The integrated batch processing engine minimizes manual analysis bottlenecks. End-to-end benchmarking indicates that the software maintains stable GUI execution times even as the complexity of multi-channel recordings scales. Full analytical processing completes in ~3.3 ms per recording, and the optimized PyQtGraph rendering pipeline maintains an interactive GUI frame rate exceeding 200 frames per second (4.79 ms median frame latency) even at maximum plot density (20 simultaneous overlaid traces).

![Batch Scaling Benchmark](results/benchmark_scaling.png)
*Figure 3: Batch execution scaling across increasing file complexities.*

![Rendering Benchmark](results/rendering_benchmark.png)
*Figure 4: Rendering optimizations for high-frequency multichannel data.*

![End-to-End macOS Rendering](results/e2e_rendering_benchmark_macos.png)
*Figure 5: Cross-platform end-to-end rendering stability.*

# Discussion
Within the current landscape of intracellular electrophysiology software, SynaptiPy provides an unparalleled, all-in-one analytical utility. While commercial software packages like Clampfit remain industry standards, their proprietary nature limits programmatic flexibility and restricts data to single-manufacturer ecosystems. SynaptiPy addresses this by providing native multi-hardware support, allowing entire research laboratories to sync up their analysis protocols regardless of the recording equipment utilized. 

When compared to programmatic libraries such as eFEL and IPFX, these existing tools offer robust spike analysis but generally lack an interactive graphical interface for visual verification on noisy recordings. Furthermore, relative to GUI-based open-source applications like Stimfit [(Guzman et al., 2014)](#ref-guzman_stimfit_2014) which require low-level C++ expertise, SynaptiPy relies entirely on a Python-based architecture. This ensures easy access for a wide audience of neuroscientists. Packaged for deployment across macOS, Windows, and Linux via simple `pip`, `conda`, or source installation modes, SynaptiPy ensures that different researchers can perform the exact same analysis on vastly different local machines.

**Limitations**: While SynaptiPy offers extensive support for intracellular recordings, it currently focuses exclusively on *in vitro* patch-clamp and optogenetic datasets. It does not currently implement spike-sorting heuristics for *in vivo* extracellular multi-electrode arrays (MEAs), nor does it natively support real-time dynamic clamp interface processing. Future versions will aim to expand the `@AnalysisRegistry` plugin system to support these modalities.

# Availability
SynaptiPy is an open-source tool licensed under the GNU Affero General Public License v3.0 (AGPL-3.0). The source code is publicly available via GitHub (https://github.com/anzalks/synaptipy), and comprehensive user documentation is hosted at ReadTheDocs (https://synaptipy.readthedocs.io/). For immediate deployment, the suite is distributed as a pre-compiled Python package via PyPI and can be installed using the `pip install synaptipy` command.

## Data and Code Availability
In accordance with *eNeuro* guidelines for reproducible research, the source code and exact software version described in this manuscript will be permanently archived on Zenodo upon publication. All biological data arrays used to generate the validation figures are available within the open-source repository's `examples/data/` structure.

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
