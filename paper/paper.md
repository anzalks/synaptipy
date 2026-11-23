---
title: 'SynaptiPy: An open-source, plugin-driven software bridging interactive visualization and automated batch processing in electrophysiology'
short_title: 'SynaptiPy'
tags:
  - Python
  - neuroscience
  - electrophysiology
  - patch-clamp
  - optogenetics
  - GUI
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
SynaptiPy is an open-source, all-in-one Python software developed for the visualization and automated analysis of intracellular electrophysiology data. It addresses the methodological divide between inflexible proprietary software and complex programmatic libraries by providing a responsive PyQt-based graphical user interface (GUI). Distributed across three major operating systems (macOS, Windows, Linux) via standard installation modes (`pip`, source, and standalone binaries), SynaptiPy natively incorporates broad amplifier-agnostic data parsing (e.g., Axon ABF, HEKA, WCP, NWB) via the `neo` library (Garcia et al., 2014). This multi-format compatibility allows diverse research groups to standardize their analytical pipelines regardless of the acquisition software used. Algorithmic accuracy was validated against standardized intracellular waveforms from adult male and female mouse cortical neurons (Allen Institute Cell Types Database). SynaptiPy introduces a metadata-driven plugin architecture that enables researchers to integrate custom algorithms as interactive GUI modules, effectively bridging the gap between exploratory visual inspection and headless batch processing.

# Significance Statement
Analyzing intracellular electrophysiology data presents a persistent methodological bottleneck; researchers frequently face a trade-off between rigid proprietary applications that limit automation and code-heavy libraries that require advanced programming expertise. This software divide creates equipment-based data silos and hinders reproducible research. SynaptiPy resolves this challenge by providing an open-source, unified analysis environment. By integrating interactive visual validation with automated batch processing and native multi-format compatibility, it enables laboratories to standardize analytical protocols regardless of the recording software they use. Ultimately, this tool eliminates proprietary silos, democratizes data analysis, and drives transparency and open science across the neuroscience community.

# Introduction
The automated analysis of electrophysiological data has a rich history of foundational tools that have vastly simplified researchers' workflows. Commercial applications such as **pClamp (Clampfit)** and **Axograph** established the gold standard for reliable visual inspection. Concurrently, community-driven environments like **Neuromatic** (Rothman and Silver, 2018) provided researchers with immense algorithmic extensibility within Igor Pro, while modern open-source applications like **WinWCP** (Dempster, 1997), **Stimfit** (Guzman et al., 2014), and **EasyElectrophysiology** (www.easyelectrophysiology.com) brought sophisticated analytics to standalone desktop environments.

However, as the field increasingly adopts open-source Python-based data science ecosystems, a methodological friction has emerged. Researchers often face a difficult transition between these established graphical applications and headless Python libraries (e.g., IPFX, eFEL). While recent Python-based visualizers like **PatchView** (Hu and Jiang, 2022) provide excellent standalone interfaces, they operate as pre-packaged applications that isolate users from integrating custom analysis workflows. Conversely, headless libraries require advanced scripting expertise and break the interactive visual validation loop that experimentalists rely upon.

SynaptiPy was designed specifically for experimentalists to address these limitations by prioritizing three core pillars: cross-platform accessibility, acquisition-agnostic data parsing, and decoupled plugin extensibility. Deploying natively on macOS, Windows, and Linux provides the stability needed to run identical analyses across diverse hardware. By leveraging community standards such as Neo (Garcia et al., 2014) to natively parse dozens of proprietary file formats, the application enables multi-lab collaborations to standardize pipelines regardless of the underlying amplifier. Driven by auto-detecting and a hot-reload plugin system, SynaptiPy allows users to seamlessly convert standard Python functions into interactive GUI modules, ensuring that graphical configurations and headless batch scripts share the exact same analytical code.

# Materials and Methods

## Metadata-Driven Plugin Architecture 
To maximize long-term extensibility, SynaptiPy employs a decoupled, metadata-driven architecture. Rather than relying on hard-coded user interfaces for individual analytical functions, the software is built around a centralized `@AnalysisRegistry` decorator. Researchers can implement custom algorithms via standard Python functions. By passing explicit keyword arguments (e.g., `ui_params`) into the registration decorator, users define parameter bounds and data types. The application then dynamically maps these inputs to corresponding Qt frontend widgets (e.g., `SpinBox`, `ComboBox`), ensuring custom coding logic is immediately accessible within the graphical interface.

![Figure 1](figures/figure_01.png)

## Multi-Format Parsing and GUI-to-Batch Parameter Serialization 
SynaptiPy leverages the Neo library (Garcia et al., 2014) to parse proprietary software files. Interactive parameter adjustments made in the GUI are fully reproducible in the headless `BatchAnalysisEngine`. Every analysis widget maps to a named entry in the `ui_params` list. When the user saves a session, these parameters are serialized to JSON format. The `BatchAnalysisEngine` accepts this identical dictionary format, ensuring that a batch result is mathematically equivalent to the interactive GUI result.

