# src/synaptipy/core/analysis/cross_file_utils.py
# -*- coding: utf-8 -*-
"""
Pure-math utility functions for cross-file trial averaging.

These functions contain no Qt or GUI dependencies and operate only on
NumPy arrays together with the NeoAdapter/Recording domain types.  They
are extracted from BaseAnalysisTab so that they can be tested in isolation
and reused from non-GUI code paths (e.g. batch engine, CLI).
"""

import logging
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from synaptipy.core.averaging import compute_time_aligned_average

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class CompatibilityEntry:
    """One source's inclusion decision for a cross-file average."""

    source: str
    included: bool
    reason: str
    channel_id: str
    source_units: str = ""
    canonical_units: str = ""


@dataclass
class CrossFileCompatibilityReport:
    """Machine-readable provenance for a cross-file average."""

    channel_id: str
    canonical_units: str = ""
    alignment: str = "relative acquisition time"
    entries: List[CompatibilityEntry] = None

    def __post_init__(self) -> None:
        if self.entries is None:
            self.entries = []

    @property
    def excluded_entries(self) -> List[CompatibilityEntry]:
        return [entry for entry in self.entries if not entry.included]

    def as_dict(self) -> Dict[str, Any]:
        return {
            "channel_id": self.channel_id,
            "canonical_units": self.canonical_units,
            "alignment": self.alignment,
            "included_sources": sum(entry.included for entry in self.entries),
            "excluded_sources": len(self.excluded_entries),
            "entries": [asdict(entry) for entry in self.entries],
        }


@dataclass(frozen=True)
class CrossFileAverageResult:
    """One cross-file average together with its scientific provenance."""

    time: Optional[np.ndarray]
    data: Optional[np.ndarray]
    contributing_file_count: int
    has_unequal_lengths: bool
    compatibility_report: CrossFileCompatibilityReport

    @property
    def is_empty(self) -> bool:
        return self.time is None or self.data is None or self.contributing_file_count == 0


def canonical_unit_and_scale(units: Any) -> Tuple[Optional[str], Optional[float]]:
    """Return a canonical electrophysiology unit and scale, or ``(None, None)``.

    The scale converts the supplied unit to the canonical unit.  Unknown or
    dimensionless channels are deliberately not pooled: treating them as a
    voltage/current signal would make a numerical result look scientifically
    meaningful when its physical dimension is unknown.
    """
    normalized = str(units or "").strip().lower().replace(" ", "")
    aliases = {
        "v": ("mV", 1_000.0),
        "volt": ("mV", 1_000.0),
        "volts": ("mV", 1_000.0),
        "mv": ("mV", 1.0),
        "millivolt": ("mV", 1.0),
        "millivolts": ("mV", 1.0),
        "uv": ("mV", 0.001),
        "µv": ("mV", 0.001),
        "a": ("pA", 1_000_000_000_000.0),
        "amp": ("pA", 1_000_000_000_000.0),
        "ampere": ("pA", 1_000_000_000_000.0),
        "amperes": ("pA", 1_000_000_000_000.0),
        "na": ("pA", 1_000.0),
        "nanoampere": ("pA", 1_000.0),
        "nanoamperes": ("pA", 1_000.0),
        "pa": ("pA", 1.0),
        "picoampere": ("pA", 1.0),
        "picoamperes": ("pA", 1.0),
    }
    return aliases.get(normalized, (None, None))


def _source_label(item: Dict[str, Any]) -> str:
    path = item.get("path", "<unknown>")
    return Path(str(path)).name or str(path)


def _channel_for_item(recording: Any, channel_idx: int, channel_id: Optional[str]) -> Optional[Any]:
    if channel_id is not None:
        # Qt comboboxes may round-trip an ID as an int while recordings use strings.
        return recording.channels.get(channel_id) or recording.channels.get(str(channel_id))
    channels_sorted = sorted(recording.channels.items())
    return channels_sorted[channel_idx][1] if channel_idx < len(channels_sorted) else None


def time_bases_compatible(reference_time: np.ndarray, candidate_time: np.ndarray) -> bool:
    """Return whether two trace time axes represent the same sample grid.

    Unequal recording duration is allowed: only their overlapping prefix must
    agree.  A differing start time or sample interval means that equal array
    indices represent different physical times and must never be averaged.
    """
    reference = np.asarray(reference_time, dtype=float)
    candidate = np.asarray(candidate_time, dtype=float)
    overlap = min(reference.size, candidate.size)
    if overlap == 0 or not (np.all(np.isfinite(reference)) and np.all(np.isfinite(candidate))):
        return False
    if reference.size > 1 and np.any(np.diff(reference) <= 0):
        return False
    if candidate.size > 1 and np.any(np.diff(candidate) <= 0):
        return False

    scale = max(float(np.max(np.abs(reference))), float(np.max(np.abs(candidate))), 1.0)
    atol = scale * 1e-10
    same_start = np.isclose(reference[0], candidate[0], rtol=1e-7, atol=atol)
    same_end = np.isclose(reference[-1], candidate[-1], rtol=1e-7, atol=atol)
    if same_start and same_end:
        # Different sampling rates are safe when the recordings span the same
        # physical interval; callers interpolate before averaging.
        return True
    if reference.size < 2 or candidate.size < 2:
        return False
    reference_step = float(np.median(np.diff(reference)))
    candidate_step = float(np.median(np.diff(candidate)))
    return bool(same_start and np.isclose(reference_step, candidate_step, rtol=1e-6, atol=atol))


