"""Bridge integration with unified project dashboard."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DASHBOARD_HTML = PROJECT_ROOT / "docs" / "assets" / "project-dashboard.html"
RENDER_SCRIPT = PROJECT_ROOT / "scripts" / "render_todo_dashboard.py"


def refresh_dashboard() -> tuple[bool, str]:
    py = PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"
    if not py.exists():
        py = Path(sys.executable)
    try:
        proc = subprocess.run(
            [str(py), str(RENDER_SCRIPT)],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
            check=False,
        )
        ok = proc.returncode == 0 and DASHBOARD_HTML.exists()
        msg = (proc.stdout or proc.stderr or "").strip() or ("OK" if ok else f"exit {proc.returncode}")
        return ok, msg
    except Exception as exc:
        return False, str(exc)


def _import_collect():
    sys.path.insert(0, str(PROJECT_ROOT))
    from scripts import dashboard_data

    return dashboard_data


def metrics_summary(hours: int = 24) -> str:
    m = _import_collect().collect_metrics(hours)
    if not m["rows"]:
        return f"Метрик за {hours}ч нет."
    lines = [f"Метрики ({hours}ч): {m['rows']} rows, errors={m['errors_total']}"]
    for row in m["table"][:6]:
        lines.append(
            f"• {row['event']} [{row['status']}] n={row['count']} "
            f"p50={row['p50_ms']}ms err={row['errors']}"
        )
    return "\n".join(lines)


def logs_summary(lines: int = 20) -> str:
    chunks = []
    for lf in _import_collect().collect_log_files()[:3]:
        if not lf.get("exists"):
            continue
        name = lf["name"]
        tail = lf.get("lines") or []
        err = sum(1 for ln in tail if "ERROR" in ln or "CRITICAL" in ln)
        chunks.append(f"--- {name} (tail {len(tail)}, errors in tail: {err}) ---")
        chunks.extend(tail[-lines:])
    return "\n".join(chunks) if chunks else "Логи пусты или logs/ отсутствует."


def reports_summary() -> str:
    dd = _import_collect()
    parts = ["Отчёты и зеркало:"]
    for r in dd.collect_reports()[:8]:
        title = r.get("title") or r.get("kind") or "?"
        path = r.get("path") or ""
        parts.append(f"• {title} — {path}")
    online = dd.collect_online_status()
    if online.get("available"):
        parts.append(f"• Online probe — {online.get('path')}")
    else:
        parts.append("• Online probe — нет данных")
    return "\n".join(parts)


def dashboard_summary() -> str:
    dd = _import_collect()
    dash = dd.collect_all(metrics_hours=24)
    m = dash.get("metrics", {})
    llm = dash.get("llm_costs", {}).get("summary", {})
    online = dash.get("online", {})
    lines = [
        f"Дашборд: {DASHBOARD_HTML.relative_to(PROJECT_ROOT)}",
        f"Roadmap + logs({len(dash.get('logs', []))}) + reports({len(dash.get('reports', []))})",
        f"Metrics 24h: {m.get('rows', 0)} rows, err {m.get('errors_total', 0)}",
        f"LLM USD: {llm.get('total_usd', '—')}",
        f"Bridge runs: {len(dash.get('bridge_runs', []))}",
        f"Online: {'ok' if online.get('available') else 'нет probe'}",
        "Открой HTML локально в браузере (вкладки Roadmap/Logs/Metrics/Online).",
    ]
    return "\n".join(lines)


def dashboard_path() -> str:
    return str(DASHBOARD_HTML)
