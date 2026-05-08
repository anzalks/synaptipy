import logging
from typing import Set

log = logging.getLogger(__name__)


def parse_trial_selection_string(selection_str: str, max_trials: int = 9999, strict: bool = False) -> Set[int]:
    """
    Parses a string of trial indices and ranges into a set of integers.
    Supports formats like "0, 2, 4-6" -> {0, 2, 4, 5, 6}

    Args:
        selection_str: The string to parse.
        max_trials: Maximum allowed trial index (exclusive) to prevent infinite loops from bad ranges.
        strict: If True, raise ValueError on any parsing error instead of logging warnings.

    Returns:
        A set of valid trial indices. Returns empty set if parsing fails or string is empty.

    Raises:
        ValueError: If strict=True and the format is invalid or indices are out of range.
    """
    indices = set()
    if not selection_str or not selection_str.strip():
        return indices

    parts = selection_str.split(",")
    errors = []

    for part in parts:
        part = part.strip()
        if not part:
            continue
        try:
            if "-" in part:
                # Validate range format
                range_parts = part.split("-")
                if len(range_parts) != 2:
                    error_msg = f"Invalid range format '{part}' (expected 'start-end')"
                    if strict:
                        errors.append(error_msg)
                        continue
                    log.warning(error_msg)
                    continue

                start_str, end_str = range_parts[0].strip(), range_parts[1].strip()

                # Check for empty bounds
                if not start_str or not end_str:
                    error_msg = f"Incomplete range '{part}' (missing start or end)"
                    if strict:
                        errors.append(error_msg)
                        continue
                    log.warning(error_msg)
                    continue

                start = int(start_str)
                end = int(end_str)

                # Validate range bounds
                if start < 0 or end < 0:
                    error_msg = f"Negative indices not allowed in range '{part}'"
                    if strict:
                        errors.append(error_msg)
                        continue
                    log.warning(error_msg)
                    continue

                if start >= max_trials or end >= max_trials:
                    error_msg = (
                        f"Range '{part}' exceeds available trials "
                        f"(max index: {max_trials - 1})"
                    )
                    if strict:
                        errors.append(error_msg)
                        continue
                    log.warning(error_msg)
                    continue

                # Handle descending ranges
                step = 1 if start <= end else -1
                for i in range(start, end + step, step):
                    if 0 <= i < max_trials:
                        indices.add(i)
            else:
                val = int(part)

                # Validate single index
                if val < 0:
                    error_msg = f"Negative index '{val}' not allowed"
                    if strict:
                        errors.append(error_msg)
                        continue
                    log.warning(error_msg)
                    continue

                if val >= max_trials:
                    error_msg = (
                        f"Index {val} exceeds available trials "
                        f"(max index: {max_trials - 1})"
                    )
                    if strict:
                        errors.append(error_msg)
                        continue
                    log.warning(error_msg)
                    continue

                indices.add(val)

        except ValueError as e:
            error_msg = f"Invalid trial selection part '{part}': {e}"
            if strict:
                errors.append(error_msg)
            else:
                log.warning(error_msg)
            continue

    # If strict mode and errors occurred, raise combined error
    if strict and errors:
        raise ValueError(
            f"Invalid trial selection string '{selection_str}': "
            + "; ".join(errors)
        )

    return indices
