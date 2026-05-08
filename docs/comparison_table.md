# Feature Comparison: Synaptipy vs. Existing Tools

This table compares Synaptipy with established electrophysiology analysis
software to demonstrate its contribution and positioning within the ecosystem.

## Tool Overview

| Feature | Synaptipy | Stimfit | EasyElectrophysiology | pyABF | Clampfit | AxoGraph |
|---------|-----------|---------|----------------------|-------|----------|----------|
| **License** | AGPL-3.0 | GPL-2.0 | GPL-3.0 | MIT | Commercial | Commercial |
| **Language** | Python | C++/Python | Python | Python | C++ | C++ |
| **GUI** | Yes (Qt6) | Yes (wxWidgets) | Yes (Qt5) | No | Yes | Yes |
| **Headless/batch** | Yes | Partial | No | Yes | No | No |
| **Plugin system** | Yes | Yes | No | No | No | No |
| **Cross-platform** | Win/Mac/Linux | Win/Mac/Linux | Win/Mac/Linux | Any | Windows | Mac |

## File Format Support

| Format | Synaptipy | Stimfit | EasyElectrophysiology | pyABF | Clampfit |
|--------|-----------|---------|----------------------|-------|----------|
| Axon ABF 1/2 | Yes (via Neo) | Yes | Yes | Yes | Yes |
| WinWCP | Yes (via Neo) | Yes | Yes | No | No |
| CED/Spike2 | Yes (via Neo) | Yes | No | No | No |
| Igor IBW/PXP | Yes (via Neo) | No | No | No | No |
| Intan RHD/RHS | Yes (via Neo) | No | No | No | No |
| NWB 2.x | Read+Write | No | No | No | No |
| Open Ephys | Yes (via Neo) | No | No | No | No |
| HEKA | Yes (via Neo) | Yes | No | No | No |
| **Total formats** | **30+** | ~10 | ~5 | 1 | ~3 |

## Analysis Capabilities

| Analysis | Synaptipy | Stimfit | EasyElectrophysiology | pyABF |
|----------|-----------|---------|----------------------|-------|
| Spike detection | dV/dt + threshold | Threshold | Template | Manual |
| AP feature extraction | 12 features | 5 features | 8 features | No |
| Phase plane (dV/dt vs V) | Yes | No | Yes | No |
| Input resistance | Yes (peak + SS) | Yes | Yes | No |
| Membrane tau (mono+bi) | Yes + CI | Yes | Yes | No |
| Capacitance (CC+VC) | Yes | Partial | Yes | No |
| Sag ratio / I_h | Yes | No | Yes | No |
| I-V curve | Yes | No | Yes | No |
| F-I curve + slope | Yes (R^2, p) | No | Yes | No |
| Burst detection | Yes (static+dynamic) | No | No | No |
| Spike train dynamics (CV, CV2, LV) | Yes | No | No | No |
| Synaptic event detection | 3 methods | Yes (template) | Yes (threshold) | No |
| Paired-pulse ratio | Yes (bi-exp fit) | No | Yes | No |
| Stimulus train (STP) | Yes | No | No | No |
| Cross-file averaging | Yes | No | No | No |
| Batch processing | Yes (pipeline) | No | No | Scripted |

## Reproducibility & Data Standards

| Feature | Synaptipy | Stimfit | EasyElectrophysiology | pyABF |
|---------|-----------|---------|----------------------|-------|
| NWB 2.x export | Yes (FAIR) | No | No | No |
| Methods text generation | Yes | No | No | No |
| Parameter provenance | Yes (in results) | No | Partial | N/A |
| Algorithmic documentation | Yes (LaTeX) | Partial | Partial | No |
| Sensitivity analysis | Yes | No | No | No |
| Cross-validation framework | Yes | No | No | No |
| Docker reproducibility | Yes | No | No | No |
| CI/CD (3 OS x 3 Python) | Yes | Yes | No | N/A |
| Test coverage (>90%) | Yes | Partial | No | Partial |

## Unique Contributions of Synaptipy

1. **Unified 30+ format support** via Neo with NWB 2.x export — no other open-source tool provides this complete I/O chain.

2. **Publication-ready reproducibility infrastructure** — pinned environments, Docker container, methods text generator, parameter provenance tracking.

3. **Dual-interface architecture** — interactive GUI for exploration AND headless batch engine for high-throughput processing, sharing the same analysis core.

4. **Formal algorithmic documentation** — every analysis has LaTeX-specified mathematics with citations, validated against synthetic ground truth.

5. **Extensible plugin system** — custom analyses can be added without modifying core code, using a decorator-based registry.

6. **Statistical rigor** — confidence intervals on fitted parameters, goodness-of-fit metrics (R^2, p-values), and quality flags on results.
