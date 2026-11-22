# -*- coding: utf-8 -*-
"""Packaging, bundle specification, and desktop entry-point regression tests."""

from __future__ import annotations

import io
import os
import sys
from pathlib import Path

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
    """Guard PyInstaller spec and CI installer/release workflows against drift."""

    def test_pyinstaller_spec_enforces_macos_signing_and_arch_invariants(self):
        spec = _read("synaptipy.spec")

        assert '_IS_DARWIN = sys.platform == "darwin"' in spec
        assert "_USE_UPX = not _IS_DARWIN" in spec
        assert "upx=_USE_UPX" in spec
        assert "SYNAPTIPY_TARGET_ARCH" in spec
        assert 'name="Synaptipy.app"' in spec
        # Ensure Info.plist uses real Python booleans rather than strings
        assert '"NSHighResolutionCapable": True' in spec
        assert '"LSBackgroundOnly": False' in spec
        assert '"NSHighResolutionCapable": "True"' not in spec
        assert '"LSBackgroundOnly": "False"' not in spec
        # Required dynamic packages and Qt modules for offline help + exports
        for required_token in (
            '"PySide6.QtHelp"',
            '"pyabf"',
            '"jsonschema_specifications"',
            '"tzdata"',
            '"ruamel"',
        ):
            assert required_token in spec

    def test_installer_and_release_workflows_cover_both_macos_architectures(self):
        installer_yml = _read(".github/workflows/installer.yml")
        release_yml = _read(".github/workflows/release.yml")

        assert "os: macos-latest" in installer_yml
        assert "os: macos-15-intel" in installer_yml
        assert "Synaptipy-macOS-arm64.dmg" in installer_yml
        assert "Synaptipy-macOS-x86_64.dmg" in installer_yml
        assert 'PYINSTALLER_STRICT_BUNDLE_CODESIGN_ERROR: "1"' in installer_yml
        assert 'PYINSTALLER_VERIFY_BUNDLE_SIGNATURE: "1"' in installer_yml
        assert 'codesign --force --deep --sign - "dist/Synaptipy.app"' in installer_yml
        assert "codesign --verify --all-architectures --deep --strict" in installer_yml
        assert "--smoke-test" in installer_yml
        assert ".[dev,docs,formats]" in installer_yml

        assert "Synaptipy-macOS-arm64.dmg" in release_yml
        assert "Synaptipy-macOS-x86_64.dmg" in release_yml

    def test_entrypoints_call_multiprocessing_freeze_support(self):
        pkg_main = _read("src/synaptipy/__main__.py")
        app_main = _read("src/synaptipy/application/__main__.py")

        assert "multiprocessing.freeze_support()" in pkg_main
        assert "multiprocessing.freeze_support()" in app_main
