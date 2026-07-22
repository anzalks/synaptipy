"""Explicit support tiers for acquisition formats exposed by Synaptipy."""

from dataclasses import asdict, dataclass
from typing import Dict


@dataclass(frozen=True)
class FormatSupport:
    """User-facing confidence statement for a file extension."""

    extension: str
    tier: str
    rationale: str

    def as_dict(self) -> Dict[str, str]:
        return asdict(self)


_VALIDATED = {
    "abf": "Validated with AxonIO, pyABF rescue, protocol extraction, batch analysis, and export tests.",
    "nwb": "Validated with NWBIO, HDF5 rescue, NWB validation, batch analysis, and export tests.",
}


def format_support(extension: str) -> FormatSupport:
    """Return the declared verification tier for one extension."""
    normalized = extension.lower().lstrip(".")
    if normalized in _VALIDATED:
        return FormatSupport(normalized, "validated", _VALIDATED[normalized])
    return FormatSupport(
        normalized,
        "experimental",
        "Reader discovery is delegated to Neo. This format lacks Synaptipy end-to-end validation fixtures.",
    )
