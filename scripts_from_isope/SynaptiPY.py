# -*- coding: utf-8 -*-
"""
Created on Thu Jan 14 00:01:39 2021

@author: Theo.ROSSI
"""


# install openpyxl

###############################
### DEF LOAD FILE  ############
###############################

def load_wcp(file_wcp, channel):
    my_file = neo.io.WinWcpIO(file_wcp)
    bl = my_file.read_block()
    TIME = bl.segments[0].analogsignals[channel].times
    REC=[]
    for episode in bl.segments :
        rec = np.array(episode.analogsignals[channel][:,0].magnitude) #The signal vector 
        REC.append(rec) 
    REC=np.squeeze(REC)
    if REC.ndim == 1:
        REC=REC[np.newaxis,:]
    return REC, TIME
        
def load_folder(path, channel):
    list_file=glob.glob(os.path.join(path, '*.wcp'))
    print (list_file)
    for i in range(len(list_file)):
       load_wcp(list_file[i], channel)
  
def load_xls(file_xls, REC):
    df=pd.read_excel (file_xls, sheet_name = 'Traces DF_F0', header = 0)
    for i in range(len(df.columns)):
        if 'Time' == df.columns[i]:
            TIME=df.iloc[:,i].values
        else:
            sweep=df.iloc[:,i].values
            REC.append(sweep)
    return REC, TIME   

###############################
## DEF GET COORDINATE CURSORS #
###############################

def on_click(event):
    global startpos, endpos
    if event.button is MouseButton.LEFT:
        startpos=[event.xdata]
    elif event.button is MouseButton.RIGHT:
        endpos=[event.xdata]
     
 ###############################
## DEF FILTERS #
###############################       
 
def filter_signal(signal, order, sample_rate, freq_low, freq_high, axis=0):
    Wn = [freq_low / (sample_rate / 2), freq_high / (sample_rate / 2)]
    sos_coeff = scipy.signal.iirfilter(order, Wn, btype="band", ftype="butter", output="sos")
    filtered_signal = scipy.signal.sosfiltfilt(sos_coeff, signal, axis=axis)

    return filtered_signal


#def notch_filter(signal, order=8, sample_rate=20000, freq_low=48, freq_high=52, axis=0):
#    Wn = [freq_low / (sample_rate / 2), freq_high / (sample_rate / 2)]
#    notch_coeff = signal.iirfilter(order, Wn, btype="bandstop", ftype="butter", output="sos")
#    notch_signal = signal.sosfiltfilt(notch_coeff, signal, axis=axis)
#
#    return notch_signal
       
#############################
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
        param_bounds=([-np.inf,0.,0.,0.],[np.inf,1.,10.,1000.])      # be careful ok for seconds. If millisec change param 2 and 3
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

#def func_line(x, a, b):
#    return a * x + b    
#
#def func_dbl_exp(x, a, b, c, d, e):
#    return a * np.exp(-x/b) + c * np.exp(-x/d)+e
#
#def func_lognormal(x, a, b, c, d):    
#    pass
    


    
###############################
### DEF AVERAGE  ############
###############################

def Make_average(REC,TIME,CursorOn):
    global AVERAGE
    global TAGREC

    
    for i in range(len(REC)):
        if TAG[i]==1:
            TAGREC.append(REC[i])
    AVERAGE = np.mean(TAGREC,axis = 0)
    if CursorOn == True:
        min_avg=calc_min_in_trace(AVERAGE, startpos[0], endpos[0], 5)
        max_avg=calc_max_in_trace(AVERAGE, startpos[0], endpos[0], 5)
    
    fig2 = plt.figure()
    ax2 = fig2.add_subplot(111)
    ax2.plot(TIME[0], AVERAGE)
    plt.xlabel('Time (s)')
    plt.ylabel('Signal (Amp)')
    plt.draw()
    
    if CursorOn == True:
        plt.title('Average: min = '+str(min_avg)+'   max = '+str(max_avg)+'    (Close me)',fontweight="bold", fontsize=12, color="g")
    else:
        plt.title('Average (CLOSE ME)')
#

##########################
# DEF Mode superimposed ##
##########################

