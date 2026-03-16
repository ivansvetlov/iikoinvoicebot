"""HTTP client for iikoServer incoming invoice import."""

from __future__ import annotations

from typing import Any

import httpx
from app.iiko.auth import build_auth_candidates, extract_auth_result, snippet


class IikoServerClient:
    """Handles auth/session and invoice import calls to iikoServer REST API."""

    def __init__(
        self,
        *,
        base_url: str,
        auth_path: str = "/resto/api/auth",
        import_path: str = "/resto/api/documents/import/incomingInvoice",
        auth_mode: str = "auto",
        verify_ssl: bool = False,
        timeout_sec: float = 30.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._auth_path = auth_path
        self._import_path = import_path
        self._auth_mode = auth_mode
        self._verify_ssl = verify_ssl
        self._timeout_sec = timeout_sec

    async def import_incoming_invoice(
        self,
        *,
        payload: dict[str, Any],
        username: str,
        password: str,
    ) -> dict[str, Any]:
        if not self._base_url:
            raise RuntimeError("IIKO_SERVER_BASE_URL is not configured")
        if not username or not password:
            raise RuntimeError("iiko credentials are missing")

        async with httpx.AsyncClient(
            base_url=self._base_url,
            verify=self._verify_ssl,
            timeout=self._timeout_sec,
        ) as client:
            headers, key_token = await self._auth(client, username=username, password=password)
            request_kwargs: dict[str, Any] = {"headers": headers}
            if key_token:
                request_kwargs["params"] = {"key": key_token}
            response = await client.post(self._import_path, json=payload, **request_kwargs)
            response.raise_for_status()
            try:
                return response.json()
            except ValueError:
                return {"raw": response.text}

    async def _auth(
        self,
        client: httpx.AsyncClient,
        *,
        username: str,
        password: str,
    ) -> tuple[dict[str, str], str | None]:
        attempts: list[str] = []
        for candidate in build_auth_candidates(username=username, password=password, mode=self._auth_mode):
            try:
                resp = await client.post(self._auth_path, **candidate.request_kwargs())
            except httpx.RequestError as exc:
                attempts.append(f"{candidate.name}: request-error: {exc}")
                continue

            if resp.status_code >= 400:
                attempts.append(
                    f"{candidate.name}: HTTP {resp.status_code}: {snippet(resp.text, 180)}",
                )
                continue

            auth_result = extract_auth_result(resp)
            if auth_result.key_token:
                return auth_result.bearer_headers, auth_result.key_token
            if auth_result.has_cookie_session:
                return auth_result.bearer_headers, None

            attempts.append(f"{candidate.name}: HTTP {resp.status_code}: missing token/cookie session")

        attempt_summary = " | ".join(attempts[-4:]) if attempts else "no attempts executed"
        raise RuntimeError(
            "iiko auth failed. "
            f"auth_path={self._auth_path}, mode={self._auth_mode}, details={attempt_summary}",
        )
