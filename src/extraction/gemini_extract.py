"""Path B: Gemini Flash extraction (cross-check).

Different model family from Claude — agreement is a strong quality signal.
77.8% Jaccard vs native, 19x cheaper than Gemini Pro.
Safety filters are non-deterministic: retry once, then mark Claude-only.
"""

import json
import re
from pathlib import Path

from rich.console import Console
from rich.progress import Progress

from ..shared.api_client import GeminiClient
from ..shared.cost_tracker import CostTracker
from ..shared.manifest import Manifest
from .prompt import load_extract_prompt

console = Console()


def _parse_response(text: str) -> tuple[str, dict | None]:
    """Split response into markdown content and JSON metadata block."""
    json_match = re.search(r'```json\s*\n(.*?)```\s*$', text, re.DOTALL)
    if json_match:
        markdown = text[:json_match.start()].strip()
        try:
            metadata = json.loads(json_match.group(1))
        except json.JSONDecodeError:
            metadata = None
    else:
        markdown = text.strip()
        metadata = None
    return markdown, metadata


def extract_pages(
    guideline_dir: Path,
    image_dir: Path,
    output_dir: Path,
    pages: list[int],
    cost_tracker: CostTracker,
    manifest: Manifest,
) -> dict[int, Path]:
    """Extract pages via Gemini Flash with safety filter retry.

    If Flash returns empty (safety block):
    1. Retry once (non-deterministic filter may pass on retry)
    2. If still blocked, mark as Claude-only in manifest

    Returns:
        Dict mapping page number to markdown output path.
    """
    pages_dir = output_dir / "pages"
    meta_dir = output_dir / "meta"
    pages_dir.mkdir(parents=True, exist_ok=True)
    meta_dir.mkdir(parents=True, exist_ok=True)

    client = GeminiClient(cost_tracker=cost_tracker)
    results: dict[int, Path] = {}
    blocked_pages: list[int] = []

    # Check cache
    pages_to_extract = []
    for p in pages:
        md_path = pages_dir / f"page-{p:04d}.md"
        if md_path.exists():
            results[p] = md_path
        else:
            pages_to_extract.append(p)

    if not pages_to_extract:
        console.print(f"  [green]All {len(pages)} Gemini Flash extractions cached[/green]")
        return results

    console.print(f"  Extracting {len(pages_to_extract)} pages via Gemini Flash...")

    with Progress() as progress:
        task = progress.add_task("Flash", total=len(pages_to_extract))

        for page_num in pages_to_extract:
            image_path = image_dir / f"page-{page_num:04d}.png"
            if not image_path.exists():
                console.print(f"  [red]Missing image for page {page_num}[/red]")
                progress.update(task, advance=1)
                continue

            prompt = load_extract_prompt(guideline_dir, page=page_num)

            try:
                response_text = client.extract_page(
                    image_path=image_path,
                    prompt=prompt,
                    stage="pathB",
                    page=page_num,
                )

                # Safety filter check — retry once if blocked
                if response_text is None:
                    console.print(f"  [yellow]Flash blocked page {page_num} — retrying...[/yellow]")
                    response_text = client.extract_page(
                        image_path=image_path,
                        prompt=prompt,
                        stage="pathB_retry",
                        page=page_num,
                    )

                if response_text is None:
                    # Still blocked — mark as Claude-only
                    console.print(f"  [yellow]Flash blocked page {page_num} (Claude-only)[/yellow]")
                    blocked_pages.append(page_num)
                    manifest.update(page_num, flash_blocked=True)
                    progress.update(task, advance=1)
                    continue

                markdown, metadata = _parse_response(response_text)

                md_path = pages_dir / f"page-{page_num:04d}.md"
                md_path.write_text(markdown)
                results[page_num] = md_path

                if metadata:
                    meta_path = meta_dir / f"page-{page_num:04d}.json"
                    meta_path.write_text(json.dumps(metadata, indent=2))

                manifest.update(page_num, flash_extracted=True)

            except Exception as e:
                console.print(f"  [red]Flash failed on page {page_num}: {e}[/red]")

            progress.update(task, advance=1)

    if blocked_pages:
        console.print(f"  [yellow]{len(blocked_pages)} pages blocked by safety filter[/yellow]")
    console.print(f"  [green]Flash extracted {len(results)} pages[/green]")
    return results
