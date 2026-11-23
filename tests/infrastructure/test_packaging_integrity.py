# -*- coding: utf-8 -*-
"""Packaging, bundle specification, and cross-platform installer regression tests."""

from __future__ import annotations

import io
import os
import subprocess
import sys
from pathlib import Path

from PySide6 import QtCore, QtGui

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _read(rel_path: str) -> str:
    return (PROJECT_ROOT / rel_path).read_text(encoding="utf-8")


class TestDesktopArgumentParsing:
    """Verify packaged GUI entry-point survives OS launcher flags."""

    def test_macos_launchservices_psn_and_cocoa_flags_do_not_exit(self):
        from synaptipy.application.__main__ import parse_arguments

        args = parse_arguments(
            [
                "-psn_0_45067",
                "-NSDocumentRevisionsDebugMode",
                "YES",
                "-ApplePersistenceIgnoreState",
                "YES",
            ]
        )
        assert args.dev is False
        assert args.file is None

    def test_positional_file_from_os_file_association_populates_file(self, tmp_path):
        from synaptipy.application.__main__ import parse_arguments

        sample = tmp_path / "recording.abf"
        sample.write_bytes(b"ABF2")
        args = parse_arguments(["-psn_0_999", str(sample)])
        assert args.file == str(sample)

    def test_explicit_file_flag_takes_precedence(self, tmp_path):
        from synaptipy.application.__main__ import parse_arguments

        explicit = tmp_path / "explicit.nwb"
        other = tmp_path / "other.nwb"
        args = parse_arguments(["--file", str(explicit), str(other)])
        assert args.file == str(explicit)


class TestFrozenEnvironmentAndFileOpen:
    """Verify frozen runtime working directory, MPLCONFIGDIR, and macOS QFileOpenEvent."""

    def test_frozen_root_cwd_relocates_to_home_and_sets_mplconfigdir(self, tmp_path, monkeypatch):
        from synaptipy.application.__main__ import _configure_frozen_environment

        saved_cwd = Path.cwd()
        try:
            monkeypatch.setattr(sys, "frozen", True, raising=False)
            monkeypatch.delenv("MPLCONFIGDIR", raising=False)
            os.chdir("/")

            _configure_frozen_environment(home_dir=tmp_path)

            assert Path.cwd().resolve() == tmp_path.resolve()
            expected_mpl = tmp_path / ".synaptipy" / "cache" / "matplotlib"
            assert os.environ.get("MPLCONFIGDIR") == str(expected_mpl)
            assert expected_mpl.is_dir()
        finally:
            os.chdir(saved_cwd)

    def test_existing_mplconfigdir_is_preserved_in_frozen_mode(self, tmp_path, monkeypatch):
        from synaptipy.application.__main__ import _configure_frozen_environment

        custom_mpl = tmp_path / "custom_mpl"
        custom_mpl.mkdir()
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        monkeypatch.setenv("MPLCONFIGDIR", str(custom_mpl))

        _configure_frozen_environment(home_dir=tmp_path)
        assert os.environ.get("MPLCONFIGDIR") == str(custom_mpl)

    def test_macos_qfileopenevent_dispatches_existing_recording_path(self, qapp, tmp_path):
        from synaptipy.application.__main__ import _MacFileOpenFilter

        sample = tmp_path / "cell_01.nwb"
        sample.write_bytes(b"NWB")
        missing = tmp_path / "does_not_exist.nwb"
        received: list[Path] = []

        flt = _MacFileOpenFilter(lambda p: received.append(p))
        qapp.installEventFilter(flt)
        try:
            QtCore.QCoreApplication.sendEvent(qapp, QtGui.QFileOpenEvent(str(missing)))
            assert received == []

            QtCore.QCoreApplication.sendEvent(qapp, QtGui.QFileOpenEvent(str(sample)))
            assert received == [sample.resolve()]

            # Non-QObject watched wrapper (e.g. Windows QWidgetItem) must return False cleanly
            non_qobject = object()
            noop_event = QtCore.QEvent(QtCore.QEvent.Type.None_)
            assert flt.eventFilter(non_qobject, noop_event) is False
        finally:
            qapp.removeEventFilter(flt)


class TestBootLogFallbackStream:
    """Verify detached windowed stdio streams write to boot.log with fileno()."""

    def test_none_stdio_routes_to_boot_log_with_valid_fileno(self, tmp_path, monkeypatch):
        import synaptipy.shared.logging_config as lc

        saved_out, saved_err = sys.stdout, sys.stderr
        saved_discard = lc._discard_stdio_stream
        try:
            lc._discard_stdio_stream = None
            monkeypatch.setenv("SYNAPTIPY_LOG_DIR", str(tmp_path))
            sys.stdout = None
            sys.stderr = io.StringIO()

            lc.ensure_stdio_streams_support_fileno()

            assert sys.stdout.fileno() >= 0
            assert sys.stderr.fileno() >= 0
            sys.stderr.write("boot-probe-line\n")
            sys.stderr.flush()
            boot_log = tmp_path / "boot.log"
            assert boot_log.exists()
            assert "boot-probe-line" in boot_log.read_text(encoding="utf-8")
        finally:
            if lc._discard_stdio_stream is not None and lc._discard_stdio_stream is not saved_discard:
                lc._discard_stdio_stream.close()
            lc._discard_stdio_stream = saved_discard
            sys.stdout, sys.stderr = saved_out, saved_err

    def test_unwritable_log_dir_falls_back_to_devnull(self, tmp_path):
        import synaptipy.shared.logging_config as lc

        blocker = tmp_path / "not_a_directory"
        blocker.write_text("file", encoding="utf-8")
        stream = lc._open_fallback_stdio_stream(log_dir=blocker)
        try:
            assert stream.fileno() >= 0
            assert stream.name == os.devnull
        finally:
            stream.close()