def superimposed(episode):
    global REC
    global TIME
    global startpos
    global endpos
    sg.theme('Black')	
 
    layout2 = [ [sg.Text('Superimposed Episodes')],
                [sg.Button('Start'), sg.Button('Close', button_color=('red', 'white'))],
                [sg.Button('Previous Trace'),sg.Button('Next Trace'),sg.Button('Clear')],
                [sg.Text('Go To (Push start)'), sg.InputText(default_text="0", size=(10, 1))]]
    
    window2 = sg.Window('Display Superimposed Traces', layout2, location=(0,110))
    episode = episode
    
    fig_super = plt.figure()
    ax_super = fig_super.add_subplot(111)
    ax_super.plot(TIME[episode], REC[episode])
    plt.xlabel('Time (s)')
    plt.ylabel('Signal (Amp)')
    plt.title('Episode '+str(episode)+'/'+str(len(REC)-1)) 
    
    while True:
        
        event2, values2 = window2.read()
        try:
           
            if event2 in (None, 'Close'):	# if user closes window or clicks cancel
                break
    
            if event2 == "Next Trace":
                episode+=1
                ax_super.plot(TIME[episode], REC[episode])
                try:
                    ax_super.axvline(startpos[0], color ='r')
                    ax_super.axvline(endpos[0], color ='g')
                    fig_super.canvas.draw()
                except:
                    pass
                plt.xlabel('Time (s)')
                plt.ylabel('Signal (Amp)')
                plt.title('Episode: '+str(episode))
                plt.draw()
     
            if event2 == "Previous Trace":
                episode-=1
                ax_super.plot(TIME[episode], REC[episode])
                try:
                    ax_super.axvline(startpos[0], color ='r')
                    ax_super.axvline(endpos[0], color ='g')
                    fig_super.canvas.draw()
                except:
                    pass
                plt.xlabel('Time (s)')
                plt.ylabel('Signal (Amp)')
                plt.title('Episode: '+str(episode))
                plt.draw()
     
            if event2 == "Start":
                ax_super.clear()
                try:
                    episode=int(values2[0])
                except:
                    episode=0
                ax_super.plot(TIME[episode], REC[episode])
                plt.xlabel('Time (s)')
                plt.ylabel('Signal (Amp)')
                plt.title('Episode: '+str(episode))
                plt.draw()
    
            if event2 == "Clear":
                ax_super.clear()
                               

        except:
            sg.popup_error('')
            pass
   
    window2.close()
    plt.close(fig_super)

    
##############################
## FUNCTIONS TO CALCULATE AMPLITUDES ##
##############################    
    
def calc_min_in_trace(trace, win1, win2, Win_for_extremum):
    start_idx = np.ravel(np.where(TIME[0] >= win1))[0]
    stop_idx = np.ravel(np.where(TIME[0] >= win2))[0]
    MIN = np.min(trace[start_idx:stop_idx])
    sub_trace=trace[start_idx:stop_idx]
    MIN_sub_trace_idx = np.argmin(sub_trace)
    MIN = np.mean(trace[start_idx+MIN_sub_trace_idx-Win_for_extremum:start_idx+MIN_sub_trace_idx+Win_for_extremum])
    MIN_idx=start_idx+MIN_sub_trace_idx
    return MIN, MIN_idx

def calc_max_in_trace(trace, win1, win2, Win_for_extremum):
    start_idx = np.ravel(np.where(TIME[0] >= win1))[0]
    stop_idx = np.ravel(np.where(TIME[0] >= win2))[0]
    MAX = np.max(trace[start_idx:stop_idx])
    sub_trace=trace[start_idx:stop_idx]
    MAX_sub_trace_idx = np.argmax(sub_trace)
    MAX = np.mean(trace[start_idx+MAX_sub_trace_idx-Win_for_extremum:start_idx+MAX_sub_trace_idx+Win_for_extremum])
    MAX_idx=start_idx+MAX_sub_trace_idx
    return MAX,MAX_idx


