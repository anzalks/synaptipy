#!/usr/bin/env python3
"""
Unified Plot Factory for Synaptipy

This module provides a centralized way to create and configure PyQtGraph plots
with proper Windows compatibility and consistent styling across the application.

Author: Anzal
Email: anzal.ks@gmail.com
"""

import logging
from typing import Optional, Any
from PySide6 import QtCore, QtWidgets
import pyqtgraph as pg

from .plot_customization import get_plot_customization_manager

log = logging.getLogger(__name__)


class SynaptipyPlotFactory:
    """
    Centralized factory for creating PyQtGraph plots with Windows compatibility.

    This factory ensures all plots are created with consistent styling and
    proper error handling to prevent null pointer errors on Windows.
    """

    @staticmethod
    def create_plot_widget(
        parent: Optional[QtWidgets.QWidget] = None,
        background: str = "white",
        enable_grid: bool = True,
        mouse_mode: str = "rect",
    ) -> pg.PlotWidget:
        """
        Create a properly configured PlotWidget with Windows compatibility.

        Args:
            parent: Parent widget
            background: Background color ('white' or 'black')
            enable_grid: Whether to enable grid
            mouse_mode: Mouse interaction mode ('rect', 'pan', etc.)

        Returns:
            Configured PlotWidget
        """
        try:
            # Create the plot widget
            plot_widget = pg.PlotWidget(parent=parent)

            # Set background immediately
            plot_widget.setBackground(background)

            # Configure view box
            viewbox = plot_widget.getViewBox()
            if viewbox:
                if mouse_mode == "rect":
                    viewbox.setMouseMode(pg.ViewBox.RectMode)
                elif mouse_mode == "pan":
                    viewbox.setMouseMode(pg.ViewBox.PanMode)
                viewbox.mouseEnabled = True

            # Defer grid configuration to prevent Windows issues
            if enable_grid:
                QtCore.QTimer.singleShot(50, lambda: SynaptipyPlotFactory._configure_grid_safe(plot_widget))

            # Apply system theme colors to the selection rectangle
            try:
                from .zoom_theme import apply_theme_with_custom_selection

                # Apply custom selection rectangle with theme
                apply_theme_with_custom_selection(plot_widget.getViewBox())
            except Exception as e:
                log.debug(f"Failed to apply theme to plot widget: {e}")

            log.debug("Created plot widget successfully")
            return plot_widget

        except Exception as e:
            log.error(f"Failed to create plot widget: {e}")
            # Return a basic plot widget as fallback
            # Return a basic plot widget as fallback
            return pg.PlotWidget(parent=parent)

    @staticmethod
    def create_graphics_layout(
        parent: Optional[QtWidgets.QWidget] = None, background: str = "white"
    ) -> pg.GraphicsLayoutWidget:
        """
        Create a properly configured GraphicsLayoutWidget with Windows compatibility.
        """
        try:
            widget = pg.GraphicsLayoutWidget(parent=parent)
            widget.setBackground(background)
            log.debug("Created GraphicsLayoutWidget successfully")
            return widget
        except Exception as e:
            log.error(f"Failed to create GraphicsLayoutWidget: {e}")
            return pg.GraphicsLayoutWidget(parent=parent)

    @staticmethod
    def get_average_pen() -> pg.mkPen:
        """Get pen for average plots with current customization."""
        try:
            return get_plot_customization_manager().get_average_pen()
        except Exception as e:
            log.warning(f"Failed to get average pen, using default: {e}")
            return pg.mkPen(color="black", width=2)

    @staticmethod
    def get_single_trial_pen() -> pg.mkPen:
        """Get pen for single trial plots with current customization."""
        try:
            return get_plot_customization_manager().get_single_trial_pen()
        except Exception as e:
            log.warning(f"Failed to get single trial pen, using default: {e}")
            return pg.mkPen(color="blue", width=1)

    @staticmethod
    def get_grid_pen() -> Optional[pg.mkPen]:
        """Get pen for grid lines with current customization."""
        try:
            return get_plot_customization_manager().get_grid_pen()
        except Exception as e:
            log.warning(f"Failed to get grid pen, using default: {e}")
            return pg.mkPen(color="gray", width=1, alpha=0.3)

    @staticmethod
    def _configure_grid_safe(plot_widget: pg.PlotWidget) -> None:  # noqa: C901
        """
        Safely configure grid with Windows compatibility.
        Uses multiple retry attempts and extensive error checking.
        """
        max_retries = 3
        retry_delay = 25  # ms

        def attempt_grid_config(attempt: int = 0):
            try:
                plot_item = plot_widget.getPlotItem()
                if not plot_item:
                    if attempt < max_retries:
                        QtCore.QTimer.singleShot(retry_delay, lambda: attempt_grid_config(attempt + 1))
                    return

                # Enable grid safely with error handling
                try:
                    from .plot_customization import is_grid_enabled, get_grid_pen

                    if is_grid_enabled():
                        grid_pen = get_grid_pen()
                        if grid_pen:
                            # Get alpha value from pen color
                            alpha = 0.3  # Default alpha
                            if hasattr(grid_pen, "color") and hasattr(grid_pen.color(), "alpha"):
                                alpha = grid_pen.color().alpha() / 255.0
                                log.debug(f"Using grid pen alpha: {alpha} (opacity: {alpha * 100:.1f}%)")
                            else:
                                log.debug("Using default grid alpha: 0.3")

                            plot_item.showGrid(x=True, y=True, alpha=alpha)
                        else:
                            plot_item.showGrid(x=False, y=False)
                    else:
                        plot_item.showGrid(x=False, y=False)
                except Exception:
                    # Fallback to enabled grid
                    plot_item.showGrid(x=True, y=True, alpha=0.3)

                # Get Z_ORDER with fallback
                try:
                    from Synaptipy.shared.constants import Z_ORDER

                    grid_z_value = Z_ORDER["grid"]
                except (ImportError, KeyError):
                    grid_z_value = -1000

                # Configure each axis safely
                for axis_name in ["bottom", "left"]:
                    try:
                        axis = plot_item.getAxis(axis_name)
                        if not axis or not hasattr(axis, "grid") or axis.grid is None:
                            continue

                        # Check if grid item is ready for configuration
                        grid_item = axis.grid
                        if not SynaptipyPlotFactory._is_graphics_item_ready(grid_item):
                            continue

                        # Configure grid properties
                        if hasattr(axis, "setGrid"):
                            axis.setGrid(255)  # Full opacity

                        if hasattr(grid_item, "setZValue"):
                            grid_item.setZValue(grid_z_value)

                        if hasattr(grid_item, "setPen"):
                            from Synaptipy.shared.styling import get_grid_pen

                            grid_pen = get_grid_pen()
                            if grid_pen:
                                grid_item.setPen(grid_pen)
                                log.debug(f"Applied grid pen to axis {axis_name}")
                            else:
                                log.debug(f"Grid pen is None for axis {axis_name}")

                    except Exception as e:
                        log.debug(f"Grid config failed for axis {axis_name}: {e}")
                        continue

                log.debug("Grid configuration completed successfully")

            except Exception as e:
                log.debug(f"Grid configuration attempt {attempt + 1} failed: {e}")
                if attempt < max_retries:
                    QtCore.QTimer.singleShot(retry_delay, lambda: attempt_grid_config(attempt + 1))

        # Start the configuration attempt
        attempt_grid_config()

    @staticmethod
    def _is_graphics_item_ready(item: Any) -> bool:
        """
        Check if a graphics item is ready for configuration.
        Prevents Windows null pointer errors.
        """
        try:
            if not item:
                return False

            # Check if item has required methods
            required_attrs = ["scene", "parentItem"]
            for attr in required_attrs:
                if not hasattr(item, attr):
                    return False

            # Check if item is properly connected to graphics scene
            scene = item.scene()
            parent = item.parentItem()

            if scene is None or parent is None:
                return False

            # Additional Windows safety check
            if hasattr(item, "isVisible") and not item.isVisible():
                return False

            return True

        except Exception:
            return False

    @staticmethod
    def configure_existing_plot(plot_widget: pg.PlotWidget) -> None:
        """
        Configure an existing plot widget with safe grid setup.
        Use this for plots that were created elsewhere.
        """
        try:
            # Set background
            plot_widget.setBackground("white")

            # Configure grid with delay
            QtCore.QTimer.singleShot(50, lambda: SynaptipyPlotFactory._configure_grid_safe(plot_widget))

        except Exception as e:
            log.debug(f"Failed to configure existing plot: {e}")


# Convenience functions for backward compatibility
def create_analysis_plot(parent: Optional[QtWidgets.QWidget] = None) -> pg.PlotWidget:
    """Create a plot widget for analysis tabs."""
    return SynaptipyPlotFactory.create_plot_widget(parent=parent, enable_grid=True, mouse_mode="rect")


def create_explorer_plot(parent: Optional[QtWidgets.QWidget] = None) -> pg.PlotWidget:
    """Create a plot widget for explorer tab."""
    return SynaptipyPlotFactory.create_plot_widget(parent=parent, enable_grid=True, mouse_mode="rect")


def configure_plot_safely(plot_widget: pg.PlotWidget) -> None:
    """Safely configure an existing plot widget."""
    SynaptipyPlotFactory.configure_existing_plot(plot_widget)