## Experimental Design and Statistical Analysis 
To quantify algorithmic reliability, SynaptiPy's feature-extraction metrics were validated against standardized intracellular waveforms obtained from the Allen Institute Cell Types Database. The automated pipeline targeted an initial cohort of $n = 6$ adult male and female mouse cortical cells. From the Neurodata Without Borders (NWB) data, step-protocol information was extracted and processed using SynaptiPy to confirm consistency with established analytical benchmarks.

## Code Accessibility
The code/software described in the paper is freely available online at [URL redacted for double-blind review]. The code is available as Extended Data 1. SynaptiPy is licensed under the GNU Affero General Public License v3.0 (AGPL-3.0). All analyses were performed on an Apple MacBook Pro (Apple M3 Pro, 18 GB RAM) running macOS 15.5 (Sequoia) and verified on Ubuntu 22.04 (x86_64). The Python environment was managed via miniconda (`conda-forge` channel), with core dependencies pinned as follows: PySide6 (v6.7.3), PyQtGraph (v0.13.7), Neo (v0.14.4) (Garcia et al., 2014), NumPy (v2.0.2) (Harris et al., 2020), SciPy (v1.17.1) (Virtanen et al., 2020), and Pandas (v3.0.2) (McKinney, 2010).

# Results

The primary objective of SynaptiPy is to provide a unified analytical pipeline for intracellular electrophysiology that integrates interactive visual exploration with automated batch processing. The software encompasses data parsing, signal conditioning, feature extraction, and modular extensibility via a plugin architecture. In practice, a standard user workflow consists of three stages: data ingestion, visual configuration, and batch execution. First, native data parsing enables direct loading of proprietary file formats (e.g., ABF, WCP, NWB, etc.). Second, users configure and validate signal conditioning and feature extraction parameters on representative recordings through the graphical user interface (GUI). Finally, these optimized parameters are serialized and applied programmatically across full datasets utilizing a headless processing engine. This architecture ensures that interactive parameter selection translates directly to standardized, reproducible high-throughput analysis, without requiring advanced programming expertise. Comprehensive step-by-step tutorials detailing this workflow are available in the official documentation at https://synaptipy.readthedocs.io/en/latest/.

## Signal Conditioning and Dynamic Baseline Estimation 
Before feature extraction, SynaptiPy employs a robust signal-conditioning pipeline (Colquhoun and Sigworth, 1995; Widmann et al., 2015) to mitigate experimental noise. For dynamic baseline estimation, the algorithm utilises localized detrending using a rolling median filter over the target epoch. To determine precise thresholds for active and miniature synaptic event detection (Clements and Bekkers, 1997; Hampel, 1974), the pipeline isolates a minimum-variance sliding window to calculate a quiescent root-mean-square (RMS) noise floor. This approach mathematically isolates random high-frequency thermal noise from slow biological baseline drift, ensuring highly reliable feature extraction across variable recording conditions.

## Biophysically Accurate Passive Property Extraction 
To accurately capture subthreshold membrane dynamics, SynaptiPy abandons naive fixed-window subtractions in favor of biophysically representative calculations (Hamill et al., 1981; Rall, 1969; Taylor, 2012). Specifically, the passive properties module actively separates peak input resistance $R_{in}$ from steady-state $R_{in}$. This separation effectively isolates hyperpolarization-activated cyclic nucleotide-gated $I_h$ channel conductance (Robinson and Siegelbaum, 2003), allowing for precise quantification of the voltage sag ratio. Because $I_h$ activation kinetics vary significantly across cell types and experimental temperatures, this analysis is exposed as a built-in plugin with dedicated UI controls, enabling experimentalists to dynamically adjust baseline, peak, and steady-state extraction windows to match specific biological realities while maintaining interactive visual validation.

## Algorithmic Parity against Computational Benchmarks
SynaptiPy successfully processed the targeted datasets via the `BatchAnalysisEngine` and supports archival export to Neurodata Without Borders (NWB) 2.x (Rubel et al., 2022). To validate the feature extraction pipeline, the results were statistically compared with two established standards in the field: the Electrophysiology Feature Extraction Library (eFEL) (Mandge et al., 2026) and the Allen Institute's Intrinsic Physiology Feature Extractor (IPFX) (Gouwens et al., 2019).

