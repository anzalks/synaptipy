#!/usr/bin/env python3
"""Bump the Synaptipy version across all canonical locations.

Usage
-----
    python scripts/bump_version.py 0.1.2b3
    python scripts/bump_version.py 1.0.0
    python scripts/bump_version.py 0.1.2b3 --dry-run   # preview only, no writes

Required update targets
-----------------------
- pyproject.toml             — version = "X.Y.Z"
- src/synaptipy/__init__.py  — __version__ = "X.Y.Z"
- CITATION.cff               — version: "X.Y.Z" and date-released → today
- installer/windows_setup.iss — installer version string
- installer/linux/synaptipy.desktop — X-AppVersion field
- CHANGELOG.md               — prepends a new [X.Y.Z] section under [Unreleased]

The script also updates matching release references in ``docs/references.md``,
``paper/envs/*.txt``, and ``README.md`` when they exist.  Those legacy or
derived references are optional and cause a warning, not a failed bump.

What this script NEVER touches
--------------------------------
- Any >=, <, == dependency constraint in any file.
- environment.yml or requirements.txt package pins.

The script requires a clean Git working tree, commits its own changes, and
creates a local annotated ``v<NEW_VERSION>`` tag.  It never pushes a branch or
tag and never dispatches a remote workflow.  Run the critical verification
checks before manually pushing the commit and tag.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

from packaging.version import InvalidVersion, Version

ROOT = Path(__file__).resolve().parent.parent


def _run_git(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    """Run Git from the repository root."""
    return subprocess.run(["git", *args], cwd=str(ROOT), text=True, check=check, capture_output=True)


def _require_clean_worktree(new_version: str) -> None:
    """Require a clean repository and a new local release tag before writing."""
    try:
        _run_git("rev-parse", "--is-inside-work-tree")
    except subprocess.CalledProcessError as exc:
        raise RuntimeError("bump_version.py must run inside a Git working tree") from exc

    status = _run_git("status", "--porcelain").stdout.strip()
    if status:
        raise RuntimeError(
            "Working tree is not clean. Commit, stash, or discard existing changes before bumping a version."
        )

    tag = f"v{new_version}"
    if _run_git("rev-parse", "-q", "--verify", f"refs/tags/{tag}", check=False).returncode == 0:
        raise RuntimeError(f"Local tag {tag} already exists. Choose a new version or remove that tag deliberately.")


def _validate_versions(old_version: str, new_version: str) -> None:
    """Require a valid, forward PEP 440 version bump."""
    try:
        old = Version(old_version)
        new = Version(new_version)
    except InvalidVersion as exc:
        raise ValueError(f"Versions must follow PEP 440: {exc}") from exc
    if new <= old:
        raise ValueError(f"New version {new_version} must be greater than current version {old_version}.")


def _require_bump_targets(old_version: str) -> None:
    """Fail before writing if a canonical version marker has drifted."""
    required_markers = {
        ROOT / "pyproject.toml": f'version = "{old_version}"',
        ROOT / "src" / "synaptipy" / "__init__.py": f'__version__ = "{old_version}"',
        ROOT / "CITATION.cff": f'version: "{old_version}"',
        ROOT / "installer" / "windows_setup.iss": f'#define MyAppVersion "{old_version}"',
        ROOT / "installer" / "linux" / "synaptipy.desktop": f"X-AppVersion={old_version}",
        ROOT / "CHANGELOG.md": "## [Unreleased]",
    }
    problems = []
    for path, marker in required_markers.items():
        if not path.exists():
            problems.append(f"missing {path.relative_to(ROOT)}")
        elif marker not in path.read_text(encoding="utf-8"):
            problems.append(f"missing marker {marker!r} in {path.relative_to(ROOT)}")
    citation = ROOT / "CITATION.cff"
    if citation.exists() and not re.search(r'date-released: "\d{4}-\d{2}-\d{2}"', citation.read_text(encoding="utf-8")):
        problems.append("missing a valid date-released marker in CITATION.cff")
    if problems:
        raise RuntimeError("Version bump preflight failed:\n- " + "\n- ".join(problems))


def _replace(path: Path, old: str, new: str, *, dry_run: bool = False) -> None:
    """Replace the first occurrence of *old* with *new* in *path*."""
    if not path.exists():
        print(f"  WARNING: file not found: {path.relative_to(ROOT)}")
        return
    text = path.read_text(encoding="utf-8")
    if old not in text:
        print(f"  WARNING: '{old}' not found in {path.relative_to(ROOT)}")
        return
    if dry_run:
        print(f"  [dry-run] would update {path.relative_to(ROOT)}")
        print(f"    - {old!r}")
        print(f"    + {new!r}")
    else:
        path.write_text(text.replace(old, new, 1), encoding="utf-8")
        print(f"  updated {path.relative_to(ROOT)}")


def _replace_all(path: Path, old: str, new: str, *, dry_run: bool = False) -> None:
    """Replace *all* occurrences of *old* with *new* in *path*."""
    if not path.exists():
        print(f"  WARNING: file not found: {path.relative_to(ROOT)}")
        return
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count == 0:
        print(f"  WARNING: '{old}' not found in {path.relative_to(ROOT)}")
        return
    if dry_run:
        print(f"  [dry-run] would update {path.relative_to(ROOT)} ({count} occurrence(s))")
        print(f"    - {old!r}")
        print(f"    + {new!r}")
    else:
        path.write_text(text.replace(old, new), encoding="utf-8")
        print(f"  updated {path.relative_to(ROOT)} ({count} occurrence(s))")


def bump(old_version: str, new_version: str, *, dry_run: bool = False) -> None:
    """Perform all version-string replacements."""
    today = date.today().isoformat()

    label = "[DRY RUN] " if dry_run else ""
    print(f"{label}Bumping {old_version} -> {new_version}")

    # pyproject.toml
    _replace(
        ROOT / "pyproject.toml",
        f'version = "{old_version}"',
        f'version = "{new_version}"',
        dry_run=dry_run,
    )

    # src/synaptipy/__init__.py
    _replace(
        ROOT / "src" / "synaptipy" / "__init__.py",
        f'__version__ = "{old_version}"',
        f'__version__ = "{new_version}"',
        dry_run=dry_run,
    )

    # CITATION.cff
    _replace(
        ROOT / "CITATION.cff",
        f'version: "{old_version}"',
        f'version: "{new_version}"',
        dry_run=dry_run,
    )
    _replace(
        ROOT / "CITATION.cff",
        re.search(r'date-released: "\d{4}-\d{2}-\d{2}"', (ROOT / "CITATION.cff").read_text(encoding="utf-8")).group(),
        f'date-released: "{today}"',
        dry_run=dry_run,
    )

    # docs/conf.py — version is now read dynamically from pyproject.toml;
    # no hardcoded string to bump.

    # docs/references.md
    _replace(
        ROOT / "docs" / "references.md",
        f"Visualization and Analysis Suite (v{old_version}).",
        f"Visualization and Analysis Suite (v{new_version}).",
        dry_run=dry_run,
    )

    # paper/envs/*.txt
    envs_dir = ROOT / "paper" / "envs"
    if envs_dir.exists():
        for env_file in envs_dir.glob("*.txt"):
            _replace(
                env_file,
                f"# Synaptipy version: {old_version}",
                f"# Synaptipy version: {new_version}",
                dry_run=dry_run,
            )

    # installer/windows_setup.iss
    _replace(
        ROOT / "installer" / "windows_setup.iss",
        f'#define MyAppVersion "{old_version}"',
        f'#define MyAppVersion "{new_version}"',
        dry_run=dry_run,
    )

    # installer/linux/synaptipy.desktop
    _replace(
        ROOT / "installer" / "linux" / "synaptipy.desktop",
        f"X-AppVersion={old_version}",
        f"X-AppVersion={new_version}",
        dry_run=dry_run,
    )

    # README.md — replace all inline version references in the Standalone section
    _replace_all(ROOT / "README.md", old_version, new_version, dry_run=dry_run)

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
        new_text = text.replace(marker + "\n", marker + "\n\n" + new_section, 1)

        # Manage link-reference anchors at the bottom of CHANGELOG
        unreleased_anchor = f"[Unreleased]: https://github.com/anzalks/synaptipy/compare/v{new_version}...HEAD"
        new_anchor = f"[{new_version}]: https://github.com/anzalks/synaptipy/compare/v{old_version}...v{new_version}"
        old_anchor_key = f"[{old_version}]:"
        if old_anchor_key in new_text:
            # Anchors already exist — prepend the new version's compare link
            new_text = new_text.replace(old_anchor_key, f"{new_anchor}\n{old_anchor_key}", 1)
            # Update the [Unreleased]: line to point at the new tag
            new_text = re.sub(r"\[Unreleased\]:.*", unreleased_anchor, new_text)
            anchor_action = "updated existing anchors"
        else:
            # No anchors yet — seed a fresh block at the end of the file.
            # [old_version] gets a tag link (no prior version known); future bumps
            # will replace it with a compare link automatically.
            old_tag_anchor = f"[{old_version}]: https://github.com/anzalks/synaptipy/releases/tag/v{old_version}"
            new_text = (
                new_text.rstrip("\n") + "\n\n" + unreleased_anchor + "\n" + new_anchor + "\n" + old_tag_anchor + "\n"
            )
            anchor_action = "seeded fresh anchor block (first-time)"

        if dry_run:
            print("  [dry-run] would update CHANGELOG.md")
            print(f"    inserted: ## [{new_version}] - {today}")
            print(f"    anchors:  {anchor_action}")
            print(f"    [Unreleased]: ...compare/v{new_version}...HEAD")
            print(f"    [{new_version}]: ...compare/v{old_version}...v{new_version}")
        else:
            changelog.write_text(new_text, encoding="utf-8")
            print("  updated CHANGELOG.md")


def _detect_current_version() -> str:
    """Read current version from pyproject.toml."""
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    m = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    if not m:
        raise RuntimeError("Could not detect current version from pyproject.toml")
    return m.group(1)


def _git_commit_and_tag(new_version: str) -> None:
    """Commit the clean version bump and create its local annotated tag."""
    _run_git("add", "-A")
    _run_git("commit", "-m", f"chore: bump version to {new_version}")
    _run_git("tag", "-a", f"v{new_version}", "-m", f"Synaptipy v{new_version}")
    print(f"  Committed: chore: bump version to {new_version}")
    print(f"  Created local tag: v{new_version}")


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
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview every change without writing any files or running git commands.",
    )
    args = parser.parse_args()

    old = args.old_version or _detect_current_version()
    new = args.new_version

    if old == new:
        print(f"Version is already {new}. Nothing to do.")
        sys.exit(0)

    _validate_versions(old, new)
    if not args.dry_run:
        _require_clean_worktree(new)
    _require_bump_targets(old)

    bump(old, new, dry_run=args.dry_run)

    if args.dry_run:
        print("\n[DRY RUN] No files were written. No git commands were run.")
        print("Run without --dry-run to apply these changes.")
        return

    print(f"\nDone. All files updated from {old} to {new}.")
    _git_commit_and_tag(new)
    print("\nVerify the committed release locally before pushing it manually:")
    print("  conda run -n synaptipy python scripts/verify_ci.py")
    print("  git push origin <branch>")
    print(f"  git push origin v{new}")


if __name__ == "__main__":
    main()
