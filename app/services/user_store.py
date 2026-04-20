"""Utilities for loading per-user iiko credentials."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

USERS_FILE = Path(__file__).resolve().parents[2] / "data" / "users.json"


def _load_data() -> dict[str, Any]:
    if not USERS_FILE.exists():
        return {"users": {}}
    try:
        return json.loads(USERS_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"users": {}}


def _save_data(data: dict[str, Any]) -> None:
    USERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    USERS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def get_iiko_credentials(user_id: str | None) -> tuple[str, str] | None:
    """Return (login, password) for the given Telegram user id, if present."""
    if not user_id:
        return None
    data = _load_data()
    users = data.get("users", {})
    entry = users.get(str(user_id))
    if not entry:
        return None
    login = (entry.get("iiko_login") or "").strip()
    password = (entry.get("iiko_password") or "").strip()
    if not login or not password:
        return None
    return login, password


def set_iiko_credentials(user_id: str, login: str, password: str) -> None:
    """Persist (login, password) for the given Telegram user id."""
    data = _load_data()
    users = data.get("users", {})
    entry = users.get(str(user_id), {})
    entry["iiko_login"] = login
    entry["iiko_password"] = password
    users[str(user_id)] = entry
    data["users"] = users
    _save_data(data)


def clear_iiko_credentials(user_id: str) -> None:
    """Remove saved iiko credentials for the given Telegram user id."""
    data = _load_data()
    users = data.get("users", {})
    entry = users.get(str(user_id))
    if not isinstance(entry, dict):
        return
    changed = False
    if "iiko_login" in entry:
        entry.pop("iiko_login", None)
        changed = True
    if "iiko_password" in entry:
        entry.pop("iiko_password", None)
        changed = True
    if changed:
        users[str(user_id)] = entry
        data["users"] = users
        _save_data(data)


def get_pdf_mode(user_id: str | None) -> str:
    """Return pdf processing mode for user: fast or accurate."""
    if not user_id:
        return "accurate"
    data = _load_data()
    users = data.get("users", {})
    entry = users.get(str(user_id), {})
    mode = (entry.get("pdf_mode") or "").strip().lower()
    return mode if mode in {"fast", "accurate"} else "accurate"


def set_pdf_mode(user_id: str, mode: str) -> None:
    """Persist pdf processing mode for the given Telegram user id."""
    mode = mode.strip().lower()
    if mode not in {"fast", "accurate"}:
        raise ValueError("Invalid pdf mode")
    data = _load_data()
    users = data.get("users", {})
    entry = users.get(str(user_id), {})
    entry["pdf_mode"] = mode
    users[str(user_id)] = entry
    data["users"] = users
    _save_data(data)
