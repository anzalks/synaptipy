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


def func_mono_exp(x, a, b, c, d):
    return a * np.exp(-(x-b)/c) + d

def Fit_single_trace(Trace, Time_trace, x_start,x_end):
    
    idx_start=np.ravel(np.where(Time_trace >=x_start))[0]
    idx_stop=np.ravel(np.where(Time_trace >= x_end))[0]
    x = Time_trace[idx_start:idx_stop]
    y = Trace[idx_start:idx_stop]
    x2=np.array(np.squeeze(x))
    y2=np.array(np.squeeze(y))  
    
    try:
        param_bounds=([-np.inf,0.,0.,-1000.],[np.inf,1.,10.,1000.])      # be careful ok for seconds. If millisec change param 2 and 3
        popt, pcov = curve_fit(func_mono_exp, x2, y2,bounds=param_bounds, max_nfev = 10000) 
        print ('tau decay =',popt[2]*1000, ' ms' )
        return popt[2], popt, idx_start, idx_stop
    except:
        print ('Fit failed')
        popt[2]= float('nan')
        popt= float('nan')
        return popt[2], popt, idx_start, idx_stop
        pass


def fit_epsp_with_alpha(t, signal, sampling_rate,
                        debug=True):
    """
    Fits an alpha function to an EPSP segment of the signal and reconstructs the waveform.

    Parameters:
        t (numpy.ndarray): 1D array of time points.
        signal (numpy.ndarray): 1D array of signal values.
        debug (bool): If True, plots intermediate results for debugging.
        
    Returns:
        numpy.ndarray: Reconstructed waveform based on the fitted alpha function.
    """
    def alpha_function(t, A, t0, tau):
        alpha = (t - t0) * np.exp(-(t - t0) / tau)
        alpha[t < t0] = 0
        return A * alpha
    
    # Estimate baseline and threshold
    baseline = np.mean(signal[:int(0.002*sampling_rate)])#np.median(signal)
    std_dev = np.std(signal)
    signal = signal-baseline
    start_time = t[int(0.0015*sampling_rate)]  # Example: Apply the mask only for times > 0.005 seconds
    threshold = np.mean(signal[:int(0.002*sampling_rate)]) #+ 1.5 * std_dev
    epsp_mask = (signal >=threshold) & (t >=start_time)
    
    if debug:
        print(f"Baseline: {baseline}, Std Dev: {std_dev}, Threshold: {threshold}")
        plt.figure(figsize=(10, 5))
        plt.plot(t, signal, label="Signal")
        plt.axhline(baseline, color='green', linestyle='--', label="Baseline")
        plt.axhline(threshold, color='red', linestyle='--', label="Threshold")
        plt.legend()
        plt.title("Signal with Baseline and Threshold")
        plt.show()
    
    # Check if EPSP region is detected
    if not np.any(epsp_mask):
        raise RuntimeError("No EPSP detected in the signal.")
    
    t_epsp = t[epsp_mask]
    signal_epsp = signal[epsp_mask]
    
    if len(t_epsp) < 5:  # Ensure sufficient data points for fitting
        raise RuntimeError("Insufficient data points for fitting.")
    
    # Initial guess and bounds
    A_init = np.max(signal_epsp) - baseline 
    t0_init = t_epsp[0]
    tau_init = 0.0005
    p0 = [A_init, t0_init, tau_init]
    #bounds = ([-1*A_init, t_epsp[0], 1e-4], [10000 * A_init, t_epsp[-1], 10000])
    bounds = ([-np.inf, t_epsp[0], 1e-4], [np.inf, t_epsp[-1], 10e4])
    try:
        popt, _ = curve_fit(alpha_function, t_epsp, signal_epsp, p0=p0,
                            bounds=bounds, maxfev=10000)
        A_fit, t0_fit, tau_fit = popt
        reconstructed_waveform = alpha_function(t, A_fit, t0_fit, tau_fit)
    except Exception as e:
        raise RuntimeError(f"Alpha function fitting failed: {e}")
    
    if debug:
        plt.figure(figsize=(10, 5))
        plt.plot(t, signal, label="Original Signal", alpha=0.7)
        plt.plot(t, reconstructed_waveform, label="Fitted Waveform", linestyle='--')
        plt.axvline(t_epsp[0])
        plt.axvline(t_epsp[-1])
        plt.xlabel("Time")
        plt.ylabel("Signal")
        plt.legend()
        plt.title("EPSP Fitting")
        plt.show()
    
    return reconstructed_waveform


