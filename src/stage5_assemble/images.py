"""Collect images for visual elements into flat output folder."""

import re
import shutil
from pathlib import Path

from rich.console import Console

console = Console()

# Match element comments that reference images
IMAGE_REF_PATTERN = re.compile(
    r'<!-- element:(?:image|flowchart|chart)\s*(?:source:(\S+))?\s*-->'
)
IMAGE_NAME_PATTERN = re.compile(r'images/p(\d+)-fig(\d+)\.png')


def find_image_pages(resolved_dir: Path, pages: list[int]) -> list[int]:
    """Find pages that contain visual elements (images, flowcharts, charts)."""
    image_pages = []
    for page_num in pages:
        md_path = resolved_dir / f"page-{page_num:04d}.md"
        if not md_path.exists():
            continue
        text = md_path.read_text()
        if IMAGE_REF_PATTERN.search(text):
            image_pages.append(page_num)
    return image_pages


def collect_images(
    image_pages: list[int],
    source_image_dir: Path,
    output_dir: Path,
) -> dict[int, list[Path]]:
    """Copy page images for pages with visual elements to output/images/.

    Names them as p{page}-fig{N}.png per the spec.
    """
    images_dir = output_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)
    collected: dict[int, list[Path]] = {}

    for page_num in image_pages:
        source = source_image_dir / f"page-{page_num:04d}.png"
        if not source.exists():
            continue

        # For now, copy as p{page}-fig1.png (single figure per page)
        # TODO: if a page has multiple figures, detect and number them
        dest = images_dir / f"p{page_num:03d}-fig1.png"
        shutil.copy2(source, dest)

        collected[page_num] = [dest]

    console.print(f"  [green]Collected images for {len(collected)} pages[/green]")
    return collected
