"""Auto-detect and repair broken linearized PDFs.

The UCG-2023 PDF is linearized (Adobe InDesign 18.0) with a broken xref
that causes pdfplumber to find 0 pages. This module rewrites the PDF
through pypdf to produce a valid xref table. Cached — only runs once.
"""

from pathlib import Path

import pdfplumber
import pypdf
from rich.console import Console

console = Console()


def repair_pdf_if_needed(pdf_path: Path) -> Path:
    """Return a usable PDF path. Repairs if pdfplumber can't read it.

    If the PDF works with pdfplumber, returns the original path.
    If not, rewrites through pypdf and returns the repaired path.
    The repaired file is cached as {stem}-repaired.pdf.
    """
    repaired_path = pdf_path.parent / f"{pdf_path.stem}-repaired.pdf"

    # If repaired version already exists and is valid, use it
    if repaired_path.exists():
        try:
            with pdfplumber.open(repaired_path) as pdf:
                if len(pdf.pages) > 0:
                    console.print(f"  [green]Using cached repaired PDF ({len(pdf.pages)} pages)[/green]")
                    return repaired_path
        except Exception:
            pass  # Repaired file is broken too, re-repair

    # Try the original first
    try:
        with pdfplumber.open(pdf_path) as pdf:
            if len(pdf.pages) > 0:
                console.print(f"  [green]PDF OK ({len(pdf.pages)} pages)[/green]")
                return pdf_path
    except Exception:
        pass

    # Repair: rewrite through pypdf to fix xref table
    console.print("  [yellow]PDF has broken xref — repairing via pypdf...[/yellow]")
    reader = pypdf.PdfReader(pdf_path)
    writer = pypdf.PdfWriter()
    for page in reader.pages:
        writer.add_page(page)

    with open(repaired_path, "wb") as f:
        writer.write(f)

    # Verify repair worked
    with pdfplumber.open(repaired_path) as pdf:
        page_count = len(pdf.pages)
        if page_count == 0:
            raise RuntimeError(f"Repair failed: repaired PDF still has 0 pages")
        console.print(f"  [green]Repaired PDF: {page_count} pages[/green]")

    return repaired_path


def get_page_count(pdf_path: Path) -> int:
    """Get total page count from a PDF."""
    usable = repair_pdf_if_needed(pdf_path)
    with pdfplumber.open(usable) as pdf:
        return len(pdf.pages)
