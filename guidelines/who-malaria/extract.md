# WHO Malaria Guidelines Extraction Prompt

You are extracting content from page {page} of the WHO Guidelines for
Malaria (World Health Organization, 13 August 2025).

Convert this page to Markdown, preserving the page's actual structure.

## Recommendations

WHO recommendations are presented in coloured boxes:
- Green = Strong recommendation FOR
- Yellow = Conditional recommendation FOR
- Orange = Conditional recommendation AGAINST
- Red = Strong recommendation AGAINST
- Blue = Good practice statement

Preserve the recommendation text exactly, with its strength and
certainty of evidence. Format as:

> **[Conditional/Strong] recommendation [for/against], [certainty] evidence**
>
> [Full recommendation text]

## Evidence-to-decision sections

These structured sections appear under recommendations:
- **Benefits and harms** — preserve outcomes with effect sizes, CIs, study designs
- **Certainty of the evidence** — preserve the GRADE rating (High/Moderate/Low/Very Low)
- **Values and preferences**
- **Resources** — preserve cost data, cost-effectiveness ratios
- **Equity**
- **Acceptability**
- **Feasibility**

Render each as a ### heading with full content preserved.

## Treatment protocols and dosing

Render treatment/dosing information as structured markdown:
- Bold condition headings: **Condition name**
- Bulleted treatment steps underneath
- Conditional instructions in italic
- Use pipe tables only for genuinely uniform grids (e.g., dosing tables, GRADE summary tables)

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

## Tables (GRADE, glossary, etc.)

Render uniform grid tables (e.g., GRADE certainty table, glossary
definitions, interpretation tables) as standard Markdown pipe tables.
Preserve all rows and columns exactly.

## General rules

- Preserve ALL text exactly as written. Do not paraphrase or summarize.
- Preserve heading hierarchy: # top-level (chapter), ## sections, ### sub.
- Include ALL drug names, doses, routes, and frequencies exactly.
- Preserve reference numbers in square brackets: [300], [301], etc.
- Preserve italic text for species names: *P. falciparum*, *P. vivax*, *Anopheles*
- If uncertain about any character or number, mark: {best guess}

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
