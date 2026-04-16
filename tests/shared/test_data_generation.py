"""
Utilities for generating synthetic test data files.

This module provides functions to create synthetic electrophysiology data
for testing purposes, avoiding the need to include large real recordings
in the repository.
"""

import logging
import os
from pathlib import Path

import numpy as np

# Try to import Neo for file writing, but provide alternative if not available
try:
    import neo
    import quantities as pq

    NEO_AVAILABLE = True
except ImportError:
    NEO_AVAILABLE = False

# Set up logging
logger = logging.getLogger(__name__)


def generate_sine_wave(duration=1.0, frequency=10.0, sampling_rate=10000, amplitude=1.0, phase=0.0):
    """
    Generate a sine wave with specified parameters.

    Args:
        duration (float): Duration in seconds
        frequency (float): Frequency in Hz
        sampling_rate (int): Sampling rate in Hz
        amplitude (float): Amplitude of the sine wave
        phase (float): Phase offset in radians

    Returns:
        tuple: (time_array, data_array)
    """
    num_samples = int(duration * sampling_rate)
    time = np.linspace(0, duration, num_samples, endpoint=False)
    data = amplitude * np.sin(2 * np.pi * frequency * time + phase)
    return time, data


def generate_voltage_clamp_step(
    duration=1.0, step_start=0.2, step_duration=0.5, baseline=-70.0, step_amplitude=-10.0, sampling_rate=10000
):
    """
    Generate a voltage clamp step protocol.

    Args:
        duration (float): Total duration in seconds
        step_start (float): When the step starts in seconds
        step_duration (float): Duration of the step in seconds
        baseline (float): Baseline holding potential in mV
        step_amplitude (float): Amplitude of the step in mV
        sampling_rate (int): Sampling rate in Hz

    Returns:
        tuple: (time_array, voltage_array)
    """
    num_samples = int(duration * sampling_rate)
    time = np.linspace(0, duration, num_samples, endpoint=False)
    voltage = np.ones_like(time) * baseline

    # Calculate sample indices for step
    step_start_idx = int(step_start * sampling_rate)
    step_end_idx = int((step_start + step_duration) * sampling_rate)

    # Apply step
    if step_end_idx > step_start_idx and step_start_idx < len(voltage):
        end_idx = min(step_end_idx, len(voltage))
        voltage[step_start_idx:end_idx] = baseline + step_amplitude

    return time, voltage


def generate_current_response(
    voltage_time, voltage_data, input_resistance=100.0, capacitance=20.0, sampling_rate=10000, noise_level=0.02
):
    """
    Generate a current response to a voltage command based on a simple RC model.

    Args:
        voltage_time (array): Time points
        voltage_data (array): Voltage command data
        input_resistance (float): Input resistance in MOhm
        capacitance (float): Membrane capacitance in pF
        sampling_rate (int): Sampling rate in Hz
        noise_level (float): Amount of noise to add (fraction of signal amplitude)

    Returns:
        array: Current response data
    """
    # Convert from MOhm to Ohm and pF to F
    resistance = input_resistance * 1e6  # MOhm to Ohm
    cap = capacitance * 1e-12  # pF to F

    # Calculate time step
    dt = 1.0 / sampling_rate

    # Initialize current array
    current = np.zeros_like(voltage_data)

    # Calculate steady-state currents (I = V/R)
    steady_state = voltage_data / resistance

    # First point
    current[0] = steady_state[0]

    # Calculate time constant (tau = RC)
    tau = resistance * cap
    _decay_factor = np.exp(-dt / tau)  # noqa: F841

    # Apply simple RC model with time constant
    for i in range(1, len(voltage_data)):
        # If voltage changes, add capacitive current
        if voltage_data[i] != voltage_data[i - 1]:
            cap_current = (voltage_data[i] - voltage_data[i - 1]) * cap / dt
        else:
            cap_current = 0

        # Current is sum of resistive (steady-state) and capacitive components
        current[i] = steady_state[i] + cap_current

    # Add noise
    if noise_level > 0:
        noise = np.random.normal(0, noise_level * np.ptp(current), size=current.shape)
        current += noise

    return current


