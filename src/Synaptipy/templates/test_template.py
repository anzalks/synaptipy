# src/Synaptipy/templates/test_template.py
"""
GOLDEN SAMPLE: Unit Test Architecture.
Use pytest. Do NOT use unittest.TestCase.
Do NOT import PySide6 or GUI classes here.
"""
import pytest
import numpy as np

# Rule: Import the PURE LOGIC function, not the GUI wrapper
from Synaptipy.core.analysis.template_analysis import calculate_metric_logic


@pytest.fixture
def synthetic_data():
    """Generate known synthetic data for testing."""
    fs = 10000.0
    time = np.arange(0, 1.0, 1 / fs)
    # Create a signal with known properties (e.g., sine wave)
    data = np.sin(2 * np.pi * 10 * time)  # 10 Hz
    return data, fs


def test_calculate_metric_basic(synthetic_data):
    """Test standard success case."""
    data, fs = synthetic_data

    # Act
    result = calculate_metric_logic(data, fs, threshold=0.5)

    # Assert
    assert result.is_valid is True
    assert result.value is not None
    # Rule: Check physical correctness, not just 'is not None'
    assert isinstance(result.value, bool)


def test_calculate_metric_empty_input():
    """Test edge case: Empty array."""
    empty_data = np.array([])
    result = calculate_metric_logic(empty_data, 10000.0, threshold=0.5)

    assert result.is_valid is False
    assert "Empty Data" in result.error_message
