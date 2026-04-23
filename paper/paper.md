---
title: 'Synaptipy: An Open-Source Electrophysiology Visualization and Analysis Suite'
tags:
  - Python
  - electrophysiology
  - patch-clamp
  - neuroscience
  - data analysis
authors:
  - name: Anzal K Shahul
    orcid: 0009-0006-9932-7944
    affiliation: "1, 2"
affiliations:
  - name: Institute Neurosciences Cellulaires Et Intégratives (INCI), Centre National de la Recherche Scientifique (CNRS), Strasbourg, France
    index: 1
  - name: University of Strasbourg, Strasbourg, France
    index: 2
date: 2026-04-16
bibliography: paper.bib
---

# Abstract

SynaptiPy is an open-source, cross-platform software suite for the visualization and automated analysis of patch-clamp electrophysiology data. It provides a unified graphical interface and a programmatic backend that supports more than 30 file formats via the Neo I/O library [@garcia_neo_2014], spanning passive membrane properties, action potential kinetics, spike-train dynamics, synaptic event detection, and optogenetics-evoked response analysis. All extracted metrics are returned as tidy tabular data traceable to their source file, channel, trial, and analysis step, enabling reproducible statistical workflows without post-processing.

# Significance Statement

Experimental neuroscientists currently rely on a fragmented toolchain: proprietary GUIs such as Clampfit (Molecular Devices) or Stimfit [@guzman_stimfit_2014] for interactive visualization, and headless Python libraries such as eFEL or pyABF [@harden_pyabf] for batch analysis. This split forces researchers to export data between tools, hard-code epoch offsets, and maintain custom glue scripts that are rarely version-controlled or shared. SynaptiPy bridges this gap by embedding the full analysis pipeline - from raw file I/O through signal preprocessing to batch-scale feature extraction - inside a single PySide6 [@qt_pyside6] application. Stimulus timing boundaries are parsed directly from TTL signals in the acquisition file header, eliminating manual epoch bookkeeping. The result is a reproducible, auditable workflow available under a permissive open-source license that runs identically on Windows, macOS, and Linux.

# Introduction

Patch-clamp electrophysiology remains the gold standard for characterising the intrinsic electrical properties of neurons and synaptic connectivity in neural circuits. As datasets grow in size and experimental throughput increases, the bottleneck has shifted from data collection to data processing: a typical multi-day experiment may yield hundreds of Axon Binary Format (ABF) files spanning gigabytes of voltage and current traces, each requiring consistent, reproducible analysis.

Existing solutions occupy two non-overlapping niches. GUI-centric tools such as Clampfit and Stimfit [@guzman_stimfit_2014] offer interactive inspection but lack scriptable batch processing. Headless Python libraries such as eFEL and pyABF [@harden_pyabf] automate feature extraction but provide no visualization layer, making it difficult to catch acquisition artefacts or verify that epoch boundaries are correctly assigned. Neo [@garcia_neo_2014] unifies file-format access but does not include analysis or visualization logic.

SynaptiPy was designed to occupy the missing middle ground: a fully interactive application that also exposes every analysis function as a pure-Python callable, so that the same code path is used in both the GUI and headless batch mode. This design guarantees that interactive spot-checks and automated large-scale analyses are always consistent.

# Materials and Methods (Software Architecture)

## Core stack

SynaptiPy is implemented in Python 3.10-3.12 using PySide6 [@qt_pyside6] for the graphical layer, pyqtgraph for accelerated time-series rendering, NumPy [@harris_numpy_2020] and SciPy [@virtanen_scipy_2020] for numerical computation, and pandas [@mckinney_pandas_2010] for tabular output. File I/O is delegated entirely to the Neo library [@garcia_neo_2014], providing transparent support for ABF, WinWCP, NWB [@rubel_nwb_2022], and more than 30 additional formats without format-specific code in SynaptiPy itself.

## Analysis pipeline

The analysis pipeline is organised into five biological domains:

