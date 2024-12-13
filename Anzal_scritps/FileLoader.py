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
from scipy.signal import find_peaks
from scipy.ndimage import gaussian_filter1d
import PySimpleGUI as sg 
import pprint as pprint 

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


def file_properties(reader,channel_list, num_chan,
                    trial_average,
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
    time_units = str(sample_trace.times.units).split()[-1]
    ti = sample_trace.t_start
    tf = sample_trace.t_stop
    t = np.linspace(0,float(tf-ti),len(sample_trace))
    if num_chan>1:
        plot_multi_channel_trials(segments,t,
                                  sampling_rate,
                                  time_units,
                                  trial_average,
                                  channel_list,num_chan)
    else:
        plot_single_channel_trials(segments,t,
                                   sampling_rate,
                                   time_units,
                                   trial_average,
                                   channel_list,num_chan)
    file_prop = {"sampling rate ":f"{sampling_rate} {sampling_rate_unit}",
                 "gorup mode":SigGrpMode,
                 "duration of recording":f"{float(tf-ti)} {time_units}"
                }
    return file_prop 


def read_with_IO(file_name, ext=None, IO=None):
    if file_name==None:
        pass
    if isinstance(file_name, str):
        file_name = Path(file_name)
    else:
        file_name=file_name
    """
    file_name, path to your individual ephys data file, must be a posixpath
    """
    ext = file_name.suffix.split('.')[-1]
    file_name=str(file_name)
    print(ext)
    print(f"file path:{file_name}")
    if IO==None:
        availableIOs = [key for key, values in IODict.items() if ext in values]
    else:
        availableIOs = IO
    usedIO= availableIOs[0] # pick your IO to open your file incase you know
    #which on to pick
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

def plot_all_trial_sing_ch(segments,t,
                           sampling_rate,
                           time_units,
                           channel_list,num_chan,
                           fig,axs):
    for ch_no,channel_name in enumerate(channel_list):
        for s, segment in enumerate(segments):
            trial_no = s
            units = str(segment.analogsignals[ch_no].units).split()[-1]
            signal =  np.ravel(segment.analogsignals[ch_no].magnitude)
            axs[s].plot(t,signal,color=trial_color,alpha=0.6)
            axs[s].set_title(f"trial: {s}")
            axs[s].set_ylabel(units)
        axs[s].set_xlabel(f"time ({time_units})")

def plot_all_trial_ac_sing_ch(segments,t,
                              sampling_rate,
                              time_units,
                              channel_list,num_chan,
                              fig,axs):
    for ch_no,channel_name in enumerate(channel_list):
        for s, segment in enumerate(segments):
            trial_no = s
            units = str(segment.analogsignals[ch_no].units).split()[-1]
            signal =  np.ravel(segment.analogsignals[ch_no].magnitude)
            axs.plot(t,signal,color=trial_color,alpha=0.6)
            axs.set_ylabel(units)
        trial_av = average_trials(segments,ch_no)
        axs.plot(t,trial_av,color=av_color)
        axs.set_title(f"Average of {s} trials")
        axs.set_xlabel(f"time ({time_units})")
    #plt.tight_layout()
    return fig


def plot_single_channel_trials(segments,t,
                               sampling_rate,
                               time_units,
                               trial_average,
                               channel_list,num_chan):
    if trial_average==True:
        num_trials=1
    else:
        num_trials=len(segments)
    fig,axs = plt.subplots(nrows=num_trials, ncols=1,#figsize=(4,8), 
                           sharex=True, sharey=False)
    if trial_average==True:
        plot_all_trial_ac_sing_ch(segments,t,              
                                  sampling_rate,
                                  time_units,
                                  channel_list,num_chan,
                                  fig,axs)
    else:
        plot_all_trial_sing_ch(segments,t,
                               sampling_rate,
                               time_units,
                               channel_list,num_chan,
                               fig,axs)
    #plt.tight_layout()
    #plt.show()
    return fig

def plot_multi_channel_trials(segments,t,
                              sampling_rate,
                              time_units,
                              trial_average,
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
        #baseline_av =np.mean(trial_av[:int(0.002*sampling_rate)])
        #trial_av = trial_av-baseline_av
        ftc_ti = int(sampling_rate*7.1)
        ftc_tf = int(sampling_rate*7.2)
        if trial_average:
            axs[ch_no].plot(t,trial_av,color=av_color)
        else:
            continue
        ##fit_av = fit_epsp_with_alpha(t[ftc_ti:ftc_tf],
        ##                             trial_av[ftc_ti:ftc_tf],
        ##                             sampling_rate
        ##                            )+baseline_av 
        #if ch_no==0:
        #    #fitted_results =fit_alpha_peaks(trial_av, t, sampling_rate,
        #    #                                use_local_baseline=True,
        #    #                                debug=False)
        #    #for i in fitted_results:
        #    #    axs[ch_no].plot(i[1],i[0]+baseline_av,color=fit_color)
        #    #fit_av = fit_epsp_with_alpha_sum(t[ftc_ti:ftc_tf],
        #    #                                 trial_av[ftc_ti:ftc_tf],
        #    #                                 sampling_rate
        #    #                                )+baseline_av 
        #    #axs[ch_no].plot(t[ftc_ti:ftc_tf],fit_av,color=fit_color)
        #    axs[ch_no].plot(t,trial_av+baseline_av,color=av_color)
        #    #print(f"fit_curve: {t[ftc_ti:ftc_tf]}")
        ##axs[ch_no].set_xlim(t[ftc_ti],t[ftc_tf])
    axs[ch_no].set_xlabel(f"time ({time_units})")
    #plt.tight_layout()
    #plt.show()
    return fig


def plot_raw_traces(reader,channel_list, num_chan,
                    trial_average,
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
    time_units = str(sample_trace.times.units).split()[-1]
    ti = sample_trace.t_start
    tf = sample_trace.t_stop
    t = np.linspace(0,float(tf-ti),len(sample_trace))
    if num_chan>1:
        fig = plot_multi_channel_trials(segments,t,
                                        sampling_rate,
                                        time_units,
                                        trial_average,
                                        channel_list,num_chan)
    else:
        fig = plot_single_channel_trials(segments,t,
                                         sampling_rate,
                                         time_units,
                                         trial_average,
                                         channel_list,num_chan)
    file_prop = {"sampling rate ":f"{sampling_rate} {sampling_rate_unit}",
                 "gorup mode":SigGrpMode,
                 "duration of recording":f"{float(tf-ti)} {time_units}"
                }
    return fig, file_prop 





def show_data(reader,
              trial_average=False):
    channel_list, num_chan  = get_channel_name(reader)
    try:
        protocol_file_name(reader)
    except:
        print(f"couldn't collect the protocol path")
    try:
        injI =current_injected(reader)
    except:
        print(f"couldn't calculate injected current")
    fig, file_prop=plot_raw_traces(reader,channel_list,num_chan,
                                   trial_average,
                                   SigGrpMode='split')
    file_prop["trial_average"] = trial_average
    return fig, file_prop


def load_files():
    sg.theme('DarkBlue')	

    layout = [[sg.Text('Enter File name'), 
               sg.InputText(key='-FILE_PATH-'),
               sg.FileBrowse(), sg.Button('Open File')
              ],
              [sg.Text('Enter Folder name '), 
               sg.InputText(key='-FOLDER_NAME-'),
               sg.FolderBrowse(), sg.Button('Start Folder')
              ],
              [sg.Button('Close')]
             ]
    
    window = sg.Window('Load files', layout, modal=True, location=(10, 10))

    reader = None  # Initialize reader to a default value

    while True:
        event, values = window.read()
        if event in (None, 'Close'):  # If user closes window or clicks cancel
            break
        
        if event == 'Open File':
            file_path = values['-FILE_PATH-']
            if not file_path:
                sg.popup_error("Please select a valid file!")
                continue
            print(f"event structure: {values}")
            reader = read_with_IO(file_path)  # Assuming `read_with_IO` is defined elsewhere
            window.close()
            break

        if event == 'Start Folder':
            folder_path = values['-FOLDER_NAME-']
            if not folder_path:
                sg.popup_error("Please select a valid folder!")
                continue
            
            list_file = glob.glob(os.path.join(folder_path, '*.wcp'))
            if not list_file:
                sg.popup_error("No .wcp files found in the selected folder!")
                continue

            FREC, FTIME, sampling = load_wcp(list_file[0])  # Assuming `load_wcp` is defined elsewhere
            for file in list_file[1:]:
                REC, TIME, sampling = load_wcp(file)
                FREC = np.append(FREC, REC, axis=0)
            
            FREC = np.transpose(FREC)
            FTIME = np.transpose(FTIME)
            columns = [f"Trace-{x}" for x in range(len(FREC[1]))]
            RECORDINGS = pd.DataFrame(FREC, index=FTIME[:, 0], columns=columns)
            window.close()
            break

    window.close()
    return reader






#def load_files():
#    sg.theme('DarkBlue')	
#    
#    layout= [  [sg.Text('Enter File name     '),
#                sg.InputText(), sg.FileBrowse(),
#                sg.Button('Start File'),key='-FILE_NAME-'
#               ],
#                [sg.Text('Enter Folder name '), sg.InputText(), sg.FolderBrowse(),sg.Button('Start Folder')]]
#    
#    window= sg.Window('Load files', layout, modal = True, location=(10,10))
#    
#    while True:
#        event, values = window.read()
#        if event in (None, 'Close'):	# if user closes window or clicks cancel
#            break
#        if event == 'Start File':
#            print(f"event structure: {values}")
#            reader = read_with_IO(values['-FILE_NAME-'])
#            window.close()
#
#            break
#        if event == 'Start Folder':
#            list_file=glob.glob(os.path.join(values[1], '*.wcp'))
#            FREC, FTIME, sampling = load_wcp(list_file[0])
#            for file in list_file [1:]:
#                REC, TIME, sampling = load_wcp(file)
#                FREC = np.append(FREC,REC, axis = 0)
#            FREC  = np.transpose(FREC)
#            FTIME = np.transpose(FTIME)
#            columns = [f"Trace-{x}" for x in range(len(FREC[1]))]
#            RECORDINGS = pd.DataFrame(FREC, index = FTIME[:,0], columns = columns)
#            window.close()
#            break
#    window.close()
#    return reader


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
    show_data(file_path)
    
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
