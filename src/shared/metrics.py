"""Word-level similarity metrics for comparing extractions."""

import re


# Markdown formatting characters to strip before comparison
_MD_STRIP = re.compile(r'[|#*\->\[\](){}`~]')
_HTML_TAG = re.compile(r'<[^>]+>')
_WHITESPACE = re.compile(r'\s+')


def tokenize_words(text: str, strip_markdown: bool = True) -> list[str]:
    """Tokenize text into words, optionally stripping markdown formatting.

    Returns words in original case. For comparison, lowercase externally.
    """
    if strip_markdown:
        text = _HTML_TAG.sub(' ', text)
        text = _MD_STRIP.sub(' ', text)
    words = _WHITESPACE.split(text.strip())
    return [w for w in words if w]


def word_set(text: str) -> set[str]:
    """Get lowercase word set from text, stripping markdown."""
    return {w.lower() for w in tokenize_words(text)}


def jaccard(text_a: str, text_b: str) -> float:
    """Word-level Jaccard similarity between two texts."""
    set_a = word_set(text_a)
    set_b = word_set(text_b)
    if not set_a and not set_b:
        return 1.0
    if not set_a or not set_b:
        return 0.0
    intersection = set_a & set_b
    union = set_a | set_b
    return len(intersection) / len(union)


def f1(text_a: str, text_b: str) -> float:
    """Word-level F1 score (text_a = prediction, text_b = reference)."""
    pred = word_set(text_a)
    ref = word_set(text_b)
    if not pred and not ref:
        return 1.0
    if not pred or not ref:
        return 0.0
    tp = len(pred & ref)
    precision = tp / len(pred)
    recall = tp / len(ref)
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def word_diff(text_a: str, text_b: str) -> dict:
    """Compute word-level diff between two texts.

    Returns:
        dict with keys: agree, a_only, b_only, jaccard
    """
    set_a = word_set(text_a)
    set_b = word_set(text_b)
    agree = set_a & set_b
    a_only = set_a - set_b
    b_only = set_b - set_a
    union = set_a | set_b
    jac = len(agree) / len(union) if union else 1.0

    return {
        "agree": agree,
        "a_only": a_only,
        "b_only": b_only,
        "jaccard": jac,
    }