def create_dummy_abf_file(output_path, sampling_rate=10000, duration=1.0):
    """
    Create a dummy ABF file with voltage and current channels.

    Args:
        output_path (str or Path): Path to save the ABF file
        sampling_rate (int): Sampling rate in Hz
        duration (float): Recording duration in seconds

    Returns:
        bool: True if successful, False otherwise
    """
    if not NEO_AVAILABLE:
        logger.error("Neo library not available. Cannot create ABF file.")
        return False

    try:
        # Generate voltage step protocol
        time, voltage = generate_voltage_clamp_step(
            duration=duration,
            sampling_rate=sampling_rate,
            baseline=-70.0,
            step_amplitude=-10.0,
            step_start=0.2,
            step_duration=0.5,
        )

        # Generate current response
        current = generate_current_response(
            time, voltage, input_resistance=100.0, capacitance=20.0, sampling_rate=sampling_rate
        )

        # Create Neo objects
        block = neo.Block(name="Test Block")
        segment = neo.Segment(name="Test Segment")
        block.segments.append(segment)

        # Create voltage signal
        voltage_signal = neo.AnalogSignal(
            voltage * pq.mV, sampling_rate=sampling_rate * pq.Hz, t_start=0 * pq.s, name="Vm", channel_index=0
        )
        voltage_signal.annotations["channel_name"] = "Vm"

        # Create current signal
        current_signal = neo.AnalogSignal(
            current * pq.pA, sampling_rate=sampling_rate * pq.Hz, t_start=0 * pq.s, name="Im", channel_index=1
        )
        current_signal.annotations["channel_name"] = "Im"

        # Add signals to segment
        segment.analogsignals.append(voltage_signal)
        segment.analogsignals.append(current_signal)

        # Create a writer
        writer = neo.io.NixIO(filename=str(output_path))
        writer.write_block(block)
        writer.close()

        logger.info(f"Created test file at: {output_path}")
        return True

    except Exception as e:
        logger.error(f"Failed to create test file: {e}")
        return False


# ---------------------------------------------------------------------------
# 5-Pillar Synthetic Ground Truth Generators
# ---------------------------------------------------------------------------


def make_rc_passive_trace(
    rin_mohm: float = 200.0,
    tau_ms: float = 20.0,
    step_amplitude_pa: float = -100.0,
    baseline_mv: float = -65.0,
    sampling_rate: float = 20000.0,
    duration_s: float = 0.3,
    step_start_s: float = 0.05,
    step_end_s: float = 0.25,
) -> tuple:
    """Generate a mathematically pure RC-circuit voltage trace.

    The voltage response is a monoexponential approach to a new steady state:

        V(t) = V_ss * (1 - exp(-t / tau))

    where ``V_ss = I * R_in`` and ``tau = R_in * C_m``.

    Returns:
        (voltage, time, known_constants) where known_constants is a dict with
        keys ``rin_mohm``, ``tau_ms``, ``cm_pf``, ``delta_v_mv``.
    """
    cm_pf = tau_ms / rin_mohm * 1e6  # tau = RC → C = tau / R  [pF = ms / MOhm]

    n = int(duration_s * sampling_rate)
    t = np.arange(n) / sampling_rate
    v = np.full(n, baseline_mv)

    # Voltage steady-state during step: ΔV = I(pA) * R(MOhm) / 1000 → mV
    delta_v_mv = step_amplitude_pa * rin_mohm / 1000.0  # pA * MOhm / 1000 = mV
    tau_s = tau_ms / 1000.0

    idx_on = int(step_start_s * sampling_rate)
    idx_off = int(step_end_s * sampling_rate)

    for i in range(idx_on, idx_off):
        dt = (i - idx_on) / sampling_rate
        v[i] = baseline_mv + delta_v_mv * (1.0 - np.exp(-dt / tau_s))

    # Off transient: return toward baseline
    v_at_off = v[idx_off - 1]
    for i in range(idx_off, n):
        dt = (i - idx_off) / sampling_rate
        v[i] = baseline_mv + (v_at_off - baseline_mv) * np.exp(-dt / tau_s)

    known = {
        "rin_mohm": rin_mohm,
        "tau_ms": tau_ms,
        "cm_pf": cm_pf,
        "delta_v_mv": delta_v_mv,
        "step_amplitude_pa": step_amplitude_pa,
        "step_start_s": step_start_s,
        "step_end_s": step_end_s,
    }
    return v, t, known


