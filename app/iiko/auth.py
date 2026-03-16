"""Shared auth helpers for iikoServer REST API variants."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any

import httpx

AUTH_MODES = ("auto", "json", "form-password", "form-pass")

TOKEN_FIELDS = ("token", "accessToken", "sessionId", "credentials", "authToken")

_PLAIN_TOKEN_RE = re.compile(r"^[A-Za-z0-9._:-]{8,256}$")


def snippet(text: str, limit: int = 320) -> str:
    value = (text or "").strip()
    if len(value) <= limit:
        return value
    return value[:limit] + "...<truncated>"


def _hash_password(password: str, transform: str) -> str:
    transform_norm = (transform or "").strip().lower()
    encoded = password.encode("utf-8")
    if transform_norm == "plain":
        return password
    if transform_norm == "sha1":
        return hashlib.sha1(encoded).hexdigest()
    if transform_norm == "md5":
        return hashlib.md5(encoded).hexdigest()
    if transform_norm == "sha256":
        return hashlib.sha256(encoded).hexdigest()
    raise ValueError(f"Unsupported pass transform: {transform}")


@dataclass(frozen=True)
class AuthCandidate:
    name: str
    json_payload: dict[str, Any] | None = None
    form_payload: dict[str, Any] | None = None

    def request_kwargs(self) -> dict[str, Any]:
        if self.json_payload is not None:
            return {"json": self.json_payload}
        if self.form_payload is not None:
            return {
                "data": self.form_payload,
                "headers": {"Content-Type": "application/x-www-form-urlencoded"},
            }
        return {}


def build_auth_candidates(*, username: str, password: str, mode: str = "auto") -> list[AuthCandidate]:
    mode_norm = (mode or "auto").strip().lower()
    if mode_norm not in AUTH_MODES:
        raise ValueError(f"Unsupported auth mode: {mode}")

    json_candidate = AuthCandidate(
        name="json_login_password",
        json_payload={"login": username, "password": password},
    )
    form_password_candidate = AuthCandidate(
        name="form_login_password",
        form_payload={"login": username, "password": password},
    )
    form_pass_candidates = [
        AuthCandidate(
            name=f"form_login_pass_{transform}",
            form_payload={"login": username, "pass": _hash_password(password, transform)},
        )
        for transform in ("plain", "sha1", "md5", "sha256")
    ]

    if mode_norm == "json":
        return [json_candidate]
    if mode_norm == "form-password":
        return [form_password_candidate]
    if mode_norm == "form-pass":
        return form_pass_candidates
    return [json_candidate, form_password_candidate, *form_pass_candidates]


def extract_token_value(data: Any) -> tuple[str | None, str | None]:
    if not isinstance(data, dict):
        return None, None
    for key in TOKEN_FIELDS:
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return key, value.strip()
    return None, None


def _extract_plain_text_token(raw_text: str) -> str | None:
    candidate = (raw_text or "").strip()
    if not candidate or "\n" in candidate or "\r" in candidate:
        return None
    if not _PLAIN_TOKEN_RE.fullmatch(candidate):
        return None
    return candidate


@dataclass(frozen=True)
class AuthResult:
    bearer_headers: dict[str, str]
    key_token: str | None
    token_source: str | None
    has_cookie_session: bool


def extract_auth_result(response: httpx.Response) -> AuthResult:
    data: Any = None
    try:
        data = response.json()
    except ValueError:
        data = None

    token_field, token_value = extract_token_value(data)
    if token_value:
        return AuthResult(
            bearer_headers={"Authorization": f"Bearer {token_value}"},
            key_token=token_value,
            token_source=token_field,
            has_cookie_session=bool(response.headers.get("set-cookie")),
        )

    plain_token = _extract_plain_text_token(response.text)
    if plain_token:
        return AuthResult(
            bearer_headers={"Authorization": f"Bearer {plain_token}"},
            key_token=plain_token,
            token_source="plain_text",
            has_cookie_session=bool(response.headers.get("set-cookie")),
        )

    return AuthResult(
        bearer_headers={},
        key_token=None,
        token_source=None,
        has_cookie_session=bool(response.headers.get("set-cookie")),
    )
