"""Фоновое обновление grok chat dump после bridge-run."""

from __future__ import annotations

import logging
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


def refresh_chat_dump(project_root: Path) -> tuple[bool, str]:
    script = project_root / "scripts" / "export_grok_chat_dump.py"
    if not script.exists():
        return False, "export script missing"
    try:
        proc = subprocess.run(
            [sys.executable, str(script)],
            cwd=str(project_root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=120,
            check=False,
        )
    except Exception as exc:
        logger.warning("chat dump export failed: %s", exc)
        return False, str(exc)

    out = (proc.stdout or "").strip() or (proc.stderr or "").strip()
    if proc.returncode != 0:
        logger.warning("chat dump export rc=%s: %s", proc.returncode, out)
        return False, out or f"exit {proc.returncode}"
    return True, out or "ok"
