#!/usr/bin/env python3
"""
Synaptipy - Multi-channel Electrophysiology Visualization and Analysis Toolkit

This module serves as the entry point for the package when run as:
    python -m Synaptipy

It parses command line arguments and launches the application with the appropriate settings.

This file is part of Synaptipy, licensed under the GNU Affero General Public License v3.0.
See the LICENSE file in the root of the repository for full license details.
"""

import os
import sys
import argparse
import logging
from pathlib import Path

# Set up logging before importing the rest of the package
from Synaptipy.shared.logging_config import setup_logging


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Synaptipy - Electrophysiology Visualization and Analysis Toolkit",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument(
        "--dev",
        action="store_true",
        help="Run in development mode with increased logging"
    )
    parser.add_argument(
        "--log-dir",
        type=str,
        default=None,
        help="Directory to store log files"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Increase output verbosity"
    )
    parser.add_argument(
        "--version",
        action="store_true",
        help="Show version information and exit"
    )
    parser.add_argument(
        "--file",
        type=str,
        default=None,
        help="Open a specific file on startup"
    )
    
    return parser.parse_args()


def main():
    """Main entry point for the application."""
    args = parse_args()
    
    # Show version and exit if requested
    if args.version:
        from Synaptipy import __version__
        print(f"Synaptipy version {__version__}")
        return 0
    
    # Set up environment variables based on arguments
    if args.dev:
        os.environ["SYNAPTIPY_DEV_MODE"] = "1"
    
    # Configure logging
    log_level = logging.DEBUG if args.verbose or args.dev else logging.INFO
    setup_logging(dev_mode=args.dev, log_dir=args.log_dir)
    logger = logging.getLogger(__name__)
    
    logger.info("Starting Synaptipy...")
    logger.debug(f"Command line arguments: {args}")
    
    # Import GUI components here to avoid circular imports
    try:
        from Synaptipy.application.__main__ import run_gui
        
        # Launch the GUI
        initial_file = Path(args.file) if args.file else None
        if initial_file and not initial_file.exists():
            logger.error(f"File not found: {initial_file}")
            print(f"Error: File not found: {initial_file}")
            return 1
            
        return run_gui()
    except ImportError as e:
        logger.error(f"Failed to import GUI components: {e}")
        print(f"Error: Failed to import GUI components: {e}")
        print("Make sure PySide6 is installed properly.")
        return 1
    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
        print(f"Error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
