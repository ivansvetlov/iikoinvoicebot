"""LLM-only Grok backend — Grok thinks, Kilo executes tools."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass


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


def _windows_popen_kwargs() -> dict:
    if sys.platform != "win32":
        return {}
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    si.wShowWindow = subprocess.SW_HIDE
    return {"startupinfo": si, "creationflags": subprocess.CREATE_NO_WINDOW}


def _has_useful_output(stdout: str) -> bool:
    if not stdout or not stdout.strip():
        return False
    text = stdout.strip()
    if text.startswith("{"):
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
    import time

    prompt_file = None
    t0 = time.time()
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
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            **_windows_popen_kwargs(),
        )
        return BackendResult(
            stdout=proc.stdout or "",
            stderr=proc.stderr or "",
            returncode=proc.returncode,
            backend="acpx-llm",
            elapsed_s=round(time.time() - t0, 2),
        )
    finally:
        if prompt_file:
            try:
                os.unlink(prompt_file)
            except OSError:
                pass


def invoke_grok_cli_llm(prompt: str, timeout: int = 90) -> BackendResult:
    """Passive LLM via grok --prompt-file (clean JSON stdout)."""
    import time

    prompt_file = None
    t0 = time.time()
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
            "8",
            "--output-format",
            "plain",
        ]
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            cwd=os.path.dirname(os.path.abspath(__file__)),
            **_windows_popen_kwargs(),
        )
        return BackendResult(
            stdout=proc.stdout or "",
            stderr=proc.stderr or "",
            returncode=proc.returncode,
            backend="grok-cli",
            elapsed_s=round(time.time() - t0, 2),
        )
    finally:
        if prompt_file:
            try:
                os.unlink(prompt_file)
            except OSError:
                pass


def is_backend_failure(result: BackendResult) -> bool:
    err = (result.stderr or "").lower()
    if "timeout" in err:
        return True
    # grok-cli may exit non-zero while still returning valid JSON on stdout.
    if _has_useful_output(result.stdout):
        return False
    if result.returncode != 0:
        return True
    return "max turns" in err


def invoke_grok_llm(prompt: str, timeout: int = 120) -> BackendResult:
    """Primary: grok CLI only (fast, clean JSON). No acpx fallback in Kilo path."""
    return invoke_grok_cli_llm(prompt, timeout=timeout)
