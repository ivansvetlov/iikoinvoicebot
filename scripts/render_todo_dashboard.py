r"""Render TODO roadmap dashboard as SVG from docs/TODO.md checkboxes.

Usage:
  .\.venv\Scripts\python.exe scripts\render_todo_dashboard.py
"""

from __future__ import annotations

import argparse
import html
import math
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


CHECKBOX_RE = re.compile(r"^- \[(?P<state>[ xX])\]\s+")


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


def _truncate(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    return text[: max_len - 1].rstrip() + "…"


def parse_todo(path: Path) -> list[SectionProgress]:
    sections: list[SectionProgress] = []
    current_title: str | None = None
    current_total = 0
    current_done = 0

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line.startswith("## "):
            if current_title is not None:
                sections.append(SectionProgress(current_title, current_total, current_done))
            current_title = line[3:].strip()
            current_total = 0
            current_done = 0
            continue

        if current_title is None:
            continue

        match = CHECKBOX_RE.match(line)
        if not match:
            continue
        current_total += 1
        if match.group("state").lower() == "x":
            current_done += 1

    if current_title is not None:
        sections.append(SectionProgress(current_title, current_total, current_done))
    return sections


def _color_for_status(status: str) -> str:
    if status == "DONE":
        return "#1f9d55"
    if status == "ACTIVE":
        return "#d97706"
    if status == "PLANNED":
        return "#64748b"
    return "#475569"


def render_svg(sections: list[SectionProgress]) -> str:
    stages = [
        s
        for s in sections
        if s.total > 0
        and (
            s.title.startswith("Этап ")
            or s.title.startswith("Текущий фокус")
            or s.title.startswith("Аудит веток")
        )
    ]
    total_done = sum(s.done for s in sections)
    total_all = sum(s.total for s in sections)
    total_pct = (total_done / total_all * 100) if total_all else 0.0
    status_counts = Counter(s.status for s in stages)

    width = 720
    row_h = 54
    overview_y = 90
    overview_h = 250
    focus_y = 360
    focus_h = 220
    bars_card_y = 600
    bars_card_h = 100 + row_h * max(len(stages), 1)
    content_height = bars_card_y + bars_card_h + 40
    min_height = int(width * 19 / 6)  # vertical canvas in 19:6 proportion (H:W)
    height = max(content_height, min_height)

    ring_cx = 155
    ring_cy = 220
    ring_r = 76
    ring_c = 2 * math.pi * ring_r
    ring_dash = ring_c * total_pct / 100

    now_label = datetime.now().strftime("%Y-%m-%d %H:%M")

    def t(value: str) -> str:
        return html.escape(value, quote=True)

    parts: list[str] = []
    parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="TODO roadmap dashboard">'
    )
    parts.append(
        '<defs>'
        '<linearGradient id="bg" x1="0" x2="1" y1="0" y2="1">'
        '<stop offset="0%" stop-color="#f8fafc"/>'
        '<stop offset="100%" stop-color="#e2e8f0"/>'
        '</linearGradient>'
        "</defs>"
    )
    parts.append(f'<rect x="0" y="0" width="{width}" height="{height}" fill="url(#bg)"/>')
    parts.append(
        '<text x="40" y="48" font-family="Segoe UI, Arial, sans-serif" font-size="28" font-weight="700" fill="#0f172a">'
        "Roadmap Dashboard"
        "</text>"
    )
    parts.append(
        '<text x="40" y="72" font-family="Segoe UI, Arial, sans-serif" font-size="14" fill="#334155">'
        f'Источник: docs/TODO.md · Обновлено: {t(now_label)}'
        "</text>"
    )

    # Overview card.
    parts.append(
        f'<rect x="40" y="{overview_y}" width="640" height="{overview_h}" rx="16" fill="#ffffff" stroke="#cbd5e1" stroke-width="1"/>'
    )
    parts.append(
        f'<circle cx="{ring_cx}" cy="{ring_cy}" r="{ring_r}" fill="none" stroke="#e2e8f0" stroke-width="18"/>'
    )
    parts.append(
        f'<circle cx="{ring_cx}" cy="{ring_cy}" r="{ring_r}" fill="none" stroke="#0ea5e9" stroke-width="18" '
        f'stroke-linecap="round" stroke-dasharray="{ring_dash:.2f} {ring_c:.2f}" transform="rotate(-90 {ring_cx} {ring_cy})"/>'
    )
    parts.append(
        f'<text x="{ring_cx}" y="{ring_cy - 2}" text-anchor="middle" font-family="Segoe UI, Arial, sans-serif" '
        f'font-size="30" font-weight="700" fill="#0f172a">{total_pct:.1f}%</text>'
    )
    parts.append(
        f'<text x="{ring_cx}" y="{ring_cy + 24}" text-anchor="middle" font-family="Segoe UI, Arial, sans-serif" '
        f'font-size="13" fill="#475569">{total_done}/{total_all} задач</text>'
    )
    parts.append(
        '<text x="300" y="150" font-family="Segoe UI, Arial, sans-serif" font-size="14" fill="#334155">Статусы этапов</text>'
    )
    parts.append(
        f'<text x="300" y="178" font-family="Segoe UI, Arial, sans-serif" font-size="14" fill="{_color_for_status("DONE")}">DONE: {status_counts.get("DONE", 0)}</text>'
    )
    parts.append(
        f'<text x="300" y="206" font-family="Segoe UI, Arial, sans-serif" font-size="14" fill="{_color_for_status("ACTIVE")}">ACTIVE: {status_counts.get("ACTIVE", 0)}</text>'
    )
    parts.append(
        f'<text x="300" y="234" font-family="Segoe UI, Arial, sans-serif" font-size="14" fill="{_color_for_status("PLANNED")}">PLANNED: {status_counts.get("PLANNED", 0)}</text>'
    )
    parts.append(
        f'<text x="300" y="272" font-family="Segoe UI, Arial, sans-serif" font-size="14" fill="#334155">Всего: {total_done}/{total_all}</text>'
    )

    # Highlights card.
    parts.append(
        f'<rect x="40" y="{focus_y}" width="640" height="{focus_h}" rx="16" fill="#ffffff" stroke="#cbd5e1" stroke-width="1"/>'
    )
    parts.append(
        f'<text x="70" y="{focus_y + 32}" font-family="Segoe UI, Arial, sans-serif" font-size="20" font-weight="600" fill="#0f172a">'
        "Фокус на спринт"
        "</text>"
    )
    highlights = [
        "Закрыть Этап 5: split-альбомы, мягкая дедупликация, fixtures",
        "Закрыть Этап 6: HTTPS/webhook и /status очереди",
        "Зафиксировать SLA MVP и еженедельный контроль",
        "Подготовить Этап 9: MAX + МойСклад + 1С",
    ]
    for idx, item in enumerate(highlights):
        y = focus_y + 64 + idx * 34
        parts.append(
            f'<text x="70" y="{y}" font-family="Segoe UI, Arial, sans-serif" font-size="14" fill="#334155">• {t(_truncate(item, 64))}</text>'
        )

    # Stage bars card.
    parts.append(
        f'<rect x="40" y="{bars_card_y}" width="640" height="{bars_card_h}" rx="16" fill="#ffffff" stroke="#cbd5e1" stroke-width="1"/>'
    )
    parts.append(
        f'<text x="70" y="{bars_card_y + 34}" font-family="Segoe UI, Arial, sans-serif" font-size="20" font-weight="600" fill="#0f172a">'
        "Прогресс по этапам"
        "</text>"
    )

    label_x = 70
    bar_x = 70
    bar_w = 380
    for i, stage in enumerate(stages):
        y = bars_card_y + 58 + i * row_h
        stage_label = _truncate(stage.title, 56)
        fill = _color_for_status(stage.status)
        parts.append(
            f'<text x="{label_x}" y="{y + 12}" font-family="Segoe UI, Arial, sans-serif" font-size="13" fill="#1e293b">{t(stage_label)}</text>'
        )
        parts.append(
            f'<rect x="{bar_x}" y="{y + 20}" width="{bar_w}" height="12" rx="6" fill="#e2e8f0"/>'
        )
        parts.append(
            f'<rect x="{bar_x}" y="{y + 20}" width="{bar_w * stage.pct / 100:.1f}" height="12" rx="6" fill="{fill}"/>'
        )
        parts.append(
            f'<text x="{bar_x + bar_w + 20}" y="{y + 31}" font-family="Segoe UI, Arial, sans-serif" font-size="12" fill="#334155">'
            f"{stage.done}/{stage.total} · {stage.pct:.1f}%"
            "</text>"
        )

    parts.append("</svg>")
    return "".join(parts)


def main() -> int:
    parser = argparse.ArgumentParser(description="Render roadmap dashboard SVG from docs/TODO.md")
    parser.add_argument("--input", type=Path, default=Path("docs/TODO.md"))
    parser.add_argument("--output", type=Path, default=Path("docs/.todo-dashboard.svg"))
    args = parser.parse_args()

    sections = parse_todo(args.input)
    svg = render_svg(sections)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(svg, encoding="utf-8")
    print(f"Dashboard written: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
