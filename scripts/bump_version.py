#!/usr/bin/env python3
"""Bump the Synaptipy version across all canonical locations.

Usage
-----
    python scripts/bump_version.py 0.1.2b3
    python scripts/bump_version.py 1.0.0

Files updated
-------------
- pyproject.toml          — version = "X.Y.Z"
- src/Synaptipy/__init__.py — __version__ = "X.Y.Z"
- CITATION.cff            — version: "X.Y.Z" and date-released → today
- docs/conf.py            — version and release fields
- installer/windows_setup.iss — installer version string
- installer/linux/synaptipy.desktop — X-AppVersion field
- README.md               — installer filename strings vX.Y.Z
- CHANGELOG.md            — prepends a new [X.Y.Z] section under [Unreleased]

What this script NEVER touches
--------------------------------
- Any >=, <, == dependency constraint in any file.
- environment.yml or requirements.txt package pins.

After running this script commit all changes with::

    git add -A && git commit -m "chore: bump version to <NEW_VERSION>"

The script will then create a local git tag automatically.
Pushing the commit and tag to the remote is always a manual step.
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _replace(path: Path, old: str, new: str) -> None:
    """Replace the first occurrence of *old* with *new* in *path*."""
    text = path.read_text(encoding="utf-8")
    if old not in text:
        print(f"  WARNING: '{old}' not found in {path.relative_to(ROOT)}")
        return
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    print(f"  updated {path.relative_to(ROOT)}")


def _replace_all(path: Path, old: str, new: str) -> None:
    """Replace *all* occurrences of *old* with *new* in *path*."""
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count == 0:
        print(f"  WARNING: '{old}' not found in {path.relative_to(ROOT)}")
        return
    path.write_text(text.replace(old, new), encoding="utf-8")
    print(f"  updated {path.relative_to(ROOT)} ({count} occurrence(s))")


def bump(old_version: str, new_version: str) -> None:
    """Perform all version-string replacements."""
    today = date.today().isoformat()

    print(f"Bumping {old_version} -> {new_version}")

    # pyproject.toml
    _replace(
        ROOT / "pyproject.toml",
        f'version = "{old_version}"',
        f'version = "{new_version}"',
    )

    # src/Synaptipy/__init__.py
    _replace(
        ROOT / "src" / "Synaptipy" / "__init__.py",
        f'__version__ = "{old_version}"',
        f'__version__ = "{new_version}"',
    )

    # CITATION.cff
    _replace(
        ROOT / "CITATION.cff",
        f'version: "{old_version}"',
        f'version: "{new_version}"',
    )
    _replace(
        ROOT / "CITATION.cff",
        re.search(r'date-released: "\d{4}-\d{2}-\d{2}"', (ROOT / "CITATION.cff").read_text(encoding="utf-8")).group(),
        f'date-released: "{today}"',
    )

    # docs/conf.py
    _replace(
        ROOT / "docs" / "conf.py",
        f'version = "{old_version}"',
        f'version = "{new_version}"',
    )
    _replace(
        ROOT / "docs" / "conf.py",
        f'release = "{old_version}"',
        f'release = "{new_version}"',
    )

    # installer/windows_setup.iss
    _replace(
        ROOT / "installer" / "windows_setup.iss",
        f'#define MyAppVersion "{old_version}"',
        f'#define MyAppVersion "{new_version}"',
    )

    # installer/linux/synaptipy.desktop
    _replace(
        ROOT / "installer" / "linux" / "synaptipy.desktop",
        f"X-AppVersion={old_version}",
        f"X-AppVersion={new_version}",
    )

    # README.md — replace all inline version references in the Standalone section
    _replace_all(ROOT / "README.md", old_version, new_version)

    # CHANGELOG.md — insert new section header after [Unreleased]
    changelog = ROOT / "CHANGELOG.md"
    text = changelog.read_text(encoding="utf-8")
    new_section = (
        f"## [{new_version}] - {today}\n\n"
        f"### Changed\n\n"
        f"- Bumped version to `{new_version}` across all canonical locations.\n\n"
    )
    marker = "## [Unreleased]"
    if marker not in text:
        print(f"  WARNING: '{marker}' not found in CHANGELOG.md - skipping section insert")
    else:
        # Insert after the [Unreleased] line (and any trailing blank lines)
        text = text.replace(
            marker + "\n",
            marker + "\n\n" + new_section,
            1,
        )
        # Also update the old-version link anchor at the bottom if present
        text = text.replace(
            f"[{old_version}]:",
            f"[{new_version}]: https://github.com/anzalks/synaptipy/compare/v{old_version}...v{new_version}\n"
            f"[{old_version}]:",
        )
        changelog.write_text(text, encoding="utf-8")
        print("  updated CHANGELOG.md")


def _detect_current_version() -> str:
    """Read current version from pyproject.toml."""
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    m = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    if not m:
        raise RuntimeError("Could not detect current version from pyproject.toml")
    return m.group(1)


def main() -> None:
    """Entry point."""
    parser = argparse.ArgumentParser(
        description="Bump Synaptipy version across all canonical locations.",
    )
    parser.add_argument("new_version", help="New version string, e.g. 0.1.2b3")
    parser.add_argument(
        "--old-version",
        default=None,
        help="Old version to replace (auto-detected from pyproject.toml if omitted)",
    )
    args = parser.parse_args()

    old = args.old_version or _detect_current_version()
    new = args.new_version

    if old == new:
        print(f"Version is already {new}. Nothing to do.")
        sys.exit(0)

    bump(old, new)
    print(f"\nDone. All files updated from {old} to {new}.")
    print("Next steps:")
    print(f"  git add -A && git commit -m 'chore: bump version to {new}'")
    print(f"  git tag v{new}   ← the script offers to do this for you below")
    print("  git push origin <branch> --tags   ← always manual")
    print()

    # Offer to create the local tag automatically
    import subprocess
    answer = input(f"Create local tag v{new} now? [y/N] ").strip().lower()
    if answer == "y":
        try:
            subprocess.run(
                ["git", "tag", f"v{new}"],
                check=True,
                cwd=str(ROOT),
            )
            print(f"  Tagged v{new} locally. Push with: git push origin v{new}")
        except subprocess.CalledProcessError as exc:
            print(f"  WARNING: git tag failed: {exc}")
    else:
        print(f"  Skipped tagging. Run manually: git tag v{new}")


if __name__ == "__main__":
    main()
