# src/Synaptipy/application/controllers/shortcut_manager.py
# -*- coding: utf-8 -*-
"""
Shortcut Manager.
Stateless router for keyboard shortcuts.
Strictly maps Keys -> Controller Actions.
"""
import logging
from PySide6 import QtCore, QtGui

log = logging.getLogger(__name__)


class ShortcutManager(QtCore.QObject):
    """
    Manages keyboard shortcuts and routes them to the appropriate controller.
    
    Constraint: Stateless. Simply maps Key_Space -> NavigationController.next_file().
    """
    
    def __init__(self, navigation_controller=None, parent=None):
        """
        Initialize the ShortcutManager.
        
        Args:
            navigation_controller: Object with 'next_file()', 'prev_file()' methods.
            parent: Parent QObject.
        """
        super().__init__(parent)
        self.navigation_controller = navigation_controller

    def handle_key_press(self, event: QtGui.QKeyEvent) -> bool:
        """
        Process a key press event.
        Returns True if handled, False otherwise.
        """
        if not self.navigation_controller:
            return False

        key = event.key()
        
        if key == QtCore.Qt.Key_Space:
            log.debug("Shortcut: Space -> Next File")
            # Check if controller has the method before calling
            if hasattr(self.navigation_controller, "next_file"):
                self.navigation_controller.next_file()
                return True
            else:
                log.warning("NavigationController missing 'next_file' method.")

        elif key == QtCore.Qt.Key_Back: # Or Backspace? or Left?
            # Optional: Add Previous File on Backspace?
            # User constraint only mentioned Space -> next_file explicitly.
            # But let's add Backspace -> Prev File for symmetry if method exists
            pass
            
        return False
