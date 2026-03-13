"""Load and template extraction prompts from guideline markdown files."""

from pathlib import Path


def load_prompt(prompt_path: Path, **kwargs) -> str:
    """Load a prompt template and inject variables.

    Template variables use {name} syntax:
    - {page}: page number
    - {fig}: figure counter
    - {claude_text}: Claude extraction (for tiebreak)
    - {flash_text}: Flash extraction (for tiebreak)
    """
    text = prompt_path.read_text()
    for key, value in kwargs.items():
        text = text.replace(f"{{{key}}}", str(value))
    return text


def load_extract_prompt(guideline_dir: Path, page: int, fig: int = 1) -> str:
    """Load the extraction prompt for a guideline, injecting page/fig numbers."""
    return load_prompt(guideline_dir / "extract.md", page=page, fig=fig)


def load_verify_prompt(guideline_dir: Path) -> str:
    """Load the verification prompt for error detection."""
    return load_prompt(guideline_dir / "verify.md")


def load_tiebreak_prompt(
    guideline_dir: Path,
    claude_text: str,
    flash_text: str,
) -> str:
    """Load the tiebreak prompt with both extractions injected."""
    return load_prompt(
        guideline_dir / "tiebreak.md",
        claude_text=claude_text,
        flash_text=flash_text,
    )
