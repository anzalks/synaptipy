# Synaptipy Styling Guide

This document explains the styling system used in Synaptipy, how it's organized, and how to ensure consistent UI styling in your code.

## Overview

Synaptipy uses Qt's native theming system (`src/Synaptipy/shared/styling.py`) for consistent application appearance. The styling system is designed to:

1. Ensure visual consistency throughout the application using Qt's built-in palette system
2. Support seamless light/dark theme switching
3. Provide convenient helpers for PyQtGraph visualization styling
4. Minimize custom styling in favor of native Qt appearance

## Key Components

### Theme Mode Management

The styling module provides simple theme management functions:

- `get_current_theme_mode()`: Returns current theme ('light' or 'dark')
- `set_theme_mode(mode)`: Set theme to 'light' or 'dark'
- `toggle_theme_mode()`: Switch between light and dark themes

### Qt Native Theming

The system uses Qt's native palette and style system:

- **Dark Theme**: Uses "Fusion" style with custom dark palette
- **Light Theme**: Uses system native style with default palette

### PyQtGraph Plot Styling

Specialized functions for plot appearance:

- `configure_plot_widget(plot_widget)`: Apply theme-appropriate colors to plots
- `get_trial_pen()`, `get_average_pen()`: Get theme-appropriate pens for data
- `get_baseline_pen()`, `get_response_pen()`: Get pens for analysis indicators
- `get_grid_pen()`: Get theme-appropriate grid line styling

### Simple Widget Styling

Minimal styling helpers that work with Qt's native theming:

- `style_button(button, style='primary')`: Apply simple button styling
- `style_label(label, style='normal')`: Apply label styling (heading, subheading)
- `style_info_label(label)`: Style informational labels
- `style_error_message(widget)`: Style error messages

### Theme Application

- `apply_stylesheet(app)`: Apply the current theme to the entire application

## How to Use

### For General UI Elements

Use the minimal styling helpers when needed:

```python
from PySide6 import QtWidgets
from Synaptipy.shared.styling import style_button, style_label

# Create widgets
button = QtWidgets.QPushButton("Save")
info_label = QtWidgets.QLabel("Select a file to analyze")

# Apply minimal styling (mostly relies on Qt's native theming)
style_button(button, 'primary')  # Makes button slightly more prominent
style_label(info_label, 'heading')  # Makes label bold and larger
```

### For PyQtGraph Elements

Use the PyQtGraph helper functions:

```python
import pyqtgraph as pg
from Synaptipy.shared.styling import configure_plot_widget, get_trial_pen, get_average_pen

# Create plot widget with theme-appropriate styling
plot_widget = pg.PlotWidget()
configure_plot_widget(plot_widget)

# Plot data with theme-appropriate pens
plot_widget.plot(time, trial_data, pen=get_trial_pen())
plot_widget.plot(time, avg_data, pen=get_average_pen())
```

### For Theme Switching

Theme switching is handled automatically by the main window, but can be controlled programmatically:

```python
from Synaptipy.shared.styling import set_theme_mode, toggle_theme_mode, apply_stylesheet
from PySide6 import QtWidgets

# Switch to dark theme
set_theme_mode('dark')
app = QtWidgets.QApplication.instance()
apply_stylesheet(app)

# Or toggle theme
new_mode = toggle_theme_mode()
apply_stylesheet(app)
```

## Best Practices

1. **Rely on Qt's native theming** - Avoid custom stylesheets when possible
2. **Use the theme helper functions** for plot styling and minimal widget customization
3. **Let Qt handle most styling** - The palette system automatically handles colors for most widgets
4. **Test both themes** - Always verify your UI works well in both light and dark modes
5. **Keep styling minimal** - Add custom styling only when necessary for functionality

## Architecture Benefits

The new Qt native theming approach provides:

1. **Better OS Integration**: Matches system appearance expectations
2. **Reduced Complexity**: Fewer custom stylesheets to maintain
3. **Improved Performance**: Qt's native rendering is optimized
4. **Better Accessibility**: Native theming supports system accessibility features
5. **Future Compatibility**: Less dependent on external styling libraries

## Migration from Previous System

The previous complex custom styling system has been replaced with this simpler approach:

- **Removed**: Complex custom stylesheets, qdarkstyle dependency, custom color palettes
- **Replaced**: Qt native palettes with minimal custom styling for specific needs
- **Maintained**: Plot styling helpers and basic widget styling functions 