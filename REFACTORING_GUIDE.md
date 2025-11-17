# AI Model Refactoring Guide for Synaptipy

## Introduction

This document provides a step-by-step guide for an AI model to refactor the Synaptipy analysis module. The goal is to unify methods, remove significant code duplication across analysis tabs, and improve the overall workflow efficiency.

Follow each phase in order, as they build upon each other.

---

## Phase 1: Unify Data Selection and Plotting in `BaseAnalysisTab`

**Objective**: Move all common data selection (channel, trial) and plotting logic from individual tabs into `BaseAnalysisTab`. Subclasses should no longer manage this boilerplate.

### Step 1.1: Modify `BaseAnalysisTab` (`base.py`)

1.  **Add UI Element Attributes**: In `BaseAnalysisTab.__init__`, add attributes for the shared UI elements.
    ```python
    self.signal_channel_combobox: Optional[QtWidgets.QComboBox] = None
    self.data_source_combobox: Optional[QtWidgets.QComboBox] = None
    self._current_plot_data: Optional[Dict[str, Any]] = None
    ```

2.  **Create a Centralized UI Setup Method**: Create a new method `_setup_data_selection_ui(self, layout)` in `BaseAnalysisTab`. This method will create the `QFormLayout` and add the `analysis_item_combo`, `signal_channel_combobox`, and `data_source_combobox` to the provided `layout`.

3.  **Enhance `_on_analysis_item_selected`**: Modify this method to handle populating the `signal_channel_combobox` and `data_source_combobox`. This logic should be moved from the individual tabs. It should find the first available channel, determine `num_trials` and `has_average`, and populate the source combobox accordingly. After populating, it should automatically trigger `_plot_selected_data()`.

4.  **Create Centralized Plotting Method**: Create a new method `_plot_selected_data` in `BaseAnalysisTab`.
    *   This method will be connected to the `currentIndexChanged` signals of `signal_channel_combobox` and `data_source_combobox`.
    *   It will be responsible for:
        *   Getting the selected channel and data source.
        *   Fetching the data (`time_vec`, `data_vec`, `units`, `sampling_rate`) from the `_selected_item_recording`.
        *   Storing this information in `self._current_plot_data`.
        *   Clearing the `plot_widget`.
        *   Plotting the main data trace.
        *   Setting plot labels and title.
        *   Calling `self.set_data_ranges()` for zoom sync.
        *   **Crucially, at the end, it must call a new abstract method: `self._on_data_plotted()`**.

5.  **Define Hook Method**: Add a new (virtual, not strictly abstract) method to `BaseAnalysisTab`.
    ```python
    def _on_data_plotted(self):
        """
        Hook for subclasses, called after new data has been successfully plotted
        by the base class. Subclasses should implement this to add their specific
        plot items (e.g., interactive regions) or update parameter ranges.
        """
        pass # Subclasses will override this.
    ```
6.  **Connect Signals**: In `BaseAnalysisTab`, add connections for the new comboboxes to `_plot_selected_data`.

### Step 1.2: Refactor Subclass Tabs (e.g., `rmp_tab.py`, `rin_tab.py`)

For **each** analysis tab (`rmp_tab.py`, `rin_tab.py`, `spike_tab.py`, `event_detection_tab.py`):

1.  **Remove UI Attributes**: Delete `self.signal_channel_combobox` and `self.data_source_combobox` from the subclass `__init__`.
2.  **Simplify `_setup_ui`**:
    *   Remove the code that creates and adds the channel and data source comboboxes.
    *   Instead, call the new `self._setup_data_selection_ui(layout)` from the base class.
3.  **Delete Redundant Methods**:
    *   Delete the `_plot_selected_channel_trace` or `_plot_selected_trace` method entirely.
    *   Delete the slots that were connected to the combobox signals.
4.  **Simplify `_update_ui_for_selected_item`**:
    *   This method in the subclass is no longer needed, as the base class now handles the entire flow from item selection to plotting. Delete it.
5.  **Implement `_on_data_plotted`**:
    *   Create the `_on_data_plotted(self)` method.
    *   Move any logic that needs to happen *after* plotting into this method. This includes adding `LinearRegionItem`s or `ScatterPlotItem`s to the plot.

---

## Phase 2: Unify Analysis Execution with a Template Method

**Objective**: Create a single, final method in `BaseAnalysisTab` that orchestrates the analysis execution, while subclasses provide the specific implementation details.

### Step 2.1: Modify `BaseAnalysisTab` (`base.py`)

1.  **Add a `run_analysis_button`**: Add `self.run_analysis_button` to the `__init__` and a `_setup_run_button` method. Subclasses can call this to add a standardized "Run Analysis" button.