def fit_epsp_with_alpha_sum(t, signal, sampling_rate, debug=True):
    """
    Fits a sum of two alpha functions (one positive, one negative) to an EPSP segment 
    of the signal and reconstructs the waveform.

    Parameters:
        t (numpy.ndarray): 1D array of time points.
        signal (numpy.ndarray): 1D array of signal values.
        sampling_rate (float): Sampling rate of the signal in Hz.
        debug (bool): If True, plots intermediate results for debugging.

    Returns:
        numpy.ndarray: Reconstructed waveform based on the fitted alpha functions.
    """
    def alpha_function(t, A, t0, tau):
        alpha = (t - t0) * np.exp(-(t - t0) / tau)
        alpha[t < t0] = 0
        return A * alpha

    def combined_alpha_function(t, A1, t01, tau1, A2, t02, tau2):
        return (alpha_function(t, A1, t01, tau1) +
                alpha_function(t, A2, t02, tau2))

    # Estimate baseline and threshold
    baseline = np.mean(signal[:int(0.002 * sampling_rate)])
    std_dev = np.std(signal)
    signal = signal - baseline  # Remove baseline
    start_time = t[int(0.0015 * sampling_rate)]  # Apply the mask only for times > start_time
    threshold = np.mean(signal[:int(0.002 * sampling_rate)])

    # Create mask for EPSP region
    epsp_mask = (signal >= threshold) & (t >= start_time)

    if debug:
        print(f"Baseline: {baseline}, Std Dev: {std_dev}, Threshold: {threshold}")
        plt.figure(figsize=(10, 5))
        plt.plot(t, signal, label="Signal")
        plt.axhline(baseline, color='green', linestyle='--', label="Baseline")
        plt.axhline(threshold, color='red', linestyle='--', label="Threshold")
        plt.legend()
        plt.title("Signal with Baseline and Threshold")
        plt.show()

    # Check if EPSP region is detected
    if not np.any(epsp_mask):
        raise RuntimeError("No EPSP detected in the signal.")

    t_epsp = t[epsp_mask]
    signal_epsp = signal[epsp_mask]

    if len(t_epsp) < 5:  # Ensure sufficient data points for fitting
        raise RuntimeError("Insufficient data points for fitting.")

    # Initial guesses and bounds for the parameters
    A1_init = np.max(signal_epsp)
    t01_init = t_epsp[0]
    tau1_init = 0.0005

    A2_init = -1 * A1_init
    t02_init = t_epsp[0] + 0.001  # Slightly shifted
    tau2_init = 0.0005

    p0 = [A1_init, t01_init, tau1_init, A2_init, t02_init, tau2_init]
    bounds = (
        [-np.inf, t_epsp[0], 1e-4, -np.inf, t_epsp[0], 1e-4],
        [np.inf, t_epsp[-1], 1.0, np.inf, t_epsp[-1], 1.0]
    )

    try:
        popt, _ = curve_fit(combined_alpha_function, t_epsp, 
                            signal_epsp, p0=p0, bounds=bounds, 
                            maxfev=100000
                           )
        A1_fit, t01_fit, tau1_fit, A2_fit, t02_fit, tau2_fit = popt
        reconstructed_waveform = combined_alpha_function(t, A1_fit, t01_fit, tau1_fit, A2_fit, t02_fit, tau2_fit)
    except Exception as e:
        raise RuntimeError(f"Alpha function fitting failed: {e}")

    if debug:
        plt.figure(figsize=(10, 5))
        plt.plot(t, signal, label="Original Signal", alpha=0.7)
        plt.plot(t, reconstructed_waveform, label="Fitted Waveform (Sum of Alphas)", linestyle='--')
        plt.axvline(t_epsp[0], linestyle='--', color='grey', label="EPSP Start")
        plt.axvline(t_epsp[-1], linestyle='--', color='grey', label="EPSP End")
        plt.xlabel("Time")
        plt.ylabel("Signal")
        plt.legend()
        plt.title("EPSP Fitting with Sum of Alpha Functions")
        plt.show()

    return reconstructed_waveform



