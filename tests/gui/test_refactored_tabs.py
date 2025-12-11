import pytest
from PySide6 import QtWidgets
from Synaptipy.application.gui.analysis_tabs.spike_tab import SpikeAnalysisTab
from Synaptipy.application.gui.analysis_tabs.phase_plane_tab import PhasePlaneTab
from Synaptipy.application.gui.analysis_tabs.event_detection_tab import EventDetectionTab
from Synaptipy.application.gui.analysis_tabs.rin_tab import RinAnalysisTab
from Synaptipy.application.gui.analysis_tabs.rmp_tab import BaselineAnalysisTab
from Synaptipy.infrastructure.file_readers import NeoAdapter

@pytest.fixture
def neo_adapter():
    return NeoAdapter()

@pytest.fixture
def app(qtbot):
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

def test_spike_tab_init(qtbot, neo_adapter):
    tab = SpikeAnalysisTab(neo_adapter)
    qtbot.addWidget(tab)
    assert tab.get_registry_name() == "spike_detection"
    # Check if params can be gathered
    params = tab._gather_analysis_parameters()
    assert isinstance(params, dict)
    assert 'threshold' in params

def test_phase_plane_tab_init(qtbot, neo_adapter):
    tab = PhasePlaneTab(neo_adapter)
    qtbot.addWidget(tab)
    assert tab.get_registry_name() == "phase_plane_analysis"
    params = tab._gather_analysis_parameters()
    assert 'sigma_ms' in params

def test_event_detection_tab_init(qtbot, neo_adapter):
    tab = EventDetectionTab(neo_adapter)
    qtbot.addWidget(tab)
    # Default method
    assert tab.get_registry_name() == "event_detection_threshold"
    params = tab._gather_analysis_parameters()
    assert 'threshold' in params
    
    # Change method
    tab.mini_method_combobox.setCurrentIndex(1) # Deconvolution
    assert tab.get_registry_name() == "event_detection_deconvolution"
    params = tab._gather_analysis_parameters()
    assert 'tau_rise_ms' in params

def test_rin_tab_init(qtbot, neo_adapter):
    tab = RinAnalysisTab(neo_adapter)
    qtbot.addWidget(tab)
    assert tab.get_registry_name() == "rin_analysis"
    params = tab._gather_analysis_parameters()
    assert 'current_amplitude' in params
    
    # Check mode switching
    tab.mode_combobox.setCurrentText(RinAnalysisTab._MODE_MANUAL)
    assert tab.param_generator.widgets['baseline_start'].isEnabled()

def test_rmp_tab_init(qtbot, neo_adapter):
    tab = BaselineAnalysisTab(neo_adapter)
    qtbot.addWidget(tab)
    assert tab.get_registry_name() == "rmp_analysis"
    params = tab._gather_analysis_parameters()
    assert 'baseline_start' in params
    
    # Check automatic mode
    tab.mode_combobox.setCurrentText(BaselineAnalysisTab._MODE_AUTOMATIC)
    params = tab._gather_analysis_parameters()
    assert params['auto_detect'] is True