For active properties, SynaptiPy utilized a standard dynamic derivative-crossing threshold ($dV/dt > 20$ V/s; Hodgkin and Huxley, 1952; Bean, 2007; Jenerick, 1963), while evoked and paired-pulse protocols incorporate iterative residual decay subtraction (Zucker and Regehr, 2002; Thanawala and Regehr, 2013). The resulting measurements for action potential onset, amplitudes, and phase-plane dynamics demonstrated mathematical agreement with both libraries (Table 1, Figure 2). For subthreshold properties, SynaptiPy's dynamic extraction algorithms yielded steady-state input resistance, resting membrane potential, and time constant estimates that closely matched the results of eFEL and IPFX values (Table 2).

<!-- TABLES_START -->

**Table 2-1: Statistical summary of SynaptiPy AP extraction vs. eFEL and IPFX benchmarks (Allen Dataset, per-sweep means).**

| Metric | SynaptiPy vs IPFX Pearson *r* | Mean bias vs IPFX | LoA vs IPFX | SynaptiPy vs eFEL Pearson *r* | Mean bias vs eFEL | LoA vs eFEL |
|--------|-------------------------------|-------------------|-------------|-------------------------------|-------------------|-------------|
| AP threshold (mV) | 0.9765 (*p* = 5.95e-29, *n* = 43)<sup>a</sup> | +0.274 mV | [-0.67, +1.21] mV | 0.9799 (*p* = 2.48e-30, *n* = 43)<sup>b</sup> | -0.325 mV | [-1.17, +0.52] mV |
| AP amplitude (mV) | 0.9980 (*p* = 5.46e-51, *n* = 43)<sup>c</sup> | -0.254 mV | [-1.24, +0.73] mV | 0.9997 (*p* = 2.53e-67, *n* = 43)<sup>d</sup> | +0.296 mV | [-0.10, +0.69] mV |
| AP half-width (ms) | 0.9876 (*p* = 1.41e-34, *n* = 43)<sup>e</sup> | -0.095 ms | [-0.19, -0.00] ms | 0.9995 (*p* = 3.05e-63, *n* = 43)<sup>f</sup> | +0.001 ms | [-0.01, +0.01] ms |
| Max dV/dt (V/s) | 0.9946 (*p* = 6.77e-42, *n* = 43)<sup>g</sup> | -9.436 V/s | [-22.07, +3.20] V/s | 0.9829 (*p* = 9.71e-32, *n* = 43)<sup>h</sup> | -37.288 V/s | [-77.53, +2.95] V/s |
| AP Delay (Time to first spike) (ms) | 1.0000 (*p* = 0.00e+00, *n* = 43)<sup>i</sup> | -0.000 ms | [-0.00, +0.00] ms | 1.0000 (*p* = 1.51e-153, *n* = 43)<sup>j</sup> | -0.002 ms | [-0.01, +0.01] ms |
| Upstroke/Downstroke Ratio | 0.9998 (*p* = 1.56e-70, *n* = 43)<sup>k</sup> | -0.083 Ratio | [-0.14, -0.02] Ratio | 0.9990 (*p* = 4.50e-57, *n* = 43)<sup>l</sup> | -0.220 Ratio | [-0.32, -0.12] Ratio |
| Fast AHP depth (mV) | 0.9886 (*p* = 2.41e-35, *n* = 43)<sup>m</sup> | +1.000 mV | [-2.48, +4.49] mV | 0.9847 (*p* = 2.13e-27, *n* = 36)<sup>n</sup> | +1.181 mV | [-2.60, +4.96] mV |
| ADP amplitude (mV) | 0.9061 (*p* = 0.0939, *n* = 4)<sup>o</sup> | -0.110 mV | [-0.25, +0.03] mV | 0.7584 (*p* = 0.0001, *n* = 20)<sup>p</sup> | +5.048 mV | [-8.16, +18.25] mV |
| Mean Firing Frequency (Hz) | 1.0000 (*p* = 6.93e-92, *n* = 43)<sup>q</sup> | -0.047 Hz | [-0.46, +0.37] Hz | 0.4501 (*p* = 0.0025, *n* = 43)<sup>r</sup> | -22.496 Hz | [-111.15, +66.16] Hz |
| Spike Frequency Adaptation | 0.9999 (*p* = 1.97e-52, *n* = 30)<sup>s</sup> | -0.000 Ratio | [-0.00, +0.00] Ratio | 0.8215 (*p* = 8.43e-08, *n* = 28)<sup>t</sup> | +0.012 Ratio | [-0.02, +0.04] Ratio |

*All correlations are Pearson's r (two-sided) with exact *p*-values and valid pair counts reported across *n* = 43 sweeps nested within *N* = 6 independent cells (cell-clustered mean correlations and non-parametric Spearman *rho* are reported in the Statistical Table). Bias = mean signed difference (SynaptiPy minus benchmark, per-sweep means). LoA = 95% Bland-Altman limits of agreement. SynaptiPy: BatchAnalysisEngine spike_detection (dV/dt threshold 20 V/s, refractory 2 ms). eFEL: BlueBrain eFEL at native sampling interval. IPFX: Allen IPFX SpikeFeatureExtractor, 9.9 kHz Bessel filter. Superscript letters refer to the statistical table. N/A = no direct benchmark equivalent.*

