"""Собирает каталог пользовательских сообщений в docs/BOT_MESSAGE_CATALOG.md."""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = PROJECT_ROOT / "docs" / "BOT_MESSAGE_CATALOG.md"
CYR_RE = re.compile(r"[А-Яа-яЁё]")


@dataclass(frozen=True)
class MessageRow:
    source: str
    line: int
    text: str
    kind: str


def _render_expr(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value

    if isinstance(node, ast.JoinedStr):
        parts: list[str] = []
        for value in node.values:
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                parts.append(value.value)
            elif isinstance(value, ast.FormattedValue):
                parts.append("{...}")
        return "".join(parts)

    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = _render_expr(node.left)
        right = _render_expr(node.right)
        if left is None or right is None:
            return None
        return left + right

    if isinstance(node, ast.Call):
        func_name = _func_name(node.func)
        if func_name == "append_event_code" and node.args:
            base = _render_expr(node.args[0]) or "{...}"
            if len(node.args) > 1:
                code = _render_expr(node.args[1]) or "{EVENT_CODE}"
            else:
                code = "{EVENT_CODE}"
            return f"{base}\\nКод события: {code}"
    return None


def _func_name(node: ast.AST) -> str:
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Name):
        return node.id
    return ""


def _collect_from_calls(tree: ast.Module, source: str) -> list[MessageRow]:
    rows: list[MessageRow] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = _func_name(node.func)
        text_node: ast.AST | None = None
        kind: str | None = None

        if name in {"answer", "edit_text"} and node.args:
            text_node = node.args[0]
            kind = f"call:{name}"
        elif name == "send_message" and len(node.args) >= 2:
            text_node = node.args[1]
            kind = "call:send_message"
        elif name == "_reply" and len(node.args) >= 2:
            text_node = node.args[1]
            kind = "call:_reply"
        elif name == "_send_telegram_message" and len(node.args) >= 2:
            text_node = node.args[1]
            kind = "call:_send_telegram_message"
        elif name == "_edit_telegram_message" and len(node.args) >= 3:
            text_node = node.args[2]
            kind = "call:_edit_telegram_message"
        elif name == "ProcessResponse":
            for kw in node.keywords:
                if kw.arg == "message":
                    text_node = kw.value
                    kind = "response:message"
                    break

        if text_node is None or kind is None:
            continue

        rendered = _render_expr(text_node)
        if not rendered:
            continue
        normalized = " ".join(rendered.strip().split())
        if not normalized or not CYR_RE.search(normalized):
            continue
        rows.append(
            MessageRow(
                source=source,
                line=getattr(text_node, "lineno", getattr(node, "lineno", 0)),
                text=normalized,
                kind=kind,
            )
        )
    return rows


def _collect_from_formatters(tree: ast.Module, source: str) -> list[MessageRow]:
    rows: list[MessageRow] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        if node.name not in {"format_user_response", "format_invoice_markdown"}:
            continue
        docstring_node = None
        if node.body and isinstance(node.body[0], ast.Expr):
            value = node.body[0].value
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                docstring_node = value
        for sub in ast.walk(node):
            if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                if sub is docstring_node:
                    continue
                value = " ".join(sub.value.strip().split())
                if not value or not CYR_RE.search(value):
                    continue
                rows.append(
                    MessageRow(
                        source=source,
                        line=getattr(sub, "lineno", getattr(node, "lineno", 0)),
                        text=value,
                        kind=f"formatter:{node.name}",
                    )
                )
    return rows


def _dedupe(rows: list[MessageRow]) -> list[MessageRow]:
    unique: dict[tuple[str, int, str], MessageRow] = {}
    for row in rows:
        unique[(row.source, row.line, row.text)] = row
    return sorted(unique.values(), key=lambda r: (r.source, r.line, r.text))


def _render_md(rows: list[MessageRow]) -> str:
    lines = [
        "# Каталог пользовательских сообщений",
        "",
        "Документ с текстами сообщений, которые отправляются пользователю.",
        "Если хотите править формулировки, ориентируйтесь на `source:line` в таблице ниже.",
        "",
        "## Источники",
        "- `app/bot/manager.py`",
        "- `app/tasks.py`",
        "- `app/api.py`",
        "- `app/services/pipeline.py`",
        "- `app/utils/user_messages.py`",
        "",
        "## Сообщения",
        "",
        "| Source | Kind | Text |",
        "| --- | --- | --- |",
    ]
    for row in rows:
        src = f"`{row.source}:{row.line}`"
        kind = f"`{row.kind}`"
        text = row.text.replace("|", "\\|")
        lines.append(f"| {src} | {kind} | {text} |")

    lines.extend(
        [
            "",
            "## Обновление каталога",
            "```powershell",
            ".\\.venv\\Scripts\\python.exe scripts\\export_user_messages.py",
            "```",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    targets = [
        PROJECT_ROOT / "app" / "bot" / "manager.py",
        PROJECT_ROOT / "app" / "tasks.py",
        PROJECT_ROOT / "app" / "api.py",
        PROJECT_ROOT / "app" / "services" / "pipeline.py",
        PROJECT_ROOT / "app" / "utils" / "user_messages.py",
    ]

    rows: list[MessageRow] = []
    for path in targets:
        source = str(path.relative_to(PROJECT_ROOT)).replace("\\", "/")
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        rows.extend(_collect_from_calls(tree, source))
        if source.endswith("user_messages.py"):
            rows.extend(_collect_from_formatters(tree, source))

    OUTPUT_PATH.write_text(_render_md(_dedupe(rows)), encoding="utf-8")
    print(f"Saved: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
