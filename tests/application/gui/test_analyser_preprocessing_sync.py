
import pytest
from unittest.mock import MagicMock, patch  # noqa: F401
from PySide6 import QtCore, QtWidgets  # noqa: F401

from Synaptipy.application.gui.analyser_tab import AnalyserTab
from Synaptipy.application.session_manager import SessionManager
from Synaptipy.infrastructure.file_readers import NeoAdapter


@pytest.fixture
def session_manager():
    # Reset singleton state for testing
    if SessionManager._instance:
        SessionManager._instance = None
    sm = SessionManager()
    yield sm
    SessionManager._instance = None


@pytest.fixture
def mock_neo_adapter():
    return MagicMock(spec=NeoAdapter)


@pytest.fixture
def analyser_tab(mock_neo_adapter, session_manager, qtbot):
    # Retrieve the class - currently it's imported in the test file
    tab = AnalyserTab(mock_neo_adapter)
    qtbot.addWidget(tab)
    return tab


def test_preprocessing_sync_after_confirmation(analyser_tab, session_manager, qtbot):
    """
    Test that AnalyserTab updates its global settings when SessionManager emits a change signal,
    but ONLY if global preprocessing is already confirmed (which is the bug scenario).
    """
    # 1. Simulate initial confirmed state (e.g. user entered tab and accepted baseline)
    initial_settings = {'baseline': {'method': 'mean'}}
    analyser_tab._global_preprocessing_confirmed = True
    analyser_tab._global_preprocessing_settings = initial_settings

    # Verify initial state
    assert analyser_tab.get_global_preprocessing() == initial_settings

    # 2. Simulate User adding a Filter in Explorer (updates SessionManager)
    new_settings = {
        'baseline': {'method': 'mean'},
        'filters': {'notch': {'method': 'notch', 'freq': 50}}
    }

    # Emit signal from SessionManager (simulating Explorer update)
    # The fix ensures AnalyserTab is listening to this signal
    with qtbot.waitSignal(session_manager.preprocessing_settings_changed, timeout=1000):
        session_manager.preprocessing_settings = new_settings

    # 3. Verify AnalyserTab updated its local state
    current_settings = analyser_tab.get_global_preprocessing()

    assert current_settings is not None
    assert 'filters' in current_settings
    assert 'notch' in current_settings['filters']
    assert current_settings['filters']['notch']['freq'] == 50
    assert current_settings == new_settings


def test_preprocessing_sync_before_confirmation(analyser_tab, session_manager, qtbot):
    """
    Test that if NOT confirmed, we don't necessarily update immediately (logic might vary),
    but at least we don't crash. (Current implementation logs but doesn't force update).
    """
    analyser_tab._global_preprocessing_confirmed = False
    analyser_tab._global_preprocessing_settings = None

    new_settings = {'baseline': {'method': 'mean'}}

    # Emit signal
    session_manager.preprocessing_settings = new_settings

    # Should NOT have updated global settings yet (waiting for user confirmation popup on enter)
    # Based on my implementation: "If not confirmed... let's just log."
    assert analyser_tab.get_global_preprocessing() is None
