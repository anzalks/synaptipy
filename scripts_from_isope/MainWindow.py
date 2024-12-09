# -*- coding: utf-8 -*-
"""
Created on Mon Aug 19 22:33:17 2024

@author: Philippe.ISOPE
"""

import glob
import os
from matplotlib.backend_bases import MouseButton
import PySimpleGUI as sg
import numpy as np
from matplotlib import pyplot as plt
from scipy.signal import savgol_filter
from elephant import signal_processing 
import quantities as pq
import scipy.signal
from scipy.optimize import curve_fit
import pandas as pd
import OpenFiles
import MoveTraces
import Analyses 


savedir = os.getcwd()

def MainWindow():
     sg.theme('SandyBeach')	
     
     sg.theme('SandyBeach')	
     
     layout = [ [sg.Frame(' Explore Traces ',[[sg.Button('Open File'),
                                               sg.Button('Previous Trace'),
                                               sg.Button('Next Trace'),
                                               sg.Button('Clear')],
                                              [sg.Button('Superimposed'),
                                               sg.Button('Go to'), 
                                               sg.InputText(default_text="0", 
                                                            size=(4, 1))]],
                           relief="ridge", border_width= 5,size=(500, 90), expand_x=True, expand_y=True)],
                 [sg.Frame(' Adjust Traces ',[[sg.Button('Leak Subtraction'), sg.Button('Undo'), sg.Text('Window (ms)'),sg.InputText(default_text="0", size=(4, 1)),
                                               sg.InputText(default_text="10", size=(11, 1))]],
                           relief="groove", border_width= 5,size=(500, 50),expand_x=True, expand_y=True)],
                 
                 [sg.Frame(' Filter Traces ',[[sg.Button('Smooth Traces'),sg.Text('Odd number'), sg.InputText(default_text="19", size=(12, 1))],
                   [sg.Button('Filter'),sg.Text('Band-Pass(Hz)'),sg.InputText(default_text="0.01", size=(5, 1)),sg.InputText(default_text="2000", size=(5, 1)), 
                    sg.Button('Undo')]],
                           relief="groove", border_width= 5, size=(500, 90),expand_x=True, expand_y=True)],
                 
                 [sg.Frame(' Select Traces ',[[sg.Button('Tag'), sg.Button('UnTag'), sg.Button('Tag All'), sg.Button('UnTag All')]],
                           relief="groove", border_width= 5, size=(500, 50), expand_x=True, expand_y=True)],
                 [sg.Frame(' Average ',[[sg.Button('Averaged Tagged Traces')]],
                           relief="groove", border_width= 5, size=(500, 50), expand_x=True, expand_y=True)],
                 [sg.Frame(' Calculate Amplitudes ',[[sg.Text('Win 1 (sec)'),sg.InputText(default_text="0.4", size=(4,1)),sg.InputText(default_text="0.6", size=(4, 1)),sg.Text('N Peak'),
                                                      sg.InputText(default_text="1", size=(3, 1)),sg.Text('ISI'),sg.InputText(default_text="0.05", size=(4, 1)),
                                                      sg.Text('Span pts'),sg.InputText(default_text="5", size=(3, 1))],
                                                     [sg.Checkbox('Min', size=(5, 1), default=True),sg.Checkbox('With grid', size=(10, 1), default=False), sg.Button('Load grid'),sg.Button('Go')]],
                           relief="groove", border_width= 5, size=(500, 80), expand_x=True, expand_y=True)],
                
                 [sg.Frame(' Fitting ',[[sg.Button('Fit current trace'),sg.Button('Fit all traces'), sg.Button('Fit average')],
                                        [sg.Button('Fit current train'),sg.Button('Fit all trains'),sg.Text('Peak number'),sg.InputText(default_text="3", size=(4, 1)),sg.Text('ISI (ms)'), sg.InputText(default_text="50", size=(4, 1))],
                                         [sg.Button('Remove residuals in current train'), sg.Button('Remove all residuals')]],
                           relief="groove", border_width= 5, size=(500, 150), expand_x=True, expand_y=True)],
                 [sg.Frame(' Save stuff ',[[sg.Button('Save Tag'), sg.Button('Save Dataframe'), sg.Button("Save Amplitudes"), sg.InputText(default_text="Avg", size=(5, 1)), sg.Button("Save Average")]],
                           relief="groove", border_width= 5, size=(500, 50), expand_x=True, expand_y=True)]]     
    
     return sg.Window('Data analysis', layout, location=(0,0), resizable=True)
 
    
