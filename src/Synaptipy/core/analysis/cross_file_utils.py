# src/Synaptipy/core/analysis/cross_file_utils.py
# -*- coding: utf-8 -*-
"""
Pure-math utility functions for cross-file trial averaging.

These functions contain no Qt or GUI dependencies and operate only on
NumPy arrays together with the NeoAdapter/Recording domain types.  They
are extracted from BaseAnalysisTab so that they can be tested in isolation
and reused from non-GUI code paths (e.g. batch engine, CLI).
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

log = logging.getLogger(__name__)


def extract_per_file_trace(
    item: Dict[str, Any],
    parsed_trials: List[int],
    channel_idx: int,
    neo_adapter: Any,
) -> Optional[Tuple[np.ndarray, np.ndarray]]:
    """Load one analysis item and return its averaged trace for the requested trials.

    Files that cannot be loaded, or that lack the requested channel / trial,
    are silently excluded by returning ``None`` - the caller decides how to
    handle the missing data.

    Args:
        item:          Single entry from an analysis-items list.  Must contain
                       a ``"path"`` key with the file path.
        parsed_trials: 0-based trial indices to average *within* the file.
        channel_idx:   0-based channel position (sorted by channel-id) shared
                       across files.
        neo_adapter:   Adapter with a ``read_recording(path)`` method that
                       returns a :class:`~Synaptipy.core.data_model.Recording`
                       or ``None``.

    Returns:
        ``(time_array, averaged_data)`` or ``None`` when the item cannot
        contribute a valid trace.
    """
    path = item.get("path")
    if not path:
        return None

    try:
        recording = neo_adapter.read_recording(path)
        if recording is None:
            log.debug("Cross-file avg: could not load %s", path)
            return None

        channels_sorted = sorted(recording.channels.items())
        if channel_idx >= len(channels_sorted):
            log.debug(
                "Cross-file avg: %s has fewer channels than index %d - skipping",
                path,
                channel_idx,
            )
            return None

        _, channel = channels_sorted[channel_idx]

        file_traces: List[np.ndarray] = []
        file_times: List[np.ndarray] = []
        for trial_idx in parsed_trials:
            trial_data = channel.get_data(trial_idx)
            trial_time = channel.get_relative_time_vector(trial_idx)
            if trial_data is None or trial_time is None:
                raise ValueError(f"Trial {trial_idx} returned None data in {getattr(path, 'name', path)}")
            file_traces.append(trial_data)
            file_times.append(trial_time)

        if not file_traces:
            return None

        min_file_len = min(len(t) for t in file_traces)
        file_avg = np.mean(np.array([t[:min_file_len] for t in file_traces]), axis=0)
        return file_times[0][:min_file_len], file_avg

    except (IndexError, ValueError) as exc:
        log.debug("Cross-file avg: skipping %s: %s", path, exc)
        return None


def get_cross_file_average(
    items: List[Dict[str, Any]],
    parsed_trials: List[int],
    channel_idx: int,
    neo_adapter: Any,
) -> Tuple[Optional[np.ndarray], Optional[np.ndarray], int, bool]:
    """Compute the grand average of specified trials across all loaded files.

    Delegates per-file extraction to :func:`extract_per_file_trace`.  Files
    that fail silently are excluded so the average denominator stays
    scientifically correct.  Per-file averages of unequal length are
    **padded with NaN** rather than truncated, so the statistical *N*
    decreases smoothly at the end of shorter recordings instead of producing
    an artificial variance step.

    Args:
        items:         List of analysis-item dicts, each containing at least a
                       ``"path"`` key.
        parsed_trials: Ordered list of 0-based trial indices to extract.
        channel_idx:   Position of the target channel (0-based, sorted by
                       channel-id) shared across files.
        neo_adapter:   Adapter with a ``read_recording(path)`` method.

    Returns:
        Tuple ``(time_array, grand_average, n_files, has_unequal_lengths)``
        where *n_files* is the number of files that contributed and
        *has_unequal_lengths* is ``True`` when the contributing traces had
        different sample counts (caller should warn the user).
        Returns ``(None, None, 0, False)`` when no valid traces could be
        obtained.
    """
    valid_traces: List[np.ndarray] = []
    valid_times: List[np.ndarray] = []

    for item in items:
        result = extract_per_file_trace(item, parsed_trials, channel_idx, neo_adapter)
        if result is not None:
            file_time, file_avg = result
            valid_traces.append(file_avg)
            valid_times.append(file_time)

    if not valid_traces:
        return None, None, 0, False

    lengths = [len(t) for t in valid_traces]
    has_unequal_lengths = len(set(lengths)) > 1
    max_len = max(lengths)

    # Pad shorter arrays with NaN so that nanmean produces a smoothly
    # decreasing N rather than an artificial variance step at the truncation
    # point.
    padded = np.full((len(valid_traces), max_len), np.nan)
    for i, trace in enumerate(valid_traces):
        padded[i, : len(trace)] = trace

    grand_average = np.nanmean(padded, axis=0)

    # Reference time vector: longest available (NaN-padded region has no
    # valid data anyway, but callers need the full axis for plotting).
    longest_idx = int(np.argmax(lengths))
    reference_time = valid_times[longest_idx]

    return reference_time, grand_average, len(valid_traces), has_unequal_lengths