def make_single_spike_trace(
    max_dvdt_vs: float = 200.0,
    half_width_ms: float = 1.0,
    baseline_mv: float = -70.0,
    peak_mv: float = 30.0,
    sampling_rate: float = 100000.0,
    duration_s: float = 0.05,
    spike_onset_s: float = 0.01,
) -> tuple:
    """Generate a parameterised single action potential waveform.

    The upstroke is a straight ramp with gradient ``max_dvdt_vs`` V/s so
    that the peak dV/dt is exactly known.  The half-width is the duration
    at half the peak amplitude above baseline.

    Returns:
        (voltage, time, known_constants) where known_constants has
        ``max_dvdt_vs`` and ``half_width_ms``.
    """
    n = int(duration_s * sampling_rate)
    t = np.arange(n) / sampling_rate
    v = np.full(n, baseline_mv)

    dt = 1.0 / sampling_rate
    amplitude_mv = peak_mv - baseline_mv  # e.g. 100 mV

    # max_dvdt in V/s → convert to mV/sample
    dvdt_mv_per_s = max_dvdt_vs * 1000.0  # V/s → mV/s
    rise_time_s = amplitude_mv / dvdt_mv_per_s  # s
    rise_samples = max(2, int(rise_time_s / dt))

    spike_idx = int(spike_onset_s * sampling_rate)
    # Upstroke: linear ramp
    for i in range(rise_samples):
        idx = spike_idx + i
        if idx < n:
            v[idx] = baseline_mv + amplitude_mv * (i / rise_samples)
    peak_idx = spike_idx + rise_samples
    if peak_idx < n:
        v[peak_idx] = peak_mv

    # Half-width: duration at amplitude = (baseline + peak) / 2  (noqa: F841 half_v unused - kept for doc clarity)
    half_width_s = half_width_ms / 1000.0
    # Symmetric: half the samples on downstroke
    half_w_samples = max(2, int(half_width_s * sampling_rate / 2))
    # Downstroke: linear fall from peak to baseline
    decay_samples = half_w_samples * 2
    for i in range(decay_samples):
        idx = peak_idx + 1 + i
        if idx < n:
            v[idx] = peak_mv - amplitude_mv * (i / decay_samples)

    known = {
        "max_dvdt_vs": max_dvdt_vs,
        "half_width_ms": half_width_ms,
        "baseline_mv": baseline_mv,
        "peak_mv": peak_mv,
        "spike_onset_s": spike_onset_s,
        "peak_idx": peak_idx,
    }
    return v, t, known


def make_spike_train_trace(
    n_spikes: int = 5,
    isi_first_ms: float = 100.0,
    adaptation_index: float = 2.0,
    baseline_mv: float = -65.0,
    sampling_rate: float = 20000.0,
    duration_s: float = 1.5,
) -> tuple:
    """Generate a pure spike train with a mathematically exact Adaptation Index.

    The Adaptation Index is defined as ``ISI_last / ISI_first``.  This
    function places spikes such that the ISIs grow geometrically, giving
    ``AI = ISI_last / ISI_first`` exactly equal to *adaptation_index*.

    Returns:
        (voltage, time, known_constants) where known_constants has
        ``adaptation_index``, ``isi_first_ms``, ``spike_times_s``.
    """
    # Build ISIs: geometric series so last/first == adaptation_index
    # ratio r: ISI_n = isi_first * r^(n-1); AI = ISI_(n-1)/ISI_0 = r^(n-2)
    n_isis = n_spikes - 1
    if n_isis > 1:
        ratio = adaptation_index ** (1.0 / (n_isis - 1))
    else:
        ratio = adaptation_index  # only 1 ISI
    isis_s = np.array([isi_first_ms / 1000.0 * ratio**i for i in range(n_isis)])

    # Spike times: first spike at 0.05 s
    spike_times = np.zeros(n_spikes)
    spike_times[0] = 0.05
    for i in range(1, n_spikes):
        spike_times[i] = spike_times[i - 1] + isis_s[i - 1]

    n = int(duration_s * sampling_rate)
    t = np.arange(n) / sampling_rate
    v = np.full(n, baseline_mv)

    # Place narrow Gaussian-shaped spikes at each spike time
    spike_hw_samples = max(2, int(0.0005 * sampling_rate))  # 0.5 ms half-width
    for st in spike_times:
        idx = int(st * sampling_rate)
        for j in range(-spike_hw_samples, spike_hw_samples + 1):
            k = idx + j
            if 0 <= k < n:
                gauss = np.exp(-0.5 * (j / max(1, spike_hw_samples * 0.4)) ** 2)
                v[k] = baseline_mv + 100.0 * gauss

    known = {
        "adaptation_index": float(isis_s[-1] / isis_s[0]) if len(isis_s) > 1 else float("nan"),
        "isi_first_ms": float(isis_s[0] * 1000.0),
        "isi_last_ms": float(isis_s[-1] * 1000.0),
        "n_spikes": n_spikes,
        "spike_times_s": spike_times.tolist(),
    }
    return v, t, known


