"""Utilities for loading per-user settings and category profiles."""

from __future__ import annotations

import json
from datetime import datetime, timezone
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


def _normalize_category_names(names: list[str]) -> list[str]:
    seen: set[str] = set()
    normalized: list[str] = []
    for raw in names:
        name = str(raw or "").strip()
        if not name:
            continue
        key = name.casefold()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(name)
    return normalized


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _ensure_global_bank(data: dict[str, Any]) -> dict[str, Any]:
    bank = data.get("global_category_bank")
    if not isinstance(bank, dict):
        bank = {}
        data["global_category_bank"] = bank
    return bank


def remember_global_categories(
    names: list[str],
    *,
    source: str,
    user_id: str | None = None,
) -> None:
    """Persist canonical category names into the shared global bank."""
    data = _load_data()
    bank = _ensure_global_bank(data)
    order = data.setdefault("global_category_order", [])
    if not isinstance(order, list):
        order = []
        data["global_category_order"] = order

    for name in _normalize_category_names(names):
        key = name.casefold()
        now = _now_iso()
        if key not in bank:
            bank[key] = {
                "name": name,
                "usage_count": 1,
                "sources": [source],
                "created_by_user_id": str(user_id) if user_id else None,
                "created_at": now,
                "updated_at": now,
            }
            order.append(name)
            continue

        entry = bank[key]
        if not isinstance(entry, dict):
            entry = {"name": name}
            bank[key] = entry
        entry["name"] = name
        entry["usage_count"] = int(entry.get("usage_count") or 0) + 1
        sources = list(entry.get("sources") or [])
        if source not in sources:
            sources.append(source)
        entry["sources"] = sources
        entry["updated_at"] = now

    _save_data(data)


def get_global_category_bank() -> list[str]:
    """Return canonical category names in first-seen order."""
    data = _load_data()
    order = data.get("global_category_order")
    if isinstance(order, list) and order:
        return [str(name) for name in order]

    bank = _ensure_global_bank(data)
    return [
        str(entry.get("name") or "")
        for entry in bank.values()
        if isinstance(entry, dict) and entry.get("name")
    ]


def set_category_profile(
    user_id: str,
    *,
    business_model: list[str],
    custom_categories: list[str],
    resolved_categories: list[str],
) -> dict[str, Any]:
    """Persist onboarding category profile for a Telegram user."""
    data = _load_data()
    users = data.setdefault("users", {})
    entry = users.setdefault(str(user_id), {})
    profile = {
        "version": 1,
        "business_model": list(business_model),
        "custom_categories": _normalize_category_names(custom_categories),
        "resolved_categories": _normalize_category_names(resolved_categories),
        "updated_at": _now_iso(),
    }
    entry["category_profile"] = profile
    users[str(user_id)] = entry
    data["users"] = users
    _save_data(data)
    remember_global_categories(resolved_categories, source="category_profile", user_id=user_id)
    return profile


def get_category_profile(user_id: str) -> dict[str, Any] | None:
    """Return saved category profile for a Telegram user."""
    data = _load_data()
    users = data.get("users", {})
    entry = users.get(str(user_id))
    if not isinstance(entry, dict):
        return None
    profile = entry.get("category_profile")
    return profile if isinstance(profile, dict) else None
