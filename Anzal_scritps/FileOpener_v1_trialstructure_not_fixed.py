__author__           = "Anzal KS"
__copyright__        = "Copyright 2024-, Anzal KS"
__maintainer__       = "Anzal KS"
__email__            = "anzalks@ncbs.res.in"

from pathlib import Path
import neo.io as nIO
import numpy as np
import multiprocessing
import time
import argparse
from tqdm import tqdm
from matplotlib import pyplot as plt
import multiprocessing
from scipy.signal import butter, filtfilt
from scipy.optimize import curve_fit

av_color = "000000" # black 
trial_color = "#377eb8" # blue 
fit_color = "#de6f00" # orange
np.set_printoptions(threshold=np.inf)


#dictionary of all availabe IOs and the file extensions in neo 
IODict = {'AlphaOmegaIO':['lsx', 'mpx'],
          'AsciiImageIO':[],
          'AsciiSignalIO':['txt', 'asc', 'csv', 'tsv'],
          'AsciiSpikeTrainIO':['txt'],
          'AxographIO':['axgd', 'axgx', ''],
          'AxonIO':['abf'],
          'AxonaIO':['bin', 'set', '1', '2', '3', '4', '5', '6', '7', '8', '9',
                     '10', '11', '12', '13', '14', '15', '16', '17', '18',
                     '19', '20', '21', '22', '23', '24', '25', '26', '27',
                     '28', '29', '30', '31', '32'],
          'BCI2000IO':['dat'],
          'BiocamIO':['h5', 'brw'],
          'BlackrockIO':['ns1', 'ns2', 'ns3', 'ns4', 'ns5', 'ns6', 'nev',
                         'sif', 'ccf'],
          'BlkIO':[],
          'BrainVisionIO':['vhdr'],
          'BrainwareDamIO':['dam'],
          'BrainwareF32IO':['f32'],
          'BrainwareSrcIO':['src'],
          'CedIO':['smr', 'smrx'],
          'EDFIO':['edf'],
          'ElanIO':['eeg'],
          'IgorIO':['ibw', 'pxp'],
          'IntanIO':['rhd', 'rhs', 'dat'],
          'KlustaKwikIO':['fet', 'clu', 'res', 'spk'],
          'KwikIO':['kwik'],
          'MEArecIO':['h5'],
          'MaxwellIO':['h5'],
          'MedIO':['medd', 'rdat', 'ridx'],
          'MicromedIO':['trc', 'TRC'],
          'NWBIO':['nwb'],
          'NeoMatlabIO':['mat'],
          'NestIO':['gdf', 'dat'],
          'NeuralynxIO':['nse', 'ncs', 'nev', 'ntt', 'nvt', 'nrd'],
          'NeuroExplorerIO':['nex'],
          'NeuroNexusIO':[],
          'NeuroScopeIO':['xml', 'dat', 'lfp', 'eeg'],
          'NeuroshareIO':['nsn'],
          'NixIO':['h5', 'nix'],
          'OpenEphysBinaryIO':['xml', 'oebin', 'txt', 'dat', 'npy'],
          'OpenEphysIO':['continuous', 'openephys', 'spikes', 'events', 'xml'],
          'PhyIO':['npy', 'mat', 'tsv', 'dat'],
          'PickleIO':['pkl', 'pickle'],
          'Plexon2IO':['pl2'],
          'PlexonIO':['plx'],
          'RawBinarySignalIO':['raw', 'bin', 'dat'],
          'RawMCSIO':['raw'],
          'Spike2IO':['smr'],
          'SpikeGLXIO':['meta', 'bin'],
          'SpikeGadgetsIO':['rec'],
          'StimfitIO':['abf', 'dat', 'axgx', 'axgd', 'cfs'],
          'TdtIO':['tbk', 'tdx', 'tev', 'tin', 'tnt', 'tsq', 'sev', 'txt'],
          'TiffIO':['tiff'],
          'WinEdrIO':[],
          'WinWcpIO':['wcp'],
          }

