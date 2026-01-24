#!/usr/bin/env python3
"""
Welcome Screen with Loading Progress for Synaptipy

This module provides a welcome screen that displays during application startup,
showing a loading bar and current loading status to improve user experience.

This file is part of Synaptipy, licensed under the GNU Affero General Public License v3.0.
See the LICENSE file in the root of the repository for full license details.
"""

import logging
from typing import Optional, Callable
from PySide6 import QtCore, QtGui, QtWidgets
import pyqtgraph as pg

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
            QtCore.Qt.WindowType.Window |
            QtCore.Qt.WindowType.WindowStaysOnTopHint |
            QtCore.Qt.WindowType.FramelessWindowHint
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
        
        # Logo placeholder (can be replaced with actual logo)
        logo_label = QtWidgets.QLabel("🧠")
        # Use system font size and colors for consistency
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
        version_label = QtWidgets.QLabel("Version 0.1.0")
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
