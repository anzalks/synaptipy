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
            f"running on Python {platform.python_version()}. "
        )

        if file_format:
            parts.append(f"Recordings were acquired in {file_format} format. ")

        if n_cells or n_recordings:
            parts.append(f"A total of {n_recordings} recordings from {n_cells} cells " f"were analyzed. ")

        for analysis in analyses_performed:
            name = analysis.get("name", "")
            params = analysis.get("parameters", {})
            if name and params:
                param_str = ", ".join(f"{k}={v}" for k, v in sorted(params.items()))
                parts.append(f"{name} was performed with parameters: {param_str}. ")

        parts.append(
            f"Analysis was performed on {datetime.now().strftime('%Y-%m-%d')}. "
            f"Full parameter sets and raw results are available in the "
            f"exported NWB files."
        )

        return "".join(parts)

    def generate_software_citation(self) -> str:
        """Generate the software citation string."""
        version = getattr(synaptipy, "__version__", "unknown")
        return (
            f"Shahul, A. K. (2026). SynaptiPy: An open-source electrophysiology "
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
