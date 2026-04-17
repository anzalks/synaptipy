# src/Synaptipy/application/gui/preferences_dialog.py
# -*- coding: utf-8 -*-
"""
Preferences Dialog for Synaptipy.

Provides a unified preferences interface for scroll direction, theme,
plugin, and performance settings.
"""

import logging
import multiprocessing
from typing import Optional

from PySide6 import QtCore, QtWidgets

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
    - Extensions (custom plugins)
    """

    # Emitted when the user saves/applies a changed plugin-enable state.
    # The bool argument is the new value (True = plugins enabled).
    sigPluginsToggled = QtCore.Signal(bool)

    # Emitted when performance settings are saved.
    # The dict contains 'max_cpu_cores' (int) and 'max_ram_allocation_gb' (float).
    sigPerformanceChanged = QtCore.Signal(dict)

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("Preferences")
        self.setMinimumWidth(450)
        self.setMinimumHeight(350)

        self._settings = QtCore.QSettings()

        # Store original values for cancel
        self._original_scroll_direction = get_scroll_direction()
        self._original_theme_mode = get_theme_mode()
        self._original_enable_plugins = self._settings.value("enable_plugins", True, type=bool)
        self._cpu_count = multiprocessing.cpu_count()

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

        # Performance tab
        self._create_performance_tab()

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

        # --- Extensions / Plugins Settings Group ---
        plugins_group = QtWidgets.QGroupBox("Extensions")
        plugins_layout = QtWidgets.QVBoxLayout(plugins_group)

        plugins_description = QtWidgets.QLabel(
            "Custom plugins are loaded from <b>~/.synaptipy/plugins/</b> and " "<b>examples/plugins/</b> at startup."
        )
        plugins_description.setWordWrap(True)
        plugins_description.setStyleSheet("color: gray; font-size: 11px;")
        plugins_layout.addWidget(plugins_description)

        self.enable_plugins_checkbox = QtWidgets.QCheckBox("Enable Custom Plugins")
        self.enable_plugins_checkbox.setToolTip(
            "When checked, Synaptipy loads Python plugins from the user and examples plugin directories."
        )
        plugins_layout.addWidget(self.enable_plugins_checkbox)

        layout.addWidget(plugins_group)

        # Spacer
        layout.addStretch()

        self.tab_widget.addTab(tab, "General")

    def _create_performance_tab(self) -> None:
        """Create the Performance settings tab (CPU cores and RAM allocation)."""
        tab = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(tab)
        layout.setSpacing(20)

        # --- CPU Group ---
        cpu_group = QtWidgets.QGroupBox("Parallel Processing")
        cpu_layout = QtWidgets.QFormLayout(cpu_group)

        cpu_desc = QtWidgets.QLabel(
            "Number of CPU cores used for batch analysis. "
            f"This machine has {self._cpu_count} logical core(s). "
            "Set to 1 to disable parallelism (safer for debugging)."
        )
        cpu_desc.setWordWrap(True)
        cpu_desc.setStyleSheet("color: gray; font-size: 11px;")
        cpu_layout.addRow(cpu_desc)

        self.cpu_cores_spinbox = QtWidgets.QSpinBox()
        self.cpu_cores_spinbox.setMinimum(1)
        self.cpu_cores_spinbox.setMaximum(max(1, self._cpu_count))
        self.cpu_cores_spinbox.setSuffix(f" / {self._cpu_count}")
        self.cpu_cores_spinbox.setToolTip("Max CPU cores for parallel batch analysis")
        cpu_layout.addRow("Max CPU cores:", self.cpu_cores_spinbox)
        layout.addWidget(cpu_group)

        # --- RAM Group ---
        ram_group = QtWidgets.QGroupBox("Memory")
        ram_layout = QtWidgets.QFormLayout(ram_group)

        ram_desc = QtWidgets.QLabel(
            "Approximate RAM ceiling for batch analysis. "
            "The engine calls gc.collect() after each file regardless of this setting."
        )
        ram_desc.setWordWrap(True)
        ram_desc.setStyleSheet("color: gray; font-size: 11px;")
        ram_layout.addRow(ram_desc)

        self.ram_spinbox = QtWidgets.QDoubleSpinBox()
        self.ram_spinbox.setMinimum(0.5)
        self.ram_spinbox.setMaximum(512.0)
        self.ram_spinbox.setDecimals(1)
        self.ram_spinbox.setSingleStep(0.5)
        self.ram_spinbox.setSuffix(" GB")
        self.ram_spinbox.setToolTip("Target maximum RAM for batch analysis (informational; enforced via gc)")
        ram_layout.addRow("Max RAM allocation:", self.ram_spinbox)
        layout.addWidget(ram_group)

        layout.addStretch()
        self.tab_widget.addTab(tab, "Performance")

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

        # Plugins toggle
        self.enable_plugins_checkbox.setChecked(self._settings.value("enable_plugins", True, type=bool))

        # Performance settings
        saved_cores = self._settings.value("performance/max_cpu_cores", 1, type=int)
        self.cpu_cores_spinbox.setValue(max(1, min(saved_cores, self._cpu_count)))
        saved_ram = self._settings.value("performance/max_ram_allocation_gb", 4.0, type=float)
        self.ram_spinbox.setValue(max(0.5, saved_ram))

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

        # Save plugins toggle and emit signal if it changed
        plugins_enabled = self.enable_plugins_checkbox.isChecked()
        plugins_changed = plugins_enabled != self._original_enable_plugins
        self._settings.setValue("enable_plugins", plugins_enabled)
        log.debug(f"Applied enable_plugins: {plugins_enabled} (changed={plugins_changed})")

        # Save performance settings and emit if changed
        new_cores = self.cpu_cores_spinbox.value()
        new_ram = self.ram_spinbox.value()
        old_cores = self._settings.value("performance/max_cpu_cores", 1, type=int)
        old_ram = self._settings.value("performance/max_ram_allocation_gb", 4.0, type=float)
        self._settings.setValue("performance/max_cpu_cores", new_cores)
        self._settings.setValue("performance/max_ram_allocation_gb", new_ram)
        if new_cores != old_cores or new_ram != old_ram:
            perf = {"max_cpu_cores": new_cores, "max_ram_allocation_gb": new_ram}
            log.debug("Performance settings changed: %s", perf)
            self.sigPerformanceChanged.emit(perf)

        # Update original values (so cancel won't revert)
        self._original_scroll_direction = new_scroll
        self._original_theme_mode = new_theme
        self._original_enable_plugins = plugins_enabled

        if plugins_changed:
            self.sigPluginsToggled.emit(plugins_enabled)

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
        self.enable_plugins_checkbox.setChecked(True)
        self.cpu_cores_spinbox.setValue(1)
        self.ram_spinbox.setValue(4.0)

        # Apply the defaults
        set_scroll_direction(ScrollDirection.SYSTEM)
        set_theme_mode(ThemeMode.SYSTEM)
        apply_theme(ThemeMode.SYSTEM)
        self._settings.setValue("enable_plugins", True)
        self._settings.setValue("performance/max_cpu_cores", 1)
        self._settings.setValue("performance/max_ram_allocation_gb", 4.0)

        # Update original values
        self._original_scroll_direction = ScrollDirection.SYSTEM
        self._original_theme_mode = ThemeMode.SYSTEM
        self._original_enable_plugins = True

        log.debug("Reset all preferences to defaults")
