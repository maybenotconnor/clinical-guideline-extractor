"""pdfplumber word-presence oracle for resolving extraction disagreements.

Resolves ~83% of disputed words per spike test results.
"""

from pathlib import Path

from ..stage0_prep.pdfplumber_extract import load_page_words

# Unicode symbols that pdfplumber's text layer may get wrong.
# The VLM reads the visual rendering and is more likely correct.
UNICODE_CLINICAL_SYMBOLS = {'↑', '↓', '→', '←', '↔', '≥', '≤', '±', '°'}


def check_word(word: str, page_words: set[str]) -> bool:
    """Check if a word exists in pdfplumber's page text (case-insensitive)."""
    return word.lower() in page_words


def resolve_disputed_words(
    claude_only: list[str],
    flash_only: list[str],
    native_dir: Path,
    page_num: int,
) -> dict:
    """Use pdfplumber as oracle to resolve disputed words.

    Returns:
        Dict with keys:
        - confirmed_claude: words pdfplumber confirms exist (Claude correct)
        - confirmed_flash: words pdfplumber confirms exist (Flash correct)
        - unresolved: words pdfplumber can't resolve
        - unicode_vlm_preferred: disputed Unicode symbols (prefer VLM)
    """
    page_words = load_page_words(native_dir, page_num)

    confirmed_claude: list[str] = []
    confirmed_flash: list[str] = []
    unresolved_claude: list[str] = []
    unresolved_flash: list[str] = []
    unicode_vlm: list[str] = []

    # Check Claude-only words
    for word in claude_only:
        if any(c in word for c in UNICODE_CLINICAL_SYMBOLS):
            # Unicode symbol dispute — prefer VLM version
            unicode_vlm.append(word)
        elif check_word(word, page_words):
            confirmed_claude.append(word)
        else:
            unresolved_claude.append(word)

    # Check Flash-only words
    for word in flash_only:
        if any(c in word for c in UNICODE_CLINICAL_SYMBOLS):
            unicode_vlm.append(word)
        elif check_word(word, page_words):
            confirmed_flash.append(word)
        else:
            unresolved_flash.append(word)

    return {
        "confirmed_claude": confirmed_claude,
        "confirmed_flash": confirmed_flash,
        "unresolved": unresolved_claude + unresolved_flash,
        "unicode_vlm_preferred": unicode_vlm,
        "resolution_rate": (
            (len(confirmed_claude) + len(confirmed_flash) + len(unicode_vlm))
            / max(len(claude_only) + len(flash_only), 1)
        ),
    }
