"""Extract native text and word positions from PDF via pdfplumber.

Used as a word-presence oracle in Stage 2 and for dose confirmation in Stage 3.
"""

import json
from pathlib import Path

import pdfplumber
from rich.console import Console
from rich.progress import Progress

console = Console()


def extract_native_text(
    pdf_path: Path,
    output_dir: Path,
    pages: list[int] | None = None,
) -> dict[int, dict]:
    """Extract per-page text, words, and tables from pdfplumber.

    Args:
        pdf_path: Path to the (repaired) PDF.
        output_dir: Directory for per-page JSON output.
        pages: Specific 1-indexed pages. None = all.

    Returns:
        Dict mapping page number to extraction data.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    result: dict[int, dict] = {}

    with pdfplumber.open(pdf_path) as pdf:
        if pages is None:
            pages = list(range(1, len(pdf.pages) + 1))

        # Check cache
        pages_to_extract = []
        for p in pages:
            json_path = output_dir / f"page-{p:04d}.json"
            if json_path.exists():
                result[p] = json.loads(json_path.read_text())
            else:
                pages_to_extract.append(p)

        if not pages_to_extract:
            console.print(f"  [green]All {len(pages)} native text extractions cached[/green]")
            return result

        console.print(f"  Extracting native text for {len(pages_to_extract)} pages...")

        with Progress() as progress:
            task = progress.add_task("pdfplumber", total=len(pages_to_extract))

            for page_num in pages_to_extract:
                page = pdf.pages[page_num - 1]  # 0-indexed

                text = page.extract_text() or ""
                words = page.extract_words() or []

                # Extract tables if detected
                tables = []
                try:
                    for table in page.extract_tables():
                        if table:
                            tables.append(table)
                except Exception:
                    pass

                # Build word set for oracle lookups
                word_list = [
                    {
                        "text": w["text"],
                        "x0": round(w["x0"], 1),
                        "top": round(w["top"], 1),
                        "x1": round(w["x1"], 1),
                        "bottom": round(w["bottom"], 1),
                    }
                    for w in words
                ]

                page_data = {
                    "page": page_num,
                    "text": text,
                    "words": word_list,
                    "word_set": list({w["text"].lower() for w in words}),
                    "tables": tables,
                    "width": float(page.width),
                    "height": float(page.height),
                }

                json_path = output_dir / f"page-{page_num:04d}.json"
                json_path.write_text(json.dumps(page_data, indent=2))
                result[page_num] = page_data

                progress.update(task, advance=1)

    console.print(f"  [green]Extracted native text for {len(pages_to_extract)} pages[/green]")
    return result


def load_page_words(native_dir: Path, page_num: int) -> set[str]:
    """Load the word set for a specific page (for oracle lookups)."""
    json_path = native_dir / f"page-{page_num:04d}.json"
    if not json_path.exists():
        return set()
    data = json.loads(json_path.read_text())
    return set(data.get("word_set", []))


def load_page_text(native_dir: Path, page_num: int) -> str:
    """Load the full text for a specific page."""
    json_path = native_dir / f"page-{page_num:04d}.json"
    if not json_path.exists():
        return ""
    data = json.loads(json_path.read_text())
    return data.get("text", "")
