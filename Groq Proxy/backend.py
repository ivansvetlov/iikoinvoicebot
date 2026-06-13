"""LLM-only Grok backend — Grok thinks, Kilo executes tools."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass

from bridge_guards import (
    stderr_indicates_real_timeout,
    stderr_indicates_session_build_failure,
)
from response_pipeline import grok_wrapper_indicates_failure, unwrap_grok_cli_stdout_auto


def _env_flag(name: str, default: str = "0") -> bool:
    return (os.environ.get(name, default) or default).strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def passive_cli_mode() -> bool:
    """When enabled, grok-cli never gets write/exec permission (Kilo owns tools)."""
    return _env_flag("GROK_PASSIVE_CLI", "1")


def _get_acpx_path() -> str:
    candidates = [
        r"C:\Users\MiBookPro\AppData\Roaming\npm\acpx.cmd",
        "acpx.cmd",
        "acpx",
    ]
    for c in candidates:
        if os.path.exists(c) or shutil.which(c):
            return shutil.which(c) or c
    return "acpx.cmd"


def _get_grok_path() -> str:
    return shutil.which("grok") or "grok"


ACPX_PATH = _get_acpx_path()
GROK_PATH = _get_grok_path()


@dataclass
class BackendResult:
    stdout: str
    stderr: str
    returncode: int
    backend: str
    elapsed_s: float
    timed_out: bool = False


def _windows_popen_kwargs() -> dict:
    if sys.platform != "win32":
        return {}
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    si.wShowWindow = subprocess.SW_HIDE
    return {"startupinfo": si, "creationflags": subprocess.CREATE_NO_WINDOW}


def _kill_process_tree(pid: int) -> None:
    if pid <= 0:
        return
    try:
        if sys.platform == "win32":
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=10,
            )
        else:
            import signal

            os.kill(pid, signal.SIGTERM)
    except (OSError, subprocess.SubprocessError):
        pass


def _run_subprocess(cmd: list[str], timeout: int, cwd: str | None = None) -> BackendResult:
    import time

    t0 = time.time()
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=cwd,
        **_windows_popen_kwargs(),
    )
    timed_out = False
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
        return BackendResult(
            stdout=stdout or "",
            stderr=stderr or "",
            returncode=proc.returncode,
            backend="subprocess",
            elapsed_s=round(time.time() - t0, 2),
            timed_out=False,
        )
    except subprocess.TimeoutExpired:
        timed_out = True
        _kill_process_tree(proc.pid)
        try:
            proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            pass
        return BackendResult(
            stdout="",
            stderr=f"timeout after {timeout}s",
            returncode=-1,
            backend="subprocess",
            elapsed_s=round(time.time() - t0, 2),
            timed_out=True,
        )


def _has_useful_output(stdout: str) -> bool:
    if not stdout or not stdout.strip():
        return False
    text = stdout.strip()
    if text.startswith("{"):
        try:
            obj = json.loads(text)
        except json.JSONDecodeError:
            pass
        else:
            if isinstance(obj, dict):
                parse_text, meta = unwrap_grok_cli_stdout_auto(text)
                if grok_wrapper_indicates_failure(meta, parse_text):
                    return False
                if (parse_text or "").strip():
                    return True
                if obj.get("tool_calls") or obj.get("content"):
                    return True
        try:
            json.loads(text)
            return True
        except json.JSONDecodeError:
            pass
    lines = [l.strip() for l in stdout.splitlines() if l.strip()]
    non_meta = [
        l for l in lines
        if not l.startswith(("[client]", "[thinking]", "[done]"))
    ]
    return bool(non_meta)


def invoke_acpx_llm(prompt: str, timeout: int = 90) -> BackendResult:
    """Passive LLM via acpx: no native agent tools, single turn."""
    prompt_file = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", suffix=".txt", delete=False
        ) as tf:
            tf.write(prompt)
            prompt_file = tf.name

        cmd = [
            ACPX_PATH,
            "--allowed-tools",
            "",
            "--max-turns",
            "1",
            "exec",
            "grok",
            "-f",
            prompt_file,
        ]
        result = _run_subprocess(cmd, timeout=timeout)
        result.backend = "acpx-llm"
        return result
    finally:
        if prompt_file:
            try:
                os.unlink(prompt_file)
            except OSError:
                pass


def _grok_output_format() -> str:
    fmt = (os.environ.get("GROK_OUTPUT_FORMAT") or "plain").strip().lower()
    if fmt in ("plain", "json", "streaming-json"):
        return fmt
    return "plain"


def _passive_permission_mode() -> str | None:
    """plan mode breaks session creation on some grok-cli builds; use dontAsk."""
    explicit = (os.environ.get("GROK_CLI_PERMISSION") or "").strip()
    if explicit:
        return explicit
    if passive_cli_mode():
        return "dontAsk"
    return None


def _effective_permission_mode(permission_mode: str | None) -> str | None:
    if passive_cli_mode():
        return _passive_permission_mode()
    return permission_mode


def invoke_grok_cli_llm(
    prompt: str,
    timeout: int = 90,
    *,
    output_format: str | None = None,
    resume_session_id: str | None = None,
    permission_mode: str | None = None,
) -> BackendResult:
    """Passive LLM via grok --prompt-file (clean JSON stdout)."""
    fmt = output_format or _grok_output_format()
    mode = _effective_permission_mode(permission_mode)
    prompt_file = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", suffix=".txt", delete=False
        ) as tf:
            tf.write(prompt)
            prompt_file = tf.name

        cmd = [
            GROK_PATH,
            "--prompt-file",
            prompt_file,
            "--max-turns",
            "1",
            "--output-format",
            fmt,
        ]
        if resume_session_id:
            cmd.extend(["--resume", resume_session_id])
        if mode:
            cmd.extend(["--permission-mode", mode])
        disallowed = (os.environ.get("GROK_DISALLOW_TOOLS") or "").strip()
        if disallowed:
            cmd.extend(["--disallowed-tools", disallowed])
        result = _run_subprocess(
            cmd,
            timeout=timeout,
            cwd=os.path.dirname(os.path.abspath(__file__)),
        )
        backend_tag = f"grok-cli:{fmt}"
        if resume_session_id:
            backend_tag += ":resume"
        if mode:
            backend_tag += f":{mode}"
        result.backend = backend_tag
        return result
    finally:
        if prompt_file:
            try:
                os.unlink(prompt_file)
            except OSError:
                pass


def _stderr_builtin_leak(stderr: str | None) -> bool:
    low = (stderr or "").lower()
    markers = (
        "tool_error",
        "grok-build",
        "search_replace",
        "update_goal",
        "execution_failure",
        "tool_output_error",
    )
    return any(m in low for m in markers)


def _stderr_hard_failure(stderr: str | None) -> bool:
    low = (stderr or "").lower()
    return "max turns" in low or _stderr_builtin_leak(stderr)


def is_backend_failure(result: BackendResult) -> bool:
    if result.timed_out:
        return True
    if stderr_indicates_real_timeout(result.stderr):
        return True
    if stderr_indicates_session_build_failure(result.stderr):
        return True
    err = (result.stderr or "").lower()
    if _stderr_hard_failure(result.stderr):
        return True
    if "max turns" in err:
        return True
    parse_text, meta = unwrap_grok_cli_stdout_auto(result.stdout or "")
    if grok_wrapper_indicates_failure(meta, parse_text):
        return True
    if _has_useful_output(result.stdout):
        return False
    if result.returncode != 0:
        return True
    return False


def invoke_grok_llm(
    prompt: str,
    timeout: int = 120,
    *,
    resume_session_id: str | None = None,
    permission_mode: str | None = None,
) -> BackendResult:
    """Primary: grok CLI only (fast, clean JSON). No acpx fallback in Kilo path."""
    fmt = _grok_output_format()
    result = invoke_grok_cli_llm(
        prompt,
        timeout=timeout,
        output_format=fmt,
        resume_session_id=resume_session_id,
        permission_mode=permission_mode,
    )
    if fmt == "json" and is_backend_failure(result) and not _stderr_hard_failure(result.stderr):
        plain = invoke_grok_cli_llm(
            prompt,
            timeout=timeout,
            output_format="plain",
            resume_session_id=resume_session_id,
            permission_mode=permission_mode,
        )
        if not is_backend_failure(plain):
            plain.backend = "grok-cli:plain-fallback"
            return plain
    return result