curve_features = {'EPSP':{'tau_rise':{'min':1,'max':5},
                          'tau_fall':{'min':10,'max':100},
                          'a_max':{'min':0,'max':30},
                          'a_min':{'min':-10,'max':0}
                         },
                  'IPSP':{'tau_rise':{'min':1,'max':5},
                          'tau_fall':{'min':10,'max':100},
                          'a_max':{'min':0,'max':30},
                          'a_min':{'min':-10,'max':0}
                         },
                  'EPSC':{'tau_rise':{'min':1,'max':5},
                          'tau_fall':{'min':5,'max':100},
                          'a_max':{'min':-1500,'max':0},
                          'a_min':{'min':0,'max':100}
                         },
                  'IPSC':{'tau_rise':{'min':1,'max':5},
                          'tau_fall':{'min':5,'max':100},
                          'a_max':{'min':-1500,'max':0},
                          'a_min':{'min':0,'max':100}
                         }
                 }



def current_injected(reader):
    """
    reader: neo object obtained from nio.{yourFileType}IO(file_name)
    injected_currentfinder
    works for axonIO readers only
    """
    try:
        protocol_raw = reader.read_raw_protocol()
    except AttributeError:
        raise ValueError(f"input reader is not based on axon recording") 

    protocol_raw = protocol_raw[0]
    protocol_trace = []
    for n in protocol_raw:
        protocol_trace.append(n[0])
    if not protocol_trace:
        i_av = 0
    else:
        i_min = np.abs(np.min(protocol_trace))
        i_max = np.abs(np.max(protocol_trace))
        i_av = np.around((i_max-i_min),2)
    print(i_av)
    return i_av

def protocol_file_name(reader):
    """
    IO read reader should be provided as reader
    the path format is made for windows
    works for AxonIO
    """                                                
    try:
        protocol_name = reader._axon_info['sProtocolPath']
    except AttributeError:
        raise ValueError(f"input reader is not based on axon recording"
                         f":'_axon_info' is not available") 
    #protocol_name = Path(protocol_name)
    # print(f"absolute path to protocol file: {protocol_name}")
    try:
        protocol_name = str(protocol_name).split('\\')[-1]
        protocol_name = protocol_name.split('.')[-2]
    except AttributeError:
        raise ValueError(f"'{protocol_name}' path was not based on the format"
                         f"above please change the path format")
    print(f"protocol_name:{protocol_name}.....")
    return protocol_name





def list_files(p,ext="abf"):
    """
    filename is an posixpath from glob.Path
    ext is the extension of your file name
    funcion list all the file names with the given extension in the folder
    """
    f_list = []
    f_list=list(p.glob(f'**/*{ext}'))
    f_list.sort()
    return f_list

def read_with_IO(file_name, ext="abf",IO=None):
    if IO==None:
        availableIOs = [key for key, values in IODict.items() if ext in values]
    else:
        availableIOs = IO
    usedIO= availableIOs[0]
    print(f'availableIOs:{availableIOs},IO in use "{usedIO}" ')
    print('if you prefer your own IO please parse the IO')
    try:
            io_class = getattr(nIO, usedIO)
    except AttributeError:
            raise ValueError(f"'{usedIO}' is not a valid IO class in neo.io")

    reader = io_class(file_name)

    return reader 

def channel_name_to_index(reader, channel_name):
    """
    Convert channel names to index as an intiger
    """
    for signal_channel in reader.header['signal_channels']:
        if channel_name == signal_channel[0]:
            return int(signal_channel[1])

def get_channel_name(reader):
    """
    If a channel name is used while recording it will be extracted
    and used for further
    """
    list_with_ch = reader.header['signal_channels']
    channels = []
    for channel in list_with_ch:
        channels.append(channel[0])
    channel_count = len(channels)
    return channels, channel_count

def apply_filter(data, fs,cutoff_freqs=(0.1,5000),
                 filter_type='bandpass',order=3):
    """
    Applies a filter (low-pass, high-pass, band-pass, or band-stop) to a 1D NumPy array.

    Args:
        - data (np.ndarray): Input 1D signal.
        - filter_type (str): Type of filter ('lowpass', 'highpass', 'bandpass', 'bandstop').
        - cutoff_freqs (float or tuple): Cutoff frequency/frequencies (Hz). 
        For 'lowpass' and 'highpass', provide a single float.
        For 'bandpass' and 'bandstop', provide a tuple (low, high).
        - fs (float): Sampling frequency of the signal (Hz).
        - order (int): Order of the filter (default: 5).

    Returns:
        - np.ndarray: Filtered signal.
    """
    # Normalize cutoff frequency to Nyquist frequency
    nyquist = 0.5 * fs
    
    if filter_type in ['bandpass', 'bandstop']:
        # Expecting a tuple (low, high)
        if not isinstance(cutoff_freqs, tuple) or len(cutoff_freqs) != 2:
            raise ValueError("For 'bandpass' or 'bandstop', cutoff_freqs must be a tuple (low, high)")
        low, high = cutoff_freqs
        normalized_cutoffs = [low / nyquist, high / nyquist]
    else:
        # Expecting a single float value
        if not isinstance(cutoff_freqs, (int, float)):
            raise ValueError("For 'lowpass' or 'highpass', cutoff_freqs must be a single float")
        normalized_cutoffs = cutoff_freqs / nyquist

    # Create filter coefficients
    b, a = butter(order, normalized_cutoffs, btype=filter_type)
    
    # Apply the filter using filtfilt (zero-phase filtering)
    filtered_data = filtfilt(b, a, data)
    
    return filtered_data