def Calculate_Amps():
    
    global amp_dict
    global amp_dict_idx
    global REC
    global TIME
    global TAG
    
    sg.theme('Black')	
 
    layout3 = [ [sg.Text('FIND PEAKS (Tagged)',font = ('Arial', 14, 'bold') )],
                [sg.Text('_'*30)], 
                [sg.Checkbox('Minimum', size=(12, 1), default=True)], 
                [sg.Text('_'*30)],
                [sg.Button('One Peak from Cursors')],
                [sg.Text('_'*30)],
                [sg.Button('All Peaks from Trains')],
                [sg.Text('ISI (ms)'), sg.InputText(default_text="50", size=(10, 1))],
                [sg.Text('Peak number'), sg.InputText(default_text="3", size=(10, 1))],
                [sg.Text('_'*30)],
                [sg.Text('Span for peaks (+/-)'), sg.InputText(default_text="5", size=(10, 1))],
                [sg.Text('_'*30)],
                [sg.Text('Save as'),sg.InputText(default_text="Amplitudes", size=(10, 1))],
                [sg.Text('_'*30)],
                [sg.Button('Some stats from Amplitudes')]]
#                [sg.Text('_'*30)],
#                [sg.Text(''*30)],
#                [sg.Button('Close_Amp', button_color=('black', 'white'))]]
    
    window3 = sg.Window('Amplitudes', layout3, location=(0,110), size=(250,500))
       
    while True:
        
        event3, values3 = window3.read()
        try:
           
            if event3 in (None, 'Close_Amp'):	# if user closes window or clicks cancel
                break
            
            if event3 == "One Peak from Cursors":
                amp_dict['AMP1'] = []
                amp_dict_idx['AMP1'] = []
                locals().update(amp_dict)
                locals().update(amp_dict_idx)
                
                for i in range(len(REC)):
                    if values3[0] == True:
                        if TAG[i] == 1:
                            local_amp, local_amp_idx =calc_min_in_trace(REC[i], startpos[0], endpos[0], int(values3[3]))
                            amp_dict['AMP1'].append(local_amp)
                            amp_dict_idx['AMP1'].append(local_amp_idx)
                    else:
                        if TAG[i] == 1:
                            local_amp, local_amp_idx =calc_max_in_trace(REC[i], startpos[0], endpos[0], int(values3[3]))
                            amp_dict['AMP1'].append(local_amp) 
                            amp_dict_idx['AMP1'].append(local_amp_idx)
                
                fig4 = plt.figure()
                ax4 = fig4.add_subplot(111)
                ax4.plot(amp_dict['AMP1'])
                plt.xlabel('Number episodes')
                plt.ylabel('Signal (Amp)')
                plt.title('Amplitude Timecosurse')
                
                df = pd.DataFrame.from_dict(amp_dict)
                writer = pd.ExcelWriter('{}\{}.xlsx'.format(savedir,str(values3[4])))
                df.to_excel(writer)
                writer.save() 
                

            if event3 == "All Peaks from Trains":
                amp_dict = {}
                amp_dict_idx = {}
                locals().update(amp_dict) 
                locals().update(amp_dict_idx) 
                   
                for i in range(int(values3[2])):
                    amp_dict['AMP' + str(i+1)] = []
                    amp_dict_idx['AMP' + str(i+1)] = []
                
                Start_for_trains=startpos[0]
                Stop_for_trains=endpos[0]
                for key in amp_dict.keys():                          
                    for i in range(len(REC)):
                        if values3[0] == True:
                            if TAG[i] == 1:
                                local_amp, local_amp_idx =calc_min_in_trace(REC[i],float(Start_for_trains), float(Stop_for_trains),int(values3[3]))
                                amp_dict[key].append(local_amp)
                                amp_dict_idx[key].append(local_amp_idx)
                        else:
                            if TAG[i] == 1:
                                local_amp, local_amp_idx =calc_max_in_trace(REC[i],float(Start_for_trains), float(Stop_for_trains),int(values3[3]))
                                amp_dict[key].append(local_amp)
                                amp_dict_idx[key].append(local_amp_idx)
                   
                    Start_for_trains+=float(values3[1])/1000
                    Stop_for_trains+=float(values3[1])/1000
                
                fig4 = plt.figure()
                ax4 = fig4.add_subplot(111)
                for key in amp_dict.keys():
                    ax4.plot(amp_dict[key], label = key)
                ax4.legend()
                plt.xlabel('Number episodes')
                plt.ylabel('Signal (Amp)')
                plt.title('Amplitude Timecourse')    
             
                df = pd.DataFrame.from_dict(amp_dict)
                writer = pd.ExcelWriter('{}\{}.xlsx'.format(savedir,'amplitude'))  #str(values3[4])
                df.to_excel(writer)
                writer.save()
                
            if event3 == "Some stats from Amplitudes":
                df = pd.DataFrame.from_dict(amp_dict)  
                print ("\n")
                print('first values')
                print (df.head())
                print ("\n")
                print ('Basic stats')
                print (df.describe())
                print ("\n")
                print ('Pearson correlation')
                print (df.corr(method='pearson'))
                sns.pairplot(df)
                sns.jointplot(x=df.columns[0], y=df.columns[1], data=df, kind="reg")
                
        except:
            sg.popup_error('Tagged traces or cursors missing')
            pass
    window3.close()

