"""Clinical guideline extraction pipeline — main entry point.

Usage:
    python -m src.main guidelines/ucg-2023
    python -m src.main guidelines/ucg-2023 --pages 1-10
    python -m src.main guidelines/ucg-2023 --stage 0   # prep only
    python -m src.main guidelines/ucg-2023 --stage 1   # extract only

Stages: 0=prep, 1=extract, 2=diff, 3=resolve, 4=validate, 5=review, 6=assemble
"""

import argparse
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel

from .shared.cost_tracker import CostTracker
from .shared.manifest import Manifest, PageStatus
from .stage0_prep.repair import repair_pdf_if_needed, get_page_count
from .stage0_prep.render import render_pages
from .stage0_prep.pdfplumber_extract import extract_native_text
from .stage0_prep.docling_structure import extract_structure, pages_with_dosing_content
from .extraction.claude_extract import extract_pages as claude_extract
from .extraction.gemini_extract import extract_pages as gemini_extract
from .stage1_diff.diff import run_diff
from .stage2_resolve.resolve import run_resolution
from .stage3_validate.regex_validate import run_regex_validation
from .stage3_validate.dose_confirm import run_dose_confirmation
from .stage3_validate.med7_ner import run_med7_validation
from .stage3_validate.claude_verify import run_claude_verification
from .stage4_review.generate_queue import build_review_queue, save_review_queue
from .stage4_review.review_ui import generate_review_html
from .stage5_assemble.assemble import assemble_guideline, generate_extraction_report
from .stage5_assemble.images import find_image_pages, collect_images

console = Console()


def parse_page_range(page_str: str, total: int) -> list[int]:
    """Parse page range string like '1-10', '5', '1-10,20-30'."""
    pages = []
    for part in page_str.split(","):
        part = part.strip()
        if "-" in part:
            start, end = part.split("-", 1)
            pages.extend(range(int(start), int(end) + 1))
        else:
            pages.append(int(part))
    return [p for p in pages if 1 <= p <= total]


def run_stage0(guideline_dir: Path, work_dir: Path, pages: list[int], manifest: Manifest):
    """Stage 0: PDF repair, rendering, pdfplumber extraction, Docling structure."""
    console.print(Panel("[bold]Stage 0: Prepare[/bold]", style="blue"))

    pdf_path = guideline_dir / "source.pdf"
    if not pdf_path.exists():
        console.print(f"[red]source.pdf not found in {guideline_dir}[/red]")
        sys.exit(1)

    # 0A: Repair PDF
    console.print("[bold]0A: PDF Repair[/bold]")
    usable_pdf = repair_pdf_if_needed(pdf_path)

    # 0B: Render page images
    console.print("[bold]0B: Render Pages[/bold]")
    image_dir = work_dir / "stage0" / "images"
    render_pages(usable_pdf, image_dir, pages=pages)

    # 0C: pdfplumber native text
    console.print("[bold]0C: pdfplumber Native Text[/bold]")
    native_dir = work_dir / "stage0" / "native"
    extract_native_text(usable_pdf, native_dir, pages=pages)

    # 0D: Docling structure
    console.print("[bold]0D: Docling Structure[/bold]")
    docling_dir = work_dir / "stage0" / "docling"
    extract_structure(usable_pdf, docling_dir)

    # Update manifest
    for p in pages:
        manifest.update(p, status=PageStatus.RENDERED)


