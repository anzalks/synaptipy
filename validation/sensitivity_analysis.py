#!/usr/bin/env python
"""
Parameter Sensitivity Analysis
==============================

Quantifies how output metrics change when key analysis parameters are
perturbed from their defaults. Demonstrates robustness of the analysis
pipeline and identifies parameters that require careful calibration.

Usage::

    python validation/sensitivity_analysis.py --all
    python validation/sensitivity_analysis.py --param dvdt_threshold
    python validation/sensitivity_analysis.py --figures  # save matplotlib plots

Each sensitivity sweep runs the relevant analysis function across a range
of parameter values on a standardised synthetic trace, recording the output
metric at each point.
"""

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np

from Synaptipy.core.analysis.firing_dynamics import calculate_bursts_logic
from Synaptipy.core.analysis.single_spike import detect_spikes_threshold
from Synaptipy.core.analysis.synaptic_events import detect_events_threshold
from Synaptipy.core.constants import (
    BURST_ISI_FRACTION,
    DVDT_THRESHOLD_VS,
    FAHP_WINDOW_MS,
    MAHP_WINDOW_MS,
    TRANSIENT_DETECTION_FACTOR,
)

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class SensitivityResult:
    """Result of sweeping one parameter."""

    param_name: str
    param_values: List[float]
    metric_name: str
    metric_values: List[float]
    default_value: float
    default_metric: float
    max_deviation_pct: float = 0.0

    def __post_init__(self):
        if abs(self.default_metric) > 1e-12:
            deviations = [abs(m - self.default_metric) / abs(self.default_metric) * 100 for m in self.metric_values]
            self.max_deviation_pct = max(deviations) if deviations else 0.0


# ---------------------------------------------------------------------------
# Synthetic test data generators
# ---------------------------------------------------------------------------


def _generate_standard_spike_trace(n_spikes: int = 15, sampling_rate: float = 20000.0) -> Tuple[np.ndarray, np.ndarray]:
    """Generate a standard trace with 15 spikes for sensitivity testing."""
    np.random.seed(123)
    duration = 1.5
    dt = 1.0 / sampling_rate
    n_samples = int(duration * sampling_rate)
    time = np.arange(n_samples) * dt
    voltage = np.full(n_samples, -65.0)

    # Regular spike train at ~10 Hz
    spike_interval = duration / (n_spikes + 1)
    for i in range(n_spikes):
        t_spike = spike_interval * (i + 1)
        idx = int(t_spike * sampling_rate)
        # AP waveform
        rise_samples = int(0.0005 * sampling_rate)  # 0.5 ms rise
        fall_samples = int(0.002 * sampling_rate)  # 2 ms fall
        for j in range(rise_samples):
            if idx + j < n_samples:
                voltage[idx + j] = -65.0 + 85.0 * (j / rise_samples)
        peak_idx = idx + rise_samples
        for j in range(fall_samples):
            if peak_idx + j < n_samples:
                voltage[peak_idx + j] = 20.0 * np.exp(-4.0 * j / fall_samples) - 65.0
        # AHP
        ahp_start = peak_idx + fall_samples
        for j in range(int(0.01 * sampling_rate)):
            if ahp_start + j < n_samples:
                voltage[ahp_start + j] = -65.0 - 5.0 * np.exp(-8.0 * j / (0.01 * sampling_rate))

    # Add realistic noise (1 mV SD)
    voltage += np.random.normal(0, 1.0, n_samples)
    return voltage, time


def _generate_burst_spike_times() -> np.ndarray:
    """Generate spike times with 3 bursts for burst sensitivity testing."""
    np.random.seed(456)
    # 3 bursts of 5 spikes (8 ms ISI within burst), 200 ms inter-burst
    spike_times = []
    for burst_start in [0.1, 0.4, 0.7]:
        for j in range(5):
            spike_times.append(burst_start + j * 0.008)
    # Add some isolated spikes
    spike_times.extend([0.25, 0.55, 0.9])
    return np.sort(spike_times)


