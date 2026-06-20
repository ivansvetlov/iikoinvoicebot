"""Git status/diff snapshots for remote handoff."""
from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class GitSnapshot:
    branch: str
    status_short: str
    diff_stat: str
    dirty_count: int


def _run(cmd: list[str], cwd: Path) -> str:
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
        )
        return (proc.stdout or proc.stderr or "").strip()
    except Exception as exc:
        return f"(git error: {exc})"


def capture(cwd: Path) -> GitSnapshot:
    branch = _run(["git", "branch", "--show-current"], cwd) or "(no branch)"
    status = _run(["git", "status", "--short"], cwd)
    diff_stat = _run(["git", "diff", "--stat"], cwd)
    if not diff_stat:
        diff_stat = _run(["git", "diff", "--cached", "--stat"], cwd)
    dirty = len([ln for ln in status.splitlines() if ln.strip()]) if status else 0
    return GitSnapshot(branch=branch, status_short=status, diff_stat=diff_stat, dirty_count=dirty)
