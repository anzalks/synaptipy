#!/usr/bin/env python3
"""
Unit tests for the plot customization module.

Author: Anzal
Email: anzal.ks@gmail.com
"""

import pytest
import tempfile
import os
from unittest.mock import patch, MagicMock
from PySide6 import QtCore

from Synaptipy.shared.plot_customization import (
    PlotCustomizationManager,
    get_plot_customization_manager,
    get_average_pen,
    get_single_trial_pen,
    get_grid_pen,
    update_plot_preference,
    save_plot_preferences
)

class TestPlotCustomizationManager:
    """Test the PlotCustomizationManager class."""
    
    def test_init_defaults(self):
        """Test that manager initializes with correct defaults."""
        with patch('PySide6.QtCore.QSettings') as mock_settings:
            # Create a mock settings object
            mock_settings_instance = MagicMock()
            mock_settings.return_value = mock_settings_instance
            
            # Mock the value method to return appropriate default values
            def mock_value(key, default_value, type=None):
                # Return the default value that was passed in
                return default_value
            
            mock_settings_instance.value.side_effect = mock_value
            
            manager = PlotCustomizationManager()
            
            assert manager.defaults['average']['color'] == '#000000'  # Black hex
            assert manager.defaults['average']['width'] == 2
            assert manager.defaults['average']['opacity'] == 100
            
            assert manager.defaults['single_trial']['color'] == '#377eb8'  # Matplotlib blue hex
            assert manager.defaults['single_trial']['width'] == 1
            assert manager.defaults['single_trial']['opacity'] == 39  # Converted from TRIAL_ALPHA (100/255*100)
            
            assert manager.defaults['grid']['color'] == '#808080'  # Gray hex
            assert manager.defaults['grid']['width'] == 1
            assert manager.defaults['grid']['opacity'] == 70  # Default 70% opacity
    
    def test_update_preference(self):
        """Test updating preferences."""
        with patch('PySide6.QtCore.QSettings') as mock_settings:
            mock_settings.return_value = MagicMock()
            manager = PlotCustomizationManager()
            
            # Test valid preference update
            manager.update_preference('average', 'color', 'red')
            assert manager.defaults['average']['color'] == 'red'
            
            # Test invalid preference
            manager.update_preference('invalid', 'color', 'blue')
            # Should not change anything
            assert 'invalid' not in manager.defaults
    
    def test_get_all_preferences(self):
        """Test getting all preferences."""
        with patch('PySide6.QtCore.QSettings') as mock_settings:
            mock_settings.return_value = MagicMock()
            manager = PlotCustomizationManager()
            
            prefs = manager.get_all_preferences()
            assert isinstance(prefs, dict)
            assert 'average' in prefs
            assert 'single_trial' in prefs
            assert 'grid' in prefs
    
    def test_reset_to_defaults(self):
        """Test resetting to defaults."""
        with patch('PySide6.QtCore.QSettings') as mock_settings:
            mock_settings.return_value = MagicMock()
            manager = PlotCustomizationManager()
            
            # Change a preference
            manager.update_preference('average', 'color', 'red')
            assert manager.defaults['average']['color'] == 'red'
            
            # Reset
            manager.reset_to_defaults()
            assert manager.defaults['average']['color'] == '#000000'  # Black hex

class TestPlotCustomizationFunctions:
    """Test the convenience functions."""
    
    @patch('Synaptipy.shared.plot_customization._plot_customization_manager')
    def test_get_plot_customization_manager(self, mock_manager):
        """Test getting the global manager instance."""
        # Reset the global instance
        import Synaptipy.shared.plot_customization as pc
        pc._plot_customization_manager = None
        
        # Test getting manager
        manager = get_plot_customization_manager()
        assert manager is not None
    
    @patch('Synaptipy.shared.plot_customization.get_plot_customization_manager')
    def test_get_average_pen(self, mock_get_manager):
        """Test getting average pen."""
        mock_manager = MagicMock()
        mock_pen = MagicMock()
        mock_manager.get_average_pen.return_value = mock_pen
        mock_get_manager.return_value = mock_manager
        
        pen = get_average_pen()
        assert pen == mock_pen
        mock_manager.get_average_pen.assert_called_once()
    
    @patch('Synaptipy.shared.plot_customization.get_plot_customization_manager')
    def test_get_single_trial_pen(self, mock_get_manager):
        """Test getting single trial pen."""
        mock_manager = MagicMock()
        mock_pen = MagicMock()
        mock_manager.get_single_trial_pen.return_value = mock_pen
        mock_get_manager.return_value = mock_manager
        
        pen = get_single_trial_pen()
        assert pen == mock_pen
        mock_manager.get_single_trial_pen.assert_called_once()
    
    @patch('Synaptipy.shared.plot_customization.get_plot_customization_manager')
    def test_get_grid_pen(self, mock_get_manager):
        """Test getting grid pen."""
        mock_manager = MagicMock()
        mock_pen = MagicMock()
        mock_manager.get_grid_pen.return_value = mock_pen
        mock_get_manager.return_value = mock_manager
        
        pen = get_grid_pen()
        assert pen == mock_pen
        mock_manager.get_grid_pen.assert_called_once()
    
    @patch('Synaptipy.shared.plot_customization.get_plot_customization_manager')
    def test_update_plot_preference(self, mock_get_manager):
        """Test updating plot preference."""
        mock_manager = MagicMock()
        mock_get_manager.return_value = mock_manager
        
        update_plot_preference('average', 'color', 'red')
        mock_manager.update_preference.assert_called_once_with('average', 'color', 'red')
    
    @patch('Synaptipy.shared.plot_customization.get_plot_customization_manager')
    def test_save_plot_preferences(self, mock_get_manager):
        """Test saving plot preferences."""
        mock_manager = MagicMock()
        mock_get_manager.return_value = mock_manager
        
        save_plot_preferences()
        mock_manager.save_preferences.assert_called_once()

if __name__ == '__main__':
    pytest.main([__file__])
