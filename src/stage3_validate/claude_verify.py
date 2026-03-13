"""Claude error detection pass — the most important validation step.

100% detection rate on planted clinical errors in spike tests.
Runs on all pages with dosing content (~280 pages for UCG).
~$1.40 and ~41 minutes for 280 pages.
"""

import json
from pathlib import Path

from rich.console import Console
from rich.progress import Progress

from ..shared.api_client import ClaudeClient
from ..shared.cost_tracker import CostTracker
from ..extraction.prompt import load_verify_prompt

console = Console()


def parse_verify_response(response: str) -> dict:
    """Parse Claude's verification response.

    Returns:
        Dict with verified (bool) and findings (list of discrepancies).
    """
    if response.strip().upper() == "VERIFIED":
        return {"verified": True, "findings": []}

    # Parse structured discrepancy reports
    findings = []
    current = {}

    for line in response.split("\n"):
        line = line.strip()
        if not line:
            if current:
                findings.append(current)
                current = {}
            continue

        lower = line.lower()
        if "extraction says" in lower or "extracted:" in lower:
            current["extraction_says"] = line.split(":", 1)[-1].strip() if ":" in line else line
        elif "image shows" in lower or "original:" in lower:
            current["image_shows"] = line.split(":", 1)[-1].strip() if ":" in line else line
        elif "critical" in lower:
            current["severity"] = "CRITICAL"
            current["detail"] = line
        elif "high" in lower and "significance" not in lower:
            current["severity"] = "HIGH"
            current["detail"] = line
        elif "medium" in lower:
            current["severity"] = "MEDIUM"
            current["detail"] = line
        elif "low" in lower and "significance" not in lower:
            current["severity"] = "LOW"
            current["detail"] = line
        elif current:
            # Accumulate detail text
            current["detail"] = current.get("detail", "") + " " + line

    if current:
        findings.append(current)

    # Default severity if not parsed
    for f in findings:
        if "severity" not in f:
            f["severity"] = "MEDIUM"

    return {"verified": False, "findings": findings}


def run_claude_verification(
    resolved_dir: Path,
    image_dir: Path,
    guideline_dir: Path,
    pages: list[int],
    cost_tracker: CostTracker,
) -> list[dict]:
    """Run Claude error detection on specified pages.

    Args:
        resolved_dir: Directory with resolved page markdowns.
        image_dir: Directory with page images.
        guideline_dir: Contains verify.md prompt.
        pages: Pages to verify (typically dosing pages).
        cost_tracker: For API cost tracking.

    Returns:
        List of all findings across pages.
    """
    verify_prompt = load_verify_prompt(guideline_dir)
    client = ClaudeClient(cost_tracker=cost_tracker)
    all_findings: list[dict] = []
    verified_count = 0
    cache_dir = resolved_dir.parent / "verify_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)

    console.print(f"  Running Claude verification on {len(pages)} pages...")

    with Progress() as progress:
        task = progress.add_task("Verify", total=len(pages))

        for page_num in pages:
            # Check cache
            cache_path = cache_dir / f"page-{page_num:04d}.json"
            if cache_path.exists():
                cached = json.loads(cache_path.read_text())
                if cached.get("verified"):
                    verified_count += 1
                else:
                    for f in cached.get("findings", []):
                        f["page"] = page_num
                        all_findings.append(f)
                progress.update(task, advance=1)
                continue

            md_path = resolved_dir / f"page-{page_num:04d}.md"
            image_path = image_dir / f"page-{page_num:04d}.png"

            if not md_path.exists() or not image_path.exists():
                progress.update(task, advance=1)
                continue

            extraction_text = md_path.read_text()

            try:
                response = client.verify_page(
                    image_path=image_path,
                    extraction_text=extraction_text,
                    verify_prompt=verify_prompt,
                    stage="validation",
                    page=page_num,
                )

                result = parse_verify_response(response)

                # Cache result
                cache_path.write_text(json.dumps(result, indent=2))

                if result["verified"]:
                    verified_count += 1
                else:
                    for f in result["findings"]:
                        f["page"] = page_num
                        all_findings.append(f)

            except Exception as e:
                console.print(f"  [red]Verify failed on page {page_num}: {e}[/red]")

            progress.update(task, advance=1)

    critical = sum(1 for f in all_findings if f.get("severity") == "CRITICAL")
    high = sum(1 for f in all_findings if f.get("severity") == "HIGH")
    console.print(f"  [green]Verification: {verified_count} verified, "
                  f"{critical} CRITICAL, {high} HIGH, "
                  f"{len(all_findings) - critical - high} other[/green]")

    return all_findings
