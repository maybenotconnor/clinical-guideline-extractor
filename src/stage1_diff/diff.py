"""Word-level diff between Claude and Flash extractions.

Compares Path A (Claude) and Path B (Flash) per page, classifying
disagreements into: AGREE, CLAUDE_ONLY, FLASH_ONLY, NUMERIC_DIFF, BLOCKED.
"""

import json
from dataclasses import dataclass, asdict
from enum import Enum
from pathlib import Path

from rich.console import Console
from rich.progress import Progress

from ..shared.manifest import Manifest
from .tokenize import word_set_lower
from .escalate import has_dose_content, find_numeric_diffs, DOSE_PATTERN

console = Console()


class DiffCategory(str, Enum):
    AGREE = "agree"
    CLAUDE_ONLY = "claude_only"
    FLASH_ONLY = "flash_only"
    NUMERIC_DIFF = "numeric_diff"
    BLOCKED = "blocked"


@dataclass
class PageDiff:
    page: int
    jaccard: float
    agree_count: int
    claude_only: list[str]
    flash_only: list[str]
    numeric_diffs: list[dict]
    drug_disagreements: int
    flash_blocked: bool
    auto_accept: bool
    needs_resolution: bool
    needs_human_review: bool


def diff_page(
    page_num: int,
    claude_text: str,
    flash_text: str | None,
) -> PageDiff:
    """Compute word-level diff for a single page.

    Args:
        page_num: Page number.
        claude_text: Claude's extraction.
        flash_text: Flash's extraction (None if blocked).

    Returns:
        PageDiff with classification details.
    """
    if flash_text is None:
        # Flash blocked — accept Claude, flag for validation
        claude_words = word_set_lower(claude_text)
        return PageDiff(
            page=page_num,
            jaccard=0.0,
            agree_count=len(claude_words),
            claude_only=list(claude_words),
            flash_only=[],
            numeric_diffs=[],
            drug_disagreements=0,
            flash_blocked=True,
            auto_accept=False,
            needs_resolution=False,
            needs_human_review=False,
        )

    claude_words = word_set_lower(claude_text)
    flash_words = word_set_lower(flash_text)

    agree = claude_words & flash_words
    claude_only = claude_words - flash_words
    flash_only = flash_words - claude_words
    union = claude_words | flash_words

    jaccard = len(agree) / len(union) if union else 1.0

    # Find numeric differences
    numeric_diffs = find_numeric_diffs(claude_only, flash_only)

    # Count drug-related disagreements.
    # DOSE_PATTERN needs number+unit in one string, but tokenization splits
    # "500 mg" into separate words. Check disputed words against dose units
    # and numbers that appear in dose contexts in the original text.
    drug_disagreements = 0
    dose_units = {'mg', 'mcg', 'µg', 'g', 'kg', 'ml', 'l', 'units', 'unit', 'iu', 'meq', 'mmol'}
    disputed = claude_only | flash_only
    # A disputed word is drug-related if it's a dose unit or a number AND
    # the original text contains dose patterns
    has_doses_in_claude = bool(DOSE_PATTERN.search(claude_text))
    has_doses_in_flash = bool(DOSE_PATTERN.search(flash_text))
    if has_doses_in_claude or has_doses_in_flash:
        for word in disputed:
            if word in dose_units or (word.replace('.', '', 1).isdigit() and word not in agree):
                drug_disagreements += 1

    # Classification per spec thresholds
    auto_accept = jaccard > 0.80 and drug_disagreements == 0
    needs_human_review = jaccard < 0.60 or drug_disagreements > 0 or len(numeric_diffs) > 0
    needs_resolution = not auto_accept and not needs_human_review

    return PageDiff(
        page=page_num,
        jaccard=round(jaccard, 4),
        agree_count=len(agree),
        claude_only=sorted(claude_only),
        flash_only=sorted(flash_only),
        numeric_diffs=numeric_diffs,
        drug_disagreements=drug_disagreements,
        flash_blocked=False,
        auto_accept=auto_accept,
        needs_resolution=needs_resolution or needs_human_review,
        needs_human_review=needs_human_review,
    )


def run_diff(
    path_a_dir: Path,
    path_b_dir: Path,
    output_dir: Path,
    pages: list[int],
    manifest: Manifest,
) -> dict[int, PageDiff]:
    """Run word-level diff across all pages.

    Returns:
        Dict mapping page number to PageDiff.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    results: dict[int, PageDiff] = {}

    console.print(f"  Running word-level diff on {len(pages)} pages...")

    auto_accept_count = 0
    resolution_count = 0
    human_review_count = 0
    blocked_count = 0

    with Progress() as progress:
        task = progress.add_task("Diff", total=len(pages))

        for page_num in pages:
            # Load Claude extraction
            claude_path = path_a_dir / "pages" / f"page-{page_num:04d}.md"
            if not claude_path.exists():
                progress.update(task, advance=1)
                continue
            claude_text = claude_path.read_text()

            # Load Flash extraction (may not exist if blocked)
            flash_path = path_b_dir / "pages" / f"page-{page_num:04d}.md"
            flash_text = flash_path.read_text() if flash_path.exists() else None

            # Check manifest for blocked status
            page_state = manifest.get(page_num)
            if page_state.flash_blocked:
                flash_text = None

            page_diff = diff_page(page_num, claude_text, flash_text)
            results[page_num] = page_diff

            # Save per-page diff
            diff_path = output_dir / f"page-{page_num:04d}.json"
            diff_path.write_text(json.dumps(asdict(page_diff), indent=2))

            # Update manifest
            manifest.update(
                page_num,
                status="diffed",
                jaccard=page_diff.jaccard,
                disagreement_count=len(page_diff.claude_only) + len(page_diff.flash_only),
                drug_disagreements=page_diff.drug_disagreements,
            )

            # Count categories
            if page_diff.flash_blocked:
                blocked_count += 1
            elif page_diff.auto_accept:
                auto_accept_count += 1
            elif page_diff.needs_human_review:
                human_review_count += 1
            else:
                resolution_count += 1

            progress.update(task, advance=1)

    total = len(pages) or 1  # Avoid division by zero
    console.print(f"  [green]Diff complete:[/green]")
    console.print(f"    Auto-accept: {auto_accept_count} ({auto_accept_count/total*100:.1f}%)")
    console.print(f"    Needs resolution: {resolution_count} ({resolution_count/total*100:.1f}%)")
    console.print(f"    Needs human review: {human_review_count} ({human_review_count/total*100:.1f}%)")
    console.print(f"    Flash blocked: {blocked_count} ({blocked_count/total*100:.1f}%)")

    return results