def average_trials(segments,ch_no):
    """
    if the trail structure is in a way that it can be stacked
    """
    trial_av = []
    for s, segment in enumerate(segments):
        signal =  np.ravel(segment.analogsignals[ch_no].magnitude)
        trial_av.append(signal)
    trial_av=np.array(trial_av)
    trial_av = np.mean(trial_av,axis=0)
    return trial_av

def fit_double_exp(x, A1, tau1, A2, tau2, C):
    """
    Double exponential function.
    x, trace or signal to pass it in
    A1, tau1: Amplitude and time constant of the first exponential.
    A2, tau2: Amplitude and time constant of the second exponential.
    C: Constant offset.
    """
    return A1 * np.exp(-x / tau1) + A2 * np.exp(-x / tau2) + C


from scipy.stats import linregress

def fitted_trace(t, signal, sampling_rate, tau_window_ms=500.0):
    """
    Fits a single exponential decay to a synaptic signal, with a data-driven initial guess for tau.
    
    Parameters
    ----------
    t : np.ndarray
        Time array for the recorded signal (seconds).
    signal : np.ndarray
        The recorded signal (EPSP, EPSC, IPSC) as a 1D array.
    sampling_rate : float
        Sampling rate in Hz (samples per second).
    tau_window_ms : float, optional
        The length of the window after the peak (in ms) used to estimate the initial tau guess.
        Default is 5 ms.
        
    Returns
    -------
    fitted_signal : np.ndarray
        The fitted curve evaluated at times t.
    A_fit : float
        Fitted amplitude.
    tau_fit : float
        Fitted time constant.
    baseline_fit : float
        Fitted baseline.
    """

    # --- Baseline Calculation ---
    baseline_window_ms = 5.0
    baseline_points = int((baseline_window_ms / 1000.0) * sampling_rate)
    baseline = np.mean(signal[:baseline_points])

    # --- Find Peak ---
    # If you know your event is an EPSP/EPSC (positive deflection), use argmax.
    # If it's an IPSC (negative), you might use argmin.
    peak_index = np.argmax(signal)  # Adjust if needed
    t_peak = t[peak_index]
    A_init = signal[peak_index] - baseline

    # --- Estimate tau_init from Data Window ---
    # Define the end time for the tau estimation window
    tau_window_s = tau_window_ms / 1000.0
    end_time_for_tau = t_peak + tau_window_s

    # Extract indices for the tau estimation window
    window_indices = np.where((t >= t_peak) & (t <= end_time_for_tau))[0]

    # Ensure we have enough points in the window
    if len(window_indices) > 2:
        # Subtract baseline in that window
        signal_window = signal[window_indices] - baseline
        time_window = t[window_indices] - t_peak

        # Use only positive values for log (if EPSC/EPSP). If IPSC is negative, invert sign appropriately.
        # For EPSC/EPSP: signal_window should be positive around the peak.
        # If IPSC is negative, you may consider signal_window = baseline - signal[window_indices].
        
        # Filter to keep only positive values (for log)
        valid_indices = np.where(signal_window > 0)[0]
        if len(valid_indices) > 2:
            signal_window_pos = signal_window[valid_indices]
            time_window_pos = time_window[valid_indices]

            # Take the natural log of the amplitude portion
            ln_signal = np.log(signal_window_pos)

            # Perform a linear regression: ln(V - baseline) vs (t - t_peak)
            slope, intercept, r_value, p_value, std_err = linregress(time_window_pos, ln_signal)

            # slope ≈ -1 / tau
            tau_init = -1.0 / slope if slope < 0 else 0.005  # fallback if slope is positive
        else:
            # Fallback if insufficient valid points
            tau_init = 0.005
    else:
        # Fallback if window too small
        tau_init = 0.005

    # --- Define the single exponential model ---
    def single_exp(t_array, A, tau, baseline_param):
        return baseline_param + A * np.exp(-(t_array - t_peak) / tau)

    p0 = [A_init, tau_init, baseline]

    # Optional parameter bounds
    A_bounds = (0, 50)
    tau_bounds = (1e-4, 0.5)
    baseline_bounds = (baseline - 5*abs(A_init), baseline + 5*abs(A_init))

    # Fit the curve
    popt, pcov = curve_fit(
        single_exp, t, signal, p0=p0,
        bounds=([0, tau_bounds[0], baseline_bounds[0]],
                [np.inf, tau_bounds[1], baseline_bounds[1]])
    )

    A_fit, tau_fit, baseline_fit = popt
    fitted_signal = single_exp(t, A_fit, tau_fit, baseline_fit)

    return fitted_signal#, A_fit, tau_fit, baseline_fit


























































