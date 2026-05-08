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
            # Check if this is a range by looking for '-' after the first character
            # Single negative number: "-5"
            # Range with negative start: "-2-5" (ambiguous, but let's try to parse)
            # Valid range: "2-5"
            # We'll try parsing as range if there's a '-' not at position 0,
            # or if there are multiple '-' characters
            dash_count = part.count("-")
            is_range = dash_count >= 2 or (dash_count == 1 and not part.startswith("-"))

            if is_range:
                # Validate range format
                # Handle negative numbers: "-2-5" splits to ["", "2", "5"]
                # Incomplete ranges: "2-" splits to ["2", ""]
                range_parts = part.split("-")

                # Check for incomplete ranges first (before filtering)
                has_empty = "" in range_parts
                trailing_dash = part.endswith("-")

                # Filter out empty strings only from leading '-'
                if part.startswith("-"):
                    # Remove first empty string from leading '-'
                    if range_parts and range_parts[0] == "":
                        range_parts = range_parts[1:]

                # Now check if valid after filtering
                if len(range_parts) != 2 or has_empty and trailing_dash:
                    if has_empty:
                        error_msg = f"Incomplete range '{part}' (missing start or end)"
                    else:
                        error_msg = f"Invalid range format '{part}' (expected 'start-end')"
                    if strict:
                        errors.append(error_msg)
                        continue
                    log.warning(error_msg)
                    continue

                start_str, end_str = range_parts[0].strip(), range_parts[1].strip()

                # Check if start was negative (original part started with '-')
                if part.startswith("-"):
                    start_str = "-" + start_str

                # Double-check for empty bounds
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

                # In strict mode, reject ranges that exceed max_trials
                # In lenient mode, clamp to valid range
                if strict and (start >= max_trials or end >= max_trials):
                    error_msg = (
                        f"Range '{part}' exceeds available trials "
                        f"(max index: {max_trials - 1})"
                    )
                    errors.append(error_msg)
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
