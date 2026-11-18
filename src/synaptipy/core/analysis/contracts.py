"""Canonical runtime contracts for registered electrophysiology analyses.

Analysis implementations are allowed to use convenient internal return types,
but every result crossing into the GUI, batch engine, or exporter is represented
by :class:`AnalysisResult`.  Keeping the coercion at this one boundary prevents
each consumer from carrying a different historical normalisation rule.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping

ANALYSIS_RESULT_SCHEMA_VERSION = 1


@dataclass
class AnalysisResult:
    """Stable, serialisable result emitted by a registered analysis."""

    analysis_name: str
    metrics: Dict[str, Any] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    plot_payload: Dict[str, Any] = field(default_factory=dict)
    provenance: Dict[str, Any] = field(default_factory=dict)
    schema_version: int = ANALYSIS_RESULT_SCHEMA_VERSION

    @classmethod
    def _merge_nested_extras(
        cls,
        raw_dict: Dict[str, Any],
        metrics_out: Dict[str, Any],
        plot_payload: Dict[str, Any],
    ) -> None:
        """Preserve top-level 'error' and private '_' overlay keys from plugin dicts."""
        reserved = {"module_used", "analysis_name", "warnings", "provenance", "schema_version"}
        if "error" in raw_dict and "error" not in metrics_out:
            metrics_out["error"] = raw_dict["error"]
        for extra_k, extra_v in raw_dict.items():
            if extra_k in reserved:
                continue
            if str(extra_k).startswith("_"):
                metrics_out.setdefault(extra_k, extra_v)
                plot_payload.setdefault(extra_k, extra_v)

    @classmethod
    def from_raw(cls, analysis_name: str, raw: Any) -> "AnalysisResult":
        """Make one canonical result from an analysis implementation's output.

        This is intentionally the only compatibility boundary.  Existing
        supplied analyses may return flat mappings while plugins transition to
        the schema; consumers never inspect those historical shapes.
        """
        if isinstance(raw, cls):
            return raw
        if isinstance(raw, Mapping):
            raw_dict = dict(raw)
            has_nested_metrics = "metrics" in raw_dict
            metrics = raw_dict.pop("metrics", raw_dict)
            if not isinstance(metrics, Mapping):
                metrics = {"result": metrics}
            metrics_out = dict(metrics)
            plot_payload = dict(raw_dict.pop("plot_payload", {}))
            if has_nested_metrics:
                cls._merge_nested_extras(raw_dict, metrics_out, plot_payload)
            return cls(
                analysis_name=str(raw_dict.pop("analysis_name", analysis_name)),
                metrics=metrics_out,
                warnings=list(raw_dict.pop("warnings", [])),
                plot_payload=plot_payload,
                provenance=dict(raw_dict.pop("provenance", {})),
                schema_version=int(raw_dict.pop("schema_version", ANALYSIS_RESULT_SCHEMA_VERSION)),
            )
        if isinstance(raw, list):
            return cls(analysis_name=analysis_name, metrics={"list_results": raw})
        return cls(analysis_name=analysis_name, metrics={"result": raw})

    def as_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "analysis_name": self.analysis_name,
            "metrics": self.metrics,
            "warnings": self.warnings,
            "plot_payload": self.plot_payload,
            "provenance": self.provenance,
        }

    def export_row(self, **metadata: Any) -> Dict[str, Any]:
        """Flatten only metrics for tabular export, retaining schema provenance."""
        row = dict(self.metrics)
        row.update(metadata)
        row.update(
            {
                "analysis_result_schema_version": self.schema_version,
                "analysis_result_warnings": "; ".join(str(warning) for warning in self.warnings),
            }
        )
        for key, value in self.provenance.items():
            row.setdefault(key, value)
        return row
