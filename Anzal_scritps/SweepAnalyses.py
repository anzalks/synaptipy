__author__           = "Anzal KS"
__copyright__        = "Copyright 2024-, Anzal KS"
__maintainer__       = "Anzal KS"
__email__            = "anzalks@ncbs.res.in"

from pathlib import Path
import neo.io as nIO
import numpy as np
import pandas as pd
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
from scipy.stats import mode
import FileLoader as fl

av_color = "000000" # black 
trial_color = "#377eb8" # blue 
fit_color = "#de6f00" # orange


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


def extract_sweep(reader,trial_no,ChanToRead='IN0',debug=False):
    block  = reader.read_block(signal_group_mode='split-all')
    segments = block.segments
    sample_trace = segments[0].analogsignals[0]
    sampling_rate = sample_trace.sampling_rate.magnitude
    sampling_rate_unit = str(sample_trace.sampling_rate.units).split()[-1]
    time_units = str(sample_trace.times.units).split()[-1] 
    ti = sample_trace.t_start
    tf = sample_trace.t_stop
    t = np.linspace(0,float(tf-ti),len(sample_trace))
    try:
        ch_no = fl.channel_name_to_index(reader, ChanToRead)
        #print(f"ChanToRead: {ChanToRead}.......ch_no:{ch_no}")
    except AttributeError:
        raise ValueError(f"input channel name provide doesn't exist")
    
    units = str(segments[trial_no].analogsignals[ch_no].units).split()[-1]
    signal =  np.ravel(segments[trial_no].analogsignals[ch_no].magnitude)
    if debug:
        fig_,axs = plt.subplots(nrows=1, 
                           ncols=1, 
                           sharex=True, 
                           sharey=False)
        axs.plot(t,signal,color=trial_color)
        axs.set_title(f"channel: {ChanToRead}  sweep: {trial_no+1}")
        axs.set_ylabel(units)
        axs.set_xlabel(f"time ({time_units})")
        fig_.show()
    return signal, t, sampling_rate 


def read_numpy_array(file_path):
    ext = file_path.suffix.split('.')[-1]
    file_path = str(file_path)
    if ext =="pkl":
        trial_data = np.load(file_path,allow_pickle=True)
    else:
        trial_data = np.load(file_path)
    return trial_data

def read_pd_get_numpy(hdf_file_path):
    ext = hdf_file_path.suffix.split('.')[-1]
    hdf_file_path = str(hdf_file_path)
    if "h5" in ext:
        trial_df =pd.read_hdf(hdf_file_path)
    else:
        "trial data format must be hdf"
    try:
        sweep_data = trial_df["trial"].to_numpy()
        sweep_time = trial_df["time"].to_numpy()
    except AttributeError:
        raise ValueError(f"trace and time header is not matching to"
                         f"'trial', 'time' ")
    return sweep_data, sweep_time

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

def compute_peak_parameters(signal, t, baseline, sampling_rate):
    peaks, _ = find_peaks(signal, height=baseline + 2 * np.std(signal),
                          distance=int(0.02 * sampling_rate),
                          prominence=baseline + 2 * np.std(signal),
                          threshold=1.2 * baseline)
    if len(peaks) == 0:
        return None

    t0s, rise_times, fall_times, amplitudes = [], [], [], []

    for peak in peaks:
        peak_amplitude = signal[peak] - baseline
        rise_region = signal[:peak]
        try:
            t0_idx = np.where(rise_region >= 0.1 * peak_amplitude)[0][0]
            t0 = t[t0_idx]
        except IndexError:
            continue

        rise_time = t[peak] - t0

        fall_region = signal[peak:]
        t_fall = t[peak:]
        try:
            def decay_func(x, A, tau):
                return A * np.exp(-x / tau)

            popt, _ = curve_fit(decay_func, t_fall - t[peak], fall_region, p0=[peak_amplitude, 0.01],
                                bounds=([0, 0.001], [np.inf, 1]))
            tau_fall = popt[1]
        except RuntimeError:
            tau_fall = np.nan

        t0s.append(t0)
        rise_times.append(rise_time)
        fall_times.append(tau_fall)
        amplitudes.append(peak_amplitude)

    if len(t0s) == 0:
        return None

    return np.nanmean(t0s), np.nanmean(rise_times), np.nanmean(fall_times), np.nanmean(amplitudes)

