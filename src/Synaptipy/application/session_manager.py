# src/Synaptipy/application/session_manager.py

from PySide6.QtCore import QObject, Signal
from typing import List, Dict, Any, Optional
from pathlib import Path
import logging

# We import Recording only for type hinting if possible.
from Synaptipy.core.data_model import Recording

log = logging.getLogger('Synaptipy.application.session_manager')

class SessionManager(QObject):
    """
    Singleton class to manage the global state of the application.
    Holds the current recording, selected analysis items, and global settings.
    """
    _instance = None

    # Signals
    current_recording_changed = Signal(object)  # Emits Recording object or None
    selected_analysis_items_changed = Signal(list) # Emits List[Dict[str, Any]]
    global_settings_changed = Signal(dict) # Emits Dict[str, Any]
    file_context_changed = Signal(list, int) # Emits file_list, current_index

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(SessionManager, cls).__new__(cls, *args, **kwargs)
        return cls._instance

    def __init__(self):
        # Only initialize once
        if hasattr(self, '_initialized') and self._initialized:
            return
        super().__init__()
        self._current_recording: Optional[Recording] = None
        self._selected_analysis_items: List[Dict[str, Any]] = []
        self._global_settings: Dict[str, Any] = {}
        self._file_list: List[Path] = []
        self._current_file_index: int = -1
        self._initialized = True
        log.info("SessionManager initialized.")

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

