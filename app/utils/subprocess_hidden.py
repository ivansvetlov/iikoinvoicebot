"""Hidden subprocess helpers (Windows: no flashing console windows)."""

from __future__ import annotations

import os
import subprocess
from typing import Any


def hidden_subprocess_kwargs() -> dict[str, Any]:
    """Extra kwargs for subprocess.run/Popen so console tools stay invisible on Windows."""
    if os.name != "nt":
        return {}
    kwargs: dict[str, Any] = {}
    no_window = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    if no_window:
        kwargs["creationflags"] = no_window
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    si.wShowWindow = subprocess.SW_HIDE
    kwargs["startupinfo"] = si
    return kwargs


def run_hidden(
    args: list[str],
    *,
    timeout: int | float | None = None,
    capture_output: bool = True,
    text: bool = False,
    check: bool = False,
    **extra: Any,
) -> subprocess.CompletedProcess[Any]:
    return subprocess.run(
        args,
        timeout=timeout,
        check=check,
        capture_output=capture_output,
        text=text,
        **hidden_subprocess_kwargs(),
        **extra,
    )