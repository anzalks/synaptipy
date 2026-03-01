#!/usr/bin/env python
"""
Synaptipy Ground-Truth Validation Suite
========================================

Generates synthetic electrophysiology traces with analytically known
properties and verifies that Synaptipy's analysis functions recover
the ground-truth values within specified tolerances.

This script is intended for:
- Continuous integration (``python -m pytest validation/``)
- Pre-publication reproducibility checks
- Regression detection after algorithm changes

Usage
-----
    python validation/validate_algorithms.py          # run all checks
    python validation/validate_algorithms.py --plot    # also save figures

Reference values are derived from the synthetic waveform parameters
(not from external software), making the suite self-contained.

"""
import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

# ---------------------------------------------------------------------------
# Synaptipy imports
# ---------------------------------------------------------------------------
from Synaptipy.core.analysis.basic_features import calculate_rmp
from Synaptipy.core.analysis.intrinsic_properties import (
    calculate_rin,
    calculate_sag_ratio,
    calculate_tau,
)
from Synaptipy.core.analysis.spike_analysis import detect_spikes_threshold
from Synaptipy.core.signal_processor import blank_artifact


# ---------------------------------------------------------------------------
# Result data classes
# ---------------------------------------------------------------------------
@dataclass
class ValidationCheck:
    """Single validation check result."""

    name: str
    expected: float
    measured: float
    tolerance_pct: float
    unit: str = ""
    passed: bool = False

    def __post_init__(self) -> None:
        if self.expected == 0:
            self.passed = abs(self.measured) < 1e-6
        else:
            error_pct = abs(self.measured - self.expected) / abs(self.expected) * 100
            self.passed = error_pct <= self.tolerance_pct


@dataclass
class ValidationReport:
    """Aggregated validation results."""

    checks: List[ValidationCheck] = field(default_factory=list)

    @property
    def n_passed(self) -> int:
        """Number of passed checks."""
        return sum(1 for c in self.checks if c.passed)

    @property
    def n_failed(self) -> int:
        """Number of failed checks."""
        return sum(1 for c in self.checks if not c.passed)

    @property
    def all_passed(self) -> bool:
        """Whether every check passed."""
        return self.n_failed == 0

    def add(self, check: ValidationCheck) -> None:
        """Add a check to the report."""
        self.checks.append(check)

    def summary_table(self) -> str:
        """Return a human-readable Markdown table."""
        lines = [
            "| Check | Expected | Measured | Tol (%) | Status |",
            "|-------|----------|----------|---------|--------|",
        ]
        for c in self.checks:
            status = "PASS" if c.passed else "**FAIL**"
            lines.append(
                f"| {c.name} | {c.expected:.4g} {c.unit} "
                f"| {c.measured:.4g} {c.unit} "
                f"| {c.tolerance_pct:.1f} | {status} |"
            )
        lines.append("")
        lines.append(
            f"**{self.n_passed}/{len(self.checks)} passed**"
        )
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Synthetic waveform generators
# ---------------------------------------------------------------------------
def _make_time(duration: float, fs: float) -> np.ndarray:
    """Create time vector."""
    return np.arange(0, duration, 1.0 / fs)


def generate_step_trace(
    fs: float = 20000.0,
    duration: float = 1.0,
    baseline_mv: float = -70.0,
    step_mv: float = -10.0,
    step_start: float = 0.2,
    step_end: float = 0.7,
    noise_sd: float = 0.0,
) -> Tuple[np.ndarray, np.ndarray, Dict]:
    """Generate a voltage trace with a rectangular current step.

    Parameters
    ----------
    fs : float
        Sampling rate in Hz.
    duration : float
        Total duration in seconds.
    baseline_mv : float
        Resting membrane potential (mV).
    step_mv : float
        Voltage deflection during the step (mV).
    step_start, step_end : float
        Step onset / offset (seconds).
    noise_sd : float
        Gaussian noise standard deviation (mV).

    Returns
    -------
    data, time, ground_truth
    """
    time = _make_time(duration, fs)
    data = np.full_like(time, baseline_mv)
    mask = (time >= step_start) & (time < step_end)
    data[mask] += step_mv

    if noise_sd > 0:
        rng = np.random.default_rng(42)
        data += rng.normal(0, noise_sd, len(data))

    gt = {
        "rmp_mv": baseline_mv,
        "voltage_deflection_mv": step_mv,
        "baseline_mv": baseline_mv,
        "steady_state_mv": baseline_mv + step_mv,
    }
    return data, time, gt