def make_biexponential_epsc(
    a_fast: float = 60.0,
    tau_fast_ms: float = 3.0,
    a_slow: float = 40.0,
    tau_slow_ms: float = 20.0,
    sampling_rate: float = 20000.0,
    duration_ms: float = 200.0,
    baseline_pa: float = 0.0,
) -> tuple:
    """Generate a pure bi-exponential synaptic current decay.

    The waveform is::

        I(t) = A_fast * exp(-t / tau_fast) + A_slow * exp(-t / tau_slow)

    with all parameters analytically known.

    Area under the curve (AUC) is computed as::

        AUC = A_fast * tau_fast + A_slow * tau_slow   (pA·ms)

    Returns:
        (current_pa, time_ms, known_constants) where known_constants has
        ``a_fast``, ``tau_fast_ms``, ``a_slow``, ``tau_slow_ms``, ``auc_pa_ms``,
        ``peak_pa``.  The *peak_pa* is ``a_fast + a_slow`` (at t=0).
    """
    n = int(duration_ms / 1000.0 * sampling_rate)
    t_s = np.arange(n) / sampling_rate
    t_ms = t_s * 1000.0

    decay = a_fast * np.exp(-t_ms / tau_fast_ms) + a_slow * np.exp(-t_ms / tau_slow_ms)
    current_pa = baseline_pa - decay  # negative (inward current convention)

    auc_pa_ms = a_fast * tau_fast_ms + a_slow * tau_slow_ms

    known = {
        "a_fast": a_fast,
        "tau_fast_ms": tau_fast_ms,
        "a_slow": a_slow,
        "tau_slow_ms": tau_slow_ms,
        "peak_pa": a_fast + a_slow,
        "auc_pa_ms": auc_pa_ms,
    }
    return current_pa, t_s, known


def make_ppr_evoked_trace(
    r1_amp_mv: float = -5.0,
    r2_amp_mv: float = -5.0,
    tau_decay_ms: float = 40.0,
    stim1_s: float = 0.1,
    stim2_s: float = 0.2,
    baseline_mv: float = -65.0,
    sampling_rate: float = 10000.0,
    duration_s: float = 0.5,
) -> tuple:
    """Generate a paired-pulse trace with a mathematically exact residual decay.

    Each event is modelled as a monoexponential decay of amplitude *r_amp_mv*.
    The second event is placed on top of the still-decaying tail of the first,
    so the exact residual at stim2 is analytically known.

    Returns:
        (voltage, time, known_constants) where known_constants includes
        ``r1_amp_mv``, ``r2_amp_mv``, ``residual_at_stim2_mv``,
        ``naive_ppr`` (= r2/r1), and ``tau_decay_ms``.
    """
    n = int(duration_s * sampling_rate)
    t = np.arange(n) / sampling_rate
    v = np.full(n, baseline_mv)

    tau_s = tau_decay_ms / 1000.0
    idx1 = int(stim1_s * sampling_rate)
    idx2 = int(stim2_s * sampling_rate)

    # First event
    for i in range(idx1, n):
        dt = (i - idx1) / sampling_rate
        v[i] += r1_amp_mv * np.exp(-dt / tau_s)

    # Second event added on top
    for i in range(idx2, n):
        dt = (i - idx2) / sampling_rate
        v[i] += r2_amp_mv * np.exp(-dt / tau_s)

    # Exact residual of event-1 at stim2 onset
    isi_s = stim2_s - stim1_s
    residual_at_stim2 = r1_amp_mv * np.exp(-isi_s / tau_s)

    known = {
        "r1_amp_mv": r1_amp_mv,
        "r2_amp_mv": r2_amp_mv,
        "tau_decay_ms": tau_decay_ms,
        "stim1_s": stim1_s,
        "stim2_s": stim2_s,
        "residual_at_stim2_mv": residual_at_stim2,
        "naive_ppr": r2_amp_mv / r1_amp_mv if r1_amp_mv != 0 else float("nan"),
        "isi_ms": isi_s * 1000.0,
    }
    return v, t, known


if __name__ == "__main__":
    # Setup basic logging
    logging.basicConfig(level=logging.INFO)

    # Path to the test data directory
    test_data_dir = Path(__file__).parent.parent / "data"
    os.makedirs(test_data_dir, exist_ok=True)

    # Create a dummy NWB file
    if NEO_AVAILABLE:
        sample_path = test_data_dir / "sample_synthetic.nix"
        if create_dummy_abf_file(sample_path):
            print(f"Created synthetic test file at: {sample_path}")
        else:
            print("Failed to create synthetic test file")
    else:
        print("Neo not available. Cannot create test files.")


