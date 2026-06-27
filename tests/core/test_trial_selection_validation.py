"""
Test suite for trial selection string validation.

This module validates that trial selection parsing correctly handles
various edge cases and provides clear error messages for invalid formats.

Covers:
- Valid formats (single indices, ranges, mixed)
- Invalid formats (negative indices, out of range, malformed strings)
- Edge cases (empty strings, whitespace, descending ranges)
- Strict vs lenient parsing modes
"""

import pytest

from synaptipy.shared.utils import parse_trial_selection_string


class TestTrialSelectionParsing:
    """Test trial selection string parsing with various formats."""

    def test_single_indices(self):
        """Parse comma-separated single indices."""
        result = parse_trial_selection_string("0, 2, 4", max_trials=10)
        assert result == {0, 2, 4}

    def test_simple_range(self):
        """Parse simple ascending range."""
        result = parse_trial_selection_string("0-3", max_trials=10)
        assert result == {0, 1, 2, 3}

    def test_mixed_format(self):
        """Parse mixed single indices and ranges."""
        result = parse_trial_selection_string("0, 2-4, 7", max_trials=10)
        assert result == {0, 2, 3, 4, 7}

    def test_descending_range(self):
        """Parse descending range (should work in reverse)."""
        result = parse_trial_selection_string("5-2", max_trials=10)
        assert result == {2, 3, 4, 5}

    def test_empty_string(self):
        """Empty string returns empty set."""
        result = parse_trial_selection_string("", max_trials=10)
        assert result == set()

    def test_whitespace_only(self):
        """Whitespace-only string returns empty set."""
        result = parse_trial_selection_string("   ", max_trials=10)
        assert result == set()

    def test_single_value(self):
        """Parse single value without commas."""
        result = parse_trial_selection_string("5", max_trials=10)
        assert result == {5}

    def test_extra_whitespace(self):
        """Handle extra whitespace gracefully."""
        result = parse_trial_selection_string("  0  ,  2 - 4  ,  7  ", max_trials=10)
        assert result == {0, 2, 3, 4, 7}

    def test_single_element_range(self):
        """Range where start equals end."""
        result = parse_trial_selection_string("3-3", max_trials=10)
        assert result == {3}


class TestTrialSelectionLenientMode:
    """Test lenient mode (default): warns but continues."""

    def test_negative_index_lenient(self):
        """Negative index should be ignored with warning."""
        result = parse_trial_selection_string("-1, 2, 3", max_trials=10, strict=False)
        # Negative values ignored, only valid ones remain
        assert result == {2, 3}

    def test_out_of_range_lenient(self):
        """Out-of-range index should be ignored with warning."""
        result = parse_trial_selection_string("0, 15, 3", max_trials=10, strict=False)
        # 15 is out of range (max is 9), should be ignored
        assert result == {0, 3}

    def test_malformed_number_lenient(self):
        """Malformed number should be skipped with warning."""
        result = parse_trial_selection_string("0, abc, 3", max_trials=10, strict=False)
        # 'abc' is invalid, should be skipped
        assert result == {0, 3}

    def test_incomplete_range_lenient(self):
        """Incomplete range should be skipped with warning."""
        result = parse_trial_selection_string("0, 2-, 5", max_trials=10, strict=False)
        # '2-' is incomplete, should be skipped
        assert result == {0, 5}

    def test_range_exceeds_max_lenient(self):
        """Range exceeding max_trials should be clamped."""
        result = parse_trial_selection_string("8-15", max_trials=10, strict=False)
        # Only valid indices (8, 9) should be included
        assert result == {8, 9}


class TestTrialSelectionStrictMode:
    """Test strict mode: raises ValueError on any invalid input."""

    def test_negative_index_strict(self):
        """Negative index should raise ValueError in strict mode."""
        with pytest.raises(ValueError, match="Negative index"):
            parse_trial_selection_string("-1, 2, 3", max_trials=10, strict=True)

    def test_out_of_range_strict(self):
        """Out-of-range index should raise ValueError in strict mode."""
        with pytest.raises(ValueError, match="exceeds available trials"):
            parse_trial_selection_string("0, 15, 3", max_trials=10, strict=True)

    def test_malformed_number_strict(self):
        """Malformed number should raise ValueError in strict mode."""
        with pytest.raises(ValueError, match="Invalid trial selection"):
            parse_trial_selection_string("0, abc, 3", max_trials=10, strict=True)

    def test_incomplete_range_strict(self):
        """Incomplete range should raise ValueError in strict mode."""
        with pytest.raises(ValueError, match="missing start or end"):
            parse_trial_selection_string("0, 2-, 5", max_trials=10, strict=True)

    def test_range_exceeds_max_strict(self):
        """Range exceeding max_trials should raise ValueError in strict mode."""
        with pytest.raises(ValueError, match="exceeds available trials"):
            parse_trial_selection_string("8-15", max_trials=10, strict=True)

    def test_negative_range_start_strict(self):
        """Negative range start should raise ValueError in strict mode."""
        with pytest.raises(ValueError, match="Negative indices not allowed"):
            parse_trial_selection_string("-2-5", max_trials=10, strict=True)

    def test_malformed_range_strict(self):
        """Malformed range with multiple dashes should raise ValueError."""
        with pytest.raises(ValueError, match="Invalid range format"):
            parse_trial_selection_string("0, 2-4-6, 8", max_trials=10, strict=True)


class TestTrialSelectionEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_zero_max_trials(self):
        """Parse with zero max_trials."""
        result = parse_trial_selection_string("0, 1, 2", max_trials=0, strict=False)
        # All indices should be out of range
        assert result == set()

    def test_large_max_trials(self):
        """Parse with very large max_trials."""
        result = parse_trial_selection_string("0, 1000, 5000", max_trials=10000)
        assert result == {0, 1000, 5000}

    def test_consecutive_commas(self):
        """Handle consecutive commas gracefully."""
        result = parse_trial_selection_string("0,,2,,4", max_trials=10)
        assert result == {0, 2, 4}

    def test_trailing_comma(self):
        """Handle trailing comma gracefully."""
        result = parse_trial_selection_string("0, 2, 4,", max_trials=10)
        assert result == {0, 2, 4}

    def test_leading_comma(self):
        """Handle leading comma gracefully."""
        result = parse_trial_selection_string(",0, 2, 4", max_trials=10)
        assert result == {0, 2, 4}

    def test_all_trials_in_range(self):
        """Select all trials using range."""
        result = parse_trial_selection_string("0-9", max_trials=10)
        assert result == set(range(10))

    def test_overlapping_ranges(self):
        """Overlapping ranges should merge into single set."""
        result = parse_trial_selection_string("0-3, 2-5", max_trials=10)
        assert result == {0, 1, 2, 3, 4, 5}

    def test_duplicate_indices(self):
        """Duplicate indices should appear once (set behavior)."""
        result = parse_trial_selection_string("2, 2, 2", max_trials=10)
        assert result == {2}

    def test_boundary_index(self):
        """Index at max_trials-1 should be valid."""
        result = parse_trial_selection_string("9", max_trials=10)
        assert result == {9}

    def test_boundary_index_plus_one(self):
        """Index at max_trials should be invalid in strict mode."""
        with pytest.raises(ValueError):
            parse_trial_selection_string("10", max_trials=10, strict=True)


class TestTrialSelectionIntegration:
    """Integration tests simulating real-world usage."""

    def test_typical_subset_selection(self):
        """Typical use case: select subset of trials."""
        # User wants trials 0, 1, 2, 5, 6, 7, 10 from 20 trials
        result = parse_trial_selection_string("0-2, 5-7, 10", max_trials=20)
        assert result == {0, 1, 2, 5, 6, 7, 10}

    def test_exclude_bad_trials(self):
        """Selecting all except specific trials (workaround pattern)."""
        # This requires application logic, but test the parsing
        all_trials = set(range(10))
        selected = parse_trial_selection_string("0-2, 5-9", max_trials=10)
        excluded = all_trials - selected
        assert excluded == {3, 4}

    def test_sparse_selection(self):
        """Sparse trial selection across large dataset."""
        result = parse_trial_selection_string("0, 10, 20, 30", max_trials=50)
        assert result == {0, 10, 20, 30}

    def test_protocol_subsets(self):
        """Different protocol phases (first 5, middle 10, last 5)."""
        # First 5 trials
        phase1 = parse_trial_selection_string("0-4", max_trials=20)
        # Middle 10 trials
        phase2 = parse_trial_selection_string("5-14", max_trials=20)
        # Last 5 trials
        phase3 = parse_trial_selection_string("15-19", max_trials=20)

        assert phase1 == {0, 1, 2, 3, 4}
        assert phase2 == {5, 6, 7, 8, 9, 10, 11, 12, 13, 14}
        assert phase3 == {15, 16, 17, 18, 19}
        assert phase1.isdisjoint(phase2)
        assert phase2.isdisjoint(phase3)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
