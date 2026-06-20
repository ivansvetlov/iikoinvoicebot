"""Синхронизация `grok chat dump` с ~/.grok/sessions/.../chat_history.jsonl.

Стратегия:
- каноническая история — уже записанный `grok chat dump` (не пересоздаём с нуля);
- новые пары user/assistant подтягиваются из jsonl;
- placeholder-ответы заменяются реальным текстом, если он появился в jsonl.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SESSIONS_ROOT = Path.home() / ".grok" / "sessions"
OUT_PATH = PROJECT_ROOT / "grok chat dump"
MAX_ASSISTANT_CHARS = 2000
JSONL_SINCE = datetime(2026, 6, 1).timestamp()

PLACEHOLDER_MARKERS = (
    "[ответ не сохранён в jsonl]",
    "[нет текстового ответа — только tool calls]",
)


def _extract_user_text(raw: str) -> str | None:
    m = re.search(r"<user_query>\s*(.*?)\s*</user_query>", raw, re.S)
    return m.group(1).strip() if m else None


def _brief(text: str, limit: int = MAX_ASSISTANT_CHARS) -> str:
    text = text.strip()
    if not text:
        return ""
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "\n… [обрезано]"


def _is_noise(user_text: str) -> bool:
    t = user_text.strip()
    if not t:
        return True
    if t.startswith("SYSTEM:") or t.startswith("grok SYSTEM:"):
        return True
    if t.startswith("grok Summarize the following"):
        return True
    if re.fullmatch(r"grok\s+(тест|test|hi|say hi)", t, re.I):
        return True
    if re.fullmatch(r"(grok\s+)?(hi|test|тест)", t, re.I):
        return True
    if re.fullmatch(r"(ping|pong|echo test)", t, re.I):
        return True
    if t.startswith("Reply with exactly:"):
        return True
    if t.startswith("[M#") or "\x00" in t:
        return True
    if "какие файлы ты видишь" in t:
        return True
    if "hello world" in t.lower():
        return True
    return False


def _is_placeholder(assistant: str) -> bool:
    a = assistant.strip()
    return not a or a in PLACEHOLDER_MARKERS


def _parse_existing_dump(path: Path) -> list[tuple[str, str]]:
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    turns: list[tuple[str, str]] = []
    for block in re.split(r"==== Message #\d+ ====", text):
        block = block.strip()
        if not block.startswith("[User]"):
            continue
        m = re.search(r"\[User\]\s*\n(.*?)\n\n\[Assistant\]\s*\n(.*)\Z", block, re.S)
        if m:
            turns.append((m.group(1).strip(), m.group(2).strip()))
    return turns


def _iter_histories() -> list[Path]:
    items: list[tuple[float, Path]] = []
    for path in SESSIONS_ROOT.rglob("chat_history.jsonl"):
        if "PythonProject" not in str(path) or "Groq Proxy" in str(path):
            continue
        if path.stat().st_mtime < JSONL_SINCE:
            continue
        items.append((path.stat().st_mtime, path))
    items.sort(key=lambda x: x[0])
    return [p for _, p in items]


def _parse_history_turns(path: Path) -> list[tuple[str, str]]:
    turns: list[tuple[str, str]] = []
    pending: str | None = None
    parts: list[str] = []

    def flush() -> None:
        nonlocal parts, pending
        if pending is None:
            parts = []
            return
        merged = _brief("\n\n".join(parts)) if parts else ""
        turns.append((pending, merged))
        parts = []

    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        obj = json.loads(line)
        if obj.get("type") == "user":
            content = obj.get("content")
            raw = (
                "".join(part.get("text", "") for part in content if isinstance(part, dict))
                if isinstance(content, list)
                else str(content or "")
            )
            user_text = _extract_user_text(raw)
            if not user_text or _is_noise(user_text):
                continue
            flush()
            pending = user_text
        elif obj.get("type") == "assistant":
            text = (obj.get("content") or "").strip()
            if text:
                parts.append(text)
    flush()
    return turns


def _collect_jsonl_turns() -> list[tuple[str, str]]:
    best: dict[str, str] = {}
    order: list[str] = []
    for path in _iter_histories():
        for user_text, assistant in _parse_history_turns(path):
            if user_text not in order:
                order.append(user_text)
            if not assistant:
                continue
            prev = best.get(user_text, "")
            if len(assistant) > len(prev):
                best[user_text] = assistant
    return [(u, best.get(u, "")) for u in order]


def _pick_assistant(old: str, new: str) -> str:
    if _is_placeholder(old) and new.strip():
        return new
    if _is_placeholder(new):
        return old
    if len(new.strip()) > len(old.strip()):
        return new
    return old


def _merge_turns(
    baseline: list[tuple[str, str]],
    jsonl_turns: list[tuple[str, str]],
) -> list[tuple[str, str]]:
    index: dict[str, int] = {}
    merged: list[tuple[str, str]] = []

    for user_text, assistant in baseline:
        if user_text in index:
            i = index[user_text]
            merged[i] = (user_text, _pick_assistant(merged[i][1], assistant))
        else:
            index[user_text] = len(merged)
            merged.append((user_text, assistant))

    for user_text, assistant in jsonl_turns:
        if user_text in index:
            i = index[user_text]
            merged[i] = (user_text, _pick_assistant(merged[i][1], assistant))
        else:
            index[user_text] = len(merged)
            merged.append(
                (
                    user_text,
                    assistant or "[нет текстового ответа — только tool calls]",
                )
            )

    return merged


def _render(turns: list[tuple[str, str]]) -> str:
    header = [
        "Chat 'Grok Build — PythonProject'",
        f"Дата экспорта: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "Источник: grok chat dump (baseline) + chat_history.jsonl",
        f"Сообщений: {len(turns)}",
        "Обновление: .venv\\Scripts\\python.exe scripts\\export_grok_chat_dump.py",
        "=" * 110,
        "",
    ]
    blocks: list[str] = []
    for i, (user_text, assistant_text) in enumerate(turns, 1):
        blocks.extend(
            [
                f"==== Message #{i} ====",
                "[User]",
                user_text,
                "",
                "[Assistant]",
                assistant_text,
                "",
            ]
        )
    return "\n".join(header + blocks)


def export(out_path: Path = OUT_PATH) -> int:
    baseline = _parse_existing_dump(out_path)
    jsonl_turns = _collect_jsonl_turns()
    turns = _merge_turns(baseline, jsonl_turns)
    out_path.write_text(_render(turns), encoding="utf-8")
    return len(turns)


def tail_excerpt(path: Path = OUT_PATH, messages: int = 12) -> str:
    turns = _parse_existing_dump(path)
    if not turns:
        return "(grok chat dump пуст — запусти scripts/export_grok_chat_dump.py)"
    chunk = turns[-messages:]
    lines = [f"Последние {len(chunk)} сообщений из grok chat dump:", ""]
    for i, (user_text, assistant_text) in enumerate(chunk, len(turns) - len(chunk) + 1):
        u = user_text.replace("\n", " ")
        a = assistant_text.replace("\n", " ")
        if len(u) > 160:
            u = u[:160] + "…"
        if len(a) > 220:
            a = a[:220] + "…"
        lines.append(f"#{i} U: {u}")
        lines.append(f"   A: {a}")
        lines.append("")
    return "\n".join(lines).strip()


def main() -> None:
    parser = argparse.ArgumentParser(description="Синхронизировать grok chat dump с jsonl")
    parser.add_argument("--tail", type=int, default=0, help="Показать последние N сообщений")
    args = parser.parse_args()

    if args.tail:
        export()
        print(tail_excerpt(messages=args.tail))
        return

    count = export()
    lines = len(OUT_PATH.read_text(encoding="utf-8").splitlines())
    print(f"OK: {count} messages, {lines} lines -> {OUT_PATH} ({OUT_PATH.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
