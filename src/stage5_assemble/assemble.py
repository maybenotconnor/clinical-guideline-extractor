"""Stage 5: Assemble final output — single guideline.md + reports.

Concatenates all resolved pages with page boundary comments,
normalizes heading levels using Docling structure, adds frontmatter.
"""

import json
from datetime import date
from pathlib import Path

from rich.console import Console

console = Console()


def normalize_headings(
    markdown: str,
    page_num: int,
    structure: dict,
) -> str:
    """Normalize heading levels using Docling's heading hierarchy.

    Docling detects heading level from font size/weight consistently
    across the full document, while VLMs may assign inconsistent levels
    page-to-page.
    """
    # Build a map of heading texts to their Docling-detected levels
    heading_map: dict[str, int] = {}
    for h in structure.get("heading_tree", []):
        if h.get("page") == page_num:
            heading_map[h["text"].strip().lower()] = h["level"]

    if not heading_map:
        return markdown

    lines = markdown.split("\n")
    result = []
    for line in lines:
        stripped = line.lstrip("#").strip()
        if line.startswith("#") and stripped.lower() in heading_map:
            level = heading_map[stripped.lower()]
            result.append("#" * level + " " + stripped)
        else:
            result.append(line)

    return "\n".join(result)


def build_frontmatter(
    guideline_name: str,
    publisher: str,
    page_count: int,
    pipeline_version: str = "0.3.0",
) -> str:
    """Build YAML frontmatter block."""
    return f"""---
source: {guideline_name}
publisher: {publisher}
extracted: {date.today().isoformat()}
pipeline_version: {pipeline_version}
page_count: {page_count}
---

"""


def assemble_guideline(
    resolved_dir: Path,
    output_dir: Path,
    pages: list[int],
    structure: dict,
    guideline_name: str = "Uganda Clinical Guidelines 2023",
    publisher: str = "Ministry of Health, Republic of Uganda",
) -> Path:
    """Assemble all resolved pages into a single guideline.md.

    Returns path to the output file.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "guideline.md"

    parts = []

    # Frontmatter
    parts.append(build_frontmatter(
        guideline_name=guideline_name,
        publisher=publisher,
        page_count=len(pages),
    ))

    # Concatenate pages with boundary comments
    for page_num in sorted(pages):
        md_path = resolved_dir / f"page-{page_num:04d}.md"
        if not md_path.exists():
            continue

        content = md_path.read_text().strip()

        # Normalize headings if Docling structure available
        if structure.get("heading_tree"):
            content = normalize_headings(content, page_num, structure)

        parts.append(f"<!-- page:{page_num} -->")
        parts.append(content)
        parts.append("")  # Blank line between pages

    output_path.write_text("\n".join(parts))
    console.print(f"  [green]Assembled {len(pages)} pages → {output_path}[/green]")
    return output_path


def generate_extraction_report(
    manifest_data: dict,
    cost_summary: dict,
    resolution_methods: dict,
    review_items: list[dict],
    output_dir: Path,
) -> Path:
    """Generate extraction-report.json with full audit trail."""
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "extraction-report.json"

    # Compute aggregates from manifest
    pages = manifest_data.get("pages", [])
    total_pages = len(pages)

    # Per-page summaries
    page_summaries = []
    for ps in pages:
        page_summaries.append({
            "page": ps["page_num"],
            "status": ps["status"],
            "jaccard": ps.get("jaccard"),
            "disagreements": ps.get("disagreement_count", 0),
            "drug_disagreements": ps.get("drug_disagreements", 0),
            "resolution_method": ps.get("resolution_method"),
            "flash_blocked": ps.get("flash_blocked", False),
        })

    # Aggregate stats
    jaccards = [ps["jaccard"] for ps in page_summaries if ps["jaccard"] is not None]
    avg_jaccard = sum(jaccards) / len(jaccards) if jaccards else 0

    auto_accept = sum(1 for ps in page_summaries if ps["resolution_method"] == "auto_accept")
    pages_processed = sum(1 for ps in page_summaries if ps["resolution_method"] is not None)
    agreement_rate = auto_accept / pages_processed if pages_processed else 0

    report = {
        "aggregate": {
            "total_pages": total_pages,
            "average_jaccard": round(avg_jaccard, 4),
            "agreement_rate": round(agreement_rate, 4),
            "auto_accepted": auto_accept,
            "pages_requiring_review": len(review_items),
            "resolution_methods": resolution_methods,
        },
        "cost": cost_summary,
        "review_items_count": {
            "CRITICAL": sum(1 for r in review_items if r.get("tier") == "CRITICAL"),
            "HIGH": sum(1 for r in review_items if r.get("tier") == "HIGH"),
            "MEDIUM": sum(1 for r in review_items if r.get("tier") == "MEDIUM"),
            "LOW": sum(1 for r in review_items if r.get("tier") == "LOW"),
        },
        "pages": page_summaries,
    }

    report_path.write_text(json.dumps(report, indent=2))
    console.print(f"  [green]Extraction report: {report_path}[/green]")
    return report_path
