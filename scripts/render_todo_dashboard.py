r"""Render TODO roadmap dashboard from docs/planning/TODO.md.

Outputs interactive HTML (primary) and optional legacy SVG.

Usage:
  .\.venv\Scripts\python.exe scripts\render_todo_dashboard.py
  .\.venv\Scripts\python.exe scripts\render_todo_dashboard.py --format both
"""

from __future__ import annotations

import argparse
import html
import json
import math
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

CHECKBOX_RE = re.compile(r"^- \[(?P<state>[ xX])\]\s+(?P<text>.+)$")
BULLET_RE = re.compile(r"^- (?!\[)(?P<text>.+)$")
SECTION_RE = re.compile(r"^## (.+)$")
SUBSECTION_RE = re.compile(r"^### (.+)$")


@dataclass
class TodoItem:
    text: str
    done: bool | None  # None = plain bullet


@dataclass
class TodoBlock:
    title: str
    items: list[TodoItem] = field(default_factory=list)


@dataclass
class TodoSection:
    title: str
    bullets: list[str] = field(default_factory=list)
    blocks: list[TodoBlock] = field(default_factory=list)
    items: list[TodoItem] = field(default_factory=list)

    @property
    def checkbox_total(self) -> int:
        n = sum(1 for i in self.items if i.done is not None)
        for b in self.blocks:
            n += sum(1 for i in b.items if i.done is not None)
        return n

    @property
    def checkbox_done(self) -> int:
        n = sum(1 for i in self.items if i.done is True)
        for b in self.blocks:
            n += sum(1 for i in b.items if i.done is True)
        return n

    @property
    def pct(self) -> float:
        t = self.checkbox_total
        return (self.checkbox_done / t * 100) if t else 0.0


def parse_todo(path: Path) -> list[TodoSection]:
    sections: list[TodoSection] = []
    current: TodoSection | None = None
    current_block: TodoBlock | None = None

    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.rstrip()
        if m := SECTION_RE.match(line):
            current = TodoSection(title=m.group(1).strip())
            sections.append(current)
            current_block = None
            continue
        if current is None:
            continue
        if m := SUBSECTION_RE.match(line):
            current_block = TodoBlock(title=m.group(1).strip())
            current.blocks.append(current_block)
            continue
        if m := CHECKBOX_RE.match(line):
            item = TodoItem(text=m.group("text").strip(), done=m.group("state").lower() == "x")
            if current_block is not None:
                current_block.items.append(item)
            else:
                current.items.append(item)
            continue
        if m := BULLET_RE.match(line):
            text = m.group("text").strip()
            if current_block is not None:
                current_block.items.append(TodoItem(text=text, done=None))
            else:
                current.bullets.append(text)
            continue

    return sections


def render_html(sections: list[TodoSection], source: str) -> str:
    total_done = sum(s.checkbox_done for s in sections)
    total_all = sum(s.checkbox_total for s in sections)
    total_pct = (total_done / total_all * 100) if total_all else 0.0
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    payload = []
    for s in sections:
        payload.append(
            {
                "title": s.title,
                "pct": round(s.pct, 1),
                "done": s.checkbox_done,
                "total": s.checkbox_total,
                "bullets": s.bullets,
                "blocks": [
                    {
                        "title": b.title,
                        "items": [
                            {"text": i.text, "done": i.done}
                            for i in b.items
                        ],
                    }
                    for b in s.blocks
                ],
                "items": [{"text": i.text, "done": i.done} for i in s.items],
            }
        )
    data_json = json.dumps(payload, ensure_ascii=False)
    esc = html.escape

    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Roadmap Dashboard</title>
