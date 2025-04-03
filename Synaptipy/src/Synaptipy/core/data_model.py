# -*- coding: utf-8 -*-
"""
Core Domain Data Models for Synaptipy.

Defines the central classes representing electrophysiology concepts like
Recording sessions and individual data Channels.
"""

import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import numpy as np
from datetime import datetime, timezone # Required for Recording timestamp

# Configure logger for this module
log = logging.getLogger(__name__)


class Channel:
    """
    Represents a single channel of recorded data, potentially across multiple
    trials or segments.
    """
    def __init__(self, id: str, name: str, units: str, sampling_rate: float, data_trials: List[np.ndarray]):
        """
        Initializes a Channel object.

        Args:
            id: A unique identifier for the channel (e.g., '0', '1', 'Vm').
            name: A descriptive name for the channel (e.g., 'Voltage', 'IN_0').
            units: The physical units of the data (e.g., 'mV', 'pA', 'V').
            sampling_rate: The sampling frequency in Hz.
            data_trials: A list where each element is a 1D NumPy array
                         representing the data for one trial/segment.
        """
        self.id: str = id
        self.name: str = name
        self.units: str = units if units else "unknown" # Ensure units is a string
        self.sampling_rate: float = sampling_rate
        # Ensure data_trials is a list of numpy arrays
        if not isinstance(data_trials, list) or not all(isinstance(t, np.ndarray) for t in data_trials):
             log.warning(f"Channel '{name}' received non-list or non-ndarray data. Attempting conversion.")
             # Attempt conversion or raise error? For now, assign but warn.
             try:
                 self.data_trials: List[np.ndarray] = [np.asarray(t) for t in data_trials]
             except Exception:
                 log.error(f"Could not convert data_trials for channel '{name}' to list of arrays.")
                 self.data_trials = []
        else:
             self.data_trials: List[np.ndarray] = data_trials

        self.t_start: float = 0.0 # Absolute start time of the first sample relative to recording start (set by adapter)

    @property
    def num_trials(self) -> int:
        """Returns the number of trials/segments available for this channel."""
        return len(self.data_trials)

    @property
    def num_samples(self) -> int:
        """
        Returns the number of samples in the first trial.
        Warns if trials have different lengths. Assumes at least one trial exists.
        Returns 0 if no trials are present.
        """
        if not self.data_trials:
            return 0
        first_trial_len = self.data_trials[0].shape[0]
        lengths = {arr.shape[0] for arr in self.data_trials}
        if len(lengths) > 1:
            log.warning(f"Channel '{self.name}' has trials with varying lengths: {lengths}. `num_samples` returning length of first trial ({first_trial_len}).")
        return first_trial_len

    def get_data(self, trial_index: int = 0) -> Optional[np.ndarray]:
        """
        Returns the data array (1D NumPy array) for the specified trial index.
        Returns None if the trial index is invalid.
        """
        if not isinstance(trial_index, int) or not (0 <= trial_index < self.num_trials):
            log.debug(f"Invalid trial index {trial_index} requested for channel '{self.name}' (has {self.num_trials} trials).")
            return None
        return self.data_trials[trial_index]

    def get_time_vector(self, trial_index: int = 0) -> Optional[np.ndarray]:
        """
        Returns an absolute time vector (relative to recording start) for the
        specified trial index. Vector length matches the data length for that trial.
        Returns None if index is invalid or sampling rate is invalid.
        """
        data = self.get_data(trial_index)
        if data is None:
            return None # Invalid index handled by get_data

        num_samples_trial = data.shape[0]
        if not isinstance(self.sampling_rate, (int, float)) or self.sampling_rate <= 0:
             log.error(f"Invalid sampling rate ({self.sampling_rate}) for channel '{self.name}'. Cannot calculate time vector.")
             return None

        duration_trial = num_samples_trial / self.sampling_rate
        # Absolute time based on the channel's t_start (relative to recording)
        return np.linspace(self.t_start, self.t_start + duration_trial, num_samples_trial, endpoint=False)

    def get_relative_time_vector(self, trial_index: int = 0) -> Optional[np.ndarray]:
        """
        Returns a relative time vector (starting from 0) for the specified trial index.
        Useful for overlaying trials or aligning events.
        Returns None if index is invalid or sampling rate is invalid.
        """
        data = self.get_data(trial_index)
        if data is None:
            return None # Invalid index handled by get_data

        num_samples_trial = data.shape[0]
        if not isinstance(self.sampling_rate, (int, float)) or self.sampling_rate <= 0:
             log.error(f"Invalid sampling rate ({self.sampling_rate}) for channel '{self.name}'. Cannot calculate relative time vector.")
             return None

        duration_trial = num_samples_trial / self.sampling_rate
        # Relative time, starting from 0
        return np.linspace(0.0, duration_trial, num_samples_trial, endpoint=False)

    def get_averaged_data(self) -> Optional[np.ndarray]:
        """
        Calculates the average trace across all trials for this channel.

        Returns:
            A 1D NumPy array containing the averaged data, or None if averaging
            is not possible (e.g., no trials, trials of different lengths, non-numeric data).
        """
        if self.num_trials == 0:
            log.debug(f"Cannot average channel '{self.name}': No trials available.")
            return None
        if self.num_trials == 1:
            log.debug(f"Only one trial for channel '{self.name}'. Returning it as 'average'.")
            return self.data_trials[0].copy() # Return a copy

        try:
            # Check for consistent trial lengths
            first_trial_len = self.data_trials[0].shape[0]
            if not all(arr.shape[0] == first_trial_len for arr in self.data_trials):
                log.error(f"Cannot average channel '{self.name}': Trials have different lengths.")
                return None

            # Check data types (basic check)
            if not all(np.issubdtype(arr.dtype, np.number) for arr in self.data_trials):
                 log.error(f"Cannot average channel '{self.name}': Contains non-numeric data.")
                 return None

            # Stack trials into a 2D array (trials x samples) and calculate mean along axis 0
            stacked_trials = np.stack(self.data_trials)
            averaged_data = np.mean(stacked_trials, axis=0)
            return averaged_data
        except ValueError as ve: # Catches stacking errors if shapes somehow differ despite check
             log.error(f"ValueError during averaging stack for channel '{self.name}': {ve}. Check trial shapes.")
             return None
        except Exception as e:
            log.error(f"Unexpected error calculating average for channel '{self.name}': {e}", exc_info=True)
            return None

    def get_averaged_time_vector(self) -> Optional[np.ndarray]:
         """
         Returns an absolute time vector (relative to recording start) suitable
         for the averaged data.
         Returns None if averaging is not possible or sampling rate is invalid.
         """
         # Check if averaging possible first by trying to get the data
         avg_data = self.get_averaged_data()
         if avg_data is None:
             return None

         num_samples_avg = avg_data.shape[0]
         if not isinstance(self.sampling_rate, (int, float)) or self.sampling_rate <= 0:
             log.error(f"Invalid sampling rate ({self.sampling_rate}) for channel '{self.name}'. Cannot calculate averaged time vector.")
             return None

         duration_avg = num_samples_avg / self.sampling_rate
         # Absolute time
         return np.linspace(self.t_start, self.t_start + duration_avg, num_samples_avg, endpoint=False)

    def get_relative_averaged_time_vector(self) -> Optional[np.ndarray]:
         """
         Returns a relative time vector (starting at 0) suitable for the averaged data.
         Returns None if averaging is not possible or sampling rate is invalid.
         """
         # Check if averaging possible first
         avg_data = self.get_averaged_data()
         if avg_data is None:
             return None

         num_samples_avg = avg_data.shape[0]
         if not isinstance(self.sampling_rate, (int, float)) or self.sampling_rate <= 0:
             log.error(f"Invalid sampling rate ({self.sampling_rate}) for channel '{self.name}'. Cannot calculate relative averaged time vector.")
             return None

         duration_avg = num_samples_avg / self.sampling_rate
         # Relative time
         return np.linspace(0.0, duration_avg, num_samples_avg, endpoint=False)