1. **Passive membrane properties** - resting membrane potential, input resistance (Rin), membrane time constant (tau, fitted via mono- or bi-exponential curve fitting using `scipy.optimize.curve_fit` [@virtanen_scipy_2020]), membrane capacitance, and sag ratio (HCN-channel activation).
2. **Single action potential kinetics** - threshold detection using the phase-plane kink-slope method [@bean_action_potential_2007; @naundorf_unique_2006], peak amplitude, half-width, rise/decay time, and after-hyperpolarisation depth.
3. **Spike-train firing dynamics** - instantaneous and mean firing rate, inter-spike interval (ISI) distributions, coefficient of variation (CV and CV2 [@holt_isi_1996]), local variation (LV [@shinomoto_lv_2003]), and burst detection using the maximum-ISI method [@legendy_burst_1985].
4. **Synaptic event detection** - threshold-crossing and deconvolution-based methods [@pernia_andrade_deconvolution_2012] for miniature and evoked postsynaptic currents.
5. **Evoked response analysis** - optogenetics-evoked and electrical-stimulation-evoked response amplitude, latency, and paired-pulse ratio, with TTL-derived epoch boundaries.

Signal preprocessing includes Savitzky-Golay smoothing [@savitzky_smoothing_1964] and baseline subtraction. Stimulus timing boundaries are extracted directly from digital TTL signals in the acquisition file header.

## Batch processing

File-level batch processing is distributed across worker processes via Python's `ProcessPoolExecutor`. Empirical benchmarks on Apple M-series hardware (10-file batches, 3 repeats) show that parallelism is only beneficial when per-file analysis time substantially exceeds the per-process spawn cost (~1-2 s on macOS): threshold-based event detection (9.9 s/file) achieves 3.6x speedup at 6 workers, degrading at 8 workers when efficiency cores become stragglers; spike detection (55 ms/file) is fastest at 1 worker because spawn overhead dominates at all parallel configurations (see Figure 1 and `paper/results/benchmark_results.csv`).

## Plugin interface

A runtime plugin interface allows researchers to register custom Python analysis functions without modifying the core package. Plugins are discovered at startup from a user-specified directory, and decorated with `@AnalysisRegistry.register` to integrate automatically with the GUI parameter forms and batch engine.

## Rendering

The graphical layer uses pyqtgraph with optional OpenGL-accelerated rendering. Per-frame update latency was benchmarked end-to-end through the complete running application in two modes: OVERLAY_AVG (N trials overlaid simultaneously) and CYCLE_SINGLE (single trial browsed frame by frame). **Important caveat: Apple deprecated OpenGL on macOS in macOS 10.14 (Mojave, 2018) and provides no native OpenGL driver on Apple Silicon. On M-series hardware all OpenGL calls are translated at runtime to Apple's Metal API via a compatibility shim; pyqtgraph's `useOpenGL=True` path therefore exercises this translation layer rather than a true hardware OpenGL implementation.** The software QPainter rasteriser delivers predictable 12-18 ms frames across N=5-20 trials (p95/median < 1.1). The Metal-translated OpenGL path shows a 125 ms first-use penalty from Metal shader compilation (N=5), intermittent pipeline-recompilation stalls of 224-347 ms at p95 during warm-up (N=10, N=15), and stabilises at 3.9 ms median (p95 = 4.6 ms) at N=20 once the shader cache is warm. In CYCLE_SINGLE mode, the Metal path is 43x faster than software (0.26 ms vs 11.1 ms), consistent with Metal's asynchronous command submission. These results should not be generalised to OpenGL on Windows or Linux (see Figure 2 and `paper/results/e2e_rendering_results.csv`).

## Testing and continuous integration

The test suite covers both analysis correctness (pytest) and graphical interactions (pytest-qt), with continuous integration across Python 3.10-3.12 on Ubuntu, Windows, and macOS. An independent algorithmic validation suite (`validation/validate_algorithms.py`) generates synthetic waveforms with analytically known properties (RMP, Rin, spike count and timing, sag ratio, membrane tau, artifact blanking) and verifies that all measured values fall within specified tolerances.