<style>
:root {{
  --bg: #0f172a; --card: #1e293b; --text: #e2e8f0; --muted: #94a3b8;
  --done: #22c55e; --todo: #f59e0b; --accent: #38bdf8; --border: #334155;
}}
* {{ box-sizing: border-box; }}
body {{ margin: 0; font-family: "Segoe UI", system-ui, sans-serif; background: linear-gradient(145deg,#0f172a,#1e293b); color: var(--text); }}
.wrap {{ max-width: 1100px; margin: 0 auto; padding: 24px; }}
header {{ margin-bottom: 20px; }}
h1 {{ margin: 0 0 8px; font-size: 1.8rem; }}
.meta {{ color: var(--muted); font-size: 0.95rem; }}
.stats {{ display: flex; gap: 16px; flex-wrap: wrap; margin: 16px 0; }}
.stat {{ background: var(--card); border: 1px solid var(--border); border-radius: 12px; padding: 14px 18px; min-width: 140px; }}
.stat b {{ font-size: 1.4rem; color: var(--accent); }}
.toolbar {{ display: flex; gap: 8px; flex-wrap: wrap; margin: 12px 0 20px; }}
.toolbar input {{ flex: 1; min-width: 200px; padding: 10px 12px; border-radius: 8px; border: 1px solid var(--border); background: #0b1220; color: var(--text); }}
.btn {{ padding: 8px 14px; border-radius: 8px; border: 1px solid var(--border); background: var(--card); color: var(--text); cursor: pointer; }}
.btn.active {{ background: var(--accent); color: #0f172a; border-color: var(--accent); font-weight: 600; }}
section.card {{ background: var(--card); border: 1px solid var(--border); border-radius: 14px; margin-bottom: 12px; overflow: hidden; }}
section.card h2 {{ margin: 0; padding: 14px 16px; cursor: pointer; display: flex; justify-content: space-between; align-items: center; gap: 12px; }}
section.card h2:hover {{ background: #243044; }}
.badge {{ font-size: 0.85rem; color: var(--muted); }}
.body {{ padding: 0 16px 14px; display: none; }}
.body.open {{ display: block; }}
.bar {{ height: 8px; background: #334155; border-radius: 4px; overflow: hidden; margin: 8px 0 12px; }}
.bar > span {{ display: block; height: 100%; background: linear-gradient(90deg,var(--accent),var(--done)); }}
h3 {{ font-size: 1rem; color: var(--accent); margin: 12px 0 6px; }}
ul {{ margin: 0; padding-left: 0; list-style: none; }}
li {{ padding: 6px 0; border-bottom: 1px solid #2a3648; font-size: 0.95rem; }}
li:last-child {{ border-bottom: none; }}
li.done {{ color: var(--done); }}
li.todo {{ color: var(--todo); }}
li.info {{ color: var(--muted); }}
li::before {{ margin-right: 8px; }}
li.done::before {{ content: "✓"; }}
li.todo::before {{ content: "○"; }}
li.info::before {{ content: "•"; color: var(--muted); }}
.hidden {{ display: none !important; }}
</style>
</head>
<body>
<div class="wrap">
<header>
  <h1>Roadmap Dashboard</h1>
  <div class="meta">Источник: {esc(source)} · Обновлено: {esc(now)}</div>
  <div class="stats">
    <div class="stat"><div>Общий прогресс</div><b>{total_pct:.1f}%</b></div>
    <div class="stat"><div>Чекбоксы</div><b>{total_done}/{total_all}</b></div>
    <div class="stat"><div>Секций</div><b>{len(sections)}</b></div>
  </div>
  <div class="toolbar">
    <input id="search" type="search" placeholder="Поиск по задачам…"/>
    <button class="btn active" data-filter="all">Все</button>
    <button class="btn" data-filter="todo">Открытые</button>
    <button class="btn" data-filter="done">Готовые</button>
    <button class="btn" id="expand">Развернуть всё</button>
  </div>
</header>
<main id="root"></main>
</div>
<script>
const DATA = {data_json};
const root = document.getElementById('root');
let filter = 'all';

function itemClass(done) {{
  if (done === true) return 'done';
  if (done === false) return 'todo';
  return 'info';
}}

function matchFilter(done) {{
  if (filter === 'all') return true;
  if (filter === 'done') return done === true;
  if (filter === 'todo') return done === false;
  return true;
}}

function renderItems(items, q) {{
  return items.filter(i => !q || i.text.toLowerCase().includes(q))
    .filter(i => matchFilter(i.done))
    .map(i => `<li class="${{itemClass(i.done)}}">${{i.text}}</li>`).join('');
}}

function render() {{
  const q = (document.getElementById('search').value || '').toLowerCase().trim();
  root.innerHTML = DATA.map((s, idx) => {{
    const itemsHtml = renderItems(s.items, q);
    const blocksHtml = (s.blocks || []).map(b => {{
      const inner = renderItems(b.items, q);
      if (!inner) return '';
      return `<h3>${{b.title}}</h3><ul>${{inner}}</ul>`;
    }}).join('');
    const bulletsHtml = (s.bullets || []).filter(t => !q || t.toLowerCase().includes(q))
      .map(t => `<li class="info">${{t}}</li>`).join('');
    if (!itemsHtml && !blocksHtml && !bulletsHtml) return '';
    const open = localStorage.getItem('todo-open-' + idx) === '1' ? 'open' : '';
    return `<section class="card" data-idx="${{idx}}">
      <h2><span>${{s.title}}</span><span class="badge">${{s.done}}/${{s.total}} · ${{s.pct}}%</span></h2>
      <div class="body ${{open}}">
        <div class="bar"><span style="width:${{s.pct}}%"></span></div>
        ${{bulletsHtml ? '<ul>' + bulletsHtml + '</ul>' : ''}}
        ${{itemsHtml ? '<ul>' + itemsHtml + '</ul>' : ''}}
        ${{blocksHtml}}
      </div>
    </section>`;
  }}).join('');
}}

document.querySelectorAll('[data-filter]').forEach(btn => {{
  btn.addEventListener('click', () => {{
    document.querySelectorAll('[data-filter]').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    filter = btn.dataset.filter;
    render();
  }});
}});
document.getElementById('search').addEventListener('input', render);
document.getElementById('expand').addEventListener('click', () => {{
  document.querySelectorAll('.body').forEach(el => el.classList.add('open'));
  DATA.forEach((_, i) => localStorage.setItem('todo-open-' + i, '1'));
}});
root.addEventListener('click', e => {{
  const h2 = e.target.closest('h2');
  if (!h2) return;
  const body = h2.nextElementSibling;
  const card = h2.closest('section');
  const idx = card.dataset.idx;
  body.classList.toggle('open');
  localStorage.setItem('todo-open-' + idx, body.classList.contains('open') ? '1' : '0');
}});
render();
</script>
</body>
</html>"""


# --- legacy SVG (abbreviated wrapper) ---

@dataclass
class SectionProgress:
    title: str
    total: int
    done: int

    @property
    def pct(self) -> float:
        return (self.done / self.total * 100) if self.total else 0.0

    @property
    def status(self) -> str:
        if self.total == 0:
            return "INFO"
        if self.done == self.total:
            return "DONE"
        if self.done == 0:
            return "PLANNED"
        return "ACTIVE"


def sections_to_progress(sections: list[TodoSection]) -> list[SectionProgress]:
    return [SectionProgress(s.title, s.checkbox_total, s.checkbox_done) for s in sections]


def render_svg(sections: list[SectionProgress]) -> str:
    stages = [s for s in sections if s.total > 0 and s.title.startswith(("Этап ", "Текущий", "Аудит"))]
    total_done = sum(s.done for s in sections)
    total_all = sum(s.total for s in sections)
    total_pct = (total_done / total_all * 100) if total_all else 0.0
    width, row_h = 1200, 120
    height = 400 + row_h * max(len(stages), 1)
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    def t(v: str) -> str:
        return html.escape(v, quote=True)

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">',
        f'<text x="40" y="50" font-size="32" font-weight="700">{total_pct:.1f}% · {total_done}/{total_all}</text>',
        f'<text x="40" y="85" font-size="18">{t(now)}</text>',
    ]
    for i, st in enumerate(stages):
        y = 120 + i * row_h
        parts.append(f'<text x="40" y="{y}" font-size="20">{t(st.title[:50])}</text>')
        parts.append(
            f'<rect x="500" y="{y-18}" width="{int(400*st.pct/100)}" height="24" fill="#0ea5e9"/>'
        )
    parts.append("</svg>")
    return "".join(parts)


def main() -> int:
    parser = argparse.ArgumentParser(description="Render TODO dashboard")
    parser.add_argument("--input", type=Path, default=Path("docs/planning/TODO.md"))
    parser.add_argument("--html", type=Path, default=Path("docs/assets/todo-dashboard.html"))
    parser.add_argument("--svg", type=Path, default=Path("docs/assets/.todo-dashboard.svg"))
    parser.add_argument("--format", choices=["html", "svg", "both"], default="html")
    args = parser.parse_args()

    sections = parse_todo(args.input)
    if args.format in ("html", "both"):
        args.html.parent.mkdir(parents=True, exist_ok=True)
        args.html.write_text(render_html(sections, str(args.input)), encoding="utf-8")
        print(f"HTML dashboard: {args.html}")
    if args.format in ("svg", "both"):
        prog = sections_to_progress(sections)
        args.svg.parent.mkdir(parents=True, exist_ok=True)
        args.svg.write_text(render_svg(prog), encoding="utf-8")
        print(f"SVG dashboard: {args.svg}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