**Table 2-2: Subthreshold passive properties benchmark on hyperpolarizing steps (Allen Dataset).**

| Metric | Valid *N* (eFEL / IPFX) | SynaptiPy vs eFEL Pearson *r* | Mean bias vs eFEL | LoA vs eFEL | SynaptiPy vs IPFX Pearson *r* | Mean bias vs IPFX | LoA vs IPFX |
|--------|-------------------------|-------------------------------|-------------------|-------------|-------------------------------|-------------------|-------------|
| Resting Membrane Potential (mV) | 34 | 0.9997 (*p* = 3.38e-52)<sup>u</sup> | +0.010 mV | [-0.10, +0.12] mV | 1.0000 (*p* = 3.76e-91)<sup>v</sup> | -0.001 mV | [-0.01, +0.01] mV |
| Input Resistance - Steady-State (MOhm) | 34 | 0.9985 (*p* = 4.11e-42)<sup>w</sup> | -1.232 MOhm | [-8.01, +5.55] MOhm | 0.9777 (*p* = 2.97e-23)<sup>x</sup> | -14.390 MOhm | [-38.71, +9.93] MOhm |
| Input Resistance - Peak (MOhm) | 34 | 0.9988 (*p* = 1.34e-43)<sup>y</sup> | +4.203 MOhm | [-1.88, +10.28] MOhm | 0.9809 (*p* = 2.56e-24)<sup>z</sup> | -10.337 MOhm | [-32.61, +11.93] MOhm |
| Membrane Time Constant (ms) | 34 | 0.9861 (*p* = 1.64e-26)<sup>aa</sup> | -1.053 ms | [-4.43, +2.32] ms | 0.9873 (*p* = 3.62e-27)<sup>ab</sup> | -0.496 ms | [-3.47, +2.48] ms |
| Sag Percentage (%) | 34 | 0.9961 (*p* = 2.60e-35)<sup>ac</sup> | -0.848 % | [-2.00, +0.30] % | 0.9969 (*p* = 6.01e-37)<sup>ad</sup> | +0.217 % | [-0.79, +1.23] % |

*All correlations are Pearson's r (two-sided) with exact *p*-values reported across sweeps from *N* = 6 independent cells (cell-clustered mean correlations and Spearman *rho* are reported in the Statistical Table). LoA = 95% Bland-Altman limits of agreement (mean +/- 1.96 SD of sweep-level differences). Steady-State Rin uses the terminal step steady-state deflection; Peak Rin uses maximum hyperpolarizing deflection. Superscript letters refer to the statistical table. N/A = no direct benchmark equivalent.*


**Statistical Table**

