__author__           = "Anzal KS"
__copyright__        = "Copyright 2024-, Anzal KS"
__maintainer__       = "Anzal KS"
__email__            = "anzalks@ncbs.res.in"


import glob
import os
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg,NavigationToolbar2Tk
from matplotlib.backend_bases import MouseButton
import PySimpleGUI as sg
from matplotlib import pyplot as plt
import FileLoader
import pprint as pprint
import matplotlib
from matplotlib.widgets import RectangleSelector


matplotlib.use("TkAgg")


# Function to draw a Matplotlib figure onto a PySimpleGUI canvas
def draw_figure(canvas, figure):
    """Embeds the figure in the given canvas."""
    for widget in canvas.winfo_children():
        widget.destroy()

    figure_canvas_agg = FigureCanvasTkAgg(figure, canvas)
    figure_canvas_agg.draw()
    figure_canvas_agg.get_tk_widget().pack(side="top", fill="both", expand=1)
    return figure_canvas_agg


# Function to add the Matplotlib Navigation Toolbar
def add_toolbar(canvas, figure_canvas_agg):
    """Adds the Matplotlib navigation toolbar to the canvas."""
    for widget in canvas.winfo_children():
        widget.destroy()
    toolbar = NavigationToolbar2Tk(figure_canvas_agg, canvas)
    toolbar.update()
    toolbar.pack(side="top", fill="x", expand=False)
    return toolbar


# Function to create the PySimpleGUI window layout
def MainWindow():
    sg.theme("SandyBeach")

    layout = [
        [
            sg.Frame(
                "Explore Traces",
                [
                    [sg.Button("Open File")],
                    [sg.Checkbox("Plot average", default=False, key="-PLOT_AV-")],
                    [sg.Checkbox("Plot all trials", default=False, key="-PLOT_ALL-")],
                ],
                relief="ridge",
                border_width=5,
                size=(400, 90),
                expand_x=True,
                expand_y=False,
            ),
            sg.Frame(
                "File Details",
                [[sg.Text("", size=(60, 4), key="-FILE_PROP-", relief="groove")]],
                relief="ridge",
                border_width=3,
                expand_x=True,
                expand_y=False,
            ),
        ],
        [
            sg.Frame(
                "Raw Traces",
                [
                    [sg.Canvas(key="-CANVAS-", expand_x=True, expand_y=True)],
                    [sg.Canvas(key="-TOOLBAR-", expand_x=True, expand_y=False)],
                ],
                relief="groove",
                border_width=3,
                expand_x=True,
                expand_y=True,
            )
        ],
        [
            sg.Button("Previous", key="-PREV-", visible=False),
            sg.Button("Next", key="-NEXT-", visible=False),
            sg.Button("Reset"),
        ],
    ]

    return sg.Window("Data Analysis", layout, finalize=True, resizable=True)


