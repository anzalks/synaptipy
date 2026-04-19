# -*- coding: utf-8 -*-
"""Tests for shared.logging_config."""

import logging

from Synaptipy.shared.logging_config import get_logger, setup_logging


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


class TestGetLogger:
    def test_get_logger_namespaced(self):
        logger = get_logger("mymodule")
        assert logger.name == "Synaptipy.mymodule"

    def test_get_logger_already_namespaced(self):
        logger = get_logger("Synaptipy.core.analysis")
        assert logger.name == "Synaptipy.core.analysis"

    def test_get_logger_returns_logger_instance(self):
        result = get_logger("test")
        assert isinstance(result, logging.Logger)
