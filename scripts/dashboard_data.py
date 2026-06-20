"""Collect logs, metrics and reports for unified project dashboard."""
from __future__ import annotations

import csv
import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LOGS_DIR = PROJECT_ROOT / "logs"
TMP_DIR = PROJECT_ROOT / "tmp"
BRIDGE_DIR = PROJECT_ROOT / "data" / "private" / "grok_bridge"


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")[:26])
    except Exception:
        return None


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = max(0, min(len(ordered) - 1, int(round((len(ordered) - 1) * p))))
    return ordered[idx]


def _tail_text(path: Path, lines: int = 80, max_chars: int = 12000) -> dict[str, Any]:
    if not path.exists():
        return {"name": path.name, "path": str(path), "exists": False, "lines": [], "size": 0}
    try:
        raw = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception as exc:
        return {"name": path.name, "path": str(path), "exists": True, "error": str(exc), "lines": []}
    tail = raw[-lines:]
    text = "\n".join(tail)
    if len(text) > max_chars:
        text = "…\n" + text[-max_chars:]
        tail = text.splitlines()
    st = path.stat()
    return {
        "name": path.name,
        "path": str(path.relative_to(PROJECT_ROOT)) if path.is_relative_to(PROJECT_ROOT) else str(path),
        "exists": True,
        "size": st.st_size,
        "mtime": datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds"),
        "lines": tail,
        "total_lines": len(raw),
    }


def collect_metrics(hours: int = 24) -> dict[str, Any]:
    cutoff = datetime.now() - timedelta(hours=max(1, hours))
    rows: list[dict[str, Any]] = []
    csv_path = LOGS_DIR / "metrics.csv"
    if csv_path.exists():
        with csv_path.open("r", encoding="utf-8", errors="replace", newline="") as fh:
            for row in csv.DictReader(fh):
                ts = _parse_ts(row.get("ts"))
                if cutoff and ts and ts < cutoff:
                    continue
                payload = dict(row)
                extra = payload.get("extra_json")
                if extra:
                    try:
                        payload.update(json.loads(extra))
                    except Exception:
                        pass
                rows.append(payload)
    if not rows:
        jsonl = LOGS_DIR / "metrics.jsonl"
        if jsonl.exists():
            for line in jsonl.read_text(encoding="utf-8", errors="replace").splitlines():
                if not line.strip():
                    continue
                try:
                    payload = json.loads(line)
                except Exception:
                    continue
                ts = _parse_ts(payload.get("ts"))
                if cutoff and ts and ts < cutoff:
                    continue
                rows.append(payload)

    grouped: dict[str, dict[str, Any]] = {}
    errors_total = 0
    for row in rows:
        event = str(row.get("event") or "unknown")
        status = str(row.get("status") or "n/a")
        key = f"{event}|{status}"
        if key not in grouped:
            grouped[key] = {"event": event, "status": status, "count": 0, "durations": [], "errors": 0}
        g = grouped[key]
        g["count"] += 1
        try:
            g["durations"].append(float(row.get("duration_ms") or 0))
        except Exception:
            pass
        if status == "error" or int(row.get("status_code") or 0) >= 500:
            g["errors"] += 1
            errors_total += 1

    table = []
    for g in sorted(grouped.values(), key=lambda x: (-x["count"], x["event"])):
        d = g["durations"]
        table.append(
            {
                "event": g["event"],
                "status": g["status"],
                "count": g["count"],
                "errors": g["errors"],
                "p50_ms": round(_percentile(d, 0.5), 1),
                "p95_ms": round(_percentile(d, 0.95), 1),
            }
        )

    return {
        "hours": hours,
        "rows": len(rows),
        "errors_total": errors_total,
        "table": table,
        "updated": datetime.now().isoformat(timespec="seconds"),
    }


def collect_llm_costs(limit: int = 15) -> dict[str, Any]:
    summary_path = LOGS_DIR / "llm_costs_summary.json"
    csv_path = LOGS_DIR / "llm_costs.csv"
    summary: dict[str, Any] = {}
    if summary_path.exists():
        try:
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
        except Exception:
            summary = {}
    recent: list[dict[str, str]] = []
    if csv_path.exists():
        with csv_path.open("r", encoding="utf-8", errors="replace", newline="") as fh:
            rows = list(csv.DictReader(fh))
        for row in rows[-limit:]:
            recent.append({k: str(v) for k, v in row.items()})
    return {"summary": summary, "recent": recent, "path": str(csv_path.relative_to(PROJECT_ROOT))}


def collect_alerts(limit: int = 30) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for path in (LOGS_DIR / "alerts.jsonl", LOGS_DIR / "alerts.csv"):
        if not path.exists():
            continue
        if path.suffix == ".jsonl":
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            for line in lines[-limit:]:
                try:
                    payload = json.loads(line)
                    out.append({k: str(v) for k, v in payload.items()})
                except Exception:
                    continue
        else:
            with path.open("r", encoding="utf-8", errors="replace", newline="") as fh:
                rows = list(csv.DictReader(fh))[-limit:]
            for row in rows:
                out.append({k: str(v) for k, v in row.items()})
        if out:
            break
    return out[-limit:]


