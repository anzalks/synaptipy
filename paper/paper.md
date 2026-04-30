---
title: 'SynaptiPy: An Open-Source Electrophysiology Visualization and Analysis Suite'
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
---

<!--
=============================================================================
MANUSCRIPT TODO - Pre-submission checklist (remove this block before submission)
=============================================================================

A) BENCHMARK FIGURES (Figures 1, 2, 3 are placeholders - MUST be regenerated):
   - [ ] Run `python scripts/generate_benchmarks.py` to produce
         paper/results/benchmark_scaling.png,
         paper/results/rendering_benchmark.png,
         paper/results/e2e_rendering_benchmark_macos.png
   - [ ] Verify each figure has axis labels, units, and a legend.
   - [ ] Replace placeholder images in the Results section with final versions.

B) BIOLOGICAL VALIDATION FIGURE (placeholder text in Results section 2):
   - [ ] Generate a scatter plot comparing SynaptiPy AP threshold and R_in
         values against eFEL and Clampfit using an open dataset
         (recommended: Allen Cell Types Database, AIBS, https://celltypes.brain-map.org/).
     Steps:
       1. Download a set of Allen Cell Types NWC/ABF files.
       2. Run SynaptiPy batch engine on the files.
       3. Run eFEL (https://github.com/BlueBrain/eFEL) on the same files.
       4. Produce a Bland-Altman or scatter plot of SynaptiPy vs eFEL/Clampfit.
       5. Save PNG to paper/results/biological_validation_scatter.png.
   - [ ] Replace the `![Biological Validation]` placeholder in Results section 2
         with the generated figure and its caption.
   - [ ] Report exact numeric agreement statistics (mean bias, limits of
         agreement, Pearson r) in the main text rather than the image alone.

C) HARD PERFORMANCE NUMBERS (to replace figure-only benchmark evidence):
   - [ ] Add a sentence reporting: median per-file batch time (ms),
         peak RAM usage (MB) for a 100-sweep ABF, and GUI frame rate (fps)
         at maximum plot density. Run `python scripts/benchmark_e2e.py --report`
         and copy results here.

D) ZENODO DOI:
   - [ ] Archive the repository on Zenodo (https://zenodo.org/) by creating
         a release tag and enabling the GitHub-Zenodo integration.
   - [ ] Replace `[Zenodo DOI Here]` in the Software Availability section
         with the real DOI badge, e.g. `[![DOI](https://zenodo.org/badge/DOI/...)](...)`.

E) BIBLIOGRAPHY (`paper.bib`):
   - [ ] Compile all references cited in the text into paper/paper.bib.
   - [ ] Required entries (at minimum):
         - Neo library (Garcia et al., 2014)
         - PyNWB / NWB standard (Rubel et al., 2022)
         - eFEL (cite BlueBrain/eFEL repository)
         - Stimfit (Guzman et al., 2014)
         - pyABF (Harden, 2020)
         - SciPy (Virtanen et al., 2020)
         - NumPy (Harris et al., 2020)
         - PySide6 / Qt
   - [ ] Verify all `@cite` keys in the text match entries in paper.bib.

=============================================================================
END TODO
=============================================================================
-->

# Abstract
SynaptiPy is an open-source, Python-based software suite developed for the visualization and automated analysis of intracellular electrophysiology data. It provides a modular, metadata-driven graphical user interface (GUI) designed to resolve the methodological divide between inflexible commercial software and complex programmatic libraries. SynaptiPy supports over 15 distinct analytical modules encompassing intrinsic passive properties, single-spike kinetics, short-term synaptic plasticity, and optogenetic mapping. The application natively supports multiple proprietary file formats via the `neo` library and integrates Neurodata Without Borders (NWB) export capabilities to facilitate open-science reproducibility.

# Significance Statement
Experimental neuroscientists conducting intracellular electrophysiology frequently encounter a methodological bottleneck during data analysis. They must currently choose between proprietary GUI applications, which offer limited flexibility for automated high-throughput workflows, and programmatic libraries, which require advanced coding expertise and lack interactive visual validation. SynaptiPy bridges this gap by providing the analytical capabilities of modern Python libraries within a dynamic, accessible graphical environment. This enables researchers to perform rigorous, automated analysis across large experimental cohorts while maintaining complete algorithmic transparency and without requiring extensive programming knowledge.