# Main function to handle the GUI and Matplotlib integration
def Main():
    window = MainWindow()

    # Access the PySimpleGUI canvases
    canvas_elem = window["-CANVAS-"]
    toolbar_elem = window["-TOOLBAR-"]

    canvas = canvas_elem.TKCanvas
    toolbar_canvas = toolbar_elem.TKCanvas

    figure_canvas_agg = None
    toolbar = None

    fig, axes = None, []
    current_axis_index = 0
    initial_lims = {}

    def show_axis(index):
        """Show only the axis at the given index."""
        ax = axes[index]
        new_fig, new_ax = plt.subplots(figsize=(6, 4))

        for line in ax.get_lines():
            new_ax.plot(
                line.get_xdata(), line.get_ydata(),
                label=line.get_label(), color=line.get_color(),
                linestyle=line.get_linestyle(), linewidth=line.get_linewidth()
            )

        new_ax.set_xlim(ax.get_xlim())
        new_ax.set_ylim(ax.get_ylim())
        new_ax.set_xlabel(ax.get_xlabel())
        new_ax.set_ylabel(ax.get_ylabel())
        new_ax.set_title(ax.get_title())
        if ax.get_legend() is not None:
            new_ax.legend(loc="best")

        draw_figure(canvas, new_fig)

    while True:
        event, values = window.read()
        if event == sg.WIN_CLOSED:
            break

        if event == "Open File":
            # Load file and generate plot
            plot_all_traces = values["-PLOT_ALL-"]
            reader = FileLoader.load_files()
            fig, file_prop = FileLoader.show_data(reader, trial_average=values["-PLOT_AV-"])

            axes = fig.get_axes()
            for ax in axes:
                initial_lims[ax] = {"x": ax.get_xlim(), "y": ax.get_ylim()}

            # Update file details
            formatted_text = pprint.pformat(file_prop, indent=4)
            window["-FILE_PROP-"].update(formatted_text)

            # Embed figure and toolbar
            figure_canvas_agg = draw_figure(canvas, fig)
            if toolbar:
                toolbar.destroy()
            toolbar = add_toolbar(toolbar_canvas, figure_canvas_agg)

            # Show navigation buttons only if needed
            window["-NEXT-"].update(visible=not plot_all_traces)
            window["-PREV-"].update(visible=not plot_all_traces)

            if not plot_all_traces :
                trial_no = 0
                fig, file_prop = FileLoader.show_data(reader,
                                                      trial_no= trial_no,
                                                      trial_average=values["-PLOT_AV-"])
                show_axis(current_axis_index)
                axes = fig.get_axes()

        if event == "Reset" and fig:
            for ax in axes:
                ax.set_xlim(initial_lims[ax]["x"])
                ax.set_ylim(initial_lims[ax]["y"])
            fig.canvas.draw()

        if event == "-NEXT-" and not values["-PLOT_ALL-"]:
            trial_no = (trial_no + 1) % len(axes)
            show_axis(trial_no)

        if event == "-PREV-" and not values["-PLOT_ALL-"]:
            trial_no = (trial_no - 1) % len(axes)
            show_axis(trial_no)

    window.close()


if __name__ == "__main__":
    Main()


##integrated the matplotlib navigation inbuilt
#matplotlib.use("TkAgg")
#
## Function to draw a Matplotlib figure onto a PySimpleGUI canvas
#def draw_figure(canvas, figure):
#    """Embeds the figure in the given canvas."""
#    for widget in canvas.winfo_children():
#        widget.destroy()
#
#    figure_canvas_agg = FigureCanvasTkAgg(figure, canvas)
#    figure_canvas_agg.draw()
#    figure_canvas_agg.get_tk_widget().pack(side="top", fill="both", expand=1)
#    return figure_canvas_agg
#
## Function to add the Matplotlib Navigation Toolbar
#def add_toolbar(canvas, figure_canvas_agg):
#    """Adds the Matplotlib navigation toolbar to the canvas."""
#    for widget in canvas.winfo_children():
#        widget.destroy()
#    
#    toolbar = NavigationToolbar2Tk(figure_canvas_agg, canvas)
#    toolbar.update()
#    toolbar.pack(side="top", fill="x", expand=False)
#    return toolbar
#
## Function to create the PySimpleGUI window layout
#def MainWindow():
#    sg.theme("SandyBeach")
#
#    layout = [
#        [
#            sg.Frame(
#                "Explore Traces",
#                [
#                    [sg.Button("Open File")],
#                    [sg.Checkbox("Plot average", default=False, key="-PLOT_AV-")],
#                    [sg.Checkbox("Plot all at once", default=False, key="-PLOT_ALL-")],
#                ],
#                relief="ridge",
#                border_width=5,
#                size=(400, 90),
#                expand_x=True,
#                expand_y=False,
#            ),
#            sg.Frame(
#                "File Details",
#                [[sg.Text("", size=(60, 4), key="-FILE_PROP-", relief="groove")]],
#                relief="ridge",
#                border_width=3,
#                expand_x=True,
#                expand_y=False,
#            ),
#        ],
#        [
#            sg.Frame(
#                "Raw Traces",
#                [
#                    [sg.Canvas(key="-CANVAS-", expand_x=True, expand_y=True)],
#                    [sg.Canvas(key="-TOOLBAR-", expand_x=True, expand_y=False)],
#                ],
#                relief="groove",
#                border_width=3,
#                expand_x=True,
#                expand_y=True,
#            )
#        ],
#        [sg.Button("Reset")
#        ],
#    ]
#
#    return sg.Window("Data Analysis", layout, finalize=True, resizable=True)
#
## Main function to handle the GUI and Matplotlib integration
#def Main():
#    window = MainWindow()
#
#    # Access the PySimpleGUI canvases
#    canvas_elem = window["-CANVAS-"]
#    toolbar_elem = window["-TOOLBAR-"]
#
#    canvas = canvas_elem.TKCanvas
#    toolbar_canvas = toolbar_elem.TKCanvas
#
#    figure_canvas_agg = None
#    toolbar = None
#
#    # Placeholder for figure
#    fig = None
#
#    while True:
#        event, values = window.read()
#
#
#        if event == "Open File":
#            # Load file and generate plot
#            reader = FileLoader.load_files()
#            fig, file_prop = FileLoader.show_data(reader, trial_average=values["-PLOT_AV-"])
#
#            # Update file details
#            formatted_text = pprint.pformat(file_prop, indent=4)
#            window["-FILE_PROP-"].update(formatted_text)
#
#            # Embed figure
#            figure_canvas_agg = draw_figure(canvas, fig)
#
#            # Add navigation toolbar
#            if toolbar:
#                toolbar.destroy()  # Destroy old toolbar if it exists
#            toolbar = add_toolbar(toolbar_canvas, figure_canvas_agg)
#
#        if event == "Reset" and fig:
#            for ax in fig.axes:
#                ax.relim()
#                ax.autoscale()
#            fig.canvas.draw()
#
#    window.close()
#
#
#if __name__ == "__main__":
#    Main()