def collect_log_files() -> list[dict[str, Any]]:
    """Mirror logs/ intelligently — main files + worker glob."""
    candidates: list[Path] = []
    if LOGS_DIR.exists():
        for pattern in ("*.log", "worker*.log"):
            candidates.extend(LOGS_DIR.glob(pattern))
        for name in ("alerts.jsonl", "metrics.jsonl", "metrics.csv", "llm_costs.csv"):
            p = LOGS_DIR / name
            if p.exists():
                candidates.append(p)
    seen: set[Path] = set()
    unique = []
    for p in sorted(candidates, key=lambda x: x.stat().st_mtime if x.exists() else 0, reverse=True):
        if p.resolve() in seen:
            continue
        seen.add(p.resolve())
        unique.append(p)
    return [_tail_text(p, lines=60) for p in unique[:12]]


def _latest_glob(directory: Path, pattern: str) -> Path | None:
    if not directory.exists():
        return None
    matches = sorted(directory.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    return matches[0] if matches else None


def collect_online_status() -> dict[str, Any]:
    """Latest availability probe summary from tmp/availability_*.json."""
    latest = _latest_glob(TMP_DIR, "availability_*.json")
    if not latest:
        return {"available": False}
    try:
        payload = json.loads(latest.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"available": False, "error": str(exc), "path": str(latest.relative_to(PROJECT_ROOT))}
    stats = payload.get("stats") or payload.get("summary") or {}
    return {
        "available": True,
        "path": str(latest.relative_to(PROJECT_ROOT)),
        "mtime": datetime.fromtimestamp(latest.stat().st_mtime).isoformat(timespec="seconds"),
        "stats": stats,
        "series": payload.get("series") or list(stats.keys()),
    }


def collect_availability_html() -> list[dict[str, Any]]:
    if not TMP_DIR.exists():
        return []
    out: list[dict[str, Any]] = []
    for p in sorted(TMP_DIR.glob("availability_*.html"), key=lambda x: x.stat().st_mtime, reverse=True)[:4]:
        rel = p.relative_to(PROJECT_ROOT)
        # iframe src from docs/assets/ → ../../tmp/...
        iframe_src = "../../" + rel.as_posix()
        out.append(
            {
                "title": p.name,
                "path": str(rel),
                "iframe_src": iframe_src,
                "mtime": datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec="seconds"),
                "size": p.stat().st_size,
            }
        )
    return out


def collect_reports() -> list[dict[str, Any]]:
    reports: list[dict[str, Any]] = []
    handoff = BRIDGE_DIR / "HANDOFF_LATEST.md"
    if handoff.exists():
        text = handoff.read_text(encoding="utf-8", errors="replace")
        reports.append(
            {
                "kind": "bridge_handoff",
                "title": "Bridge HANDOFF_LATEST",
                "path": str(handoff.relative_to(PROJECT_ROOT)),
                "preview": text[:4000],
                "mtime": datetime.fromtimestamp(handoff.stat().st_mtime).isoformat(timespec="seconds"),
            }
        )
    if TMP_DIR.exists():
        for pattern in ("availability_*.html", "diagnose_*.json", "availability_*.csv"):
            for p in sorted(TMP_DIR.glob(pattern), key=lambda x: x.stat().st_mtime, reverse=True)[:5]:
                entry: dict[str, Any] = {
                    "kind": "tmp_report",
                    "title": p.name,
                    "path": str(p.relative_to(PROJECT_ROOT)),
                    "mtime": datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec="seconds"),
                    "size": p.stat().st_size,
                }
                if p.suffix == ".json":
                    try:
                        entry["preview"] = p.read_text(encoding="utf-8", errors="replace")[:3000]
                    except Exception:
                        pass
                reports.append(entry)
    journal = BRIDGE_DIR / "journal.jsonl"
    if journal.exists():
        lines = journal.read_text(encoding="utf-8", errors="replace").splitlines()
        recent = []
        for line in lines[-8:]:
            try:
                recent.append(json.loads(line))
            except Exception:
                continue
        reports.append(
            {
                "kind": "bridge_journal",
                "title": "Bridge journal (last runs)",
                "path": str(journal.relative_to(PROJECT_ROOT)),
                "runs": recent,
            }
        )
    return reports


def collect_bridge_runs(limit: int = 8) -> list[dict[str, Any]]:
    runs_dir = BRIDGE_DIR / "runs"
    if not runs_dir.exists():
        return []
    out = []
    for d in sorted(runs_dir.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True)[:limit]:
        if not d.is_dir():
            continue
        meta_path = d / "meta.json"
        if meta_path.exists():
            try:
                out.append(json.loads(meta_path.read_text(encoding="utf-8")))
            except Exception:
                continue
    return out


def collect_all(*, metrics_hours: int = 24) -> dict[str, Any]:
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "project_root": str(PROJECT_ROOT),
        "metrics": collect_metrics(metrics_hours),
        "llm_costs": collect_llm_costs(),
        "alerts": collect_alerts(),
        "logs": collect_log_files(),
        "reports": collect_reports(),
        "bridge_runs": collect_bridge_runs(),
        "online": collect_online_status(),
        "availability_html": collect_availability_html(),
    }
