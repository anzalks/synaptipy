# -*- coding: utf-8 -*-
"""Tests for shared.logging_config."""

import logging
import sys

from synaptipy.shared.logging_config import get_logger, setup_logging


class TestSetupLogging:
    def test_setup_logging_returns_logger(self, tmp_path):
        logger = setup_logging(dev_mode=False, log_dir=tmp_path)
        assert isinstance(logger, logging.Logger)

    def test_setup_logging_dev_mode(self, tmp_path):
        logger = setup_logging(dev_mode=True, log_dir=tmp_path)
        assert isinstance(logger, logging.Logger)
        # Dev mode enables DEBUG level
        assert logger.level == logging.DEBUG

    def test_setup_logging_creates_log_file(self, tmp_path):
        setup_logging(dev_mode=False, log_dir=tmp_path)
        log_files = list(tmp_path.glob("*.log"))
        # Should have created at least one log file
        assert len(log_files) >= 1

    def test_setup_logging_custom_filename(self, tmp_path):
        setup_logging(dev_mode=False, log_dir=tmp_path, log_filename="custom.log")
        assert (tmp_path / "custom.log").exists()

    def test_setup_logging_creates_app_log(self, tmp_path):
        setup_logging(dev_mode=False, log_dir=tmp_path)
        assert (tmp_path / "app.log").exists()

    def test_setup_logging_handlers_attached(self, tmp_path):
        logger = setup_logging(dev_mode=False, log_dir=tmp_path)
        assert len(logger.handlers) >= 2  # console + file


class TestEnsureStdioStreamsSupportFileno:
    """Regression: PyInstaller windowed builds use streams without fileno()."""

    def test_stringio_streams_replaced_so_fileno_and_faulthandler_work(self):
        import faulthandler
        import io

        from synaptipy.shared.logging_config import ensure_stdio_streams_support_fileno

        saved_o, saved_e = sys.stdout, sys.stderr
        try:
            sys.stdout = io.StringIO()
            sys.stderr = io.StringIO()
            ensure_stdio_streams_support_fileno()
            sys.stdout.fileno()
            sys.stderr.fileno()
            faulthandler.enable()
        finally:
            faulthandler.disable()
            sys.stdout, sys.stderr = saved_o, saved_e

    def test_synaptipy_main_main_survives_stringio_stdio(self, monkeypatch):
        """Exercise package entry ``main()`` after stdio lacks fileno() (frozen exe analogue)."""
        import importlib
        import io

        monkeypatch.setattr(sys, "stdout", io.StringIO())
        monkeypatch.setattr(sys, "stderr", io.StringIO())

        import synaptipy.__main__ as syn_entry

        syn_entry = importlib.reload(syn_entry)
        monkeypatch.setattr(sys, "argv", ["synaptipy", "--version"])
        assert syn_entry.main() == 0


class TestGetLogger:
    def test_get_logger_namespaced(self):
        logger = get_logger("mymodule")
        assert logger.name == "synaptipy.mymodule"

    def test_get_logger_already_namespaced(self):
        logger = get_logger("synaptipy.core.analysis")
        assert logger.name == "synaptipy.core.analysis"

    def test_get_logger_returns_logger_instance(self):
        result = get_logger("test")
        assert isinstance(result, logging.Logger)
