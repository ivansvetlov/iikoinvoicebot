"""Invoke local Grok CLI in headless mode (terminal-parity)."""
from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path

ProgressCallback = Callable[[str, str], Awaitable[None]]


@dataclass
class GrokResult:
    text: str
    session_id: str | None
    stop_reason: str | None
    raw_events: int = 0


class GrokRunnerError(RuntimeError):
    pass


class GrokRunner:
    def __init__(
        self,
        *,
        cli_path: Path,
        cwd: Path,
        model: str,
        max_turns: int,
        timeout_sec: int,
        yolo: bool,
        stream: bool,
    ) -> None:
        self.cli_path = cli_path
        self.cwd = cwd
        self.model = model
        self.max_turns = max_turns
        self.timeout_sec = timeout_sec
        self.yolo = yolo
        self.stream = stream

    def _build_cmd(
        self,
        prompt: str,
        *,
        session_id: str | None,
        use_check: bool,
    ) -> list[str]:
        fmt = "streaming-json" if self.stream else "json"
        cmd = [
            str(self.cli_path),
            "-p",
            prompt,
            "--cwd",
            str(self.cwd),
            "-m",
            self.model,
            "--output-format",
            fmt,
            "--max-turns",
            str(self.max_turns),
            "--no-auto-update",
        ]
        if session_id:
            cmd.extend(["--resume", session_id])
        if self.yolo:
            cmd.append("--always-approve")
        if use_check:
            cmd.append("--check")
        return cmd

    async def run(
        self,
        prompt: str,
        *,
        session_id: str | None = None,
        use_check: bool = False,
        on_progress: ProgressCallback | None = None,
    ) -> GrokResult:
        if not self.cli_path.exists():
            raise GrokRunnerError(f"Grok CLI not found: {self.cli_path}")

        cmd = self._build_cmd(prompt, session_id=session_id, use_check=use_check)
        env = {**os.environ, "GROK_DISABLE_AUTOUPDATER": "1"}

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(self.cwd),
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            if self.stream:
                return await asyncio.wait_for(
                    self._consume_stream(proc, on_progress),
                    timeout=self.timeout_sec,
                )
            return await asyncio.wait_for(
                self._consume_json(proc),
                timeout=self.timeout_sec,
            )
        except asyncio.TimeoutError as exc:
            proc.kill()
            raise GrokRunnerError(f"Grok timeout ({self.timeout_sec}s)") from exc
        finally:
            await proc.wait()

    async def _consume_json(self, proc: asyncio.subprocess.Process) -> GrokResult:
        stdout, stderr = await proc.communicate()
        if proc.returncode not in (0, None):
            err_tail = (stderr or b"").decode(errors="replace")[-500:]
            raise GrokRunnerError(f"Grok exit {proc.returncode}: {err_tail}")

        raw = (stdout or b"").decode(errors="replace").strip()
        if not raw:
            raise GrokRunnerError("Empty Grok output")

        # stdout may contain log lines before JSON — take last JSON object line
        data = None
        for line in reversed(raw.splitlines()):
            line = line.strip()
            if line.startswith("{"):
                try:
                    data = json.loads(line)
                    break
                except json.JSONDecodeError:
                    continue
        if data is None:
            try:
                data = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise GrokRunnerError(f"Invalid JSON from Grok: {raw[:200]}") from exc

        if data.get("type") == "error":
            raise GrokRunnerError(data.get("message", "Grok error"))

        return GrokResult(
            text=(data.get("text") or "").strip(),
            session_id=data.get("sessionId"),
            stop_reason=data.get("stopReason"),
        )

    @staticmethod
    def parse_stream_lines(lines: list[str]) -> GrokResult:
        """Parse NDJSON stream events (for tests and _consume_stream)."""
        text_parts: list[str] = []
        session_id: str | None = None
        stop_reason: str | None = None
        events = 0

        for raw in lines:
            raw = raw.strip()
            if not raw:
                continue
            events += 1
            try:
                event = json.loads(raw)
            except json.JSONDecodeError:
                continue

            etype = event.get("type")
            if etype == "text":
                text_parts.append(event.get("data") or "")
            elif etype == "error":
                raise GrokRunnerError(event.get("message", "Grok stream error"))
            elif etype == "end":
                session_id = event.get("sessionId")
                stop_reason = event.get("stopReason")

        return GrokResult(
            text="".join(text_parts).strip(),
            session_id=session_id,
            stop_reason=stop_reason,
            raw_events=events,
        )

    async def _consume_stream(
        self,
        proc: asyncio.subprocess.Process,
        on_progress: ProgressCallback | None,
    ) -> GrokResult:
        assert proc.stdout is not None
        text_parts: list[str] = []
        session_id: str | None = None
        stop_reason: str | None = None
        events = 0
        last_notify = 0.0

        while True:
            line = await proc.stdout.readline()
            if not line:
                break
            events += 1
            try:
                event = json.loads(line.decode(errors="replace"))
            except json.JSONDecodeError:
                continue

            etype = event.get("type")
            if etype == "text":
                chunk = event.get("data") or ""
                text_parts.append(chunk)
                if on_progress:
                    now = asyncio.get_running_loop().time()
                    if now - last_notify >= 2.0:
                        await on_progress("".join(text_parts), "streaming")
                        last_notify = now
            elif etype == "thought" and on_progress:
                now = asyncio.get_running_loop().time()
                if now - last_notify >= 4.0:
                    await on_progress("".join(text_parts), "thinking")
                    last_notify = now
            elif etype == "error":
                raise GrokRunnerError(event.get("message", "Grok stream error"))
            elif etype == "end":
                session_id = event.get("sessionId")
                stop_reason = event.get("stopReason")
                if on_progress:
                    await on_progress("".join(text_parts), "done")

        await proc.wait()
        if proc.returncode not in (0, None):
            stderr = (await proc.stderr.read() if proc.stderr else b"").decode(errors="replace")
            raise GrokRunnerError(f"Grok exit {proc.returncode}: {stderr[-400:]}")

        return GrokResult(
            text="".join(text_parts).strip(),
            session_id=session_id,
            stop_reason=stop_reason,
            raw_events=events,
        )
