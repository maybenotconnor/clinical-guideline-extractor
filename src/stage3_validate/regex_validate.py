"""Regex structural validation for doses, units, and LOC values."""

import re
from pathlib import Path

from rich.console import Console

console = Console()

DOSE_PATTERN = re.compile(
    r'(\d+\.?\d*)\s*(mg|mcg|µg|g|kg|mL|L|units?|IU|mEq|mmol)\b',
    re.IGNORECASE,
)

IMPOSSIBLE_COMBOS = [
    (re.compile(r'\b\d{3,}\s*g\b', re.IGNORECASE), "Dose in hundreds of grams — likely unit error"),
    (re.compile(r'\bIV\b.*\btablet\b', re.IGNORECASE), "IV route with tablet form"),
    (re.compile(r'\b0\.\d+\s*g\b', re.IGNORECASE), "Sub-gram dose in grams — should be mg?"),
    (re.compile(r'\b\d{5,}\s*(mg|mcg|mL)\b', re.IGNORECASE), "Dose >10,000 — likely error"),
]

VALID_LOC_VALUES = {'HC2', 'HC3', 'HC4', 'Hospital', 'RRH', 'NRH'}

LOC_PATTERN = re.compile(r'\(LOC:\s*([^)]+)\)')


def validate_doses(text: str, page_num: int) -> list[dict]:
    """Check for impossible dose-unit combinations."""
    findings = []
    for pattern, description in IMPOSSIBLE_COMBOS:
        for match in pattern.finditer(text):
            findings.append({
                "page": page_num,
                "type": "impossible_dose",
                "severity": "CRITICAL",
                "match": match.group(),
                "detail": description,
                "position": match.start(),
            })
    return findings


def validate_loc_values(text: str, page_num: int) -> list[dict]:
    """Validate LOC annotations against known values."""
    findings = []
    for match in LOC_PATTERN.finditer(text):
        loc_value = match.group(1).strip()
        if loc_value not in VALID_LOC_VALUES:
            findings.append({
                "page": page_num,
                "type": "invalid_loc",
                "severity": "HIGH",
                "match": match.group(),
                "detail": f"LOC value '{loc_value}' not in valid set: {VALID_LOC_VALUES}",
                "position": match.start(),
            })
    return findings


def run_regex_validation(
    resolved_dir: Path,
    pages: list[int],
) -> list[dict]:
    """Run regex validation across all resolved pages.

    Returns list of all findings.
    """
    all_findings = []

    for page_num in pages:
        md_path = resolved_dir / f"page-{page_num:04d}.md"
        if not md_path.exists():
            continue

        text = md_path.read_text()
        all_findings.extend(validate_doses(text, page_num))
        all_findings.extend(validate_loc_values(text, page_num))

    if all_findings:
        critical = sum(1 for f in all_findings if f["severity"] == "CRITICAL")
        high = sum(1 for f in all_findings if f["severity"] == "HIGH")
        console.print(f"  [yellow]Regex validation: {critical} CRITICAL, {high} HIGH[/yellow]")
    else:
        console.print(f"  [green]Regex validation clean[/green]")

    return all_findings
