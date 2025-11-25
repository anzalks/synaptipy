# src/Synaptipy/application/gui/batch_dialog.py
# -*- coding: utf-8 -*-
"""
Batch Analysis Dialog for Synaptipy.

Provides a user-friendly dialog for configuring and running batch analysis
across multiple files using a pipeline-based approach.

Author: Anzal KS <anzal.ks@gmail.com>
"""
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime

from PySide6 import QtCore, QtGui, QtWidgets
import pandas as pd

from Synaptipy.core.analysis.batch_engine import BatchAnalysisEngine
from Synaptipy.core.analysis.registry import AnalysisRegistry
from Synaptipy.shared.styling import style_button, style_label

log = logging.getLogger('Synaptipy.application.gui.batch_dialog')


# ==============================================================================
# Worker Thread for Background Processing
# ==============================================================================

class BatchWorkerSignals(QtCore.QObject):
    """Signals for the batch worker thread."""
    progress = QtCore.Signal(int, int, str)  # current, total, message
    finished = QtCore.Signal(object)  # DataFrame result
    error = QtCore.Signal(str)  # Error message


class BatchWorker(QtCore.QThread):
    """
    Worker thread for running batch analysis in the background.
    
    This prevents the UI from freezing during long-running batch operations.
    """
    
    def __init__(self, 
                 engine: BatchAnalysisEngine,
                 files: List[Path],
                 pipeline_config: List[Dict[str, Any]],
                 channel_filter: Optional[List[str]] = None,
                 parent=None):
        super().__init__(parent)
        self.engine = engine
        self.files = files
        self.pipeline_config = pipeline_config
        self.channel_filter = channel_filter
        self.signals = BatchWorkerSignals()
        self._cancelled = False
    
    def run(self):
        """Execute the batch analysis."""
        try:
            def progress_callback(current, total, message):
                if not self._cancelled:
                    self.signals.progress.emit(current, total, message)
            
            result_df = self.engine.run_batch(
                files=self.files,
                pipeline_config=self.pipeline_config,
                progress_callback=progress_callback,
                channel_filter=self.channel_filter
            )
            
            if not self._cancelled:
                self.signals.finished.emit(result_df)
                
        except Exception as e:
            log.error(f"Batch analysis error: {e}", exc_info=True)
            self.signals.error.emit(str(e))
    
    def cancel(self):
        """Request cancellation of the batch analysis."""
        self._cancelled = True
        self.engine.cancel()


# ==============================================================================
# Pipeline Step Configuration Widget
# ==============================================================================

class PipelineStepWidget(QtWidgets.QFrame):
    """Widget for displaying and editing a single pipeline step."""
    
    remove_requested = QtCore.Signal(object)  # Emits self when remove is clicked
    
    def __init__(self, step_config: Dict[str, Any], step_index: int, parent=None):
        super().__init__(parent)
        self.step_config = step_config
        self.step_index = step_index
        self._setup_ui()
    
    def _setup_ui(self):
        """Setup the UI for this pipeline step."""
        self.setFrameStyle(QtWidgets.QFrame.Shape.StyledPanel | QtWidgets.QFrame.Shadow.Raised)
        self.setLineWidth(1)
        
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(8)
        
        # Step number
        step_label = QtWidgets.QLabel(f"#{self.step_index + 1}")
        step_label.setMinimumWidth(30)
        style_label(step_label, 'subheading')
        layout.addWidget(step_label)
        
        # Analysis name
        analysis_name = self.step_config.get('analysis', 'Unknown')
        name_label = QtWidgets.QLabel(analysis_name)
        name_label.setMinimumWidth(120)
        layout.addWidget(name_label)
        
        # Scope
        scope = self.step_config.get('scope', 'first_trial')
        scope_label = QtWidgets.QLabel(f"[{scope}]")
        scope_label.setMinimumWidth(80)
        layout.addWidget(scope_label)
        
        # Parameters summary
        params = self.step_config.get('params', {})
        if params:
            params_str = ", ".join(f"{k}={v}" for k, v in list(params.items())[:3])
            if len(params) > 3:
                params_str += "..."
        else:
            params_str = "(default params)"
        params_label = QtWidgets.QLabel(params_str)
        params_label.setStyleSheet("color: gray;")
        layout.addWidget(params_label, stretch=1)
        
        # Remove button
        remove_btn = QtWidgets.QPushButton("×")
        remove_btn.setFixedSize(24, 24)
        remove_btn.setToolTip("Remove this step")
        remove_btn.clicked.connect(lambda: self.remove_requested.emit(self))
        layout.addWidget(remove_btn)
    
    def get_config(self) -> Dict[str, Any]:
        """Return the step configuration."""
        return self.step_config


