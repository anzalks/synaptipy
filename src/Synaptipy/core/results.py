from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import numpy as np


@dataclass
class AnalysisResult:
    """Base class for analysis results."""

    value: Any  # Primary result value (e.g., float, array, or None if failed)
    unit: str
    is_valid: bool = True
    error_message: Optional[str] = None
    quality_flags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def set_error(self, message: str):
        self.is_valid = False
        self.error_message = message


@dataclass
class SpikeTrainResult(AnalysisResult):
    """
    Result of spike detection analysis.
    Primary 'value' is usually the spike count or mean frequency, depending on context.
    """

    spike_times: Optional[np.ndarray] = None  # Array of spike times in seconds
    spike_indices: Optional[np.ndarray] = None  # Array of sample indices
    mean_frequency: Optional[float] = None  # Mean frequency in Hz
    instantaneous_frequencies: Optional[np.ndarray] = None  # Array of inst. freqs in Hz
    parameters: Dict[str, Any] = field(default_factory=dict)  # Analysis parameters used

    def __repr__(self):
        if self.is_valid:
            count = len(self.spike_times) if self.spike_times is not None else 0
            freq_str = f"{self.mean_frequency:.2f}" if self.mean_frequency is not None else "N/A"
            return f"SpikeTrainResult(count={count}, mean_freq={freq_str} Hz)"
        return f"SpikeTrainResult(Error: {self.error_message})"


@dataclass
class RinResult(AnalysisResult):
    """
    Result of Input Resistance (Rin) analysis.
    Primary 'value' is the Input Resistance in MOhm.
    """

    tau: Optional[float] = None  # Membrane time constant in seconds (or ms)
    conductance: Optional[float] = None  # Conductance in uS (micro-Siemens)
    sag_ratio: Optional[float] = None  # Ratio (0-1 or %)
    voltage_deflection: Optional[float] = None  # Delta V in mV
    current_injection: Optional[float] = None  # Delta I in pA
    baseline_voltage: Optional[float] = None  # Baseline V in mV
    steady_state_voltage: Optional[float] = None  # Steady state V in mV
    parameters: Dict[str, Any] = field(default_factory=dict)  # Analysis parameters used

    def __repr__(self):
        if self.is_valid:
            val_str = f"{self.value:.2f}" if isinstance(self.value, (int, float)) else str(self.value)
            return f"RinResult(Rin={val_str} {self.unit})"
        return f"RinResult(Error: {self.error_message})"


@dataclass
class RmpResult(AnalysisResult):
    """
    Result of Resting Membrane Potential (RMP) analysis.
    Primary 'value' is the RMP in mV.
    """

    std_dev: Optional[float] = None  # Standard deviation of the trace segment
    drift: Optional[float] = None  # Linear drift (slope) in mV/s
    duration: Optional[float] = None  # Duration of analysis window in seconds
    parameters: Dict[str, Any] = field(default_factory=dict)  # Analysis parameters used

    def __repr__(self):
        if self.is_valid:
            val_str = f"{self.value:.2f}" if isinstance(self.value, (int, float)) else str(self.value)
            return f"RmpResult(RMP={val_str} {self.unit})"
        return f"RmpResult(Error: {self.error_message})"


@dataclass
class BurstResult(AnalysisResult):
    """
    Result of Burst Analysis.
    """

    burst_count: int = 0
    spikes_per_burst_avg: float = 0.0
    burst_duration_avg: float = 0.0
    burst_freq_hz: float = 0.0
    parameters: Dict[str, Any] = field(default_factory=dict)  # Analysis parameters used
    bursts: List[List[float]] = field(default_factory=list)  # List of lists of spike times

    def __repr__(self):
        if self.is_valid:
            freq_str = f"{self.burst_freq_hz:.2f}" if self.burst_freq_hz is not None else "N/A"
            return f"BurstResult(count={self.burst_count}, freq={freq_str} Hz)"
        return f"BurstResult(Error: {self.error_message})"


@dataclass
class EventDetectionResult(AnalysisResult):
    """
    Result of Event/Mini Detection.
    """

    event_count: int = 0
    frequency_hz: Optional[float] = None
    mean_amplitude: Optional[float] = None
    amplitude_sd: Optional[float] = None
    event_indices: Optional[np.ndarray] = None
    event_times: Optional[np.ndarray] = None
    event_amplitudes: Optional[np.ndarray] = None
    detection_method: str = "threshold"
    threshold_value: Optional[float] = None
    direction: str = "negative"
    parameters: Dict[str, Any] = field(default_factory=dict)  # Analysis parameters used
    summary_stats: Dict[str, Any] = field(default_factory=dict)

    # Deconvolution specific
    tau_rise_ms: Optional[float] = None
    tau_decay_ms: Optional[float] = None
    threshold_sd: Optional[float] = None

    # Artifact Rejection
    n_artifacts_rejected: int = 0
    artifact_mask: Optional[np.ndarray] = None

    def __repr__(self):
        if self.is_valid:
            freq_str = f"{self.frequency_hz:.2f}" if self.frequency_hz is not None else "N/A"
            return f"EventDetectionResult(count={self.event_count}, freq={freq_str} Hz)"
        return f"EventDetectionResult(Error: {self.error_message})"
