# src/Synaptipy/application/gui/preferences_dialog.py
# -*- coding: utf-8 -*-
"""
Preferences Dialog for Synaptipy.

Provides a unified preferences interface for scroll direction and theme settings.
"""
import logging
from typing import Optional

from PySide6 import QtWidgets

from Synaptipy.shared.scroll_settings import (
    ScrollDirection,
    get_scroll_direction,
    set_scroll_direction,
)
from Synaptipy.shared.theme_manager import (
    ThemeMode,
    apply_theme,
    get_theme_mode,
    set_theme_mode,
)

log = logging.getLogger(__name__)


class PreferencesDialog(QtWidgets.QDialog):
    """
    Application preferences dialog.

    Contains settings for:
    - Scroll behavior (Natural/Inverted/System)
    - Theme appearance (Light/Dark/System)
    """

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("Preferences")
        self.setMinimumWidth(450)
        self.setMinimumHeight(350)

        # Store original values for cancel
        self._original_scroll_direction = get_scroll_direction()
        self._original_theme_mode = get_theme_mode()

        self._setup_ui()
        self._load_current_settings()

    def _setup_ui(self):
        """Set up the dialog UI."""
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setSpacing(15)

        # Tab widget for different settings categories
        self.tab_widget = QtWidgets.QTabWidget()
        main_layout.addWidget(self.tab_widget)

        # General tab (scroll + appearance)
        self._create_general_tab()

        # Button box
        button_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok
            | QtWidgets.QDialogButtonBox.StandardButton.Cancel
            | QtWidgets.QDialogButtonBox.StandardButton.Apply
            | QtWidgets.QDialogButtonBox.StandardButton.RestoreDefaults
        )
        button_box.accepted.connect(self._on_accepted)
        button_box.rejected.connect(self._on_rejected)
        apply_btn = button_box.button(QtWidgets.QDialogButtonBox.StandardButton.Apply)
        apply_btn.clicked.connect(self._apply_settings)
        reset_btn = button_box.button(QtWidgets.QDialogButtonBox.StandardButton.RestoreDefaults)
        reset_btn.clicked.connect(self._reset_to_defaults)
        main_layout.addWidget(button_box)

    def _create_general_tab(self):
        """Create the General settings tab."""
        tab = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(tab)
        layout.setSpacing(20)

        # --- Scroll Settings Group ---
        scroll_group = QtWidgets.QGroupBox("Scroll Behavior")
        scroll_layout = QtWidgets.QVBoxLayout(scroll_group)

        scroll_description = QtWidgets.QLabel("Controls how mouse wheel and trackpad scrolling affects the view.")
        scroll_description.setWordWrap(True)
        scroll_description.setStyleSheet("color: gray; font-size: 11px;")
        scroll_layout.addWidget(scroll_description)

        # Radio buttons for scroll direction
        self.scroll_natural_radio = QtWidgets.QRadioButton("Natural")
        self.scroll_natural_radio.setToolTip("Content moves in the same direction as your fingers (macOS-style)")
        natural_desc = QtWidgets.QLabel("Content moves in the same direction as your fingers")
        natural_desc.setStyleSheet("color: gray; font-size: 10px; margin-left: 20px;")

        self.scroll_inverted_radio = QtWidgets.QRadioButton("Inverted")
        self.scroll_inverted_radio.setToolTip("Traditional mouse wheel behavior (scroll up = content goes down)")
        inverted_desc = QtWidgets.QLabel("Traditional scrolling (scroll up = content goes down)")
        inverted_desc.setStyleSheet("color: gray; font-size: 10px; margin-left: 20px;")

        self.scroll_system_radio = QtWidgets.QRadioButton("System")
        self.scroll_system_radio.setToolTip("Follow your operating system's scroll direction setting")
        system_desc = QtWidgets.QLabel("Follow operating system setting")
        system_desc.setStyleSheet("color: gray; font-size: 10px; margin-left: 20px;")

        scroll_layout.addWidget(self.scroll_natural_radio)
        scroll_layout.addWidget(natural_desc)
        scroll_layout.addWidget(self.scroll_inverted_radio)
        scroll_layout.addWidget(inverted_desc)
        scroll_layout.addWidget(self.scroll_system_radio)
        scroll_layout.addWidget(system_desc)

        layout.addWidget(scroll_group)

        # --- Appearance Settings Group ---
        appearance_group = QtWidgets.QGroupBox("Appearance")
        appearance_layout = QtWidgets.QVBoxLayout(appearance_group)

        appearance_description = QtWidgets.QLabel("Application color theme.")
        appearance_description.setWordWrap(True)
        appearance_description.setStyleSheet("color: gray; font-size: 11px;")
        appearance_layout.addWidget(appearance_description)

        # Radio buttons for theme
        self.theme_light_radio = QtWidgets.QRadioButton("Light")
        self.theme_light_radio.setToolTip("Light color scheme")
        self.theme_light_radio.toggled.connect(self._on_theme_preview)

        self.theme_dark_radio = QtWidgets.QRadioButton("Dark")
        self.theme_dark_radio.setToolTip("Dark color scheme")
        self.theme_dark_radio.toggled.connect(self._on_theme_preview)

        self.theme_system_radio = QtWidgets.QRadioButton("System")
        self.theme_system_radio.setToolTip("Follow operating system theme")
        self.theme_system_radio.toggled.connect(self._on_theme_preview)

        theme_buttons_layout = QtWidgets.QHBoxLayout()
        theme_buttons_layout.addWidget(self.theme_light_radio)
        theme_buttons_layout.addWidget(self.theme_dark_radio)
        theme_buttons_layout.addWidget(self.theme_system_radio)
        theme_buttons_layout.addStretch()

        appearance_layout.addLayout(theme_buttons_layout)

        layout.addWidget(appearance_group)

        # Spacer
        layout.addStretch()

        self.tab_widget.addTab(tab, "General")

    def _load_current_settings(self):
        """Load current settings into the UI."""
        # Scroll direction
        current_scroll = get_scroll_direction()
        if current_scroll == ScrollDirection.NATURAL:
            self.scroll_natural_radio.setChecked(True)
        elif current_scroll == ScrollDirection.INVERTED:
            self.scroll_inverted_radio.setChecked(True)
        else:
            self.scroll_system_radio.setChecked(True)

        # Theme
        current_theme = get_theme_mode()
        if current_theme == ThemeMode.LIGHT:
            self.theme_light_radio.setChecked(True)
        elif current_theme == ThemeMode.DARK:
            self.theme_dark_radio.setChecked(True)
        else:
            self.theme_system_radio.setChecked(True)

    def _get_selected_scroll_direction(self) -> ScrollDirection:
        """Get the currently selected scroll direction."""
        if self.scroll_natural_radio.isChecked():
            return ScrollDirection.NATURAL
        elif self.scroll_inverted_radio.isChecked():
            return ScrollDirection.INVERTED
        else:
            return ScrollDirection.SYSTEM

    def _get_selected_theme_mode(self) -> ThemeMode:
        """Get the currently selected theme mode."""
        if self.theme_light_radio.isChecked():
            return ThemeMode.LIGHT
        elif self.theme_dark_radio.isChecked():
            return ThemeMode.DARK
        else:
            return ThemeMode.SYSTEM

    def _on_theme_preview(self, checked: bool):
        """Preview theme changes in real-time."""
        if not checked:
            return

        # Apply the selected theme immediately for preview
        selected_theme = self._get_selected_theme_mode()
        apply_theme(selected_theme)

    def _apply_settings(self):
        """Apply current settings without closing dialog."""
        # Save scroll direction
        new_scroll = self._get_selected_scroll_direction()
        set_scroll_direction(new_scroll)
        log.debug(f"Applied scroll direction: {new_scroll.value}")

        # Save theme mode
        new_theme = self._get_selected_theme_mode()
        set_theme_mode(new_theme)
        apply_theme(new_theme)
        log.debug(f"Applied theme mode: {new_theme.value}")

        # Update original values (so cancel won't revert)
        self._original_scroll_direction = new_scroll
        self._original_theme_mode = new_theme

    def _on_accepted(self):
        """Handle OK button click."""
        self._apply_settings()
        self.accept()

    def _on_rejected(self):
        """Handle Cancel button click - revert to original settings."""
        # Revert theme if changed
        if self._get_selected_theme_mode() != self._original_theme_mode:
            apply_theme(self._original_theme_mode)

        self.reject()

    def _reset_to_defaults(self):
        """Reset all preferences to default values (System for all settings)."""
        # Set UI to defaults
        self.scroll_system_radio.setChecked(True)
        self.theme_system_radio.setChecked(True)

        # Apply the defaults
        set_scroll_direction(ScrollDirection.SYSTEM)
        set_theme_mode(ThemeMode.SYSTEM)
        apply_theme(ThemeMode.SYSTEM)

        # Update original values
        self._original_scroll_direction = ScrollDirection.SYSTEM
        self._original_theme_mode = ThemeMode.SYSTEM

        log.debug("Reset all preferences to defaults")
