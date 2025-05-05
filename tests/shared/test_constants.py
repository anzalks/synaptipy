import pytest
from Synaptipy.shared import constants

def test_get_neo_file_filter_format():
    """Check if the generated file filter string has the expected format."""
    filter_str = constants.get_neo_file_filter()
    assert isinstance(filter_str, str)
    assert "All Supported Formats" in filter_str
    assert ";;" in filter_str # Separator for filters
    assert "ABF Files (*.abf)" in filter_str # Example specific filter
    assert filter_str.endswith(")") # Should end with a parenthesis

def test_neo_file_filter_content():
    """Check if specific extensions are present."""
    filter_str = constants.NEO_FILE_FILTER
    assert "*.abf" in filter_str
    assert "*.nex" in filter_str # Add checks for other important formats
    assert "*.smr" in filter_str

# Add tests for other constants or utility functions in shared/constants.py if any