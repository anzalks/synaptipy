# Release Process

This guide is for maintainers preparing a Synaptipy release. It documents the
current local-first process; the version-bump script never pushes to GitHub or
starts a workflow on its own.

## Before the version bump

Use the existing `synaptipy` conda environment. Do not change the project's
PySide6 pin while preparing a release.

Start from the branch you intend to release and make sure it has no uncommitted
work:

```bash
git status --short
```

The normal bump refuses to run when this command has output. This protects the
script's `git add -A` commit from including unrelated work. It also refuses a
version that is not valid PEP 440, is not greater than the current version, or
would reuse an existing local `vX.Y.Z` tag.

## Create the local release commit and tag

Preview the exact edit set first. A dry run makes no file or Git changes and
is safe while reviewing unrelated local work:

```bash
conda run -n synaptipy python scripts/bump_version.py 0.1.6.2 --dry-run
```

After reviewing the preview, run the same command without `--dry-run`:

```bash
conda run -n synaptipy python scripts/bump_version.py 0.1.6.2
```

The script updates these required release locations:

- `pyproject.toml` and `src/synaptipy/__init__.py`;
- `CITATION.cff`, including its release date;
- the Windows installer version and Linux desktop-entry version;
- `CHANGELOG.md`, including its release comparison links.

It also updates matching release text in `docs/references.md`, the
cross-platform installer guide, versioned paper-environment files, and
`README.md` when present. These derived references are optional: missing text
produces a warning rather than a partial release. The installer guide normally
uses wildcard filenames, so it only changes when a maintainer has deliberately
included a concrete versioned example.

On a normal run, the script stages the resulting clean release update with
`git add -A`, creates the commit `chore: bump version to X.Y.Z`, and creates an
annotated local tag `vX.Y.Z`. It never changes dependency constraints, pushes
a branch or tag, or dispatches a GitHub Actions workflow.

## Verify before publishing

Inspect the generated release commit and tag, then run the local CI verifier in
the same conda environment:

```bash
git show --stat HEAD
git show --no-patch v0.1.6.2
conda run -n synaptipy python scripts/verify_ci.py
```

`verify_ci.py` checks formatting, import order, linting, the primary
90-percent coverage test gate, and the repository's source-text policy. Add
`--with-screenshots` when documentation screenshots are part of the release.
The GitHub workflow remains the cross-platform authority: it runs on Ubuntu,
Windows, and macOS with Python 3.10, 3.11, and 3.12, plus its specialised jobs.

## Publish deliberately

Only after the checks and review are satisfactory, push the release commit and
its tag yourself:

```bash
git push origin <branch>
git push origin v0.1.6.2
```

The branch push starts the normal CI workflow. Pushing the `vX.Y.Z` tag is the
normal release trigger; it starts the release workflow, which rebuilds and
validates the distribution and documentation before its publication jobs.
Manual workflow dispatch defaults to a dry run that produces build artifacts
without publishing. The workflow also exposes a non-dry-run option, so use it
only when an intentional manual publication is required.

For a real publication, the workflow uploads the wheel and source distribution
to TestPyPI first, installs that exact version in a clean environment, and only
then permits the PyPI upload. If TestPyPI or that smoke test is unavailable,
PyPI publishing is skipped; it is never bypassed. The macOS DMG name is derived
from the canonical `pyproject.toml` version at build time, so it has no separate
version string for the bump script to edit.
