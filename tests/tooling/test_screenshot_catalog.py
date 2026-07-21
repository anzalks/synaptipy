"""Regression checks for the published documentation screenshot catalog."""

import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_DOCS = _ROOT / "docs"
_SCREENSHOTS = _DOCS / "tutorial" / "screenshots"
_REFERENCE = re.compile(r"(?:tutorial/)?screenshots/([A-Za-z0-9_.-]+\.png)")


def _documented_screenshots():
    references = set()
    for doc in _DOCS.rglob("*.md"):
        references.update(_REFERENCE.findall(doc.read_text(encoding="utf-8")))
    for doc in _DOCS.rglob("*.rst"):
        references.update(_REFERENCE.findall(doc.read_text(encoding="utf-8")))
    return references


def test_every_documented_screenshot_is_present():
    """Published Markdown/RST image references must resolve in the source tree."""
    missing = sorted(name for name in _documented_screenshots() if not (_SCREENSHOTS / name).is_file())
    assert not missing, f"Missing documentation screenshot assets: {', '.join(missing)}"


def test_capture_runner_uses_dark_isolated_grouped_workflow():
    """Guard the reproducibility contract of the headless capture runner."""
    source = (_ROOT / "scripts" / "capture_screenshots.py").read_text(encoding="utf-8")

    assert "ThemeMode.DARK" in source
    assert 'TemporaryDirectory(prefix="synaptipy-docs-plugins-")' in source
    for group in ("core", "exporter", "miniml", "spikeinterface"):
        assert f'"{group}"' in source
