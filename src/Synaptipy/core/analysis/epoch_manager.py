# src/Synaptipy/core/analysis/epoch_manager.py
# -*- coding: utf-8 -*-
"""
EpochManager - Hardware TTL and manual experimental epoch management.

Experimental recordings often contain distinct phases (Baseline, Stimulation,
Washout).  :class:`EpochManager` either auto-detects these boundaries from a
TTL/Digital-Input channel or lets the researcher define them manually.

Once epochs are defined, per-epoch data slices can be extracted from any
:class:`~Synaptipy.core.data_model.Channel` for downstream analysis
(e.g. tracking plasticity changes across Stim vs. Baseline).
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from Synaptipy.core.analysis.evoked_responses import extract_ttl_epochs

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Epoch dataclass
# ---------------------------------------------------------------------------


@dataclass
class Epoch:
    """A named time window within a recording.

    Attributes:
        name: Human-readable label (e.g. ``"Baseline"``, ``"Stim"``, ``"Washout"``).
        start_time: Epoch start in seconds (relative to recording onset).
        end_time: Epoch end in seconds.
        epoch_type: Either ``"ttl"`` (auto-detected from hardware) or ``"manual"``.
        metadata: Optional arbitrary key/value annotations.
    """

    name: str
    start_time: float
    end_time: float
    epoch_type: str = "manual"
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def duration(self) -> float:
        """Epoch duration in seconds."""
        return max(0.0, self.end_time - self.start_time)

    def contains(self, t: float) -> bool:
        """Return ``True`` if time *t* falls within ``[start_time, end_time]``."""
        return self.start_time <= t <= self.end_time

    def __repr__(self) -> str:
        return (
            f"Epoch(name='{self.name}', start={self.start_time:.4f} s, "
            f"end={self.end_time:.4f} s, type='{self.epoch_type}')"
        )


# ---------------------------------------------------------------------------
# EpochManager
# ---------------------------------------------------------------------------


class EpochManager:
    """Manage experimental epoch boundaries for a recording.

    Epochs are ordered by :attr:`Epoch.start_time`.  Overlapping epochs are
    allowed so that the same window can be labelled with multiple semantic tags.

    Typical workflow::

        em = EpochManager()

        # Option A: auto-detect from a TTL channel
        em.from_ttl(ttl_data, time_vector, pre_stim_s=1.0, post_stim_s=1.0)

        # Option B: manual definition
        em.add_manual_epoch("Baseline", 0.0, 60.0)
        em.add_manual_epoch("Stim",     60.0, 120.0)
        em.add_manual_epoch("Washout",  120.0, 300.0)

        # Slice channel data by epoch
        slices = em.get_epoch_slices(channel, trial_index=0)
    """

    DEFAULT_EPOCH_NAMES = ("Baseline", "Stim", "Washout")

    def __init__(self) -> None:
        self._epochs: List[Epoch] = []

    # ------------------------------------------------------------------
    # Read-only properties
    # ------------------------------------------------------------------

    @property
    def epochs(self) -> List[Epoch]:
        """Sorted list of all defined epochs."""
        return sorted(self._epochs, key=lambda e: e.start_time)

    @property
    def epoch_names(self) -> List[str]:
        """Names of all defined epochs in time order."""
        return [e.name for e in self.epochs]

    def __len__(self) -> int:
        return len(self._epochs)

    def __repr__(self) -> str:
        return f"EpochManager({len(self._epochs)} epochs: {self.epoch_names})"

    # ------------------------------------------------------------------
    # Epoch creation
    # ------------------------------------------------------------------

    def add_manual_epoch(self, name: str, start_time: float, end_time: float, **metadata: Any) -> Epoch:
        """Add a manually defined epoch.

        Args:
            name: Label for the epoch.
            start_time: Start time in seconds.
            end_time: End time in seconds.
            **metadata: Optional key/value annotations stored in :attr:`Epoch.metadata`.

        Returns:
            The newly created :class:`Epoch`.

        Raises:
            ValueError: If *end_time* <= *start_time*.
        """
        if end_time <= start_time:
            raise ValueError(f"Epoch '{name}': end_time ({end_time}) must be > start_time ({start_time}).")
        epoch = Epoch(
            name=name,
            start_time=float(start_time),
            end_time=float(end_time),
            epoch_type="manual",
            metadata=dict(metadata),
        )
        self._epochs.append(epoch)
        log.debug("Manual epoch added: %r", epoch)
        return epoch

    def from_ttl(
        self,
        ttl_data: np.ndarray,
        time: np.ndarray,
        ttl_threshold: float = 2.5,
        pre_stim_s: float = 1.0,
        post_stim_s: float = 1.0,
        min_inter_epoch_s: float = 0.5,
        stim_name: str = "Stim",
        baseline_name: str = "Baseline",
        washout_name: str = "Washout",
    ) -> List[Epoch]:
        """Auto-generate epochs from a TTL / Digital-Input channel.

        Detects TTL pulse boundaries using :func:`~Synaptipy.core.analysis.evoked_responses.extract_ttl_epochs`,
        then creates:

        * A *Baseline* epoch from ``time[0]`` to ``first_onset - pre_stim_s``.
        * A *Stim* epoch spanning the detected TTL activity
          (``first_onset - pre_stim_s`` to ``last_offset + post_stim_s``).
        * A *Washout* epoch from ``last_offset + post_stim_s`` to ``time[-1]``,
          if enough time remains.

        Returns:
            List of the newly created :class:`Epoch` objects.  The manager's
            :attr:`epochs` list is also updated in place.
        """
        if ttl_data is None or ttl_data.size == 0 or time is None or time.size == 0:
            log.warning("from_ttl: empty TTL data provided; no epochs created.")
            return []

        onsets, offsets = extract_ttl_epochs(ttl_data, time, threshold=ttl_threshold)

        if onsets.size == 0:
            log.warning("from_ttl: no TTL pulses detected above threshold %.3f.", ttl_threshold)
            return []

        t_start = float(time[0])
        t_end = float(time[-1])
        first_onset = float(onsets[0])
        last_offset = float(offsets[-1]) if offsets.size > 0 else float(onsets[-1])

        # Build TTL-derived stim epoch
        stim_start = max(t_start, first_onset - pre_stim_s)
        stim_end = min(t_end, last_offset + post_stim_s)

        created: List[Epoch] = []

        # Baseline (only if there is meaningful pre-stim time)
        if stim_start - t_start >= min_inter_epoch_s:
            created.append(self.add_manual_epoch(baseline_name, t_start, stim_start, source="ttl_auto"))
            # Override epoch_type to reflect TTL origin
            created[-1].epoch_type = "ttl"

        # Stim
        stim_epoch = self.add_manual_epoch(
            stim_name, stim_start, stim_end, n_pulses=int(onsets.size), source="ttl_auto"
        )
        stim_epoch.epoch_type = "ttl"
        created.append(stim_epoch)

        # Washout (only if there is meaningful post-stim time)
        if t_end - stim_end >= min_inter_epoch_s:
            washout_epoch = self.add_manual_epoch(washout_name, stim_end, t_end, source="ttl_auto")
            washout_epoch.epoch_type = "ttl"
            created.append(washout_epoch)

        log.info("from_ttl: created %d epochs from %d TTL pulse(s).", len(created), int(onsets.size))
        return created

    # ------------------------------------------------------------------
    # Querying
    # ------------------------------------------------------------------

    def get_epoch(self, name: str) -> Optional[Epoch]:
        """Return the first epoch whose name matches *name* (case-insensitive)."""
        name_lower = name.lower()
        for epoch in self._epochs:
            if epoch.name.lower() == name_lower:
                return epoch
        return None

    def epochs_at_time(self, t: float) -> List[Epoch]:
        """Return all epochs that contain time *t*."""
        return [e for e in self._epochs if e.contains(t)]

    # ------------------------------------------------------------------
    # Data extraction
    # ------------------------------------------------------------------

    def get_epoch_slices(
        self,
        channel: Any,
        trial_index: int = 0,
    ) -> Dict[str, Tuple[np.ndarray, np.ndarray]]:
        """Extract (data, time) slices for every epoch from a channel trial.

        Args:
            channel: A :class:`~Synaptipy.core.data_model.Channel` instance.
            trial_index: Which trial to slice (default 0).

        Returns:
            Dict mapping epoch name to ``(data_slice, time_slice)`` ndarrays.
            Epochs with no overlapping samples map to empty arrays.
        """
        result: Dict[str, Tuple[np.ndarray, np.ndarray]] = {}

        data = channel.get_data(trial_index)
        time = channel.get_relative_time_vector(trial_index)

        if data is None or time is None or data.size == 0:
            log.warning("get_epoch_slices: no data for channel '%s' trial %d.", channel.name, trial_index)
            for epoch in self.epochs:
                result[epoch.name] = (np.array([]), np.array([]))
            return result

        for epoch in self.epochs:
            mask = (time >= epoch.start_time) & (time <= epoch.end_time)
            result[epoch.name] = (data[mask], time[mask])

        return result

    # ------------------------------------------------------------------
    # Modification
    # ------------------------------------------------------------------

    def remove_epoch(self, name: str) -> bool:
        """Remove the first epoch matching *name*.

        Returns:
            ``True`` if an epoch was removed, ``False`` if not found.
        """
        for i, epoch in enumerate(self._epochs):
            if epoch.name.lower() == name.lower():
                self._epochs.pop(i)
                log.debug("Removed epoch '%s'.", name)
                return True
        return False

    def clear(self) -> None:
        """Remove all epochs."""
        self._epochs.clear()
        log.debug("EpochManager cleared.")