"""   
###########################
##   MAIN WINDOW       ####
###########################
"""

    
def Main_window(REC, timescale):
    
    sg.theme('SandyBeach')	
    
    layout1 = [ [sg.Frame(' Init ',[[sg.Button('Start'),sg.Button('Previous Trace'),sg.Button('Next Trace'),sg.Button('Clear')],
                                     [sg.Button('Superimposed'),sg.Text('Go To (Push start)'), sg.InputText(default_text="0", size=(10, 1))]],relief="ridge", border_width= 5,size=(500, 150))],
                [sg.Frame(' Adjust Traces ',[[sg.Button('Leak Subtraction'), sg.Button('Bleaching correction')],
                                     [sg.Text('Window (ms)'),sg.InputText(default_text="0", size=(10, 1)),sg.InputText(default_text="10", size=(11, 1)),sg.Button('Undo')]],relief="groove", border_width= 5,size=(500, 150))],
                [sg.Frame(' Filter Traces ',[[sg.Button('Smooth Traces'),sg.Text('Odd number'), sg.InputText(default_text="19", size=(12, 1))],
                  [sg.Button('Filter'),sg.Text('Band-Pass(Hz)'),sg.InputText(default_text="0.01", size=(10, 1)),sg.InputText(default_text="2000", size=(10, 1))]],relief="groove", border_width= 5, size=(500, 150))],
                [sg.Frame(' Select Traces ',[[sg.Button('Tag'), sg.Button('UnTag'), sg.Button('Tag All'), sg.Button('UnTag All'), sg.Button('Save Tags')]],relief="groove", border_width= 5, size=(500, 100))],
                [sg.Frame(' Average ',[[sg.Button('Averaged Tagged Traces'),sg.Checkbox('calc on cursors', size=(12, 1), default=False)],
                                        [sg.Button("Save Average"), sg.InputText(default_text="Avg", size=(10, 1))]],relief="groove", border_width= 5, size=(500, 150))],
                [sg.Frame(' Cursors and Amplitudes ',[[sg.Button('Select Cursors'),sg.Button('Draw Cursors'),sg.Text('Left/right click')],
                                        [sg.Button('Calculate Amps')]],relief="groove", border_width= 5, size=(500, 150))],
                [sg.Frame(' Fitting with cursors ',[[sg.Button('Fit current trace'),sg.Button('Fit all traces'), sg.Button('Fit average')],
                                        [sg.Button('Fit current train'),sg.Button('Fit all trains')],
                                        [sg.Text('Peak number'),sg.InputText(default_text="3", size=(10, 1)),sg.Text('ISI (ms)'), sg.InputText(default_text="50", size=(10, 1))],
                                        [sg.Button('Remove residuals in current train'), sg.Button('Remove all residuals')]],relief="groove", border_width= 5, size=(500, 180))]]
     
    window1 = sg.Window('Browse Traces', layout1, location=(0,0), resizable=True)    
    
    plt.ion()
    fig = plt.figure('Main Figure')
    ax = fig.add_subplot(111)
    
    episode=0
    
    TAG = np.zeros(len(REC))
    
    while True:
        
        event, values = window1.read()
        
