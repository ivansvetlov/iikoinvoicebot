from __future__ import annotations

from pathlib import Path
import subprocess
from typing import Literal

from mcp.server.fastmcp import FastMCP


app = FastMCP(
    name="Termux Bridge MCP",
    instructions=(
        "Execute local host commands for remote terminal workflows and return "
        "stdout/stderr/exit_code."
    ),
)


def _normalize_timeout(timeout_sec: int) -> int:
    if timeout_sec < 1:
        return 1
    if timeout_sec > 600:
        return 600
    return timeout_sec


@app.tool(
    name="run_command",
    description=(
        "Run a host command and return stdout/stderr/exit_code. "
        "Default shell is PowerShell."
    ),
)
def run_command(
    command: str,
    cwd: str | None = None,
    shell: Literal["powershell", "cmd"] = "powershell",
    timeout_sec: int = 120,
) -> dict:
    command = (command or "").strip()
    if not command:
        return {
            "ok": False,
            "error": "Empty command",
            "stdout": "",
            "stderr": "",
            "exit_code": 2,
            "cwd": str(Path.cwd()),
            "shell": shell,
        }

    workdir = Path(cwd).expanduser().resolve() if cwd else Path.cwd()
    timeout = _normalize_timeout(timeout_sec)

    if shell == "cmd":
        argv = ["cmd.exe", "/d", "/c", command]
    else:
        prelude = (
            "chcp 65001 > $null; "
            "[Console]::InputEncoding=[System.Text.UTF8Encoding]::new($false); "
            "[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new($false); "
            "$OutputEncoding=[Console]::OutputEncoding; "
        )
        argv = [
            "powershell.exe",
            "-NoLogo",
            "-NoProfile",
            "-Command",
            prelude + command,
        ]

    try:
        proc = subprocess.run(
            argv,
            cwd=str(workdir),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        return {
            "ok": proc.returncode == 0,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "exit_code": proc.returncode,
            "cwd": str(workdir),
            "shell": shell,
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "ok": False,
            "error": f"Command timed out after {timeout}s",
            "stdout": (exc.stdout or ""),
            "stderr": (exc.stderr or ""),
            "exit_code": 124,
            "cwd": str(workdir),
            "shell": shell,
        }
    except Exception as exc:
        return {
            "ok": False,
            "error": f"{type(exc).__name__}: {exc}",
            "stdout": "",
            "stderr": "",
            "exit_code": 1,
            "cwd": str(workdir),
            "shell": shell,
        }


if __name__ == "__main__":
    app.run(transport="stdio")

