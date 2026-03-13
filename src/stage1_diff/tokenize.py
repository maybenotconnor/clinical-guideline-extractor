"""Word-level tokenization for diff comparison.

Strips markdown formatting, splits on whitespace, preserves original case
for output but lowercases for comparison.
"""

import re

# Markdown formatting to strip
_MD_CHARS = re.compile(r'[|#*\->\[\](){}`~_]')
_HTML_TAGS = re.compile(r'<[^>]+>')
_HTML_COMMENTS = re.compile(r'<!--.*?-->', re.DOTALL)
_WHITESPACE = re.compile(r'\s+')
_BR_TAG = re.compile(r'<br\s*/?>', re.IGNORECASE)


def tokenize(text: str) -> list[str]:
    """Tokenize text into words, stripping markdown formatting.

    Returns words in original case.
    """
    # Remove HTML comments (<!-- page:N --> etc.)
    text = _HTML_COMMENTS.sub(' ', text)
    # Replace <br> with space
    text = _BR_TAG.sub(' ', text)
    # Remove HTML tags
    text = _HTML_TAGS.sub(' ', text)
    # Remove markdown formatting characters
    text = _MD_CHARS.sub(' ', text)
    # Split on whitespace
    words = _WHITESPACE.split(text.strip())
    return [w for w in words if w]


def word_set_lower(text: str) -> set[str]:
    """Get lowercase word set for comparison."""
    return {w.lower() for w in tokenize(text)}


def word_multiset(text: str) -> dict[str, int]:
    """Get word frequency map (lowercase) for more precise comparison."""
    counts: dict[str, int] = {}
    for w in tokenize(text):
        key = w.lower()
        counts[key] = counts.get(key, 0) + 1
    return counts
