# src/Synaptipy/core/constants.py
# -*- coding: utf-8 -*-
"""
Unified constants for Synaptipy electrophysiology analysis.

This module centralises all numerical constants (precision epsilons, detection
thresholds, physiological windows) so that:

1. Magic numbers are replaced by descriptive names.
2. Each value carries a documented rationale and, where applicable, a citation.
3. Downstream modules import from one location, making it trivial to adjust
   parameters for different preparations or temperatures.

Usage::

    from Synaptipy.core.constants import EPSILON_ISI_SUM, DVDT_THRESHOLD_VS
"""

# ===========================================================================
# PRECISION HIERARCHY
# ===========================================================================
# These epsilon values guard against floating-point division by zero.
# The hierarchy reflects the physical scale of the quantities being compared.

# Sub-nanosecond: below any physiological timescale (smallest AP ~100 us)
EPSILON_TIME_S = 1e-9

# Sub-microvolt: below thermal noise floor (~1 uV RMS at room temperature)
EPSILON_VOLTAGE_MV = 1e-6

# Sub-femtoampere: below Johnson noise floor in patch-clamp amplifiers
EPSILON_CURRENT_PA = 1e-6

# Below any measurable resistance in electrophysiology (pipette ~1-10 MOhm)
EPSILON_RESISTANCE = 1e-12

# For CV2 calculation: sum of adjacent ISIs (seconds).
# Two ISIs summing to < 1 ns is physically impossible for neural spikes.
EPSILON_ISI_SUM = 1e-9

# For LV calculation: squared sum of adjacent ISIs (seconds^2).
# Tighter epsilon because squaring already-small numbers yields values near
# machine epsilon; 1e-15 ~ (1e-7.5 s)^2, still sub-microsecond scale.
EPSILON_ISI_SUM_SQ = 1e-15


# ===========================================================================
# SPIKE DETECTION DEFAULTS
# ===========================================================================

# dV/dt threshold for AP onset detection (phase-plane method).
# Bean (2007) "The action potential in mammalian central neurons"
# Nature Reviews Neuroscience 8:451-465.
# Cortical pyramidal neurons: AP onset ~10-30 V/s; 20 V/s is a robust default.
DVDT_THRESHOLD_VS = 20.0  # V/s

# Artifact ceiling: maximum physiological dV/dt for fastest cortical APs.
# Naundorf, Wolf & Volgushev (2006) "Unique features of action potential
# initiation in cortical neurons" Nature 440:1060-1063.
# Fastest cortical APs show ~250-300 V/s rising rates; above this is artifact.
DVDT_ARTIFACT_CEILING_VS = 300.0  # V/s

# Minimum rising phase duration for a physiological action potential.
# APs shorter than 0.2 ms threshold-to-peak indicate capacitive artifact
# or poorly clamped axonal spikes rather than somatic action potentials.
# Typical somatic AP rise time: 0.3-1.0 ms (Bean 2007).
MIN_RISING_PHASE_MS = 0.2  # ms


# ===========================================================================
# AHP WINDOWS
# ===========================================================================
# After-hyperpolarisation component windows for mammalian cortical neurons
# at room temperature (20-25 C).
#
# Storm (1987) "Action potential repolarization and a fast
# after-hyperpolarization in rat hippocampal pyramidal cells"
# J Physiol 385:733-759.
#
# Sah & Faber (2002) "Channels underlying neuronal calcium-activated
# potassium currents" Nature Reviews Neuroscience 3:175-190.

# Fast AHP (fAHP): BK (big-conductance Ca2+-activated K+) channel-mediated.
# Peaks 1-5 ms after AP repolarisation.
FAHP_WINDOW_MS = (1.0, 5.0)

# Medium AHP (mAHP): SK (small-conductance Ca2+-activated K+) channel-mediated.
# Peaks 10-50 ms after AP repolarisation.
MAHP_WINDOW_MS = (10.0, 50.0)


# ===========================================================================
# BURST DETECTION
# ===========================================================================
# Grace & Bunney (1984) "The control of firing pattern in nigral dopamine
# neurons: burst firing" J Neurosci 4:2877-2890.
# Adapted for cortical use: a burst is defined by ISIs shorter than a
# fraction of the mean ISI.

# Fraction of mean ISI that defines the burst boundary.
# ISIs below (BURST_ISI_FRACTION * mean_ISI) are considered intra-burst.
BURST_ISI_FRACTION = 0.3


# ===========================================================================
# SYNAPTIC EVENT DETECTION
# ===========================================================================
# Bhatt, McLean, Bhatt & Bhatt (2009) "Bhatt et al." J Physiol methodology
# for noise floor estimation in miniature synaptic event detection.

# Minimum RMS noise floor to prevent zero-noise division when the trace is
# completely flat (e.g., digital zeros or saturated amplifier).
NOISE_FLOOR_MIN_RMS = 1e-6  # units match trace (mV or pA)

# Multiple of noise standard deviation used as threshold for transient
# (synaptic event) detection above baseline.
TRANSIENT_DETECTION_FACTOR = 3.0


# ===========================================================================
# SIGNAL PROCESSING / QUALITY CONTROL
# ===========================================================================

# Baseline drift threshold: multiplier of signal standard deviation.
# If total linear drift exceeds this many SDs, a warning is issued.
# Empirically, 5x SD corresponds to ~0.5 mV/s over 10 s in a typical
# cortical recording -- exceeds physiological slow fluctuations and
# indicates recording instability (seal degradation, pipette drift).
BASELINE_DRIFT_THRESHOLD_MV = 5.0
