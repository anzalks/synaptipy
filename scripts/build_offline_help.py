# scripts/build_offline_help.py
# -*- coding: utf-8 -*-
"""
Build pipeline for the Synaptipy offline documentation artefacts.

Steps
-----
1. Run ``sphinx-build -b html`` to produce plain HTML under
   ``docs/_build/html/``.  These files are bundled directly into the pip
   wheel (``resources/docs/html/``) and serve as the tier-2 fallback when
   no ``.qhc`` is found at runtime.
2. Run ``sphinx-build -b qthelp`` to produce the ``.qhp`` project file
   inside ``docs/_build/qthelp/``.
3. Locate the ``qhelpgenerator`` binary (shipped with PySide6's Qt tools or
   available as a system Qt6 package) and invoke it to compile the project
   into a ``.qch`` compressed help file and a ``.qhc`` collection file.
4. Copy the HTML tree into ``src/synaptipy/resources/docs/html/``.
5. Copy the ``.qch`` / ``.qhc`` artefacts into
   ``src/synaptipy/resources/docs/`` so they are picked up by both the
   ``pyproject.toml`` package-data rule and the PyInstaller ``datas`` rule
   in ``synaptipy.spec``.

Usage
-----
    python scripts/build_offline_help.py

The script exits with a non-zero code on the first failure so that CI jobs
detect build problems immediately.

When ``qhelpgenerator`` is not available (step 3 fails to locate the binary)
the script still completes steps 1 and 4, so the HTML fallback is always
bundled even on platforms without Qt6 developer tools installed.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# ---------------------------------------------------------------------------
# Paths - all relative to the repository root
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS_SRC = REPO_ROOT / "docs"
HTML_BUILD = REPO_ROOT / "docs" / "_build" / "html"
QTHELP_BUILD = REPO_ROOT / "docs" / "_build" / "qthelp"
DEST_DIR = REPO_ROOT / "src" / "synaptipy" / "resources" / "docs"
HTML_DEST_DIR = DEST_DIR / "html"

# The sphinx qthelp builder derives these filenames from `qthelp_basename`
# in conf.py.  Keep in sync with the value set there.
QHP_FILE = QTHELP_BUILD / "synaptipy.qhp"
QCH_FILE = QTHELP_BUILD / "synaptipy.qch"
QHC_FILE = QTHELP_BUILD / "synaptipy.qhc"

# QHC collection project: sphinx generates a .qhcp alongside the .qhp.
QHCP_FILE = QTHELP_BUILD / "synaptipy.qhcp"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run(cmd: list, description: str) -> None:
    """Run *cmd* as a subprocess, raising SystemExit on non-zero return code."""
    print(f"\n[build_offline_help] {description}")
    print("  $", " ".join(str(c) for c in cmd))
    result = subprocess.run(cmd, check=False)
    if result.returncode != 0:
        print(f"[build_offline_help] ERROR: '{description}' failed (exit {result.returncode})", file=sys.stderr)
        sys.exit(result.returncode)


def _is_runnable_qhelpgenerator(candidate: Path) -> bool:
    """Return True if *candidate* exists and executes cleanly without missing shared libs."""
    if not candidate.is_file():
        return False
    try:
        probe = subprocess.run(
            [str(candidate), "--version"],
            capture_output=True,
            timeout=10,
            check=False,
        )
        return probe.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def _pyside6_qhelpgenerator_candidates() -> list[Path]:
    """Return wheel-internal ``qhelpgenerator`` paths shipped with PySide6."""
    try:
        import PySide6

        pyside6_dir = Path(PySide6.__file__).parent
        return [
            pyside6_dir / "Qt" / "libexec" / "qhelpgenerator",
            pyside6_dir / "qhelpgenerator",
            pyside6_dir / "qhelpgenerator.exe",
            pyside6_dir / "Qt" / "bin" / "qhelpgenerator.exe",
        ]
    except ImportError:
        return []


def _fuzzy_path_qhelpgenerator_candidates() -> list[Path]:
    """Scan PATH directories for versioned binaries such as ``qhelpgenerator6``."""
    matches: list[Path] = []
    for directory_str in (os.environ.get("PATH") or "").split(os.pathsep):
        if not directory_str:
            continue
        directory = Path(directory_str)
        if not directory.is_dir():
            continue
        for entry in directory.iterdir():
            if "qhelpgenerator" in entry.name.lower() and entry.is_file():
                matches.append(entry)
    return matches


def _find_qhelpgenerator() -> Optional[Path]:
    """Locate a runnable ``qhelpgenerator`` binary, returning *None* if unavailable.

    Search order:
    1. ``qhelpgenerator`` on PATH (system Qt6 install).
    2. Active Python environment's ``bin`` / ``Scripts`` directory - covers
       ``pyside6-tools`` and similar pip-installed Qt helper packages.
    3. Qt tools bundled by the ``pyside6`` pip package (wheel-internal layout).
    4. Fuzzy PATH scan for versioned names like ``qhelpgenerator6``.
    """
    candidates: list[Path] = []
    found = shutil.which("qhelpgenerator")
    if found:
        candidates.append(Path(found))

    py_bin = Path(sys.executable).resolve().parent
    candidates.extend([py_bin / "qhelpgenerator", py_bin / "qhelpgenerator.exe"])
    candidates.extend(_pyside6_qhelpgenerator_candidates())
    candidates.extend(_fuzzy_path_qhelpgenerator_candidates())

    for candidate in candidates:
        if _is_runnable_qhelpgenerator(candidate):
            return candidate

    print(
        "[build_offline_help] Runnable qhelpgenerator not found on PATH or in the pyside6 wheel.",
    )
    return None


# ---------------------------------------------------------------------------
# Build steps
# ---------------------------------------------------------------------------


def step_clean_build_outputs() -> None:
    """Remove prior generated Sphinx output before rebuilding offline help.

    Sphinx leaves pages that have since been excluded in an incremental output
    directory.  A clean rebuild is required so removed internal documentation
    cannot be copied into the packaged HTML fallback or Qt Help archive.
    """
    for output_dir in (HTML_BUILD, QTHELP_BUILD):
        if output_dir.exists():
            shutil.rmtree(output_dir)
            print(f"[build_offline_help] Removed stale build output -> {output_dir}")


def step_sphinx_html() -> None:
    """Step 1: run sphinx-build with the HTML builder (tier-2 fallback docs).

    The HTML output is bundled directly into the pip wheel via the
    ``resources/docs/html/`` package-data rule so that the app shows real
    documentation even on installs where ``qhelpgenerator`` was not available
    at build time.
    """
    _run(
        [sys.executable, "-m", "sphinx", "-b", "html", str(DOCS_SRC), str(HTML_BUILD)],
        "sphinx-build (html builder)",
    )
    if not (HTML_BUILD / "index.html").exists():
        print(
            f"[build_offline_help] ERROR: expected {HTML_BUILD / 'index.html'} was not produced.",
            file=sys.stderr,
        )
        sys.exit(1)


def step_sphinx_qthelp() -> None:
    """Step 2: run sphinx-build with the qthelp builder."""
    _run(
        [sys.executable, "-m", "sphinx", "-b", "qthelp", str(DOCS_SRC), str(QTHELP_BUILD)],
        "sphinx-build (qthelp builder)",
    )
    if not QHP_FILE.exists():
        print(
            f"[build_offline_help] ERROR: expected {QHP_FILE} was not produced by sphinx-build.",
            file=sys.stderr,
        )
        sys.exit(1)


def step_compile_qch(qhelpgenerator: Path) -> None:
    """Step 3a: compile the .qhp project into a .qch compressed help archive."""
    _run(
        [str(qhelpgenerator), str(QHP_FILE), "-o", str(QCH_FILE)],
        "qhelpgenerator -> synaptipy.qch",
    )
    if not QCH_FILE.exists():
        print(f"[build_offline_help] ERROR: {QCH_FILE} was not produced.", file=sys.stderr)
        sys.exit(1)


def step_compile_qhc(qhelpgenerator: Path) -> None:
    """Step 3b: compile the .qhcp collection project into a .qhc index file.

    The .qhc file is the entry point for ``QHelpEngine``; it indexes one or
    more .qch archives and stores the user's bookmarks / custom filters.
    """
    if not QHCP_FILE.exists():
        print(
            f"[build_offline_help] WARNING: {QHCP_FILE} not found - skipping .qhc compilation.\n"
            "  QHelpEngine will fall back to loading the .qch directly.",
        )
        return
    _run(
        [str(qhelpgenerator), str(QHCP_FILE), "-o", str(QHC_FILE)],
        "qhelpgenerator -> synaptipy.qhc",
    )


def step_copy_artefacts() -> None:
    """Step 4: copy HTML tree and compiled Qt Help files into the resources dir.

    The HTML tree lands in ``resources/docs/html/`` and is included in the pip
    wheel via the ``resources/**/*`` package-data glob in ``pyproject.toml``.
    The ``.qch`` / ``.qhc`` files land in ``resources/docs/`` for the
    PyInstaller bundle and for tier-1 QHelpEngine use.
    """
    DEST_DIR.mkdir(parents=True, exist_ok=True)

    # HTML tree (tier-2 fallback - works without qhelpgenerator)
    if HTML_BUILD.exists() and (HTML_BUILD / "index.html").exists():
        if HTML_DEST_DIR.exists():
            shutil.rmtree(HTML_DEST_DIR)
        shutil.copytree(HTML_BUILD, HTML_DEST_DIR)
        print(f"[build_offline_help] Copied HTML tree -> {HTML_DEST_DIR}")
    else:
        print("[build_offline_help] WARNING: HTML build not found; HTML fallback will be unavailable.")

    # Qt Help artefacts (tier-1 QHelpEngine)
    # Explicit makedirs guard: PyInstaller's datas collector walks
    # src/synaptipy/resources/ at spec-parse time and will error if the
    # docs/ subdirectory is missing, even when qhelpgenerator was unavailable.
    os.makedirs(DEST_DIR, exist_ok=True)
    for src in (QCH_FILE, QHC_FILE):
        if src.exists():
            dest = DEST_DIR / src.name
            shutil.copy2(src, dest)
            print(f"[build_offline_help] Copied {src.name} -> {dest}")
        else:
            print(f"[build_offline_help] WARNING: {src.name} not found; skipping copy.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Run the full build pipeline."""
    print("[build_offline_help] Starting offline Help build pipeline...")

    step_clean_build_outputs()

    # Step 1: HTML docs (always succeeds; needed for pip-install tier-2 fallback)
    step_sphinx_html()

    # Step 2: qthelp source tree
    step_sphinx_qthelp()

    # Steps 3a/3b: compile with qhelpgenerator (skipped gracefully if unavailable)
    qhelpgenerator = _find_qhelpgenerator()
    if qhelpgenerator is not None:
        print(f"[build_offline_help] Found qhelpgenerator: {qhelpgenerator}")
        step_compile_qch(qhelpgenerator)
        step_compile_qhc(qhelpgenerator)
    else:
        print(
            "[build_offline_help] WARNING: qhelpgenerator not found - "
            "skipping .qch/.qhc compilation.\n"
            "  The HTML fallback (tier 2) will still be bundled.\n"
            "  Install Qt6 tools for the full QHelpEngine experience:\n"
            "    apt install qt6-tools-dev-tools  OR\n"
            "    brew install qt@6 && export PATH=$(brew --prefix qt@6)/bin:$PATH"
        )

    # Step 4: copy everything into resources/docs/
    step_copy_artefacts()

    print("\n[build_offline_help] Done.  Artefacts in:", DEST_DIR)


if __name__ == "__main__":
    main()
