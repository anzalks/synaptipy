# src/Synaptipy/application/session_manager.py

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from PySide6.QtCore import QObject, Signal

# We import Recording only for type hinting if possible.
from Synaptipy.core.data_model import Recording

log = logging.getLogger(__name__)


class SessionManager(QObject):
    """
    Singleton class to manage the global state of the application.
    Holds the current recording, selected analysis items, and global settings.
    """

    _instance = None

    # Signals
    current_recording_changed = Signal(object)  # Emits Recording object or None
    selected_analysis_items_changed = Signal(list)  # Emits List[Dict[str, Any]]
    global_settings_changed = Signal(dict)  # Emits Dict[str, Any]
    preprocessing_settings_changed = Signal(object)  # Emits preprocessing settings dict or None
    file_context_changed = Signal(list, int)  # Emits file_list, current_index

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(SessionManager, cls).__new__(cls, *args, **kwargs)
        return cls._instance

    def __init__(self):
        # Only initialize once
        if hasattr(self, "_initialized") and self._initialized:
            return
        super().__init__()
        self._current_recording: Optional[Recording] = None
        self._selected_analysis_items: List[Dict[str, Any]] = []
        self._global_settings: Dict[str, Any] = {}
        self._preprocessing_settings: Optional[Dict[str, Any]] = None
        self._file_list: List[Path] = []
        self._current_file_index: int = -1
        self._initialized = True
        log.debug("SessionManager initialized.")

    @property
    def current_recording(self) -> Optional[Recording]:
        return self._current_recording

    @current_recording.setter
    def current_recording(self, recording: Optional[Recording]):
        if self._current_recording != recording:
            self._current_recording = recording
            log.debug(f"Current recording changed to: {recording.source_file.name if recording else 'None'}")
            self.current_recording_changed.emit(recording)

    @property
    def selected_analysis_items(self) -> List[Dict[str, Any]]:
        return self._selected_analysis_items

    @selected_analysis_items.setter
    def selected_analysis_items(self, items: List[Dict[str, Any]]):
        # We compare lengths or content to decide if we should emit, or just emit always on set
        # For now, assuming if set is called, something might have changed or we want to refresh
        self._selected_analysis_items = items
        log.debug(f"Selected analysis items updated. Count: {len(items)}")
        self.selected_analysis_items_changed.emit(items)

    @property
    def global_settings(self) -> Dict[str, Any]:
        return self._global_settings

    def update_global_setting(self, key: str, value: Any):
        if self._global_settings.get(key) != value:
            self._global_settings[key] = value
            log.debug(f"Global setting updated: {key} = {value}")
            self.global_settings_changed.emit(self._global_settings)

    def set_global_settings(self, settings: Dict[str, Any]):
        if self._global_settings != settings:
            self._global_settings = settings
            log.debug("Global settings replaced.")
            self.global_settings_changed.emit(self._global_settings)

    def set_file_context(self, file_list: List[Path], current_index: int):
        """Updates the list of files and the current index (e.g. for navigation)."""
        self._file_list = file_list
        self._current_file_index = current_index
        # We don't necessarily emit current_recording_changed here, just context
        self.file_context_changed.emit(file_list, current_index)

    @property
    def file_list(self) -> List[Path]:
        return self._file_list

    @property
    def current_file_index(self) -> int:
        return self._current_file_index

    @property
    def preprocessing_settings(self) -> Optional[Dict[str, Any]]:
        """Returns the current global preprocessing settings as a dict with slots."""
        return self._preprocessing_settings

    @preprocessing_settings.setter
    def preprocessing_settings(self, settings: Optional[Dict[str, Any]]):
        """
        Sets global preprocessing settings and emits signal.

        Settings can be:
        - None: Clear all preprocessing
        - A dict with 'type' key: Update specific slot (baseline or filter by method)
        - A dict with 'baseline' and/or 'filters' keys: Set slots directly
        """
        if settings is None:
            # Clear all
            self._preprocessing_settings = None
            log.debug("Preprocessing settings cleared")
            self.preprocessing_settings_changed.emit(None)
            return

        # Check if this is a slot-based settings dict or a single step
        if "baseline" in settings or "filters" in settings:
            # Already in slot format
            self._preprocessing_settings = settings
        else:
            # Single step format - merge into slots
            step_type = settings.get("type")
            if self._preprocessing_settings is None:
                self._preprocessing_settings = {}

            if step_type == "baseline":
                self._preprocessing_settings["baseline"] = settings
            elif step_type == "filter":
                # Multiple filters supported - keyed by method (lowpass, highpass, etc.)
                filter_method = settings.get("method", "unknown")
                if "filters" not in self._preprocessing_settings:
                    self._preprocessing_settings["filters"] = {}
                # Same filter type replaces old one
                self._preprocessing_settings["filters"][filter_method] = settings
            else:
                log.warning(f"Unknown preprocessing step type: {step_type}")
                return

        # Log current state
        has_baseline = self._preprocessing_settings.get("baseline") is not None
        filter_count = len(self._preprocessing_settings.get("filters", {}))
        log.debug(f"Preprocessing settings updated: baseline={has_baseline}, filters={filter_count}")
        self.preprocessing_settings_changed.emit(self._preprocessing_settings)

    def clear_preprocessing_slot(self, slot_type: str, filter_method: str = None):
        """Clear a specific preprocessing slot ('baseline' or a specific filter method)."""
        if not self._preprocessing_settings:
            return

        if slot_type == "baseline" and "baseline" in self._preprocessing_settings:
            del self._preprocessing_settings["baseline"]
        elif slot_type == "filter" and filter_method and "filters" in self._preprocessing_settings:
            if filter_method in self._preprocessing_settings["filters"]:
                del self._preprocessing_settings["filters"][filter_method]
                if not self._preprocessing_settings["filters"]:
                    del self._preprocessing_settings["filters"]

        if not self._preprocessing_settings:
            self._preprocessing_settings = None
        log.debug(f"Cleared preprocessing slot: {slot_type} {filter_method or ''}")
        self.preprocessing_settings_changed.emit(self._preprocessing_settings)

    def get_preprocessing_steps(self) -> List[Dict[str, Any]]:
        """
        Returns preprocessing steps in the correct order:
        1. Baseline first
        2. Then all filters in consistent order (alphabetical by method)
        This ensures consistent processing regardless of application order.
        """
        steps = []
        if self._preprocessing_settings:
            # Always apply baseline before filters
            if "baseline" in self._preprocessing_settings:
                steps.append(self._preprocessing_settings["baseline"])
            # Add all filters in sorted order for consistency
            if "filters" in self._preprocessing_settings:
                for method in sorted(self._preprocessing_settings["filters"].keys()):
                    steps.append(self._preprocessing_settings["filters"][method])
        return steps