#       try:
           
        if event in (None, 'Close'):	# if user closes window or clicks cancel
            break
        
        if event == "Start":
            ax.clear()
            try:
                episode=int(values[0])
            except:
                episode=0
            if TAG[episode] == 1:    
                ax.plot(timescale, REC[episode], color ='r')
            else:
                ax.plot(timescale, REC[episode])
                plt.xlabel('Time (s)')
                plt.ylabel('Signal (Amp)')
                plt.title('Episode '+str(episode)+'/'+str(len(REC)-1), fontweight="bold", fontsize=16, color="g")
                plt.draw()

        if event == "Clear":
            ax.clear()
            plt.draw()
        if event == "Next Trace":
            ax.clear()
            episode+=1
            if episode>(len(REC)-1):
                sg.popup_error('End of episodes')
                pass
            else:
                if TAG[episode] == 1:
                    ax.plot(timescale, REC[episode], color ='r')
                else:
                    ax.plot(timescale, REC[episode])
                try:
                    ax.axvline(startpos[0], color ='r')
                    ax.axvline(endpos[0], color ='g')
                    fig.canvas.draw()
                except:
                    pass
                try:
                    for key in amp_dict.keys():  
                        index=amp_dict_idx[key][episode]
                        x=timescale
                        y=amp_dict[key][episode]
                        ax.plot(x,y,'bo', linewidth = 3)
                except:
                    pass
                
                plt.xlabel('Time (s)')
                plt.ylabel('Signal (Amp)')
                plt.title('Episode '+str(episode)+'/'+str(len(REC)-1), fontweight="bold", fontsize=16, color="g")
                plt.draw()
 
        if event == "Previous Trace":
            ax.clear()
            episode-=1  
            if TAG[episode] == 1:
                ax.plot(timescale, REC[episode], color ='r')
            else:
                ax.plot(timescale, REC[episode])
            try:
                ax.axvline(startpos[0], color ='r')
                ax.axvline(endpos[0], color ='g')
                fig.canvas.draw()
            except:
                pass
            try:
                for key in amp_dict.keys():  
                    index=amp_dict_idx[key][episode]
                    x=timescale
                    y=amp_dict[key][episode]
                    ax.plot(x,y,'bo', linewidth = 3)
            except:
                pass
            plt.xlabel('Time (s)')
            plt.ylabel('Signal (Amp)')
            plt.title('Episode '+str(episode)+'/'+str(len(REC)-1), fontweight="bold", fontsize=16, color="g")
            plt.draw()
            
        if event == "Superimposed":
            superimposed(episode)

        if event == "Leak Subtraction": 
            Saved_REC=[]
            locals().update(Saved_REC)
            
            for i in range(len(REC)):
                Saved_REC.append(REC[i])
            for i in range(len(REC)):
                rec = REC[i]
                leak = np.mean(rec[int(float(values[1])/timescale[1]):int(float(values[2])/timescale[1])])
                REC[i]=REC[i]-leak 
        
        if event == "Bleaching correction": 
            xstart = float(values[1])/1000
            xstop = float(values[2])/1000
            Saved_REC=[]
            locals().update(Saved_REC)
            
            for i in range(len(REC)):
                Saved_REC.append(REC[i])
            for i in range(len(REC)):
                rec = REC[i]
                local_tau, local_popt, idxstart, idxstop = Fit_single_trace(rec, timescale, xstart,xstop)
                print (local_popt)
                try:
                    for j in range(len(REC[i])):
                        bleaching = func_mono_exp(timescale[j], *local_popt)
                        REC[i][j] -= bleaching
                except:
                    pass
                
        if event == "Smooth Traces": 
            Saved_REC=[]
            locals().update(Saved_REC)
            
            for i in range(len(REC)):
                Saved_REC.append(REC[i])
            for i in range(len(REC)):
                REC[i] = savgol_filter(np.squeeze(REC[i]), int(values[3]), 2) # Filter: window size 19, polynomial order 2   
                      
        if event == "Undo": 
            for i in range(len(REC)):
                REC[i]=Saved_REC[i]
        
        if event == "Filter": 
            Saved_REC=[]
            locals().update(Saved_REC)
            
            for i in range(len(REC)):
                Saved_REC.append(REC[i])
            for i in range(len(REC)):
                REC[i]=filter_signal(REC[i], 8, 1000*round(float(1/timescale[1])), float(values[4]), float(values[5]), axis=0)

    
        if event == "Tag":
            TAG[episode]=1
 
        if event == "UnTag":
            TAG[episode]=0
  
        if event == "Tag All":
            TAG= [1 for i in range(len(REC))]
       
        if event == "UnTag All":
            TAG= [0 for i in range(len(REC))]   

        if event == "Save Tags":
            df = pd.DataFrame(TAG, columns=['Tags'])
            writer = pd.ExcelWriter('{}\Tags.xlsx'.format(savedir))
            df.to_excel(writer, index = False)
            writer.save()
                        
        if event == "Averaged Tagged Traces":
            Make_average(REC,timescale,values[6])
        
        if event == "Save Average":
            df = pd.DataFrame(AVERAGE, columns=['Average'])
            writer = pd.ExcelWriter('{}\{}.xlsx'.format(savedir,str(values[7])))
            df.to_excel(writer, index = False)
            writer.save()

                
        if event == 'Select Cursors': 
            cid=fig.canvas.mpl_connect('button_press_event', on_click)
                              
        if event == 'Draw Cursors': 
            fig.canvas.mpl_disconnect(cid)
            try:
                ax.axvline(startpos[0], color ='r')
                ax.axvline(endpos[0], color ='g')
                fig.canvas.draw()
            except:
                pass
            
        if event == 'Calculate Amps':
            Calculate_Amps()
            
        if event == 'Fit current trace':    
            local_tau, local_popt, idxstart, idxstop = Fit_single_trace(REC[episode], TIME[episode],startpos[0],endpos[0])
            x=TIME[episode][idxstart:idxstop]
            x2=np.array(np.squeeze(x))
            fig_fit=plt.figure()
            ax_fit = fig_fit.add_subplot(111)
            ax_fit.plot(TIME[episode], REC[episode], color = 'green', alpha = 1, lw = '2')
            ax_fit.plot(x2, func_mono_exp(x2, *local_popt), color = 'black', alpha = 1, lw = '3')
            print ('tau decay episode'+str(episode)+' =',local_popt[2]*1000, ' ms' )
            
        if event == 'Fit all traces':    
            All_Tau=[]
            All_popt=[]
            for i in range(len(REC)): 
                if TAG[i] == 1:
                    local_tau, local_popt, idxstart, idxstop = Fit_single_trace(REC[i], TIME[i],startpos[0],endpos[0])
                    All_Tau.append(local_tau)
                    All_popt.append(local_popt)
                else:
                    pass
            data = {'Tau': np.array(All_Tau)}
            df = pd.DataFrame.from_dict(data)
            writer = pd.ExcelWriter('{}\All Tau AMP1.xlsx'.format(savedir))
            df.to_excel(writer)
            writer.save() 
                      
        if event == 'Fit average':    
            local_tau, local_popt, idxstart, idxstop = Fit_single_trace(AVERAGE, TIME[0],startpos[0],endpos[0])
            x=TIME[episode][idxstart:idxstop]
            x2=np.array(np.squeeze(x))
            fig_fit=plt.figure()
            ax_fit = fig_fit.add_subplot(111)
            ax_fit.plot(TIME[0], AVERAGE, color = 'green', alpha = 1, lw = '2')
            ax_fit.plot(x2, func_mono_exp(x2, *local_popt), color = 'black', alpha = 1, lw = '3')
            print ('tau decay average'+str(episode)+' =',local_popt[2]*1000, ' ms' )
                
 
                        
        if event == 'Fit all trains':  
            FitPeaks_dict_tau = {}
            FitPeaks_dict_popt = {}
            locals().update(FitPeaks_dict_tau) 
            locals().update(FitPeaks_dict_popt)
            
            for i in range(int(values[8])):
                FitPeaks_dict_tau['AMP' + str(i+1)] = []
                FitPeaks_dict_popt['AMP' + str(i+1)] = []
             
            Start_for_trains=startpos[0]
            Stop_for_trains=endpos[0]
            
            for key in FitPeaks_dict_popt.keys():
                for i in range(len(REC)):
                    print(key,'  episode: ', i)
                    if TAG[i] == 1: 
                        local_tau, local_popt, idxstart, idxstop = Fit_single_trace(REC[i], TIME[i],Start_for_trains,Stop_for_trains)
                        FitPeaks_dict_tau[key].append(local_tau)
                        FitPeaks_dict_popt[key].append(local_popt) 

                    else:
                        pass
                Start_for_trains+=float(values[9])/1000
                Stop_for_trains+=float(values[9])/1000

        
            df = pd.DataFrame.from_dict(FitPeaks_dict_tau)
            writer = pd.ExcelWriter('{}\Fit peaks dict tau.xlsx'.format(savedir))
            df.to_excel(writer)
            writer.save() 
            df2 = pd.DataFrame.from_dict(FitPeaks_dict_popt)
            writer = pd.ExcelWriter('{}\Fit peaks dict popt.xlsx'.format(savedir))
            df2.to_excel(writer)
            writer.save() 
            
        if event == 'Fit current train':  
            
            FitPeaks_dict_tau = {}
            FitPeaks_dict_popt = {}
            locals().update(FitPeaks_dict_tau) 
            locals().update(FitPeaks_dict_popt)
            
            for i in range(int(values[8])):
                FitPeaks_dict_tau['AMP' + str(i+1)] = []
                FitPeaks_dict_popt['AMP' + str(i+1)] = []
             
            
            Start_for_trains=startpos[0]
            Stop_for_trains=endpos[0]
            
            fig_fit=plt.figure()
            ax_fit = fig_fit.add_subplot(111)
            ax_fit.plot(TIME[episode], REC[episode], color = 'green', alpha = 1, lw = '2')
            
            for key in FitPeaks_dict_popt.keys(): 
                tau, popt, idxstart, idxstop = Fit_single_trace(REC[episode], TIME[episode],Start_for_trains,Stop_for_trains)
                FitPeaks_dict_tau[key].append(tau)
                FitPeaks_dict_popt[key].append(popt) 
                Start_for_trains+=float(values[9])/1000
                Stop_for_trains+=float(values[9])/1000
                x=TIME[episode][idxstart:idxstop]
                x2=np.array(np.squeeze(x))
                ax_fit.plot(x2, func_mono_exp(x2, *popt), color = 'black', alpha = 1, lw = '3')
            
            df = pd.DataFrame.from_dict(FitPeaks_dict_tau)
            writer = pd.ExcelWriter('{}\Fit peaks dict tau.xlsx'.format(savedir))
            df.to_excel(writer)
            writer.save() 
            df2 = pd.DataFrame.from_dict(FitPeaks_dict_popt)
            writer = pd.ExcelWriter('{}\Fit peaks dict popt.xlsx'.format(savedir))
            df2.to_excel(writer)
            writer.save() 
            
            print (FitPeaks_dict_tau)  
            
            
        if event == 'Remove residuals in current train':
            amp_dict_corr = {}
            print ('Episode', episode)
            locals().update(amp_dict_corr)
            for i in range(int(values[8])):
                amp_dict_corr['AMP' + str(i+1)] = []
                 
            for key in amp_dict_corr.keys():
                if key == 'AMP1':
                    amp_dict_corr[key].append(amp_dict[key][episode])
                    print ('AMP1 =', amp_dict[key][episode])
                else:
                    key_for_residual='AMP' + str(int(key[3:])-1)
                    index_peak_key=amp_dict_idx[key][episode]
                    residual = func_mono_exp(float(TIME[episode][index_peak_key]), *FitPeaks_dict_popt[key_for_residual][0])
                    new_amp = amp_dict[key][episode]-residual
                    amp_dict_corr[key].append(new_amp)
                    print ('new',key,' = ',new_amp)
                    
            df = pd.DataFrame.from_dict(amp_dict_corr)
            writer = pd.ExcelWriter('{}\Amplitudes_corr.xlsx'.format(savedir))
            df.to_excel(writer)
            writer.save()
            
            
        if event == 'Remove all residuals':
            amp_dict_corr = {}
            locals().update(amp_dict_corr)  
            for i in range(int(values[8])):
                amp_dict_corr['AMP' + str(i+1)] = []
           
            
            for key in amp_dict_corr.keys():
                 for i in range(len(REC)):
                    if TAG[i] == 1: 
                        if key == 'AMP1':
                            amp_dict_corr[key].append(amp_dict[key][i])
                            
                        else:
                            key_for_residual='AMP' + str(int(key[3:])-1)
                            index_peak_key=amp_dict_idx[key][i]
                            residual = func_mono_exp(float(TIME[i][index_peak_key]), *FitPeaks_dict_popt[key_for_residual][i])
                            new_amp=amp_dict[key][i]-residual
                            amp_dict_corr[key].append(new_amp)
                    else:
                        pass        #                                locals().update(amp_dict_corr)                            
            
            fig5 = plt.figure()
            ax5 = fig5.add_subplot(111)
            for key in amp_dict_corr.keys():
                ax5.plot(amp_dict_corr[key], label = key)
            ax5.legend()
            plt.xlabel('Number episodes')
            plt.ylabel('Signal (Amp)')
            plt.title('Corrected Amplitude Timecourse')  
            
            df = pd.DataFrame.from_dict(amp_dict_corr)
            writer = pd.ExcelWriter('{}\Amplitudes_corr.xlsx'.format(savedir))
            df.to_excel(writer)
            writer.save()
      
        # except:
        #     sg.popup_error('')
        #     pass
            
    window1.close()