2.  **Create the Template Method**: Create a new method `_trigger_analysis`.
    *   This method should not be overridden by subclasses. It will contain the generic workflow: set wait cursor, `try...finally` block for error handling, and calls to new abstract methods.
    
    ```python
    # In BaseAnalysisTab
    @QtCore.Slot()
    def _trigger_analysis(self):
        if not self._current_plot_data:
            # ... show error ...
            return

        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
        self._last_analysis_result = None
        try:
            # 1. Gather specific parameters from the subclass UI
            params = self._gather_analysis_parameters()

            # 2. Execute the core logic, passing in current data
            results = self._execute_core_analysis(params, self._current_plot_data)
            self._last_analysis_result = results # Store for saving

            # 3. Display results in UI
            self._display_analysis_results(results)

            # 4. Update plot with visualizations
            self._plot_analysis_visualizations(results)

            self._set_save_button_enabled(True)
        except Exception as e:
            log.error(f"Analysis failed in {self.get_display_name()}: {e}", exc_info=True)
            # ... show error message to user ...
            self._set_save_button_enabled(False)
        finally:
            QtWidgets.QApplication.restoreOverrideCursor()
    ```

3.  **Define Abstract Helper Methods**: Add the following new abstract methods to `BaseAnalysisTab` using the `abc` module.
    ```python
    from abc import ABC, abstractmethod

    class BaseAnalysisTab(QtWidgets.QWidget, ABC):
        # ... existing stuff ...

        @abstractmethod
        def _gather_analysis_parameters(self) -> Dict[str, Any]:
            """Subclass must implement this to read parameters from its UI widgets."""
            pass

        @abstractmethod
        def _execute_core_analysis(self, params: Dict[str, Any], data: Dict[str, Any]) -> Dict[str, Any]:
            """Subclass must implement this to call its core analysis function."""
            pass

        @abstractmethod
        def _display_analysis_results(self, results: Dict[str, Any]):
            """Subclass must implement this to update its results labels/text edits."""
            pass

        @abstractmethod
        def _plot_analysis_visualizations(self, results: Dict[str, Any]):
            """Subclass must implement this to add markers/lines to the plot."""
            pass
    ```

### Step 2.2: Refactor Subclass Tabs

For **each** analysis tab:

1.  **Remove Old Execution Logic**: Delete the old `_run_..._analysis` method.
2.  **Implement Abstract Methods**: Implement all four new abstract methods:
    *   `_gather_analysis_parameters`: Read values from `self.threshold_edit`, spinboxes, etc., and return them in a dictionary.
    *   `_execute_core_analysis`: Take the `params` dict and the `data` dict. Call the specific function from `core.analysis` (e.g., `spike_analysis.detect_spikes_threshold`). Return the results in a structured dictionary.
    *   `_display_analysis_results`: Take the `results` dict and format a string to display in `self.results_textedit`.
    *   `_plot_analysis_visualizations`: Take the `results` dict and use it to call `self.spike_markers_item.setData(...)` or `self.baseline_line.setValue(...)`.

---

## Phase 3: Implement Real-Time Parameter Tuning

**Objective**: Make the UI more interactive by automatically re-running analyses when parameters are changed.

### Step 3.1: Add a Debounce Timer to `BaseAnalysisTab`

1.  In `BaseAnalysisTab.__init__`, add a `QTimer`.
    ```python
    self.debounce_timer = QTimer(self)
    self.debounce_timer.setSingleShot(True)
    self.debounce_timer.timeout.connect(self._trigger_analysis)
    ```

### Step 3.2: Modify Subclass Tabs

1.  In each subclass's `_connect_signals` method, connect the relevant parameter widgets to a new debounce handler.
    ```python
    # In SpikeAnalysisTab._connect_signals
    self.threshold_edit.textChanged.connect(self._on_parameter_changed)
    self.refractory_edit.textChanged.connect(self._on_parameter_changed)

    # In RinAnalysisTab._connect_signals (for interactive mode)
    self.manual_delta_i_spinbox.valueChanged.connect(self._on_parameter_changed)
    ```

2.  Add the `_on_parameter_changed` handler to each subclass.
    ```python
    # In SpikeAnalysisTab
    def _on_parameter_changed(self):
        """Called when a parameter widget's value changes."""
        # Optional: Add a check for interactive mode if desired
        # Start or restart the timer. The analysis will run after 250ms of inactivity.
        self.debounce_timer.start(250)
    ```

This will make the workflow much smoother for tuning parameters. The "Run" button will now primarily be for manual mode in tabs that have it.

---

## Phase 4: Unify Results Management (Future Direction)

**Objective**: Centralize all saved analysis results into a single, powerful view instead of just a simple list.

This is a larger architectural change and should be tackled after the above refactoring is complete.

1.  **Modify `ExporterTab`**: Rename `ExporterTab` to `ResultsTab`.
2.  **Replace `QListWidget`**: Change the results list from a simple list to a `QTableWidget`.
3.  **Define Table Columns**: Create columns for common data points: `Analysis Type`, `Source File`, `Channel`, `Trial`, `Result Value`, `Units`, etc.
4.  **Update `MainWindow.add_saved_result`**: Modify this method to take the result dictionary and populate a new row in the `ResultsTab`'s table instead of adding a string to a list.
5.  **Add Functionality**: Add buttons to the `ResultsTab` for `Export Selected to CSV`, `Export All`, `Clear Results`, and `Group By...`.

This phase will provide a much more professional and useful way for users to manage and export their analysis data.

