"""Utilities for loading per-user iiko credentials."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from threading import RLock
from typing import Any

USERS_FILE = Path(__file__).resolve().parents[2] / "data" / "users.json"
_STORE_LOCK = RLock()


def _ensure_parent_dir() -> None:
    USERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    # Best-effort hardening on POSIX; Windows may ignore mode semantics.
    try:
        os.chmod(USERS_FILE.parent, 0o700)
    except OSError:
        pass


def _load_data_unlocked() -> dict[str, Any]:
    if not USERS_FILE.exists():
        return {"users": {}}
    try:
        return json.loads(USERS_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"users": {}}


def _save_data_unlocked(data: dict[str, Any]) -> None:
    _ensure_parent_dir()
    payload = json.dumps(data, ensure_ascii=False, indent=2)

    # Atomic replace prevents partially written JSON on interruption.
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        delete=False,
        dir=USERS_FILE.parent,
        prefix=f"{USERS_FILE.name}.",
        suffix=".tmp",
    ) as handle:
        handle.write(payload)
        tmp_path = Path(handle.name)
    os.replace(tmp_path, USERS_FILE)

    # Best-effort hardening on POSIX; Windows may ignore mode semantics.
    try:
        os.chmod(USERS_FILE, 0o600)
    except OSError:
        pass


def _load_data() -> dict[str, Any]:
    with _STORE_LOCK:
        return _load_data_unlocked()


def _save_data(data: dict[str, Any]) -> None:
    with _STORE_LOCK:
        _save_data_unlocked(data)


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
    with _STORE_LOCK:
        data = _load_data_unlocked()
        users = data.get("users", {})
        entry = users.get(str(user_id), {})
        entry["iiko_login"] = login
        entry["iiko_password"] = password
        users[str(user_id)] = entry
        data["users"] = users
        _save_data_unlocked(data)


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
    with _STORE_LOCK:
        data = _load_data_unlocked()
        users = data.get("users", {})
        entry = users.get(str(user_id), {})
        entry["pdf_mode"] = mode
        users[str(user_id)] = entry
        data["users"] = users
        _save_data_unlocked(data)
