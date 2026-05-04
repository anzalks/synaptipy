# tests/shared/test_scroll_settings_coverage.py
# -*- coding: utf-8 -*-
"""
Coverage-boosting tests for shared/scroll_settings.py.

Targets previously uncovered lines:
  42-44   : get_scroll_settings_signals creates new instance on first call
  58-60   : _get_settings returns a QSettings instance
  65-72   : get_scroll_direction with invalid stored value → defaults to NATURAL
  86      : set_scroll_direction stores value
  88      : settings.sync() is called
  93      : direction_changed signal is emitted
  109-116 : get_scroll_multiplier SYSTEM branch → _detect_system_scroll_direction
  117-129 : _detect_system_scroll_direction for all platforms
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from PySide6 import QtCore

import Synaptipy.shared.scroll_settings as ss
from Synaptipy.shared.scroll_settings import (
    ScrollDirection,
    _detect_system_scroll_direction,
    _get_settings,
    get_scroll_direction,
    get_scroll_multiplier,
    get_scroll_settings_signals,
    is_scroll_inverted,
    set_scroll_direction,
)

# ---------------------------------------------------------------------------
# Helpers – reset global state
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_scroll_signals():
    """Reset the module-level singleton before and after each test."""
    original = ss._scroll_signals
    ss._scroll_signals = None
    yield
    ss._scroll_signals = original


# ---------------------------------------------------------------------------
# get_scroll_settings_signals
# ---------------------------------------------------------------------------


class TestGetScrollSettingsSignals:
    def test_creates_instance_on_first_call(self):
        """Lines 42-44: returns a new ScrollSettingsSignals when None."""
        assert ss._scroll_signals is None
        sig = get_scroll_settings_signals()
        assert sig is not None
        assert isinstance(sig, ss.ScrollSettingsSignals)

    def test_returns_same_instance_on_second_call(self):
        sig1 = get_scroll_settings_signals()
        sig2 = get_scroll_settings_signals()
        assert sig1 is sig2


# ---------------------------------------------------------------------------
# _get_settings
# ---------------------------------------------------------------------------


class TestGetSettings:
    def test_returns_qsettings(self):
        """Lines 58-60: _get_settings must return a QSettings object."""
        settings = _get_settings()
        assert isinstance(settings, QtCore.QSettings)


# ---------------------------------------------------------------------------
# get_scroll_direction
# ---------------------------------------------------------------------------


class TestGetScrollDirection:
    def test_valid_value_returns_enum(self):
        mock_settings = MagicMock(spec=QtCore.QSettings)
        mock_settings.value.return_value = ScrollDirection.NATURAL.value
        with patch("Synaptipy.shared.scroll_settings._get_settings", return_value=mock_settings):
            result = get_scroll_direction()
        assert result == ScrollDirection.NATURAL

    def test_invalid_value_defaults_to_natural(self):
        """Lines 65-72: invalid stored value → defaults to NATURAL with warning."""
        mock_settings = MagicMock(spec=QtCore.QSettings)
        mock_settings.value.return_value = "completely_invalid_value"
        with patch("Synaptipy.shared.scroll_settings._get_settings", return_value=mock_settings):
            result = get_scroll_direction()
        assert result == ScrollDirection.NATURAL

    def test_inverted_value_returns_inverted(self):
        mock_settings = MagicMock(spec=QtCore.QSettings)
        mock_settings.value.return_value = ScrollDirection.INVERTED.value
        with patch("Synaptipy.shared.scroll_settings._get_settings", return_value=mock_settings):
            result = get_scroll_direction()
        assert result == ScrollDirection.INVERTED


# ---------------------------------------------------------------------------
# set_scroll_direction
# ---------------------------------------------------------------------------


class TestSetScrollDirection:
    def test_stores_and_syncs_and_emits(self, qtbot):
        """Lines 86, 88, 93: setValue, sync, and signal emission."""
        mock_settings = MagicMock(spec=QtCore.QSettings)

        # Ensure a real signal instance exists before we capture emissions
        sig_instance = get_scroll_settings_signals()
        received = []
        sig_instance.direction_changed.connect(received.append)

        with patch("Synaptipy.shared.scroll_settings._get_settings", return_value=mock_settings):
            set_scroll_direction(ScrollDirection.INVERTED)

        mock_settings.setValue.assert_called_once_with("scroll/direction", ScrollDirection.INVERTED.value)
        mock_settings.sync.assert_called_once()
        assert received == [ScrollDirection.INVERTED.value]

    def test_set_natural_after_inverted(self, qtbot):
        mock_settings = MagicMock(spec=QtCore.QSettings)
        sig_instance = get_scroll_settings_signals()
        received = []
        sig_instance.direction_changed.connect(received.append)

        with patch("Synaptipy.shared.scroll_settings._get_settings", return_value=mock_settings):
            set_scroll_direction(ScrollDirection.NATURAL)

        assert received == [ScrollDirection.NATURAL.value]


# ---------------------------------------------------------------------------
# get_scroll_multiplier
# ---------------------------------------------------------------------------


class TestGetScrollMultiplier:
    def _set_direction(self, direction: ScrollDirection):
        mock_settings = MagicMock(spec=QtCore.QSettings)
        mock_settings.value.return_value = direction.value
        return mock_settings

    def test_natural_returns_1(self):
        with patch(
            "Synaptipy.shared.scroll_settings.get_scroll_direction",
            return_value=ScrollDirection.NATURAL,
        ):
            assert get_scroll_multiplier() == 1

    def test_inverted_returns_minus_1(self):
        with patch(
            "Synaptipy.shared.scroll_settings.get_scroll_direction",
            return_value=ScrollDirection.INVERTED,
        ):
            assert get_scroll_multiplier() == -1

    def test_system_calls_detect(self):
        """Lines 109-116: SYSTEM branch delegates to _detect_system_scroll_direction."""
        with patch(
            "Synaptipy.shared.scroll_settings.get_scroll_direction",
            return_value=ScrollDirection.SYSTEM,
        ):
            with patch(
                "Synaptipy.shared.scroll_settings._detect_system_scroll_direction",
                return_value=1,
            ) as mock_detect:
                result = get_scroll_multiplier()
        mock_detect.assert_called_once()
        assert result == 1


# ---------------------------------------------------------------------------
# _detect_system_scroll_direction
# ---------------------------------------------------------------------------


class TestDetectSystemScrollDirection:
    def test_darwin_returns_1(self):
        with patch("sys.platform", "darwin"):
            assert _detect_system_scroll_direction() == 1

    def test_win32_returns_minus_1(self):
        with patch("sys.platform", "win32"):
            assert _detect_system_scroll_direction() == -1

    def test_linux_returns_1(self):
        with patch("sys.platform", "linux"):
            assert _detect_system_scroll_direction() == 1


# ---------------------------------------------------------------------------
# is_scroll_inverted
# ---------------------------------------------------------------------------


class TestIsScrollInverted:
    def test_natural_not_inverted(self):
        with patch(
            "Synaptipy.shared.scroll_settings.get_scroll_multiplier",
            return_value=1,
        ):
            assert is_scroll_inverted() is False

    def test_inverted_is_inverted(self):
        with patch(
            "Synaptipy.shared.scroll_settings.get_scroll_multiplier",
            return_value=-1,
        ):
            assert is_scroll_inverted() is True
