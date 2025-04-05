# src/Synaptipy/core/data_model.py
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
log = logging.getLogger('Synaptipy.core.data_model') # Use specific logger name


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
        # --- Core Attributes (Assigned ONCE) ---
        self.id: str = id
        self.name: str = name
        self.units: str = units if units else "unknown" # Ensure units is a string
        self.sampling_rate: float = sampling_rate
        self.t_start: float = 0.0 # Absolute start time relative to recording start (set by adapter)

        # --- Data Trials Validation and Assignment ---
        if not isinstance(data_trials, list) or not all(isinstance(t, np.ndarray) for t in data_trials):
             log.warning(f"Channel '{name}' received non-list or non-ndarray data. Attempting conversion.")
             try:
                 # Ensure data is numpy array and handle potential conversion errors
                 self.data_trials: List[np.ndarray] = [np.asarray(t, dtype=float) for t in data_trials] # Ensure float dtype?
             except Exception as e:
                 log.error(f"Could not convert data_trials for channel '{name}' to list of arrays: {e}")
                 self.data_trials = [] # Assign empty list on failure
        else:
             # Ensure arrays within the list are ndarrays (already checked but belt-and-suspenders)
             self.data_trials: List[np.ndarray] = [np.asarray(t) for t in data_trials]

        # --- Optional Electrode Metadata (Populated by NeoAdapter) ---
        self.electrode_description: Optional[str] = None
        self.electrode_location: Optional[str] = None
        self.electrode_filtering: Optional[str] = None
        self.electrode_gain: Optional[float] = None # Gain applied by amplifier/acquisition
        self.electrode_offset: Optional[float] = None # ADC offset or baseline offset
        self.electrode_resistance: Optional[str] = None # Pipette resistance (e.g., "10 MOhm") - Requires parsing for NWB
        self.electrode_seal: Optional[str] = None # Seal resistance (e.g., "5 GOhm") - Requires parsing for NWB

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
        # Ensure the first trial is valid before accessing shape
        if not isinstance(self.data_trials[0], np.ndarray) or self.data_trials[0].ndim == 0:
             log.warning(f"Channel '{self.name}': First trial is not a valid NumPy array.")
             return 0

        first_trial_len = self.data_trials[0].shape[0]
        # Check other trials more carefully
        lengths = set()
        valid_trial_found = False
        for arr in self.data_trials:
             if isinstance(arr, np.ndarray) and arr.ndim > 0:
                 lengths.add(arr.shape[0])
                 valid_trial_found = True
             else:
                  log.warning(f"Channel '{self.name}' contains invalid trial data type: {type(arr)}")

        if not valid_trial_found:
             log.warning(f"Channel '{self.name}' contains no valid NumPy array trials.")
             return 0

        if len(lengths) > 1:
            log.warning(f"Channel '{self.name}' has trials with varying lengths: {lengths}. `num_samples` returning length of first trial ({first_trial_len}).")
        # Return length of first valid trial if lengths are consistent or vary
        return first_trial_len if lengths else 0


    def get_data(self, trial_index: int = 0) -> Optional[np.ndarray]:
        """
        Returns the data array (1D NumPy array) for the specified trial index.
        Returns None if the trial index is invalid or data is not valid.
        """
        if not isinstance(trial_index, int) or not (0 <= trial_index < self.num_trials):
            log.debug(f"Invalid trial index {trial_index} requested for channel '{self.name}' (has {self.num_trials} trials).")
            return None
        # Check if the specific trial data is valid
        trial_data = self.data_trials[trial_index]
        if not isinstance(trial_data, np.ndarray):
            log.warning(f"Data for trial {trial_index} in channel '{self.name}' is not a NumPy array (type: {type(trial_data)}).")
            return None
        return trial_data

    def get_time_vector(self, trial_index: int = 0) -> Optional[np.ndarray]:
        """
        Returns an absolute time vector (relative to recording start) for the
        specified trial index. Vector length matches the data length for that trial.
        Returns None if index is invalid or sampling rate is invalid.
        """
        data = self.get_data(trial_index)
        if data is None:
            return None # Invalid index or data handled by get_data

        num_samples_trial = data.shape[0]
        if num_samples_trial == 0:
             log.warning(f"Cannot generate time vector for empty trial {trial_index} in channel '{self.name}'.")
             return None # Cannot generate time for empty data

        if not isinstance(self.sampling_rate, (int, float)) or self.sampling_rate <= 0:
             log.error(f"Invalid sampling rate ({self.sampling_rate}) for channel '{self.name}'. Cannot calculate time vector.")
             return None

        # Prevent division by zero if sampling rate is somehow zero despite check
        try:
            duration_trial = num_samples_trial / self.sampling_rate
        except ZeroDivisionError:
            log.error(f"Zero sampling rate encountered for channel '{self.name}'. Cannot calculate time vector.")
            return None

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
            return None

        num_samples_trial = data.shape[0]
        if num_samples_trial == 0:
             log.warning(f"Cannot generate relative time vector for empty trial {trial_index} in channel '{self.name}'.")
             return None

        if not isinstance(self.sampling_rate, (int, float)) or self.sampling_rate <= 0:
             log.error(f"Invalid sampling rate ({self.sampling_rate}) for channel '{self.name}'. Cannot calculate relative time vector.")
             return None

        try:
            duration_trial = num_samples_trial / self.sampling_rate
        except ZeroDivisionError:
             log.error(f"Zero sampling rate encountered for channel '{self.name}'. Cannot calculate relative time vector.")
             return None

        # Relative time, starting from 0
        return np.linspace(0.0, duration_trial, num_samples_trial, endpoint=False)

    def get_averaged_data(self) -> Optional[np.ndarray]:
        """
        Calculates the average trace across all trials for this channel. Trials
        must have the same length and numeric data type.

        Returns:
            A 1D NumPy array containing the averaged data, or None if averaging
            is not possible.
        """
        if self.num_trials == 0:
            log.debug(f"Cannot average channel '{self.name}': No trials available.")
            return None
        if self.num_trials == 1:
            # Check if the single trial is valid before returning
            single_trial = self.get_data(0)
            if single_trial is not None and np.issubdtype(single_trial.dtype, np.number):
                 log.debug(f"Only one trial for channel '{self.name}'. Returning it as 'average'.")
                 return single_trial.copy()
            else:
                 log.warning(f"Cannot use single trial as average for channel '{self.name}': Invalid data.")
                 return None

        try:
            # Ensure all trials are valid ndarrays before proceeding
            valid_trials = [t for t in self.data_trials if isinstance(t, np.ndarray) and np.issubdtype(t.dtype, np.number)]
            if len(valid_trials) != self.num_trials:
                 log.error(f"Cannot average channel '{self.name}': Contains non-numeric or invalid trial data.")
                 return None
            if not valid_trials: # Should be covered by num_trials check, but safety
                 return None

            # Check for consistent trial lengths
            first_trial_len = valid_trials[0].shape[0]
            if not all(arr.shape[0] == first_trial_len for arr in valid_trials):
                lengths = {arr.shape[0] for arr in valid_trials}
                log.error(f"Cannot average channel '{self.name}': Trials have different lengths: {lengths}.")
                return None

            # Stack valid trials and calculate mean
            stacked_trials = np.stack(valid_trials)
            averaged_data = np.mean(stacked_trials, axis=0)
            return averaged_data
        except ValueError as ve:
             log.error(f"ValueError during averaging stack for channel '{self.name}': {ve}. Check trial shapes.")
             return None
        except Exception as e:
            log.error(f"Unexpected error calculating average for channel '{self.name}': {e}", exc_info=True)
            return None

    def get_averaged_time_vector(self) -> Optional[np.ndarray]:
         """
         Returns an absolute time vector (relative to recording start) suitable
         for the averaged data. Returns None if averaging is not possible or
         sampling rate is invalid.
         """
         avg_data = self.get_averaged_data()
         if avg_data is None: return None # Averaging failed

         num_samples_avg = avg_data.shape[0]
         if not isinstance(self.sampling_rate, (int, float)) or self.sampling_rate <= 0:
             log.error(f"Invalid sampling rate ({self.sampling_rate}) for channel '{self.name}'. Cannot calculate averaged time vector.")
             return None

         try:
             duration_avg = num_samples_avg / self.sampling_rate
         except ZeroDivisionError:
              log.error(f"Zero sampling rate for channel '{self.name}'. Cannot calculate averaged time vector.")
              return None

         return np.linspace(self.t_start, self.t_start + duration_avg, num_samples_avg, endpoint=False)

    def get_relative_averaged_time_vector(self) -> Optional[np.ndarray]:
         """
         Returns a relative time vector (starting at 0) suitable for the averaged data.
         Returns None if averaging is not possible or sampling rate is invalid.
         """
         avg_data = self.get_averaged_data()
         if avg_data is None: return None

         num_samples_avg = avg_data.shape[0]
         if not isinstance(self.sampling_rate, (int, float)) or self.sampling_rate <= 0:
             log.error(f"Invalid sampling rate ({self.sampling_rate}) for channel '{self.name}'. Cannot calculate relative averaged time vector.")
             return None

         try:
            duration_avg = num_samples_avg / self.sampling_rate
         except ZeroDivisionError:
            log.error(f"Zero sampling rate for channel '{self.name}'. Cannot calculate relative averaged time vector.")
            return None

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
        if not isinstance(source_file, Path):
             # Handle case where None or other type might be passed
             log.warning(f"Invalid source_file type ({type(source_file)}), setting to placeholder.")
             self.source_file: Path = Path("./unknown_source_file") # Or raise error
        else:
             self.source_file: Path = source_file

        self.channels: Dict[str, Channel] = {} # Key: Channel ID
        self.sampling_rate: Optional[float] = None # Global sampling rate (Hz), confirmed across channels or from block
        self.duration: Optional[float] = None      # Estimated duration (seconds)
        self.t_start: Optional[float] = None       # Global start time (seconds), relative to session start
        self.session_start_time_dt: Optional[datetime] = None # Actual datetime object of session start
        self.protocol_name: Optional[str] = None
        self.injected_current: Optional[float] = None # Estimated current range (PTP)
        self.metadata: Dict[str, Any] = {} # Other miscellaneous metadata

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
        num_trials_list = [ch.num_trials for ch in self.channels.values()]
        return max(num_trials_list) if num_trials_list else 0


# Optional Experiment class remains unchanged
class Experiment:
    """Optional container for multiple Recordings."""
    def __init__(self):
        self.recordings: List[Recording] = []
        self.metadata: Dict[str, Any] = {}
        self.identifier: str = str(uuid.uuid4())