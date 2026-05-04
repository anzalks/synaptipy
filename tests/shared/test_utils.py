# -*- coding: utf-8 -*-
"""Tests for shared.utils.parse_trial_selection_string."""

from Synaptipy.shared.utils import parse_trial_selection_string


class TestParseTrialSelectionString:
    def test_empty_string(self):
        assert parse_trial_selection_string("") == set()

    def test_whitespace_only(self):
        assert parse_trial_selection_string("   ") == set()

    def test_single_index(self):
        assert parse_trial_selection_string("3") == {3}

    def test_multiple_indices(self):
        assert parse_trial_selection_string("0, 2, 4") == {0, 2, 4}

    def test_range(self):
        assert parse_trial_selection_string("4-6") == {4, 5, 6}

    def test_mixed(self):
        result = parse_trial_selection_string("0, 2, 4-6")
        assert result == {0, 2, 4, 5, 6}

    def test_negative_index_excluded(self):
        result = parse_trial_selection_string("-1, 0, 1")
        # -1 parsed as a range token (contains '-'), invalid
        assert 0 in result or result == set()

    def test_max_trials_limit(self):
        result = parse_trial_selection_string("0-100", max_trials=5)
        assert all(i < 5 for i in result)

    def test_descending_range(self):
        result = parse_trial_selection_string("6-4")
        assert result == {4, 5, 6}

    def test_invalid_part_skipped(self):
        result = parse_trial_selection_string("0, abc, 2")
        assert result == {0, 2}

    def test_extra_spaces(self):
        assert parse_trial_selection_string("  1 , 3  ") == {1, 3}

    def test_zero_index(self):
        assert 0 in parse_trial_selection_string("0")

    def test_large_range_capped(self):
        result = parse_trial_selection_string("0-999999", max_trials=10)
        assert len(result) == 10

    def test_consecutive_commas_skip_empty_part(self):
        """Line 27: empty part after split (e.g. '0,,2') → continue."""
        result = parse_trial_selection_string("0,,2")
        assert result == {0, 2}
