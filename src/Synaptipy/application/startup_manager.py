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
import urllib.error
import urllib.request
from typing import Optional

from PySide6 import QtCore, QtWidgets

from .gui.main_window import MainWindow
from .gui.welcome_screen import WelcomeScreen

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Version checker — runs once at startup, never blocks the UI
# ---------------------------------------------------------------------------

_RELEASES_API_URL = "https://api.github.com/repos/anzalks/synaptipy/releases/latest"


class VersionCheckerWorker(QtCore.QThread):
    """Background thread that queries the GitHub Releases API once at startup.

    Emits :attr:`update_available` with the latest release tag when the
    remote version is strictly newer than the running version according to
    simple tuple comparison on dot-separated version strings.

    The HTTP request uses ``timeout=3`` seconds.  Any network error
    (offline rig, firewall, DNS failure, timeout, rate-limit, malformed
    response) is caught silently and the thread exits without logging at
    WARNING or ERROR level - wet-lab machines are frequently airgapped.

    Signals:
        update_available: ``str`` -- the latest release tag (e.g. ``"0.2.0"``).
    """

    update_available = QtCore.Signal(str)

    def __init__(self, current_version: str, parent: Optional[QtCore.QObject] = None) -> None:
        super().__init__(parent)
        self._current_version = current_version

    def run(self) -> None:
        """Fetch the latest release tag and compare versions."""
        import json

        try:
            req = urllib.request.Request(
                _RELEASES_API_URL,
                headers={
                    "Accept": "application/vnd.github+json",
                    "User-Agent": f"Synaptipy/{self._current_version}",
                },
            )
            with urllib.request.urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read().decode())
        except ConnectionError:
            return  # offline / DNS failure -- silent
        except TimeoutError:
            return  # request took longer than 3 s -- silent
        except Exception:
            return  # rate-limit, SSL, malformed response, etc. -- silent

        try:
            tag = data.get("tag_name", "").lstrip("v")
            if tag and self._is_newer(tag, self._current_version.lstrip("v")):
                self.update_available.emit(tag)
        except Exception:
            return  # malformed tag string -- silent

    @staticmethod
    def _is_newer(remote: str, local: str) -> bool:
        """Return ``True`` if *remote* is strictly newer than *local*."""
        try:
            r = tuple(int(x) for x in remote.split("."))
            lo = tuple(int(x) for x in local.split("."))
            return r > lo
        except ValueError:
            return False


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

        # Load built-in analysis modules FIRST so that all @AnalysisRegistry.register
        # decorators run and populate the registry before the GUI is constructed.
        # Importing only registry.py (as analyser_tab used to do) does not trigger
        # the sub-module imports in core/analysis/__init__.py — this explicit import
        # of the package does.  This is the root cause of analyses missing on Windows.
        try:
            import Synaptipy.core.analysis  # noqa: F401 — side-effect: registers all built-in analyses
            from Synaptipy.core.analysis.registry import AnalysisRegistry

            AnalysisRegistry.mark_core_snapshot()
            log.debug("Built-in analysis modules loaded and registered.")
        except Exception as e:
            log.error(f"Failed to import built-in analysis modules: {e}")

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
            except Exception as e:
                log.debug(f"Could not connect to initialized signal: {e}")

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

                # Start background version check — done after show() so the
                # main-thread event loop is fully running when the signal fires.
                self._start_version_check()

            except Exception as e:
                log.error(f"Transition to main window failed: {e}", exc_info=True)

    def _start_version_check(self) -> None:
        """Launch :class:`VersionCheckerWorker` once the main window is visible."""
        try:
            from Synaptipy import __version__

            self._version_checker = VersionCheckerWorker(current_version=__version__, parent=self)
            if self.main_window and hasattr(self.main_window, "show_update_banner"):
                self._version_checker.update_available.connect(self.main_window.show_update_banner)
            self._version_checker.start()
        except Exception as exc:
            log.debug("Could not start version checker: %s", exc)

    def is_loading_complete(self) -> bool:
        """Check if loading is complete."""
        return self._loading_complete

    def get_main_window(self) -> Optional[MainWindow]:
        """Get the main window instance."""
        return self.main_window
