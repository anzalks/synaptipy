# Release Process

This guide is for maintainers preparing a Synaptipy release. It documents the
local-first release workflow; `scripts/bump_version.py` never pushes to GitHub
or triggers a remote workflow on its own.

## Before the version bump

Use the existing `synaptipy` conda environment. Do not change the project's
`PySide6==6.7.3` pin while preparing a release.

Start from the branch you intend to release (`main`) and verify there are no
uncommitted changes:

```bash
git status --short
```

A live bump refuses to run when `git status --short` produces output, when the
target version is not a valid forward PEP 440 version relative to
`pyproject.toml`, or when the target local `vX.Y.Z` tag already exists.

## Create the local release commit and tag

Preview the edit set first with `--dry-run`:

```bash
conda run -n synaptipy python scripts/bump_version.py 0.1.9 --dry-run
```

After reviewing the preview, apply the bump:

```bash
conda run -n synaptipy python scripts/bump_version.py 0.1.9
```

The script updates all canonical release markers atomically:

- `pyproject.toml` and `src/synaptipy/__init__.py`;
- `CITATION.cff` (`version` and `date-released`);
- `installer/windows_setup.iss` (`MyAppVersion`) and `installer/linux/synaptipy.desktop` (`X-AppVersion`);
- `CHANGELOG.md` (promotes `[Unreleased]` into `## [X.Y.Z] - YYYY-MM-DD` and updates comparison anchors).

It also updates matching version strings in `docs/references.md`,
`docs/development/manuals/CROSS_PLATFORM_SETUP.md`, `paper/envs/*.txt`, and
`README.md` when present. It stages all updates with `git add -A`, commits
`chore: bump version to X.Y.Z`, and creates the annotated tag `vX.Y.Z`.

## Verify before publishing

Inspect the generated commit and tag, then run the full local CI verifier:

```bash
git show --stat HEAD
git show --no-patch v0.1.9
conda run -n synaptipy python scripts/verify_ci.py
```

`verify_ci.py` enforces `black`, `isort`, `flake8` syntax and complexity rules,
the headless test suite with the 90-percent coverage threshold, and the
zero-emoji source check.

## Publish deliberately

Push `main` and the annotated `vX.Y.Z` tag together:

```bash
git push origin main && git push origin v0.1.9
```

Pushing `main` and `vX.Y.Z` together coordinates all three GitHub Actions
workflows cleanly:

1. `test.yml` runs the 3x3 OS/Python matrix, dependency bounds, Bandit SAST,
   High-DPI checks, notebooks, and wheel installation on `main`. Its `auto-tag`
   job detects that `vX.Y.Z` already exists on `origin` and skips re-tagging.
   (If you push `main` *without* pushing `vX.Y.Z`, `auto-tag` creates an
   annotated `vX.Y.Z` tag after CI succeeds and dispatches `installer.yml` and
   `release.yml` via `workflow_dispatch` with `dry_run=false`.)
2. `installer.yml` builds and smoke-tests all four standalone installers
   (`Synaptipy-<ver>-x86_64.AppImage`, `Synaptipy_Setup_<ver>.exe`,
   `Synaptipy_<ver>_macOS_arm64.dmg`, and `Synaptipy_<ver>_macOS_x86_64.dmg`).
3. `release.yml` runs tests, strict Sphinx docs + `linkcheck`, builds the wheel
   and sdist (including offline Help artefacts), publishes to TestPyPI and
   verifies clean installation before publishing to PyPI via OIDC Trusted
   Publisher, waits for `installer.yml` to finish, and attaches all four
   desktop installers alongside the wheel and sdist on the GitHub Release.