def generate_spike_train(
    fs: float = 20000.0,
    duration: float = 1.0,
    baseline_mv: float = -70.0,
    spike_times_s: Optional[List[float]] = None,
    spike_peak_mv: float = 30.0,
    spike_width_ms: float = 1.0,
) -> Tuple[np.ndarray, np.ndarray, Dict]:
    """Generate a voltage trace with triangular spike waveforms.

    Parameters
    ----------
    fs : float
        Sampling rate (Hz).
    duration : float
        Total duration (seconds).
    baseline_mv : float
        Resting membrane potential (mV).
    spike_times_s : list of float or None
        Spike peak times in seconds.  Defaults to [0.2, 0.4, 0.6, 0.8].
    spike_peak_mv : float
        Peak voltage of each spike (mV).
    spike_width_ms : float
        Full width of the triangular spike (ms).

    Returns
    -------
    data, time, ground_truth
    """
    if spike_times_s is None:
        spike_times_s = [0.2, 0.4, 0.6, 0.8]

    time = _make_time(duration, fs)
    data = np.full_like(time, baseline_mv)
    half_w = int((spike_width_ms / 1000.0) * fs / 2)

    actual_peaks = []
    for st in spike_times_s:
        idx = int(st * fs)
        if idx - half_w < 0 or idx + half_w >= len(data):
            continue
        # Rising phase
        data[idx - half_w: idx] = np.linspace(baseline_mv, spike_peak_mv, half_w)
        # Falling phase
        data[idx: idx + half_w] = np.linspace(spike_peak_mv, baseline_mv, half_w)
        actual_peaks.append(st)

    n_spikes = len(actual_peaks)
    if n_spikes >= 2:
        isis = np.diff(actual_peaks)
        mean_freq = 1.0 / np.mean(isis)
    elif n_spikes == 1:
        mean_freq = 0.0
    else:
        mean_freq = 0.0

    gt = {
        "spike_count": n_spikes,
        "spike_times_s": actual_peaks,
        "mean_frequency_hz": mean_freq,
    }
    return data, time, gt


def generate_exponential_decay(
    fs: float = 20000.0,
    duration: float = 1.0,
    baseline_mv: float = -70.0,
    amplitude_mv: float = -10.0,
    tau_s: float = 0.050,
    step_start: float = 0.2,
) -> Tuple[np.ndarray, np.ndarray, Dict]:
    """Generate voltage trace with exponential charging curve.

    Parameters
    ----------
    fs : float
        Sampling rate (Hz).
    duration : float
        Total duration (seconds).
    baseline_mv : float
        Resting potential (mV).
    amplitude_mv : float
        Step amplitude at steady state (mV).
    tau_s : float
        Membrane time constant (seconds).
    step_start : float
        Time of step onset (seconds).

    Returns
    -------
    data, time, ground_truth
    """
    time = _make_time(duration, fs)
    data = np.full_like(time, baseline_mv)
    step_mask = time >= step_start
    t_rel = time[step_mask] - step_start
    data[step_mask] = baseline_mv + amplitude_mv * (1 - np.exp(-t_rel / tau_s))

    gt = {
        "tau_s": tau_s,
        "amplitude_mv": amplitude_mv,
        "baseline_mv": baseline_mv,
    }
    return data, time, gt


# ---------------------------------------------------------------------------
# Validation functions
# ---------------------------------------------------------------------------
def validate_rmp(report: ValidationReport) -> None:
    """Validate RMP measurement on a flat trace."""
    rmp_expected = -65.0
    data, time, gt = generate_step_trace(
        baseline_mv=rmp_expected, step_mv=0.0, noise_sd=0.1
    )
    result = calculate_rmp(data, time, baseline_window=(0.0, 0.5))
    report.add(ValidationCheck(
        name="RMP (flat trace)",
        expected=rmp_expected,
        measured=result.value,
        tolerance_pct=1.0,
        unit="mV",
    ))


