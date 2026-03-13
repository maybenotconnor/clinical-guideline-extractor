# UCG 2023 Extraction Prompt

You are extracting content from page {page} of the Uganda Clinical
Guidelines 2023 (Ministry of Health, Republic of Uganda).

Convert this page to Markdown, preserving the page's actual structure.

## Treatment protocols

Pages with TREATMENT | LOC columns are NOT uniform grid tables. They
are structured clinical protocols with nested conditions and
treatments.

Render them as structured markdown:
- Bold condition headings with inline LOC: **Condition name** (LOC: HC3)
- Bulleted treatment steps underneath each condition
- Conditional instructions in italic: *If blood loss >1 litre:*
- Only use pipe tables for genuinely uniform grids (e.g., Glasgow
  Coma Scale, classification tables with consistent columns and rows)

## Warnings and cautions

Prefix with **CAUTION:** or **WARNING:** in bold. Include the full
text. These are safety-critical.

## Flowcharts and diagrams

Write `<!-- element:flowchart -->` before the description, then a
detailed numbered walkthrough of the decision logic. Include every
node, branch condition, action, drug name, dose, and LOC/facility
level. End with: (Original image: images/p{page}-fig{fig}.png)

## Clinical images

Write `<!-- element:image source:images/p{page}-fig{fig}.png -->`
before the description. Write a detailed prose description with all
clinically relevant visual features for species/condition
identification. End with: (Original image: images/p{page}-fig{fig}.png)

## Charts and graphs

Write `<!-- element:chart -->` before the description. Describe axes,
ranges, key thresholds, percentile lines, reference values.

## General rules

- Preserve ALL text exactly as written. Do not paraphrase or summarize.
- Preserve heading hierarchy: # top-level, ## sections, ### sub.
- Include ALL drug names, doses, routes, and frequencies exactly.
- If uncertain about any character or number, mark: ⚠️{best guess}

## Metadata

After the markdown, output a JSON metadata block:

```json
{
  "headings": [{"level": 2, "text": "..."}],
  "tables": [{"description": "...", "rows": 0, "cols": 0}],
  "warnings": ["full text of each warning"],
  "images": ["description of each image"],
  "drugs": [{"drug": "...", "dose": "...", "route": "..."}]
}
```