# Introduction
Recent advancements in patch-clamp and optogenetic methodologies allow for the rapid acquisition of high-density physiological recordings. However, the manual quantification of these parameters remains highly time-consuming and susceptible to user bias. While several open-source initiatives have provided programmatic solutions, these tools are often tailored toward computational modelers rather than experimentalists. SynaptiPy addresses this limitation by offering a highly maintainable software application that prioritizes interactive visual validation, automated batch processing, and robust computational stability for wet-lab researchers.

# Materials and Methods (Software Architecture)

### 1. Metadata-Driven Architecture and Extensibility
To maximize long-term extensibility, SynaptiPy utilizes a decoupled, metadata-driven architecture. Rather than utilizing hard-coded user interfaces for individual analytical functions, the software employs a centralized `@AnalysisRegistry`. Researchers can implement custom algorithms via standard Python functions, which the application automatically parses to dynamically generate the required GUI elements, interactive plotting bounds, and batch-processing hooks. This abstraction allows users to expand the software’s capabilities without requiring familiarity with the underlying PySide6/Qt framework.

### 2. Automated Testing and Software Maintenance
A common limitation of academic software is dependency drift, where unmonitored updates to third-party libraries alter underlying calculations. To ensure long-term reproducibility, SynaptiPy is supported by a continuous integration and continuous deployment (CI/CD) pipeline with strict semantic dependency constraints. Furthermore, the repository employs baseline regression testing-executing the core analytical pipeline against raw experimental datasets (`.abf`, `.wcp`) during automated checks-to verify that upstream updates to core libraries (`SciPy`, `NumPy`) do not introduce silent mathematical deviations.

### 3. GUI-to-Batch Parameter Serialization

Interactive parameter adjustments made in the SynaptiPy GUI are fully reproducible in the headless `BatchAnalysisEngine`. Every analysis widget (spin-boxes, draggable region handles, combo-boxes) maps to a named entry in the `ui_params` list declared alongside the `@AnalysisRegistry.register(...)` decorator. When the user clicks **Run Analysis**, `_gather_analysis_parameters()` reads the current widget values into a plain Python dictionary:

```python
params = {"stim_start_time": 0.200, "fit_duration": 0.300, "model": "mono"}
```

This dictionary is stored in `SessionManager` and serialized to JSON when the user saves a session file. The `BatchAnalysisEngine` accepts the same dictionary format and invokes the identical registered wrapper function, ensuring that a batch result is mathematically equivalent to the GUI result. Draggable region handles are two-way linked to their spin-box counterparts via Qt signals; the spin-box value-not the graphical position-is the canonical parameter that enters the analysis. The preprocessing pipeline (filters, baseline subtraction) is passed to the batch engine via `preprocessing_settings`, applying the same `ProcessingPipeline` that the GUI uses on the visually validated trace.

### 4. Interoperability and FAIR Data Standards
In accordance with FAIR (Findable, Accessible, Interoperable, and Reusable) data principles, SynaptiPy incorporates native Neurodata Without Borders (NWB) compliance. A dedicated export module translates proprietary manufacturer data arrays and user-generated analytical metadata into the open NWB standard, thereby streamlining data deposition and facilitating cross-laboratory reproducibility. Critically, SynaptiPy does not merely package raw voltage traces: the exporter writes the extracted analytical metrics -- including action potential thresholds, input resistance ($R_{\text{in}}$), membrane time constants, and synaptic kinetics -- as structured NWB ``TimeSeries`` and ``IntracellularElectrophysiology`` table entries alongside the raw waveforms, enabling downstream reanalysis without repeating the full analysis pipeline. Stimulus artifact interpolation is applied *before* any digital signal processing (DSP) filter in the preprocessing pipeline; performing interpolation upstream of filtering prevents Gibbs ringing that would otherwise smear transient energy across the waveform and corrupt kinetic measurements, a common flaw in single-step electrophysiology analysis workflows.

P/N leak subtraction relies entirely on *manual sweep selection* by the experimenter. The user explicitly designates which sweeps serve as sub-threshold P/N references via the GUI; automated inference of leak-only sweeps is intentionally not implemented because amplifier protocols vary too widely across laboratories and formats (Axon ABF, WinWCP, CED) for a heuristic to reliably distinguish true leak sweeps from test pulses. This design decision ensures accurate leak isolation regardless of the recording hardware or stimulus template.

