    def _on_threshold_dragged(self):
        """Handle threshold line drag event."""
        if not self.threshold_line:
            return

        new_val = self.threshold_line.value()
        log.debug(f"Threshold dragged to: {new_val}")

        # Update parameter widget
        if hasattr(self, "param_generator") and "threshold" in self.param_generator.widgets:
            widget = self.param_generator.widgets["threshold"]
            # Block signals to prevent loop (param change -> plot update -> line update)
            # Actually MetadataDriven tab usually regenerates params on change or uses debounce.
            # But the widget itself might trigger immediate change.
            signals_blocked = widget.blockSignals(True)
            if isinstance(widget, QtWidgets.QDoubleSpinBox):
                widget.setValue(new_val)
            widget.blockSignals(signals_blocked)

        # Trigger analysis (debounce handled by BaseAnalysisTab._on_param_changed usually)
        # But we need to explicitly trigger it if blocking signals prevented it.
        # Or better: don't block signals, let it flow?
        # If we update widget, it triggers _on_param_changed.
        # _on_param_changed triggers _trigger_analysis (debounced).
        # _trigger_analysis calls _execute_core_analysis -> results -> _on_analysis_result -> _plot_analysis_visualizations.
        # _plot_analysis_visualizations updates line position.
        # If line position is same, no loop.
        # So we can just update widget and let signals flow!
        
        # However, to be safe, we can manually trigger if needed.
        # Let's try updating widget normally.
        if hasattr(self, "param_generator") and "threshold" in self.param_generator.widgets:
             widget = self.param_generator.widgets["threshold"]
             if isinstance(widget, QtWidgets.QDoubleSpinBox):
                widget.setValue(new_val)
