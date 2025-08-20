#!/usr/bin/env python3
"""
Startup Manager for Synaptipy

This module manages the application startup process, showing a welcome screen
and loading components in the background with progress updates.

This file is part of Synaptipy, licensed under the GNU Affero General Public License v3.0.
See the LICENSE file in the root of the repository for full license details.
"""

import logging
import time
from typing import Optional, Callable, List, Tuple
from PySide6 import QtCore, QtWidgets

from .gui.welcome_screen import WelcomeScreen
from .gui.main_window import MainWindow

log = logging.getLogger('Synaptipy.application.startup_manager')

class StartupManager(QtCore.QObject):
    """
    Manages the application startup process with progress tracking.
    """
    
    # Define loading steps
    LOADING_STEPS = [
        (0, "Initializing application...", "Setting up core components"),
        (1, "Loading Qt framework...", "Initializing PySide6"),
        (2, "Configuring PyQtGraph...", "Setting up plotting system"),
        (3, "Loading styling system...", "Applying application themes"),
        (4, "Creating main window...", "Building user interface"),
        (5, "Loading analysis modules...", "Discovering analysis tabs"),
        (6, "Finalizing setup...", "Preparing for use"),
        (7, "Ready!", "Application loaded successfully")
    ]
    
    def __init__(self, app: QtWidgets.QApplication):
        super().__init__()
        self.app = app
        self.welcome_screen: Optional[WelcomeScreen] = None
        self.main_window: Optional[MainWindow] = None
        self._loading_complete = False
        
    def start_loading(self) -> WelcomeScreen:
        """
        Start the loading process and return the welcome screen.
        
        Returns:
            WelcomeScreen: The welcome screen widget to display
        """
        log.info("Starting application loading process")
        
        # Create and setup welcome screen
        self.welcome_screen = WelcomeScreen()
        self.welcome_screen.set_loading_steps(len(self.LOADING_STEPS))
        
        # Start loading process in background
        QtCore.QTimer.singleShot(100, self._begin_loading)
        
        return self.welcome_screen
        
    def _begin_loading(self):
        """Begin the loading process step by step."""
        log.info("Beginning loading process")
        
        # Step 0: Initial setup
        self._update_progress(0)
        
        # Step 1: Qt framework (already done)
        QtCore.QTimer.singleShot(200, lambda: self._update_progress(1))
        
        # Step 2: PyQtGraph configuration
        QtCore.QTimer.singleShot(400, self._configure_pyqtgraph)
        
        # Step 3: Styling system
        QtCore.QTimer.singleShot(600, self._load_styling)
        
        # Step 4: Main window creation
        QtCore.QTimer.singleShot(800, self._create_main_window)
        
        # Step 5: Analysis modules loading (deferred until main window is ready)
        QtCore.QTimer.singleShot(1200, self._load_analysis_modules)
        
        # Step 6: Finalization
        QtCore.QTimer.singleShot(1600, self._finalize_setup)
        
        # Step 7: Complete
        QtCore.QTimer.singleShot(2000, self._complete_loading)
        
    def _update_progress(self, step: int):
        """Update the progress display."""
        if step < len(self.LOADING_STEPS) and self.welcome_screen:
            step_info = self.LOADING_STEPS[step]
            self.welcome_screen.update_progress(
                step_info[0], 
                step_info[1], 
                step_info[2]
            )
            log.info(f"Loading step {step}: {step_info[1]}")
            
    def _configure_pyqtgraph(self):
        """Configure PyQtGraph globally."""
        try:
            from Synaptipy.shared.styling import configure_pyqtgraph_globally
            configure_pyqtgraph_globally()
            log.info("PyQtGraph configuration complete")
        except Exception as e:
            log.warning(f"PyQtGraph configuration failed: {e}")
        finally:
            self._update_progress(2)
            
    def _load_styling(self):
        """Load and apply styling system."""
        try:
            from Synaptipy.shared.styling import apply_stylesheet
            self.app = apply_stylesheet(self.app)
            log.info("Styling system loaded")
        except Exception as e:
            log.warning(f"Styling system loading failed: {e}")
        finally:
            self._update_progress(3)
            
    def _create_main_window(self):
        """Create the main application window."""
        try:
            self.main_window = MainWindow()
            # Connect to initialized signal to transition promptly when ready
            try:
                self.main_window.initialized.connect(self._on_main_window_initialized)
            except Exception:
                pass
            log.info("Main window created successfully")
        except Exception as e:
            log.error(f"Main window creation failed: {e}", exc_info=True)
            if self.welcome_screen:
                self.welcome_screen.set_status(f"Error: {str(e)}")
        finally:
            self._update_progress(4)
            
    def _load_analysis_modules(self):
        """Load analysis modules in background."""
        try:
            if self.main_window and hasattr(self.main_window, 'analyser_tab'):
                # The analysis modules are loaded when the AnalyserTab is created
                # We just need to wait for the main window to complete
                log.info("Analysis modules loading initiated")
            else:
                log.warning("Main window not ready for analysis modules")
        except Exception as e:
            log.warning(f"Analysis modules loading failed: {e}")
        finally:
            self._update_progress(5)
            
    def _finalize_setup(self):
        """Finalize the setup process."""
        try:
            # Any final setup tasks
            log.info("Setup finalization complete")
        except Exception as e:
            log.warning(f"Setup finalization failed: {e}")
        finally:
            self._update_progress(6)
            
    def _complete_loading(self):
        """Handle loading completion."""
        try:
            self._update_progress(7)
            self._loading_complete = True
            
            # Show completion message briefly
            QtCore.QTimer.singleShot(1000, self._transition_to_main_window)
            
        except Exception as e:
            log.error(f"Loading completion failed: {e}", exc_info=True)

    def _on_main_window_initialized(self):
        """Fast-track transition when main window reports ready."""
        try:
            self._update_progress(7)
            self._loading_complete = True
            self._transition_to_main_window()
        except Exception as e:
            log.error(f"Fast transition failed: {e}", exc_info=True)
            
    def _transition_to_main_window(self):
        """Transition from welcome screen to main window."""
        if self.main_window and self.welcome_screen:
            try:
                # Hide welcome screen
                self.welcome_screen.hide()
                
                # Show main window
                self.main_window.show()
                
                # Clean up welcome screen
                self.welcome_screen.deleteLater()
                self.welcome_screen = None
                
                log.info("Successfully transitioned to main window")
                
            except Exception as e:
                log.error(f"Transition to main window failed: {e}", exc_info=True)
                
    def is_loading_complete(self) -> bool:
        """Check if loading is complete."""
        return self._loading_complete
        
    def get_main_window(self) -> Optional[MainWindow]:
        """Get the main window instance."""
        return self.main_window
