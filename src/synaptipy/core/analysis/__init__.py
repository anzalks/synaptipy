# src/synaptipy/core/analysis/__init__.py
"""
Synaptipy Analysis Sub-package.

Provides functions for analysing electrophysiology data represented
by the core data models.

This module also imports all analysis modules to trigger registration
of analysis functions with the AnalysisRegistry for batch processing.
"""

from synaptipy.core.protocols import (  # noqa: F401
    BUILTIN_ANALYSIS_REQUIREMENTS,
    ProtocolAssignment,
    ProtocolMap,
    ProtocolRequirement,
    ProtocolSource,
    ResolvedProtocol,
    apply_builtin_protocol_requirements,
)

# Keep batch_engine importable
# Import new consolidated modules to trigger @AnalysisRegistry.register decorators
from . import batch_engine  # noqa: F401
from . import epoch_manager  # noqa: F401 - EpochManager for TTL and manual epoch management
from . import evoked_responses  # noqa: F401 - registers: optogenetic_sync
from . import firing_dynamics  # noqa: F401 - registers: excitability_analysis, burst_analysis, train_dynamics
from . import passive_properties  # noqa: F401 - registers passive-property analyses
from . import single_spike  # noqa: F401 - registers: spike_detection, phase_plane_analysis
from . import synaptic_events  # noqa: F401 - registers event-detection analyses
from .contracts import ANALYSIS_RESULT_SCHEMA_VERSION, AnalysisResult  # noqa: F401
from .epoch_manager import Epoch, EpochManager  # noqa: F401

# Expose key functions for easier import (backward compatibility)
from .passive_properties import calculate_rin, calculate_rmp, calculate_sag_ratio, calculate_tau

# Import registry first so the decorator is available when modules load
from .registry import AnalysisRegistry  # noqa: F401
from .single_spike import detect_spikes_threshold
from .synaptic_events import detect_minis_threshold

# Attach a common, inspectable protocol contract to every supplied analysis.
# External plugins are deliberately not modified; they can opt in by declaring
# ``protocol_requirements`` in their own registry metadata.
apply_builtin_protocol_requirements(AnalysisRegistry)

# Define what `from synaptipy.core.analysis import *` imports
__all__ = [
    "AnalysisRegistry",
    "AnalysisResult",
    "ANALYSIS_RESULT_SCHEMA_VERSION",
    "calculate_rmp",
    "detect_spikes_threshold",
    "calculate_rin",
    "calculate_tau",
    "calculate_sag_ratio",
    "detect_minis_threshold",
    "ProtocolAssignment",
    "ProtocolMap",
    "ProtocolRequirement",
    "ProtocolSource",
    "ResolvedProtocol",
    "BUILTIN_ANALYSIS_REQUIREMENTS",
]
