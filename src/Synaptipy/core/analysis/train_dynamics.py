# src/Synaptipy/core/analysis/train_dynamics.py
# -*- coding: utf-8 -*-
"""
Spike Train Dynamics.

Advanced statistical metrics for spike trains natively implemented using NumPy,
replacing the need for external libraries like Elephant.

Calculates:
    - Inter-Spike Intervals (ISI)
    - Coefficient of Variation (CV)
    - Local Variation (LV)
    - CV2

This file is part of Synaptipy, licensed under the GNU Affero General Public License v3.0.
See the LICENSE file in the root of the repository for full license details.
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, Any, Optional
import numpy as np

from Synaptipy.core.analysis.registry import AnalysisRegistry
from Synaptipy.core.results import AnalysisResult
from Synaptipy.core.analysis.spike_analysis import detect_spikes_threshold

log = logging.getLogger(__name__)


@dataclass
class TrainDynamicsResult(AnalysisResult):
    """Result object for spike train dynamics analysis."""
    spike_count: int = 0
    mean_isi_s: Optional[float] = None
    cv: Optional[float] = None
    cv2: Optional[float] = None
    lv: Optional[float] = None
    isis: Optional[np.ndarray] = None
    parameters: Dict[str, Any] = field(default_factory=dict)

    def __repr__(self):
        if self.is_valid:
            cv_str = f"{self.cv:.3f}" if self.cv is not None else "N/A"
            lv_str = f"{self.lv:.3f}" if self.lv is not None else "N/A"
            return f"TrainDynamicsResult(Spikes={self.spike_count}, CV={cv_str}, LV={lv_str})"
        return f"TrainDynamicsResult(Error: {self.error_message})"


def calculate_train_dynamics(
    spike_times: np.ndarray,
) -> TrainDynamicsResult:
    """
    Core logic: Compute native spike train statistical metrics.

    Args:
        spike_times: 1D NumPy array of spike times in seconds.

    Returns:
        TrainDynamicsResult object.
    """
    spike_count = len(spike_times)

    # Need at least 2 spikes for a single ISI
    if spike_count < 2:
        return TrainDynamicsResult(
            value=None,
            unit="",
            is_valid=False,
            error_message="Requires at least 2 spikes for ISI calculations.",
            spike_count=spike_count
        )

    # Calculate Inter-Spike Intervals (ISI)
    isis = np.diff(spike_times)
    mean_isi = float(np.mean(isis))

    # Calculate Coefficient of Variation (CV)
    # CV = std(ISI) / mean(ISI)
    cv = float(np.std(isis) / mean_isi) if mean_isi > 0 else np.nan

    # Need at least 3 spikes (2 ISIs) for CV2 and LV
    if spike_count < 3:
        return TrainDynamicsResult(
            value=mean_isi,
            unit="s",
            is_valid=True,
            spike_count=spike_count,
            mean_isi_s=mean_isi,
            cv=cv,
            cv2=np.nan,
            lv=np.nan,
            isis=isis
        )

    # Guard against zero ISIs (duplicate spike times) which cause division by zero
    isis = isis[isis > 0]
    if len(isis) < 2:
        return TrainDynamicsResult(
            value=mean_isi,
            unit="s",
            is_valid=True,
            spike_count=spike_count,
            mean_isi_s=mean_isi,
            cv=cv,
            cv2=np.nan,
            lv=np.nan,
            isis=isis
        )

    # Consecutive ISIs: ISI_i and ISI_{i+1}
    isi_i = isis[:-1]
    isi_i_plus_1 = isis[1:]

    # Calculate CV2 (holt et al. 1996)
    # CV2 = 1/N * sum( 2 * |ISI_{i+1} - ISI_i| / (ISI_{i+1} + ISI_i) )
    cv2_array = 2.0 * np.abs(isi_i_plus_1 - isi_i) / (isi_i_plus_1 + isi_i)
    cv2_val = float(np.mean(cv2_array))

    # Calculate Local Variation (LV) (Shinomoto et al. 2003)
    # LV = 3/(N-1) * sum( (ISI_i - ISI_{i+1})^2 / (ISI_i + ISI_{i+1})^2 )
    lv_array = 3.0 * ((isi_i - isi_i_plus_1) ** 2) / ((isi_i + isi_i_plus_1) ** 2)
    lv_val = float(np.mean(lv_array))

    return TrainDynamicsResult(
        value=cv,  # Make CV the primary value
        unit="",
        is_valid=True,
        spike_count=spike_count,
        mean_isi_s=mean_isi,
        cv=cv,
        cv2=cv2_val,
        lv=lv_val,
        isis=isis
    )


# --- WRAPPER (Dynamic Plugin Format) ---

@AnalysisRegistry.register(
    name="train_dynamics",
    label="Spike Train Dynamics",
    ui_params=[
        {
            "name": "spike_threshold",
            "type": "float",
            "label": "AP Threshold (mV)",
            "default": 0.0,
            "min": -50.0,
            "max": 50.0,
            "step": 1.0,
            "tooltip": "Threshold to detect action potentials if extracting from trace."
        }
    ],
    plots=[
        {"name": "Trace", "type": "trace", "show_spikes": True},
    ]
)
def run_train_dynamics_wrapper(data: np.ndarray, time: np.ndarray, sampling_rate: float, **kwargs) -> Dict[str, Any]:
    """
    Wrapper for Spike Train Dynamics.
    """

    ap_threshold = kwargs.get("spike_threshold", 0.0)

    ap_times = kwargs.get("action_potential_times", None)
    if ap_times is None:
        # Detect spikes using proper threshold + refractory period method
        refractory_samples = max(1, int(0.002 * sampling_rate))  # 2 ms refractory
        spike_result = detect_spikes_threshold(
            data, time, threshold=ap_threshold,
            refractory_samples=refractory_samples
        )
        has_spikes = (
            spike_result.spike_indices is not None
            and len(spike_result.spike_indices) > 0
        )
        ap_times = time[spike_result.spike_indices] if has_spikes else np.array([])

    result = calculate_train_dynamics(ap_times)

    if not result.is_valid:
        return {"error": result.error_message}

    return {
        "spike_count": result.spike_count,
        "mean_isi_s": result.mean_isi_s,
        "cv": result.cv,
        "cv2": result.cv2,
        "lv": result.lv
    }