def fit_epsp_with_alpha_sum(t, signal, sampling_rate, 
                            debug=False):
    """
    Fits a sum of two alpha functions (one positive, one negative) to an EPSP segment 
    of the signal and reconstructs the waveform.

    Parameters:
        t (numpy.ndarray): 1D array of time points.
        signal (numpy.ndarray): 1D array of signal values.
        sampling_rate (float): Sampling rate of the signal in Hz.
        debug (bool): If True, plots intermediate results for debugging.

    Returns:
        numpy.ndarray: Reconstructed waveform based on the fitted alpha functions.
    """
    def alpha_function(t, A, t0, tau):
        alpha = (t - t0) * np.exp(-(t - t0) / tau)
        alpha[t < t0] = 0
        return A * alpha

    def combined_alpha_function(t, A1, t01, tau1, A2, t02, tau2):
        return (alpha_function(t, A1, t01, tau1) +
                alpha_function(t, A2, t02, tau2))

    # Estimate baseline and threshold
    baseline = np.mean(signal[:int(0.002 * sampling_rate)])
    std_dev = np.std(signal)
    signal = signal - baseline  # Remove baseline
    start_time = t[int(0.0015 * sampling_rate)]  # Apply the mask only for times > start_time
    threshold = np.mean(signal[:int(0.002 * sampling_rate)])

    # Create mask for EPSP region
    epsp_mask = (signal >= threshold) & (t >= start_time)

    if debug:
        print(f"Baseline: {baseline}, Std Dev: {std_dev}, Threshold: {threshold}")
        plt.figure(figsize=(10, 5))
        plt.plot(t, signal, label="Signal")
        plt.axhline(baseline, color='green', linestyle='--', label="Baseline")
        plt.axhline(threshold, color='red', linestyle='--', label="Threshold")
        plt.legend()
        plt.title("Signal with Baseline and Threshold")
        plt.show()

    # Check if EPSP region is detected
    if not np.any(epsp_mask):
        raise RuntimeError("No EPSP detected in the signal.")

    t_epsp = t[epsp_mask]
    signal_epsp = signal[epsp_mask]

    if len(t_epsp) < 5:  # Ensure sufficient data points for fitting
        raise RuntimeError("Insufficient data points for fitting.")

    # Initial guesses and bounds for the parameters
    A1_init = np.max(signal_epsp)
    t01_init = t_epsp[0]
    tau1_init = 0.0005

    A2_init = -0.5 * A1_init
    t02_init = t_epsp[0] + 0.001  # Slightly shifted
    tau2_init = 0.0005

    p0 = [A1_init, t01_init, tau1_init, A2_init, t02_init, tau2_init]
    bounds = (
        [-np.inf, t_epsp[0], 1e-4, -np.inf, t_epsp[0], 1e-4],
        [np.inf, t_epsp[-1], 1.0, np.inf, t_epsp[-1], 1.0]
    )

    try:
        popt, _ = curve_fit(
            combined_alpha_function, t_epsp, signal_epsp, p0=p0, bounds=bounds, maxfev=10000
        )
        A1_fit, t01_fit, tau1_fit, A2_fit, t02_fit, tau2_fit = popt
        reconstructed_waveform = combined_alpha_function(t, A1_fit, t01_fit, tau1_fit, A2_fit, t02_fit, tau2_fit)
    except Exception as e:
        raise RuntimeError(f"Alpha function fitting failed: {e}")

    if debug:
        plt.figure(figsize=(10, 5))
        plt.plot(t, signal, label="Original Signal", alpha=0.7)
        plt.plot(t, reconstructed_waveform, label="Fitted Waveform (Sum of Alphas)", linestyle='--')
        plt.axvline(t_epsp[0], linestyle='--', color='grey', label="EPSP Start")
        plt.axvline(t_epsp[-1], linestyle='--', color='grey', label="EPSP End")
        plt.xlabel("Time")
        plt.ylabel("Signal")
        plt.legend()
        plt.title("EPSP Fitting with Sum of Alpha Functions")
        plt.show()

    return reconstructed_waveform

def plot_single_channel_trials(segments,t,
                               sampling_rate,
                               channel_list,num_chan):
    num_trials=len(segments)
    #num_trials = 4
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
        ftc_tf = int(sampling_rate*1)
        #fit_av = fitted_trace(t[ftc_ti:ftc_tf],
        #                      trial_av[ftc_ti:ftc_tf],
        #                      sampling_rate)
        fit_av = fit_epsp_with_alpha_sum(t[ftc_ti:ftc_tf],
                                         trial_av[ftc_ti:ftc_tf],
                                         sampling_rate
                                        )+baseline_av 


    #axs[3].plot(t[ftc_ti:ftc_tf],fit_av)
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
            #baseline_trial = np.mean(signal[:int(0.005*sampling_rate)])
            #signal = signal-baseline_trial
            axs_.plot(t,signal,color=trial_color,alpha=0.6)
            axs_.set_title(f"channel: {channel_name}")
            if s==0:
                axs_.set_ylabel(units)
        trial_av = average_trials(segments,ch_no)
        baseline_av =np.mean(trial_av[:int(0.002*sampling_rate)])
        trial_av = trial_av-baseline_av
        ftc_ti = int(sampling_rate*7.1)
        ftc_tf = int(sampling_rate*7.2)
        #fit_av = fit_epsp_with_alpha(t[ftc_ti:ftc_tf],
        #                             trial_av[ftc_ti:ftc_tf],
        #                             sampling_rate
        #                            )+baseline_av 
        if ch_no==0:
            fit_av = fit_epsp_with_alpha_sum(t[ftc_ti:ftc_tf],
                                             trial_av[ftc_ti:ftc_tf],
                                             sampling_rate
                                            )+baseline_av 
            axs[ch_no].plot(t,trial_av+baseline_av,color=av_color)
            #print(f"fit_curve: {t[ftc_ti:ftc_tf]}")
            axs[ch_no].plot(t[ftc_ti:ftc_tf],fit_av,color=fit_color)
        #axs[ch_no].set_xlim(t[ftc_ti],t[ftc_tf])
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