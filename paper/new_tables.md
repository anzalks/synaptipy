**Table 2-1: Statistical summary of SynaptiPy AP extraction vs. eFEL and IPFX benchmarks (Allen Dataset, per-sweep means).**

| Metric | SynaptiPy vs IPFX Pearson *r* | Mean bias vs IPFX | LoA vs IPFX | SynaptiPy vs eFEL Pearson *r* | Mean bias vs eFEL | LoA vs eFEL |
|--------|-------------------------------|-------------------|-------------|-------------------------------|-------------------|-------------|
| AP threshold (mV) | 0.9132 (*p* = 1.41e-17, *n* = 43) | -0.007 mV | [-1.79, +1.77] mV | 0.9252 (*p* = 7.43e-19, *n* = 43) | -0.607 mV | [-2.23, +1.02] mV |
| AP amplitude (mV) | 0.9942 (*p* = 2.24e-41, *n* = 43) | +0.027 mV | [-1.76, +1.82] mV | 0.9959 (*p* = 1.93e-44, *n* = 43) | +0.578 mV | [-0.98, +2.13] mV |
| AP half-width (ms) | 0.9878 (*p* = 1.01e-34, *n* = 43) | -0.094 ms | [-0.19, -0.00] ms | 0.9995 (*p* = 2.21e-62, *n* = 43) | +0.002 ms | [-0.01, +0.02] ms |
| Max dV/dt (V/s) | 0.9918 (*p* = 2.66e-38, *n* = 43) | -6.488 V/s | [-19.53, +6.55] V/s | 0.9879 (*p* = 7.89e-35, *n* = 43) | -34.340 V/s | [-65.71, -2.97] V/s |
| AP Delay (Time to first spike) (ms) | 1.0000 (*p* = 0.00e+00, *n* = 43) | -0.000 ms | [-0.00, +0.00] ms | 1.0000 (*p* = 1.51e-153, *n* = 43) | -0.002 ms | [-0.01, +0.01] ms |
| Upstroke/Downstroke Ratio | 0.9996 (*p* = 6.03e-66, *n* = 43) | -0.073 Ratio | [-0.16, +0.02] Ratio | 0.9988 (*p* = 2.06e-55, *n* = 43) | -0.211 Ratio | [-0.34, -0.09] Ratio |
| Fast AHP depth (mV) | 0.9802 (*p* = 1.75e-30, *n* = 43) | +0.718 mV | [-3.79, +5.22] mV | 0.9820 (*p* = 3.35e-26, *n* = 36) | +0.844 mV | [-3.91, +5.59] mV |
| ADP amplitude (mV) | 0.9061 (*p* = 0.0939, *n* = 4) | -0.110 mV | [-0.25, +0.03] mV | 0.6555 (*p* = 0.0017, *n* = 20) | +5.768 mV | [-10.94, +22.48] mV |
| Mean Firing Frequency (Hz) | 1.0000 (*p* = 6.93e-92, *n* = 43) | -0.047 Hz | [-0.46, +0.37] Hz | 0.4501 (*p* = 0.0025, *n* = 43) | -22.496 Hz | [-111.15, +66.16] Hz |
| Spike Frequency Adaptation | 0.9999 (*p* = 1.97e-52, *n* = 30) | -0.000 Ratio | [-0.00, +0.00] Ratio | 0.8215 (*p* = 8.43e-08, *n* = 28) | +0.012 Ratio | [-0.02, +0.04] Ratio |

*All correlations are Pearson's r (two-sided) with exact *p*-values and valid pair counts reported across *n* = 43 sweeps nested within *N* = 6 independent cells. Bias = mean signed difference (SynaptiPy minus benchmark, per-sweep means). LoA = 95% Bland-Altman limits of agreement.*

**Table 2-2: Subthreshold passive properties benchmark on hyperpolarizing steps (Allen Dataset).**

| Metric | Valid *N* (eFEL / IPFX) | SynaptiPy vs eFEL Pearson *r* | Mean bias vs eFEL | LoA vs eFEL | SynaptiPy vs IPFX Pearson *r* | Mean bias vs IPFX | LoA vs IPFX |
|--------|-------------------------|-------------------------------|-------------------|-------------|-------------------------------|-------------------|-------------|
| Resting Membrane Potential (mV) | 34 | 0.9997 (*p* = 3.38e-52) | +0.010 mV | [-0.10, +0.12] mV | 1.0000 (*p* = 3.76e-91) | -0.001 mV | [-0.01, +0.01] mV |
| Input Resistance - Steady-State (MOhm) | 34 | 0.9985 (*p* = 4.11e-42) | -1.232 MOhm | [-8.01, +5.55] MOhm | 0.9777 (*p* = 2.97e-23) | -14.390 MOhm | [-38.71, +9.93] MOhm |
| Input Resistance - Peak (MOhm) | 34 | 0.9988 (*p* = 1.34e-43) | +4.203 MOhm | [-1.88, +10.28] MOhm | 0.9809 (*p* = 2.56e-24) | -10.337 MOhm | [-32.61, +11.93] MOhm |
| Membrane Time Constant (ms) | 34 | 0.9861 (*p* = 1.64e-26) | -1.053 ms | [-4.43, +2.32] ms | 0.9873 (*p* = 3.62e-27) | -0.496 ms | [-3.47, +2.48] ms |
| Sag Percentage (%) | 34 | 0.9961 (*p* = 2.60e-35) | -0.848 % | [-2.00, +0.30] % | 0.9969 (*p* = 6.01e-37) | +0.217 % | [-0.79, +1.23] % |
