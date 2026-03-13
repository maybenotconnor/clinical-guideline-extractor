# Clinical Guideline Extractor

Extracts clinical guideline PDFs into structured markdown optimized for RAG retrieval. Uses dual-extraction (Claude Sonnet + Gemini Flash) with word-level diff, multi-stage resolution, drug/dose validation, and human review.

## Prerequisites

- Python 3.11+
- `poppler-utils` (for `pdf2image`)
- API keys for Anthropic (Claude) and Google (Gemini)

```bash
# Ubuntu/Debian
sudo apt install poppler-utils

# macOS
brew install poppler
```

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

Create a `.env` file in the project root (or parent directory):

```
ANTHROPIC_API_KEY=sk-ant-...
GEMINI_API_KEY=...
```

### Optional dependencies

- **Docling** — heading hierarchy detection (installed with base deps, but can be slow on first run)
- **Med7/spaCy** — independent NER drug validation:
  ```bash
  pip install https://huggingface.co/kormilitzin/en_core_med7_lg/resolve/main/en_core_med7_lg-any-py3-none-any.whl
  ```

## Running on a new guideline

```bash
# 1. Create guideline directory from template
cp -r guidelines/_template guidelines/your-guideline-name

# 2. Copy or symlink your PDF as source.pdf
cp /path/to/your-guideline.pdf guidelines/your-guideline-name/source.pdf

# 3. Edit extract.md to describe your guideline's structure
#    (treatment tables, dosing formats, special elements, etc.)
nano guidelines/your-guideline-name/extract.md

# 4. Optionally edit verify.md and tiebreak.md

# 5. Run the full pipeline
python -m src guidelines/your-guideline-name

# Or test on a few pages first
python -m src guidelines/your-guideline-name --pages 5,10,15
```

### CLI options

| Flag | Description | Example |
|------|-------------|---------|
| `--pages` | Page range to process | `--pages 1-10,20-30` |
| `--stage` | Run a single stage (0-6) | `--stage 0` |
| `--work-dir` | Custom working directory | `--work-dir work/test` |
| `--output-dir` | Custom output directory | `--output-dir output/test` |
| `--name` | Guideline title for frontmatter | `--name "WHO Malaria Guidelines"` |
| `--publisher` | Publisher for frontmatter | `--publisher "WHO"` |

### Stages

| Stage | Name | What it does |
|-------|------|--------------|
| 0 | Prepare | PDF repair, page rendering (300 DPI), pdfplumber text extraction, Docling structure |
| 1 | Extract | Dual extraction via Claude Sonnet (primary) and Gemini Flash (cross-check) |
| 2 | Diff | Word-level Jaccard similarity, drug/dose disagreement detection |
| 3 | Resolve | pdfplumber oracle, Gemini Pro tiebreaker, decision rules |
| 4 | Validate | Med7 NER, regex validation, pdfplumber dose confirmation, Claude error detection |
| 5 | Review | Generates prioritized review queue and HTML review UI |
| 6 | Assemble | Concatenates into single `guideline.md` with frontmatter, copies images, writes reports |

## Output

```
output/your-guideline-name/
  guideline.md              # Single assembled markdown file
  extraction-report.json    # Per-page stats, costs, audit trail
  validation-report.json    # Drug/dose validation results
  review/
    review-queue.html       # Open in browser for human review (keyboard: A=accept, E=edit, F=flag)
    diffs/                  # Per-page diff files
  images/                   # Referenced clinical images
```

## Customizing prompts

Each guideline directory contains three prompt files:

- **`extract.md`** — Describes how to interpret the guideline's layout. This is where you tell the VLM about treatment protocol structure, dosing table formats, special elements (LOC values, evidence grades, etc.).
- **`verify.md`** — What to focus on during Claude's error detection pass. Emphasize whatever is safety-critical for this guideline.
- **`tiebreak.md`** — Instructions for the Gemini Pro tiebreaker. Usually needs minimal editing from the template.

See `guidelines/ucg-2023/` for a fully customized example.

## Project structure

```
src/
  main.py                  # CLI entry point, orchestrates all stages
  shared/
    api_client.py          # Claude and Gemini API clients with retry
    cost_tracker.py        # Token usage and cost tracking
    manifest.py            # Per-page state tracking for resume
    metrics.py             # Jaccard/F1 word-level metrics
  extraction/
    prompt.py              # Prompt template loading
    claude_extract.py      # Path A: Claude Sonnet extraction
    gemini_extract.py      # Path B: Gemini Flash extraction
  stage0_prep/
    repair.py              # PDF repair for broken xref tables
    render.py              # Page rendering at 300 DPI
    pdfplumber_extract.py  # Native text and word extraction
    docling_structure.py   # Heading hierarchy and element types
  stage1_diff/
    diff.py                # Word-level diff engine
    tokenize.py            # Markdown-aware word tokenization
    escalate.py            # Drug/dose pattern detection
  stage2_resolve/
    resolve.py             # Decision rules orchestration
    pdfplumber_oracle.py   # Word-presence confirmation
    gemini_tiebreak.py     # Gemini Pro tiebreaker
  stage3_validate/
    regex_validate.py      # Structural validation (doses, LOC values)
    dose_confirm.py        # pdfplumber dose confirmation
    med7_ner.py            # Med7 NER drug entity extraction
    claude_verify.py       # Claude error detection pass
  stage4_review/
    generate_queue.py      # Review queue prioritization
    review_ui.py           # Standalone HTML review interface
  stage5_assemble/
    assemble.py            # Final markdown assembly
    images.py              # Image collection
guidelines/
  _template/               # Copy this for new guidelines
  ucg-2023/                # Uganda Clinical Guidelines 2023
```
