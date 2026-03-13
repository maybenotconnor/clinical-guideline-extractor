"""Generate standalone HTML review interface for human review.

Side-by-side view: original page image | resolved extraction | pdfplumber text.
Keyboard shortcuts for speed: A (accept), E (edit), F (flag for expert).
"""

import json
from pathlib import Path

from rich.console import Console

console = Console()

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Clinical Guideline Review Queue</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
         background: #1a1a2e; color: #e0e0e0; }
  .header { background: #16213e; padding: 16px 24px; border-bottom: 2px solid #0f3460;
            display: flex; justify-content: space-between; align-items: center; }
  .header h1 { font-size: 18px; color: #e94560; }
  .stats { display: flex; gap: 16px; font-size: 13px; }
  .stat { padding: 4px 12px; border-radius: 4px; }
  .stat.critical { background: #e94560; color: white; }
  .stat.high { background: #f47c20; color: white; }
  .stat.medium { background: #3282b8; color: white; }
  .stat.completed { background: #27ae60; color: white; }

  .nav { background: #16213e; padding: 8px 24px; display: flex; gap: 8px;
         align-items: center; border-bottom: 1px solid #0f3460; }
  .nav button { padding: 6px 14px; border: 1px solid #0f3460; background: #1a1a2e;
                color: #e0e0e0; border-radius: 4px; cursor: pointer; font-size: 13px; }
  .nav button:hover { background: #0f3460; }
  .nav button.active { background: #e94560; border-color: #e94560; }
  .nav select { padding: 6px; background: #1a1a2e; color: #e0e0e0;
                border: 1px solid #0f3460; border-radius: 4px; }

  .item { display: none; padding: 16px 24px; }
  .item.active { display: block; }
  .item-header { display: flex; justify-content: space-between; margin-bottom: 12px; }
  .tier-badge { padding: 2px 10px; border-radius: 3px; font-weight: bold; font-size: 12px; }
  .tier-CRITICAL { background: #e94560; }
  .tier-HIGH { background: #f47c20; }
  .tier-MEDIUM { background: #3282b8; }
  .tier-LOW { background: #666; }

  .panels { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 12px;
            height: calc(100vh - 220px); }
  .panel { background: #16213e; border-radius: 6px; overflow: auto; padding: 12px; }
  .panel h3 { font-size: 13px; color: #888; margin-bottom: 8px;
              border-bottom: 1px solid #0f3460; padding-bottom: 4px; }
  .panel img { max-width: 100%; }
  .panel pre { white-space: pre-wrap; font-size: 12px; line-height: 1.5; color: #ccc; }
  .panel .highlight { background: #e9456033; padding: 2px 4px; border-radius: 2px; }

  .finding { background: #0f3460; padding: 8px 12px; border-radius: 4px;
             margin-bottom: 8px; font-size: 13px; }
  .finding .label { font-weight: bold; color: #e94560; }

  .actions { padding: 12px 24px; background: #16213e; border-top: 2px solid #0f3460;
             display: flex; gap: 12px; align-items: center; }
  .actions button { padding: 8px 20px; border: none; border-radius: 4px;
                    font-size: 14px; cursor: pointer; font-weight: bold; }
  .btn-accept { background: #27ae60; color: white; }
  .btn-edit { background: #f47c20; color: white; }
  .btn-flag { background: #e94560; color: white; }
  .shortcut { color: #666; font-size: 12px; margin-left: 4px; }

  textarea { width: 100%; height: 200px; background: #1a1a2e; color: #e0e0e0;
             border: 1px solid #0f3460; border-radius: 4px; padding: 8px;
             font-family: monospace; font-size: 12px; display: none; }
  textarea.visible { display: block; }
</style>
</head>
<body>
  <div class="header">
    <h1>Clinical Guideline Review Queue</h1>
    <div class="stats">
      <span class="stat critical" id="stat-critical">CRITICAL: 0</span>
      <span class="stat high" id="stat-high">HIGH: 0</span>
      <span class="stat medium" id="stat-medium">MEDIUM: 0</span>
      <span class="stat completed" id="stat-done">Done: 0/0</span>
    </div>
  </div>

  <div class="nav">
    <button onclick="prev()">← Prev</button>
    <button onclick="next()">Next →</button>
    <select id="filter" onchange="applyFilter()">
      <option value="all">All Items</option>
      <option value="CRITICAL">CRITICAL only</option>
      <option value="HIGH">HIGH only</option>
      <option value="MEDIUM">MEDIUM only</option>
      <option value="pending">Pending only</option>
    </select>
    <span id="position">1 / 0</span>
  </div>

  <div id="items-container"></div>

  <div class="actions">
    <button class="btn-accept" onclick="decide('accept')">Accept <span class="shortcut">[A]</span></button>
    <button class="btn-edit" onclick="toggleEdit()">Edit <span class="shortcut">[E]</span></button>
    <button class="btn-flag" onclick="decide('flag')">Flag for Expert <span class="shortcut">[F]</span></button>
  </div>

<script>
const ITEMS = __ITEMS_JSON__;
const IMAGE_BASE = '__IMAGE_BASE__';
let current = 0;
let decisions = {};
let filter = 'all';
let filteredIndices = [];

function init() {
  const container = document.getElementById('items-container');
  ITEMS.forEach((item, i) => {
    const div = document.createElement('div');
    div.className = 'item';
    div.id = `item-${i}`;
    div.innerHTML = `
      <div class="item-header">
        <div>
          <span class="tier-badge tier-${item.tier}">${item.tier}</span>
          <strong>Page ${item.page}</strong> — ${item.type || 'review'}
        </div>
        <span id="decision-${i}" style="font-weight:bold"></span>
      </div>
      <div class="finding">
        <span class="label">${item.source || ''}:</span> ${item.reason || ''}
      </div>
      <div class="panels">
        <div class="panel">
          <h3>Original Page Image</h3>
          <img src="${IMAGE_BASE}/page-${String(item.page).padStart(4,'0')}.png"
               onerror="this.alt='Image not available'" alt="Page ${item.page}">
        </div>
        <div class="panel">
          <h3>Resolved Extraction</h3>
          <pre id="extraction-${i}">Loading...</pre>
          <textarea id="edit-${i}" class="" placeholder="Edit extraction here..."></textarea>
        </div>
        <div class="panel">
          <h3>Validation Details</h3>
          <div class="finding"><span class="label">Match:</span> ${item.match || item.dose || ''}</div>
          ${item.extraction_says ? `<div class="finding"><span class="label">Extraction says:</span> ${item.extraction_says}</div>` : ''}
          ${item.image_shows ? `<div class="finding"><span class="label">Image shows:</span> ${item.image_shows}</div>` : ''}
        </div>
      </div>
    `;
    container.appendChild(div);
  });

  updateStats();
  applyFilter();
}

function applyFilter() {
  filter = document.getElementById('filter').value;
  filteredIndices = [];
  ITEMS.forEach((item, i) => {
    if (filter === 'all') filteredIndices.push(i);
    else if (filter === 'pending' && !decisions[i]) filteredIndices.push(i);
    else if (item.tier === filter) filteredIndices.push(i);
  });
  current = 0;
  showCurrent();
}

function showCurrent() {
  document.querySelectorAll('.item').forEach(el => el.classList.remove('active'));
  if (filteredIndices.length > 0) {
    const idx = filteredIndices[current];
    document.getElementById(`item-${idx}`).classList.add('active');
    document.getElementById('position').textContent =
      `${current + 1} / ${filteredIndices.length}`;
  } else {
    document.getElementById('position').textContent = '0 / 0';
  }
}

function next() {
  if (current < filteredIndices.length - 1) { current++; showCurrent(); }
}
function prev() {
  if (current > 0) { current--; showCurrent(); }
}

function decide(action) {
  if (filteredIndices.length === 0) return;
  const idx = filteredIndices[current];
  decisions[idx] = action;
  const el = document.getElementById(`decision-${idx}`);
  el.textContent = action === 'accept' ? 'ACCEPTED' : action === 'flag' ? 'FLAGGED' : 'EDITED';
  el.style.color = action === 'accept' ? '#27ae60' : '#e94560';
  updateStats();
  next();
}

function toggleEdit() {
  if (filteredIndices.length === 0) return;
  const idx = filteredIndices[current];
  const ta = document.getElementById(`edit-${idx}`);
  ta.classList.toggle('visible');
  if (ta.classList.contains('visible')) ta.focus();
}

function updateStats() {
  const tiers = {CRITICAL: 0, HIGH: 0, MEDIUM: 0};
  ITEMS.forEach(item => { if (tiers[item.tier] !== undefined) tiers[item.tier]++; });
  document.getElementById('stat-critical').textContent = `CRITICAL: ${tiers.CRITICAL}`;
  document.getElementById('stat-high').textContent = `HIGH: ${tiers.HIGH}`;
  document.getElementById('stat-medium').textContent = `MEDIUM: ${tiers.MEDIUM}`;
  const done = Object.keys(decisions).length;
  document.getElementById('stat-done').textContent = `Done: ${done}/${ITEMS.length}`;
}

document.addEventListener('keydown', e => {
  if (e.target.tagName === 'TEXTAREA') return;
  if (e.key === 'a' || e.key === 'A') decide('accept');
  else if (e.key === 'e' || e.key === 'E') toggleEdit();
  else if (e.key === 'f' || e.key === 'F') decide('flag');
  else if (e.key === 'ArrowRight') next();
  else if (e.key === 'ArrowLeft') prev();
});

init();
</script>
</body>
</html>"""


def generate_review_html(
    review_items: list[dict],
    image_dir: Path,
    output_path: Path,
):
    """Generate standalone HTML review interface.

    Args:
        review_items: Sorted review queue items.
        image_dir: Path to page images (for relative src).
        output_path: Where to write the HTML file.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Make image path relative to output
    try:
        image_rel = str(image_dir.relative_to(output_path.parent))
    except ValueError:
        image_rel = str(image_dir)

    items_json = json.dumps(review_items)
    # Escape </script> sequences to prevent premature script block closure
    items_json = items_json.replace("</", "<\\/")
    html = HTML_TEMPLATE.replace("__ITEMS_JSON__", items_json)
    html = html.replace("__IMAGE_BASE__", image_rel)

    output_path.write_text(html)
    console.print(f"  [green]Review UI generated: {output_path}[/green]")
    console.print(f"  Open in browser to review {len(review_items)} items")
