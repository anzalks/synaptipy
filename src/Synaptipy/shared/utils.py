import logging
from typing import List, Set

log = logging.getLogger(__name__)

def parse_trial_selection_string(selection_str: str, max_trials: int = 9999) -> Set[int]:
    """
    Parses a string of trial indices and ranges into a set of integers.
    Supports formats like "0, 2, 4-6" -> {0, 2, 4, 5, 6}

    Args:
        selection_str: The string to parse.
        max_trials: Maximum allowed trial index (exclusive) to prevent infinite loops from bad ranges.

    Returns:
        A set of valid trial indices. Returns empty set if parsing fails or string is empty.
    """
    indices = set()
    if not selection_str or not selection_str.strip():
        return indices

    parts = selection_str.split(',')
    for part in parts:
        part = part.strip()
        if not part:
            continue
        try:
            if '-' in part:
                start_str, end_str = part.split('-', 1)
                start = int(start_str.strip())
                end = int(end_str.strip())
                # Handle descending ranges or ranges that hit max_trials
                step = 1 if start <= end else -1
                for i in range(start, end + step, step):
                    if 0 <= i < max_trials:
                        indices.add(i)
            else:
                val = int(part)
                if 0 <= val < max_trials:
                    indices.add(val)
        except ValueError:
            log.warning(f"Failed to parse trial selection part: '{part}'")
            continue
            
    return indices
