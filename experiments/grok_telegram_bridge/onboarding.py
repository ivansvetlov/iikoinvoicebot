"""First-run bootstrap prompt injection."""
from __future__ import annotations

BOOTSTRAP_PROMPT = """\
[Bootstrap — первый запуск сессии bridge]

По METAPROMPT выполни обязательный bootstrap (п. «Первый запуск сессии»):
прочитай HANDOFF, AGENTS, DEBUG, TODO, HANDOFF_LATEST; проверь git и health;
кратко отчитайся в 5–8 строках; затем жди задачу пользователя.

Если пользователь уже прислал задачу ниже — после bootstrap выполни и её.
"""


def needs_bootstrap(meta: dict) -> bool:
    return not meta.get("bootstrap_done")


def mark_bootstrapped(meta: dict) -> dict:
    meta = dict(meta or {})
    meta["bootstrap_done"] = True
    return meta


def wrap_first_prompt(user_text: str, *, bootstrap: bool) -> str:
    if not bootstrap:
        return user_text
    return f"{BOOTSTRAP_PROMPT}\n\n---\nЗадача пользователя:\n{user_text}"
