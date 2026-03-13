"""Med7 NER extraction for independent drug-dose-route validation.

Provides a third independent opinion on drug mentions beyond the two VLMs.
"""

import json
from pathlib import Path

from rich.console import Console

console = Console()

_nlp = None


def _get_nlp():
    """Lazy-load Med7 model."""
    global _nlp
    if _nlp is None:
        try:
            import spacy
            _nlp = spacy.load("en_core_med7_lg")
        except (OSError, ImportError):
            console.print("  [yellow]Med7/spacy not available — skipping NER validation[/yellow]")
            return None
    return _nlp


def extract_drug_entities(text: str) -> list[dict]:
    """Extract drug-dose-route tuples from text using Med7 NER.

    Returns list of dicts with keys: drug, dosage, route, frequency, form, strength, duration.
    """
    nlp = _get_nlp()
    if nlp is None:
        return []

    doc = nlp(text)
    entities = []
    for ent in doc.ents:
        entities.append({
            "text": ent.text,
            "label": ent.label_,
            "start": ent.start_char,
            "end": ent.end_char,
        })
    return entities


def validate_against_metadata(
    ner_entities: list[dict],
    vlm_drugs: list[dict],
) -> list[dict]:
    """Cross-check Med7 NER entities against VLM-extracted drug metadata.

    Returns list of discrepancies.
    """
    discrepancies = []

    # Get drug names from VLM metadata
    vlm_drug_names = {d.get("drug", "").lower() for d in vlm_drugs if d.get("drug")}

    # Get drug names from NER
    ner_drug_names = {e["text"].lower() for e in ner_entities if e["label"] == "DRUG"}

    # Drugs found by NER but not VLM
    for drug in ner_drug_names - vlm_drug_names:
        discrepancies.append({
            "type": "drug_missing_from_vlm",
            "drug": drug,
            "severity": "HIGH",
            "detail": f"Med7 found drug '{drug}' not in VLM metadata",
        })

    return discrepancies


def run_med7_validation(
    resolved_dir: Path,
    meta_dir: Path,
    pages: list[int],
) -> list[dict]:
    """Run Med7 NER across all resolved pages and cross-check.

    Returns list of all validation findings.
    """
    nlp = _get_nlp()
    if nlp is None:
        console.print("  [yellow]Skipping Med7 validation (model not available)[/yellow]")
        return []

    findings = []

    for page_num in pages:
        md_path = resolved_dir / f"page-{page_num:04d}.md"
        if not md_path.exists():
            continue

        text = md_path.read_text()
        entities = extract_drug_entities(text)

        # Load VLM metadata if available
        vlm_drugs = []
        for source in ["pathA", "pathB"]:
            meta_path = meta_dir / source / "meta" / f"page-{page_num:04d}.json"
            if meta_path.exists():
                meta = json.loads(meta_path.read_text())
                vlm_drugs.extend(meta.get("drugs", []))

        if vlm_drugs:
            discrepancies = validate_against_metadata(entities, vlm_drugs)
            for d in discrepancies:
                d["page"] = page_num
                findings.append(d)

    if findings:
        console.print(f"  [yellow]Med7 found {len(findings)} discrepancies[/yellow]")
    else:
        console.print(f"  [green]Med7 validation clean[/green]")

    return findings