class TestPackagingConfigurations:
    """Guard PyInstaller spec, OS installer configs, and CI/release workflows against drift."""

    def test_pyinstaller_spec_enforces_macos_signing_arch_and_document_types(self):
        spec = _read("synaptipy.spec")

        assert '_IS_DARWIN = sys.platform == "darwin"' in spec
        assert "_USE_UPX = False" in spec
        assert "upx=_USE_UPX" in spec
        assert "SYNAPTIPY_TARGET_ARCH" in spec
        assert 'name="Synaptipy.app"' in spec
        assert '"NSHighResolutionCapable": True' in spec
        assert '"LSBackgroundOnly": False' in spec
        assert '"NSHighResolutionCapable": "True"' not in spec
        assert '"LSBackgroundOnly": "False"' not in spec
        assert '"CFBundleDocumentTypes"' in spec
        for required_token in (
            '"PySide6.QtHelp"',
            '"scipy"',
            '"pyabf"',
            '"jsonschema_specifications"',
            '"tzdata"',
            '"ruamel"',
            '"abf"',
            '"nwb"',
            "excludes=_EXCLUDED_MODULES",
            '"pytest"',
            '"sphinx"',
            '"black"',
            '"tkinter"',
            '".tests." not in mod',
        ):
            assert required_token in spec

    def test_windows_inno_setup_enforces_64bit_mode_and_clean_upgrade(self):
        iss = _read("installer/windows_setup.iss")

        assert '#define MyAppVersion "' in iss
        assert "ArchitecturesAllowed=x64compatible" in iss
        assert "ArchitecturesInstallIn64BitMode=x64compatible" in iss
        assert "CloseApplications=yes" in iss
        assert "CompressionThreads=auto" in iss
        assert "[InstallDelete]" in iss
        assert r'Name: "{app}\_internal"' in iss

    def test_linux_desktop_entry_supports_file_open_and_wm_class(self):
        desktop = _read("installer/linux/synaptipy.desktop")

        assert "X-AppVersion=" in desktop
        assert "Exec=synaptipy %f" in desktop
        assert "StartupWMClass=synaptipy" in desktop

    def test_installer_and_release_workflows_verify_packaged_artifacts_across_all_oses(self):
        installer_yml = _read(".github/workflows/installer.yml")
        release_yml = _read(".github/workflows/release.yml")
        test_yml = _read(".github/workflows/test.yml")

        # Dual-arch macOS + post-DMG mount + lipo slice verification
        assert "os: macos-latest" in installer_yml
        assert "os: macos-15-intel" in installer_yml
        assert "Synaptipy-macOS-arm64.dmg" in installer_yml
        assert "Synaptipy-macOS-x86_64.dmg" in installer_yml
        assert 'PYINSTALLER_STRICT_BUNDLE_CODESIGN_ERROR: "1"' in installer_yml
        assert 'PYINSTALLER_VERIFY_BUNDLE_SIGNATURE: "1"' in installer_yml
        assert 'codesign --force --deep --sign - "dist/Synaptipy.app"' in installer_yml
        assert "hdiutil attach" in installer_yml
        assert "lipo -archs" in installer_yml
        assert "--skip-jenkins" in installer_yml

        # Windows MAX_PATH check + silent Inno Setup install smoke verification
        assert "maxRelLen -ge 160" in installer_yml
        assert '"/VERYSILENT"' in installer_yml

        # Linux Wayland-safe AppRun + wget retries + post-AppImage smoke verification
        assert 'export QT_QPA_PLATFORM="xcb"' in installer_yml
        assert "--tries=5" in installer_yml
        assert "--appimage-extract-and-run --smoke-test" in installer_yml
        assert ".[dev,docs,formats]" in installer_yml

        # Release workflow libegl1 + boolean dry_run safety + timeout + fast-fail + dual DMG download
        assert "libegl1" in release_yml
        assert "(inputs.dry_run == false || github.event.inputs.dry_run == 'false')" in release_yml
        assert "github.event.inputs.dry_run != 'false'" not in release_yml
        assert "timeout-minutes: 75" in release_yml
        assert "finished with non-success conclusion" in release_yml
        assert "Synaptipy-macOS-arm64.dmg" in release_yml
        assert "Synaptipy-macOS-x86_64.dmg" in release_yml

        # Auto-tag creates annotated tags matching scripts/bump_version.py
        assert 'git tag -a "${TAG}"' in test_yml

        # CI speedups preserve standard pip wheel/TestPyPI smoke tests and safety gates
        assert "astral-sh/setup-uv@v7" in test_yml
        assert "astral-sh/setup-uv@v7" in installer_yml
        assert "astral-sh/setup-uv@v7" in release_yml
        assert "concurrency:" in test_yml
        assert "pytest -n auto --no-cov" in test_yml
        assert "/tmp/synaptipy-wheel-test/bin/python -m pip install dist/*.whl" in test_yml
        assert "Finder AppleScript styling timed out" not in installer_yml
        assert '-processors "$(nproc)"' in installer_yml
        assert "verify-ci:" in release_yml
        assert "workflow_id: 'test.yml'" in release_yml
        assert 'python -m pip install --pre --no-cache-dir "synaptipy==$APP_VERSION"' in release_yml
        assert "--no-build-isolation" not in test_yml
        assert "--no-build-isolation" not in installer_yml
        assert "--no-build-isolation" not in release_yml

        # Every non-core test directory under tests/ must be covered by NON_CORE_TARGETS
        ignored_dirs = {"core", "data", "__pycache__"}
        for child in (PROJECT_ROOT / "tests").iterdir():
            if child.is_dir() and not child.name.startswith(".") and child.name not in ignored_dirs:
                target_rel = f"tests/{child.name}"
                assert target_rel in test_yml, f"{target_rel} missing from NON_CORE_TARGETS in test.yml"
                assert target_rel in release_yml, f"{target_rel} missing from NON_CORE_TARGETS in release.yml"
            elif child.is_file() and child.name.startswith("test_") and child.suffix == ".py":
                target_rel = f"tests/{child.name}"
                assert target_rel in test_yml, f"{target_rel} missing from NON_CORE_TARGETS in test.yml"

    def test_qhelpgenerator_probe_rejects_broken_binary_and_accepts_working_binary(self, tmp_path):
        from importlib.util import module_from_spec, spec_from_file_location

        spec = spec_from_file_location("build_offline_help", PROJECT_ROOT / "scripts" / "build_offline_help.py")
        assert spec is not None and spec.loader is not None
        mod = module_from_spec(spec)
        spec.loader.exec_module(mod)

        broken = tmp_path / "qhelpgenerator_broken"
        broken.write_text("#!/bin/sh\nexit 127\n", encoding="utf-8")
        broken.chmod(0o755)

        working = tmp_path / "qhelpgenerator_ok"
        working.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        working.chmod(0o755)

        if sys.platform != "win32":
            assert mod._is_runnable_qhelpgenerator(broken) is False
            assert mod._is_runnable_qhelpgenerator(working) is True
        assert mod._is_runnable_qhelpgenerator(tmp_path / "missing_bin") is False

    def test_entrypoints_call_multiprocessing_freeze_support(self):
        pkg_main = _read("src/synaptipy/__main__.py")
        app_main = _read("src/synaptipy/application/__main__.py")

        assert "multiprocessing.freeze_support()" in pkg_main
        assert "multiprocessing.freeze_support()" in app_main

    def test_workflow_yaml_files_parse_cleanly_and_apprun_shebang_is_column_zero(self):
        from ruamel.yaml import YAML

        yaml = YAML(typ="safe")
        installer_data = yaml.load(PROJECT_ROOT / ".github" / "workflows" / "installer.yml")
        release_data = yaml.load(PROJECT_ROOT / ".github" / "workflows" / "release.yml")
        test_data = yaml.load(PROJECT_ROOT / ".github" / "workflows" / "test.yml")
        docs_data = yaml.load(PROJECT_ROOT / ".github" / "workflows" / "docs.yml")

        assert "jobs" in installer_data and "build" in installer_data["jobs"]
        assert "jobs" in release_data and "release" in release_data["jobs"]
        assert "jobs" in test_data and "auto-tag" in test_data["jobs"]
        assert "jobs" in docs_data and "docs" in docs_data["jobs"]

        linux_steps = [s for s in installer_data["jobs"]["build"]["steps"] if "AppImage" in s.get("name", "")]
        assert len(linux_steps) == 1
        run_script = linux_steps[0]["run"]
        assert "\n#!/bin/sh\n" in run_script
        assert "\nEOF\n" in run_script

    def test_bump_version_dry_run_remains_compatible_with_installer_files(self):
        res = subprocess.run(
            [sys.executable, str(PROJECT_ROOT / "scripts" / "bump_version.py"), "99.0.0", "--dry-run"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        # Note: bump_version.py requires a clean git tree unless only testing marker syntax;
        # verify _require_bump_targets directly so dirty working trees during development pass.
        if res.returncode != 0:
            assert "Working tree is not clean" in (res.stderr + res.stdout)
        from importlib.util import module_from_spec, spec_from_file_location

        spec = spec_from_file_location("bump_version", PROJECT_ROOT / "scripts" / "bump_version.py")
        assert spec is not None and spec.loader is not None
        mod = module_from_spec(spec)
        spec.loader.exec_module(mod)
        from synaptipy import __version__

        mod._require_bump_targets(__version__)