def _generate_synaptic_event_trace(n_events: int = 20, sampling_rate: float = 20000.0) -> Tuple[np.ndarray, np.ndarray]:
    """Generate a trace with known synaptic events for detection testing."""
    np.random.seed(789)
    duration = 2.0
    dt = 1.0 / sampling_rate
    n_samples = int(duration * sampling_rate)
    time = np.arange(n_samples) * dt
    current = np.zeros(n_samples)

    # Add events (alpha-function shaped EPSCs)
    event_times = np.linspace(0.05, duration - 0.05, n_events)
    tau_rise = 0.001  # 1 ms
    tau_decay = 0.005  # 5 ms
    amplitude = -15.0  # pA (inward current)

    for t_event in event_times:
        idx = int(t_event * sampling_rate)
        event_len = int(0.05 * sampling_rate)  # 50 ms window
        for j in range(event_len):
            if idx + j < n_samples:
                t = j * dt
                waveform = amplitude * (np.exp(-t / tau_decay) - np.exp(-t / tau_rise))
                waveform *= tau_decay / (tau_decay - tau_rise)  # normalize peak
                current[idx + j] += waveform

    # Add noise
    current += np.random.normal(0, 3.0, n_samples)  # 3 pA noise SD

    return current, time


# ---------------------------------------------------------------------------
# Sweep functions
# ---------------------------------------------------------------------------


def sweep_dvdt_threshold(
    values: Optional[List[float]] = None,
) -> SensitivityResult:
    """Sweep dV/dt threshold and measure spike count."""
    if values is None:
        values = [5.0, 10.0, 15.0, 20.0, 25.0, 30.0, 40.0, 50.0]

    voltage, time = _generate_standard_spike_trace()
    sampling_rate = 1.0 / (time[1] - time[0])
    refractory_samples = int(0.002 * sampling_rate)

    metric_values = []
    for dvdt_thresh in values:
        result = detect_spikes_threshold(
            voltage,
            time,
            threshold=-20.0,
            refractory_samples=refractory_samples,
            dvdt_threshold=dvdt_thresh,
        )
        count = len(result.spike_indices) if result.spike_indices is not None else 0
        metric_values.append(float(count))

    # Default metric
    default_idx = values.index(DVDT_THRESHOLD_VS) if DVDT_THRESHOLD_VS in values else 3
    default_metric = metric_values[default_idx]

    return SensitivityResult(
        param_name="dvdt_threshold_vs",
        param_values=values,
        metric_name="spike_count",
        metric_values=metric_values,
        default_value=DVDT_THRESHOLD_VS,
        default_metric=default_metric,
    )


def sweep_burst_isi_fraction(
    values: Optional[List[float]] = None,
) -> SensitivityResult:
    """Sweep burst ISI fraction and measure burst count."""
    if values is None:
        values = [0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.45, 0.5]

    spike_times = _generate_burst_spike_times()

    metric_values = []
    for frac in values:
        result = calculate_bursts_logic(
            spike_times,
            dynamic_burst=True,
            burst_isi_fraction=frac,
            min_spikes=3,
        )
        metric_values.append(float(result.burst_count))

    default_idx = values.index(BURST_ISI_FRACTION) if BURST_ISI_FRACTION in values else 4
    default_metric = metric_values[default_idx]

    return SensitivityResult(
        param_name="burst_isi_fraction",
        param_values=values,
        metric_name="burst_count",
        metric_values=metric_values,
        default_value=BURST_ISI_FRACTION,
        default_metric=default_metric,
    )