class Recording:
    """
    Represents data and metadata loaded from a single recording file.
    Contains multiple Channel objects.
    """
    def __init__(self, source_file: Path):
        """
        Initializes a Recording object.

        Args:
            source_file: The Path object pointing to the original data file.
        """
        self.source_file: Path = source_file
        self.channels: Dict[str, Channel] = {} # Key: Channel ID
        self.sampling_rate: Optional[float] = None # Global sampling rate (Hz)
        self.duration: Optional[float] = None      # Estimated duration (seconds), often based on first channel/trial
        self.t_start: Optional[float] = None       # Global start time (seconds), relative to session/block start
        self.session_start_time_dt: Optional[datetime] = None # Actual datetime object of session start, if available
        self.protocol_name: Optional[str] = None
        self.injected_current: Optional[float] = None # Estimated current range (e.g., from Axon)
        self.metadata: Dict = {} # Other miscellaneous metadata (e.g., from neo block annotations)

    @property
    def num_channels(self) -> int:
        """Returns the number of channels in this recording."""
        return len(self.channels)

    @property
    def channel_names(self) -> List[str]:
        """Returns a list of the names of all channels."""
        return [ch.name for ch in self.channels.values() if hasattr(ch, 'name')]

    @property
    def max_trials(self) -> int:
        """
        Returns the maximum number of trials found across all channels in this recording.
        Returns 0 if there are no channels or no trials.
        """
        if not self.channels:
            return 0
        # Use the num_trials property of each channel
        num_trials_list = [ch.num_trials for ch in self.channels.values()]
        return max(num_trials_list) if num_trials_list else 0


class Experiment:
    """
    Optional container representing a collection of Recordings, potentially
    from a single experimental session or related set. (Currently basic).
    """
    def __init__(self):
        self.recordings: List[Recording] = []
        self.metadata: Dict = {} # Metadata about the overall experiment
        self.identifier: str = str(uuid.uuid4()) # Example unique ID for the experiment