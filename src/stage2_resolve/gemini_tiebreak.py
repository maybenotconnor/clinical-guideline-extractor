"""Gemini Pro tiebreaker for remaining unresolved disagreements.

Expected to run on ~30 pages (2.5% of total). Cost minimal.
"""

from pathlib import Path

from ..shared.api_client import GeminiClient
from ..shared.cost_tracker import CostTracker
from ..extraction.prompt import load_tiebreak_prompt


def tiebreak_page(
    page_num: int,
    claude_text: str,
    flash_text: str,
    image_path: Path,
    guideline_dir: Path,
    client: GeminiClient,
) -> dict:
    """Send disputed region to Gemini Pro for tiebreaking.

    Returns:
        Dict with winner ("claude" or "flash"), correct_text, and reasoning.
    """
    prompt = load_tiebreak_prompt(
        guideline_dir,
        claude_text=claude_text,
        flash_text=flash_text,
    )

    response = client.tiebreak(
        image_path=image_path,
        prompt=prompt,
        stage="tiebreak",
        page=page_num,
    )

    if response is None:
        return {
            "winner": "claude",  # Default to Claude (primary extractor)
            "correct_text": claude_text,
            "reasoning": "Gemini Pro blocked — defaulting to Claude",
        }

    # Parse response to determine winner
    response_lower = response.lower()
    if "extractor a" in response_lower or "claude" in response_lower:
        winner = "claude"
    elif "extractor b" in response_lower or "flash" in response_lower or "gemini" in response_lower:
        winner = "flash"
    else:
        winner = "claude"  # Default to Claude if unclear

    return {
        "winner": winner,
        "correct_text": claude_text if winner == "claude" else flash_text,
        "reasoning": response,
    }
