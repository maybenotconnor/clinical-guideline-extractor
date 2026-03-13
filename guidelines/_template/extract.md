# Guideline Extraction Prompt

You are extracting content from page {page} of a clinical guideline.

Convert this page to Markdown, preserving the page's actual structure.

## Treatment protocols

Render treatment protocols as structured markdown:
- Bold condition headings: **Condition name**
- Bulleted treatment steps underneath each condition
- Conditional instructions in italic
- Use pipe tables only for genuinely uniform grids

## Warnings and cautions

Prefix with **CAUTION:** or **WARNING:** in bold. Include the full
text. These are safety-critical.

## Flowcharts and diagrams

Write `<!-- element:flowchart -->` before the description, then a
detailed numbered walkthrough of the decision logic. Include every
node, branch condition, action, drug name, and dose.
End with: (Original image: images/p{page}-fig{fig}.png)

## Clinical images

Write `<!-- element:image source:images/p{page}-fig{fig}.png -->`
before the description. Write a detailed prose description with all
clinically relevant visual features.
End with: (Original image: images/p{page}-fig{fig}.png)

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
