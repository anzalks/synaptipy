"""Core Domain Data Models for Synaptipy."""

from pathlib import Path
from typing import Dict, List, Optional, Tuple
import numpy as np
import logging # Added logging

log = logging.getLogger(__name__) # Added logger

class Channel:
    """Represents a single channel of data across one or more trials."""
    def __init__(self, id: str, name: str, units: str, sampling_rate: float, data_trials: List[np.ndarray]):
        self.id = id
        self.name = name
        self.units = units
        self.sampling_rate = sampling_rate
        self.data_trials = data_trials # List of 1D numpy arrays
        self.t_start = 0.0 # Time of the first sample relative to recording start

    # ... (previous properties: num_trials, num_samples) ...
    @property
    def num_trials(self) -> int:
        """Number of trials/segments available for this channel."""
        return len(self.data_trials)

    @property
    def num_samples(self) -> int:
        """Number of samples in the first trial (assuming all are same length)."""
        # Be more robust: check if trials have varying lengths
        if not self.data_trials:
            return 0
        lengths = {arr.shape[0] for arr in self.data_trials}
        if len(lengths) > 1:
            log.warning(f"Channel '{self.name}' has trials with varying lengths: {lengths}. `num_samples` returning length of first trial.")
        return self.data_trials[0].shape[0]

    def get_time_vector(self, trial_index: int = 0) -> Optional[np.ndarray]:
        """Returns a time vector for the specified trial."""
        if not self.data_trials or trial_index >= len(self.data_trials):
            log.error(f"Requested time vector for non-existent trial {trial_index} in channel '{self.name}'")
            return None
        num_samples_trial = self.data_trials[trial_index].shape[0] # Use length of specific trial
        if self.sampling_rate <= 0:
             log.error(f"Invalid sampling rate ({self.sampling_rate}) for channel '{self.name}'")
             return None
        # Calculate duration based on the specific trial's length
        duration_trial = num_samples_trial / self.sampling_rate
        # Assume t_start applies to the beginning of each trial conceptually
        # If neo segments have different t_starts, the adapter needs to handle this better.
        return np.linspace(self.t_start, self.t_start + duration_trial, num_samples_trial, endpoint=False)

    def get_data(self, trial_index: int = 0) -> Optional[np.ndarray]:
        """Returns the data array for the specified trial."""
        if not self.data_trials or trial_index >= len(self.data_trials):
            log.error(f"Requested data for non-existent trial {trial_index} in channel '{self.name}'")
            return None
        return self.data_trials[trial_index]

    def get_averaged_data(self) -> Optional[np.ndarray]:
        """
        Calculates the average trace across all trials.

        Returns:
            A 1D numpy array containing the averaged data, or None if averaging
            is not possible (e.g., no trials, trials of different lengths).
        """
        if not self.data_trials:
            log.warning(f"Cannot average channel '{self.name}': No trials available.")
            return None

        # Check for consistent trial lengths
        first_trial_len = self.data_trials[0].shape[0]
        if not all(arr.shape[0] == first_trial_len for arr in self.data_trials):
            log.error(f"Cannot average channel '{self.name}': Trials have different lengths.")
            # Option: Add logic here to pad/truncate if desired, but error is safer.
            return None

        try:
            # Stack trials into a 2D array (trials x samples) and calculate mean along axis 0
            stacked_trials = np.stack(self.data_trials)
            averaged_data = np.mean(stacked_trials, axis=0)
            return averaged_data
        except Exception as e:
            log.error(f"Error calculating average for channel '{self.name}': {e}", exc_info=True)
            return None

    def get_averaged_time_vector(self) -> Optional[np.ndarray]:
         """Returns a time vector suitable for the averaged data."""
         avg_data = self.get_averaged_data() # Calculate average first to check eligibility
         if avg_data is None:
             return None # Averaging not possible

         num_samples_avg = avg_data.shape[0]
         if self.sampling_rate <= 0:
             log.error(f"Invalid sampling rate ({self.sampling_rate}) for channel '{self.name}'")
             return None

         duration_avg = num_samples_avg / self.sampling_rate
         return np.linspace(self.t_start, self.t_start + duration_avg, num_samples_avg, endpoint=False)


class Recording:
    """Represents data and metadata from a single recording file."""
    def __init__(self, source_file: Path):
        self.source_file: Path = source_file
        self.channels: Dict[str, Channel] = {} # Key: Channel ID
        self.sampling_rate: Optional[float] = None # Global sampling rate (Hz)
        self.duration: Optional[float] = None      # Estimated duration (seconds)
        self.t_start: Optional[float] = None       # Global start time (seconds)
        # --- Added for NWB ---
        self.session_start_time_dt: Optional[datetime] = None # Actual datetime object
        # ---
        self.protocol_name: Optional[str] = None
        self.injected_current: Optional[float] = None
        self.metadata: Dict = {} # Other miscellaneous metadata like neo block annotations

    # ... (previous properties: num_channels, channel_names, max_trials) ...
    @property
    def num_channels(self) -> int:
        return len(self.channels)

    @property
    def channel_names(self) -> List[str]:
        return [ch.name for ch in self.channels.values()]

    @property
    def max_trials(self) -> int:
        """Maximum number of trials found across all channels."""
        if not self.channels:
            return 0
        # Handle case where a channel might have 0 trials if loading failed partially
        num_trials_list = [ch.num_trials for ch in self.channels.values()]
        return max(num_trials_list) if num_trials_list else 0

# Need datetime for NWB
from datetime import datetime, timezone # Added timezone
import uuid # Added for NWB identifier

class Experiment:
    """Optional: Represents a collection of Recordings."""
    def __init__(self):
        self.recordings: List[Recording] = []
        self.metadata: Dict = {}