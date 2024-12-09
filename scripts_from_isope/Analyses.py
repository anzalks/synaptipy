# -*- coding: utf-8 -*-
"""
Created on Thu Aug 22 15:34:06 2024

@author: Philippe.ISOPE
"""

import numpy as np
import pandas as pd
from matplotlib import pyplot as plt 
from scipy.optimize import curve_fit


##############################
### AVERAGE
############################# 

def Make_average(RECORDINGS,Tagged):
    Transposed = RECORDINGS.T 
    Transposed['Tagged'] = Tagged   
    TAG1 = Transposed[Transposed['Tagged'] == 1]
    Average = TAG1.mean(axis = 0)
    Average = Average.T
    Average = Average.iloc[:-1]
    fig2 = plt.figure()
    ax2 = fig2.add_subplot(111)
    ax2.plot(Average)
    plt.xlabel('Time (s)')
    plt.ylabel('Signal (Amp)')
    return Average

##############################
### FIT
#############################    

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

def func_mono_exp(x, a, b, c, d):
    return a * np.exp(-(x-b)/c) + d


##############################
## CALCULATE AMPLITUDES ##
##############################    
    
def calc_min_in_trace(trace, start, stop, pts_for_mean):   # start et stop in seconds and win_for_extremum in points
    Slice_index = np.where((trace.index > start) & (trace.index < stop))
    MIN = np.min(trace.iloc[Slice_index])
    Slice_index = np.squeeze(Slice_index)
    MIN_trace_idx = np.argmin(trace.iloc[Slice_index])
    MIN = np.mean(trace.iloc[(Slice_index[0] + MIN_trace_idx - pts_for_mean):(Slice_index[0] + MIN_trace_idx  + pts_for_mean)])
    MIN_idx=Slice_index[0] + MIN_trace_idx
    return MIN, MIN_idx

def calc_max_in_trace(trace, start, stop, pts_for_mean):
    Slice_index = np.where((trace.index > start) & (trace.index < stop))
    MAX = np.max(trace.iloc[Slice_index])
    Slice_index = np.squeeze(Slice_index)
    MAX_trace_idx = np.argmax(trace.iloc[Slice_index])
    MAX = np.mean(trace.iloc[(Slice_index[0] + MAX_trace_idx - pts_for_mean):(Slice_index[0] + MAX_trace_idx  + pts_for_mean)])
    MAX_idx=Slice_index[0] + MAX_trace_idx
    return MAX, MAX_idx

def calculate_amplitudes(RECORDINGS,Tagged, start, stop, N_win, ISI,pts_for_mean, Min):
    amp_dict = {}
    amp_dict_idx = {}

    for i in range(N_win):
        amp_dict['AMP' + str(i+1)] = []
        amp_dict_idx['AMP' + str(i+1)] = []
    
    for key in amp_dict.keys():    
        for column in RECORDINGS:
           if Min == True:
               if Tagged[i] == 1:
                   local_amp, local_amp_idx =calc_min_in_trace(RECORDINGS[column],start,stop,pts_for_mean)
                   amp_dict[key].append(local_amp)
                   amp_dict_idx[key].append(local_amp_idx)
           else:
               if Tagged[i] == 1:
                   local_amp, local_amp_idx =calc_max_in_trace(RECORDINGS[column],start,stop,pts_for_mean)
                   amp_dict[key].append(local_amp)
                   amp_dict_idx[key].append(local_amp_idx)
       
        start+=float(ISI)
        stop+=float(ISI)
    
    fig4 = plt.figure()
    ax4 = fig4.add_subplot(111)
    for key in amp_dict.keys():
        ax4.plot(amp_dict[key], label = key)
    ax4.legend()
    plt.xlabel('Number episodes')
    plt.ylabel('Signal (Amp)')
    plt.title('Amplitude Timecourse')   
    
    Amps = pd.DataFrame.from_dict(amp_dict)
    return Amps