def sweep_event_threshold_factor(
    values: Optional[List[float]] = None,
) -> SensitivityResult:
    """Sweep noise threshold factor and measure event detection rate."""
    if values is None:
        values = [2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0]

    current, time = _generate_synaptic_event_trace()
    sampling_rate = 1.0 / (time[1] - time[0])

    metric_values = []
    for factor in values:
        result = detect_events_threshold(
            current,
            time,
            sampling_rate,
            threshold_factor=factor,
            direction="negative",
        )
        metric_values.append(float(result.event_count))

    default_idx = values.index(TRANSIENT_DETECTION_FACTOR) if TRANSIENT_DETECTION_FACTOR in values else 2
    default_metric = metric_values[default_idx]

    return SensitivityResult(
        param_name="event_threshold_factor",
        param_values=values,
        metric_name="event_count",
        metric_values=metric_values,
        default_value=TRANSIENT_DETECTION_FACTOR,
        default_metric=default_metric,
    )


def sweep_ahp_windows(
    scale_factors: Optional[List[float]] = None,
) -> SensitivityResult:
    """Sweep AHP window scale (±50%) and measure effect on detection."""
    if scale_factors is None:
        scale_factors = [0.5, 0.75, 1.0, 1.25, 1.5, 2.0]

    # For AHP, we just verify that the default window captures the AHP.
    # The metric is whether fAHP depth changes with window size.
    from Synaptipy.core.analysis.single_spike import calculate_spike_features

    voltage, time = _generate_standard_spike_trace()
    sampling_rate = 1.0 / (time[1] - time[0])
    refractory_samples = int(0.002 * sampling_rate)

    # Detect spikes first
    spike_result = detect_spikes_threshold(voltage, time, threshold=-20.0, refractory_samples=refractory_samples)
    if spike_result.spike_indices is None or len(spike_result.spike_indices) == 0:
        return SensitivityResult(
            param_name="ahp_window_scale",
            param_values=scale_factors,
            metric_name="mean_fahp_depth_mv",
            metric_values=[0.0] * len(scale_factors),
            default_value=1.0,
            default_metric=0.0,
        )

    metric_values = []
    for scale in scale_factors:
        fahp = (FAHP_WINDOW_MS[0] * scale, FAHP_WINDOW_MS[1] * scale)
        mahp = (MAHP_WINDOW_MS[0] * scale, MAHP_WINDOW_MS[1] * scale)
        features = calculate_spike_features(
            voltage,
            time,
            spike_result.spike_indices,
            fahp_window_ms=fahp,
            mahp_window_ms=mahp,
        )
        depths = [
            f.get("fahp_depth", np.nan)
            for f in features
            if f.get("fahp_depth") is not None and not np.isnan(f.get("fahp_depth", np.nan))
        ]
        mean_depth = float(np.mean(depths)) if depths else 0.0
        metric_values.append(mean_depth)

    default_idx = scale_factors.index(1.0) if 1.0 in scale_factors else 2
    default_metric = metric_values[default_idx]

    return SensitivityResult(
        param_name="ahp_window_scale",
        param_values=scale_factors,
        metric_name="mean_fahp_depth_mv",
        metric_values=metric_values,
        default_value=1.0,
        default_metric=default_metric,
    )


# ---------------------------------------------------------------------------
# Report and figure generation
# ---------------------------------------------------------------------------


def run_all_sweeps() -> List[SensitivityResult]:
    """Run all sensitivity sweeps."""
    return [
        sweep_dvdt_threshold(),
        sweep_burst_isi_fraction(),
        sweep_event_threshold_factor(),
        sweep_ahp_windows(),
    ]


