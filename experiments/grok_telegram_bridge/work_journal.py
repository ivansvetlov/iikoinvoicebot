"""Remote work journal: bridge ↔ Cursor handoff."""
from __future__ import annotations

import json
import threading
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from experiments.grok_telegram_bridge.git_snapshot import GitSnapshot, capture


@dataclass
class RunRecord:
    run_id: str
    user_id: int
    started_at: str
    finished_at: str
    prompt_preview: str
    response_preview: str
    grok_session_id: str | None
    stop_reason: str | None
    duration_sec: float
    use_check: bool
    git_branch: str
    git_dirty: int
    git_diff_stat: str


class WorkJournal:
    def __init__(self, base_dir: Path) -> None:
        self._base = base_dir
        self._lock = threading.Lock()
        self._journal = base_dir / "journal.jsonl"
        self._handoff = base_dir / "HANDOFF_LATEST.md"
        self._runs = base_dir / "runs"
        self._base.mkdir(parents=True, exist_ok=True)
        self._runs.mkdir(parents=True, exist_ok=True)

    def new_run_id(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:8]

    def record_run(
        self,
        *,
        user_id: int,
        run_id: str,
        started_at: datetime,
        finished_at: datetime,
        prompt: str,
        response: str,
        grok_session_id: str | None,
        stop_reason: str | None,
        use_check: bool,
        git_before: GitSnapshot,
        git_after: GitSnapshot,
        cwd: Path,
    ) -> RunRecord:
        duration = (finished_at - started_at).total_seconds()
        rec = RunRecord(
            run_id=run_id,
            user_id=user_id,
            started_at=started_at.isoformat(),
            finished_at=finished_at.isoformat(),
            prompt_preview=(prompt or "")[:500],
            response_preview=(response or "")[:800],
            grok_session_id=grok_session_id,
            stop_reason=stop_reason,
            duration_sec=round(duration, 1),
            use_check=use_check,
            git_branch=git_after.branch,
            git_dirty=git_after.dirty_count,
            git_diff_stat=git_after.diff_stat[:2000],
        )
        run_dir = self._runs / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "meta.json").write_text(
            json.dumps(asdict(rec), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (run_dir / "prompt.txt").write_text(prompt or "", encoding="utf-8")
        (run_dir / "response.txt").write_text(response or "", encoding="utf-8")
        (run_dir / "git_before.json").write_text(
            json.dumps(asdict(git_before), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (run_dir / "git_after.json").write_text(
            json.dumps(asdict(git_after), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        diff = _git_diff(cwd)
        if diff:
            (run_dir / "git_diff.patch").write_text(diff, encoding="utf-8")

        with self._lock:
            with self._journal.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(asdict(rec), ensure_ascii=False) + "\n")
            self._refresh_handoff(rec)

        return rec

    def _refresh_handoff(self, latest: RunRecord) -> None:
        lines = [
            "# HANDOFF_LATEST — remote Grok bridge",
            "",
            f"> Автообновлено: {latest.finished_at}",
            "> **Cursor:** прочитай этот файл первым после работы из Telegram.",
            "",
            "## Последний run",
            f"- **run_id:** `{latest.run_id}`",
            f"- **branch:** `{latest.git_branch}` · dirty: {latest.git_dirty}",
            f"- **duration:** {latest.duration_sec}s · check: {latest.use_check}",
            f"- **grok session:** `{latest.grok_session_id or '(none)'}`",
            "",
            "### Запрос",
            "```",
            latest.prompt_preview,
            "```",
            "",
            "### Ответ (preview)",
            "```",
            latest.response_preview,
            "```",
            "",
            "### Git diff stat",
            "```",
            latest.git_diff_stat or "(no diff)",
            "```",
            "",
            "## Для Cursor",
            "1. `git status` и diff по `data/private/grok_bridge/runs/`",
            "2. Полный ответ: `runs/<run_id>/response.txt`",
            "3. Журнал: `journal.jsonl`",
            "",
        ]
        recent = self.recent_runs(5)
        if len(recent) > 1:
            lines.append("## Предыдущие runs")
            for r in recent[1:]:
                lines.append(
                    f"- `{r.run_id}` · {r.finished_at[:16]} · dirty={r.git_dirty} · "
                    f"{r.prompt_preview[:60]}…"
                )
            lines.append("")

        self._handoff.write_text("\n".join(lines), encoding="utf-8")

    def recent_runs(self, limit: int = 10) -> list[RunRecord]:
        if not self._journal.exists():
            return []
        rows: list[RunRecord] = []
        for raw in self._journal.read_text(encoding="utf-8").splitlines():
            if not raw.strip():
                continue
            try:
                data = json.loads(raw)
                rows.append(RunRecord(**data))
            except Exception:
                continue
        return list(reversed(rows[-limit:]))

    def handoff_text(self, max_chars: int = 3500) -> str:
        if self._handoff.exists():
            text = self._handoff.read_text(encoding="utf-8").strip()
            if len(text) > max_chars:
                return text[: max_chars - 20] + "\n…(truncated)"
            return text
        return "HANDOFF_LATEST.md ещё нет. Выполни задачу через bridge."

    def journal_preview(self, limit: int = 5) -> str:
        runs = self.recent_runs(limit)
        if not runs:
            return "Журнал пуст."
        lines = []
        for r in runs:
            lines.append(
                f"• {r.finished_at[:16]} | {r.run_id} | dirty={r.git_dirty} | "
                f"{r.prompt_preview[:50]}…"
            )
        return "\n".join(lines)


def _git_diff(cwd: Path) -> str:
    from experiments.grok_telegram_bridge.git_snapshot import _run

    return _run(["git", "diff"], cwd)
