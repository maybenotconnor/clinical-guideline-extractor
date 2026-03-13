"""Extract structural metadata from PDF via Docling.

We use Docling for three things only:
1. Heading hierarchy (SectionHeaderItem level detection)
2. Element type classification (table, picture, list, text)
3. Page-level element inventory (count of tables, images, text blocks)

We do NOT use Docling for text content or table content.
"""

import json
from pathlib import Path

from rich.console import Console

console = Console()


def extract_structure(
    pdf_path: Path,
    output_dir: Path,
) -> dict:
    """Run Docling over the PDF and extract structural metadata.

    Returns:
        Dict with heading_tree and per_page element counts.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    cache_path = output_dir / "structure.json"

    if cache_path.exists():
        console.print("  [green]Docling structure cached[/green]")
        return json.loads(cache_path.read_text())

    console.print("  Running Docling for structural metadata...")

    try:
        from docling.document_converter import DocumentConverter, PdfFormatOption
        from docling.datamodel.pipeline_options import PdfPipelineOptions
    except ImportError:
        console.print("  [yellow]Docling not installed — skipping structure extraction[/yellow]")
        return _empty_structure()

    pipeline_options = PdfPipelineOptions(
        do_table_structure=False,  # We don't need table content
        do_ocr=False,  # Born-digital PDF
    )
    converter = DocumentConverter(
        format_options={"pdf": PdfFormatOption(pipeline_options=pipeline_options)}
    )

    result = converter.convert(str(pdf_path))
    doc = result.document

    # Extract heading hierarchy
    headings = []
    per_page: dict[int, dict] = {}

    for item in doc.body:
        page_num = None
        if hasattr(item, 'prov') and item.prov:
            page_num = item.prov[0].page_no

        if page_num is not None:
            if page_num not in per_page:
                per_page[page_num] = {
                    "headings": 0, "tables": 0, "images": 0,
                    "text_blocks": 0, "lists": 0, "warnings": 0,
                }

        item_type = type(item).__name__

        if item_type == "SectionHeaderItem":
            level = getattr(item, 'level', 1)
            text = item.text if hasattr(item, 'text') else str(item)
            headings.append({
                "level": level,
                "text": text,
                "page": page_num,
            })
            if page_num:
                per_page[page_num]["headings"] += 1

        elif item_type == "TableItem":
            if page_num:
                per_page[page_num]["tables"] += 1

        elif item_type == "PictureItem":
            if page_num:
                per_page[page_num]["images"] += 1

        elif item_type == "TextItem":
            label = getattr(item, 'label', '')
            text = item.text if hasattr(item, 'text') else ''

            if label in ('PAGE_HEADER', 'PAGE_FOOTER'):
                continue

            if label == 'LIST_ITEM':
                if page_num:
                    per_page[page_num]["lists"] += 1
            elif any(kw in text.lower() for kw in ('caution', 'warning', 'do not')):
                if page_num:
                    per_page[page_num]["warnings"] += 1
            else:
                if page_num:
                    per_page[page_num]["text_blocks"] += 1

    structure = {
        "heading_tree": headings,
        "per_page": {str(k): v for k, v in sorted(per_page.items())},
        "total_pages": len(per_page),
    }

    cache_path.write_text(json.dumps(structure, indent=2))
    console.print(f"  [green]Docling structure: {len(headings)} headings across {len(per_page)} pages[/green]")
    return structure


def _empty_structure() -> dict:
    return {"heading_tree": [], "per_page": {}, "total_pages": 0}


def pages_with_dosing_content(structure: dict) -> list[int]:
    """Identify pages that likely contain dosing content (for Stage 3 validation).

    Pages with tables or warnings are likely to have drug/dose information.
    """
    dosing_pages = []
    for page_str, counts in structure.get("per_page", {}).items():
        page = int(page_str)
        if counts.get("tables", 0) > 0 or counts.get("warnings", 0) > 0:
            dosing_pages.append(page)
    return sorted(dosing_pages)


def get_heading_for_page(structure: dict, page_num: int) -> dict | None:
    """Get the most recent heading at or before a given page."""
    best = None
    for h in structure.get("heading_tree", []):
        if h.get("page") and h["page"] <= page_num:
            best = h
    return best