def generate_sensitivity_report(output_dir: Optional[Path] = None) -> str:
    """Generate markdown report summarizing sensitivity analysis."""
    if output_dir is None:
        output_dir = Path(__file__).parent

    results = run_all_sweeps()

    lines = ["# Parameter Sensitivity Analysis\n"]
    lines.append(
        "This report quantifies how key output metrics change when analysis\n"
        "parameters are perturbed from their defaults. Low sensitivity indicates\n"
        "robust parameter choices.\n"
    )

    lines.append("## Summary\n")
    lines.append("| Parameter | Default | Metric | Max Deviation (%) | Robust? |")
    lines.append("|-----------|---------|--------|-------------------|---------|")

    for r in results:
        robust = "Yes" if r.max_deviation_pct < 20 else "No"
        lines.append(
            f"| {r.param_name} | {r.default_value} | {r.metric_name} | " f"{r.max_deviation_pct:.1f}% | {robust} |"
        )

    for r in results:
        lines.append(f"\n## {r.param_name}\n")
        lines.append(f"Default value: {r.default_value}")
        lines.append(f"Output metric: {r.metric_name}")
        lines.append(f"Default metric value: {r.default_metric}\n")
        lines.append("| Parameter Value | Metric Value | Change (%) |")
        lines.append("|----------------|-------------|------------|")
        for pval, mval in zip(r.param_values, r.metric_values):
            if abs(r.default_metric) > 1e-12:
                change = (mval - r.default_metric) / abs(r.default_metric) * 100
            else:
                change = 0.0
            marker = " **←default**" if abs(pval - r.default_value) < 1e-9 else ""
            lines.append(f"| {pval:.3f}{marker} | {mval:.2f} | {change:+.1f}% |")

    report_text = "\n".join(lines)

    report_path = output_dir / "sensitivity_report.md"
    report_path.write_text(report_text)

    # JSON output
    json_path = output_dir / "sensitivity_results.json"
    json_data = [
        {
            "param_name": r.param_name,
            "param_values": r.param_values,
            "metric_name": r.metric_name,
            "metric_values": r.metric_values,
            "default_value": r.default_value,
            "max_deviation_pct": r.max_deviation_pct,
        }
        for r in results
    ]
    json_path.write_text(json.dumps(json_data, indent=2))

    return report_text


def generate_sensitivity_figures(output_dir: Optional[Path] = None) -> None:
    """Generate matplotlib figures for each sensitivity sweep."""
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib required for figure generation", file=sys.stderr)
        return

    if output_dir is None:
        output_dir = Path(__file__).parent / "figures"
    output_dir.mkdir(parents=True, exist_ok=True)

    results = run_all_sweeps()

    for r in results:
        fig, ax = plt.subplots(1, 1, figsize=(6, 4))
        ax.plot(r.param_values, r.metric_values, "o-", color="#0072B2", linewidth=2)
        ax.axvline(r.default_value, color="#D55E00", linestyle="--", label="Default")
        ax.set_xlabel(r.param_name.replace("_", " ").title())
        ax.set_ylabel(r.metric_name.replace("_", " ").title())
        ax.set_title(f"Sensitivity: {r.param_name}")
        ax.legend()
        ax.grid(True, alpha=0.3)
        fig.tight_layout()
        fig.savefig(output_dir / f"sensitivity_{r.param_name}.png", dpi=150)
        plt.close(fig)

    print(f"Figures saved to {output_dir}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Synaptipy Parameter Sensitivity Analysis")
    parser.add_argument("--all", action="store_true", help="Run all sweeps and print report")
    parser.add_argument("--figures", action="store_true", help="Generate matplotlib figures")
    parser.add_argument("--param", type=str, help="Run specific parameter sweep")
    args = parser.parse_args()

    if args.figures:
        generate_sensitivity_figures()
    elif args.param:
        sweep_map = {
            "dvdt_threshold": sweep_dvdt_threshold,
            "burst_isi_fraction": sweep_burst_isi_fraction,
            "event_threshold": sweep_event_threshold_factor,
            "ahp_windows": sweep_ahp_windows,
        }
        if args.param in sweep_map:
            result = sweep_map[args.param]()
            print(f"{result.param_name}: max deviation = {result.max_deviation_pct:.1f}%")
        else:
            print(f"Unknown param. Available: {list(sweep_map.keys())}")
    elif args.all:
        report = generate_sensitivity_report()
        print(report)
    else:
        parser.print_help()
