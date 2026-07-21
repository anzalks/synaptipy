#!/usr/bin/env python3
"""Reject internal engineering material in published documentation inputs."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
OFFLINE_HTML = ROOT / "src" / "synaptipy" / "resources" / "docs" / "html"
FORBIDDEN_PATH_PARTS = ("development_logs", "_INTERNAL_")
FORBIDDEN_TEXT = ("AI Model Refactoring Guide", "step-by-step guide for an AI model")


def _find_violations(root: Path, suffixes: tuple[str, ...]) -> list[Path]:
    if not root.exists():
        return []
    violations = []
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in suffixes:
            continue
        relative = path.relative_to(root).as_posix()
        if any(part in relative for part in FORBIDDEN_PATH_PARTS):
            violations.append(path)
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if any(marker in text for marker in FORBIDDEN_TEXT):
            violations.append(path)
    return violations


def main() -> int:
    violations = _find_violations(DOCS, (".md", ".rst"))
    violations.extend(_find_violations(OFFLINE_HTML, (".html", ".txt")))
    if not violations:
        print("Published documentation contains no internal engineering material.")
        return 0
    print("Internal material found in published documentation:", file=sys.stderr)
    for path in violations:
        print(f"- {path.relative_to(ROOT)}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