| | Data structure | Type of test | Statistical value |
|---|---|---|---|
| a | Non-normal paired differences | Pearson + Spearman correlation (two-sided, *n* = 43 sweeps) | *r* = 0.9765 (*p* = 5.95e-29); Spearman *rho* = 0.9479 (*p* = 5.57e-22); Shapiro-Wilk *W* = 0.6030 (*p* = 1.45e-09); cell-mean *r* = 0.9919 |
| b | Non-normal paired differences | Pearson + Spearman correlation (two-sided, *n* = 43 sweeps) | *r* = 0.9799 (*p* = 2.48e-30); Spearman *rho* = 0.9547 (*p* = 3.39e-23); Shapiro-Wilk *W* = 0.3789 (*p* = 2.93e-12); cell-mean *r* = 0.9972 |
| c | Non-normal paired differences | Pearson + Spearman correlation (two-sided, *n* = 43 sweeps) | *r* = 0.9980 (*p* = 5.46e-51); Spearman *rho* = 0.9946 (*p* = 6.55e-42); Shapiro-Wilk *W* = 0.6277 (*p* = 3.28e-09); cell-mean *r* = 0.9994 |
| d | Non-normal paired differences | Pearson + Spearman correlation (two-sided, *n* = 43 sweeps) | *r* = 0.9997 (*p* = 2.53e-67); Spearman *rho* = 0.9985 (*p* = 2.68e-53); Shapiro-Wilk *W* = 0.9331 (*p* = 0.0149); cell-mean *r* = 0.9999 |
| e | Non-normal paired differences | Pearson + Spearman correlation (two-sided, *n* = 43 sweeps) | *r* = 0.9876 (*p* = 1.41e-34); Spearman *rho* = 0.9833 (*p* = 5.96e-32); Shapiro-Wilk *W* = 0.8319 (*p* = 1.88e-05); cell-mean *r* = 0.9877 |
| f | Non-normal paired differences | Pearson + Spearman correlation (two-sided, *n* = 43 sweeps) | *r* = 0.9995 (*p* = 3.05e-63); Spearman *rho* = 0.9975 (*p* = 7.69e-49); Shapiro-Wilk *W* = 0.6958 (*p* = 3.83e-08); cell-mean *r* = 1.0000 |
| g | Non-normal paired differences | Pearson + Spearman correlation (two-sided, *n* = 43 sweeps) | *r* = 0.9946 (*p* = 6.77e-42); Spearman *rho* = 0.9890 (*p* = 1.22e-35); Shapiro-Wilk *W* = 0.8066 (*p* = 5.00e-06); cell-mean *r* = 0.9964 |
| h | Non-normal paired differences | Pearson + Spearman correlation (two-sided, *n* = 43 sweeps) | *r* = 0.9829 (*p* = 9.71e-32); Spearman *rho* = 0.9819 (*p* = 3.04e-31); Shapiro-Wilk *W* = 0.8287 (*p* = 1.58e-05); cell-mean *r* = 0.9781 |
| i | Zero-variance paired differences | Pearson correlation (two-sided, *n* = 43 sweeps) | *r* = 1.0000 (*p* = 0.00e+00); Spearman *rho* = 1.0000 (*p* = 0.00e+00); Shapiro-Wilk N/A (exact identity); cell-mean *r* = 1.0000 |
| j | Non-normal paired differences | Pearson + Spearman correlation (two-sided, *n* = 43 sweeps) | *r* = 1.0000 (*p* = 1.51e-153); Spearman *rho* = 1.0000 (*p* = 0.00e+00); Shapiro-Wilk *W* = 0.8358 (*p* = 2.34e-05); cell-mean *r* = 1.0000 |
| k | Non-normal paired differences | Pearson + Spearman correlation (two-sided, *n* = 43 sweeps) | *r* = 0.9998 (*p* = 1.56e-70); Spearman *rho* = 0.9964 (*p* = 1.63e-45); Shapiro-Wilk *W* = 0.8102 (*p* = 6.00e-06); cell-mean *r* = 0.9999 |
| l | Non-normal paired differences | Pearson + Spearman correlation (two-sided, *n* = 43 sweeps) | *r* = 0.9990 (*p* = 4.50e-57); Spearman *rho* = 0.9902 (*p* = 1.14e-36); Shapiro-Wilk *W* = 0.9034 (*p* = 0.0016); cell-mean *r* = 0.9993 |
| m | Non-normal paired differences | Pearson + Spearman correlation (two-sided, *n* = 43 sweeps) | *r* = 0.9886 (*p* = 2.41e-35); Spearman *rho* = 0.9479 (*p* = 5.57e-22); Shapiro-Wilk *W* = 0.9453 (*p* = 0.0404); cell-mean *r* = 0.9934 |
| n | Normal paired differences | Pearson correlation (two-sided, *n* = 36 sweeps) | *r* = 0.9847 (*p* = 2.13e-27); Spearman *rho* = 0.9207 (*p* = 1.87e-15); Shapiro-Wilk *W* = 0.9719 (*p* = 0.4811); cell-mean *r* = 0.9799 |
| o | Small sample (*n* < 8) | Pearson correlation (two-sided, *n* = 4 sweeps) | *r* = 0.9061 (*p* = 0.0939); Spearman *rho* = 0.4000 (*p* = 0.6000); Shapiro-Wilk N/A |
| p | Normal paired differences | Pearson correlation (two-sided, *n* = 20 sweeps) | *r* = 0.7584 (*p* = 0.0001); Spearman *rho* = 0.6135 (*p* = 0.0040); Shapiro-Wilk *W* = 0.9133 (*p* = 0.0738); cell-mean *r* = 0.9188 |
| q | Non-normal paired differences | Pearson + Spearman correlation (two-sided, *n* = 43 sweeps) | *r* = 1.0000 (*p* = 6.93e-92); Spearman *rho* = 0.9997 (*p* = 1.37e-67); Shapiro-Wilk *W* = 0.2189 (*p* = 8.68e-14); cell-mean *r* = 1.0000 |
| r | Non-normal paired differences | Pearson + Spearman correlation (two-sided, *n* = 43 sweeps) | *r* = 0.4501 (*p* = 0.0025); Spearman *rho* = 0.4187 (*p* = 0.0052); Shapiro-Wilk *W* = 0.5265 (*p* = 1.40e-10); cell-mean *r* = 0.9373 |
| s | Non-normal paired differences | Pearson + Spearman correlation (two-sided, *n* = 30 sweeps) | *r* = 0.9999 (*p* = 1.97e-52); Spearman *rho* = 0.9991 (*p* = 4.76e-40); Shapiro-Wilk *W* = 0.2343 (*p* = 2.05e-11); cell-mean *r* = 1.0000 |
| t | Non-normal paired differences | Pearson + Spearman correlation (two-sided, *n* = 28 sweeps) | *r* = 0.8215 (*p* = 8.43e-08); Spearman *rho* = 0.8084 (*p* = 1.95e-07); Shapiro-Wilk *W* = 0.8261 (*p* = 0.0003); cell-mean *r* = 0.8755 |
| u | Non-normal paired differences | Pearson + Spearman correlation (two-sided, *n* = 34 sweeps) | *r* = 0.9997 (*p* = 3.38e-52); Spearman *rho* = 0.9976 (*p* = 1.47e-38); Shapiro-Wilk *W* = 0.9189 (*p* = 0.0150); cell-mean *r* = 0.9999 |
| v | Normal paired differences | Pearson correlation (two-sided, *n* = 34 sweeps) | *r* = 1.0000 (*p* = 3.76e-91); Spearman *rho* = 0.9997 (*p* = 5.29e-53); Shapiro-Wilk *W* = 0.9696 (*p* = 0.4497); cell-mean *r* = 1.0000 |
| w | Non-normal paired differences | Pearson + Spearman correlation (two-sided, *n* = 34 sweeps) | *r* = 0.9985 (*p* = 4.11e-42); Spearman *rho* = 0.9972 (*p* = 9.63e-38); Shapiro-Wilk *W* = 0.7639 (*p* = 5.51e-06); cell-mean *r* = 0.9999 |
| x | Non-normal paired differences | Pearson + Spearman correlation (two-sided, *n* = 34 sweeps) | *r* = 0.9777 (*p* = 2.97e-23); Spearman *rho* = 0.9844 (*p* = 9.94e-26); Shapiro-Wilk *W* = 0.8092 (*p* = 3.87e-05); cell-mean *r* = 0.9786 |
| y | Non-normal paired differences | Pearson + Spearman correlation (two-sided, *n* = 34 sweeps) | *r* = 0.9988 (*p* = 1.34e-43); Spearman *rho* = 0.9979 (*p* = 1.74e-39); Shapiro-Wilk *W* = 0.8716 (*p* = 0.0009); cell-mean *r* = 0.9999 |
| z | Non-normal paired differences | Pearson + Spearman correlation (two-sided, *n* = 34 sweeps) | *r* = 0.9809 (*p* = 2.56e-24); Spearman *rho* = 0.9872 (*p* = 4.54e-27); Shapiro-Wilk *W* = 0.7745 (*p* = 8.53e-06); cell-mean *r* = 0.9804 |
| aa | Non-normal paired differences | Pearson + Spearman correlation (two-sided, *n* = 34 sweeps) | *r* = 0.9861 (*p* = 1.64e-26); Spearman *rho* = 0.9737 (*p* = 3.94e-22); Shapiro-Wilk *W* = 0.9059 (*p* = 0.0066); cell-mean *r* = 0.9903 |
| ab | Non-normal paired differences | Pearson + Spearman correlation (two-sided, *n* = 34 sweeps) | *r* = 0.9873 (*p* = 3.62e-27); Spearman *rho* = 0.9948 (*p* = 2.49e-33); Shapiro-Wilk *W* = 0.6481 (*p* = 8.62e-08); cell-mean *r* = 0.9902 |
| ac | Non-normal paired differences | Pearson + Spearman correlation (two-sided, *n* = 34 sweeps) | *r* = 0.9961 (*p* = 2.60e-35); Spearman *rho* = 0.9786 (*p* = 1.51e-23); Shapiro-Wilk *W* = 0.8277 (*p* = 9.22e-05); cell-mean *r* = 0.9986 |
| ad | Normal paired differences | Pearson correlation (two-sided, *n* = 34 sweeps) | *r* = 0.9969 (*p* = 6.01e-37); Spearman *rho* = 0.9587 (*p* = 4.81e-19); Shapiro-Wilk *W* = 0.9734 (*p* = 0.5601); cell-mean *r* = 0.9996 |

