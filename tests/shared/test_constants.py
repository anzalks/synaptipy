#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Tests for Synaptipy shared constants module."""

import unittest
from unittest import TestCase

class TestConstants(TestCase):
    """Test shared constants are properly defined."""

    def test_z_order_constant_exists(self):
        """Test that Z_ORDER constant is properly defined."""
        from Synaptipy.shared.constants import Z_ORDER
        
        # Test Z_ORDER is a dictionary
        self.assertIsInstance(Z_ORDER, dict)
        
        # Test required keys exist
        required_keys = ['grid', 'baseline', 'data', 'selection', 'annotation']
        for key in required_keys:
            self.assertIn(key, Z_ORDER, f"Z_ORDER missing required key: {key}")
        
        # Test grid has correct negative value (should be behind data)
        self.assertEqual(Z_ORDER['grid'], -1000)
        self.assertLess(Z_ORDER['grid'], Z_ORDER['data'])
        
        # Test ordering makes sense (lower values = behind, higher = in front)
        self.assertLess(Z_ORDER['grid'], Z_ORDER['baseline'])
        self.assertLess(Z_ORDER['baseline'], Z_ORDER['data'])
        self.assertLess(Z_ORDER['data'], Z_ORDER['selection'])
        self.assertLess(Z_ORDER['selection'], Z_ORDER['annotation'])

    def test_z_order_in_all_exports(self):
        """Test that Z_ORDER is included in __all__ exports."""
        from Synaptipy.shared import constants
        
        self.assertIn('Z_ORDER', constants.__all__)

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