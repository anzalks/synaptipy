"""
Methods Text Generator
======================

Generates publication-ready methods paragraphs describing the analysis
pipeline, parameters, and software version used. Designed for direct
copy-paste into a paper's Methods section.
"""

import platform
from datetime import datetime
from typing import Any, Dict, List

import synaptipy

# Canonical primary literature citations mapped by normalized analysis keyword.
_ANALYSIS_CITATIONS: List[tuple] = [
    (("rmp", "resting membrane"), "Hamill et al., 1981"),
    (("rin", "input resistance", "iv_curve", "i-v"), "Hamill et al., 1981; Robinson & Siegelbaum, 2003"),
    (("tau", "time constant"), "Rall, 1969; Spruston & Johnston, 1992"),
    (("sag",), "Robinson & Siegelbaum, 2003"),
    (("capacitance",), "Lindau & Neher, 1988; Golowasch et al., 2009; Taylor, 2012"),
    (("phase_plane", "phase plane"), "Jenerick, 1963; Bean, 2007"),
    (("spike_detection", "spike detection", "single_spike"), "Hodgkin & Huxley, 1952; Storm, 1987; Bean, 2007"),
    (("excitability", "f-i", "fi_curve"), "Connors & Gutnick, 1990; Gouwens et al., 2019"),
    (("burst",), "Grace & Bunney, 1984; Harris et al., 2001"),
    (("train_dynamics", "train dynamics"), "Holt et al., 1996; Shinomoto et al., 2003"),
    (("template", "deconvolution"), "Clements & Bekkers, 1997; Rall, 1967; Hampel, 1974"),
    (("event", "synaptic"), "Clements & Bekkers, 1997; Jonas et al., 1993; Hampel, 1974"),
    (("opto", "evoked sync"), "Sabatini & Regehr, 1999; Boyden et al., 2005"),
    (("paired_pulse", "paired-pulse", "ppr"), "Kim & Alger, 2001; Zucker & Regehr, 2002; Thanawala & Regehr, 2013"),
    (("stimulus_train", "stimulus train", "stp"), "Zucker & Regehr, 2002; Wesseling & Lo, 2002; Regehr, 2012"),
    (
        ("filter", "lowpass", "highpass", "bandpass"),
        "Colquhoun & Sigworth, 1995; Gustafsson, 1996; Widmann et al., 2015",
    ),
]


def _resolve_analysis_citation(name: str) -> str:
    """Return canonical in-text citation string for an analysis name, or empty string."""
    norm = name.strip().lower()
    for keys, citation in _ANALYSIS_CITATIONS:
        if any(k in norm for k in keys):
            return citation
    return ""


class MethodsGenerator:
    """Generates methods text for publication."""

    def generate_methods_paragraph(
        self,
        analyses_performed: List[Dict[str, Any]],
        file_format: str = "",
        n_cells: int = 0,
        n_recordings: int = 0,
    ) -> str:
        """
        Generate a complete methods paragraph.

        Parameters
        ----------
        analyses_performed : list of dict
            Each dict has keys: 'name', 'parameters' (dict of param:value)
        file_format : str
            Recording file format (e.g., "Axon Binary Format (ABF)")
        n_cells : int
            Number of cells analyzed
        n_recordings : int
            Number of recordings
        """
        version = getattr(synaptipy, "__version__", "unknown")

        parts = []
        parts.append(
            f"Electrophysiology data were analyzed using Synaptipy v{version} "
            f"(Shahul, 2026; https://github.com/anzalks/synaptipy) "
            f"running on Python {platform.python_version()} "
            f"with Neo I/O (Garcia et al., 2014) and SciPy/NumPy (Virtanen et al., 2020; Harris et al., 2020). "
        )

        if file_format:
            parts.append(f"Recordings were acquired in {file_format} format. ")

        if n_cells or n_recordings:
            parts.append(f"A total of {n_recordings} recordings from {n_cells} cells were analyzed. ")

        for analysis in analyses_performed:
            name = analysis.get("name", "")
            params = analysis.get("parameters", {})
            if name and params:
                param_str = ", ".join(f"{k}={v}" for k, v in sorted(params.items()))
                cite = _resolve_analysis_citation(name)
                cite_suffix = f" ({cite})" if cite else ""
                parts.append(f"{name} was performed with parameters: {param_str}{cite_suffix}. ")

        parts.append(
            f"Analysis was performed on {datetime.now().strftime('%Y-%m-%d')}. "
            f"Full parameter sets and raw results are available in the "
            f"exported NWB files (Rubel et al., 2022)."
        )

        return "".join(parts)

    def generate_software_citation(self) -> str:
        """Generate the software citation string."""
        version = getattr(synaptipy, "__version__", "unknown")
        return (
            f"Shahul, A. K. (2026). Synaptipy: An open-source electrophysiology "
            f"visualization and analysis suite (Version {version}). "
            f"https://github.com/anzalks/synaptipy"
        )

    def generate_analysis_summary(
        self,
        analyses_performed: List[Dict[str, Any]],
    ) -> str:
        """Generate a structured summary table (markdown) of all analyses."""
        version = getattr(synaptipy, "__version__", "unknown")
        lines = [
            f"| Software | Synaptipy v{version} |",
            f"| Python | {platform.python_version()} |",
            f"| Platform | {platform.system()} {platform.release()} |",
            f"| Date | {datetime.now().strftime('%Y-%m-%d %H:%M')} |",
            "",
            "| Analysis | Parameters |",
            "|----------|-----------|",
        ]
        for a in analyses_performed:
            name = a.get("name", "unknown")
            params = a.get("parameters", {})
            param_str = "; ".join(f"{k}={v}" for k, v in params.items())
            lines.append(f"| {name} | {param_str} |")

        return "\n".join(lines)
