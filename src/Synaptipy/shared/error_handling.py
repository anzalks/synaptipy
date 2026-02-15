"""
Custom Exception classes for Synaptipy.

This module defines a hierarchy of exception classes specific to Synaptipy.
All custom exceptions inherit from the base SynaptipyError class, which
itself inherits from Python's Exception class.

These custom exceptions provide more specific error handling for various
application components and help route errors to appropriate handlers.
"""


class SynaptipyError(Exception):
    """Base class for Synaptipy specific errors."""

    pass


class FileReadError(SynaptipyError, IOError):
    """Error occurred during file reading or parsing by an adapter."""

    pass


class SynaptipyFileNotFoundError(SynaptipyError, IOError):
    """Error raised when a specified file does not exist."""

    pass


class UnsupportedFormatError(SynaptipyError, ValueError):
    """File format is not supported by any available reader."""

    pass


class ProcessingError(SynaptipyError):
    """Error occurred during signal processing."""

    pass


class PlottingError(SynaptipyError):
    """Error occurred during plot generation or update."""

    pass


class ExportError(SynaptipyError, IOError):
    """Error occurred during file saving/exporting."""

    pass


class ConfigurationError(SynaptipyError):
    """Error occurred during application configuration."""

    pass


class AnalysisError(SynaptipyError):
    """Error occurred during data analysis operations."""

    pass


class UnitError(SynaptipyError, ValueError):
    """Error raised when signal units or sampling rate are invalid (e.g. <100Hz)."""

    pass
