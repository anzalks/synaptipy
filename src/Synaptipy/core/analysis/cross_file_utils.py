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


def _resolve_effective_trials(item: Dict[str, Any], channel: Any, parsed_trials: List[int]) -> List[int]:
    """Return the list of trial indices to use for *item* within *channel*.

    ``"Current Trial"`` items specify their own ``trial_index``; ``"Recording"``
    items use every available trial; all other items fall back to *parsed_trials*.
    """
    if item.get("target_type") == "Current Trial" and item.get("trial_index") is not None:
        return [item["trial_index"]]
    if item.get("target_type") == "Recording":
        n_avail = getattr(channel, "num_trials", 1)
        return list(range(max(1, n_avail)))
    return parsed_trials


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

        # Determine which trials to use for this item.
        effective_trials = _resolve_effective_trials(item, channel, parsed_trials)

        file_traces: List[np.ndarray] = []
        file_times: List[np.ndarray] = []
        for trial_idx in effective_trials:
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
    **padded with NaN** rather than truncated so the statistical *N*
    decreases smoothly at the end of shorter recordings instead of producing
    an artificial variance step.

    Algorithm
    ---------
    1. Call :func:`extract_per_file_trace` for every item; collect the
       ``(time, averaged_data)`` pairs from files that succeed.
    2. If all traces share the same length, compute a plain
       :func:`numpy.mean` across the file axis.
    3. When lengths differ, allocate a ``(n_files, max_len)`` matrix filled
       with ``NaN`` and copy each trace into the corresponding row up to its
       own length.  :func:`numpy.nanmean` then produces a grand average
       whose effective *N* equals the number of files that contributed a
       non-NaN sample at each time point.
    4. The reference time vector is taken from the longest contributing file
       so the full axis is available for downstream plotting.

    Parameters
    ----------
    items : list of dict
        Analysis-item dicts, each containing at least a ``"path"`` key.
    parsed_trials : list of int
        Ordered 0-based trial indices to extract from every file.
    channel_idx : int
        0-based position of the target channel (sorted by channel-id),
        shared across all files.
    neo_adapter : object
        Adapter with a ``read_recording(path)`` method that returns a
        :class:`~Synaptipy.core.data_model.Recording` or ``None``.

    Returns
    -------
    tuple
        ``(time_array, grand_average, n_files, has_unequal_lengths)``
        where *n_files* is the number of files that contributed and
        *has_unequal_lengths* is ``True`` when the contributing traces had
        different sample counts (the GUI layer should warn the user).
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

    if has_unequal_lengths:
        min_len = min(lengths)
        log.warning(
            "Cross-file average: unequal trace lengths detected across %d files. "
            "min=%d samples, max=%d samples. "
            "Traces shorter than max_len (%d samples) are NaN-padded; "
            "effective N decreases after sample %d.",
            len(valid_traces),
            min_len,
            max_len,
            max_len,
            min_len,
        )

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