def Main():
        
    plt.ion()
    RECORDINGS = None
    sampling = None


    window1 = MainWindow()
    while True:
        event, values = window1.read()
#        try:
           
        if event in (None, 'Close'):	# if user closes window or clicks cancel
           break
       
        if event == "Open File":
           RECORDINGS, sampling = OpenFiles.load_files()
           fig = plt.figure('Main Figure')
           episode_number = len(RECORDINGS.columns)
           Tagged = np.zeros(episode_number)
           episode=0
           ax = fig.add_subplot(111)
           ax.plot(RECORDINGS['Trace-0'])
           plt.xlabel('Time (s)')
           plt.ylabel('Signal (Amp)')
           plt.title('Episode '+str(episode)+'/'+str(episode_number-1), fontweight="bold", fontsize=16, color="g")
           
        if event == "Previous Trace":
           ax.clear()
           episode = MoveTraces.previous_trace(episode, episode_number, Tagged, RECORDINGS, ax)   
                       
        if event == "Next Trace":
           ax.clear()
           episode = MoveTraces.next_trace(episode, episode_number, Tagged, RECORDINGS, ax)
           
        if event == "Clear":
           ax.clear()
           plt.draw()
           
        if event == "Go to":
           ax.clear()
           episode = int(values[0])-1 
           episode = MoveTraces.next_trace(episode, episode_number, Tagged, RECORDINGS, ax)
       
        if event == "Leak Subtraction": 
           Saved_REC=RECORDINGS.copy()
           for column in RECORDINGS:
               leak = np.mean(RECORDINGS[column][int(float(values[1])/sampling):int(float(values[2])/sampling)])
               RECORDINGS[column]=RECORDINGS[column]-leak 

        if event == "Undo": 
           RECORDINGS=Saved_REC.copy()
              
        if event == "Smooth Traces": 
            Saved_REC=RECORDINGS.copy()
            for column in RECORDINGS:
               RECORDINGS[column] = savgol_filter(np.squeeze(RECORDINGS[column]), int(values[3]), 2) # Filter: window size 19, polynomial order 2   
                     
        if event == "Filter": 
            Saved_REC=RECORDINGS.copy()
            for column in RECORDINGS:
               RECORDINGS[column]=signal_processing.butter(np.array(RECORDINGS[column]), float(values[4])* pq.Hz, float(values[5])* pq.Hz, order = 4, filter_function='sosfiltfilt', sampling_frequency= float(sampling)* pq.Hz, axis= 0)
             
        if event == "Tag":
           Tagged[episode]=int(1)
    
        if event == "UnTag":
           Tagged[episode]=int(0)
     
        if event == "Tag All":
           Tagged = [1 for i in range(len(Tagged))]
       
        if event == "UnTag All":
           Tagged = [0 for i in range(len(Tagged))]   
                       
        if event == "Averaged Tagged Traces":
           Averaged_Traces = Analyses.Make_average(RECORDINGS,Tagged)

        if event == 'Go':
           Amplitudes = Analyses.calculate_amplitudes(RECORDINGS,Tagged, float(values[6]), float(values[7]), int(values[8]),float(values[9]), int(values[10]), bool(values[11]))   
           
        #if event == 'With grid':   

        # if event == 'Fit current trace':    
        #    local_tau, local_popt, idxstart, idxstop = Fit_single_trace(REC[episode], TIME[episode],startpos[0],endpos[0])
        #    x=TIME[episode][idxstart:idxstop]
        #    x2=np.array(np.squeeze(x))
        #    fig_fit=plt.figure()
        #    ax_fit = fig_fit.add_subplot(111)
        #    ax_fit.plot(TIME[episode], REC[episode], color = 'green', alpha = 1, lw = '2')
        #    ax_fit.plot(x2, func_mono_exp(x2, *local_popt), color = 'black', alpha = 1, lw = '3')
        #    print ('tau decay episode'+str(episode)+' =',local_popt[2]*1000, ' ms' )
           
        # if event == 'Fit all traces':    
        #    All_Tau=[]
        #    All_popt=[]
        #    for i in range(len(REC)): 
        #        if TAG[i] == 1:
        #            local_tau, local_popt, idxstart, idxstop = Fit_single_trace(REC[i], TIME[i],startpos[0],endpos[0])
        #            All_Tau.append(local_tau)
        #            All_popt.append(local_popt)
        #        else:
        #            pass
        #    data = {'Tau': np.array(All_Tau)}
        #    df = pd.DataFrame.from_dict(data)
        #    writer = pd.ExcelWriter('{}\All Tau AMP1.xlsx'.format(savedir))
        #    df.to_excel(writer)
        #    writer.save() 
                     
        # if event == 'Fit average':    
        #    local_tau, local_popt, idxstart, idxstop = Fit_single_trace(AVERAGE, TIME[0],startpos[0],endpos[0])
        #    x=TIME[episode][idxstart:idxstop]
        #    x2=np.array(np.squeeze(x))
        #    fig_fit=plt.figure()
        #    ax_fit = fig_fit.add_subplot(111)
        #    ax_fit.plot(TIME[0], AVERAGE, color = 'green', alpha = 1, lw = '2')
        #    ax_fit.plot(x2, func_mono_exp(x2, *local_popt), color = 'black', alpha = 1, lw = '3')
        #    print ('tau decay average'+str(episode)+' =',local_popt[2]*1000, ' ms' )
               
    
                       
        # if event == 'Fit all trains':  
        #    FitPeaks_dict_tau = {}
        #    FitPeaks_dict_popt = {}
        #    locals().update(FitPeaks_dict_tau) 
        #    locals().update(FitPeaks_dict_popt)
           
        #    for i in range(int(values[8])):
        #        FitPeaks_dict_tau['AMP' + str(i+1)] = []
        #        FitPeaks_dict_popt['AMP' + str(i+1)] = []
            
        #    Start_for_trains=startpos[0]
        #    Stop_for_trains=endpos[0]
           
        #    for key in FitPeaks_dict_popt.keys():
        #        for i in range(len(REC)):
        #            print(key,'  episode: ', i)
        #            if TAG[i] == 1: 
        #                local_tau, local_popt, idxstart, idxstop = Fit_single_trace(REC[i], TIME[i],Start_for_trains,Stop_for_trains)
        #                FitPeaks_dict_tau[key].append(local_tau)
        #                FitPeaks_dict_popt[key].append(local_popt) 
    
        #            else:
        #                pass
        #        Start_for_trains+=float(values[9])/1000
        #        Stop_for_trains+=float(values[9])/1000
       
       
        #    df = pd.DataFrame.from_dict(FitPeaks_dict_tau)
        #    writer = pd.ExcelWriter('{}\Fit peaks dict tau.xlsx'.format(savedir))
        #    df.to_excel(writer)
        #    writer.save() 
        #    df2 = pd.DataFrame.from_dict(FitPeaks_dict_popt)
        #    writer = pd.ExcelWriter('{}\Fit peaks dict popt.xlsx'.format(savedir))
        #    df2.to_excel(writer)
        #    writer.save() 
           
        # if event == 'Fit current train':  
           
        #    FitPeaks_dict_tau = {}
        #    FitPeaks_dict_popt = {}
        #    locals().update(FitPeaks_dict_tau) 
        #    locals().update(FitPeaks_dict_popt)
           
        #    for i in range(int(values[8])):
        #        FitPeaks_dict_tau['AMP' + str(i+1)] = []
        #        FitPeaks_dict_popt['AMP' + str(i+1)] = []
            
           
        #    Start_for_trains=startpos[0]
        #    Stop_for_trains=endpos[0]
           
        #    fig_fit=plt.figure()
        #    ax_fit = fig_fit.add_subplot(111)
        #    ax_fit.plot(TIME[episode], REC[episode], color = 'green', alpha = 1, lw = '2')
           
        #    for key in FitPeaks_dict_popt.keys(): 
        #        tau, popt, idxstart, idxstop = Fit_single_trace(REC[episode], TIME[episode],Start_for_trains,Stop_for_trains)
        #        FitPeaks_dict_tau[key].append(tau)
        #        FitPeaks_dict_popt[key].append(popt) 
        #        Start_for_trains+=float(values[9])/1000
        #        Stop_for_trains+=float(values[9])/1000
        #        x=TIME[episode][idxstart:idxstop]
        #        x2=np.array(np.squeeze(x))
        #        ax_fit.plot(x2, func_mono_exp(x2, *popt), color = 'black', alpha = 1, lw = '3')
               
        #    print (FitPeaks_dict_tau)  
           
      
           
        # if event == 'Remove residuals in current train':
        #    amp_dict_corr = {}
        #    print ('Episode', episode)
        #    locals().update(amp_dict_corr)
        #    for i in range(int(values[8])):
        #        amp_dict_corr['AMP' + str(i+1)] = []
                
        #    for key in amp_dict_corr.keys():
        #        if key == 'AMP1':
        #            amp_dict_corr[key].append(amp_dict[key][episode])
        #            print ('AMP1 =', amp_dict[key][episode])
        #        else:
        #            key_for_residual='AMP' + str(int(key[3:])-1)
        #            index_peak_key=amp_dict_idx[key][episode]
        #            residual = func_mono_exp(float(TIME[episode][index_peak_key]), *FitPeaks_dict_popt[key_for_residual][0])
        #            new_amp = amp_dict[key][episode]-residual
        #            amp_dict_corr[key].append(new_amp)
        #            print ('new',key,' = ',new_amp)
                   
                                         
           
        # if event == 'Remove all residuals':
        #    amp_dict_corr = {}
        #    locals().update(amp_dict_corr)  
        #    for i in range(int(values[8])):
        #        amp_dict_corr['AMP' + str(i+1)] = []
          
           
        #    for key in amp_dict_corr.keys():
        #         for i in range(len(REC)):
        #            if TAG[i] == 1: 
        #                if key == 'AMP1':
        #                    amp_dict_corr[key].append(amp_dict[key][i])
                           
        #                else:
        #                    key_for_residual='AMP' + str(int(key[3:])-1)
        #                    index_peak_key=amp_dict_idx[key][i]
        #                    residual = func_mono_exp(float(TIME[i][index_peak_key]), *FitPeaks_dict_popt[key_for_residual][i])
        #                    new_amp=amp_dict[key][i]-residual
        #                    amp_dict_corr[key].append(new_amp)
        #            else:
        #                pass        #                                locals().update(amp_dict_corr)                            
           
        #    fig5 = plt.figure()
        #    ax5 = fig5.add_subplot(111)
        #    for key in amp_dict_corr.keys():
        #        ax5.plot(amp_dict_corr[key], label = key)
        #    ax5.legend()
        #    plt.xlabel('Number episodes')
        #    plt.ylabel('Signal (Amp)')
        #    plt.title('Corrected Amplitude Timecourse')  
           
        #    df = pd.DataFrame.from_dict(amp_dict_corr)
        #    writer = pd.ExcelWriter('{}\Amplitudes_corr.xlsx'.format(savedir))
        #    df.to_excel(writer)
        #    writer.save()
        
        if event == "Save Dataframe":
           RECORDINGS.to_excel('{}\RECORDINGS.xlsx'.format(savedir))
        
        if event == "Save Tag":
           Tagged.to_excel('{}\Tags.xlsx'.format(savedir))

        if event == "Save Average":
           Averaged_Traces.to_excel('{}\{}.xlsx'.format(savedir,str(values[9])))
        
        if event == "Save Amplitudes":
             Amplitudes.to_excel('{}\Amplitudes.xlsx'.format(savedir))
            
        
           
           
# #        except:
#             sg.popup_error('')
#             pass
    print (values)       
    window1.close()
    return RECORDINGS




if __name__ == '__main__' :
   
     RECORDINGS = Main()
