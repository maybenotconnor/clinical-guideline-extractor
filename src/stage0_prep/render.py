"""Render PDF pages to PNG images at 300 DPI."""

from pathlib import Path

from pdf2image import convert_from_path
from rich.console import Console
from rich.progress import Progress

console = Console()

DPI = 300


def render_pages(
    pdf_path: Path,
    output_dir: Path,
    pages: list[int] | None = None,
    dpi: int = DPI,
) -> dict[int, Path]:
    """Render PDF pages to PNG images.

    Args:
        pdf_path: Path to the PDF file.
        output_dir: Directory to save images.
        pages: Specific 1-indexed page numbers to render. None = all pages.
        dpi: Resolution for rendering.

    Returns:
        Dict mapping page number to image path.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    result: dict[int, Path] = {}

    # Check which pages are already cached
    if pages is None:
        from .repair import get_page_count
        total = get_page_count(pdf_path)
        pages = list(range(1, total + 1))

    pages_to_render = []
    for p in pages:
        img_path = output_dir / f"page-{p:04d}.png"
        if img_path.exists():
            result[p] = img_path
        else:
            pages_to_render.append(p)

    if not pages_to_render:
        console.print(f"  [green]All {len(pages)} page images cached[/green]")
        return result

    console.print(f"  Rendering {len(pages_to_render)} pages at {dpi} DPI...")

    with Progress() as progress:
        task = progress.add_task("Rendering", total=len(pages_to_render))

        # Render in batches to manage memory
        batch_size = 20
        for i in range(0, len(pages_to_render), batch_size):
            batch = pages_to_render[i:i + batch_size]

            for page_num in batch:
                img_path = output_dir / f"page-{page_num:04d}.png"
                images = convert_from_path(
                    str(pdf_path),
                    dpi=dpi,
                    first_page=page_num,
                    last_page=page_num,
                    fmt="png",
                )
                if images:
                    images[0].save(str(img_path), "PNG")
                    result[page_num] = img_path
                progress.update(task, advance=1)

    console.print(f"  [green]Rendered {len(pages_to_render)} new pages[/green]")
    return result
