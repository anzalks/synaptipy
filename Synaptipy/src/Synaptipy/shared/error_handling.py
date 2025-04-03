"""Custom Exception classes for Synaptipy."""

class SynaptipyError(Exception):
    """Base class for Synaptipy specific errors."""
    pass

class FileReadError(SynaptipyError, IOError):
    """Error occurred during file reading or parsing by an adapter."""
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

# Add more specific errors as needed