def alpha_function(t, A, t0, tau_rise, tau_fall):
    alpha = np.zeros_like(t)
    rise_mask = (t >= t0) & (t < t0 + tau_rise)
    fall_mask = t >= t0 + tau_rise

    alpha[rise_mask] = A * (1 - np.exp(-(t[rise_mask] - t0) / tau_rise))
    alpha[fall_mask] = A * np.exp(-(t[fall_mask] - (t0 + tau_rise)) / tau_fall)

    return alpha


def calculate_goodness_of_fit(signal, fitted_signals):
    scores = []
    for fitted_signal, _ in fitted_signals:
        residuals = signal - fitted_signal
        ss_res = np.sum(residuals ** 2)
        ss_tot = np.sum((signal - np.mean(signal)) ** 2)
        r2_score = 1 - (ss_res / ss_tot)
        scores.append(r2_score)
    return scores


def fit_alpha_peaks(signal, t, sampling_rate, 
                    use_local_baseline=False, debug=False,
                    score_threshold=0.8):
    smoothed_signal = gaussian_filter1d(signal, sigma=5)
    filtered_signal = smoothed_signal
    global_baseline = np.round(np.mean(filtered_signal), 1)

    min_distance = int(0.002 * sampling_rate)
    #peaks, properties = find_peaks(filtered_signal, 
    #                               height=global_baseline+0.1* np.std(filtered_signal),
    #                                distance=min_distance, prominence=0.5 * np.std(filtered_signal))

    avg_params = compute_peak_parameters(filtered_signal, t, global_baseline, sampling_rate)
    if avg_params is None:
        print("No valid peaks found for computing average parameters.")
        return []

    avg_t0, avg_rise_time, avg_tau_fall, avg_amplitude = avg_params

    fitted_results = []
    scores = []
    valid_peak_sig = []
    valid_peaks = []
    valid_peaks_t = []

    for peak in peaks:
        if properties["peak_heights"][np.where(peaks == peak)[0][0]] <= global_baseline:
            continue

        local_baseline = np.mean(filtered_signal[max(0, peak - int(0.002 * sampling_rate)):peak]) if use_local_baseline else global_baseline

        window_left = max(0, peak - int(0.02 * sampling_rate))
        window_right = peak
        for i in range(peak, len(filtered_signal)):
            if filtered_signal[i] <= global_baseline:
                window_right = i + int(0.002 * sampling_rate)
                break

        t_window = t[window_left:window_right]
        signal_window = signal[window_left:window_right] - global_baseline

        if len(t_window) < 5:
            continue

        A_init = filtered_signal[peak] - global_baseline
        t0_init = t[peak]
        tau_rise_init = avg_rise_time if not np.isnan(avg_rise_time) else 0.002
        tau_fall_init = avg_tau_fall if not np.isnan(avg_tau_fall) else 0.01

        bounds = ([0.5 * A_init, t_window[0], 0.001, 0.001],
                  [10.0 * A_init, t_window[-1], 0.05, 0.2])
        p0 = [
            np.clip(A_init, bounds[0][0], bounds[1][0]),
            np.clip(t0_init, bounds[0][1], bounds[1][1]),
            np.clip(tau_rise_init, bounds[0][2], bounds[1][2]),
            np.clip(tau_fall_init, bounds[0][3], bounds[1][3])
        ]

        try:
            popt, _ = curve_fit(alpha_function, t_window, signal_window,
                                p0=p0, bounds=bounds, maxfev=10000)
            A_fit, t0_fit, tau_rise_fit, tau_fall_fit = popt

            signal_fitted = alpha_function(t_window, A_fit, t0_fit,
                                           tau_rise_fit, tau_fall_fit)

            full_signal_fit = np.full_like(t, global_baseline)
            start_idx = np.argmin(np.abs(t - t_window[0]))
            end_idx = np.argmin(np.abs(t - t_window[-1])) + 1
            if len(signal_fitted) == (end_idx - start_idx):
                full_signal_fit[start_idx:end_idx] = signal_fitted + global_baseline

            residuals = signal_window - signal_fitted
            ss_res = np.sum(residuals ** 2)
            ss_tot = np.sum((signal_window - np.mean(signal_window)) ** 2)
            r2_score = 1 - (ss_res / ss_tot)

            if r2_score >= score_threshold:
                fitted_results.append((full_signal_fit, t))
                scores.append(r2_score)
                valid_peaks.append(peak)
                valid_peaks_t.append(t[peak])
                valid_peak_sig.append(signal_window)
            else:
                fitted_results.append((None, None))
                scores.append(None)
                valid_peaks.append(None)
                valid_peaks_t.append(None)
                valid_peak_sig.append(None)


        except RuntimeError:
            print(f"Failed to fit alpha function at peak index {peak}.")
        except ValueError as e:
            print(f"ValueError during curve fitting at peak index {peak}: {e}")

    if debug:
        plt.figure(figsize=(12, 6))
        plt.plot(t, signal, label="Raw Signal", alpha=0.5)
        plt.plot(t, filtered_signal, label="Filtered Signal", alpha=0.8)

        for peak in peaks:
            if peak in valid_peaks:
                fit_index = valid_peaks.index(peak)
                r2_score = scores[fit_index]
                plt.scatter(t[peak], filtered_signal[peak], color="green", 
                            label=f"Good Fit (R^2: {r2_score:.2f})" if peak == valid_peaks[0] else "")
            else:
                plt.scatter(t[peak], filtered_signal[peak], color="red", 
                            label="Detected Peaks")

        for i, (signal_fitted, time_segment) in enumerate(fitted_results):
            plt.plot(time_segment, signal_fitted, linestyle="--",
                     label=f"Fitted Curve {i+1}, R^2: {scores[i]:.2f}")

        plt.xlabel("Time (s)")
        plt.ylabel("Signal")