def build_averaged_recording(
    items: List[Dict[str, Any]],
    trial_indices: List[int],
    neo_adapter: Any,
    label: str = "multifile_average",
) -> Optional[Any]:
    """Build a synthetic ``Recording`` whose channels each hold one averaged trial.

    For every channel position found in the first loadable file the function
    calls :func:`get_cross_file_average` to compute the grand average across
    all *items*.  The resulting per-channel average is stored as the sole trial
    of a new :class:`~Synaptipy.core.data_model.Recording` whose
    ``source_file`` is set to ``Path("__mfa__/<label>")``.

    Parameters
    ----------
    items : list of dict
        Analysis-item dicts, each containing at least a ``"path"`` key.
    trial_indices : list of int
        0-based trial indices to average within every file.
    neo_adapter : object
        Adapter with ``read_recording(path)`` returning a Recording or None.
    label : str
        Short human-readable label embedded in the synthetic ``source_file``
        path and ``Recording.metadata["label"]``.

    Returns
    -------
    Recording or None
        Populated synthetic Recording, or ``None`` if no valid data could be
        obtained from any file.
    """
    from pathlib import Path

    from Synaptipy.core.data_model import Channel, Recording

    # Discover channel layout from the first loadable file
    reference_recording = None
    for item in items:
        path = item.get("path")
        if path:
            try:
                rec = neo_adapter.read_recording(path)
                if rec is not None and rec.channels:
                    reference_recording = rec
                    break
            except Exception as exc:
                log.debug("build_averaged_recording: cannot load %s: %s", path, exc)

    if reference_recording is None:
        log.warning("build_averaged_recording: no loadable file found in items list.")
        return None

    channels_sorted = sorted(reference_recording.channels.items())
    n_channels = len(channels_sorted)

    averaged_channels: Dict[str, "Channel"] = {}
    for ch_idx in range(n_channels):
        ref_ch_id, ref_ch = channels_sorted[ch_idx]
        time_arr, avg_arr, n_files, _ = get_cross_file_average(items, trial_indices, ch_idx, neo_adapter)
        if time_arr is None or avg_arr is None:
            log.debug(
                "build_averaged_recording: channel %d produced no average - skipping.",
                ch_idx,
            )
            continue

        ch = Channel(
            id=ref_ch_id,
            name=ref_ch.name,
            units=ref_ch.units,
            sampling_rate=ref_ch.sampling_rate,
            data_trials=[avg_arr],
        )
        ch.t_start = float(time_arr[0]) if len(time_arr) > 0 else 0.0
        ch.metadata["n_files_averaged"] = n_files
        ch.metadata["trial_indices"] = trial_indices
        averaged_channels[ref_ch_id] = ch

    if not averaged_channels:
        log.warning("build_averaged_recording: all channels produced empty averages.")
        return None

    synthetic_path = Path(f"__mfa__/{label}")
    rec = Recording(source_file=synthetic_path)
    rec.channels = averaged_channels
    rec.sampling_rate = reference_recording.sampling_rate
    rec.duration = reference_recording.duration
    rec.metadata["label"] = label
    rec.metadata["is_multifile_average"] = True
    rec.metadata["source_items"] = [str(item.get("path", "")) for item in items]
    rec.metadata["trial_indices"] = trial_indices
    log.debug(
        "build_averaged_recording: built synthetic Recording '%s' with %d channel(s).",
        label,
        len(averaged_channels),
    )
    return rec


def _make_mfa_label(file_paths: List[Any]) -> str:
    """Derive the ``multifile_average(...)`` display label from a list of file paths.

    Takes the last three characters of each file stem and joins them with
    commas.  When more than five files are present the middle entries are
    replaced with ``...`` to keep the label short.

    Parameters
    ----------
    file_paths : list
        Iterable of :class:`pathlib.Path` objects (or path-like strings).

    Returns
    -------
    str
        A compact label such as ``"multifile_average(001,002,003)"`` or
        ``"multifile_average(001,002,...,099,100)"`` for longer sets.
    """
    from pathlib import Path

    suffixes = []
    for p in file_paths:
        stem = Path(p).stem
        suffixes.append(stem[-3:] if len(stem) >= 3 else stem)

    if not suffixes:
        return "multifile_average()"

    if len(suffixes) <= 5:
        inner = ",".join(suffixes)
    else:
        inner = f"{suffixes[0]},{suffixes[1]},...,{suffixes[-2]},{suffixes[-1]}"

    return f"multifile_average({inner})"


def average_padded_trials(trial_list: List[np.ndarray]) -> Optional[np.ndarray]:
    """Compute a NaN-padded mean across a flat list of 1-D trial arrays.

    Shorter arrays are right-padded with NaN so that :func:`numpy.nanmean`
    produces a smoothly decreasing effective N at the tail rather than an
    artificial variance step at the truncation point.

    Parameters
    ----------
    trial_list : list of np.ndarray
        Flat collection of 1-D trial arrays to average (e.g. all trials from
        all files pooled together for a cross-file batch average).

    Returns
    -------
    np.ndarray or None
        Grand-average array, or ``None`` when *trial_list* is empty.
    """
    if not trial_list:
        return None

    lengths = [len(t) for t in trial_list]
    max_len = max(lengths)

    if len(set(lengths)) == 1:
        # Fast path: all arrays share the same length
        return np.mean(np.array(trial_list), axis=0)

    # NaN-pad shorter arrays so nanmean keeps the full time axis intact
    padded = np.full((len(trial_list), max_len), np.nan)
    for i, trace in enumerate(trial_list):
        padded[i, : len(trace)] = trace

    return np.nanmean(padded, axis=0)
