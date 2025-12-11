# src/Synaptipy/core/data_model.py
# -*- coding: utf-8 -*-
"""
Core Domain Data Models for Synaptipy.

Defines the central classes representing electrophysiology concepts like
Recording sessions and individual data Channels.
"""

import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any # Added Any for metadata dict
import numpy as np
import uuid
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
        # For lazy loading, data_trials may be empty initially
        if not isinstance(data_trials, list):
             log.warning(f"Channel '{name}' received non-list data. Attempting conversion.")
             try:
                 # Ensure data is numpy array and handle potential conversion errors
                 self.data_trials: List[np.ndarray] = [np.asarray(data_trials, dtype=float)] if data_trials is not None else []
             except Exception as e:
                 log.error(f"Could not convert data_trials for channel '{name}' to list of arrays: {e}")
                 self.data_trials = [] # Assign empty list on failure
        else:
             # For lazy loading, data_trials may be empty or contain actual data
             if data_trials and all(isinstance(t, np.ndarray) for t in data_trials):
                 # Normal case: data is already loaded
                 self.data_trials: List[np.ndarray] = [np.asarray(t) for t in data_trials]
             else:
                 # Lazy loading case: empty data_trials
                 self.data_trials: List[np.ndarray] = []

        # --- ADDED: Attributes for Associated Current Data --- 
        self.current_data_trials: List[np.ndarray] = [] # Populated by adapter if current signal found
        self.current_units: Optional[str] = None # Populated by adapter
        # --- END ADDED ---

        # --- Optional Electrode Metadata (Populated by NeoAdapter) ---
        self.electrode_description: Optional[str] = None
        self.electrode_location: Optional[str] = None
        self.electrode_filtering: Optional[str] = None
        self.electrode_gain: Optional[float] = None # Gain applied by amplifier/acquisition
        self.electrode_offset: Optional[float] = None # ADC offset or baseline offset
        self.electrode_resistance: Optional[str] = None # Pipette resistance (e.g., "10 MOhm") - Requires parsing for NWB
        self.electrode_seal: Optional[str] = None # Seal resistance (e.g., "5 GOhm") - Requires parsing for NWB
        
        # --- Lazy Loading Support ---
        self.lazy_info: Dict[str, Any] = {}  # Stores lazy loading information from NeoAdapter
        self.metadata: Dict[str, Any] = {}   # General metadata dictionary

    @property
    def num_trials(self) -> int:
        """Returns the number of trials/segments available for this channel."""
        # For lazy loading, check metadata first, then data_trials
        if hasattr(self, 'metadata') and 'num_trials' in self.metadata:
            return self.metadata['num_trials']
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

    # --- Data Retrieval Methods ---
    def get_data(self, trial_index: int) -> Optional[np.ndarray]:
        """
        Returns the raw data for a specific trial.
        For lazy loading, this method will load the data from disk if not already loaded.
        """
        # Check if data is already loaded
        if self.data_trials and 0 <= trial_index < len(self.data_trials):
            return self.data_trials[trial_index]
        
        # For lazy loading, try to load data from neo Block
        if hasattr(self, 'lazy_info') and self.lazy_info:
            try:
                return self._load_trial_data_lazy(trial_index)
            except Exception as e:
                log.error(f"Failed to load trial {trial_index} data lazily for channel {self.id}: {e}")
                return None
        
        return None
    
    def _load_trial_data_lazy(self, trial_index: int) -> Optional[np.ndarray]:
        """
        Load data for a specific trial from the neo Block using lazy loading.
        This method accesses the stored neo Block and reader to load data on-demand.
        """
        if not hasattr(self, 'lazy_info') or not self.lazy_info:
            log.warning(f"No lazy loading info available for channel {self.id}")
            return None
        
        try:
            # Get the recording object (should be accessible through the channel's parent)
            # For now, we'll need to access it through the lazy_info
            recording = getattr(self, '_recording_ref', None)
            if not recording or not hasattr(recording, 'neo_block'):
                log.error(f"No recording reference or neo_block available for lazy loading")
                return None
            
            neo_block = recording.neo_block
            
            # Determine which trial to load based on lazy_info
            if trial_index == 0:
                # First trial - use the main signal reference
                analog_signal_ref = self.lazy_info.get('analog_signal_ref')
                if analog_signal_ref is None:
                    log.error(f"No analog signal reference for trial 0 in channel {self.id}")
                    return None
            else:
                # Additional trials - use the trials list
                trials_info = self.lazy_info.get('trials', [])
                if trial_index - 1 >= len(trials_info):
                    log.error(f"Trial index {trial_index} out of range for channel {self.id}")
                    return None
                analog_signal_ref = trials_info[trial_index - 1].get('analog_signal_ref')
                if analog_signal_ref is None:
                    log.error(f"No analog signal reference for trial {trial_index} in channel {self.id}")
                    return None
            
            # Load the actual data from the lazy AnalogSignal
            log.debug(f"Loading trial {trial_index} data for channel {self.id}")
            data = np.ravel(analog_signal_ref.magnitude)
            
            # Store the loaded data in data_trials for future access
            # Ensure data_trials list is long enough
            while len(self.data_trials) <= trial_index:
                self.data_trials.append(None)
            
            self.data_trials[trial_index] = data
            log.debug(f"Successfully loaded trial {trial_index} data for channel {self.id}: {data.shape[0]} samples")
            
            return data
            
        except Exception as e:
            log.error(f"Error loading trial {trial_index} data lazily for channel {self.id}: {e}", exc_info=True)
            return None

    def get_time_vector(self, trial_index: int) -> Optional[np.ndarray]:
        # Returns the absolute time vector for a specific trial.
        data = self.get_data(trial_index)
        if data is not None and self.sampling_rate and self.sampling_rate > 0:
            num_samples = len(data)
            duration = num_samples / self.sampling_rate
            trial_t_start = self.t_start + trial_index * duration # Approximate start time
            return np.linspace(trial_t_start, trial_t_start + duration, num_samples, endpoint=False)
        return None

    def get_relative_time_vector(self, trial_index: int) -> Optional[np.ndarray]:
        # Returns the time vector relative to the start of the trial (starts at 0).
        data = self.get_data(trial_index)
        if data is not None and self.sampling_rate and self.sampling_rate > 0:
            num_samples = len(data)
            duration = num_samples / self.sampling_rate
            return np.linspace(0, duration, num_samples, endpoint=False)
        return None

    def get_averaged_data(self) -> Optional[np.ndarray]:
        # Returns the averaged data across all trials.
        if self.data_trials:
            try:
                # Ensure all trials have the same length for simple averaging
                first_len = len(self.data_trials[0])
                if all(len(trial) == first_len for trial in self.data_trials):
                    return np.mean(np.array(self.data_trials), axis=0)
                else:
                    # Handle differing lengths (e.g., pad or error)
                    log.warning(f"Channel {self.id}: Trials have different lengths, cannot average directly.")
                    return None
            except Exception as e:
                log.error(f"Channel {self.id}: Error averaging trials: {e}")
                return None
        return None

    def get_averaged_time_vector(self) -> Optional[np.ndarray]:
        # Returns the absolute time vector for the averaged data (assumes first trial time base).
        avg_data = self.get_averaged_data()
        if avg_data is not None and self.sampling_rate and self.sampling_rate > 0:
            num_samples = len(avg_data)
            duration = num_samples / self.sampling_rate
            return np.linspace(self.t_start, self.t_start + duration, num_samples, endpoint=False)
        return None

    def get_relative_averaged_time_vector(self) -> Optional[np.ndarray]:
        # Returns the time vector relative to the start of the averaged data (starts at 0).
        avg_data = self.get_averaged_data()
        if avg_data is not None and self.sampling_rate and self.sampling_rate > 0:
            num_samples = len(avg_data)
            duration = num_samples / self.sampling_rate
            return np.linspace(0, duration, num_samples, endpoint=False)
        return None

    def get_current_data(self, trial_index: int) -> Optional[np.ndarray]:
        # Returns the current data for a specific trial, if available.
        if self.current_data_trials and 0 <= trial_index < len(self.current_data_trials):
            return self.current_data_trials[trial_index]
        return None

    def get_averaged_current_data(self) -> Optional[np.ndarray]:
        # Returns the averaged current data across all trials, if available.
        if self.current_data_trials:
            try:
                first_len = len(self.current_data_trials[0])
                if all(len(trial) == first_len for trial in self.current_data_trials):
                    return np.mean(np.array(self.current_data_trials), axis=0)
                else:
                    log.warning(f"Channel {self.id}: Current trials have different lengths, cannot average.")
                    return None
            except Exception as e:
                log.error(f"Channel {self.id}: Error averaging current trials: {e}")
                return None
        return None

    # --- ADDED HELPER FOR PLOT LABELS ---
    def get_primary_data_label(self) -> str:
        """Determines a suitable label ('Voltage', 'Current', 'Signal') based on units."""
        if self.units:
            units_lower = self.units.lower()
            if 'v' in units_lower:
                return 'Voltage'
            elif 'a' in units_lower: # Check for 'amp' or 'a'
                return 'Current'
        return 'Signal' # Default if no units or not recognized
    # --- END ADDED HELPER ---

    def get_data_bounds(self) -> Optional[Tuple[float, float]]:
        """Returns the min and max values across all trials for this channel."""
        if not self.data_trials or not any(trial.size > 0 for trial in self.data_trials):
            return None
        
        min_val = np.min([np.min(trial) for trial in self.data_trials if trial.size > 0])
        max_val = np.max([np.max(trial) for trial in self.data_trials if trial.size > 0])
        
        return float(min_val), float(max_val)

    def get_finite_data_bounds(self) -> Optional[Tuple[float, float]]:
        """
        Returns the min and max values across all trials, ensuring they are finite.
        Returns None if no finite data is found.
        """
        if not self.data_trials or not any(trial.size > 0 for trial in self.data_trials):
            return None
        
        try:
            # Concatenate all finite data from all trials
            all_finite_data = np.concatenate([trial[np.isfinite(trial)] for trial in self.data_trials if trial.size > 0])
            
            if all_finite_data.size == 0:
                return None
                
            min_val = np.min(all_finite_data)
            max_val = np.max(all_finite_data)
            
            return float(min_val), float(max_val)
        except (ValueError, TypeError):
            # Handles cases where there's no data left after filtering
            return None

    def __repr__(self):
        return f"Channel(id='{self.id}', name='{self.name}', units='{self.units}', trials={self.num_trials})"


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
             log.warning(f"Invalid source_file type ({type(source_file)}), setting to placeholder.")
             self.source_file: Path = Path("./unknown_source_file") # Or raise error
        else:
             self.source_file: Path = source_file

        self.channels: Dict[str, Channel] = {}
        self.sampling_rate: Optional[float] = None
        self.duration: Optional[float] = None
        self.t_start: Optional[float] = None
        self.session_start_time_dt: Optional[datetime] = None
        self.protocol_name: Optional[str] = None
        self.injected_current: Optional[float] = None
        self.metadata: Dict[str, Any] = {} # Use Any for metadata flexibility
        
        # --- Lazy Loading Support ---
        self.neo_block = None  # Will be set by NeoAdapter for lazy loading
        self.neo_reader = None  # Will be set by NeoAdapter for lazy loading

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


class Experiment:
    """
    Optional container representing a collection of Recordings, potentially
    from a single experimental session or related set. (Currently basic).
    """
    def __init__(self):
        self.recordings: List[Recording] = []
        self.metadata: Dict[str, Any] = {} # Use Any for metadata flexibility
        self.identifier: str = str(uuid.uuid4()) # Example unique ID for the experiment