# ---------------------------------------------------------------------------
# Noise injection helpers (Phase 6 — biological noise testing)
# ---------------------------------------------------------------------------


def inject_pink_noise(
    signal: np.ndarray,
    sampling_rate: float,
    rms_amplitude: float = 0.5,
    rng: np.random.Generator = None,
) -> np.ndarray:
    """Add 1/f (pink) noise to *signal*.

    Pink noise is generated by filtering white noise in the frequency domain:
    each frequency bin amplitude is scaled by ``1 / sqrt(f)`` to achieve the
    ``1/f`` power spectrum characteristic of biological membrane noise.

    Parameters
    ----------
    signal : np.ndarray
        1-D input signal array (any units).
    sampling_rate : float
        Sampling rate in Hz (used to normalise DC bin).
    rms_amplitude : float
        Target RMS amplitude of the injected noise (same units as *signal*).
    rng : np.random.Generator, optional
        NumPy random generator for reproducibility.  Defaults to
        ``np.random.default_rng(42)``.

    Returns
    -------
    np.ndarray
        Copy of *signal* with pink noise added.
    """
    if rng is None:
        rng = np.random.default_rng(42)

    n = len(signal)
    white = rng.standard_normal(n)
    fft_white = np.fft.rfft(white)
    freqs = np.fft.rfftfreq(n, d=1.0 / sampling_rate)
    # Avoid division-by-zero at DC (f=0); leave DC component unscaled
    scale = np.where(freqs > 0, 1.0 / np.sqrt(freqs), 1.0)
    pink_fft = fft_white * scale
    pink = np.fft.irfft(pink_fft, n=n)
    # Normalise to target RMS
    current_rms = float(np.sqrt(np.mean(pink**2)))
    if current_rms > 1e-12:
        pink = pink * (rms_amplitude / current_rms)
    return signal.copy() + pink


def inject_line_hum(
    signal: np.ndarray,
    sampling_rate: float,
    frequency_hz: float = 50.0,
    amplitude: float = 0.3,
) -> np.ndarray:
    """Add a sinusoidal mains-frequency hum to *signal*.

    Parameters
    ----------
    signal : np.ndarray
        1-D input signal array.
    sampling_rate : float
        Sampling rate in Hz.
    frequency_hz : float
        Hum frequency (50 Hz Europe/Asia, 60 Hz North America).
    amplitude : float
        Peak amplitude of the sinusoidal component (same units as *signal*).

    Returns
    -------
    np.ndarray
        Copy of *signal* with sinusoidal hum added.
    """
    t = np.arange(len(signal)) / sampling_rate
    hum = amplitude * np.sin(2.0 * np.pi * frequency_hz * t)
    return signal.copy() + hum


def make_noisy_variants(
    clean_signal: np.ndarray,
    sampling_rate: float,
    pink_rms: float = 0.5,
    hum_amplitude: float = 0.3,
    hum_frequency_hz: float = 50.0,
    rng: np.random.Generator = None,
) -> dict:
    """Return a dict of noise-contaminated variants of *clean_signal*.

    Generates two variants:

    ``"pink"``
        Clean signal + 1/f pink noise (``rms = pink_rms``).
    ``"pink_hum"``
        Clean signal + pink noise + 50/60 Hz line hum.

    Parameters
    ----------
    clean_signal : np.ndarray
        Pure ground-truth signal (any units).
    sampling_rate : float
        Sampling rate in Hz.
    pink_rms : float
        RMS amplitude of pink noise component.
    hum_amplitude : float
        Peak amplitude of sinusoidal hum component.
    hum_frequency_hz : float
        Hum frequency in Hz (default 50).
    rng : np.random.Generator, optional
        Seeded RNG for reproducibility.

    Returns
    -------
    dict
        ``{"clean": clean_signal, "pink": ..., "pink_hum": ...}``
    """
    with_pink = inject_pink_noise(clean_signal, sampling_rate, pink_rms, rng=rng)
    with_pink_hum = inject_line_hum(with_pink, sampling_rate, hum_frequency_hz, hum_amplitude)
    return {
        "clean": clean_signal.copy(),
        "pink": with_pink,
        "pink_hum": with_pink_hum,
    }
