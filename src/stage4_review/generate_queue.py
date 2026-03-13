"""Build prioritized review queue from all validation results.

Items sorted by priority:
  Tier 1 (CRITICAL): drug/dose disagreements, wrong dose/drug/route, impossible combos
  Tier 2 (HIGH): missing content, Flash-blocked pages, cross-page contradictions
  Tier 3 (MEDIUM): non-clinical word disagreements, formatting issues
"""

import json
from pathlib import Path

from rich.console import Console

console = Console()

TIER_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}


def build_review_queue(
    stage2_review_items: list[dict],
    regex_findings: list[dict],
    dose_findings: list[dict],
    claude_findings: list[dict],
    med7_findings: list[dict],
) -> list[dict]:
    """Merge all validation findings into a single prioritized review queue.

    Returns:
        Sorted list of review items (CRITICAL first).
    """
    all_items: list[dict] = []

    # Stage 2 resolution items
    for item in stage2_review_items:
        item.setdefault("source", "stage2_resolution")
        all_items.append(item)

    # Regex validation
    for finding in regex_findings:
        all_items.append({
            "page": finding["page"],
            "tier": finding["severity"],
            "reason": finding["detail"],
            "type": finding["type"],
            "match": finding.get("match", ""),
            "source": "regex_validation",
        })

    # Dose confirmation
    for finding in dose_findings:
        all_items.append({
            "page": finding["page"],
            "tier": finding["severity"],
            "reason": finding["detail"],
            "type": finding["type"],
            "dose": finding.get("dose", ""),
            "source": "dose_confirmation",
        })

    # Claude verification
    for finding in claude_findings:
        all_items.append({
            "page": finding.get("page", 0),
            "tier": finding.get("severity", "MEDIUM"),
            "reason": finding.get("detail", ""),
            "type": "claude_verification",
            "extraction_says": finding.get("extraction_says", ""),
            "image_shows": finding.get("image_shows", ""),
            "source": "claude_verification",
        })

    # Med7 NER
    for finding in med7_findings:
        all_items.append({
            "page": finding.get("page", 0),
            "tier": finding.get("severity", "HIGH"),
            "reason": finding.get("detail", ""),
            "type": finding["type"],
            "source": "med7_ner",
        })

    # Sort by tier priority, then page number
    all_items.sort(key=lambda x: (TIER_ORDER.get(x.get("tier", "LOW"), 3), x.get("page", 0)))

    return all_items


def save_review_queue(items: list[dict], output_path: Path):
    """Save the review queue to JSON."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(items, indent=2))

    # Print summary
    by_tier: dict[str, int] = {}
    for item in items:
        tier = item.get("tier", "LOW")
        by_tier[tier] = by_tier.get(tier, 0) + 1

    console.print(f"  [green]Review queue: {len(items)} items[/green]")
    for tier in ["CRITICAL", "HIGH", "MEDIUM", "LOW"]:
        if tier in by_tier:
            console.print(f"    {tier}: {by_tier[tier]}")
