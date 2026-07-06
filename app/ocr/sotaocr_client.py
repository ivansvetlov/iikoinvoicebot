"""Async HTTP client for SotaOCR API (https://sotaocr.com/docs)."""
from __future__ import annotations

import asyncio
import json
import logging
import mimetypes
import platform
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlencode

import requests
from pydantic import BaseModel, ConfigDict, ValidationError
from requests.adapters import HTTPAdapter
from urllib3.exceptions import ProtocolError as Urllib3ProtocolError
from urllib3.util.retry import Retry

from app.config import settings
from app.utils.subprocess_hidden import hidden_subprocess_kwargs

logger = logging.getLogger(__name__)

_vpn_ready = False

ResultFormat = Literal["json", "markdown", "text"]
TERMINAL_FAILURES = frozenset({"failed", "error", "cancelled", "canceled"})
_CURL_HTTP_CODE_RE = re.compile(r"\n__HTTP_CODE__(\d{3})\s*$")


class SotaOcrError(RuntimeError):
    """Raised when SotaOCR API returns an error or response is invalid."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        code: str | None = None,
        payload: Any = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.payload = payload


class SotaOcrJob(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    account_id: str | None = None
    status: str
    page_count: int | None = None
    pages_completed: int | None = None
    model_profile: str | None = None
    upstream_job_id: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class SotaOcrResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    content: str
    format: ResultFormat | None = None


@dataclass(frozen=True, slots=True)
class SotaOcrBalance:
    remaining_pages: int
    total_affordable_pages: int
    raw: dict[str, Any]


def _parse_api_error(status_code: int, payload: Any, action: str) -> SotaOcrError:
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            code = str(error.get("code") or "unknown_error")
            message = str(error.get("message") or action)
            extras = {
                key: error[key]
                for key in ("entity_code", "requested_units", "available_units")
                if key in error
            }
            if extras:
                message = f"{message} ({json.dumps(extras, ensure_ascii=False)})"
            return SotaOcrError(
                f"{action} failed: {message}",
                status_code=status_code,
                code=code,
                payload=payload,
            )
        if payload.get("errorMessage"):
            return SotaOcrError(
                str(payload["errorMessage"]),
                status_code=status_code,
                code=str(payload.get("code") or "api_error"),
                payload=payload,
            )
    return SotaOcrError(
        f"{action} failed with HTTP {status_code}",
        status_code=status_code,
        payload=payload,
    )


def _validate_job(payload: Any, *, action: str) -> SotaOcrJob:
    try:
        return SotaOcrJob.model_validate(payload)
    except ValidationError as exc:
        raise SotaOcrError(
            f"{action}: invalid job payload",
            payload=payload,
        ) from exc


def _validate_result(payload: Any, *, action: str) -> SotaOcrResult:
    try:
        return SotaOcrResult.model_validate(payload)
    except ValidationError as exc:
        raise SotaOcrError(
            f"{action}: invalid result payload",
            payload=payload,
        ) from exc


def _build_requests_session(max_retries: int) -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=max_retries,
        connect=max_retries,
        read=max_retries,
        backoff_factor=0.5,
        status_forcelist=(502, 503, 504),
        allowed_methods=frozenset(["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"]),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def _is_transient_network_error(exc: BaseException) -> bool:
    if isinstance(exc, requests.exceptions.ConnectionError):
        return True
    if isinstance(exc, Urllib3ProtocolError):
        return True
    return False


def _find_curl_executable() -> str | None:
    for name in ("curl.exe", "curl"):
        path = shutil.which(name)
        if path:
            return path
    return None


def _ensure_vpn_once() -> None:
    global _vpn_ready
    if _vpn_ready:
        return
    from app.ocr.vpn import ensure_sotaocr_vpn

    if ensure_sotaocr_vpn():
        _vpn_ready = True
    else:
        logger.warning("SotaOCR split VPN is not running; API may fail without VPN route")


class SotaOcrClient:
    """SotaOCR REST client: upload → poll job → fetch result."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout_sec: float | None = None,
        poll_interval_sec: float | None = None,
        model_profile: str | None = None,
        max_retries: int | None = None,
        prefer_curl: bool | None = None,
    ) -> None:
        self.api_key = (api_key if api_key is not None else settings.sotaocr_api_key).strip()
        self.base_url = (base_url or settings.sotaocr_base_url).rstrip("/")
        self.timeout_sec = float(
            timeout_sec if timeout_sec is not None else settings.sotaocr_timeout_sec
        )
        self.poll_interval_sec = max(
            1.0,
            float(
                poll_interval_sec
                if poll_interval_sec is not None
                else settings.sotaocr_poll_interval_sec
            ),
        )
        self.model_profile = (
            model_profile
            if model_profile is not None
            else (settings.sotaocr_model_profile or "").strip()
        ) or None
        self.max_retries = max(
            0,
            int(max_retries if max_retries is not None else settings.sotaocr_max_retries),
        )
        if prefer_curl is None:
            mode = (settings.sotaocr_prefer_curl or "auto").strip().lower()
            if mode in {"1", "true", "yes", "curl"}:
                prefer_curl = True
            elif mode in {"0", "false", "no", "requests"}:
                prefer_curl = False
            else:
                prefer_curl = platform.system() == "Windows"
        self.prefer_curl = bool(prefer_curl)
        self._session = _build_requests_session(self.max_retries)

    def _headers(self) -> dict[str, str]:
        if not self.api_key:
            raise SotaOcrError(
                "SOTAOCR_API_KEY is not configured",
                code="missing_api_key",
            )
        return {"Authorization": f"Bearer {self.api_key}"}

    def _url(self, path: str, *, params: dict[str, Any] | None = None) -> str:
        url = f"{self.base_url}{path}"
        if params:
            query = urlencode({key: str(value) for key, value in params.items()})
            url = f"{url}?{query}"
        return url

    def _decode_response(
        self,
        status_code: int,
        body: str,
        *,
        action: str,
        expected: set[int],
    ) -> tuple[int, Any]:
        try:
            payload = json.loads(body) if body else None
        except json.JSONDecodeError as exc:
            raise SotaOcrError(
                f"{action}: invalid JSON response",
                status_code=status_code,
                payload=(body or "")[:500],
            ) from exc

        if status_code not in expected:
            raise _parse_api_error(status_code, payload, action)
        return status_code, payload

    def _curl_request_json(
        self,
        method: str,
        path: str,
        *,
        action: str,
        expected: set[int] | None = None,
        params: dict[str, Any] | None = None,
        data: dict[str, str] | None = None,
        files: dict[str, tuple[str, bytes, str]] | None = None,
    ) -> tuple[int, Any]:
        expected = expected or {200}
        curl = _find_curl_executable()
        if not curl:
            raise SotaOcrError(f"{action}: curl fallback is unavailable", code="curl_missing")

        url = self._url(path, params=params)
        timeout_sec = max(30, int(self.timeout_sec))
        cmd = [
            curl,
            "-sS",
            "--http1.1",
            "--max-time",
            str(timeout_sec),
            "-H",
            "Expect:",
            "-w",
            "\n__HTTP_CODE__%{http_code}",
        ]
        for key, value in self._headers().items():
            cmd.extend(["-H", f"{key}: {value}"])

        temp_paths: list[Path] = []
        try:
            if files:
                for field, (filename, content, mime) in files.items():
                    suffix = Path(filename).suffix or ".bin"
                    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
                    tmp.write(content)
                    tmp.close()
                    temp_paths.append(Path(tmp.name))
                    cmd.extend(["-F", f"{field}=@{tmp.name};type={mime};filename={filename}"])
            if data:
                for key, value in data.items():
                    cmd.extend(["-F", f"{key}={value}"])
            if method.upper() != "GET":
                cmd.extend(["-X", method.upper()])
            cmd.append(url)

            completed = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout_sec + 15,
                check=False,
                **hidden_subprocess_kwargs(),
            )
        finally:
            for path in temp_paths:
                path.unlink(missing_ok=True)

        if completed.returncode != 0:
            stderr = (completed.stderr or "").strip()
            raise SotaOcrError(
                f"{action}: curl transport failed ({stderr or completed.returncode})",
                code="curl_transport_error",
            )

        raw = completed.stdout or ""
        match = _CURL_HTTP_CODE_RE.search(raw)
        if not match:
            raise SotaOcrError(
                f"{action}: curl response missing HTTP status",
                payload=raw[:500],
            )
        status_code = int(match.group(1))
        body = raw[: match.start()].strip()
        return self._decode_response(status_code, body, action=action, expected=expected)

    def _sync_request_json(
        self,
        method: str,
        path: str,
        *,
        action: str,
        expected: set[int] | None = None,
        params: dict[str, Any] | None = None,
        data: dict[str, str] | None = None,
        files: dict[str, tuple[str, bytes, str]] | None = None,
        force_curl: bool = False,
    ) -> tuple[int, Any]:
        expected = expected or {200}
        url = self._url(path, params=params)
        timeout = (30.0, self.timeout_sec)

        def via_curl() -> tuple[int, Any]:
            return self._curl_request_json(
                method,
                path,
                action=action,
                expected=expected,
                params=params,
                data=data,
                files=files,
            )

        if force_curl:
            return via_curl()

        if self.prefer_curl and _find_curl_executable():
            try:
                return via_curl()
            except SotaOcrError as exc:
                if exc.code != "curl_transport_error":
                    raise
                logger.warning("%s: curl failed, retrying via requests", action)

        prepared_files: list[tuple[str, tuple[str, Any, str]]] | None = None
        if files:
            prepared_files = [
                (field, (filename, content, mime))
                for field, (filename, content, mime) in files.items()
            ]

        try:
            response = self._session.request(
                method,
                url,
                headers=self._headers(),
                data=data,
                files=prepared_files,
                timeout=timeout,
            )
        except requests.exceptions.Timeout as exc:
            raise SotaOcrError(f"{action}: request timed out") from exc
        except requests.exceptions.RequestException as exc:
            if _is_transient_network_error(exc) and _find_curl_executable():
                logger.warning("%s: requests failed, retrying via curl fallback", action)
                return via_curl()
            raise SotaOcrError(f"{action}: network error ({exc})") from exc

        body = response.text or ""
        return self._decode_response(
            response.status_code,
            body,
            action=action,
            expected=expected,
        )

    async def _request_json(
        self,
        method: str,
        path: str,
        *,
        action: str,
        expected: set[int] | None = None,
        **kwargs: Any,
    ) -> tuple[int, Any]:
        return await asyncio.to_thread(
            self._sync_request_json,
            method,
            path,
            action=action,
            expected=expected,
            **kwargs,
        )

    async def get_balance(self) -> SotaOcrBalance:
        _, payload = await self._request_json("GET", "/v1/balance", action="Balance")
        if not isinstance(payload, dict):
            raise SotaOcrError("Balance: unexpected payload", payload=payload)
        return SotaOcrBalance(
            remaining_pages=int(payload.get("remaining_pages") or 0),
            total_affordable_pages=int(payload.get("total_affordable_pages") or 0),
            raw=payload,
        )

    async def get_info(self) -> dict[str, Any]:
        _, payload = await self._request_json("GET", "/api/v1/info", action="Info")
        if not isinstance(payload, dict):
            raise SotaOcrError("Info: unexpected payload", payload=payload)
        return payload

    async def create_job(
        self,
        content: bytes,
        filename: str,
        *,
        page_ranges: list[dict[str, int]] | None = None,
        model_profile: str | None = None,
    ) -> SotaOcrJob:
        mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        data: dict[str, str] = {}
        profile = (model_profile or self.model_profile or "").strip()
        if profile:
            data["model_profile"] = profile
        if page_ranges:
            data["page_ranges"] = json.dumps(page_ranges, ensure_ascii=False)

        files = {"file": (filename, content, mime)}
        _, payload = await self._request_json(
            "POST",
            "/v1/extract",
            action="Upload",
            expected={200, 202},
            files=files,
            data=data or None,
        )
        job = _validate_job(payload, action="Upload")
        if not job.id:
            raise SotaOcrError("Upload: missing job id", payload=payload)
        return job

    async def get_job(self, job_id: str) -> SotaOcrJob:
        _, payload = await self._request_json(
            "GET",
            f"/v1/jobs/{job_id}",
            action="Job status",
        )
        return _validate_job(payload, action="Job status")

    async def wait_for_job(
        self,
        job_id: str,
        *,
        timeout_sec: float | None = None,
        poll_interval_sec: float | None = None,
    ) -> SotaOcrJob:
        deadline = asyncio.get_running_loop().time() + float(
            timeout_sec if timeout_sec is not None else self.timeout_sec
        )
        interval = max(
            1.0,
            float(poll_interval_sec if poll_interval_sec is not None else self.poll_interval_sec),
        )
        while True:
            job = await self.get_job(job_id)
            status = (job.status or "").lower()
            if status == "completed":
                return job
            if status in TERMINAL_FAILURES:
                raise SotaOcrError(
                    f"Job {job_id} ended with status {status}",
                    code=status,
                    payload=job.model_dump(),
                )
            if asyncio.get_running_loop().time() >= deadline:
                raise SotaOcrError(f"Timed out waiting for job {job_id}", code="timeout")
            await asyncio.sleep(interval)

    async def get_result(
        self,
        job_id: str,
        *,
        result_format: ResultFormat = "text",
    ) -> SotaOcrResult:
        status_code, payload = await self._request_json(
            "GET",
            f"/v1/jobs/{job_id}/result",
            action="Result fetch",
            expected={200, 202},
            params={"format": result_format},
        )
        if status_code == 202:
            raise _parse_api_error(status_code, payload, "Result fetch")
        return _validate_result(payload, action="Result fetch")

    async def extract_text(
        self,
        content: bytes,
        filename: str,
        *,
        result_format: ResultFormat = "text",
        page_ranges: list[dict[str, int]] | None = None,
        model_profile: str | None = None,
        wait: bool = True,
    ) -> tuple[SotaOcrJob, SotaOcrResult]:
        job = await self.create_job(
            content,
            filename,
            page_ranges=page_ranges,
            model_profile=model_profile,
        )
        if wait:
            await self.wait_for_job(job.id)
            result = await self.get_result(job.id, result_format=result_format)
            return job, result
        empty = SotaOcrResult(content="", format=result_format)
        return job, empty