<!-- TABLES_END -->

![Figure 2](figures/figure_02.png)

## Biological Use-Case Demonstration 
Beyond standalone mathematical validation, SynaptiPy offers immediate utility for experimental workflows (Figure 3). End-to-end benchmarking indicates that the software maintains stable execution times even as recording complexity scales. In headless batch mode, core spike detection completes in approximately 68.5 ms per multi-sweep recording, allowing high-throughput processing across multiple CPU cores (Figure 3A). Furthermore, under software rendering, the full end-to-end application loop remains responsive, ranging from 14 to 18 ms for 10 to 20 overlaid trials (Figure 3C).

![Figure 3](figures/figure_03.png)

# Discussion
Within the current landscape of intracellular electrophysiology software, SynaptiPy provides a unified analytical utility explicitly tailored to experimental workflows. It is not intended to replace the deep, highly specialized functionality of established suites such as **Neuromatic** or **EasyElectrophysiology**, but rather to serve as a complementary bridge to the Python ecosystem.

While software packages like **Clampfit** and **Axograph** remain robust industry standards, their proprietary formats and platform dependencies can create friction in multi-lab collaborations spanning macOS and Linux. By combining the interactive GUI experience of tools like **Stimfit** with a pure Python backend, SynaptiPy allows researchers to sync their analysis protocols using a universal standard (Table 3).

