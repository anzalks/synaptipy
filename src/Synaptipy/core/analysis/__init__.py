# src/Synaptipy/core/analysis/__init__.py
"""
Synaptipy Analysis Sub-package.

Provides functions for analysing electrophysiology data represented
by the core data models.

This module also imports all analysis modules to trigger registration
of analysis functions with the AnalysisRegistry for batch processing.
"""
# Import registry first
from .registry import AnalysisRegistry

# Import analysis modules to trigger registration
# Each module registers its functions via @AnalysisRegistry.register decorator
from . import basic_features  # noqa: F401 - registers: rmp_analysis
from . import spike_analysis  # noqa: F401 - registers: spike_detection
from . import intrinsic_properties  # noqa: F401 - registers: rin_analysis, tau_analysis, sag_ratio_analysis
from . import event_detection  # noqa: F401 - registers: mini_detection, event_detection_threshold, etc.
from . import phase_plane  # noqa: F401 - registers: phase_plane_analysis
from . import burst_analysis  # noqa: F401 - registers: burst_analysis
from . import excitability  # noqa: F401 - registers: fi_curve_analysis
from . import capacitance  # noqa: F401 - registers: capacitance_analysis
from . import optogenetics  # noqa: F401 - registers: optogenetic_sync
from . import train_dynamics  # noqa: F401 - registers: train_dynamics

# Expose key functions for easier import
from .basic_features import calculate_rmp
from .spike_analysis import detect_spikes_threshold
from .intrinsic_properties import calculate_rin, calculate_tau, calculate_sag_ratio
from .event_detection import detect_minis_threshold

# Define what `from Synaptipy.core.analysis import *` imports
__all__ = [
    "AnalysisRegistry",
    "calculate_rmp",
    "detect_spikes_threshold",
    "calculate_rin",
    "calculate_tau",
    "calculate_sag_ratio",
    "detect_minis_threshold",
]
