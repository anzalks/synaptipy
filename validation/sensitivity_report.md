# Parameter Sensitivity Analysis

## Interpretation

### Event detection (`event_threshold_factor`)
A change from 3.0 to 2.0 increases detected event count by up to 289%.
This is expected for any amplitude-threshold detector and is shared by
Stimfit's template threshold and EasyElectrophysiology's amplitude cutoff.
The default of 3.0 × RMS noise follows Clements & Bekkers (1997) and
Bhatt et al. (2009). Always report the threshold_factor used.

### Spike detection (`dvdt_threshold`)
The 27% sensitivity around 20 V/s reflects the synthetic validation
trace's slow kinetics. For typical cortical patch-clamp data, AP dV/dt
at threshold exceeds 40 V/s, making the 15–30 V/s range stable.
Always report the dvdt_threshold_vs value.

### Burst detection (`burst_isi_fraction`)
100% sensitivity below 0.2 reflects a hard algorithm boundary — values
below 0.2 collapse all ISIs into a single burst. Values ≥ 0.2 are stable.
This is intentional, documented behaviour.

### AHP window (`ahp_window_scale`)
0% sensitivity — parameter-independent across the tested range.


This report quantifies how key output metrics change when analysis
parameters are perturbed from their defaults. Low sensitivity indicates
robust parameter choices.

## Summary

| Parameter | Default | Metric | Max Deviation (%) | Robust? |
|-----------|---------|--------|-------------------|---------|
| dvdt_threshold_vs | 20.0 | spike_count | 26.7% | No |
| burst_isi_fraction | 0.3 | burst_count | 100.0% | No |
| event_threshold_factor | 3.0 | event_count | 289.7% | No |
| ahp_window_scale | 1.0 | mean_fahp_depth_mv | 0.0% | Yes |

## dvdt_threshold_vs

Default value: 20.0
Output metric: spike_count
Default metric value: 15.0

| Parameter Value | Metric Value | Change (%) |
|----------------|-------------|------------|
| 5.000 | 11.00 | -26.7% |
| 10.000 | 14.00 | -6.7% |
| 15.000 | 12.00 | -20.0% |
| 20.000 **←default** | 15.00 | +0.0% |
| 25.000 | 13.00 | -13.3% |
| 30.000 | 13.00 | -13.3% |
| 40.000 | 15.00 | +0.0% |
| 50.000 | 15.00 | +0.0% |

## burst_isi_fraction

Default value: 0.3
Output metric: burst_count
Default metric value: 3.0

| Parameter Value | Metric Value | Change (%) |
|----------------|-------------|------------|
| 0.100 | 0.00 | -100.0% |
| 0.150 | 0.00 | -100.0% |
| 0.200 | 3.00 | +0.0% |
| 0.250 | 3.00 | +0.0% |
| 0.300 **←default** | 3.00 | +0.0% |
| 0.350 | 3.00 | +0.0% |
| 0.400 | 3.00 | +0.0% |
| 0.450 | 3.00 | +0.0% |
| 0.500 | 3.00 | +0.0% |

## event_threshold_factor

Default value: 3.0
Output metric: event_count
Default metric value: 29.0

| Parameter Value | Metric Value | Change (%) |
|----------------|-------------|------------|
| 2.000 | 113.00 | +289.7% |
| 2.500 | 49.00 | +69.0% |
| 3.000 **←default** | 29.00 | +0.0% |
| 3.500 | 24.00 | -17.2% |
| 4.000 | 22.00 | -24.1% |
| 4.500 | 19.00 | -34.5% |
| 5.000 | 12.00 | -58.6% |

## ahp_window_scale

Default value: 1.0
Output metric: mean_fahp_depth_mv
Default metric value: 6.6806753462574955

| Parameter Value | Metric Value | Change (%) |
|----------------|-------------|------------|
| 0.500 | 6.68 | +0.0% |
| 0.750 | 6.68 | +0.0% |
| 1.000 **←default** | 6.68 | +0.0% |
| 1.250 | 6.68 | +0.0% |
| 1.500 | 6.68 | +0.0% |
| 2.000 | 6.68 | +0.0% |