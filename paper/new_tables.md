**Extended Data Table 1: Statistical summary of SynaptiPy AP extraction vs. eFEL and IPFX benchmarks (Allen Dataset, per-sweep means).**

| Metric | SynaptiPy vs IPFX Pearson *r* | SynaptiPy vs eFEL Pearson *r* | Mean bias vs IPFX | Mean bias vs eFEL |
|--------|-------------------------------|-------------------------------|-------------------|-------------------|
| AP threshold (mV) | 0.9381*** | 0.9440*** | -0.112 mV | -0.163 mV |
| AP amplitude (mV) | 0.9960*** | 0.9912*** | +0.112 mV | +0.870 mV |
| AP half-width (ms) | 0.9879*** | 0.9948*** | -0.092 ms | -0.011 ms |
| Max dV/dt (V/s) | 0.9884*** | 0.7056*** | -6.352 V/s | +79.539 V/s |
| AP Delay (Time to first spike) (ms) | 1.0000*** | 1.0000*** | -0.000 ms | -0.002 ms |
| Upstroke/Downstroke Ratio | 0.9998*** | 0.9971*** | -0.070 Ratio | +0.519 Ratio |
| Fast AHP depth (mV) | 0.9817*** | 0.9524*** | +0.561 mV | -2.056 mV |
| ADP amplitude (mV) | -0.3867 (*p*=0.5203) | 0.5881*** | -6.561 mV | +2.929 mV |
| Mean Firing Frequency (Hz) | 1.0000*** | 0.5951*** | +0.000 Hz | +23.921 Hz |
| Spike Frequency Adaptation | 1.0000*** | 0.7569*** | -0.000 Ratio | +0.014 Ratio |

*Statistical approaches: All correlations are Pearson's r (two-sided). *** denotes p < 0.0001. Data reflects n = 43 sweeps (unless otherwise missing/rejected) where pipelines detected ≥1 action potential. Bias = mean signed difference (SynaptiPy − benchmark, per-sweep means). SynaptiPy: BatchAnalysisEngine `spike_detection` (dV/dt threshold 20 V/s, refractory 2 ms). eFEL: BlueBrain eFEL defaults. IPFX: Allen IPFX SpikeFeatureExtractor, 9.9 kHz Bessel filter. N/A = no direct benchmark equivalent.*

**Extended Data Table 2: Subthreshold passive properties benchmark on hyperpolarizing steps (Allen Dataset).**

| Metric | Valid *N* | SynaptiPy vs eFEL Pearson *r* | Mean bias vs eFEL | LoA vs eFEL | SynaptiPy vs IPFX Pearson *r* | Mean bias vs IPFX | LoA vs IPFX |
|--------|-----------|-------------------------------|-------------------|-------------|-------------------------------|-------------------|-------------|
| Resting Membrane Potential (mV) | 34 | 0.9825*** | -2.224 mV | [-3.06, -1.39] mV | 0.9999*** | -0.125 mV | [-0.18, -0.06] mV |
| Input Resistance — Steady-State (MΩ) † | 34 | 0.9995*** | +0.258 MΩ | [-2.76, +3.28] MΩ | N/A | N/A | N/A |
| Input Resistance — Peak (MΩ) ‡ | 34 | N/A | N/A | N/A | 0.5065 (*p*=0.0022) | -6.561 MΩ | [-126.09, +112.97] MΩ |
| Membrane Time Constant (ms) | 34 | 0.2547 (*p*=0.1461) | -18.485 ms | [-92.86, +55.89] ms | 0.9013 (*p*=0.0056) | -2.126 ms | [-10.43, +6.17] ms |
| Sag Percentage (%) | 34 | -0.0798 (*p*=0.6539) | -1558.875 % | [-2936.86, -180.89] % | 0.0750 (*p*=0.6735) | -1467.770 % | [-2844.47, -91.07] % |

*All correlations are Pearson's r (two-sided); *** = p < 0.0001. LoA = 95% Bland-Altman limits of agreement (mean ± 1.96 SD of sweep-level differences). † SS-Rin: mean voltage in last 100 ms of step (matches eFEL ohmic_input_resistance). ‡ Peak-Rin: maximum hyperpolarization deflection (matches IPFX voltage_deflection). N/A = no direct benchmark equivalent.*