def validate_rin(report: ValidationReport) -> None:
    """Validate Rin on a rectangular step response."""
    baseline_mv = -70.0
    current_pA = -50.0         # pA
    deflection_mv = -10.0      # mV
    # Rin = |dV| / |dI/1000| = 10 / 0.05 = 200 MOhm
    rin_expected = abs(deflection_mv) / (abs(current_pA) / 1000.0)

    data, time, _ = generate_step_trace(
        baseline_mv=baseline_mv,
        step_mv=deflection_mv,
        step_start=0.2,
        step_end=0.7,
    )
    result = calculate_rin(
        voltage_trace=data,
        time_vector=time,
        current_amplitude=current_pA,
        baseline_window=(0.0, 0.15),
        response_window=(0.5, 0.65),
    )
    report.add(ValidationCheck(
        name="Rin (step response)",
        expected=rin_expected,
        measured=result.value if result.is_valid else float("nan"),
        tolerance_pct=2.0,
        unit="MOhm",
    ))


def validate_spike_count(report: ValidationReport) -> None:
    """Validate spike count on a synthetic spike train."""
    expected_spikes = [0.2, 0.4, 0.6, 0.8]
    data, time, gt = generate_spike_train(
        spike_times_s=expected_spikes,
        spike_peak_mv=30.0,
    )
    fs = 20000.0
    result = detect_spikes_threshold(
        data, time,
        threshold=-20.0,
        refractory_samples=int(0.002 * fs),
    )
    n_detected = len(result.spike_times) if result.spike_times is not None else 0
    report.add(ValidationCheck(
        name="Spike count",
        expected=gt["spike_count"],
        measured=n_detected,
        tolerance_pct=0.0,  # exact match
        unit="spikes",
    ))


def validate_spike_timing(report: ValidationReport) -> None:
    """Validate that detected spike times are within 1 sample of ground truth."""
    expected_spikes = [0.2, 0.4, 0.6, 0.8]
    fs = 20000.0
    data, time, gt = generate_spike_train(spike_times_s=expected_spikes)
    result = detect_spikes_threshold(
        data, time,
        threshold=-20.0,
        refractory_samples=int(0.002 * fs),
    )
    if result.spike_times is not None and len(result.spike_times) > 0:
        max_error = max(
            abs(det - exp)
            for det, exp in zip(result.spike_times, expected_spikes)
        )
        max_error_ms = max_error * 1000
    else:
        max_error_ms = float("inf")

    report.add(ValidationCheck(
        name="Spike timing accuracy",
        expected=0.0,
        measured=max_error_ms,
        tolerance_pct=100.0,  # absolute: < 0.1 ms
        unit="ms",
    ))
    # Override pass/fail with absolute tolerance
    report.checks[-1].passed = max_error_ms < 0.1


def validate_sag_ratio(report: ValidationReport) -> None:
    """Validate sag ratio on a trace with known sag."""
    fs = 20000.0
    duration = 1.0
    time = _make_time(duration, fs)
    baseline_mv = -70.0
    peak_mv = -90.0       # transient peak (20 mV deflection)
    steady_mv = -80.0     # steady state (10 mV deflection)

    data = np.full_like(time, baseline_mv)
    step_start = 0.2
    step_end = 0.8

    # Build a trace with exponential sag
    mask = (time >= step_start) & (time < step_end)
    t_step = time[mask] - step_start
    tau_sag = 0.05  # 50 ms sag time constant
    data[mask] = baseline_mv + (peak_mv - baseline_mv) * np.exp(-t_step / tau_sag) + (
        steady_mv - baseline_mv
    ) * (1 - np.exp(-t_step / tau_sag))

    # Expected sag_ratio = (V_peak - V_baseline) / (V_ss - V_baseline)
    # = (-90 - (-70)) / (-80 - (-70)) = -20 / -10 = 2.0
    expected_ratio = (peak_mv - baseline_mv) / (steady_mv - baseline_mv)

    result = calculate_sag_ratio(
        voltage_trace=data,
        time_vector=time,
        baseline_window=(0.0, 0.15),
        response_peak_window=(step_start, step_start + 0.1),
        response_steady_state_window=(step_end - 0.1, step_end),
    )
    sag_val = result.get("sag_ratio", float("nan"))
    report.add(ValidationCheck(
        name="Sag ratio",
        expected=expected_ratio,
        measured=sag_val if sag_val is not None else float("nan"),
        tolerance_pct=5.0,
        unit="",
    ))