#matplotlib.use('TkAgg')
#
## Function to draw a Matplotlib figure onto a PySimpleGUI canvas
#def draw_figure(canvas, figure):
#    # Clear previous figure if it exists
#    for widget in canvas.winfo_children():
#        widget.destroy()
#
#    figure_canvas_agg = FigureCanvasTkAgg(figure, canvas)
#    figure_canvas_agg.draw()
#    figure_canvas_agg.get_tk_widget().pack(side="top", fill="both", expand=1)
#    return figure_canvas_agg
#
## Function to create the main window layout
#def MainWindow():
#    sg.theme('SandyBeach')
#
#    layout = [
#        [
#            sg.Frame(
#                'Explore Traces',
#                [
#                    [sg.Button('Open File')],
#                    [sg.Checkbox('Plot average', 
#                                 default=False, 
#                                 key='-PLOT_AV-')],
#                    [sg.Checkbox('Plot all at once',
#                                 default=False,
#                                 key='-PLOT_ALL-')],
#                ],
#                relief="ridge", border_width=5, size=(400, 90),
#                expand_x=True, expand_y=False
#            ),
#            sg.Frame(
#                'File Details',
#                [
#                    [sg.Text('', size=(60, 4), key='-FILE_PROP-', relief='groove')]
#                ],
#                relief="ridge", border_width=3, expand_x=True, expand_y=False
#            )
#        ],
#        [
#            sg.Column(
#                [[sg.Slider(range=(0, 100), default_value=100, resolution=1, orientation="v", size=(10, 20),
#                            key="-YZOOM-", enable_events=True, expand_y=True)]],
#                expand_y=True, expand_x=False
#            ),
#            sg.Frame(
#                'Raw Traces',
#                [
#                    [sg.Canvas(key="-CANVAS-", expand_x=True, expand_y=True)],
#                    [sg.Canvas(key="-TOOLBAR-")]
#                ],
#                relief="groove", border_width=3, expand_x=True, expand_y=True
#            )
#        ],
#        [
#            sg.Text("X Axis"),
#            sg.Slider(range=(0, 100), default_value=100, resolution=1, orientation="h", size=(60, 15),
#                      key="-XZOOM-", enable_events=True, expand_x=True)
#        ],
#        [
#            sg.Button("Previous", key="-PREV-", visible=False),
#            sg.Button("Next", key="-NEXT-", visible=False),
#            sg.Button("Reset")
#        ]
#    ]
#
#    return sg.Window('Data Analysis', layout, location=(0, 0), finalize=True, resizable=True)
#
#def Main():
#    window1 = MainWindow()
#
#    # Access the PySimpleGUI canvas
#    canvas_elem = window1["-CANVAS-"]
#    toolbar_elem = window1["-TOOLBAR-"]
#    canvas = canvas_elem.TKCanvas
#    toolbar_canvas = toolbar_elem.Widget
#    figure_canvas_agg = None  # Initialize placeholder for the drawn figure
#
#    # Placeholder for the figure and axis limits
#    fig, axes = None, []  # Store all axes
#    initial_lims = {}  # Store initial xlim and ylim for each axis
#    current_axis_index = 0  # Track the currently displayed axis
#
#    def calculate_zoom_factor(slider_value):
#        """Calculate exponential zoom factor."""
#        return 10 ** ((100 - slider_value) / 100)
#
#    def on_scroll(event):
#        """Handles scrolling to pan."""
#        if fig is not None:
#            if values['-PLOT_ALL-']:
#                for ax in axes:
#                    xlim = ax.get_xlim()
#                    ylim = ax.get_ylim()
#
#                    x_range = xlim[1] - xlim[0]
#                    y_range = ylim[1] - ylim[0]
#                    scroll_step_x = 0.1 * x_range
#                    scroll_step_y = 0.05 * y_range
#
#                    if event.key is None:  # Default scrolling
#                        if event.button == 'up':
#                            ax.set_xlim(xlim[0] - scroll_step_x, xlim[1] - scroll_step_x)
#                        elif event.button == 'down':
#                            ax.set_xlim(xlim[0] + scroll_step_x, xlim[1] + scroll_step_x)
#
#                    elif event.key == 'control':
#                        if event.button == 'up':
#                            ax.set_ylim(ylim[0] - scroll_step_y, ylim[1] - scroll_step_y)
#                        elif event.button == 'down':
#                            ax.set_ylim(ylim[0] + scroll_step_y, ylim[1] + scroll_step_y)
#
#            else:
#                ax = axes[current_axis_index]
#                xlim = ax.get_xlim()
#                ylim = ax.get_ylim()
#
#                x_range = xlim[1] - xlim[0]
#                y_range = ylim[1] - ylim[0]
#                scroll_step_x = 0.1 * x_range
#                scroll_step_y = 0.05 * y_range
#
#                if event.key is None:  # Default scrolling
#                    if event.button == 'up':
#                        ax.set_xlim(xlim[0] - scroll_step_x, xlim[1] - scroll_step_x)
#                    elif event.button == 'down':
#                        ax.set_xlim(xlim[0] + scroll_step_x, xlim[1] + scroll_step_x)
#
#                elif event.key == 'control':
#                    if event.button == 'up':
#                        ax.set_ylim(ylim[0] - scroll_step_y, ylim[1] - scroll_step_y)
#                    elif event.button == 'down':
#                        ax.set_ylim(ylim[0] + scroll_step_y, ylim[1] + scroll_step_y)
#
#            fig.canvas.draw()
#
#
#    def update_zoom_sliders(values):
#        """Updates the axis limits based on zoom slider values."""
#        if fig is not None:
#            if values['-PLOT_ALL-']:
#                for ax in axes:
#                    zoom_factor_x = calculate_zoom_factor(values["-XZOOM-"])
#                    zoom_factor_y = calculate_zoom_factor(values["-YZOOM-"])
#
#                    x_center = (initial_lims[ax]["x"][0] + initial_lims[ax]["x"][1]) / 2
#                    y_center = (initial_lims[ax]["y"][0] + initial_lims[ax]["y"][1]) / 2
#
#                    x_range = (initial_lims[ax]["x"][1] - initial_lims[ax]["x"][0]) / zoom_factor_x
#                    y_range = (initial_lims[ax]["y"][1] - initial_lims[ax]["y"][0]) / zoom_factor_y
#
#                    ax.set_xlim(x_center - x_range / 2, x_center + x_range / 2)
#                    ax.set_ylim(y_center - y_range / 2, y_center + y_range / 2)
#            else:
#                ax = axes[current_axis_index]
#                zoom_factor_x = calculate_zoom_factor(values["-XZOOM-"])
#                zoom_factor_y = calculate_zoom_factor(values["-YZOOM-"])
#
#                x_center = (initial_lims[ax]["x"][0] + initial_lims[ax]["x"][1]) / 2
#                y_center = (initial_lims[ax]["y"][0] + initial_lims[ax]["y"][1]) / 2
#
#                x_range = (initial_lims[ax]["x"][1] - initial_lims[ax]["x"][0]) / zoom_factor_x
#                y_range = (initial_lims[ax]["y"][1] - initial_lims[ax]["y"][0]) / zoom_factor_y
#
#                ax.set_xlim(x_center - x_range / 2, x_center + x_range / 2)
#                ax.set_ylim(y_center - y_range / 2, y_center + y_range / 2)
#
#            fig.canvas.draw()
#
#
#    def show_axis(index):
#        """Show only the axis at the given index as a standalone figure."""
#        ax = axes[index]
#
#        # Create a new figure for the single axis
#        new_fig, new_ax = matplotlib.pyplot.subplots(figsize=(6, 4))
#        
#        # Copy data and properties from the current axis to the new one
#        for line in ax.get_lines():
#            new_ax.plot(
#                line.get_xdata(),
#                line.get_ydata(),
#                label=line.get_label(),
#                color=line.get_color(),  # Retain the original line color
#                linestyle=line.get_linestyle(),  # Retain original line style
#                linewidth=line.get_linewidth()  # Retain original line width
#            )
#        
#        # Copy axis limits and labels
#        new_ax.set_xlim(ax.get_xlim())
#        new_ax.set_ylim(ax.get_ylim())
#        new_ax.set_xlabel(ax.get_xlabel())
#        new_ax.set_ylabel(ax.get_ylabel())
#        new_ax.set_title(ax.get_title())
#        if ax.get_legend() is not None:
#            new_ax.legend(loc="best")  # Include the legend if available
#        
#        # Connect scroll event to the new figure
#        new_fig.canvas.mpl_connect("scroll_event", lambda e: on_scroll(e))
#        # Clear and redraw the new figure on the canvas
#        draw_figure(canvas, new_fig)
#
#    while True:
#        event, values = window1.read()
#
#        if event in (sg.WINDOW_CLOSED, "Exit"):
#            break
#
#        if event == "Open File":
#            plot_all_traces = values['-PLOT_ALL-']
#            reader = FileLoader.load_files()
#            fig, file_prop = FileLoader.show_data(reader, 
#                                                  trial_average=values['-PLOT_AV-'])
#            axes = fig.get_axes()  # Get all axes
#            for ax in axes:
#                initial_lims[ax] = {
#                    "x": ax.get_xlim(),
#                    "y": ax.get_ylim()
#                }
#
#            fig.canvas.mpl_connect("scroll_event", lambda e: on_scroll(e))
#            formatted_text = pprint.pformat(file_prop, indent=4)
#            window1['-FILE_PROP-'].update(formatted_text)
#
#            figure_canvas_agg = draw_figure(canvas, fig)
#
#            # Show navigation buttons only when "Plot all at once" is unchecked
#            window1["-NEXT-"].update(visible=not plot_all_traces)
#            window1["-PREV-"].update(visible=not plot_all_traces)
#
#            if not plot_all_traces and len(axes) > 1:
#                current_axis_index = 0  # Reset to the first axis
#                show_axis(current_axis_index)
#
#        if event in ["-XZOOM-", "-YZOOM-"]:
#            update_zoom_sliders(values)
#
#        if event == "Reset" and fig is not None:
#            for ax in axes:
#                ax.set_xlim(initial_lims[ax]["x"])
#                ax.set_ylim(initial_lims[ax]["y"])
#            fig.canvas.draw()
#            
#            
#
#            window1['-XZOOM-'].update(100)
#            window1['-YZOOM-'].update(100)
#        
#        if event == "-NEXT-" and not values['-PLOT_ALL-']:
#            current_axis_index = (current_axis_index + 1) % len(axes)
#            show_axis(current_axis_index)
#
#        if event == "-PREV-" and not values['-PLOT_ALL-']:
#            current_axis_index = (current_axis_index - 1) % len(axes)
#            show_axis(current_axis_index)
#        #toolbar = NavigationToolbar2Tk(figure_canvas_agg, toolbar_canvas)
#        #toolbar.update()
#    window1.close()
#
#if __name__ == '__main__':
#    Main()