# Results (Biological Validation)

**Batch scaling (Figure 1).** Benchmarks were run on macOS (Apple M-series processor, 6 performance cores + 2 efficiency cores, 32 GB RAM). Two datasets were constructed: 10 copies of `2023_04_11_0021.abf` (single voltage channel, 20 trials, 20 000 samples at 20 kHz), analysed with `spike_detection` (threshold -20 mV, all_trials scope, ~55 ms/file); and 10 copies of `2023_04_11_0022.abf` (four-channel recording, 3 trials), analysed with `event_detection_threshold` (threshold 2 mV, positive direction, all_trials scope, ~9.9 s/file). Worker counts of 1, 2, 4, 6, and 8 were evaluated with 3 repeats each; the median wall-clock time is reported and error bars span the observed minimum and maximum. The dashed reference line ("Ideal T1/N") shows the theoretical wall-clock time if N workers processed 1/N of the files with zero coordination overhead. For spike_detection, spawn overhead (~1.5 s/worker on macOS) exceeds the per-file analysis time at all worker counts, so the single-worker configuration is optimal (0.55 s total); measured times with 2-8 workers are 3.5-4.2x longer. For event_detection, the heavy per-file cost amortises spawn overhead well: speedup reaches 3.6x at w=6 (S=T1/T6 = 98.8/27.2), then degrades at w=8 as the two efficiency cores become stragglers (30.8 s, 13% slower than w=6).

**End-to-end rendering (Figure 2).** Per-frame update time was measured for pyqtgraph with `useOpenGL=True` and `useOpenGL=False` (Qt QPainter software rasteriser) through the complete running SynaptiPy application. Each renderer mode was run in a separate child process (so `pg.setConfigOption("useOpenGL", ...)` was applied before any Qt object was created). The child process bootstraps the full `MainWindow`, loads `2023_04_11_0021.abf` via `ExplorerTab.load_recording_data()`, and waits for the background `QThreadPool` worker to complete before beginning timing. Two modes were benchmarked: (a) OVERLAY_AVG with N in {5, 10, 15, 20} trials overlaid simultaneously; (b) CYCLE_SINGLE stepping through all 20 trials in sequence. Each timing cycle calls `explorer._update_plot()` followed by `app.processEvents()`. The first 50 cycles are discarded as warm-up; statistics are computed over the remaining 500 cycles as median and 5th/95th percentile.

*Platform caveat.* These benchmarks were run on Apple Silicon (M-series). Apple deprecated OpenGL on macOS in 2018 and ships no native OpenGL driver on M-series hardware; `useOpenGL=True` therefore invokes Apple's Metal-compatibility translation layer. The anomalous results observed here are artefacts of this translation layer and are not representative of OpenGL performance on Windows or Linux systems where native OpenGL drivers are available.

# Discussion (Comparison to Existing Tools)

SynaptiPy occupies a distinct position in the electrophysiology software landscape by combining interactive visualization with scriptable, batch-capable analysis in a single open-source package.

**Stimfit** [@guzman_stimfit_2014] is the closest precedent: it provides a Python-scriptable GUI for patch-clamp analysis built on wxPython and is widely used for synaptic current kinetics. However, Stimfit does not natively support parallel batch processing across many files, its file-format support is narrower than Neo's 30+ formats, and it is not actively maintained for modern Python environments (3.10+) on all platforms. SynaptiPy covers the same core analysis domains while adding native multi-process batch execution, a live plugin registry, and full cross-platform CI.

**pyABF** [@harden_pyabf] is a lightweight, well-documented library for reading Axon Binary Format files in Python. It is excellent for scripted access to ABF metadata and raw signal arrays, but provides no analysis functions, no visualization layer, and no batch engine. SynaptiPy uses Neo for I/O (which itself supports ABF via pyABF internally) and adds the complete analysis and GUI stack on top.

