"""
Centralized logging configuration for Synaptipy.

This module provides functions to set up logging with different verbosity levels,
including a development mode with more detailed logging. All logs are written to
both a file (in the logs directory) and the console.

The module provides two main functions:
1. setup_logging - Configure the root logger with console and file handlers
2. get_logger - Get a properly namespaced logger for a specific module

Usage:
    # In application entry point:
    from Synaptipy.shared.logging_config import setup_logging
    setup_logging(dev_mode=True)  # Enable development mode
    
    # In other modules:
    from Synaptipy.shared.logging_config import get_logger
    log = get_logger(__name__)  # Get a logger for current module
    log.info("This is a log message")
"""
import os
import sys
import logging
from pathlib import Path
from datetime import datetime

# Default log directory is in the user's home directory
DEFAULT_LOG_DIR = Path.home() / '.synaptipy' / 'logs'

# Define logger levels for different modes 
DEFAULT_CONSOLE_LEVEL = logging.INFO    # Regular operation - show INFO+ in console
DEFAULT_FILE_LEVEL = logging.INFO       # Regular operation - log INFO+ to file (balanced)
DEV_CONSOLE_LEVEL = logging.DEBUG       # Dev mode - show DEBUG+ in console
DEV_FILE_LEVEL = logging.DEBUG          # Dev mode - log DEBUG+ to file

def setup_logging(dev_mode=False, log_dir=None, log_filename=None):
    """
    Configure the logging system for Synaptipy.
    
    This function sets up the root logger with both console and file handlers.
    In development mode, more detailed log messages are shown, including file and
    line number information.
    
    Args:
        dev_mode (bool): If True, enables more verbose logging for development.
        log_dir (Path, optional): Directory where log files will be stored.
            Defaults to ~/.synaptipy/logs/
        log_filename (str, optional): Name of the log file.
            If not provided, a timestamped name will be used.
            
    Returns:
        logging.Logger: The configured root logger
    """
    # Create the root logger and set its level
    root_logger = logging.getLogger('Synaptipy')
    
    # Remove existing handlers if any
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)
    
    # Set the root logger level to the most verbose level needed
    root_logger.setLevel(logging.DEBUG)  # Always use DEBUG to catch all messages
    
    # Determine console and file logging levels based on dev_mode
    console_level = DEV_CONSOLE_LEVEL if dev_mode else DEFAULT_CONSOLE_LEVEL
    file_level = DEV_FILE_LEVEL if dev_mode else DEFAULT_FILE_LEVEL
    
    # Define common formatter with more detail for dev mode
    if dev_mode:
        # Include filename and line number in development mode
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s'
        )
    else:
        # Standard format for production use
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
    
    # Add console handler for terminal output
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(console_level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)
    
    # Setup file logging
    log_dir = Path(log_dir) if log_dir else DEFAULT_LOG_DIR
    
    # Create log directory if it doesn't exist
    os.makedirs(log_dir, exist_ok=True)
    
    # Generate log filename if not provided
    if not log_filename:
        timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        log_filename = f"synaptipy_{timestamp}.log"
    
    log_file_path = log_dir / log_filename
    
    # Add file handler for saving logs to file
    file_handler = logging.FileHandler(log_file_path)
    file_handler.setLevel(file_level)
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)
    
    # Create a separate app.log for the most recent run
    # This overwrites the previous app.log to provide easy access to latest logs
    app_log_path = log_dir / "app.log"
    app_file_handler = logging.FileHandler(app_log_path, mode='w')  # Overwrite existing file
    app_file_handler.setLevel(file_level)
    app_file_handler.setFormatter(formatter)
    root_logger.addHandler(app_file_handler)
    
    # Log the initialization
    mode_str = "DEVELOPMENT" if dev_mode else "PRODUCTION"
    root_logger.info(f"Synaptipy logging initialized in {mode_str} mode")
    root_logger.info(f"Log file: {log_file_path}")
    
    return root_logger

def get_logger(name):
    """
    Get a logger with the specified name, properly namespaced under Synaptipy.
    
    This ensures all loggers use the same namespace hierarchy for consistent
    configuration and filtering.
    
    Args:
        name (str): The logger name, which will be prefixed with 'Synaptipy.' if not already.
        
    Returns:
        logging.Logger: A logger instance
    """
    if not name.startswith('Synaptipy.'):
        name = f'Synaptipy.{name}'
    return logging.getLogger(name) 