if __name__ == '__main__' :    
    

    
    from matplotlib.backend_bases import MouseButton
    import PySimpleGUI as sg
    import glob
    import os
    import neo
    import numpy as np
    from matplotlib import pyplot as plt
    from scipy.signal import savgol_filter
    import scipy.signal
    from scipy.optimize import curve_fit
    import pandas as pd
    import seaborn as sns
    
    
    savedir = r'C:/Users/Isope/Desktop'
    

    TAGREC=[]
    TAG = []
    All_Tau=[]
    All_popt=[]
    amp_dict = {}
    amp_dict_idx = {}
    amp_dict_corr= {}
    FitPeaks_dict_tau = {}
    FitPeaks_dict_popt = {}
  
    
         
    sg.theme('DarkBlue')	
    
    layout0= [[sg.InputText(default_text='{}'.format(savedir)),sg.FolderBrowse()],
              [sg.Button('Select Save Folder')],
              [sg.Text('Enter File name     '), sg.InputText(), sg.FileBrowse(),sg.Button('Start File')],
              [sg.Text('Channel                '), sg.InputText(default_text = "0", size=(3, 1))],
              [sg.Text('Enter Folder name '), sg.InputText(), sg.FolderBrowse(),sg.Button('Start Folder')],
              [sg.Text('Enter xls file          '), sg.InputText(), sg.FileBrowse(),sg.Button('Start xls')]]
    
    window_main= sg.Window('New Analysis', layout0, location=(0,0))
    
    while True:
        event_main, values_main = window_main.read()
            
        if event_main in (None, 'Close'):	# if user closes window or clicks cancel
            break
        
        if event_main == 'Select Save Folder':
            savedir=str(values_main[0])
            print (savedir)
                                
        if event_main == 'Start File':
            channel = int(values_main[2])
            Matrix, timescale = load_wcp(values_main[1], channel) 
            Main_window(Matrix, timescale)
            
        if event_main == 'Start Folder':
            channel = int(values_main[2])
            Matrix, timescale = load_folder(values_main[3], channel)
            Main_window(Matrix, timescale)
                   
        if event_main == 'Start xls':
            load_xls(values_main[4], 0, REC)
            Main_window()
           
    window_main.close()    
    plt.close('all')
    
    
    

    