r"""Unified project dashboard: TODO + logs + metrics + reports.

Usage:
  .\.venv\Scripts\python.exe scripts\render_todo_dashboard.py
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dashboard_data import collect_all

CHECKBOX_RE = re.compile(r"^- \[(?P<state>[ xX])\]\s+(?P<text>.+)$")
BULLET_RE = re.compile(r"^- (?!\[)(?P<text>.+)$")
SECTION_RE = re.compile(r"^## (.+)$")
SUBSECTION_RE = re.compile(r"^### (.+)$")


@dataclass
class TodoItem:
    text: str
    done: bool | None


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
            (current_block.items if current_block else current.items).append(item)
            continue
        if m := BULLET_RE.match(line):
            text = m.group("text").strip()
            if current_block:
                current_block.items.append(TodoItem(text=text, done=None))
            else:
                current.bullets.append(text)
    return sections


def render_html(sections: list[TodoSection], dash: dict, todo_source: str) -> str:
    total_done = sum(s.checkbox_done for s in sections)
    total_all = sum(s.checkbox_total for s in sections)
    total_pct = (total_done / total_all * 100) if total_all else 0.0
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    todo_json = json.dumps(
        [
            {
                "title": s.title,
                "pct": round(s.pct, 1),
                "done": s.checkbox_done,
                "total": s.checkbox_total,
                "bullets": s.bullets,
                "blocks": [{"title": b.title, "items": [{"text": i.text, "done": i.done} for i in b.items]} for b in s.blocks],
                "items": [{"text": i.text, "done": i.done} for i in s.items],
            }
            for s in sections
        ],
        ensure_ascii=False,
    )
    dash_json = json.dumps(dash, ensure_ascii=False)
    esc = html.escape
    m = dash.get("metrics", {})
    llm = dash.get("llm_costs", {}).get("summary", {})
    online = dash.get("online", {})
    online_pct = "—"
    if online.get("available"):
        stats = online.get("stats") or {}
        if stats:
            first = next(iter(stats.values()), {})
            if isinstance(first, dict) and "pct" in first:
                online_pct = f"{first['pct']}%"

    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Project Dashboard</title>
<style>
:root {{
  --bg:#0b1220; --card:#151f32; --text:#e8eef7; --muted:#8fa3bf;
  --done:#34d399; --todo:#fbbf24; --accent:#60a5fa; --err:#f87171; --warn:#fbbf24;
  --border:#2a3a55; --tab:#1a2740;
}}
*{{box-sizing:border-box}}
body{{margin:0;font-family:"Segoe UI",system-ui,sans-serif;background:radial-gradient(1200px 600px at 10% -10%,#1e3a5f,var(--bg));color:var(--text)}}
.wrap{{max-width:1200px;margin:0 auto;padding:20px}}
header h1{{margin:0 0 6px;font-size:1.75rem}}
.meta{{color:var(--muted);font-size:.9rem}}
.stats{{display:flex;gap:12px;flex-wrap:wrap;margin:14px 0;align-items:flex-start}}
.stat{{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:12px 16px;min-width:120px}}
.stat b{{font-size:1.25rem;color:var(--accent)}}
.stat small{{color:var(--muted)}}
.tabs{{display:flex;gap:6px;flex-wrap:wrap;margin:16px 0}}
.tab{{padding:10px 16px;border-radius:10px;border:1px solid var(--border);background:var(--tab);cursor:pointer;color:var(--text)}}
.tab.active{{background:var(--accent);color:#0b1220;font-weight:700;border-color:var(--accent)}}
.panel{{display:none}}
.panel.active{{display:block}}
.card{{background:var(--card);border:1px solid var(--border);border-radius:14px;margin-bottom:12px;overflow:hidden}}
.card h2{{margin:0;padding:14px 16px;cursor:pointer;display:flex;justify-content:space-between;gap:10px;font-size:1rem}}
.card h2:hover{{background:#1c2a44}}
.badge{{color:var(--muted);font-size:.85rem}}
.body{{padding:0 16px 14px;display:none}}
.body.open{{display:block}}
.bar{{height:8px;background:#2a3a55;border-radius:4px;overflow:hidden;margin:8px 0 12px}}
.bar>span{{display:block;height:100%;background:linear-gradient(90deg,var(--accent),var(--done))}}
.toolbar{{display:flex;gap:8px;flex-wrap:wrap;margin:10px 0}}
.toolbar input{{flex:1;min-width:180px;padding:9px 12px;border-radius:8px;border:1px solid var(--border);background:#0b1220;color:var(--text)}}
.btn{{padding:8px 12px;border-radius:8px;border:1px solid var(--border);background:var(--tab);color:var(--text);cursor:pointer}}
.btn.active{{background:var(--accent);color:#0b1220;font-weight:600}}
ul.plain{{list-style:none;margin:0;padding:0}}
ul.plain li{{padding:6px 0;border-bottom:1px solid #243049;font-size:.92rem}}
li.done{{color:var(--done)}} li.todo{{color:var(--todo)}} li.info{{color:var(--muted)}}
table{{width:100%;border-collapse:collapse;font-size:.9rem}}
th,td{{padding:8px 10px;border-bottom:1px solid var(--border);text-align:left}}
th{{color:var(--muted);font-weight:600}}
.log-viewer{{background:#070d18;border:1px solid var(--border);border-radius:10px;max-height:460px;overflow:auto;font-family:Consolas,"Cascadia Mono",monospace;font-size:.76rem;line-height:1.5}}
.log-row{{display:grid;grid-template-columns:42px 1fr;gap:0;border-bottom:1px solid #141e30}}
.log-row:hover{{background:#0f1828}}
.log-gutter{{color:#4b5f7d;text-align:right;padding:2px 8px 2px 4px;user-select:none;border-right:1px solid #141e30}}
.log-text{{padding:2px 10px;white-space:pre-wrap;word-break:break-word}}
.logline.err .log-text{{color:var(--err)}} .logline.warn .log-text{{color:var(--warn)}}
.logline.info .log-text{{color:#7dd3fc}} .logline.dim .log-text{{color:var(--muted)}}
.online-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:10px;margin:12px 0}}
.online-card{{background:#0a101c;border:1px solid var(--border);border-radius:10px;padding:12px}}
.online-card b{{font-size:1.1rem;color:var(--accent)}}
.online-card.ok b{{color:var(--done)}} .online-card.bad b{{color:var(--err)}}
.iframe-wrap{{border:1px solid var(--border);border-radius:10px;overflow:hidden;margin-top:10px;background:#fff}}
.iframe-wrap iframe{{width:100%;height:480px;border:0;display:block}}
.report{{padding:12px 16px}}
.report pre{{background:#0a101c;padding:12px;border-radius:8px;overflow:auto;max-height:360px;font-size:.8rem}}
.grid2{{display:grid;grid-template-columns:1fr 1fr;gap:12px}}
@media(max-width:800px){{.grid2{{grid-template-columns:1fr}}}}
.refresh{{margin-left:auto;font-size:.85rem;color:var(--muted)}}
</style>
</head>
<body>
<div class="wrap">
<header>
  <h1>Project Dashboard</h1>
  <div class="meta">TODO: {esc(todo_source)} · Сгенерировано: {esc(now)} · зеркало logs/ + tmp/ + bridge</div>
  <div class="stats">
    <div class="stat"><small>Roadmap</small><br><b>{total_pct:.1f}%</b><br><small>{total_done}/{total_all}</small></div>
    <div class="stat"><small>Metrics 24h</small><br><b>{m.get('rows',0)}</b><br><small>err {m.get('errors_total',0)}</small></div>
    <div class="stat"><small>Log files</small><br><b>{len(dash.get('logs',[]))}</b></div>
    <div class="stat"><small>Reports</small><br><b>{len(dash.get('reports',[]))}</b></div>
    <div class="stat"><small>LLM USD</small><br><b>{llm.get('total_usd','—')}</b></div>
    <div class="stat"><small>Online probe</small><br><b>{esc(str(online_pct))}</b><br><small>{'ok' if online.get('available') else 'нет данных'}</small></div>
    <label class="refresh"><input type="checkbox" id="autorefresh"/> авто 2 мин</label>
  </div>
  <div class="tabs" id="tabs">
    <button class="tab active" data-tab="roadmap">🗺️ Roadmap</button>
    <button class="tab" data-tab="metrics">📊 Metrics</button>
    <button class="tab" data-tab="logs">📜 Logs</button>
    <button class="tab" data-tab="reports">📋 Reports</button>
    <button class="tab" data-tab="online">🌐 Online</button>
    <button class="tab" data-tab="bridge">🔗 Bridge</button>
  </div>
</header>

<section id="roadmap" class="panel active">
  <div class="toolbar">
    <input id="search" type="search" placeholder="Поиск задач…"/>
    <button class="btn active" data-filter="all">Все</button>
    <button class="btn" data-filter="todo">Открытые</button>
    <button class="btn" data-filter="done">Готовые</button>
  </div>
  <main id="todo-root"></main>
</section>

<section id="metrics" class="panel">
  <div class="card"><div class="report">
    <h3>Метрики (последние {m.get('hours',24)}ч)</h3>
    <table id="metrics-table"><thead><tr><th>Event</th><th>Status</th><th>Count</th><th>Errors</th><th>p50 ms</th><th>p95 ms</th></tr></thead><tbody></tbody></table>
  </div></div>
  <div class="card"><div class="report"><h3>LLM costs (recent)</h3><pre id="llm-recent"></pre></div></div>
</section>

<section id="logs" class="panel">
  <div class="toolbar">
    <input id="log-search" type="search" placeholder="Фильтр по всем логам…"/>
    <button class="btn" id="log-errors">Только ERROR</button>
  </div>
  <div id="logs-root"></div>
</section>

<section id="reports" class="panel"><div id="reports-root"></div></section>
<section id="online" class="panel"><div id="online-root"></div></section>
<section id="bridge" class="panel"><div id="bridge-root"></div></section>
</div>

<script>
const TODO = {todo_json};
const DASH = {dash_json};
let todoFilter = 'all';

function esc(s) {{ return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;'); }}
function logClass(line) {{
  if (/ERROR|CRITICAL|Exception|Traceback/i.test(line)) return 'logline err';
  if (/WARNING|WARN/i.test(line)) return 'logline warn';
  if (/INFO/i.test(line)) return 'logline info';
  if (/DEBUG/i.test(line)) return 'logline dim';
  return 'logline';
}}
function renderLogLines(lines, startNo, q, errorsOnly) {{
  return (lines||[]).map((l, i) => {{
    const cls = logClass(l);
    if (errorsOnly && !/ERROR|CRITICAL|Exception/i.test(l)) return '';
    if (q && !l.toLowerCase().includes(q)) return '';
    const n = (startNo || 0) + i + 1;
    return `<div class="log-row ${{cls}}"><div class="log-gutter">${{n}}</div><div class="log-text">${{esc(l)}}</div></div>`;
  }}).join('');
}}

document.querySelectorAll('.tab').forEach(t => t.addEventListener('click', () => {{
  document.querySelectorAll('.tab').forEach(x => x.classList.remove('active'));
  document.querySelectorAll('.panel').forEach(x => x.classList.remove('active'));
  t.classList.add('active');
  document.getElementById(t.dataset.tab).classList.add('active');
  localStorage.setItem('dash-tab', t.dataset.tab);
}}));
const savedTab = localStorage.getItem('dash-tab');
if (savedTab) document.querySelector(`[data-tab="${{savedTab}}"]`)?.click();

const ar = document.getElementById('autorefresh');
let refreshTimer = null;
function setRefresh(on) {{
  if (refreshTimer) clearInterval(refreshTimer);
  refreshTimer = null;
  if (on) refreshTimer = setInterval(() => location.reload(), 120000);
  localStorage.setItem('dash-autorefresh', on ? '1' : '0');
}}
ar.checked = localStorage.getItem('dash-autorefresh') === '1';
setRefresh(ar.checked);
ar.addEventListener('change', () => setRefresh(ar.checked));

function renderTodo() {{
  const q = (document.getElementById('search').value || '').toLowerCase().trim();
  const root = document.getElementById('todo-root');
  root.innerHTML = TODO.map((s, idx) => {{
    const filt = i => todoFilter==='all'||(todoFilter==='done'&&i.done)||(todoFilter==='todo'&&i.done===false);
    const items = s.items.filter(i => filt(i) && (!q || i.text.toLowerCase().includes(q)));
    const blocks = (s.blocks||[]).map(b => {{
      const bi = b.items.filter(i => filt(i) && (!q || i.text.toLowerCase().includes(q)));
      return bi.length ? `<h4>${{esc(b.title)}}</h4><ul class="plain">${{bi.map(i=>`<li class="${{i.done?'done':i.done===false?'todo':'info'}}">${{esc(i.text)}}</li>`).join('')}}</ul>` : '';
    }}).join('');
    const bullets = (s.bullets||[]).filter(t => !q || t.toLowerCase().includes(q)).map(t=>`<li class="info">${{esc(t)}}</li>`).join('');
    if (!items.length && !blocks && !bullets) return '';
    const open = localStorage.getItem('todo-open-'+idx)==='1' ? 'open' : '';
    return `<div class="card" data-idx="${{idx}}"><h2><span>${{esc(s.title)}}</span><span class="badge">${{s.done}}/${{s.total}} · ${{s.pct}}%</span></h2>
      <div class="body ${{open}}"><div class="bar"><span style="width:${{s.pct}}%"></span></div>
      ${{bullets?'<ul class="plain">'+bullets+'</ul>':''}}
      ${{items.length?'<ul class="plain">'+items.map(i=>`<li class="${{i.done?'done':'todo'}}">${{esc(i.text)}}</li>`).join('')+'</ul>':''}}
      ${{blocks}}</div></div>`;
  }}).join('');
}}
document.querySelectorAll('[data-filter]').forEach(b => b.addEventListener('click', () => {{
  document.querySelectorAll('[data-filter]').forEach(x => x.classList.remove('active'));
  b.classList.add('active'); todoFilter = b.dataset.filter; renderTodo();
}}));
document.getElementById('search').addEventListener('input', renderTodo);
document.getElementById('todo-root').addEventListener('click', e => {{
  const h2 = e.target.closest('h2'); if (!h2) return;
  const body = h2.nextElementSibling; body.classList.toggle('open');
  localStorage.setItem('todo-open-'+h2.closest('.card').dataset.idx, body.classList.contains('open')?'1':'0');
}});
renderTodo();

const mt = document.querySelector('#metrics-table tbody');
mt.innerHTML = (DASH.metrics.table||[]).map(r => `<tr><td>${{esc(r.event)}}</td><td>${{esc(r.status)}}</td><td>${{r.count}}</td><td>${{r.errors}}</td><td>${{r.p50_ms}}</td><td>${{r.p95_ms}}</td></tr>`).join('');
document.getElementById('llm-recent').textContent = JSON.stringify(DASH.llm_costs, null, 2);

let logErrorsOnly = false;
function renderLogs() {{
  const q = (document.getElementById('log-search').value || '').toLowerCase().trim();
  document.getElementById('logs-root').innerHTML = (DASH.logs||[]).map((lf, i) => {{
    if (!lf.exists) return `<div class="card"><div class="report">${{esc(lf.name)}} — нет файла</div></div>`;
    const start = Math.max(0, (lf.total_lines||0) - (lf.lines||[]).length);
    const lines = renderLogLines(lf.lines, start, q, logErrorsOnly);
    const open = i < 2 ? 'open' : '';
    const errN = (lf.lines||[]).filter(l => /ERROR|CRITICAL/i.test(l)).length;
    return `<div class="card"><h2><span>📄 ${{esc(lf.name)}}</span><span class="badge">${{lf.path}} · ${{lf.total_lines||'?'}} lines · err ${{errN}}</span></h2>
      <div class="body ${{open}}"><div class="log-viewer">${{lines || '<div class="report">(пусто)</div>'}}</div></div></div>`;
  }}).join('');
}}
document.getElementById('log-search').addEventListener('input', renderLogs);
document.getElementById('log-errors').addEventListener('click', e => {{
  logErrorsOnly = !logErrorsOnly;
  e.target.classList.toggle('active', logErrorsOnly);
  renderLogs();
}});
document.getElementById('logs-root').addEventListener('click', e => {{
  const h2 = e.target.closest('h2'); if (!h2) return;
  h2.nextElementSibling.classList.toggle('open');
}});
renderLogs();

document.getElementById('reports-root').innerHTML = (DASH.reports||[]).map(r => {{
  let body = '';
  if (r.preview) body = `<pre>${{esc(r.preview)}}</pre>`;
  if (r.runs) body = `<pre>${{esc(JSON.stringify(r.runs, null, 2))}}</pre>`;
  return `<div class="card"><div class="report"><h3>${{esc(r.title)}}</h3><div class="badge">${{esc(r.path||'')}}</div>${{body}}</div></div>`;
}}).join('') || '<div class="card"><div class="report">Нет отчётов</div></div>';

if ((DASH.alerts||[]).length) {{
  const al = document.createElement('div');
  al.className = 'card';
  al.innerHTML = '<div class="report"><h3>⚠️ Alerts</h3><pre>' + esc(JSON.stringify(DASH.alerts, null, 2)) + '</pre></div>';
  document.getElementById('reports-root').prepend(al);
}}

(function() {{
  const root = document.getElementById('online-root');
  const on = DASH.online || {{}};
  let html = '<div class="card"><div class="report"><h3>🌐 Availability probe</h3>';
  if (!on.available) {{
    html += '<p>Нет свежих <code>tmp/availability_*.json</code>. Запусти <code>tmp/monitor_openai_availability.py</code>.</p></div></div>';
  }} else {{
    const cards = Object.entries(on.stats||{{}}).map(([k,v]) => {{
      const pct = (v && v.pct != null) ? v.pct : '?';
      const cls = (v && v.pct >= 90) ? 'ok' : (v && v.pct < 70) ? 'bad' : '';
      return `<div class="online-card ${{cls}}"><small>${{esc(k)}}</small><br><b>${{pct}}%</b><br><small>avg ${{v.avg_ms||0}}ms</small></div>`;
    }}).join('');
    html += `<div class="badge">${{esc(on.path||'')}} · ${{esc(on.mtime||'')}}</div><div class="online-grid">${{cards}}</div></div></div>`;
  }}
  (DASH.availability_html||[]).forEach(r => {{
    html += `<div class="card"><div class="report"><h3>${{esc(r.title)}}</h3><div class="badge">${{esc(r.path)}} · ${{esc(r.mtime||'')}}</div>
      <div class="iframe-wrap"><iframe src="${{esc(r.iframe_src)}}" title="${{esc(r.title)}}" loading="lazy"></iframe></div></div></div>`;
  }});
  root.innerHTML = html;
}})();

document.getElementById('bridge-root').innerHTML = (DASH.bridge_runs||[]).map(r =>
  `<div class="card"><div class="report"><h3>Run ${{esc(r.run_id||'')}}</h3><pre>${{esc(JSON.stringify(r, null, 2))}}</pre></div></div>`
).join('') || '<div class="card"><div class="report">Нет bridge runs</div></div>';
</script>
</body>
</html>"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Render unified project dashboard")
    parser.add_argument("--input", type=Path, default=Path("docs/planning/TODO.md"))
    parser.add_argument("--output", type=Path, default=Path("docs/assets/project-dashboard.html"))
    parser.add_argument("--legacy", type=Path, default=Path("docs/assets/todo-dashboard.html"))
    parser.add_argument("--metrics-hours", type=int, default=24)
    args = parser.parse_args()

    sections = parse_todo(args.input)
    dash = collect_all(metrics_hours=args.metrics_hours)
    content = render_html(sections, dash, str(args.input))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(content, encoding="utf-8")
    args.legacy.write_text(content, encoding="utf-8")
    print(f"Dashboard: {args.output}")
    print(f"Legacy alias: {args.legacy}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
