#!/usr/bin/env python3
"""Bump the Synaptipy version across all canonical locations.

Usage
-----
    python scripts/bump_version.py 0.1.2b3
    python scripts/bump_version.py 1.0.0
    python scripts/bump_version.py 0.1.2b3 --dry-run   # preview only, no writes

Files updated
-------------
- pyproject.toml          — version = "X.Y.Z"
- src/synaptipy/__init__.py — __version__ = "X.Y.Z"
- CITATION.cff            — version: "X.Y.Z" and date-released → today
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


def _trigger_dry_runs() -> None:
    """Trigger dry-run dispatches for all three CI/CD workflows and print run URLs."""
    import subprocess
    import time

    workflows = [
        ("test.yml", [], "CI tests (9-slot matrix)"),
        ("release.yml", ["--field", "dry_run=true"], "Release (docs + build + PyPI)"),
        ("installer.yml", ["--field", "dry_run=true"], "Installer (Linux/Windows/macOS)"),
    ]

    run_ids = []
    for wf, extra_fields, label in workflows:
        print(f"  Triggering dry run: {label} ...", end=" ", flush=True)
        result = subprocess.run(
            ["gh", "workflow", "run", wf] + extra_fields,
            capture_output=True,
            text=True,
            cwd=str(ROOT),
        )
        if result.returncode != 0:
            print(f"FAILED\n    {result.stderr.strip()}")
            continue
        # GitHub needs a moment before the run appears in the API
        time.sleep(3)
        runs = subprocess.run(
            ["gh", "run", "list", "--workflow", wf, "--limit", "1", "--json", "databaseId,url"],
            capture_output=True,
            text=True,
            cwd=str(ROOT),
        )
        import json as _json

        try:
            data = _json.loads(runs.stdout)
            run_id = data[0]["databaseId"]
            url = data[0]["url"]
            run_ids.append((label, run_id, url))
            print(f"OK → {url}")
        except (KeyError, IndexError, _json.JSONDecodeError):
            print("OK (could not fetch URL — check gh run list)")

    if run_ids:
        print("\nMonitor all runs:")
        for label, run_id, url in run_ids:
            print(f"  gh run watch {run_id}   # {label}")


def _git_commit_and_tag(new_version: str) -> None:
    """Offer to commit changed files then create a local tag."""
    import subprocess

    dirty = subprocess.run(
        ["git", "status", "--porcelain"],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    ).stdout.strip()

    committed = False
    if dirty:
        answer = input("Commit version-bump changes now? [y/N] ").strip().lower()
        if answer == "y":
            try:
                subprocess.run(["git", "add", "-A"], check=True, cwd=str(ROOT))
                subprocess.run(
                    ["git", "commit", "-m", f"chore: bump version to {new_version}"],
                    check=True,
                    cwd=str(ROOT),
                )
                print(f"  Committed: chore: bump version to {new_version}")
                committed = True
            except subprocess.CalledProcessError as exc:
                print(f"  WARNING: git commit failed: {exc}")
        else:
            print("  Skipped commit. Commit before pushing to avoid tagging a dirty tree.")
    else:
        print("  Working tree clean — nothing to commit.")
        committed = True

    if not committed:
        print(f"  Skipped tagging (uncommitted changes present). Commit first, then: git tag v{new_version}")
        return

    answer = input(f"Create local tag v{new_version} now? [y/N] ").strip().lower()
    if answer == "y":
        try:
            subprocess.run(["git", "tag", f"v{new_version}"], check=True, cwd=str(ROOT))
            print(f"  Tagged v{new_version} locally. Push with: git push origin v{new_version}")
        except subprocess.CalledProcessError as exc:
            print(f"  WARNING: git tag failed: {exc}")
    else:
        print(f"  Skipped tagging. Run manually: git tag v{new_version}")


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
    parser.add_argument(
        "--verify",
        action="store_true",
        help=(
            "After bumping, push the branch and trigger dry-run dispatches for "
            "all three workflows (CI tests, release, installer). Requires gh CLI."
        ),
    )
    args = parser.parse_args()

    old = args.old_version or _detect_current_version()
    new = args.new_version

    if old == new:
        print(f"Version is already {new}. Nothing to do.")
        sys.exit(0)

    bump(old, new, dry_run=args.dry_run)

    if args.dry_run:
        print("\n[DRY RUN] No files were written. No git commands were run.")
        print("Run without --dry-run to apply these changes.")
        return

    print(f"\nDone. All files updated from {old} to {new}.")
    print("Next steps:")
    print(f"  git add -A && git commit -m 'chore: bump version to {new}'")
    print(f"  git tag v{new}   ← the script offers to do this for you below")
    print("  git push origin <branch> --tags   ← always manual")
    print()
    _git_commit_and_tag(new)

    if args.verify:
        print("\nPush branch so the dispatched runs can see the new version string.")
        import subprocess

        branch = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            cwd=str(ROOT),
        ).stdout.strip()
        answer = input(f"Push '{branch}' to origin now? [y/N] ").strip().lower()
        if answer == "y":
            subprocess.run(["git", "push", "origin", branch], check=True, cwd=str(ROOT))
            print(f"  Pushed {branch}.")
        else:
            print("  Skipped push — dry-run workflows will run against the previously pushed commit.")
        print()
        _trigger_dry_runs()


if __name__ == "__main__":
    main()
