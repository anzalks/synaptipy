# -*- coding: utf-8 -*-
"""
Created on Fri Aug  9 12:44:57 2024

@author: Philippe.ISOPE
"""
import neo
import numpy as np 
import os
import glob
import pandas as pd
import PySimpleGUI as sg


def load_wcp(file_wcp):
    REC = []
    TIME = []
    my_file = neo.io.WinWcpIO(file_wcp)
    bl = my_file.read_block()
    for episode in bl.segments :
        time = episode.analogsignals[0].times #The time vector
        TIME.append(time)
        rec = episode.analogsignals[0].magnitude #The signal vector 
        REC.append(rec) 
    sampling = episode.analogsignals[0].sampling_rate # sampling is in Hz
    REC = np.squeeze(REC, axis=None)
    TIME = np.squeeze(TIME, axis=None)
    return REC, TIME, sampling
  
def load_files():
    sg.theme('DarkBlue')	
    
    layout= [  [sg.Text('Enter File name     '), sg.InputText(), sg.FileBrowse(),sg.Button('Start File')],
                [sg.Text('Enter Folder name '), sg.InputText(), sg.FolderBrowse(),sg.Button('Start Folder')]]
    
    window= sg.Window('Load files', layout, modal = True, location=(10,10))
    
    while True:
        event, values = window.read()
        if event in (None, 'Close'):	# if user closes window or clicks cancel
            break
        if event == 'Start File':
            REC, TIME, sampling = load_wcp(values[0])
            REC  = np.transpose(REC)
            TIME = np.transpose(TIME)
            columns = [f"Trace-{x}" for x in range(len(REC[1]))]
            RECORDINGS = pd.DataFrame(REC, index = TIME[:,0], columns = columns)
            window.close()

            break
        if event == 'Start Folder':
            list_file=glob.glob(os.path.join(values[1], '*.wcp'))
            FREC, FTIME, sampling = load_wcp(list_file[0])
            for file in list_file [1:]:
                REC, TIME, sampling = load_wcp(file)
                FREC = np.append(FREC,REC, axis = 0)
            FREC  = np.transpose(FREC)
            FTIME = np.transpose(FTIME)
            columns = [f"Trace-{x}" for x in range(len(FREC[1]))]
            RECORDINGS = pd.DataFrame(FREC, index = FTIME[:,0], columns = columns)
            window.close()
            break

    window.close() 
    return RECORDINGS, sampling

if __name__ == '__main__' :
    RECORDINGS, sampling = load_files()