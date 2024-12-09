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
    list_with_ch = reader.header['signal_channels']
    channels = []
    for channel in list_with_ch:
        channels.append(channel[0])
    channel_count = len(channels)
    return channels, channel_count

def apply_filter(data, filter_type='bandpass',
                 cutoff_freqs=(0.1,2000), 
                 fs=10000, order=5):
    """
    Applies a filter (low-pass, high-pass, band-pass, or band-stop) to a 1D NumPy array.
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
        low, high = cutoff_freqs
        normalized_cutoffs = [low / nyquist, high / nyquist]
    else:
        normalized_cutoffs = cutoff_freqs / nyquist

    # Create filter coefficients
    b, a = butter(order, normalized_cutoffs, btype=filter_type)
    
    # Apply the filter using filtfilt (zero-phase filtering)
    filtered_data = filtfilt(b, a, data)
    
    return filtered_data

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
    trial_av = []
    for s, segment in enumerate(segments):
        signal =  np.ravel(segment.analogsignals[ch_no].magnitude)
        trial_av.append(signal)
    trial_av=np.array(trial_av)
    trial_av = np.mean(trial_av,axis=0)
    return trial_av


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
            axs[s].plot(t,signal)
            axs[s].plot(t,filt_sig)
            axs[s].set_title(f"trial: {s}")
            axs[s].set_ylabel(units)
        trial_av = average_trials(segments,ch_no)
    axs[3].plot(t,trial_av)
    plt.tight_layout()
    plt.show()
    pass

def plot_multi_channel_trials(segments,t,
                              sampling_rate,
                              hannel_list,num_chan):
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
            axs_.plot(t,signal)
            axs_.set_title(f"channel: {channel_name}")
            if s==0:
                axs_.set_ylabel(units)
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
