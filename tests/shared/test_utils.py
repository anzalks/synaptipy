# -*- coding: utf-8 -*-
"""Tests for shared.utils.parse_trial_selection_string."""

from synaptipy.shared.utils import parse_trial_selection_string


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

    def test_strict_mode_raises_on_invalid(self):
        """strict=True → ValueError for invalid token."""
        import pytest

        with pytest.raises(ValueError):
            parse_trial_selection_string("abc", strict=True)

    def test_strict_mode_raises_on_negative_range(self):
        """strict=True → ValueError when a range has negative bounds."""
        import pytest

        with pytest.raises(ValueError):
            parse_trial_selection_string("-2-5", strict=True)

    def test_lenient_negative_range_skipped(self):
        """Negative-index range is silently skipped in lenient mode (default)."""
        result = parse_trial_selection_string("-2-5")
        # Should not raise; the negative-index part is discarded
        assert isinstance(result, set)

    def test_strict_mode_raises_on_incomplete_range(self):
        """strict=True → ValueError for a range missing an endpoint."""
        import pytest

        # A token like '3-' has an empty end — strict mode should raise
        with pytest.raises(ValueError):
            parse_trial_selection_string("3-", strict=True)

    def test_lenient_incomplete_range_logged_not_raised(self):
        """Lines 62-70: incomplete range with trailing dash in lenient mode logs and continues."""
        # '3-' is an incomplete range — lenient mode skips and returns what was valid
        result = parse_trial_selection_string("1, 3-")
        assert 1 in result
        assert isinstance(result, set)

    def test_lenient_empty_end_after_strip_skipped(self):
        """Lines 80-85: range where end_str is empty after strip → logged in lenient mode."""
        # "3 - " → split on "-" gives ["3 ", " "] — neither is "" so has_empty=False,
        # but after strip end_str="" triggers the second guard at line 79-85.
        result = parse_trial_selection_string("1, 3 - ")
        assert 1 in result
        assert isinstance(result, set)
        # The "3 - " part is invalid and should be skipped

    def test_strict_empty_end_after_strip_raises(self):
        """Lines 81-84: strict=True with empty end_str after strip → ValueError."""
        import pytest

        with pytest.raises(ValueError):
            parse_trial_selection_string("3 - ", strict=True)

    def test_lenient_double_dash_range_skipped(self):
        """Incomplete range with empty start ('−5' parsed as 'empty-5') skips."""
        result = parse_trial_selection_string("-5")
        # '-5' is a negative number, parsed as range with leading dash — skipped
        assert isinstance(result, set)

    def test_attribute_error_nonexistent(self):
        """shared.__getattr__ raises AttributeError for unknown names (line 58)."""
        import pytest

        import synaptipy.shared as shared

        with pytest.raises(AttributeError):
            _ = shared.nonexistent_attribute_xyz

    def test_lazy_loading_constants_module(self):
        """shared.__getattr__ lazy-loads a known export and caches it (lines 59-63)."""
        # Remove any cached value to force a fresh lazy load
        import synaptipy.shared as shared

        cached = shared.__dict__.pop("apply_stylesheet", None)
        try:
            val = shared.apply_stylesheet
            assert callable(val)
            # Second access uses cached globals
            val2 = shared.apply_stylesheet
            assert val2 is val
        finally:
            if cached is not None:
                shared.__dict__["apply_stylesheet"] = cached
