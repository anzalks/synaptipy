"""Release-tool regression tests that do not touch the working repository."""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BUMP_SCRIPT = ROOT / "scripts" / "bump_version.py"
OFFLINE_HELP_SCRIPT = ROOT / "scripts" / "build_offline_help.py"


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=root, text=True, check=True, capture_output=True)


def _release_repo(tmp_path: Path) -> Path:
    root = tmp_path / "release-repo"
    (root / "scripts").mkdir(parents=True)
    shutil.copy2(BUMP_SCRIPT, root / "scripts" / "bump_version.py")
    (root / "src" / "synaptipy").mkdir(parents=True)
    (root / "docs" / "development" / "manuals").mkdir(parents=True)
    (root / "installer" / "linux").mkdir(parents=True)
    (root / "pyproject.toml").write_text('version = "1.0.0"\n', encoding="utf-8")
    (root / "src" / "synaptipy" / "__init__.py").write_text('__version__ = "1.0.0"\n', encoding="utf-8")
    (root / "CITATION.cff").write_text('version: "1.0.0"\ndate-released: "2026-01-01"\n', encoding="utf-8")
    (root / "installer" / "windows_setup.iss").write_text('#define MyAppVersion "1.0.0"\n', encoding="utf-8")
    (root / "installer" / "linux" / "synaptipy.desktop").write_text("X-AppVersion=1.0.0\n", encoding="utf-8")
    (root / "CHANGELOG.md").write_text("## [Unreleased]\n", encoding="utf-8")
    (root / "docs" / "development" / "manuals" / "CROSS_PLATFORM_SETUP.md").write_text(
        "Download Synaptipy_v1.0.0.dmg from the releases page.\n", encoding="utf-8"
    )
    _git(root, "init")
    _git(root, "config", "user.email", "tests@example.invalid")
    _git(root, "config", "user.name", "Synaptipy tests")
    _git(root, "add", ".")
    _git(root, "commit", "-m", "initial")
    return root


def _run_bump(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, "scripts/bump_version.py", *args], cwd=root, text=True, capture_output=True)


def test_bump_dry_run_leaves_repository_unchanged(tmp_path: Path) -> None:
    root = _release_repo(tmp_path)
    result = _run_bump(root, "1.0.1", "--dry-run")
    assert result.returncode == 0, result.stderr
    assert _git(root, "status", "--porcelain").stdout == ""
    assert _git(root, "tag", "--list", "v1.0.1").stdout == ""


def test_bump_commits_and_creates_local_annotated_tag(tmp_path: Path) -> None:
    root = _release_repo(tmp_path)
    result = _run_bump(root, "1.0.1")
    assert result.returncode == 0, result.stderr
    assert _git(root, "status", "--porcelain").stdout == ""
    assert "chore: bump version to 1.0.1" in _git(root, "log", "-1", "--format=%s").stdout
    assert _git(root, "cat-file", "-t", "v1.0.1").stdout.strip() == "tag"
    assert 'version = "1.0.1"' in (root / "pyproject.toml").read_text(encoding="utf-8")
    assert "Synaptipy_v1.0.1.dmg" in (root / "docs" / "development" / "manuals" / "CROSS_PLATFORM_SETUP.md").read_text(
        encoding="utf-8"
    )


def test_bump_rejects_a_dirty_repository(tmp_path: Path) -> None:
    root = _release_repo(tmp_path)
    (root / "notes.txt").write_text("unrelated work\n", encoding="utf-8")
    result = _run_bump(root, "1.0.1")
    assert result.returncode != 0
    assert "Working tree is not clean" in result.stderr


def test_offline_help_cleanup_removes_stale_generated_output(tmp_path: Path) -> None:
    spec = importlib.util.spec_from_file_location("offline_help", OFFLINE_HELP_SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.HTML_BUILD = tmp_path / "html"
    module.QTHELP_BUILD = tmp_path / "qthelp"
    (module.HTML_BUILD / "development_logs").mkdir(parents=True)
    (module.QTHELP_BUILD / "decisions").mkdir(parents=True)
    (module.HTML_BUILD / "development_logs" / "internal.html").write_text("internal", encoding="utf-8")
    (module.QTHELP_BUILD / "decisions" / "internal.qhp").write_text("internal", encoding="utf-8")
    module.step_clean_build_outputs()
    assert not module.HTML_BUILD.exists()
    assert not module.QTHELP_BUILD.exists()