def average_time_aligned_trials(
    trial_list: List[np.ndarray], time_list: List[np.ndarray]
) -> Tuple[Optional[np.ndarray], Optional[np.ndarray]]:
    """Interpolate compatible traces to one physical time axis before averaging."""
    average = compute_time_aligned_average(trial_list, time_list)
    return average.time, average.data


def sampling_rate_from_timebase(time_vector: np.ndarray) -> Optional[float]:
    """Derive the effective Hz rate from the actual analysis time axis."""
    time = np.asarray(time_vector, dtype=float)
    if time.size < 2 or not np.all(np.isfinite(time)):
        return None
    dt = float(np.median(np.diff(time)))
    return 1.0 / dt if dt > 0 and np.isfinite(dt) else None


def _resolve_effective_trials(item: Dict[str, Any], parsed_trials: List[int]) -> List[int]:
    """Return the list of trial indices to use for *item* within *channel*.

    ``"Current Trial"`` items specify their own ``trial_index``.  Every other
    item honours the user-selected *parsed_trials* list, including full
    ``"Recording"`` entries selected from the project tree.
    """
    if item.get("target_type") == "Current Trial" and item.get("trial_index") is not None:
        return [item["trial_index"]]
    return parsed_trials


def extract_per_file_trace(  # noqa: C901 - validates all file/channel/trial failure modes at one boundary
    item: Dict[str, Any],
    parsed_trials: List[int],
    channel_idx: int,
    neo_adapter: Any,
    channel_id: Optional[str] = None,
    unit_scale: float = 1.0,
    recording: Optional[Any] = None,
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
                       returns a :class:`~synaptipy.core.data_model.Recording`
                       or ``None``.

    Returns:
        ``(time_array, averaged_data)`` or ``None`` when the item cannot
        contribute a valid trace.
    """
    path = item.get("path")
    if not path:
        return None

    try:
        recording = recording if recording is not None else neo_adapter.read_recording(path)
        if recording is None:
            log.debug("Cross-file avg: could not load %s", path)
            return None

        channel = _channel_for_item(recording, channel_idx, channel_id)
        if channel is None:
            if channel_id is not None:
                log.debug("Cross-file avg: %s does not contain channel ID %s", path, channel_id)
            else:
                log.debug(
                    "Cross-file avg: %s has fewer channels than index %d - skipping",
                    path,
                    channel_idx,
                )
            return None

        # Determine which trials to use for this item.
        effective_trials = _resolve_effective_trials(item, parsed_trials)

        file_traces: List[np.ndarray] = []
        file_times: List[np.ndarray] = []
        for trial_idx in effective_trials:
            trial_data = channel.get_data(trial_idx)
            trial_time = channel.get_relative_time_vector(trial_idx)
            if trial_data is None or trial_time is None:
                raise ValueError(f"Trial {trial_idx} returned None data in {getattr(path, 'name', path)}")
            file_traces.append(np.asarray(trial_data, dtype=float) * unit_scale)
            file_times.append(trial_time)

        if not file_traces:
            return None

        if any(not time_bases_compatible(file_times[0], time) for time in file_times[1:]):
            log.warning("Cross-file avg: trials in %s have incompatible time bases; excluding file.", path)
            return None
        file_time, file_avg = average_time_aligned_trials(file_traces, file_times)
        return (file_time, file_avg) if file_time is not None and file_avg is not None else None

    except (IndexError, ValueError) as exc:
        log.debug("Cross-file avg: skipping %s: %s", path, exc)
        return None


def compute_cross_file_average(  # noqa: C901 - compatibility report requires explicit exclusion branches
    items: List[Dict[str, Any]],
    parsed_trials: List[int],
    channel_idx: int,
    neo_adapter: Any,
    channel_id: Optional[str] = None,
) -> CrossFileAverageResult:
    """Compute an average and a complete per-source compatibility report.

    Inputs are pooled only when they have the selected *channel ID*, a known
    compatible physical unit (converted to mV or pA), and a compatible time
    origin/grid.  Every rejection is retained in the returned report.
    """
    report = CrossFileCompatibilityReport(channel_id=str(channel_id if channel_id is not None else channel_idx))
    valid_traces: List[np.ndarray] = []
    valid_times: List[np.ndarray] = []

    for item in items:
        source = _source_label(item)
        path = item.get("path")
        try:
            recording = neo_adapter.read_recording(path) if path else None
        except Exception as exc:  # noqa: BLE001 - report a third-party reader failure
            report.entries.append(
                CompatibilityEntry(source, False, f"could not load recording: {exc}", report.channel_id)
            )
            continue
        if recording is None:
            report.entries.append(CompatibilityEntry(source, False, "could not load recording", report.channel_id))
            continue
        channel = _channel_for_item(recording, channel_idx, channel_id)
        if channel is None:
            report.entries.append(CompatibilityEntry(source, False, "selected channel is absent", report.channel_id))
            continue
        unit, scale = canonical_unit_and_scale(getattr(channel, "units", ""))
        if unit is None or scale is None:
            report.entries.append(
                CompatibilityEntry(
                    source,
                    False,
                    "channel has unknown or unsupported physical units",
                    report.channel_id,
                    str(getattr(channel, "units", "")),
                )
            )
            continue
        if report.canonical_units and report.canonical_units != unit:
            report.entries.append(
                CompatibilityEntry(
                    source,
                    False,
                    "physical dimension differs from included channels",
                    report.channel_id,
                    str(channel.units),
                    unit,
                )
            )
            continue
        result = extract_per_file_trace(
            item,
            parsed_trials,
            channel_idx,
            neo_adapter,
            channel_id=channel_id,
            unit_scale=scale,
            recording=recording,
        )
        if result is not None:
            file_time, file_avg = result
            if valid_times and not time_bases_compatible(valid_times[0], file_time):
                log.warning(
                    "Cross-file average: excluding %s because its time base differs from the first valid file. "
                    "Resample recordings to a common sampling rate/time origin before averaging.",
                    item.get("path", "<unknown>"),
                )
                report.entries.append(
                    CompatibilityEntry(
                        source,
                        False,
                        "time base is incompatible with included recordings",
                        report.channel_id,
                        str(channel.units),
                        unit,
                    )
                )
                continue
            valid_traces.append(file_avg)
            valid_times.append(file_time)
            report.canonical_units = unit
            report.entries.append(
                CompatibilityEntry(source, True, "included", report.channel_id, str(channel.units), unit)
            )
        else:
            report.entries.append(
                CompatibilityEntry(
                    source,
                    False,
                    "selected trials are unavailable or internally incompatible",
                    report.channel_id,
                    str(channel.units),
                    unit,
                )
            )

    if not valid_traces:
        return CrossFileAverageResult(None, None, 0, False, report)

    lengths = [len(t) for t in valid_traces]
    has_unequal_lengths = len(set(lengths)) > 1
    max_len = max(lengths)

    if has_unequal_lengths:
        min_len = min(lengths)
        log.warning(
            "Cross-file average: unequal trace lengths detected across %d files. "
            "min=%d samples, max=%d samples. "
            "Traces are aligned by physical time; effective N decreases "
            "outside the shorter recordings' acquisition interval.",
            len(valid_traces),
            min_len,
            max_len,
        )

    reference_time, grand_average = average_time_aligned_trials(valid_traces, valid_times)
    if reference_time is None or grand_average is None:
        return CrossFileAverageResult(None, None, 0, False, report)

    return CrossFileAverageResult(
        reference_time,
        grand_average,
        len(valid_traces),
        has_unequal_lengths,
        report,
    )


def build_averaged_recording(
    items: List[Dict[str, Any]],
    trial_indices: List[int],
    neo_adapter: Any,
    label: str = "multifile_average",
) -> Optional[Any]:
    """Build a synthetic ``Recording`` whose channels each hold one averaged trial.

    For every channel position found in the first loadable file the function
    calls :func:`compute_cross_file_average` to compute the grand average across
    all *items*.  The resulting per-channel average is stored as the sole trial
    of a new :class:`~synaptipy.core.data_model.Recording` whose
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

    from synaptipy.core.data_model import Channel, Recording

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
        average_result = compute_cross_file_average(items, trial_indices, ch_idx, neo_adapter, channel_id=ref_ch_id)
        time_arr = average_result.time
        avg_arr = average_result.data
        n_files = average_result.contributing_file_count
        report = average_result.compatibility_report
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
            sampling_rate=sampling_rate_from_timebase(time_arr) or ref_ch.sampling_rate,
            data_trials=[avg_arr],
        )
        ch.t_start = float(time_arr[0]) if len(time_arr) > 0 else 0.0
        ch.metadata["n_files_averaged"] = n_files
        ch.metadata["trial_indices"] = trial_indices
        ch.metadata["cross_file_compatibility"] = report.as_dict()
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
    rec.metadata["cross_file_alignment"] = "relative acquisition time"
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