def run_extraction(
    guideline_dir: Path, work_dir: Path, pages: list[int],
    cost_tracker: CostTracker, manifest: Manifest,
):
    """Stage 0A/0B: Parallel extraction via Claude and Gemini Flash."""
    console.print(Panel("[bold]Extraction: Claude + Gemini Flash[/bold]", style="blue"))

    image_dir = work_dir / "stage0" / "images"
    path_a_dir = work_dir / "pathA"
    path_b_dir = work_dir / "pathB"

    # Path A: Claude Sonnet
    console.print("[bold]Path A: Claude Sonnet[/bold]")
    claude_extract(
        guideline_dir=guideline_dir,
        image_dir=image_dir,
        output_dir=path_a_dir,
        pages=pages,
        cost_tracker=cost_tracker,
        manifest=manifest,
    )

    # Path B: Gemini Flash
    console.print("[bold]Path B: Gemini Flash[/bold]")
    gemini_extract(
        guideline_dir=guideline_dir,
        image_dir=image_dir,
        output_dir=path_b_dir,
        pages=pages,
        cost_tracker=cost_tracker,
        manifest=manifest,
    )

    # Update manifest
    for p in pages:
        ps = manifest.get(p)
        if ps.claude_extracted and ps.flash_extracted:
            manifest.update(p, status=PageStatus.EXTRACTED_BOTH)
        elif ps.claude_extracted:
            manifest.update(p, status=PageStatus.EXTRACTED_A)


def run_stage1(work_dir: Path, pages: list[int], manifest: Manifest):
    """Stage 1: Word-level diff."""
    console.print(Panel("[bold]Stage 1: Word-Level Diff[/bold]", style="blue"))

    diffs = run_diff(
        path_a_dir=work_dir / "pathA",
        path_b_dir=work_dir / "pathB",
        output_dir=work_dir / "stage1" / "diffs",
        pages=pages,
        manifest=manifest,
    )
    return diffs


def run_stage2(
    guideline_dir: Path, work_dir: Path, pages: list[int],
    diffs: dict, cost_tracker: CostTracker, manifest: Manifest,
):
    """Stage 2: Resolve disagreements."""
    console.print(Panel("[bold]Stage 2: Resolve Disagreements[/bold]", style="blue"))

    result = run_resolution(
        diffs=diffs,
        path_a_dir=work_dir / "pathA",
        path_b_dir=work_dir / "pathB",
        native_dir=work_dir / "stage0" / "native",
        image_dir=work_dir / "stage0" / "images",
        guideline_dir=guideline_dir,
        output_dir=work_dir / "stage2",
        pages=pages,
        cost_tracker=cost_tracker,
        manifest=manifest,
    )
    return result


def run_stage3(
    guideline_dir: Path, work_dir: Path, pages: list[int],
    cost_tracker: CostTracker,
):
    """Stage 3: Validate."""
    console.print(Panel("[bold]Stage 3: Validate[/bold]", style="blue"))

    resolved_dir = work_dir / "stage2" / "resolved"
    native_dir = work_dir / "stage0" / "native"
    image_dir = work_dir / "stage0" / "images"

    # 3A: Med7 NER
    console.print("[bold]3A: Med7 NER[/bold]")
    med7_findings = run_med7_validation(resolved_dir, work_dir, pages)

    # 3B: Regex validation
    console.print("[bold]3B: Regex Validation[/bold]")
    regex_findings = run_regex_validation(resolved_dir, pages)

    # 3C: pdfplumber dose confirmation
    console.print("[bold]3C: Dose Confirmation[/bold]")
    dose_findings = run_dose_confirmation(resolved_dir, native_dir, pages)

    # 3D: Claude error detection on dosing pages
    console.print("[bold]3D: Claude Verification[/bold]")
    docling_structure_path = work_dir / "stage0" / "docling" / "structure.json"
    if docling_structure_path.exists():
        structure = json.loads(docling_structure_path.read_text())
        dosing_pages = pages_with_dosing_content(structure)
        # Intersect with our page set
        dosing_pages = [p for p in dosing_pages if p in pages]
    else:
        # Without Docling, verify all pages (more expensive but safe)
        dosing_pages = pages

    claude_findings = run_claude_verification(
        resolved_dir=resolved_dir,
        image_dir=image_dir,
        guideline_dir=guideline_dir,
        pages=dosing_pages,
        cost_tracker=cost_tracker,
    )

    # Save validation report — use same keys as in-memory return value
    result = {
        "med7": med7_findings,
        "regex": regex_findings,
        "dose": dose_findings,
        "claude": claude_findings,
    }
    report_path = work_dir / "stage3" / "validation-report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(result, indent=2))

    return result


