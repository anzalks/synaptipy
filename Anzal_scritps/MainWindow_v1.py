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
import SweepAnalyses as san
import pprint as pprint
import matplotlib
from matplotlib.widgets import RectangleSelector
from pynput import keyboard
from threading import Thread



try:
    matplotlib.use("TkAgg")
except ImportError:
    raise MissingDependencyError("matplotlib has no access to TkAgg, using Agg instead")
try:
    matplotlib.use("Agg")
except ImportError:
    MissingDependencyError("matplotlib has no access to Agg or TkAgg",
                           "please asign a graphic module to plot")


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
    theme_text = sg.theme_text_color()

    layout = [
        [
            sg.Frame(
                "Explore Traces",
                [
                    [sg.Button("Open a File", key="-OPEN_FILE-")],
                    [sg.Button("Open a Folder", key="-OPEN_FOLDER-")],
                    [sg.Checkbox("Plot average", default=False, key="-PLOT_AV-")],
                    [sg.Checkbox("Plot all trials", default=False, key="-PLOT_ALL-")],
                ],
                relief="ridge",
                border_width=5,
                size=(400, 150),
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
            sg.Frame(
                "Channel details",
                [[sg.Text("", size=(60, 4), key="-CHAN_PROP-", relief="groove")]],
                relief="ridge",
                border_width=3,
                expand_x=True,
                expand_y=False,
            ),
        ],
        [
            sg.Frame(
                "Raw Sweeps",
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
            sg.Button("Reset", key="Reset"),  # Reset button first
            #sg.Input(focus=False),
            sg.Column(
                [[
                    sg.Button("Previous", key="-PREV-", visible=False),
                    sg.Button("Next", key="-NEXT-", visible=False)
                ]],
                justification="right", expand_x=True
            )
        ],

        [
            sg.Frame(
                "Analysed Results",
                [
                    [sg.Text("", size=(60, 4), key="-AN_RESULTS-",
                              relief="groove")],
                    [sg.Button("Run Sweep\nAnalysis",
                               key="-S_ANALYSIS-",visible=False)],
                ],
                relief="ridge",
                border_width=5,
                size=(400, 150),
                expand_x=True,
                expand_y=False,
            ),

        ]





    ]

    return sg.Window("Synaptipy", layout,finalize=True, resizable=True)


# Main function to handle the GUI and Matplotlib integration
def Main():
    window = MainWindow()
    # Flag to stop the listener when the window is closed
    stop_listener = False
    # Function to trigger PySimpleGUI events
    def trigger_event(event_key):
        if event_key == "Right":
            window.write_event_value("-NEXT-", None)
        elif event_key == "Left":
            window.write_event_value("-PREV-", None)
    # Listener function
    def on_press(key):
        try:
            if key == keyboard.Key.right:
                trigger_event("Right")
            elif key == keyboard.Key.left:
                trigger_event("Left")
        except Exception as e:
            print(f"Error: {e}")
    # Function to run the listener in a separate thread
    def start_listener():
        global stop_listener
        with keyboard.Listener(on_press=on_press) as listener:
            while not stop_listener:
                pass
            listener.stop()
    ##to activate keyboard read, mightnot work in all OS 
    #listener_thread = Thread(target=start_listener, daemon=True)
    #listener_thread.start()
    
    # Access the PySimpleGUI canvases
    canvas_elem = window["-CANVAS-"]
    toolbar_elem = window["-TOOLBAR-"]

    canvas = canvas_elem.TKCanvas
    toolbar_canvas = toolbar_elem.TKCanvas

    figure_canvas_agg = None
    toolbar = None
    fig = None
    trial_no = 0  # Default trial number

    def update_trial_figure(trial_no, reader, plot_all_traces,
                            trial_average,ChanToRead="Im0"):
        """Updates the figure based on the trial number."""
        nonlocal fig, figure_canvas_agg, toolbar
        # Clear previous canvas
        if figure_canvas_agg:
            figure_canvas_agg.get_tk_widget().pack_forget()

        # Reload the figure for the specific trial
        fig = FileLoader.show_data(reader,
                                   trial_no,
                                   plot_all_traces,
                                   trial_average)
        sweep, time, sampling_rate = san.extract_sweep(reader,trial_no,
                                                       ChanToRead)
        base_line = san.baseline_measurement(sweep)#,debug=True)
        offset_baseline = san.offset_baseline(sweep,base_line,debug=True) 
        #peak_stats = san.collect_peak_stats(sweep,time,sampling_rate,debug=True)
        peak_stats = 'None'
        analysed_result = f"""sweep baseline: {base_line},
                          baseline (leak substracted): {offset_baseline}
                          peak stats: {peak_stats}"""
        figure_canvas_agg = draw_figure(canvas, fig)
        # Refresh toolbar
        if toolbar:
            toolbar.destroy()
        toolbar = add_toolbar(toolbar_canvas, figure_canvas_agg)
        return analysed_result

    while True:
        event, values = window.read()
        if event == sg.WIN_CLOSED:
            stop_listener = True
            break

        if event == "-OPEN_FILE-":
            # Load file and generate plot
            plot_all_traces = values["-PLOT_ALL-"]
            reader, file_prop = FileLoader.load_files()

            # Initial trial
            trial_no = 0
            max_trials = file_prop["no of trials"]
            chan_name,num_chan = FileLoader.get_channel_name(reader)
            chan_name_ = chan_name[0]
            print(f"chan_name_:{chan_name_}.....")
            update_trial_figure(trial_no, reader, 
                                plot_all_traces=plot_all_traces,
                                trial_average=values["-PLOT_AV-"],
                                ChanToRead=chan_name_)

            # Update file details
            file_details = pprint.pformat(file_prop, indent=4)
            window["-FILE_PROP-"].update(file_details)
            chan_details = pprint.pformat(f"channel names: {chan_name},"
                                          f"number of channels: {num_chan}", 
                                          indent=4)
            window["-CHAN_PROP-"].update(chan_details)


            # Show navigation buttons only if needed
            window["-PREV-"].update(visible=not plot_all_traces)
            window["-NEXT-"].update(visible=not plot_all_traces)
            window["-S_ANALYSIS-"].update(visible=True)
            window["-AN_RESULTS-"].update(visible=True)
        
        if event == "Reset" and fig:
            trial_no = 0
            update_trial_figure(trial_no, reader, 
                                plot_all_traces=plot_all_traces,
                                trial_average=values["-PLOT_AV-"],
                                ChanToRead=chan_name_)

        if event in ("-NEXT-","Right"):
            if trial_no < max_trials - 1:
                trial_no += 1
                update_trial_figure(trial_no, reader, 
                                    plot_all_traces=plot_all_traces,
                                    trial_average=values["-PLOT_AV-"],
                                    ChanToRead=chan_name_)
            else:
                sg.popup("You are already at the last trial!",
                         title="End of Trials")

        if event in("-PREV-","Left"):
            if trial_no > 0:
                trial_no -= 1
                update_trial_figure(trial_no, reader, 
                                    plot_all_traces=plot_all_traces,
                                    trial_average=values["-PLOT_AV-"],
                                    ChanToRead=chan_name_)



            else:
                sg.popup("You are already at the first trial!", 
                         title="Start of Trials")
        if event == "-S_ANALYSIS-":
            analysed_result = update_trial_figure(trial_no, reader, 
                                                  plot_all_traces=plot_all_traces,
                                                  trial_average=values["-PLOT_AV-"],
                                                  ChanToRead=chan_name_)
            analysed_result = pprint.pformat(analysed_result, indent=4)
            window["-AN_RESULTS-"].update(analysed_result)
            #sg.popup(f"Result: {analysed_result}", 
            #         title="Running Analysis")



    window.close()
    stop_listener = True


if __name__ == "__main__":
    Main()


