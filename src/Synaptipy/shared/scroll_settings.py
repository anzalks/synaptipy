# src/Synaptipy/shared/scroll_settings.py
# -*- coding: utf-8 -*-
"""
Scroll Settings Module for Synaptipy.

Manages scroll direction preferences with persistence via QSettings.
Provides unified scroll behavior across the application.
"""
import logging
from enum import Enum
from typing import Optional

from PySide6 import QtCore

from Synaptipy.shared.constants import APP_NAME, SETTINGS_SECTION

log = logging.getLogger(__name__)


class ScrollDirection(Enum):
    """Scroll direction modes."""

    NATURAL = "natural"  # macOS style: scroll up = content goes up
    INVERTED = "inverted"  # Traditional: scroll up = content goes down
    SYSTEM = "system"  # Follow OS setting


class ScrollSettingsSignals(QtCore.QObject):
    """Signals for scroll settings changes."""

    direction_changed = QtCore.Signal(str)


# Global signal instance
_scroll_signals: Optional[ScrollSettingsSignals] = None


def get_scroll_settings_signals() -> ScrollSettingsSignals:
    """Get the global scroll settings signals instance."""
    global _scroll_signals
    if _scroll_signals is None:
        _scroll_signals = ScrollSettingsSignals()
    return _scroll_signals


def _get_settings() -> QtCore.QSettings:
    """Get QSettings instance for scroll preferences."""
    return QtCore.QSettings(APP_NAME, SETTINGS_SECTION)


def get_scroll_direction() -> ScrollDirection:
    """Get the current scroll direction setting."""
    settings = _get_settings()
    value = settings.value("scroll/direction", ScrollDirection.NATURAL.value, type=str)
    try:
        return ScrollDirection(value)
    except ValueError:
        log.warning(f"Invalid scroll direction value: {value}, defaulting to NATURAL")
        return ScrollDirection.NATURAL


def set_scroll_direction(direction: ScrollDirection) -> None:
    """Set the scroll direction setting."""
    settings = _get_settings()
    settings.setValue("scroll/direction", direction.value)
    settings.sync()
    log.debug(f"Scroll direction set to: {direction.value}")

    # Emit signal
    signals = get_scroll_settings_signals()
    signals.direction_changed.emit(direction.value)


def get_scroll_multiplier() -> int:
    """
    Get the scroll multiplier based on current direction setting.

    Returns:
        1 for natural scrolling (scroll up = view moves up)
        -1 for inverted scrolling (scroll up = view moves down)
    """
    direction = get_scroll_direction()

    if direction == ScrollDirection.NATURAL:
        return 1
    elif direction == ScrollDirection.INVERTED:
        return -1
    elif direction == ScrollDirection.SYSTEM:
        # Try to detect system setting
        return _detect_system_scroll_direction()

    return 1  # Default to natural


def _detect_system_scroll_direction() -> int:
    """
    Attempt to detect the system scroll direction setting.

    Returns 1 for natural, -1 for inverted.
    Falls back to natural (1) if detection fails.
    """
    import sys

    if sys.platform == "darwin":
        # macOS: Natural scrolling is typically enabled by default
        # Could query com.apple.swipescrolldirection but requires pyobjc
        return 1
    elif sys.platform == "win32":
        # Windows: Traditional scrolling is default
        # Could query registry HKEY_CURRENT_USER\Control Panel\Desktop\WheelScrollLines
        # but the sign doesn't indicate direction
        return -1
    else:
        # Linux: Varies by DE, default to natural for touchpads
        return 1


def is_scroll_inverted() -> bool:
    """Check if scroll direction is inverted."""
    return get_scroll_multiplier() < 0


__all__ = [
    "ScrollDirection",
    "get_scroll_direction",
    "set_scroll_direction",
    "get_scroll_multiplier",
    "is_scroll_inverted",
    "get_scroll_settings_signals",
]
