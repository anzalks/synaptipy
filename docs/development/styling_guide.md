# Synaptipy Styling Guide

This document explains the styling system used in Synaptipy, how it's organized, and how to ensure consistent UI styling in your code.

## Overview

Synaptipy uses a centralized styling module (`src/Synaptipy/shared/styling.py`) that provides consistent colors, themes, and styling across all UI components. The styling system is designed to:

1. Ensure visual consistency throughout the application
2. Make it easy to apply standard styling to UI elements
3. Support theming and customization in the future
4. Provide convenient helpers for PyQtGraph visualization styling

## Key Components

### Theme and Color Constants

The styling module defines several key constants:

- `THEME`: Core application colors (primary, secondary, accent, etc.)
- `PALETTE`: Color palettes by hue with 10 shades each
- `PLOT_COLORS`: Standard colors for data plots
- `ALPHA`: Transparency values for different UI elements

Example usage:
```python
from Synaptipy.shared.styling import THEME

# Use a theme color directly
button.setStyleSheet(f"background-color: {THEME['primary']};")
```

### Element Style Definitions

Predefined styles for common UI elements:

- `BUTTON_STYLES`: Different button styles (primary, action, toolbar)
- `TEXT_STYLES`: Text styling for different contexts (heading, info, error)

### Helper Functions

The module provides helper functions for consistently styling widgets:

#### General Widget Styling

- `style_button(button, style='primary')`: Apply standard button styling
- `style_label(label, style='subheading')`: Apply standard label styling
- `style_result_display(widget)`: Style widgets that display results
- `style_info_label(label)`: Style informational labels
- `style_error_message(widget)`: Style error messages

#### PyQtGraph Styling

- `get_trial_pen()`, `get_average_pen()`: Get pens for different trace types
- `get_baseline_pen()`, `get_response_pen()`: Get pens for measurement indicators
- `get_plot_pen(index)`: Get a pen from the standard plot color set
- `configure_plot_widget(plot_widget)`: Apply standard styling to a plot widget

#### Theme Application

- `apply_stylesheet(app)`: Apply styling to the entire application

## How to Use

### For General UI Elements

Always use the helper functions instead of hardcoding styles:

```python
from PySide6 import QtWidgets
from Synaptipy.shared.styling import style_button, style_label

# Create widgets
button = QtWidgets.QPushButton("Save")
info_label = QtWidgets.QLabel("Select a file to analyze")

# Apply styling
style_button(button, 'action')  # Makes an accent-colored action button
style_label(info_label, 'info')  # Styles as an info label
```

### For PyQtGraph Elements

Use the PyQtGraph helper functions:

```python
import pyqtgraph as pg
from Synaptipy.shared.styling import configure_plot_widget, get_trial_pen, get_average_pen

# Create plot widget with standard styling
plot_widget = pg.PlotWidget()
configure_plot_widget(plot_widget)

# Plot data with standard pens
plot_widget.plot(time, trial_data, pen=get_trial_pen())
plot_widget.plot(time, avg_data, pen=get_average_pen())
```

### For Applying the Global Theme

The theme is applied automatically in the application entry point, but can be manually applied if needed:

```python
from PySide6 import QtWidgets
from Synaptipy.shared.styling import apply_stylesheet

app = QtWidgets.QApplication([])
apply_stylesheet(app)
```

## Best Practices

1. **Never use inline styles** or hardcoded colors in UI code
2. **Always use the styling module** functions and constants
3. **Keep styling separate from logic** when building UI components
4. **When adding new UI elements**, follow existing styling patterns
5. **If new styling needs are identified**, extend the styling module rather than implementing one-off styles

## Customizing and Extending

To extend the styling system:

1. Add new constants or functions to `styling.py`
2. Expose them in `shared/__init__.py` for easy imports
3. Add appropriate tests in `tests/shared/test_styling.py`
4. Document their purpose and usage

## Dark Mode Support

The styling module is designed with dark mode in mind by default. It:

1. Uses `qdarkstyle` if available
2. Falls back to a custom dark style if not available

## Testing Styling

When writing tests for UI components, use the provided fixtures in `tests/shared/conftest.py`. 