#        plt.legend()
        plt.title("Alpha Function Fitting to Detected Peaks")
        plt.show()

    return fitted_results,valid_peak_sig, valid_peaks, valid_peaks_t

def baseline_measurement(TrialData,debug=False):
    trialDatBsln = np.round(TrialData,1)
    trialDatBsln,count =np.round(mode(trialDatBsln,keepdims=False),2)
    fig_,axs_ = plt.subplots(1,1)
    if debug:
        print(f"trialDatBsln,count : {trialDatBsln,count}")
        plt.plot(TrialData,label='raw sweep')
        plt.axhline(trialDatBsln,color='k',linestyle=':',label='baseline')
        fig_.legend()
        fig_.show()
    return trialDatBsln

def offset_baseline(sweep,baseline,debug=False):
    offsetted_sweep = sweep-baseline
    offsetted_baseline=baseline_measurement(offsetted_sweep)
    fig_,axs_ = plt.subplots(1,1)
    if debug:
        print(f"trialDatBsln,count : {baseline}")
        plt.plot(offsetted_sweep,label='leak subsctracte\nsweep')
        plt.axhline(baseline,color='k',linestyle=':',label="leak")
        plt.axhline(offsetted_baseline,color='r',linestyle=':',label="baseline")
        fig_.legend()
        fig_.show()
    return offsetted_baseline





def collect_peak_stats(TrialData,t,sampling_rate,
                       use_local_baseline=False,
                       debug=False,
                       score_threshold=0.8):
    swp_fit,swp,pks, pks_t = fit_alpha_peaks(TrialData, 
                                             t, 
                                             sampling_rate,
                                             use_local_baseline, 
                                             debug, 
                                             score_threshold)
    t_trial = float(len(t)/sampling_rate)
    num_peaks = len(pks)
    freq_peaks =num_peaks/t_trial
    peak_stats= {'fitted_curve':swp_fit,'raw_trace':swp,
                 'peak_amplitude':pks,
                 'peak_time':pks_t,'peak_frequency':freq_peaks}
    return peak_stats










def main():
    # Argument parser.
    description = '''Set of anlaysis fucntiosn on single sweeps'''
    
    #setup the argument parser
    parser = argparse.ArgumentParser(description=description)
    
    #listed out arguments
    parser.add_argument('--file-path', '-f'
                        , required = False,default ='./', type=str
                        , help = 'path to df with trace and time in .h5'
                       )
    parser.add_argument('--sampling-rate', '-s'
                        , required = False,default =20000., type=float
                        , help = 'Sampling rate of the trace'
                       )



    #parse the arguents
    args = parser.parse_args()

    #define the variable from parser
    file_path = Path(args.file_path)
    reader,_ = fl.read_with_IO(file_path)
    
    #call the fucntion to open np file
    #sweep_data, sweep_time = read_pd_get_numpy(file_path)
    sweep, time, sampling_rate = extract_sweep(reader,
                                               trial_no=1,
                                               ChanToRead='IN0')
    
    #run analyses on single trial data
    peak_stats = collect_peak_stats(sweep,time,sampling_rate,
                                    use_local_baseline=True,
                                    debug=True,
                                    score_threshold=0.8)
    baseline = baseline_measurement(sweep_data)


if __name__  == '__main__':
    #timing the run with time.time
    ts =time.time()
    main() 
    tf =time.time()
    print(f'total time = {np.around(((tf-ts)/60),1)} (mins)')
