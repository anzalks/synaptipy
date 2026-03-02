# src/Synaptipy/application/gui/analysis_config_dialog.py
# -*- coding: utf-8 -*-
"""
Dialog for configuring global analysis default parameters.
"""
import json
import logging
from typing import Any, Dict, Optional

from PySide6 import QtCore, QtWidgets  # noqa: F401

from Synaptipy.application.gui.ui_generator import ParameterWidgetGenerator
from Synaptipy.core.analysis.registry import AnalysisRegistry

log = logging.getLogger(__name__)


class AnalysisConfigDialog(QtWidgets.QDialog):
    """
    Dialog to view and edit default parameters for all registered analyses.
    Supports saving/loading configurations to JSON.
    """

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("Analysis Configuration")
        self.resize(800, 600)

        # Store widget generators to retrieve values
        self._generators: Dict[str, ParameterWidgetGenerator] = {}

        self._setup_ui()
        self._populate_tabs()

    def _setup_ui(self):
        """Setup the dialog UI."""
        main_layout = QtWidgets.QVBoxLayout(self)

        # Description
        desc = QtWidgets.QLabel(
            "Configure default parameters for analysis modules.\n"
            "Changes will apply to new analysis tabs or when resetting parameters."
        )
        desc.setStyleSheet("color: gray;")
        main_layout.addWidget(desc)

        # Tab Widget for Analyses
        self.tab_widget = QtWidgets.QTabWidget()
        main_layout.addWidget(self.tab_widget)

        # Buttons
        button_layout = QtWidgets.QHBoxLayout()

        # IO Buttons
        self.save_btn = QtWidgets.QPushButton("Save Config...")
        self.save_btn.clicked.connect(self._save_configuration)
        self.load_btn = QtWidgets.QPushButton("Load Config...")
        self.load_btn.clicked.connect(self._load_configuration)
        self.factory_btn = QtWidgets.QPushButton("Restore Factory Defaults")
        self.factory_btn.clicked.connect(self._restore_factory_defaults)

        button_layout.addWidget(self.save_btn)
        button_layout.addWidget(self.load_btn)
        button_layout.addWidget(self.factory_btn)
        button_layout.addStretch()

        # Dialog Buttons
        self.button_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok | QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        self.button_box.accepted.connect(self._on_accepted)
        self.button_box.rejected.connect(self.reject)

        button_layout.addWidget(self.button_box)
        main_layout.addLayout(button_layout)

    def _populate_tabs(self):
        """Populate tabs with registered analyses."""
        self.tab_widget.clear()
        self._generators.clear()

        # Get all registered analyses
        analysis_names = sorted(AnalysisRegistry.list_analysis())

        for name in analysis_names:
            meta = AnalysisRegistry.get_metadata(name)
            ui_params = meta.get("ui_params", [])

            if not ui_params:
                continue

            # Create tab page
            page = QtWidgets.QWidget()
            layout = QtWidgets.QFormLayout(page)

            # Use ParameterWidgetGenerator to create UI
            # We use a NEW generator for each tab
            generator = ParameterWidgetGenerator(layout)
            generator.generate_widgets(ui_params, callback=None)  # No callback needed for realtime updates here

            # Store generator to gather params later
            self._generators[name] = generator

            # Add to tab widget
            # Use display name if available, else registered name
            display_name = name.replace("_", " ").title()

            # Scroll area for long lists
            scroll = QtWidgets.QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setWidget(page)

            self.tab_widget.addTab(scroll, display_name)

    def _gather_all_params(self) -> Dict[str, Dict[str, Any]]:
        """Gather current values from all tabs."""
        config = {}
        for name, generator in self._generators.items():
            params = generator.gather_params()
            if params:
                config[name] = params
        return config

    def _apply_configuration(self, config: Dict[str, Dict[str, Any]]):
        """
        Apply configuration to AnalysisRegistry.
        config: { analysis_name: { param_name: value } }
        """
        for name, defaults in config.items():
            AnalysisRegistry.update_default_params(name, defaults)
        log.info("Applied new analysis configuration defaults.")

    def _on_accepted(self):
        """Handle OK button."""
        config = self._gather_all_params()
        self._apply_configuration(config)
        self.accept()

    def _save_configuration(self):
        """Save current configuration to JSON."""
        config = self._gather_all_params()

        file_path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Save Analysis Configuration", "", "JSON Files (*.json)"
        )
        if not file_path:
            return

        try:
            with open(file_path, "w") as f:
                json.dump(config, f, indent=4)
            QtWidgets.QMessageBox.information(self, "Success", f"Configuration saved to:\n{file_path}")
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Error", f"Failed to save configuration:\n{e}")

    def _load_configuration(self):
        """Load configuration from JSON."""
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Load Analysis Configuration", "", "JSON Files (*.json)"
        )
        if not file_path:
            return

        try:
            with open(file_path, "r") as f:
                config = json.load(f)

            # Apply to UI
            self._apply_to_ui(config)

            QtWidgets.QMessageBox.information(self, "Success", "Configuration loaded. Click OK to apply.")
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Error", f"Failed to load configuration:\n{e}")

    def _apply_to_ui(self, config: Dict[str, Dict[str, Any]]):
        """Update UI widgets with values from config."""
        for name, params in config.items():
            if name in self._generators:
                generator = self._generators[name]
                generator.set_params(params)

    def _restore_factory_defaults(self):
        """Reset UI to factory defaults."""
        reply = QtWidgets.QMessageBox.question(
            self,
            "Restore Defaults",
            "Are you sure you want to restore all parameters to factory defaults?",
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
        )
        if reply == QtWidgets.QMessageBox.StandardButton.Yes:
            # 1. Reset Registry
            AnalysisRegistry.reset_to_factory()
            # 2. Re-populate UI
            self._populate_tabs()
            QtWidgets.QMessageBox.information(self, "Restored", "Factory defaults restored.")