**Table 3: Feature comparison of SynaptiPy against prominent electrophysiology tools.**

| Feature | SynaptiPy | Clampfit | Stimfit | Neuromatic (Igor) | EasyElectrophysiology |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Interactive GUI** | Yes | Yes | Yes | Yes | Yes |
| **Batch Engine** | Yes (Python) | Limited | Yes (Python/C++) | Yes (Igor Pro) | Limited |
| **Multi-Format Loading** | Yes | No | Yes | Limited | Yes |
| **OS Compatibility** | Win, macOS, Linux | Win | Win, macOS, Linux | Win, macOS | Win, macOS, Linux |

**Limitations**: SynaptiPy currently focuses exclusively on *in vitro* patch-clamp and optogenetic datasets. It does not implement clustering or spike-train heuristics for *in vivo* extracellular multi-electrode arrays (MEAs), a domain already expertly served by broader Python ecosystem libraries such as **Elephant** and **Pynapple**. The open-source community is actively invited to leverage the decoupled `@AnalysisRegistry` to expand these functionalities.

# References

Bean BP (2007) The action potential in mammalian central neurons. *Nat Rev Neurosci* 8:451-465. doi:10.1038/nrn2148

Clements JD, Bekkers JM (1997) Detection of spontaneous synaptic events with an optimally scaled template. *Biophys J* 73:220-229. doi:10.1016/S0006-3495(97)78062-7

Colquhoun D, Sigworth FJ (1995) Fitting and statistical analysis of single-channel records. In: *Single-Channel Recording* (Sakmann B, Neher E, eds), 2nd ed, pp483-587. New York: Springer. doi:10.1007/978-1-4419-1229-9_19

Dempster J (1997) A new version of the Strathclyde Electrophysiology software package running within the Microsoft Windows environment. *J Physiol* 504:P57-P57.

Garcia S, Guarino D, Jaillet F, Jennings TR, Pröpper R, Rautenberg PL, Rodgers C, Sobolev A, Wachtler T, Yger P, Davison AP (2014) Neo: an object model for handling electrophysiology data in multiple formats. *Front Neuroinform* 8:10. doi:10.3389/fninf.2014.00010

Gouwens NW et al. (2019) Classification of electrophysiological and morphological neuron types in the mouse visual cortex. *Nat Neurosci* 22:1182-1195. doi:10.1038/s41593-019-0417-0

Guzman SJ, Schlögl A, Schmidt-Hieber C (2014) Stimfit: quantifying electrophysiological data with Python. *Front Neuroinform* 8:16. doi:10.3389/fninf.2014.00016

Hamill OP, Marty A, Neher E, Sakmann B, Sigworth FJ (1981) Improved patch-clamp techniques for high-resolution current recording from cells and cell-free membrane patches. *Pflugers Arch* 391:85-100. doi:10.1007/BF00656997

Hampel FR (1974) The influence curve and its role in robust estimation. *J Am Stat Assoc* 69:383-393. doi:10.1080/01621459.1974.10482962

Harris CR, Millman KJ, van der Walt SJ, Gommers R, Virtanen P, Cournapeau D, Wieser E, Taylor J, Berg S, Smith NJ, Kern R, Picus M, Hoyer S, van Kerkwijk MH, Brett M, Haldane A, del Río JF, Wiebe M, Peterson P, Gérard-Marchant P, Sheppard K, Reddy T, Weckesser W, Abbasi H, Gohlke C, Oliphant TE (2020) Array programming with NumPy. *Nature* 585:357-362. doi:10.1038/s41586-020-2649-2

Hodgkin AL, Huxley AF (1952) A quantitative description of membrane current and its application to conduction and excitation in nerve. *J Physiol* 117:500-544. doi:10.1113/jphysiol.1952.sp004764

Hu M, Jiang X (2022) PatchView: a Python package for patch-clamp data analysis and visualization. *J Open Source Softw* 7:4706. doi:10.21105/joss.04706

Jenerick H (1963) Phase plane trajectories of the muscle spike potential. *Biophys J* 3:363-377. doi:10.1016/S0006-3495(63)86827-7

