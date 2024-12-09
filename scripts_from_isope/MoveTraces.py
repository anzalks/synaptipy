# -*- coding: utf-8 -*-
"""
Created on Thu Aug 22 14:33:02 2024

@author: Philippe.ISOPE
"""

from matplotlib import pyplot as plt
import PySimpleGUI as sg



def next_trace(episode,episode_number, Tagged, RECORDINGS, ax):
    episode+=1
    if episode > (episode_number-1):
        sg.popup_error('End of episodes')
        episode-=1 
        return episode
       
    else:
        if Tagged[episode] == 1:
            ax.plot(RECORDINGS[f'Trace-{episode}'], color ='r')
        else:
            ax.plot(RECORDINGS[f'Trace-{episode}'])
        # try:
        #     # ax.axvline(startpos[0], color ='r')
        #     # ax.axvline(endpos[0], color ='g')
        #     # fig.canvas.draw()
            
        # except:
        #     pass
        # try:
        #     for key in amp_dict.keys():  
        #         index=amp_dict_idx[key][episode]
        #         x=TIME[episode][index]
        #         y=amp_dict[key][episode]
        #         ax.plot(x,y,'bo', linewidth = 3)
        # except:
        #     pass
        plt.xlabel('Time (s)')
        plt.ylabel('Signal (Amp)')
        plt.title('Episode '+str(episode)+'/'+str(episode_number-1), fontweight="bold", fontsize=16, color="g")
        plt.draw()
        return episode
    
def previous_trace(episode,episode_number, Tagged, RECORDINGS, ax):
    episode-=1 
    if episode < 0:
        sg.popup_error('End of episodes')
        episode+=1
        return episode
    else:
        if Tagged[episode] == 1:
            ax.plot(RECORDINGS[f'Trace-{episode}'], color ='r')
        else:
            ax.plot(RECORDINGS[f'Trace-{episode}'])
        # try:
        #     ax.axvline(startpos[0], color ='r')
        #     ax.axvline(endpos[0], color ='g')
        #     fig.canvas.draw()
        # except:
        #     pass
        # try:
        #     for key in amp_dict.keys():  
        #         index=amp_dict_idx[key][episode]
        #         x=TIME[episode][index]
        #         y=amp_dict[key][episode]
        #         ax.plot(x,y,'bo', linewidth = 3)
        # except:
        #     pass
        plt.xlabel('Time (s)')
        plt.ylabel('Signal (Amp)')
        plt.title('Episode '+str(episode)+'/'+str(episode_number-1), fontweight="bold", fontsize=16, color="g")
        plt.draw()          
        return episode
    
    
if __name__ == '__main__' :
    
   episode = None  
   episode_number =  None
   TAG =  None
   RECORDINGS = None
   ax =  None
   next_trace(episode,episode_number, TAG, RECORDINGS, ax)