#def fitted_trace(t, signal,sampling_rate):
#    
#    #baseline = np.mean(signal[:int(0.005*sampling_rate)])
#    #signal=signal-baseline
#    #param_bounds=([-np.inf,0.,0.,-1000.,0],[np.inf,1.,10.,1000.,0.5])
#    a1_max = np.max(signal)
#    a2_max = a1_max
#    a1_min = np.min(signal)
#    a2_min = a1_min
#    c_max = int(0.005*sampling_rate)
#    c_min = int(0.001*sampling_rate)
#    tau1_max =100
#    tau1_min =5
#    tau2_max =100
#    tau2_min =5
#
#    #param_bounds=([a1_min,0.,a2_min,0.,0.],[a1_max,1,a2_max,0.,0.5])
#    #param_bounds=([a1_min,0.0001,a2_min,0.0001,0.],[a1_max,1.,a2_max,1.,0.5])
#    param_bounds=([a1_min,tau1_min,a2_min,tau2_min,c_min],
#                  [a1_max,tau1_max,a2_max,tau2_max,c_max])
#    popt, pcov = curve_fit(fit_double_exp, t, signal,
#                           bounds=param_bounds, max_nfev = 100000)
#    A1, tau1, A2, tau2, C = popt
#    fitted_curve = fit_double_exp(t, *popt)
#    return fitted_curve

#def plot_single_channel_trials(segments,t,
#                               sampling_rate,
#                               channel_list,num_chan):
#    """
#    function can access the segments and plot each trial in rows of subplot 
#    """
#    num_trials=len(segments)
#    fig,axs = plt.subplots(nrows=num_trials, ncols=1,figsize=(5,15), 
#                           sharex=True, sharey=False)
#    for ch_no,channel_name in enumerate(channel_list):
#        for s, segment in enumerate(segments):
#            trial_no = s
#            units = str(segment.analogsignals[ch_no].units).split()[-1]
#            signal =  np.ravel(segment.analogsignals[ch_no].magnitude)
#            if s==0:
#                print()
#            axs[s].plot(t,signal)
#            axs[s].plot(t,filt_sig)
#            axs[s].set_title(f"trial: {s}")
#            axs[s].set_ylabel(units)
#    plt.tight_layout()
#    plt.show()
#    pass


def plot_single_channel_trials(segments,t,
                               sampling_rate,
                               channel_list,num_chan):
    #num_trials=len(segments)
    num_trials = 4
    fig,axs = plt.subplots(nrows=num_trials, ncols=1,figsize=(5,15), 
                           sharex=True, sharey=False)
    for ch_no,channel_name in enumerate(channel_list):
        for s, segment in enumerate(segments):
            if s>=3:
                break
            trial_no = s
            units = str(segment.analogsignals[ch_no].units).split()[-1]
            signal =  np.ravel(segment.analogsignals[ch_no].magnitude)
            filt_sig = apply_filter(signal,
                                    cutoff_freqs=(1,1000),
                                    fs=sampling_rate
                                   )
            if s==0:
                print()
            axs[s].plot(t,signal,color=trial_color,alpha=0.6)
            axs[s].plot(t,filt_sig)
            axs[s].set_title(f"trial: {s}")
            axs[s].set_ylabel(units)
        trial_av = average_trials(segments,ch_no)
        ftc_ti = int(sampling_rate*0.05)
        ftc_tf = int(sampling_rate*0.0508)
        fit_av = fitted_trace(t[ftc_ti:ftc_tf],
                              trial_av[ftc_ti:ftc_tf],
                              sampling_rate)
    axs[3].plot(t[ftc_ti:ftc_tf],fit_av)
    axs[3].plot(t,trial_av,color=av_color)
    plt.tight_layout()
    plt.show()
    pass

