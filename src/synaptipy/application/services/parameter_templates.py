"""
Parameter Template Manager
==========================

Allows users to save and load analysis parameter configurations as JSON
templates. Templates persist between sessions and can be shared between
lab members for standardised analysis workflows.
"""

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)

DEFAULT_TEMPLATE_DIR = Path.home() / ".synaptipy" / "templates"


class ParameterTemplateManager:
    """Manages save/load of analysis parameter templates."""

    def __init__(self, template_dir: Optional[Path] = None):
        self.template_dir = template_dir or DEFAULT_TEMPLATE_DIR
        self.template_dir.mkdir(parents=True, exist_ok=True)

    def _path_for(self, name: str) -> Path:
        """Return a safe JSON file path inside template_dir for template *name*."""
        sanitized = re.sub(r'[/\\:*?"<>|\x00]', "_", str(name))
        sanitized = sanitized.strip(" .")
        if not sanitized or sanitized in (".", ".."):
            sanitized = "template"
        return self.template_dir / f"{sanitized}.json"

    def _find_stored_path(self, name: str) -> Optional[Path]:
        """Locate the template file for *name* by sanitized filename or stored JSON name."""
        direct = self._path_for(name)
        if direct.exists():
            return direct
        for candidate in sorted(self.template_dir.glob("*.json")):
            try:
                data = json.loads(candidate.read_text(encoding="utf-8"))
                if isinstance(data, dict) and data.get("name") == name:
                    return candidate
            except (OSError, json.JSONDecodeError):
                continue
        return None

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
        path = self._path_for(name)
        path.write_text(json.dumps(template, indent=2, default=str), encoding="utf-8")
        log.info(f"Saved parameter template: {path}")
        return path

    def load_template(self, name: str) -> Optional[Dict[str, Any]]:
        """Load a named template. Returns None if not found."""
        path = self._find_stored_path(name)
        if path is None or not path.exists():
            log.warning(f"Template not found: {self._path_for(name)}")
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return data.get("parameters", {})

    def list_templates(self, analysis_type: str = "") -> List[Dict[str, str]]:
        """List available templates, optionally filtered by analysis type."""
        templates = []
        for p in sorted(self.template_dir.glob("*.json")):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
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
            except (OSError, json.JSONDecodeError, KeyError, AttributeError):
                continue
        return templates

    def delete_template(self, name: str) -> bool:
        """Delete a template by name."""
        path = self._find_stored_path(name)
        if path is not None and path.exists():
            path.unlink()
            return True
        return False

    def get_builtin_templates(self) -> List[Dict[str, Any]]:
        """Return built-in workflow templates for common protocols."""
        return [
            {
                "name": "Standard IV Protocol",
                "description": "Hyperpolarising current steps for passive properties",
                "analysis_type": "iv_curve_analysis",
                "parameters": {
                    "start_current": -50.0,
                    "step_current": 10.0,
                    "baseline_start": 0.0,
                    "baseline_end": 0.1,
                    "response_start": 0.3,
                    "response_end": 0.4,
                },
            },
            {
                "name": "Synaptic Event Screening",
                "description": "Adaptive threshold for spontaneous mEPSC/mIPSC detection",
                "analysis_type": "event_detection_threshold",
                "parameters": {
                    "threshold": 5.0,
                    "direction": "negative",
                    "refractory_period": 0.005,
                    "rolling_baseline_window_ms": 100.0,
                    "use_quiescent_noise_floor": True,
                },
            },
            {
                "name": "Plasticity Experiment",
                "description": "Evoked response monitoring for paired-pulse / LTP/LTD protocols",
                "analysis_type": "paired_pulse_ratio",
                "parameters": {
                    "use_ttl": True,
                    "n_pulses": 2,
                    "polarity": "negative",
                    "response_window_ms": 20.0,
                    "baseline_window_ms": 5.0,
                    "artifact_blanking_ms": 1.0,
                },
            },
            {
                "name": "Fast-Spiking Interneurons",
                "description": "Parameters adjusted for PV+ fast-spiking interneurons",
                "analysis_type": "spike_detection",
                "parameters": {
                    "threshold": -25.0,
                    "refractory_period": 0.001,
                    "dvdt_threshold": 30.0,
                    "ahp_window": 0.03,
                    "fahp_window_ms": [0.5, 3.0],
                    "mahp_window_ms": [5.0, 30.0],
                },
            },
        ]
