"""QA validation: random 30-page sample for accuracy checking.

Supports definition of done item 7: "Random 30-page QA sample shows
>99% word-level accuracy on text, all drug-dose-route tuples correct."
"""

import json
import random
import sys
from pathlib import Path

from rich.console import Console
from rich.table import Table

from .shared.metrics import jaccard, f1
from .stage0_prep.pdfplumber_extract import load_page_text
from .stage1_diff.escalate import DOSE_PATTERN

console = Console()


def run_qa_sample(
    resolved_dir: Path,
    native_dir: Path,
    pages: list[int],
    sample_size: int = 30,
    seed: int = 42,
) -> dict:
    """Run QA validation on a random page sample.

    Compares resolved extractions against pdfplumber native text
    for word-level accuracy.

    Returns:
        dict with sample_pages, avg_jaccard, avg_f1, results.
    """
    rng = random.Random(seed)

    # Select random sample
    available = [p for p in pages if (resolved_dir / f"page-{p:04d}.md").exists()]
    sample = sorted(rng.sample(available, min(sample_size, len(available))))

    results = []
    total_jaccard = 0
    total_f1 = 0
    drug_issues = 0

    for page_num in sample:
        resolved_text = (resolved_dir / f"page-{page_num:04d}.md").read_text()
        native_text = load_page_text(native_dir, page_num)

        jac = jaccard(resolved_text, native_text)
        f1_score = f1(resolved_text, native_text)

        # Check drug-dose tuples
        resolved_doses = set(DOSE_PATTERN.findall(resolved_text))
        native_doses = set(DOSE_PATTERN.findall(native_text))
        dose_match = resolved_doses == native_doses
        if not dose_match:
            drug_issues += 1

        results.append({
            "page": page_num,
            "jaccard": round(jac, 4),
            "f1": round(f1_score, 4),
            "dose_match": dose_match,
            "resolved_doses": len(resolved_doses),
            "native_doses": len(native_doses),
        })

        total_jaccard += jac
        total_f1 += f1_score

    avg_jaccard = total_jaccard / len(sample) if sample else 0
    avg_f1 = total_f1 / len(sample) if sample else 0

    # Display results
    table = Table(title=f"QA Sample ({len(sample)} pages)")
    table.add_column("Page", style="cyan")
    table.add_column("Jaccard", justify="right")
    table.add_column("F1", justify="right")
    table.add_column("Doses OK", justify="center")

    for r in results:
        dose_ok = "[green]YES[/green]" if r["dose_match"] else "[red]NO[/red]"
        jac_style = "green" if r["jaccard"] >= 0.99 else "yellow" if r["jaccard"] >= 0.90 else "red"
        table.add_row(
            str(r["page"]),
            f"[{jac_style}]{r['jaccard']:.4f}[/{jac_style}]",
            f"{r['f1']:.4f}",
            dose_ok,
        )

    console.print(table)
    console.print(f"\n[bold]Average Jaccard:[/bold] {avg_jaccard:.4f}")
    console.print(f"[bold]Average F1:[/bold] {avg_f1:.4f}")
    console.print(f"[bold]Drug/dose issues:[/bold] {drug_issues}/{len(sample)}")

    passes = avg_f1 >= 0.99 and drug_issues == 0
    if passes:
        console.print("[bold green]QA PASS: >99% accuracy, all doses correct[/bold green]")
    else:
        console.print("[bold red]QA FAIL: review needed[/bold red]")

    return {
        "sample_size": len(sample),
        "avg_jaccard": round(avg_jaccard, 4),
        "avg_f1": round(avg_f1, 4),
        "drug_issues": drug_issues,
        "passes": passes,
        "results": results,
    }


if __name__ == "__main__":
    work_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("work/ucg-2023")
    resolved_dir = work_dir / "stage2" / "resolved"
    native_dir = work_dir / "stage0" / "native"

    # Get all available pages
    pages = []
    for f in sorted(resolved_dir.glob("page-*.md")):
        pages.append(int(f.stem.split("-")[1]))

    result = run_qa_sample(resolved_dir, native_dir, pages)
    report_path = work_dir / "qa-sample-report.json"
    report_path.write_text(json.dumps(result, indent=2))
    console.print(f"\nReport saved: {report_path}")
