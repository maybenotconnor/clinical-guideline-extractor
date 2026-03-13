"""Drug/dose pattern detection and escalation to CRITICAL."""

import re

# Matches drug doses like "500 mg", "0.5 mL", "10,000 IU"
DOSE_PATTERN = re.compile(
    r'\d+\.?\d*\s*(mg|mcg|µg|g|kg|mL|L|units?|IU|mEq|mmol)\b',
    re.IGNORECASE,
)

# Matches standalone numbers that could be doses
NUMERIC_PATTERN = re.compile(r'\d+\.?\d*')


def is_dose_word(word: str) -> bool:
    """Check if a word looks like a drug dose (e.g., '500mg', '0.5')."""
    return bool(DOSE_PATTERN.search(word))


def has_dose_content(words: set[str]) -> bool:
    """Check if any word in a set matches a dose pattern."""
    return any(is_dose_word(w) for w in words)


def find_numeric_diffs(a_only: set[str], b_only: set[str]) -> list[dict]:
    """Find numbers that are plausible substitution errors between extractors.

    E.g., "0.5" in A vs "5" in B — CRITICAL (10x error).
    Only pairs numbers that look like they could be the same value with a
    transcription error (ratio between 1.5x and 100x), not every combination.
    Uses greedy closest-match to avoid cartesian explosion.
    """
    diffs = []
    a_nums = sorted({w for w in a_only if NUMERIC_PATTERN.fullmatch(w)})
    b_nums_remaining = sorted({w for w in b_only if NUMERIC_PATTERN.fullmatch(w)})

    for a_num in a_nums:
        try:
            a_val = float(a_num)
        except ValueError:
            continue
        if a_val == 0:
            continue

        # Find the closest match in b_nums
        best_match = None
        best_ratio = float('inf')
        for b_num in b_nums_remaining:
            try:
                b_val = float(b_num)
            except ValueError:
                continue
            if b_val == 0 or a_val == b_val:
                continue
            ratio = max(a_val, b_val) / min(a_val, b_val)
            # Only flag plausible substitution errors (1.5x to 100x)
            if 1.5 <= ratio <= 100 and ratio < best_ratio:
                best_ratio = ratio
                best_match = b_num

        if best_match is not None:
            b_nums_remaining.remove(best_match)
            diffs.append({
                "a_value": a_num,
                "b_value": best_match,
                "ratio": round(best_ratio, 2),
                "likely_10x_error": best_ratio == 10.0,
            })

    return diffs
