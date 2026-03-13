"""Stage 2: Resolve disagreements using decision rules from the spec.

Decision table:
- Both agree → Accept Claude's formatting
- pdfplumber confirms one → Accept confirmed
- Unicode symbol dispute → Prefer VLM version
- Gemini Pro confirms one → Accept confirmed
- Drug/dose, pdfplumber confirms → Accept confirmed, still flag for Stage 3
- Drug/dose, unresolved → CRITICAL → human review
- Flash blocked → Accept Claude, flag for Stage 3
"""

import json
from pathlib import Path

from rich.console import Console
from rich.progress import Progress

from ..shared.api_client import GeminiClient
from ..shared.cost_tracker import CostTracker
from ..shared.manifest import Manifest
from ..stage1_diff.diff import PageDiff
from .pdfplumber_oracle import resolve_disputed_words
from .gemini_tiebreak import tiebreak_page

console = Console()


def resolve_page(
    page_num: int,
    page_diff: PageDiff,
    claude_text: str,
    flash_text: str | None,
    native_dir: Path,
    image_dir: Path,
    guideline_dir: Path,
    gemini_client: GeminiClient | None,
) -> dict:
    """Resolve a single page's disagreements.

    Returns:
        Dict with resolved_text, method, review_items.
    """
    # Case: auto-accept (high agreement, no drug disagreements)
    if page_diff.auto_accept:
        return {
            "resolved_text": claude_text,
            "method": "auto_accept",
            "review_items": [],
        }

    # Case: Flash blocked
    if page_diff.flash_blocked:
        return {
            "resolved_text": claude_text,
            "method": "claude_only",
            "review_items": [{
                "page": page_num,
                "tier": "HIGH",
                "reason": "Flash blocked — no cross-check available",
                "type": "blocked",
            }],
        }

    review_items = []

    # Step 1: pdfplumber oracle
    oracle_result = resolve_disputed_words(
        claude_only=page_diff.claude_only,
        flash_only=page_diff.flash_only,
        native_dir=native_dir,
        page_num=page_num,
    )

    # If oracle resolved everything AND Flash had no confirmed-missing words,
    # Claude's text is correct. But if pdfplumber confirmed words that Flash
    # found and Claude missed, we need tiebreak to get the full text.
    flash_has_confirmed_missing = len(oracle_result.get("confirmed_flash", [])) > 0

    if not oracle_result["unresolved"] and not flash_has_confirmed_missing:
        method = "pdfplumber_oracle"
        if page_diff.drug_disagreements > 0:
            review_items.append({
                "page": page_num,
                "tier": "HIGH",
                "reason": f"Drug/dose disagreement resolved by pdfplumber ({page_diff.drug_disagreements} items)",
                "type": "drug_dose_resolved",
            })
        return {
            "resolved_text": claude_text,
            "method": method,
            "review_items": review_items,
        }

    # If pdfplumber confirmed Flash has words Claude missed, or there are
    # unresolved words, escalate to Gemini Pro tiebreak
    needs_tiebreak = oracle_result.get("unresolved") or flash_has_confirmed_missing

    # Step 2: Gemini Pro tiebreak
    if gemini_client and needs_tiebreak:
        image_path = image_dir / f"page-{page_num:04d}.png"
        if image_path.exists():
            tiebreak = tiebreak_page(
                page_num=page_num,
                claude_text=claude_text,
                flash_text=flash_text or "",
                image_path=image_path,
                guideline_dir=guideline_dir,
                client=gemini_client,
            )

            resolved_text = tiebreak["correct_text"]
            method = f"tiebreak_{tiebreak['winner']}"

            # Drug/dose disagreements always get flagged
            if page_diff.drug_disagreements > 0:
                review_items.append({
                    "page": page_num,
                    "tier": "CRITICAL",
                    "reason": f"Drug/dose disagreement: {page_diff.numeric_diffs}",
                    "type": "drug_dose_unresolved",
                    "tiebreak_winner": tiebreak["winner"],
                })

            return {
                "resolved_text": resolved_text,
                "method": method,
                "review_items": review_items,
            }

    # Fallback: use Claude's text, flag for review
    if page_diff.drug_disagreements > 0:
        review_items.append({
            "page": page_num,
            "tier": "CRITICAL",
            "reason": f"Drug/dose disagreement unresolved ({page_diff.drug_disagreements} items)",
            "type": "drug_dose_unresolved",
        })

    if page_diff.needs_human_review:
        review_items.append({
            "page": page_num,
            "tier": "MEDIUM",
            "reason": f"Low agreement (Jaccard: {page_diff.jaccard})",
            "type": "low_agreement",
        })

    return {
        "resolved_text": claude_text,
        "method": "claude_default",
        "review_items": review_items,
    }


def run_resolution(
    diffs: dict[int, PageDiff],
    path_a_dir: Path,
    path_b_dir: Path,
    native_dir: Path,
    image_dir: Path,
    guideline_dir: Path,
    output_dir: Path,
    pages: list[int],
    cost_tracker: CostTracker,
    manifest: Manifest,
) -> dict:
    """Run Stage 2 resolution across all pages.

    Returns:
        Dict with per-page results and aggregate review queue.
    """
    resolved_dir = output_dir / "resolved"
    resolved_dir.mkdir(parents=True, exist_ok=True)

    # Only init Gemini Pro if there are pages needing tiebreak
    pages_needing_tiebreak = [
        p for p in pages
        if p in diffs and not diffs[p].auto_accept and not diffs[p].flash_blocked
    ]
    gemini_client = None
    if pages_needing_tiebreak:
        try:
            gemini_client = GeminiClient(cost_tracker=cost_tracker)
        except ValueError:
            console.print("  [yellow]No Gemini API key — skipping tiebreak[/yellow]")

    all_review_items: list[dict] = []
    resolution_methods: dict[str, int] = {}

    console.print(f"  Resolving {len(pages)} pages...")

    with Progress() as progress:
        task = progress.add_task("Resolve", total=len(pages))

        for page_num in pages:
            page_diff = diffs.get(page_num)
            if not page_diff:
                progress.update(task, advance=1)
                continue

            # Load extractions
            claude_path = path_a_dir / "pages" / f"page-{page_num:04d}.md"
            claude_text = claude_path.read_text() if claude_path.exists() else ""

            flash_path = path_b_dir / "pages" / f"page-{page_num:04d}.md"
            flash_text = flash_path.read_text() if flash_path.exists() else None

            result = resolve_page(
                page_num=page_num,
                page_diff=page_diff,
                claude_text=claude_text,
                flash_text=flash_text,
                native_dir=native_dir,
                image_dir=image_dir,
                guideline_dir=guideline_dir,
                gemini_client=gemini_client,
            )

            # Save resolved markdown
            out_path = resolved_dir / f"page-{page_num:04d}.md"
            out_path.write_text(result["resolved_text"])

            # Track methods
            method = result["method"]
            resolution_methods[method] = resolution_methods.get(method, 0) + 1

            # Collect review items
            all_review_items.extend(result["review_items"])

            # Update manifest
            manifest.update(
                page_num,
                status="resolved",
                resolution_method=method,
            )

            progress.update(task, advance=1)

    # Save review queue
    review_queue_path = output_dir / "review-queue.json"
    review_queue_path.write_text(json.dumps(all_review_items, indent=2))

    console.print(f"  [green]Resolution complete:[/green]")
    for method, count in sorted(resolution_methods.items()):
        console.print(f"    {method}: {count}")
    console.print(f"    Review items: {len(all_review_items)}")

    return {
        "review_items": all_review_items,
        "resolution_methods": resolution_methods,
    }