# Results (Biological Validation and Performance)

### 1. Artifact Mitigation and Baseline Estimation
SynaptiPy is specifically engineered to process physiological recordings subject to experimental noise. The core analytical modules incorporate configurable artifact-exclusion windows for series resistance ($R_s$) calculations, preventing capacitance misestimations. Additionally, the synaptic event detection algorithms utilize localized linear detrending to calculate accurate root-mean-square (RMS) noise floors, isolating thermal noise from slow baseline drift. The RMS noise floor is computed over a sliding window of length $w = \lfloor 50\,\text{ms} / \Delta t \rfloor$ samples that advances in non-overlapping steps across the pre-event region. Within each window the linear trend is removed by ordinary least-squares regression before computing the RMS, ensuring that slow biological drift (e.g., intrinsic bursting, after-depolarizations) does not inflate the noise estimate. Windows containing candidate events are identified by a preliminary amplitude threshold and excluded from the noise calculation, so physiological transients do not bias the floor estimate.

### 2. Algorithmic Transparency and Visual Validation
To facilitate user confidence in automated metrics, SynaptiPy relies heavily on visual validation. The software renders declarative overlays directly onto the raw electrophysiological traces via PyQtGraph. Users can visually confirm baseline assessment windows, spike threshold detection coordinates, and exponential decay kinetics superimposed on the raw data (e.g., excitatory postsynaptic potentials), ensuring that the algorithmic outputs accurately reflect the underlying biology.

*(biological validation figure, e.g., `![Biological Validation](docs/tutorial/screenshots/analyser_intrinsic_properties_tau_time_constant.png)`)*

### 3. High-Throughput Processing and Rendering Optimization
The integrated batch processing engine minimizes manual analysis bottlenecks, allowing for the rapid extraction of intrinsic properties and synaptic events across extensive experimental cohorts. To support this high-throughput capability, SynaptiPy utilizes significant rendering optimizations. End-to-end benchmarking indicates that the software maintains stable GUI execution times and smooth navigational frame rates even as the complexity and density of the multi-channel recordings scale:

![Batch Scaling Benchmark](results/benchmark_scaling.png)
*Figure 1: Batch execution scaling across increasing file complexities.*

![Rendering Benchmark](results/rendering_benchmark.png)
*Figure 2: Rendering optimizations for high-frequency multichannel data.*

![End-to-End macOS Rendering](results/e2e_rendering_benchmark_macos.png)
*Figure 3: Cross-platform end-to-end rendering stability.*

# Discussion (Comparison to Existing Tools)
Within the current landscape of intracellular electrophysiology software, SynaptiPy provides a distinct analytical utility:
* **Commercial Software (e.g., Clampfit):** While considered an industry standard, proprietary applications offer limited programmatic flexibility for high-throughput batch analysis. SynaptiPy provides comparable analytical rigor alongside comprehensive automation and an open-source (AGPL-3.0) license.
* **Programmatic Libraries (e.g., eFEL, pyABF):** Libraries such as the Electrophysiology Feature Extraction Library (eFEL) offer robust programmatic spike analysis but lack a graphical interface for visual verification. Similarly, `pyABF` provides excellent file I/O capabilities but requires users to construct independent analysis pipelines. SynaptiPy integrates these programmatic strengths into a cohesive visual platform.
* **GUI-Based Open-Source Applications (e.g., Stimfit):** Stimfit provides a highly respected C++ application; however, extending its functionality requires low-level programming expertise. SynaptiPy relies entirely on a Python-based architecture for simplified extensibility and includes native integration with modern NWB standards.

# Software Availability
* **License:** GNU Affero General Public License v3.0 (AGPL-3.0)
* **Operating Systems:** Windows, macOS, Linux
* **Source Code:** [https://github.com/anzalks/synaptipy](https://github.com/anzalks/synaptipy)
* **Archived Release:** [Zenodo DOI Here]
* **Documentation:** [https://synaptipy.readthedocs.io/](https://synaptipy.readthedocs.io/)

# References
*(References will be compiled via paper.bib)*