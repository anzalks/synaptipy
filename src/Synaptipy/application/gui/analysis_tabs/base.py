# src/Synaptipy/application/gui/analysis_tabs/base.py
# -*- coding: utf-8 -*-
"""
Base class for individual analysis tab widgets. Defines the expected interface
without using ABC to avoid metaclass conflicts with QWidget.
"""
import logging
# from abc import ABC, abstractmethod # REMOVED ABC
from typing import Optional

# Import QWidget correctly
from PySide6 import QtWidgets

# Use absolute path to import ExplorerTab from its location
from Synaptipy.application.gui.explorer_tab import ExplorerTab
from Synaptipy.core.data_model import Recording # Import Recording for type hint

log = logging.getLogger('Synaptipy.application.gui.analysis_tabs.base')

# Inherit ONLY from QWidget
class BaseAnalysisTab(QtWidgets.QWidget):
    """Base Class for all analysis sub-tabs."""

    TRIAL_MODES = ["Single Trial", "Trial Range", "All Trials", "Average Trace"] # Common trial modes

    def __init__(self, explorer_tab_ref: ExplorerTab, parent=None):
        """
        Initialize the base analysis tab.

        Args:
            explorer_tab_ref: Reference to the main ExplorerTab instance.
            parent: Parent widget.
        """
        super().__init__(parent) # Calls QWidget.__init__
        self._explorer_tab = explorer_tab_ref
        self._current_recording: Optional[Recording] = None
        log.debug(f"Initializing BaseAnalysisTab: {self.__class__.__name__}")

    # --- Methods Subclasses MUST Implement (Runtime Check) ---

    def get_display_name(self) -> str:
        """Return the string to be displayed on the sub-tab button."""
        log.error(f"Subclass {self.__class__.__name__} must implement get_display_name()")
        raise NotImplementedError(f"Subclass {self.__class__.__name__} must implement get_display_name()")

    def update_state(self):
        """
        Update the UI elements within this sub-tab based on the data
        currently loaded in the ExplorerTab. Should be called by the
        main AnalyserTab when data changes.
        """
        # Base implementation can store the current recording
        self._current_recording = self._explorer_tab.get_current_recording()
        # Subclasses should override this to update their specific UI
        log.error(f"Subclass {self.__class__.__name__} must implement update_state()")
        raise NotImplementedError(f"Subclass {self.__class__.__name__} must implement update_state()")

    def _setup_ui(self):
        """Create the specific UI elements for this analysis tab."""
        log.error(f"Subclass {self.__class__.__name__} must implement _setup_ui()")
        raise NotImplementedError(f"Subclass {self.__class__.__name__} must implement _setup_ui()")

    def _connect_signals(self):
        """Connect signals for the widgets within this analysis tab."""
        # Make optional for subclasses if no signals need connecting
        pass

    def cleanup(self):
        """Optional cleanup method for resources specific to this tab."""
        log.debug(f"Cleaning up {self.__class__.__name__}")
        # Implement specific cleanup if needed
        pass