def validate_artifact_blanking(report: ValidationReport) -> None:
    """Validate that artifact blanking zeroes the correct samples."""
    fs = 20000.0
    duration = 0.5
    time = _make_time(duration, fs)
    data = np.ones(len(time)) * -70.0

    # Insert an artifact
    art_start = 0.1
    art_dur_ms = 5.0
    art_mask = (time >= art_start) & (time < art_start + art_dur_ms / 1000)
    data[art_mask] = 1000.0  # large artifact

    blanked = blank_artifact(data, time, art_start, art_dur_ms, method="zero")
    artifact_residual = np.max(np.abs(blanked[art_mask]))

    report.add(ValidationCheck(
        name="Artifact blanking (zero)",
        expected=0.0,
        measured=artifact_residual,
        tolerance_pct=0.0,
        unit="mV",
    ))
    report.checks[-1].passed = artifact_residual < 1e-10


def validate_tau(report: ValidationReport) -> None:
    """Validate membrane time-constant recovery."""
    tau_expected = 0.030  # 30 ms
    data, time, gt = generate_exponential_decay(
        tau_s=tau_expected,
        amplitude_mv=-15.0,
        step_start=0.2,
    )
    result = calculate_tau(
        voltage_trace=data,
        time_vector=time,
        stim_start_time=0.2,
        fit_duration=0.3,
    )
    tau_measured_raw = result
    if tau_measured_raw is None:
        tau_measured = float("nan")
    elif isinstance(tau_measured_raw, (int, float)):
        # tau is returned in ms by calculate_tau — convert to seconds
        tau_measured = float(tau_measured_raw) / 1000.0
    else:
        tau_measured = float("nan")
    report.add(ValidationCheck(
        name="Tau (exp decay)",
        expected=tau_expected,
        measured=tau_measured if tau_measured is not None else float("nan"),
        tolerance_pct=15.0,
        unit="s",
    ))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def run_all(save_report: bool = True) -> ValidationReport:
    """Execute all validation checks.

    Parameters
    ----------
    save_report : bool
        If True, write a Markdown report to validation/report.md.

    Returns
    -------
    ValidationReport
    """
    report = ValidationReport()

    validate_rmp(report)
    validate_rin(report)
    validate_spike_count(report)
    validate_spike_timing(report)
    validate_sag_ratio(report)
    validate_artifact_blanking(report)
    validate_tau(report)

    # Print summary
    print(report.summary_table())
    print()

    if save_report:
        out_dir = Path(__file__).parent
        out_dir.mkdir(parents=True, exist_ok=True)
        report_path = out_dir / "report.md"
        header = (
            "# Synaptipy Algorithm Validation Report\n\n"
            "Auto-generated by `validate_algorithms.py`.\n\n"
        )
        report_path.write_text(header + report.summary_table() + "\n")
        print(f"Report saved to {report_path}")

    # Also dump JSON for CI consumption
    if save_report:
        json_path = out_dir / "report.json"
        checks_list = []
        for c in report.checks:
            checks_list.append({
                "name": c.name,
                "expected": float(c.expected),
                "measured": float(c.measured),
                "tolerance_pct": float(c.tolerance_pct),
                "unit": c.unit,
                "passed": bool(c.passed),
            })
        json_path.write_text(json.dumps(checks_list, indent=2) + "\n")

    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Synaptipy validation suite")
    parser.add_argument(
        "--no-save", action="store_true",
        help="Do not save report files",
    )
    args = parser.parse_args()

    report = run_all(save_report=not args.no_save)
    sys.exit(0 if report.all_passed else 1)
