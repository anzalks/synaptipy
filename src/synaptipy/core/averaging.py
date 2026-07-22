"""Canonical time-aware averaging with trial-quality provenance."""

from dataclasses import dataclass
from typing import Any, Iterable, List, Optional

import numpy as np

from synaptipy.core.trial_qc import TrialQCDecision, assess_trial_eligibility


@dataclass(frozen=True)
class TimeAlignedAverage:
    """An average trace and the full inclusion record used to create it."""

    time: Optional[np.ndarray]
    data: Optional[np.ndarray]
    contributors_per_sample: Optional[np.ndarray]
    decisions: List[TrialQCDecision]
    alignment_method: str = "linear interpolation on relative time"

    @property
    def included_indices(self) -> List[int]:
        return [decision.trial_index for decision in self.decisions if decision.included]

    @property
    def is_empty(self) -> bool:
        return self.time is None or self.data is None or not self.included_indices


def compute_time_aligned_average(
    trial_list: Iterable[Any],
    time_list: Iterable[Any],
    trial_indices: Optional[Iterable[int]] = None,
    manually_excluded: Optional[Iterable[int]] = None,
) -> TimeAlignedAverage:
    """Average eligible traces on their physical time axis.

    The longest valid time axis is used as the target grid. Each contributor is
    interpolated only over its measured range, so unequal durations retain an
    explicit per-sample contributor count rather than fabricated extrapolation.
    """
    traces = list(trial_list)
    times = list(time_list)
    indices = list(trial_indices) if trial_indices is not None else list(range(len(traces)))
    if len(traces) != len(times) or len(traces) != len(indices):
        return TimeAlignedAverage(None, None, None, [], "invalid trial/time collection")

    decisions = [
        assess_trial_eligibility(trace, time, trial_index, manually_excluded)
        for trace, time, trial_index in zip(traces, times, indices)
    ]
    valid_rows = [
        (np.asarray(trace, dtype=float), np.asarray(time, dtype=float))
        for trace, time, decision in zip(traces, times, decisions)
        if decision.included
    ]
    if not valid_rows:
        return TimeAlignedAverage(None, None, None, decisions)

    target_time = max((time for _, time in valid_rows), key=len)
    aligned = np.full((len(valid_rows), target_time.size), np.nan, dtype=float)
    for row, (trace, time) in enumerate(valid_rows):
        in_range = (target_time >= time[0]) & (target_time <= time[-1])
        aligned[row, in_range] = np.interp(target_time[in_range], time, trace)
    contributors = np.sum(np.isfinite(aligned), axis=0)
    with np.errstate(invalid="ignore"):
        average = np.nanmean(aligned, axis=0)
    return TimeAlignedAverage(target_time, average, contributors, decisions)
