"""Path A: Claude Sonnet extraction.

Primary extractor — highest F1 (92.6%), fastest (13.7s/page), zero safety
filter blocks. Different model family from Gemini maximizes cross-check value.
"""

import json
import re
from pathlib import Path

from rich.console import Console
from rich.progress import Progress

from ..shared.api_client import ClaudeClient
from ..shared.cost_tracker import CostTracker
from ..shared.manifest import Manifest, PageStatus
from .prompt import load_extract_prompt

console = Console()


def _parse_response(text: str) -> tuple[str, dict | None]:
    """Split response into markdown content and JSON metadata block."""
    # Look for ```json block at the end
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
    """Extract pages via Claude Sonnet.

    Args:
        guideline_dir: Path to guideline config (contains extract.md).
        image_dir: Directory with page-NNNN.png images.
        output_dir: Where to write pathA results.
        pages: List of page numbers to extract.
        cost_tracker: For recording API costs.
        manifest: For tracking progress.

    Returns:
        Dict mapping page number to markdown output path.
    """
    pages_dir = output_dir / "pages"
    meta_dir = output_dir / "meta"
    pages_dir.mkdir(parents=True, exist_ok=True)
    meta_dir.mkdir(parents=True, exist_ok=True)

    client = ClaudeClient(cost_tracker=cost_tracker)
    results: dict[int, Path] = {}

    # Check cache
    pages_to_extract = []
    for p in pages:
        md_path = pages_dir / f"page-{p:04d}.md"
        if md_path.exists():
            results[p] = md_path
        else:
            pages_to_extract.append(p)

    if not pages_to_extract:
        console.print(f"  [green]All {len(pages)} Claude extractions cached[/green]")
        return results

    console.print(f"  Extracting {len(pages_to_extract)} pages via Claude Sonnet...")

    with Progress() as progress:
        task = progress.add_task("Claude", total=len(pages_to_extract))

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
                    stage="pathA",
                    page=page_num,
                )

                markdown, metadata = _parse_response(response_text)

                # Save markdown
                md_path = pages_dir / f"page-{page_num:04d}.md"
                md_path.write_text(markdown)
                results[page_num] = md_path

                # Save metadata
                if metadata:
                    meta_path = meta_dir / f"page-{page_num:04d}.json"
                    meta_path.write_text(json.dumps(metadata, indent=2))

                manifest.update(page_num, claude_extracted=True)

            except Exception as e:
                console.print(f"  [red]Claude failed on page {page_num}: {e}[/red]")

            progress.update(task, advance=1)

    console.print(f"  [green]Claude extracted {len(results)} pages[/green]")
    return results
