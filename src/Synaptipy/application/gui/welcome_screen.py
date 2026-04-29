#!/usr/bin/env python3
"""
Welcome Screen with Loading Progress for Synaptipy

This module provides two public components:

1. :class:`WelcomeScreen` — startup splash screen shown while the application
   loads.
2. :class:`DemoDataDownloader` — background ``QThread`` that downloads a demo
   ABF recording from the repository and saves it to
   ``~/Documents/SynaptiPy_Demo/``.
3. :class:`DemoDownloadBanner` — compact widget with a "Download Demo Data"
   button that wraps :class:`DemoDataDownloader`.  Embed it in any window to
   offer instant onboarding for first-time users.

This file is part of Synaptipy, licensed under the GNU Affero General Public License v3.0.
See the LICENSE file in the root of the repository for full license details.
"""

import logging
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

from PySide6 import QtCore, QtGui, QtWidgets

from Synaptipy import __version__

log = logging.getLogger(__name__)


class WelcomeScreen(QtWidgets.QWidget):
    """
    Welcome screen that displays during application startup.
    Shows a loading bar and current loading status.
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        # Set window flags for instant display
        self.setWindowFlags(
            QtCore.Qt.WindowType.Window
            | QtCore.Qt.WindowType.WindowStaysOnTopHint
            | QtCore.Qt.WindowType.FramelessWindowHint
        )

        # Set window attributes for better performance
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_NoSystemBackground, False)

        self._setup_ui()
        self._current_step = 0
        self._total_steps = 0
        self._loading_text = ""

    def _setup_ui(self):
        """Set up the welcome screen UI components."""
        # Main layout
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(40, 40, 40, 40)
        main_layout.setSpacing(30)

        # Application title and logo area
        title_layout = QtWidgets.QHBoxLayout()

        # Logo
        logo_label = QtWidgets.QLabel()
        # Resolve resource path: use sys._MEIPASS when running as PyInstaller bundle.
        if hasattr(sys, "_MEIPASS"):
            logo_path = Path(sys._MEIPASS) / "Synaptipy" / "resources" / "icons" / "logo.png"
        else:
            logo_path = Path(__file__).parent.parent.parent / "resources" / "icons" / "logo.png"
        if logo_path.exists():
            pixmap = QtGui.QPixmap(str(logo_path))
            # Scale logo to reasonable size (e.g., 100x100)
            pixmap = pixmap.scaled(
                100, 100, QtCore.Qt.AspectRatioMode.KeepAspectRatio, QtCore.Qt.TransformationMode.SmoothTransformation
            )
            logo_label.setPixmap(pixmap)
        else:
            logo_label.setText("[LOGO]")
            font = logo_label.font()
            font.setPointSize(48)
            logo_label.setFont(font)

        logo_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        title_layout.addWidget(logo_label)

        # Title and subtitle
        title_widget = QtWidgets.QWidget()
        title_layout_widget = QtWidgets.QVBoxLayout(title_widget)
        title_layout_widget.setSpacing(5)

        title_label = QtWidgets.QLabel("Synaptipy")
        # Use system font styling for consistency
        font = title_label.font()
        font.setPointSize(32)
        font.setBold(True)
        title_label.setFont(font)
        title_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

        subtitle_label = QtWidgets.QLabel("Electrophysiology Visualization Suite")
        # Use system font styling for consistency
        font = subtitle_label.font()
        font.setPointSize(16)
        subtitle_label.setFont(font)
        subtitle_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

        title_layout_widget.addWidget(title_label)
        title_layout_widget.addWidget(subtitle_label)
        title_layout.addWidget(title_widget)

        main_layout.addLayout(title_layout)

        # Loading progress section
        progress_group = QtWidgets.QGroupBox("Initializing Application")
        # Use system font styling for consistency
        font = progress_group.font()
        font.setPointSize(14)
        font.setBold(True)
        progress_group.setFont(font)

        progress_layout = QtWidgets.QVBoxLayout(progress_group)
        progress_layout.setSpacing(15)

        # Current loading text
        self.loading_text_label = QtWidgets.QLabel("Preparing application...")
        # Use system font styling for consistency
        font = self.loading_text_label.font()
        font.setPointSize(12)
        self.loading_text_label.setFont(font)
        self.loading_text_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.loading_text_label.setWordWrap(True)
        progress_layout.addWidget(self.loading_text_label)

        # Progress bar
        self.progress_bar = QtWidgets.QProgressBar()
        # Use system font styling for consistency
        font = self.progress_bar.font()
        font.setBold(True)
        self.progress_bar.setFont(font)
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)
        progress_layout.addWidget(self.progress_bar)

        # Progress percentage
        self.progress_label = QtWidgets.QLabel("0%")
        # Use system font styling for consistency
        font = self.progress_label.font()
        font.setPointSize(14)
        font.setBold(True)
        self.progress_label.setFont(font)
        self.progress_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        progress_layout.addWidget(self.progress_label)

        main_layout.addWidget(progress_group)

        # Status area
        status_group = QtWidgets.QGroupBox("Status")
        # Use system font styling for consistency
        font = status_group.font()
        font.setPointSize(12)
        font.setBold(True)
        status_group.setFont(font)

        status_layout = QtWidgets.QVBoxLayout(status_group)

        self.status_text_label = QtWidgets.QLabel("Ready to start...")
        # Use system font styling for consistency
        font = self.status_text_label.font()
        font.setPointSize(11)
        self.status_text_label.setFont(font)
        self.status_text_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft)
        self.status_text_label.setWordWrap(True)
        status_layout.addWidget(self.status_text_label)

        main_layout.addWidget(status_group)

        # Spacer to push everything to center
        main_layout.addStretch()

        # Version info at bottom
        version_label = QtWidgets.QLabel(f"Version {__version__}")
        # Use system font styling for consistency
        font = version_label.font()
        font.setPointSize(10)
        version_label.setFont(font)
        version_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(version_label)

        self.setLayout(main_layout)

        # Set window properties
        self.setWindowTitle("Synaptipy - Starting...")
        self.setMinimumSize(500, 400)

    def showEvent(self, event):
        """Override showEvent to ensure proper positioning and immediate display."""
        super().showEvent(event)

        # Center the window on screen
        screen = QtWidgets.QApplication.primaryScreen()
        if screen:
            available_geometry = screen.availableGeometry()
            window_geometry = self.geometry()

            # Calculate center position
            x = available_geometry.left() + (available_geometry.width() - window_geometry.width()) // 2
            y = available_geometry.top() + (available_geometry.height() - window_geometry.height()) // 2

            # Move to center
            self.move(x, y)

        # Force immediate display
        self.repaint()
        QtWidgets.QApplication.processEvents()

    def force_display(self):
        """Force the welcome screen to display immediately."""
        self.show()
        self.raise_()
        self.activateWindow()
        self.repaint()
        QtWidgets.QApplication.processEvents()

    def set_loading_steps(self, total_steps: int):
        """Set the total number of loading steps."""
        self._total_steps = total_steps
        self.progress_bar.setMaximum(total_steps)
        log.debug(f"Set loading steps: {total_steps}")

    def update_progress(self, step: int, text: str, status: str = ""):
        """
        Update the loading progress.

        Args:
            step: Current step number (0-based)
            text: Loading text to display
            status: Optional status message
        """
        self._current_step = step
        self._loading_text = text

        # Update progress bar
        progress_percentage = int((step / max(1, self._total_steps)) * 100)
        self.progress_bar.setValue(step)
        self.progress_label.setText(f"{progress_percentage}%")

        # Update loading text
        self.loading_text_label.setText(text)

        # Update status if provided
        if status:
            self.status_text_label.setText(status)

        log.debug(f"Progress update: {step}/{self._total_steps} - {text}")

    def set_status(self, status: str):
        """Set the status message."""
        self.status_text_label.setText(status)
        log.debug(f"Status update: {status}")

    def get_progress(self) -> tuple[int, int]:
        """Get current progress (current_step, total_steps)."""
        return self._current_step, self._total_steps

    def is_complete(self) -> bool:
        """Check if loading is complete."""
        return self._current_step >= self._total_steps


# ---------------------------------------------------------------------------
# Demo data download — background thread + UI banner
# ---------------------------------------------------------------------------

#: Base URL for the demo data files hosted in the repository.
_DEMO_BASE_URL = "https://raw.githubusercontent.com/anzalks/synaptipy/main/examples/data/"

#: All example data files to be downloaded.  The first ``.abf`` entry is
#: opened automatically in the Explorer Tab once the download completes.
_DEMO_FILES = [
    "2023_04_11_0018.abf",
    "2023_04_11_0019.abf",
    "2023_04_11_0021.abf",
    "2023_04_11_0022.abf",
    "240326_003.wcp",
]

#: Destination folder inside the user's Documents directory.
_DEMO_DEST_DIR = Path.home() / "Documents" / "SynaptiPy_Demo"


class DemoDataDownloader(QtCore.QThread):
    """Background thread that downloads the demo ABF recording.

    Signals:
        download_finished: Emitted with the local :class:`~pathlib.Path` of the
            saved file when the download succeeds.
        download_failed: Emitted with a human-readable error message on failure.
        download_progress: ``(bytes_received: int, total_bytes: int)`` — emitted
            periodically during the download.  ``total_bytes`` may be ``-1`` if
            the server does not send ``Content-Length``.
    """

    download_finished = QtCore.Signal(object)  # Path
    download_failed = QtCore.Signal(str)
    download_progress = QtCore.Signal(int, int)

    def __init__(self, parent: Optional[QtCore.QObject] = None) -> None:
        super().__init__(parent)

    def run(self) -> None:
        """Download all demo files.  Called automatically by :meth:`QThread.start`."""
        dest_dir = _DEMO_DEST_DIR
        try:
            dest_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            self.download_failed.emit(f"Cannot create destination folder: {exc}")
            return

        # If every file is already present skip the download entirely.
        first = self._all_files_present(dest_dir)
        if first is not None:
            log.debug("All demo files already present — skipping download.")
            self.download_finished.emit(first)
            return

        first, error = self._download_all(dest_dir)
        if error:
            self.download_failed.emit(error)
            return

        log.info("All demo files downloaded to %s", dest_dir)
        self.download_finished.emit(first)

    def _all_files_present(self, dest_dir: Path) -> Optional[Path]:
        """Return the first ABF path if every demo file exists, else ``None``."""
        first_abf: Optional[Path] = None
        for fname in _DEMO_FILES:
            if not (dest_dir / fname).exists():
                return None
            if first_abf is None and fname.endswith(".abf"):
                first_abf = dest_dir / fname
        return first_abf

    def _download_all(self, dest_dir: Path) -> tuple:
        """Download every file in :data:`_DEMO_FILES` sequentially.

        Returns:
            ``(first_abf_path, None)`` on full success, or
            ``(None, error_message)`` on the first failure (partial files
            are cleaned up).
        """
        first_abf: Optional[Path] = None
        for idx, fname in enumerate(_DEMO_FILES):
            dest_file = dest_dir / fname
            self.download_progress.emit(idx, len(_DEMO_FILES))
            err = self._do_download(dest_file, _DEMO_BASE_URL + fname)
            if err:
                self._cleanup_partial(dest_dir)
                return None, err
            if first_abf is None and fname.endswith(".abf"):
                first_abf = dest_file
        self.download_progress.emit(len(_DEMO_FILES), len(_DEMO_FILES))
        return first_abf, None

    def _cleanup_partial(self, dest_dir: Path) -> None:
        """Remove any partially downloaded demo files."""
        for fname in _DEMO_FILES:
            fp = dest_dir / fname
            if fp.exists():
                fp.unlink(missing_ok=True)

    def _do_download(self, dest_file: Path, url: str) -> Optional[str]:
        """Stream *url* into *dest_file*.

        Returns:
            ``None`` on success, or an error string on failure.
        """
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "Synaptipy-DemoDownloader/1.0"},
            )
            with urllib.request.urlopen(req, timeout=60) as response:
                with dest_file.open("wb") as fh:
                    while True:
                        data = response.read(8192)
                        if not data:
                            break
                        fh.write(data)
            return None
        except urllib.error.URLError as exc:
            return f"Network error: {exc.reason}"
        except Exception as exc:
            return str(exc)


class DemoDownloadBanner(QtWidgets.QFrame):
    """Compact banner widget offering one-click demo data download.

    Embeds a :class:`DemoDataDownloader` thread and exposes a
    ``file_ready`` signal so the parent window can load the file into the
    Explorer Tab automatically.

    Signals:
        file_ready: Emitted with the local :class:`~pathlib.Path` once the demo
            file is successfully downloaded (or was already present).
    """

    file_ready = QtCore.Signal(object)  # pathlib.Path

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("DemoDownloadBanner")
        self.setFrameShape(QtWidgets.QFrame.Shape.StyledPanel)
        self._worker: Optional[DemoDataDownloader] = None
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(12, 6, 12, 6)

        icon_label = QtWidgets.QLabel("Get started instantly:")
        layout.addWidget(icon_label)

        self._download_btn = QtWidgets.QPushButton("Download Demo Data")
        self._download_btn.setToolTip(
            "Downloads all example ABF/WCP recordings to ~/Documents/SynaptiPy_Demo/ "
            "and opens the first file in the Explorer Tab."
        )
        self._download_btn.clicked.connect(self._start_download)
        layout.addWidget(self._download_btn)

        self._progress_bar = QtWidgets.QProgressBar()
        self._progress_bar.setVisible(False)
        self._progress_bar.setMinimum(0)
        self._progress_bar.setMaximum(0)  # indeterminate until we know Content-Length
        self._progress_bar.setFixedWidth(200)
        layout.addWidget(self._progress_bar)

        self._status_label = QtWidgets.QLabel()
        self._status_label.setVisible(False)
        layout.addWidget(self._status_label)

        layout.addStretch()

    def _start_download(self) -> None:
        """Start the background download."""
        self._download_btn.setEnabled(False)
        self._progress_bar.setVisible(True)
        self._status_label.setText("Downloading…")
        self._status_label.setVisible(True)

        self._worker = DemoDataDownloader(parent=self)
        self._worker.download_progress.connect(self._on_progress)
        self._worker.download_finished.connect(self._on_finished)
        self._worker.download_failed.connect(self._on_failed)
        self._worker.start()

    def _on_progress(self, files_done: int, total_files: int) -> None:
        if total_files > 0:
            self._progress_bar.setMaximum(total_files)
            self._progress_bar.setValue(files_done)
        self._status_label.setText(f"Downloading… {files_done}/{total_files} files")

    def _on_finished(self, dest_path: object) -> None:
        """Hide the entire banner on success — demo data is now on disk."""
        self._progress_bar.setVisible(False)
        self.file_ready.emit(dest_path)
        # Hide the banner permanently; user can access files from Explorer.
        self.setVisible(False)

    def _on_failed(self, error_msg: str) -> None:
        self._progress_bar.setVisible(False)
        self._status_label.setText(f"Download failed: {error_msg}")
        self._download_btn.setEnabled(True)
        log.error("Demo data download failed: %s", error_msg)
