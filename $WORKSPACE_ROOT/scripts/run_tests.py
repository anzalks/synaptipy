#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test runner script for Synaptipy.

This script provides a convenient way to run tests with various options like
coverage reporting and filtering by test name. It specifically targets the
tests inside the project directory to avoid collecting tests from other projects.
"""
import argparse
import os
import sys
import subprocess
from pathlib import Path

def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Run Synaptipy tests")
    parser.add_argument("--coverage", action="store_true", help="Generate coverage report")
    parser.add_argument("--html", action="store_true", help="Generate HTML coverage report")
    parser.add_argument("--test", "-t", type=str, help="Run specific test (e.g., 'test_exporter_tab')")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument("--dev-mode", action="store_true", help="Run in development mode with additional logging")
    return parser.parse_args()

def run_tests(args):
    """Run tests with the specified options."""
    # Get the project root directory
    root_dir = Path(__file__).parent.parent
    
    # Set up environment for tests
    env = os.environ.copy()
    if args.dev_mode:
        env["SYNAPTIPY_DEV_MODE"] = "1"
    
    # Basic command: run pytest specifically on our tests directory
    cmd = ["pytest", str(root_dir / "tests")]
    
    # Add options
    if args.verbose:
        cmd.append("-v")
    
    # Run specific test if requested
    if args.test:
        cmd.append(f"-k {args.test}")
    
    # Add coverage options
    if args.coverage:
        cmd.append("--cov=src/Synaptipy")
        
        if args.html:
            cmd.append("--cov-report=html")
        else:
            cmd.append("--cov-report=term")
    
    # Print the command for transparency
    cmd_str = " ".join(cmd)
    print(f"Running: {cmd_str}")
    
    # Run the command
    try:
        result = subprocess.run(cmd, env=env, cwd=str(root_dir))
        return result.returncode
    except Exception as e:
        print(f"Error running tests: {e}")
        return 1

if __name__ == "__main__":
    args = parse_args()
    sys.exit(run_tests(args)) 