# ==============================================================================
# Add Pipeline Step Dialog
# ==============================================================================

class AddStepDialog(QtWidgets.QDialog):
    """Dialog for adding a new analysis step to the pipeline."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Analysis Step")
        self.setMinimumWidth(450)
        self._result_config = None
        self._setup_ui()
    
    def _setup_ui(self):
        """Setup the dialog UI."""
        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(12)
        
        # Analysis Type Selection
        type_group = QtWidgets.QGroupBox("Analysis Type")
        type_layout = QtWidgets.QFormLayout(type_group)
        
        self.analysis_combo = QtWidgets.QComboBox()
        available_analyses = AnalysisRegistry.list_registered()
        if available_analyses:
            self.analysis_combo.addItems(sorted(available_analyses))
        else:
            self.analysis_combo.addItem("No analyses registered")
            self.analysis_combo.setEnabled(False)
        self.analysis_combo.currentTextChanged.connect(self._on_analysis_changed)
        type_layout.addRow("Analysis:", self.analysis_combo)
        
        # Description
        self.description_label = QtWidgets.QLabel()
        self.description_label.setWordWrap(True)
        self.description_label.setStyleSheet("color: gray; font-style: italic;")
        type_layout.addRow("", self.description_label)
        
        layout.addWidget(type_group)
        
        # Scope Selection
        scope_group = QtWidgets.QGroupBox("Data Scope")
        scope_layout = QtWidgets.QVBoxLayout(scope_group)
        
        self.scope_group = QtWidgets.QButtonGroup(self)
        
        scope_options = [
            ("average", "Average Trace", "Analyze the averaged trace across all trials"),
            ("all_trials", "All Trials", "Analyze each trial separately"),
            ("first_trial", "First Trial Only", "Analyze only the first trial"),
        ]
        
        for scope_id, scope_name, scope_desc in scope_options:
            radio = QtWidgets.QRadioButton(f"{scope_name} - {scope_desc}")
            radio.setProperty("scope_id", scope_id)
            self.scope_group.addButton(radio)
            scope_layout.addWidget(radio)
            if scope_id == "average":
                radio.setChecked(True)
        
        layout.addWidget(scope_group)
        
        # Parameters Section
        params_group = QtWidgets.QGroupBox("Parameters")
        self.params_layout = QtWidgets.QFormLayout(params_group)
        self.params_layout.setSpacing(8)
        
        # Dynamic parameter widgets will be added here
        self.param_widgets = {}
        
        layout.addWidget(params_group)
        
        # Buttons
        button_layout = QtWidgets.QHBoxLayout()
        button_layout.addStretch()
        
        cancel_btn = QtWidgets.QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)
        
        add_btn = QtWidgets.QPushButton("Add Step")
        style_button(add_btn, 'primary')
        add_btn.clicked.connect(self._on_add_clicked)
        button_layout.addWidget(add_btn)
        
        layout.addLayout(button_layout)
        
        # Initialize with first analysis
        if available_analyses:
            self._on_analysis_changed(self.analysis_combo.currentText())
    
    def _on_analysis_changed(self, analysis_name: str):
        """Update UI when analysis type changes."""
        # Clear existing parameter widgets
        for widget in self.param_widgets.values():
            self.params_layout.removeRow(widget)
        self.param_widgets.clear()
        
        # Get analysis info
        info = BatchAnalysisEngine.get_analysis_info(analysis_name)
        if info:
            docstring = info.get('docstring', 'No description available.')
            # Extract first paragraph
            first_para = docstring.split('\n\n')[0].strip()
            self.description_label.setText(first_para[:200] + "..." if len(first_para) > 200 else first_para)
        else:
            self.description_label.setText("No description available.")
        
        # Add common parameter widgets based on analysis type
        self._add_parameter_widgets(analysis_name)
    
    def _add_parameter_widgets(self, analysis_name: str):
        """Add parameter widgets based on the analysis type."""
        # Get metadata from registry
        metadata = AnalysisRegistry.get_metadata(analysis_name)
        ui_params = metadata.get('ui_params', [])
        
        if ui_params:
            for param in ui_params:
                param_type = param.get('type', 'float')
                name = param.get('name')
                label = param.get('label', name)
                
                if param_type == 'float':
                    default = param.get('default', 0.0)
                    min_val = param.get('min', -10000.0)
                    max_val = param.get('max', 10000.0)
                    decimals = param.get('decimals', 2)
                    self._add_param(name, label, default, min_val, max_val, decimals)
                    
                elif param_type == 'choice':
                    choices = param.get('choices', [])
                    default = param.get('default')
                    
                    combo = QtWidgets.QComboBox()
                    combo.addItems(choices)
                    if default and default in choices:
                        combo.setCurrentText(default)
                        
                    self.params_layout.addRow(label, combo)
                    self.param_widgets[name] = combo
                    
        else:
            # Fallback for legacy/unmigrated analysis types
            # This ensures we don't break existing analyses that haven't been migrated yet
            self._add_legacy_parameter_widgets(analysis_name)

    def _add_legacy_parameter_widgets(self, analysis_name: str):
        """Fallback for analysis types not yet migrated to metadata system."""
        if analysis_name == "rmp_analysis":
            self._add_param("baseline_start", "Baseline Start (s):", 0.0, 0.0, 10.0, 3)
            self._add_param("baseline_end", "Baseline End (s):", 0.1, 0.0, 10.0, 3)
            
        elif analysis_name == "rin_analysis":
            self._add_param("current_amplitude", "Current (pA):", -50.0, -1000.0, 1000.0, 1)
            self._add_param("baseline_start", "Baseline Start (s):", 0.0, 0.0, 10.0, 3)
            self._add_param("baseline_end", "Baseline End (s):", 0.1, 0.0, 10.0, 3)
            self._add_param("response_start", "Response Start (s):", 0.3, 0.0, 10.0, 3)
            self._add_param("response_end", "Response End (s):", 0.4, 0.0, 10.0, 3)
            
        elif analysis_name == "tau_analysis":
            self._add_param("stim_start_time", "Stim Start (s):", 0.1, 0.0, 10.0, 3)
            self._add_param("fit_duration", "Fit Duration (s):", 0.05, 0.001, 1.0, 3)
            
        elif analysis_name == "mini_detection":
            self._add_param("threshold", "Threshold:", 5.0, 0.1, 1000.0, 1)
            # Direction combo
            direction_combo = QtWidgets.QComboBox()
            direction_combo.addItems(["negative", "positive"])
            self.params_layout.addRow("Direction:", direction_combo)
            self.param_widgets["direction"] = direction_combo
            
        elif analysis_name in ["event_detection_threshold", "event_detection_deconvolution", "event_detection_baseline_peak"]:
            self._add_param("threshold", "Threshold:", 5.0, 0.1, 1000.0, 1)
            # Direction combo
            direction_combo = QtWidgets.QComboBox()
            direction_combo.addItems(["negative", "positive"])
            self.params_layout.addRow("Direction:", direction_combo)
            self.param_widgets["direction"] = direction_combo
        else:
            # Generic message for unknown analysis types
            info_label = QtWidgets.QLabel("Default parameters will be used.")
            info_label.setStyleSheet("color: gray; font-style: italic;")
            self.params_layout.addRow("", info_label)
            self.param_widgets["_info"] = info_label
    
    def _add_param(self, name: str, label: str, default: float, 
                   min_val: float, max_val: float, decimals: int):
        """Add a numeric parameter input."""
        spinbox = QtWidgets.QDoubleSpinBox()
        spinbox.setRange(min_val, max_val)
        spinbox.setDecimals(decimals)
        spinbox.setValue(default)
        spinbox.setSingleStep(10 ** (-decimals))
        self.params_layout.addRow(label, spinbox)
        self.param_widgets[name] = spinbox
    
    def _on_add_clicked(self):
        """Handle add button click."""
        analysis_name = self.analysis_combo.currentText()
        
        # Get selected scope
        selected_scope = "average"
        for button in self.scope_group.buttons():
            if button.isChecked():
                selected_scope = button.property("scope_id")
                break
        
        # Gather parameters
        params = {}
        for name, widget in self.param_widgets.items():
            if name.startswith("_"):
                continue
            if isinstance(widget, QtWidgets.QDoubleSpinBox):
                params[name] = widget.value()
            elif isinstance(widget, QtWidgets.QComboBox):
                params[name] = widget.currentText()
            elif isinstance(widget, QtWidgets.QSpinBox):
                params[name] = widget.value()
        
        self._result_config = {
            'analysis': analysis_name,
            'scope': selected_scope,
            'params': params
        }
        
        self.accept()
    
    def get_step_config(self) -> Optional[Dict[str, Any]]:
        """Get the configured step, or None if cancelled."""
        return self._result_config


# ==============================================================================
# Main Batch Analysis Dialog
# ==============================================================================

class BatchAnalysisDialog(QtWidgets.QDialog):
    """
    Main dialog for configuring and running batch analysis.
    
    Allows users to:
    - View the list of files to be processed
    - Build a pipeline of analysis steps
    - Run the batch analysis
    - Export results to CSV
    """
    
    def __init__(self, files: List[Path], parent=None):
        super().__init__(parent)
        self.files = files
        self.pipeline_steps: List[Dict[str, Any]] = []
        self.result_df: Optional[pd.DataFrame] = None
        self.worker: Optional[BatchWorker] = None
        self.engine = BatchAnalysisEngine()
        
        self.setWindowTitle("Batch Analysis")
        self.setMinimumSize(700, 600)
        self.resize(800, 700)
        
        self._setup_ui()
    
    def _setup_ui(self):
        """Setup the dialog UI."""
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setSpacing(12)
        
        # ==== Files Section ====
        files_group = QtWidgets.QGroupBox(f"Files to Process ({len(self.files)} files)")
        files_layout = QtWidgets.QVBoxLayout(files_group)
        
        self.files_list = QtWidgets.QListWidget()
        self.files_list.setMaximumHeight(100)
        self.files_list.setAlternatingRowColors(True)
        for f in self.files:
            item = QtWidgets.QListWidgetItem(f.name)
            item.setToolTip(str(f))
            self.files_list.addItem(item)
        files_layout.addWidget(self.files_list)
        
        main_layout.addWidget(files_group)
        
        # ==== Pipeline Section ====
        pipeline_group = QtWidgets.QGroupBox("Analysis Pipeline")
        pipeline_layout = QtWidgets.QVBoxLayout(pipeline_group)
        
        # Pipeline steps container with scroll
        self.pipeline_scroll = QtWidgets.QScrollArea()
        self.pipeline_scroll.setWidgetResizable(True)
        self.pipeline_scroll.setMinimumHeight(150)
        self.pipeline_scroll.setMaximumHeight(200)
        
        self.pipeline_container = QtWidgets.QWidget()
        self.pipeline_container_layout = QtWidgets.QVBoxLayout(self.pipeline_container)
        self.pipeline_container_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)
        self.pipeline_container_layout.setSpacing(4)
        
        # Placeholder label
        self.empty_pipeline_label = QtWidgets.QLabel("No analysis steps added. Click 'Add Step' to begin.")
        self.empty_pipeline_label.setStyleSheet("color: gray; font-style: italic;")
        self.empty_pipeline_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.pipeline_container_layout.addWidget(self.empty_pipeline_label)
        
        self.pipeline_scroll.setWidget(self.pipeline_container)
        pipeline_layout.addWidget(self.pipeline_scroll)
        
        # Pipeline buttons
        pipeline_btn_layout = QtWidgets.QHBoxLayout()
        
        add_step_btn = QtWidgets.QPushButton("+ Add Step")
        add_step_btn.setToolTip("Add an analysis step to the pipeline")
        add_step_btn.clicked.connect(self._on_add_step)
        pipeline_btn_layout.addWidget(add_step_btn)
        
        clear_pipeline_btn = QtWidgets.QPushButton("Clear All")
        clear_pipeline_btn.setToolTip("Remove all pipeline steps")
        clear_pipeline_btn.clicked.connect(self._on_clear_pipeline)
        pipeline_btn_layout.addWidget(clear_pipeline_btn)
        
        pipeline_btn_layout.addStretch()
        
        # Available analyses info
        available_count = len(AnalysisRegistry.list_registered())
        info_label = QtWidgets.QLabel(f"{available_count} analysis types available")
        info_label.setStyleSheet("color: gray;")
        pipeline_btn_layout.addWidget(info_label)
        
        pipeline_layout.addLayout(pipeline_btn_layout)
        main_layout.addWidget(pipeline_group)
        
        # ==== Progress Section ====
        progress_group = QtWidgets.QGroupBox("Progress")
        progress_layout = QtWidgets.QVBoxLayout(progress_group)
        
        self.progress_bar = QtWidgets.QProgressBar()
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)
        progress_layout.addWidget(self.progress_bar)
        
        self.status_label = QtWidgets.QLabel("Ready")
        self.status_label.setStyleSheet("color: gray;")
        progress_layout.addWidget(self.status_label)
        
        main_layout.addWidget(progress_group)
        
        # ==== Results Section ====
        results_group = QtWidgets.QGroupBox("Results")
        results_layout = QtWidgets.QVBoxLayout(results_group)
        
        self.results_table = QtWidgets.QTableWidget()
        self.results_table.setAlternatingRowColors(True)
        self.results_table.setMinimumHeight(150)
        self.results_table.horizontalHeader().setStretchLastSection(True)
        results_layout.addWidget(self.results_table)
        
        # Results info
        self.results_info_label = QtWidgets.QLabel("No results yet")
        self.results_info_label.setStyleSheet("color: gray;")
        results_layout.addWidget(self.results_info_label)
        
        main_layout.addWidget(results_group, stretch=1)
        
        # ==== Action Buttons ====
        button_layout = QtWidgets.QHBoxLayout()
        
        self.export_btn = QtWidgets.QPushButton("Export to CSV...")
        self.export_btn.setEnabled(False)
        self.export_btn.clicked.connect(self._on_export)
        button_layout.addWidget(self.export_btn)
        
        button_layout.addStretch()
        
        self.cancel_btn = QtWidgets.QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self._on_cancel)
        button_layout.addWidget(self.cancel_btn)
        
        self.run_btn = QtWidgets.QPushButton("Run Batch Analysis")
        style_button(self.run_btn, 'primary')
        self.run_btn.clicked.connect(self._on_run)
        button_layout.addWidget(self.run_btn)
        
        main_layout.addLayout(button_layout)
    
    def _on_add_step(self):
        """Open dialog to add a new pipeline step."""
        dialog = AddStepDialog(self)
        if dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            step_config = dialog.get_step_config()
            if step_config:
                self._add_pipeline_step(step_config)
    
    def _add_pipeline_step(self, step_config: Dict[str, Any]):
        """Add a step to the pipeline."""
        # Hide empty label
        self.empty_pipeline_label.setVisible(False)
        
        # Create step widget
        step_index = len(self.pipeline_steps)
        step_widget = PipelineStepWidget(step_config, step_index, self.pipeline_container)
        step_widget.remove_requested.connect(self._on_remove_step)
        
        self.pipeline_container_layout.addWidget(step_widget)
        self.pipeline_steps.append(step_config)
        
        log.info(f"Added pipeline step: {step_config.get('analysis')} [{step_config.get('scope')}]")
    
    def _on_remove_step(self, step_widget: PipelineStepWidget):
        """Remove a step from the pipeline."""
        # Find and remove the step
        step_config = step_widget.get_config()
        if step_config in self.pipeline_steps:
            self.pipeline_steps.remove(step_config)
        
        # Remove widget
        self.pipeline_container_layout.removeWidget(step_widget)
        step_widget.deleteLater()
        
        # Re-index remaining steps
        self._reindex_steps()
        
        # Show empty label if no steps
        if not self.pipeline_steps:
            self.empty_pipeline_label.setVisible(True)
    
    def _reindex_steps(self):
        """Re-index all step widgets after removal."""
        for i in range(self.pipeline_container_layout.count()):
            item = self.pipeline_container_layout.itemAt(i)
            if item and item.widget() and isinstance(item.widget(), PipelineStepWidget):
                # We'd need to update the step index display
                # For simplicity, we'll recreate the widgets
                pass
    
    def _on_clear_pipeline(self):
        """Clear all pipeline steps."""
        if not self.pipeline_steps:
            return
        
        reply = QtWidgets.QMessageBox.question(
            self,
            "Clear Pipeline",
            "Are you sure you want to remove all pipeline steps?",
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
            QtWidgets.QMessageBox.StandardButton.No
        )
        
        if reply == QtWidgets.QMessageBox.StandardButton.Yes:
            # Remove all step widgets
            while self.pipeline_container_layout.count() > 1:  # Keep the empty label
                item = self.pipeline_container_layout.takeAt(1)
                if item and item.widget():
                    item.widget().deleteLater()
            
            self.pipeline_steps.clear()
            self.empty_pipeline_label.setVisible(True)
    
    def _on_run(self):
        """Start the batch analysis."""
        if not self.pipeline_steps:
            QtWidgets.QMessageBox.warning(
                self,
                "No Pipeline Steps",
                "Please add at least one analysis step to the pipeline."
            )
            return
        
        if not self.files:
            QtWidgets.QMessageBox.warning(
                self,
                "No Files",
                "No files available for batch analysis."
            )
            return
        
        # Disable UI during processing
        self.run_btn.setEnabled(False)
        self.export_btn.setEnabled(False)
        self.cancel_btn.setText("Stop")
        self.progress_bar.setValue(0)
        self.status_label.setText("Starting batch analysis...")
        
        # Create and start worker
        self.worker = BatchWorker(
            engine=self.engine,
            files=self.files,
            pipeline_config=self.pipeline_steps
        )
        self.worker.signals.progress.connect(self._on_progress)
        self.worker.signals.finished.connect(self._on_finished)
        self.worker.signals.error.connect(self._on_error)
        self.worker.start()
    
    def _on_progress(self, current: int, total: int, message: str):
        """Update progress display."""
        if total > 0:
            percent = int((current / total) * 100)
            self.progress_bar.setValue(percent)
        self.status_label.setText(message)
    
    def _on_finished(self, result_df: pd.DataFrame):
        """Handle batch analysis completion."""
        self.result_df = result_df
        self.worker = None
        
        # Re-enable UI
        self.run_btn.setEnabled(True)
        self.cancel_btn.setText("Close")
        
        if result_df is not None and not result_df.empty:
            self.export_btn.setEnabled(True)
            self.progress_bar.setValue(100)
            self.status_label.setText(f"Completed: {len(result_df)} result rows")
            self._display_results(result_df)
        else:
            self.status_label.setText("Completed with no results")
            self.results_info_label.setText("No results generated")
    
    def _on_error(self, error_message: str):
        """Handle batch analysis error."""
        self.worker = None
        
        # Re-enable UI
        self.run_btn.setEnabled(True)
        self.cancel_btn.setText("Close")
        self.progress_bar.setValue(0)
        self.status_label.setText(f"Error: {error_message}")
        
        QtWidgets.QMessageBox.critical(
            self,
            "Batch Analysis Error",
            f"An error occurred during batch analysis:\n\n{error_message}"
        )
    
    def _on_cancel(self):
        """Cancel or close the dialog."""
        if self.worker and self.worker.isRunning():
            # Cancel running analysis
            reply = QtWidgets.QMessageBox.question(
                self,
                "Cancel Analysis",
                "Are you sure you want to cancel the running analysis?",
                QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
                QtWidgets.QMessageBox.StandardButton.No
            )
            
            if reply == QtWidgets.QMessageBox.StandardButton.Yes:
                self.worker.cancel()
                self.status_label.setText("Cancelling...")
        else:
            # Close dialog
            self.accept()
    
    def _display_results(self, df: pd.DataFrame):
        """Display results in the table widget."""
        self.results_table.clear()
        
        if df.empty:
            self.results_info_label.setText("No results to display")
            return
        
        # Setup table
        self.results_table.setRowCount(min(100, len(df)))  # Limit display rows
        self.results_table.setColumnCount(len(df.columns))
        self.results_table.setHorizontalHeaderLabels(df.columns.tolist())
        
        # Populate table
        for row_idx in range(min(100, len(df))):
            for col_idx, col_name in enumerate(df.columns):
                value = df.iloc[row_idx, col_idx]
                if pd.isna(value):
                    display_value = ""
                elif isinstance(value, float):
                    display_value = f"{value:.4g}"
                else:
                    display_value = str(value)
                
                item = QtWidgets.QTableWidgetItem(display_value)
                self.results_table.setItem(row_idx, col_idx, item)
        
        # Update info label
        if len(df) > 100:
            self.results_info_label.setText(f"Showing first 100 of {len(df)} rows")
        else:
            self.results_info_label.setText(f"{len(df)} rows")
        
        # Resize columns to content
        self.results_table.resizeColumnsToContents()
    
    def _on_export(self):
        """Export results to CSV."""
        if self.result_df is None or self.result_df.empty:
            QtWidgets.QMessageBox.warning(
                self,
                "No Results",
                "No results available to export."
            )
            return
        
        # Generate default filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_name = f"batch_analysis_{timestamp}.csv"
        
        file_path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "Export Results to CSV",
            default_name,
            "CSV Files (*.csv);;All Files (*)"
        )
        
        if file_path:
            try:
                self.result_df.to_csv(file_path, index=False)
                log.info(f"Exported batch results to: {file_path}")
                
                QtWidgets.QMessageBox.information(
                    self,
                    "Export Successful",
                    f"Results exported to:\n{file_path}"
                )
            except Exception as e:
                log.error(f"Failed to export results: {e}", exc_info=True)
                QtWidgets.QMessageBox.critical(
                    self,
                    "Export Failed",
                    f"Failed to export results:\n{str(e)}"
                )
    
    def closeEvent(self, event):
        """Handle dialog close."""
        if self.worker and self.worker.isRunning():
            reply = QtWidgets.QMessageBox.question(
                self,
                "Analysis Running",
                "An analysis is still running. Cancel it and close?",
                QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
                QtWidgets.QMessageBox.StandardButton.No
            )
            
            if reply == QtWidgets.QMessageBox.StandardButton.Yes:
                self.worker.cancel()
                self.worker.wait(5000)  # Wait up to 5 seconds
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()