def run_stage4(
    work_dir: Path, pages: list[int],
    stage2_result: dict, validation: dict,
):
    """Stage 4: Human review queue."""
    console.print(Panel("[bold]Stage 4: Review Queue[/bold]", style="blue"))

    review_items = build_review_queue(
        stage2_review_items=stage2_result.get("review_items", []),
        regex_findings=validation.get("regex", []),
        dose_findings=validation.get("dose", []),
        claude_findings=validation.get("claude", []),
        med7_findings=validation.get("med7", []),
    )

    # Save review queue
    review_dir = work_dir / "review"
    save_review_queue(review_items, review_dir / "review-queue.json")

    # Generate HTML UI
    image_dir = work_dir / "stage0" / "images"
    generate_review_html(
        review_items=review_items,
        image_dir=image_dir,
        output_path=review_dir / "review-queue.html",
    )

    return review_items


def run_stage5(
    work_dir: Path, output_dir: Path, pages: list[int],
    manifest: Manifest, cost_tracker: CostTracker,
    stage2_result: dict, review_items: list[dict],
    guideline_name: str, publisher: str,
):
    """Stage 5: Assemble final output."""
    console.print(Panel("[bold]Stage 5: Assemble[/bold]", style="blue"))

    resolved_dir = work_dir / "stage2" / "resolved"
    image_dir = work_dir / "stage0" / "images"

    # Load Docling structure
    structure_path = work_dir / "stage0" / "docling" / "structure.json"
    structure = json.loads(structure_path.read_text()) if structure_path.exists() else {}

    # Assemble guideline.md
    assemble_guideline(
        resolved_dir=resolved_dir,
        output_dir=output_dir,
        pages=pages,
        structure=structure,
        guideline_name=guideline_name,
        publisher=publisher,
    )

    # Collect images
    image_pages = find_image_pages(resolved_dir, pages)
    collect_images(image_pages, image_dir, output_dir)

    # Copy validation report
    val_src = work_dir / "stage3" / "validation-report.json"
    if val_src.exists():
        val_dest = output_dir / "validation-report.json"
        val_dest.write_text(val_src.read_text())

    # Copy review queue and diffs
    review_dest = output_dir / "review"
    review_dest.mkdir(parents=True, exist_ok=True)

    review_src = work_dir / "review" / "review-queue.html"
    if review_src.exists():
        (review_dest / "review-queue.html").write_text(review_src.read_text())

    # Copy per-page diffs for audit trail
    diffs_src = work_dir / "stage1" / "diffs"
    diffs_dest = review_dest / "diffs"
    if diffs_src.exists():
        import shutil
        if diffs_dest.exists():
            shutil.rmtree(diffs_dest)
        shutil.copytree(diffs_src, diffs_dest)

    # Generate extraction report
    manifest.save()
    manifest_data = json.loads((work_dir / "manifest.json").read_text())
    generate_extraction_report(
        manifest_data=manifest_data,
        cost_summary=cost_tracker.summary(),
        resolution_methods=stage2_result.get("resolution_methods", {}),
        review_items=review_items,
        output_dir=output_dir,
    )

    console.print(Panel(f"[bold green]Pipeline complete! Output: {output_dir}[/bold green]", style="green"))


