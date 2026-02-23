#!/usr/bin/env python3
"""
Optimized Startup Manager for Synaptipy

This module manages the application startup process with minimal delays
and optimized loading for fast startup times.

This file is part of Synaptipy, licensed under the GNU Affero General Public License v3.0.
See the LICENSE file in the root of the repository for full license details.
"""

import logging
import time
from typing import Optional
from PySide6 import QtCore, QtWidgets

from .gui.welcome_screen import WelcomeScreen
from .gui.main_window import MainWindow

log = logging.getLogger(__name__)


class StartupManager(QtCore.QObject):
    """
    Optimized startup manager with minimal delays and parallel loading.
    """

    # Streamlined loading steps
    LOADING_STEPS = [
        (0, "Initializing...", "Setting up core components"),
        (1, "Loading GUI...", "Building user interface"),
        (2, "Configuring plots...", "Setting up visualization"),
        (3, "Ready!", "Application loaded successfully"),
    ]

    def __init__(self, app: QtWidgets.QApplication):
        super().__init__()
        self.app = app
        self.welcome_screen: Optional[WelcomeScreen] = None
        self.main_window: Optional[MainWindow] = None
        self._loading_complete = False
        self._start_time = time.time()

    def start_loading(self) -> WelcomeScreen:
        """
        Start the optimized loading process and return the welcome screen.

        Returns:
            WelcomeScreen: The welcome screen widget to display
        """
        log.debug("Starting optimized application loading process")

        # Create and setup welcome screen
        self.welcome_screen = WelcomeScreen()
        self.welcome_screen.set_loading_steps(len(self.LOADING_STEPS))

        # Start loading process immediately (no artificial delays)
        QtCore.QTimer.singleShot(10, self._begin_loading)

        return self.welcome_screen

    def _begin_loading(self):
        """Begin the optimized loading process."""
        log.debug("Beginning optimized loading process")

        # Step 0: Initial setup
        self._update_progress(0)
        
        # Load external plugins safely before building the GUI
        try:
            from Synaptipy.application.plugin_manager import PluginManager
            PluginManager.load_plugins()
        except Exception as e:
            log.error(f"Critical error loading plugins during startup: {e}")

        # Step 1: Create main window and configure PyQtGraph in parallel
        QtCore.QTimer.singleShot(50, self._load_gui_components)

        # Step 2: Configure PyQtGraph (minimal delay)
        QtCore.QTimer.singleShot(100, self._configure_pyqtgraph)

        # Step 3: Complete loading (minimal delay)
        QtCore.QTimer.singleShot(150, self._complete_loading)

    def _update_progress(self, step: int):
        """Update the progress display."""
        if step < len(self.LOADING_STEPS) and self.welcome_screen:
            step_info = self.LOADING_STEPS[step]
            self.welcome_screen.update_progress(step_info[0], step_info[1], step_info[2])
            log.debug(f"Loading step {step}: {step_info[1]}")

            # Force Qt to process events to update the UI immediately
            if self.app:
                self.app.processEvents()

    def _load_gui_components(self):
        """Load GUI components efficiently."""
        try:
            # Create main window
            self.main_window = MainWindow()

            # Connect to initialized signal for fast transition
            try:
                self.main_window.initialized.connect(self._on_main_window_initialized)
            except Exception:
                pass

            log.debug("Main window created successfully")
            self._update_progress(1)

        except Exception as e:
            log.error(f"Main window creation failed: {e}", exc_info=True)
            if self.welcome_screen:
                self.welcome_screen.set_status(f"Error: {str(e)}")

    def _configure_pyqtgraph(self):
        """Configure PyQtGraph with minimal overhead."""
        try:
            from Synaptipy.shared.styling import configure_pyqtgraph_globally

            configure_pyqtgraph_globally()
            log.debug("PyQtGraph configuration complete")
        except Exception as e:
            log.warning(f"PyQtGraph configuration failed: {e}")
        finally:
            self._update_progress(2)

    def _complete_loading(self):
        """Complete the loading process."""
        try:
            self._update_progress(3)
            self._loading_complete = True

            # Transition immediately (no artificial delays)
            QtCore.QTimer.singleShot(50, self._transition_to_main_window)

        except Exception as e:
            log.error(f"Loading completion failed: {e}", exc_info=True)

    def _on_main_window_initialized(self):
        """Fast-track transition when main window reports ready."""
        try:
            self._update_progress(3)
            self._loading_complete = True
            self._transition_to_main_window()
        except Exception as e:
            log.error(f"Fast transition failed: {e}", exc_info=True)

    def _transition_to_main_window(self):
        """Transition from welcome screen to main window."""
        if self.main_window and self.welcome_screen:
            try:
                # Calculate total loading time
                total_time = time.time() - self._start_time
                log.debug(f"Total startup time: {total_time:.2f} seconds")

                # Hide welcome screen
                self.welcome_screen.hide()

                # Show main window
                self.main_window.show()

                # Clean up welcome screen
                self.welcome_screen.deleteLater()
                self.welcome_screen = None

                log.debug("Successfully transitioned to main window")

            except Exception as e:
                log.error(f"Transition to main window failed: {e}", exc_info=True)

    def is_loading_complete(self) -> bool:
        """Check if loading is complete."""
        return self._loading_complete

    def get_main_window(self) -> Optional[MainWindow]:
        """Get the main window instance."""
        return self.main_window