def plot_multi_channel_trials(segments,t,
                              sampling_rate,
                              channel_list,num_chan):
    fig,axs = plt.subplots(nrows=num_chan, ncols=1, 
                           sharex=True, sharey=False)
    
    for ch_no,channel_name in enumerate(channel_list):
        for s, segment in enumerate(segments):
            if num_chan>1:
                axs_=axs[ch_no]
            else:
                axs_=axs
            trial_no = s
            units = str(segment.analogsignals[ch_no].units).split()[-1]
            signal =  np.ravel(segment.analogsignals[ch_no].magnitude)
            axs_.plot(t,signal,color=trial_color,alpha=0.6)
            axs_.set_title(f"channel: {channel_name}")
            if s==0:
                axs_.set_ylabel(units)
        trial_av = average_trials(segments,ch_no)
        ftc_ti = int(sampling_rate*7.1)
        ftc_tf = int(sampling_rate*7.2)
        fit_av = fitted_trace(t[ftc_ti:ftc_tf],
                              trial_av[ftc_ti:ftc_tf],
                              sampling_rate)
        axs[ch_no].plot(t,trial_av,color=av_color)
        print(f"fit_curve: {t[ftc_ti:ftc_tf]}")
        axs[ch_no].plot(t[ftc_ti:ftc_tf],fit_av,color=fit_color)
        axs[ch_no].set_xlim(t[ftc_ti],t[ftc_tf])
    plt.tight_layout()
    plt.show()
    pass


def plot_raw_traces(reader,channel_list, num_chan,
                    SigGrpMode='split'):
    if SigGrpMode=='split':
        SigGrpMode = 'split-all'
    else:
        SigGrpMode = 'all-in-one'
    
    block  = reader.read_block(signal_group_mode=SigGrpMode)
    segments = block.segments
    sample_trace = segments[0].analogsignals[0]
    sampling_rate = sample_trace.sampling_rate.magnitude
    print(f"sampling_rate:{sampling_rate}")
    sampling_rate_unit = str(sample_trace.sampling_rate.units).split()[-1]
    ti = sample_trace.t_start
    tf = sample_trace.t_stop
    t = np.linspace(0,float(tf-ti),len(sample_trace))
    if num_chan>1:
        plot_multi_channel_trials(segments,t,
                                  sampling_rate,
                                  channel_list,num_chan)
    else:
        plot_single_channel_trials(segments,t,
                                   sampling_rate,
                                   channel_list,num_chan)
    pass





def open_data(file_name):
    """
    file_name, path to your individual ephys data file, must be a posixpath
    """
    ext = file_name.suffix.split('.')[-1]
    file_name=str(file_name)
    print(ext)
    reader= read_with_IO(file_name,ext)
    print(reader)
    channel_list, num_chan  = get_channel_name(reader)
    try:
        protocol_file_name(reader)
    except:
        print(f"couldn't collect the protocol path"
              f"for file: {file_name}")
    try:
        injI =current_injected(reader)
    except:
        print(f"couldn't calculate injected current"
              f"for file: {file_name}")
    plot_raw_traces(reader,channel_list,num_chan,
                    SigGrpMode='split')
    pass









































def main():
    # Argument parser.
    description = '''A script that opens neural data using neo'''
    
    #setup the argument parser
    parser = argparse.ArgumentParser(description=description)
    
    #listed out arguments
    parser.add_argument('--file-path', '-f'
                        , required = False,default ='./', type=str
                        , help = 'path to neural data'
                       )
    parser.add_argument('--folder-path', '-d'
                        , required = False,default ='./', type=str
                        , help = 'path to neural data'
                       )




    #parse the arguents
    args = parser.parse_args()

    #define the variable from parser
    file_path = Path(args.file_path)
    folder_path = Path(args.folder_path)

    #call the fucntion to open files
    open_data(file_path)
    
    #open files in a folder
    if folder_path!=None:
        file_list = list_files(folder_path)
        print(file_list)





if __name__  == '__main__':
    #timing the run with time.time
    ts =time.time()
    main() 
    tf =time.time()
    print(f'total time = {np.around(((tf-ts)/60),1)} (mins)')