def main():
    parser = argparse.ArgumentParser(description="Clinical guideline extraction pipeline")
    parser.add_argument("guideline_dir", type=Path, help="Path to guideline directory (e.g., guidelines/ucg-2023)")
    parser.add_argument("--pages", type=str, default=None, help="Page range (e.g., '1-10', '5', '1-10,20-30')")
    parser.add_argument("--stage", type=int, default=None,
                        help="Run specific stage: 0=prep, 1=extract, 2=diff, 3=resolve, 4=validate, 5=review, 6=assemble")
    parser.add_argument("--work-dir", type=Path, default=None, help="Working directory (default: work/)")
    parser.add_argument("--output-dir", type=Path, default=None, help="Output directory (default: output/{name}/)")
    parser.add_argument("--name", type=str, default=None, help="Guideline name for frontmatter")
    parser.add_argument("--publisher", type=str, default=None, help="Publisher for frontmatter")
    args = parser.parse_args()

    # Load .env from project root
    project_root = Path(__file__).parent.parent
    env_path = project_root / ".env"
    if not env_path.exists():
        # Try parent directory
        env_path = project_root.parent / ".env"
    load_dotenv(env_path)

    guideline_dir = args.guideline_dir.resolve()
    if not guideline_dir.exists():
        console.print(f"[red]Guideline directory not found: {guideline_dir}[/red]")
        sys.exit(1)

    # Derive name from directory
    name = guideline_dir.name
    guideline_name = args.name or name.replace("-", " ").title()
    publisher = args.publisher or ""

    work_dir = (args.work_dir or project_root / "work" / name).resolve()
    output_dir = (args.output_dir or project_root / "output" / name).resolve()
    work_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Initialize tracking
    cost_tracker = CostTracker(work_dir)
    manifest = Manifest(work_dir)

    # Determine page range
    pdf_path = guideline_dir / "source.pdf"
    if not pdf_path.exists():
        console.print(f"[red]source.pdf not found in {guideline_dir}[/red]")
        sys.exit(1)

    total_pages = get_page_count(pdf_path)
    if args.pages:
        pages = parse_page_range(args.pages, total_pages)
    else:
        pages = list(range(1, total_pages + 1))

    manifest.init_pages(total_pages)

    console.print(Panel(
        f"[bold]Clinical Guideline Extraction Pipeline[/bold]\n"
        f"Guideline: {guideline_name}\n"
        f"Pages: {len(pages)} of {total_pages}\n"
        f"Work dir: {work_dir}\n"
        f"Output: {output_dir}",
        style="blue",
    ))

    # Run stages
    if args.stage is None or args.stage == 0:
        run_stage0(guideline_dir, work_dir, pages, manifest)

    if args.stage is None or args.stage == 1:
        run_extraction(guideline_dir, work_dir, pages, cost_tracker, manifest)

    diffs = {}
    if args.stage is None or args.stage == 2:
        diffs = run_stage1(work_dir, pages, manifest)

    stage2_result = {}
    if args.stage is None or args.stage == 3:
        if not diffs:
            # Load diffs from disk
            diffs_dir = work_dir / "stage1" / "diffs"
            if diffs_dir.exists():
                from .stage1_diff.diff import PageDiff
                for p in pages:
                    diff_path = diffs_dir / f"page-{p:04d}.json"
                    if diff_path.exists():
                        data = json.loads(diff_path.read_text())
                        diffs[p] = PageDiff(**data)

        stage2_result = run_stage2(guideline_dir, work_dir, pages, diffs, cost_tracker, manifest)

    validation = {}
    if args.stage is None or args.stage == 4:
        validation = run_stage3(guideline_dir, work_dir, pages, cost_tracker)

    review_items = []
    if args.stage is None or args.stage == 5:
        if not stage2_result:
            review_queue_path = work_dir / "stage2" / "review-queue.json"
            if review_queue_path.exists():
                stage2_result = {"review_items": json.loads(review_queue_path.read_text()), "resolution_methods": {}}

        if not validation:
            val_path = work_dir / "stage3" / "validation-report.json"
            if val_path.exists():
                validation = json.loads(val_path.read_text())

        review_items = run_stage4(work_dir, pages, stage2_result, validation)

    if args.stage is None or args.stage == 6:
        if not review_items:
            rq_path = work_dir / "review" / "review-queue.json"
            if rq_path.exists():
                review_items = json.loads(rq_path.read_text())

        run_stage5(
            work_dir, output_dir, pages,
            manifest, cost_tracker,
            stage2_result, review_items,
            guideline_name, publisher,
        )

    # Print cost summary
    summary = cost_tracker.summary()
    if summary["total_calls"] > 0:
        console.print(f"\n[bold]Cost: ${summary['total_cost']:.4f} ({summary['total_calls']} API calls)[/bold]")


if __name__ == "__main__":
    main()
