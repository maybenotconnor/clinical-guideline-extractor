"""pdfplumber dose confirmation — verify drug-dose pairs exist in source PDF.

Catches hallucinated doses where the VLM invented a number that doesn't
exist in the source.
"""

import re
from pathlib import Path

from rich.console import Console

from ..stage0_prep.pdfplumber_extract import load_page_text, load_page_words

console = Console()

DOSE_PATTERN = re.compile(
    r'(\d+\.?\d*)\s*(mg|mcg|µg|g|kg|mL|L|units?|IU|mEq|mmol)\b',
    re.IGNORECASE,
)

# Common drug name patterns (simplified — not exhaustive)
DRUG_INDICATORS = re.compile(
    r'\b(tablet|capsule|injection|infusion|syrup|suspension|cream|ointment|'
    r'IV|IM|PO|SC|oral|topical|rectal)\b',
    re.IGNORECASE,
)


def extract_dose_tuples(text: str) -> list[dict]:
    """Extract drug-dose-unit tuples from text."""
    tuples = []
    for match in DOSE_PATTERN.finditer(text):
        value = match.group(1)
        unit = match.group(2)
        # Get surrounding context for drug name
        start = max(0, match.start() - 100)
        context = text[start:match.end() + 50]
        tuples.append({
            "value": value,
            "unit": unit,
            "full_match": match.group(),
            "context": context.strip(),
        })
    return tuples


def confirm_doses_on_page(
    text: str,
    native_dir: Path,
    page_num: int,
) -> list[dict]:
    """Confirm dose values exist in pdfplumber's native text.

    Returns list of findings for unconfirmed doses.
    """
    page_words = load_page_words(native_dir, page_num)
    native_text = load_page_text(native_dir, page_num).lower()
    dose_tuples = extract_dose_tuples(text)
    findings = []

    for dt in dose_tuples:
        value = dt["value"]
        unit = dt["unit"]

        # Check both the word set (exact tokens) and full native text
        # (handles cases where pdfplumber joins number+unit like "20mg")
        value_found = (
            value.lower() in page_words
            or value.lower() in native_text
        )
        unit_found = (
            unit.lower() in page_words
            or unit.lower() in native_text
        )

        if not value_found:
            findings.append({
                "page": page_num,
                "type": "dose_not_confirmed",
                "severity": "HIGH",
                "detail": f"Dose value '{value}' not found in pdfplumber text",
                "dose": dt["full_match"],
                "context": dt["context"],
            })
        elif not unit_found:
            findings.append({
                "page": page_num,
                "type": "unit_not_confirmed",
                "severity": "MEDIUM",
                "detail": f"Unit '{unit}' not found in pdfplumber text",
                "dose": dt["full_match"],
                "context": dt["context"],
            })

    return findings


def run_dose_confirmation(
    resolved_dir: Path,
    native_dir: Path,
    pages: list[int],
) -> list[dict]:
    """Run dose confirmation across all resolved pages."""
    all_findings = []

    for page_num in pages:
        md_path = resolved_dir / f"page-{page_num:04d}.md"
        if not md_path.exists():
            continue

        text = md_path.read_text()
        findings = confirm_doses_on_page(text, native_dir, page_num)
        all_findings.extend(findings)

    if all_findings:
        high = sum(1 for f in all_findings if f["severity"] == "HIGH")
        console.print(f"  [yellow]Dose confirmation: {high} unconfirmed doses[/yellow]")
    else:
        console.print(f"  [green]All doses confirmed by pdfplumber[/green]")

    return all_findings
