#!/usr/bin/env python3
"""
Synaptipy - Multi-channel Electrophysiology Visualization and Analysis Toolkit

This module serves as the entry point for the package when run as:
    python -m synaptipy

It delegates to the canonical run_gui() entry point in
synaptipy.application.__main__, which owns the argument parser shared by both
``python -m synaptipy`` and the installed ``synaptipy`` console script.

This file is part of Synaptipy, licensed under the GNU Affero General Public License v3.0.
See the LICENSE file in the root of the repository for full license details.
"""

import sys

from synaptipy.shared.logging_config import ensure_stdio_streams_support_fileno

# Windowed PyInstaller builds: streams must support ``fileno()`` before logging /
# GUI bootstrap (see application/__main__.py ``faulthandler.enable``).
ensure_stdio_streams_support_fileno()

# Install the crash reporter as early as possible -- before any Qt
# components are created -- so that import-time errors are also caught.
from synaptipy.core.error_handler import install_excepthook as _install_crash_hook  # noqa: E402

_install_crash_hook()


def main():
    """Main entry point for the application."""
    if "--version" in sys.argv:
        from synaptipy import __version__

        print(f"Synaptipy version {__version__}")
        return 0

    from synaptipy.application.__main__ import run_gui

    return run_gui()


if __name__ == "__main__":
    sys.exit(main())
