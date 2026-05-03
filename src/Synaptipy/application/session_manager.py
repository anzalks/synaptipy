# src/Synaptipy/application/session_manager.py

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from PySide6.QtCore import QObject, Signal

# We import Recording only for type hinting if possible.
from Synaptipy.core.data_model import Recording

log = logging.getLogger(__name__)

# Default directory for session persistence: ~/.synaptipy/
_SESSION_DIR: Path = Path.home() / ".synaptipy"
_SESSION_FILE: Path = _SESSION_DIR / "session.json"
_SESSION_SCHEMA_VERSION: int = 1



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
    # Emitted when performance preferences change (max_cpu_cores, max_ram_allocation_gb).
    # Subscribers (e.g. BatchAnalysisEngine) can call update_performance_settings() immediately.
    preferences_changed = Signal(dict)  # Emits performance settings dict

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
        self._global_settings: Dict[str, Any] = {"liquid_junction_potential_mv": 0.0}
        self._preprocessing_settings: Optional[Dict[str, Any]] = None
        self._file_list: List[Path] = []
        self._current_file_index: int = -1
        self._performance_settings: Dict[str, Any] = {"max_cpu_cores": 1, "max_ram_allocation_gb": 4.0}
        self._initialized = True
        log.debug("SessionManager initialized.")

    @property
    def liquid_junction_potential_mv(self) -> float:
        """Global Liquid Junction Potential correction (mV). Default 0.0."""
        return float(self._global_settings.get("liquid_junction_potential_mv", 0.0))

    @liquid_junction_potential_mv.setter
    def liquid_junction_potential_mv(self, value: float) -> None:
        """Set the global LJP correction and emit global_settings_changed."""
        self.update_global_setting("liquid_junction_potential_mv", float(value))

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

    # ------------------------------------------------------------------
    # Performance settings — pub/sub
    # ------------------------------------------------------------------

    @property
    def performance_settings(self) -> Dict[str, Any]:
        """Current performance settings (max_cpu_cores, max_ram_allocation_gb)."""
        return dict(self._performance_settings)

    @performance_settings.setter
    def performance_settings(self, settings: Dict[str, Any]) -> None:
        """Update performance settings and emit :attr:`preferences_changed`.

        This is the *publisher* side of the pub/sub architecture.  Connecting
        a :class:`~Synaptipy.core.analysis.batch_engine.BatchAnalysisEngine`'s
        :meth:`~BatchAnalysisEngine.update_performance_settings` slot to
        :attr:`preferences_changed` keeps the engine in sync without restarts.

        Args:
            settings: Dict with any subset of ``"max_cpu_cores"`` (int) and
                      ``"max_ram_allocation_gb"`` (float).
        """
        if not isinstance(settings, dict):
            log.warning("performance_settings must be a dict, got %s.", type(settings).__name__)
            return
        self._performance_settings.update(settings)
        log.debug("SessionManager: performance_settings updated: %s", self._performance_settings)
        self.preferences_changed.emit(dict(self._performance_settings))

    def emit_preferences_changed(self) -> None:
        """Re-emit the current performance settings (e.g. on app start-up)."""
        self.preferences_changed.emit(dict(self._performance_settings))

    # ------------------------------------------------------------------
    # Session persistence  (JSON save / restore)
    # ------------------------------------------------------------------

    def save_session(
        self,
        active_tab_index: int = 0,
        analysis_params: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Persist the current application state to ``~/.synaptipy/session.json``.

        Saves:

        * The list of currently loaded file paths (as POSIX strings).
        * The active tab index.
        * The global settings (LJP, etc.).
        * The performance settings.
        * Optional per-tab analysis parameter snapshots.

        Parameters
        ----------
        active_tab_index : int
            Zero-based index of the currently visible tab in the main
            ``QTabWidget``.
        analysis_params : dict, optional
            Arbitrary key/value mapping of analysis slider / spinbox values
            that the caller wants to persist (e.g. threshold, window sizes).

        Returns
        -------
        bool
            ``True`` on success, ``False`` if the write failed.
        """
        payload: Dict[str, Any] = {
            "schema_version": _SESSION_SCHEMA_VERSION,
            "active_tab_index": active_tab_index,
            "file_paths": [str(p) for p in self._file_list if p is not None],
            "current_file_index": self._current_file_index,
            "global_settings": dict(self._global_settings),
            "performance_settings": dict(self._performance_settings),
            "analysis_params": analysis_params or {},
        }
        try:
            _SESSION_DIR.mkdir(parents=True, exist_ok=True)
            _SESSION_FILE.write_text(
                json.dumps(payload, indent=2, default=str),
                encoding="utf-8",
            )
            log.debug(
                "SessionManager.save_session: wrote %d file path(s) to %s.",
                len(payload["file_paths"]),
                _SESSION_FILE,
            )
            return True
        except Exception as exc:
            log.warning("SessionManager.save_session failed: %s", exc)
            return False

    @staticmethod
    def load_session() -> Optional[Dict[str, Any]]:
        """Read ``~/.synaptipy/session.json`` and return its contents.

        This is a **pure read** method — it does not modify any singleton
        state.  The caller (e.g. ``MainWindow``) is responsible for prompting
        the user and applying the returned values.

        Returns
        -------
        dict or None
            The parsed session dict, or ``None`` if the file does not exist,
            cannot be parsed, or has an incompatible schema version.
        """
        if not _SESSION_FILE.is_file():
            return None
        try:
            raw = json.loads(_SESSION_FILE.read_text(encoding="utf-8"))
        except Exception as exc:
            log.warning("SessionManager.load_session: cannot read %s: %s", _SESSION_FILE, exc)
            return None

        if not isinstance(raw, dict):
            return None
        if raw.get("schema_version") != _SESSION_SCHEMA_VERSION:
            log.info(
                "SessionManager.load_session: schema_version mismatch "
                "(got %s, expected %s) — ignoring session file.",
                raw.get("schema_version"),
                _SESSION_SCHEMA_VERSION,
            )
            return None

        # Coerce file_paths back to Path objects
        raw["file_paths"] = [
            Path(p) for p in raw.get("file_paths", []) if Path(p).is_file()
        ]
        log.debug(
            "SessionManager.load_session: found %d valid file path(s).",
            len(raw["file_paths"]),
        )
        return raw

    def apply_session(self, session: Dict[str, Any]) -> None:
        """Apply a previously loaded session dict to the singleton's internal state.

        Restores global settings and performance settings only — file context
        and tab index are left for ``MainWindow`` to handle, since those
        require triggering Qt signals and loading data asynchronously.

        Parameters
        ----------
        session : dict
            A dict returned by :meth:`load_session`.
        """
        if not isinstance(session, dict):
            return
        if "global_settings" in session:
            self.set_global_settings(session["global_settings"])
        if "performance_settings" in session:
            self.performance_settings = session["performance_settings"]
        log.debug("SessionManager.apply_session: global and performance settings restored.")

