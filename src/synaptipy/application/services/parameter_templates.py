"""
Parameter Template Manager
==========================

Allows users to save and load analysis parameter configurations as JSON
templates. Templates persist between sessions and can be shared between
lab members for standardised analysis workflows.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)

DEFAULT_TEMPLATE_DIR = Path.home() / ".synaptipy" / "templates"


class ParameterTemplateManager:
    """Manages save/load of analysis parameter templates."""

    def __init__(self, template_dir: Optional[Path] = None):
        self.template_dir = template_dir or DEFAULT_TEMPLATE_DIR
        self.template_dir.mkdir(parents=True, exist_ok=True)

    def save_template(
        self,
        name: str,
        parameters: Dict[str, Any],
        description: str = "",
        analysis_type: str = "",
    ) -> Path:
        """Save a parameter set as a named template."""
        template = {
            "name": name,
            "description": description,
            "analysis_type": analysis_type,
            "parameters": parameters,
            "version": "1.0",
        }
        path = self.template_dir / f"{name}.json"
        path.write_text(json.dumps(template, indent=2, default=str))
        log.info(f"Saved parameter template: {path}")
        return path

    def load_template(self, name: str) -> Optional[Dict[str, Any]]:
        """Load a named template. Returns None if not found."""
        path = self.template_dir / f"{name}.json"
        if not path.exists():
            log.warning(f"Template not found: {path}")
            return None
        data = json.loads(path.read_text())
        return data.get("parameters", {})

    def list_templates(self, analysis_type: str = "") -> List[Dict[str, str]]:
        """List available templates, optionally filtered by analysis type."""
        templates = []
        for p in sorted(self.template_dir.glob("*.json")):
            try:
                data = json.loads(p.read_text())
                if analysis_type and data.get("analysis_type") != analysis_type:
                    continue
                templates.append(
                    {
                        "name": data.get("name", p.stem),
                        "description": data.get("description", ""),
                        "analysis_type": data.get("analysis_type", ""),
                        "path": str(p),
                    }
                )
            except (json.JSONDecodeError, KeyError):
                continue
        return templates

    def delete_template(self, name: str) -> bool:
        """Delete a template by name."""
        path = self.template_dir / f"{name}.json"
        if path.exists():
            path.unlink()
            return True
        return False

    def get_builtin_templates(self) -> List[Dict[str, Any]]:
        """Return built-in workflow templates for common protocols."""
        return [
            {
                "name": "Standard IV Protocol",
                "description": "Hyperpolarising current steps for passive properties",
                "analysis_type": "passive_properties",
                "parameters": {
                    "baseline_start_s": 0.0,
                    "baseline_end_s": 0.1,
                    "response_start_s": 0.1,
                    "response_end_s": 0.6,
                    "rs_artifact_blanking_ms": 0.5,
                },
            },
            {
                "name": "Synaptic Event Screening",
                "description": "Adaptive threshold for spontaneous mEPSC/mIPSC detection",
                "analysis_type": "synaptic_events",
                "parameters": {
                    "detection_method": "adaptive_threshold",
                    "threshold_factor": 3.5,
                    "min_amplitude_mv": 0.2,
                    "direction": "negative",
                    "filter_freq_hz": 1000,
                },
            },
            {
                "name": "Plasticity Experiment",
                "description": "Evoked response monitoring for LTP/LTD protocols",
                "analysis_type": "evoked_responses",
                "parameters": {
                    "stimulus_artifact_ms": 1.0,
                    "response_window_ms": 50.0,
                    "baseline_window_ms": 10.0,
                },
            },
            {
                "name": "Fast-Spiking Interneurons",
                "description": "Parameters adjusted for PV+ fast-spiking interneurons",
                "analysis_type": "spike_analysis",
                "parameters": {
                    "dvdt_threshold": 30.0,
                    "refractory_ms": 1.0,
                    "threshold_mv": -25.0,
                    "fahp_window_ms": [0.5, 3.0],
                    "mahp_window_ms": [5.0, 30.0],
                },
            },
        ]
