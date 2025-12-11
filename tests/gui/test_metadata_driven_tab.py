# tests/gui/test_metadata_driven_tab.py
import pytest
from PySide6 import QtWidgets
from Synaptipy.application.gui.analysis_tabs.metadata_driven import MetadataDrivenAnalysisTab
from Synaptipy.core.analysis.registry import AnalysisRegistry
from unittest.mock import MagicMock

# Register a dummy analysis for testing
@AnalysisRegistry.register(
    "test_analysis",
    label="Test Analysis",
    ui_params=[
        {'name': 'param1', 'type': 'float', 'default': 1.0, 'label': 'Param 1'},
        {'name': 'param2', 'type': 'int', 'default': 5, 'label': 'Param 2'},
        {'name': 'param3', 'type': 'choice', 'choices': ['A', 'B'], 'default': 'A', 'label': 'Param 3'},
        {'name': 'param4', 'type': 'bool', 'default': True, 'label': 'Param 4'}
    ]
)
def dummy_analysis_func(data, time, fs, **kwargs):
    return {'result': 'success', 'kwargs': kwargs}

@pytest.fixture
def app(qapp):
    return qapp

def test_metadata_tab_creation(app):
    """Test that the tab creates widgets based on metadata."""
    neo_adapter = MagicMock()
    tab = MetadataDrivenAnalysisTab("test_analysis", neo_adapter)
    
    # Check if widgets were created
    assert 'param1' in tab.param_widgets
    assert 'param2' in tab.param_widgets
    assert 'param3' in tab.param_widgets
    assert 'param4' in tab.param_widgets
    
    # Check widget types
    assert isinstance(tab.param_widgets['param1'], QtWidgets.QDoubleSpinBox)
    assert isinstance(tab.param_widgets['param2'], QtWidgets.QSpinBox)
    assert isinstance(tab.param_widgets['param3'], QtWidgets.QComboBox)
    assert isinstance(tab.param_widgets['param4'], QtWidgets.QCheckBox)
    
    # Check default values
    assert tab.param_widgets['param1'].value() == 1.0
    assert tab.param_widgets['param2'].value() == 5
    assert tab.param_widgets['param3'].currentText() == 'A'
    assert tab.param_widgets['param4'].isChecked() == True

def test_parameter_gathering(app):
    """Test that parameters are correctly gathered from widgets."""
    neo_adapter = MagicMock()
    tab = MetadataDrivenAnalysisTab("test_analysis", neo_adapter)
    
    # Modify values
    tab.param_widgets['param1'].setValue(2.5)
    tab.param_widgets['param2'].setValue(10)
    tab.param_widgets['param3'].setCurrentText('B')
    tab.param_widgets['param4'].setChecked(False)
    
    params = tab._gather_analysis_parameters()
    
    assert params['param1'] == 2.5
    assert params['param2'] == 10
    assert params['param3'] == 'B'
    assert params['param4'] == False