**Easy Electrophysiology** (EasyElectrophysiology.com) is a commercial web-based platform that offers an accessible GUI for common patch-clamp analyses. Unlike SynaptiPy it is closed-source, requires a network connection, and does not expose a programmatic API for custom analysis extensions. SynaptiPy's AGPL-3.0 license guarantees that all source code remains open and that any modifications distributed to users must also remain open.

**eFEL** (Blue Brain Project) provides a comprehensive library of electrophysiology feature extractors optimised for large-scale modelling workflows. It has no GUI and requires traces to be pre-loaded as Python dictionaries with manually specified stimulus epochs. SynaptiPy complements eFEL by handling the upstream steps (file I/O, epoch parsing from TTL signals, interactive quality control) and can export tidy DataFrames that feed directly into eFEL or downstream statistical tools.

In summary, SynaptiPy is the only tool in this space that simultaneously offers: (1) a cross-platform interactive GUI, (2) Neo-backed support for 30+ file formats, (3) multi-process batch analysis, (4) a runtime plugin interface, and (5) a fully open-source, version-controlled codebase with CI-verified correctness across three operating systems.

# Software Availability

SynaptiPy is released under the **GNU Affero General Public License v3.0 or later (AGPL-3.0-or-later)**. The source code, installation instructions, and full documentation are available at:

- **Repository:** https://github.com/anzalks/synaptipy
- **Documentation (Read the Docs):** https://synaptipy.readthedocs.io
- **Operating systems:** Windows 10/11, macOS 12+, Ubuntu 20.04+ (and compatible Linux distributions)
- **Python versions:** 3.10, 3.11, 3.12

Installation via pip: `pip install synaptipy`

# Figures

![**Figure 1.** Wall-clock time for `BatchAnalysisEngine.run_batch()` across 10 ABF files as a function of worker-process count (Apple M-series, 6P+2E cores, 32 GB RAM; median of 3 runs, error bars = min/max). Left column: raw time with ideal T1/N dashed reference. Right column: speedup S=T1/TW with ideal S=W reference. Top row: `spike_detection` (~55 ms/file) -- parallelism is counterproductive at all worker counts because per-process spawn overhead dominates; optimal at w=1 (0.55 s). Bottom row: `event_detection_threshold` (~9.9 s/file) -- real speedup observed up to w=6 (S=3.63x, 60% parallel efficiency); w=8 regresses 13% relative to w=6 as efficiency cores become stragglers. Raw data: `paper/results/benchmark_results_macos.csv`.](results/benchmark_scaling_macos.png)

![**Figure 2.** End-to-end per-frame update time (ms) measured through the full SynaptiPy MainWindow loaded with `2023_04_11_0021.abf` (20 trials x 20 000 samples @ 20 kHz) on Apple Silicon (M-series). Each data point is the median of 500 post-warmup `_update_plot()` + `processEvents()` cycles; error bars show the 5th/95th percentile. Left panel (A): OVERLAY_AVG mode latency vs N overlaid trials for software QPainter (red dashes) and the `useOpenGL=True` path (blue circles). Right panel (B): grouped bar chart per N. **Note: on Apple Silicon, `useOpenGL=True` routes through Apple's deprecated Metal-compatibility translation layer, not a native OpenGL driver.** Software rendering is predictable (12-18 ms, p95/median < 1.1) and scales linearly with N. The Metal-translated OpenGL path shows a 125 ms first-use penalty at N=5, p95 spikes of 224-347 ms at N=10 and N=15, and stabilises at 3.9 ms median (p95 = 4.6 ms) at N=20. CYCLE_SINGLE (single trial): the Metal path is 43x faster than software (0.26 ms vs 11.1 ms). These anomalous warm-up characteristics are not expected on Windows or Linux with native OpenGL drivers. Raw data: `paper/results/e2e_rendering_results_macos.csv`.](results/e2e_rendering_benchmark_macos.png)