Mandge D, Tuncel A, Jaquier A, Kilic I, Damart T, Markram H, Van Geit W, Ranjan R (2026) eFEL: electrophysiology feature extraction library. *Bioinformatics* 42:btag328. doi:10.1093/bioinformatics/btag328

McKinney W (2010) Data structures for statistical computing in Python. In: Proceedings of the 9th Python in Science Conference, pp56-61. doi:10.25080/Majora-92bf1922-00a

Rall W (1969) Time constants and electrotonic length of membrane cylinders and neurons. *Biophys J* 9:1483-1508. doi:10.1016/S0006-3495(69)86467-2

Robinson RB, Siegelbaum SA (2003) Hyperpolarization-activated cation currents: from molecules to physiological function. *Annu Rev Physiol* 65:453-480. doi:10.1146/annurev.physiol.65.092101.142734

Rothman JS, Silver RA (2018) NeuroMatic: an integrated open-source software toolkit for acquisition, analysis and simulation of electrophysiological data. *Front Neuroinform* 12:14. doi:10.3389/fninf.2018.00014

Rubel O et al. (2022) The Neurodata Without Borders ecosystem for neurophysiological data science. *eLife* 11:e78362. doi:10.7554/eLife.78362

Taylor AL (2012) What we talk about when we talk about capacitance measured with the voltage-clamp step method. *J Comput Neurosci* 32:167-175. doi:10.1007/s10827-011-0346-8

Thanawala MS, Regehr WG (2013) Presynaptic calcium influx controls neurotransmitter release in part by regulating the effective size of the readily releasable pool. *J Neurosci* 33:4625-4633. doi:10.1523/JNEUROSCI.4031-12.2013

Virtanen P, Gommers R, Oliphant TE, Haberland M, Reddy T, Cournapeau D, Burovski E, Peterson P, Weckesser W, Bright J, van der Walt SJ, Brett M, Wilson J, Millman KJ, Mayorov N, Nelson ARJ, Jones E, Kern R, Larson E, Carey CJ, Polat İ, Feng Y, Moore EW, VanderPlas J, Laxalde D, Perktold J, Cimrman R, Henriksen I, Quintero EA, Harris CR, Archibald AM, Ribeiro AH, Pedregosa F, van Mulbregt P (2020) SciPy 1.0: fundamental algorithms for scientific computing in Python. *Nat Methods* 17:261-272. doi:10.1038/s41592-019-0686-2

Widmann A, Schröger E, Maess B (2015) Digital filter design for electrophysiological data: a practical approach. *J Neurosci Methods* 250:34-46. doi:10.1016/j.jneumeth.2014.08.002

Zucker RS, Regehr WG (2002) Short-term synaptic plasticity. *Annu Rev Physiol* 64:355-405. doi:10.1146/annurev.physiol.64.092501.114547

# Figure Legends

**Figure 1.** SynaptiPy architectural workflow and graphical user interface. **(A)** Vector schematic of recording import, visual parameter selection, shared analysis routines (built-in and plugin), and CSV/NWB export. The traces and table entries in A are illustrative. The same parameter set and analysis functions serve interactive inspection and headless batch processing. **(B)** The Data Explorer interface, enabling hierarchical file navigation and interactive inspection of raw electrophysiological sweeps. **(C)** The Analysis Pipeline Builder, configuring modular analysis workflows for intrinsic and active properties. **(D)** The Data Exporter module for consolidating and exporting batch results.

**Figure 2.** Algorithmic parity against established computational benchmarks. **(A-D)** Scatter plots comparing SynaptiPy feature extractions against eFEL (blue circles) and IPFX (red squares) for core action potential metrics: Peak Voltage (A), Half-Width (B), Maximum dV/dt (C), and Minimum dV/dt (D). Black triangles represent SynaptiPy plotted against itself to define the unity line of perfect agreement. Pearson correlation coefficients ($r$) and mean biases are provided in each panel.

**Figure 3.** Computational scaling and UI rendering benchmarks. **(A, B)** Multi-core scaling efficiency of the `BatchAnalysisEngine`, resolving execution times into active compute (blue bars) versus I/O overhead (grey bars) for a lightweight spike detection task (A) and a CPU-bound event detection task (B). **(C, D)** Rendering latency as a function of overlaid experimental sweeps. Latency is compared between the raw `pyqtgraph` rendering layer (black circles) and the full end-to-end application GUI loop (blue squares) under both software (C) and OpenGL-accelerated (D) modes. The 16.6 ms latency threshold required to maintain 60 FPS interactivity is indicated by the horizontal dashed line.

# Extended Data Legends

**Extended Data 1.** SynaptiPy source code (ZIP archive). The complete source code for the SynaptiPy software package, including all analysis modules, GUI components, plugin architecture, and batch processing engine.
