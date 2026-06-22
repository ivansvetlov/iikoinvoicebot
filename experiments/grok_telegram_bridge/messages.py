"""Single place for Grok bridge user-facing texts (Telegram + MAX)."""
from __future__ import annotations

from experiments.grok_telegram_bridge.git_snapshot import GitSnapshot
from experiments.grok_telegram_bridge.session_store import UserSession


class BridgeMsg:
    ACCESS_DENIED = "Access denied."
    CALLBACK_OK = "OK"
    UNKNOWN_BUTTON = "Неизвестная кнопка"
    NEW_SESSION = "Новая сессия. Bootstrap при первом текстовом запросе."
    CHECK_MODE = (
        "Режим <b>check</b>. Отправь текст задачи — добавлю тестировщика (--check)."
    )
    DEFAULT_CHECK_PROMPT = "Проверь последние изменения в проекте."
    GROK_RUNNING = "⏳ Grok…"
    EMPTY_RESPONSE = "(пустой ответ)"
    DASHBOARD_OK = "Дашборд обновлён."
    DASHBOARD_FAIL = "Не удалось: {note}"

    HANDOFF_TG = "data/private/grok_bridge/HANDOFF_LATEST.md"
    HANDOFF_MAX = "data/private/grok_max_bridge/HANDOFF_LATEST.md"

    @staticmethod
    def help_text(*, channel: str) -> str:
        if channel == "max":
            channel_line = "на твоём ПК (канал MAX)."
            handoff = BridgeMsg.HANDOFF_MAX
        else:
            channel_line = "на твоём ПК."
            handoff = BridgeMsg.HANDOFF_TG
        return (
            f"<b>Grok Bridge</b> — удалённый терминальный агент {channel_line}\n\n"
            "Используй <b>кнопки ниже</b> или текстовые команды.\n"
            "Первый запрос после /new — bootstrap. "
            "Дашборд: <code>docs/assets/project-dashboard.html</code>\n\n"
            "<b>Текст</b> → <code>grok -p</code> + <code>--resume</code> + метапромпт.\n"
            f"Результаты пишутся в <code>{handoff}</code> для Cursor дома."
        )

    @staticmethod
    def yolo_hint(current: bool) -> str:
        return f"YOLO: <b>{current}</b>. Кнопки или /yolo on|off"

    @staticmethod
    def yolo_set(value: bool) -> str:
        return f"YOLO: <b>{value}</b>"

    @staticmethod
    def context_block(preview: str) -> str:
        return f"<b>Контекст</b>\n<pre>{preview}</pre>"

    @staticmethod
    def journal_block(preview: str) -> str:
        return f"<b>Журнал</b>\n<pre>{preview}</pre>"

    @staticmethod
    def metrics_block(text: str) -> str:
        return f"<b>Метрики</b>\n<pre>{text}</pre>"

    @staticmethod
    def reports_block(text: str, dashboard_path: str) -> str:
        return (
            f"<b>Отчёты</b>\n<pre>{text}</pre>\n\n"
            f"Полный вид: <code>{dashboard_path}</code>"
        )

    @staticmethod
    def dashboard_block(*, ok: bool, note: str, path: str, summary: str) -> str:
        status = "обновлён" if ok else f"ошибка: {note}"
        return (
            f"<b>Project Dashboard</b> ({status})\n"
            f"<code>{path}</code>\n\n<pre>{summary}</pre>"
        )

    @staticmethod
    def dash_refresh_block(*, ok: bool, note: str, path: str) -> str:
        text = BridgeMsg.DASHBOARD_OK if ok else BridgeMsg.DASHBOARD_FAIL.format(note=note)
        return f"<b>HTML</b>\n{text}\n<code>{path}</code>"

    @staticmethod
    def grok_running(*, use_check: bool, do_bootstrap: bool) -> str:
        suffix = ""
        if use_check:
            suffix += " + check"
        if do_bootstrap:
            suffix += " + bootstrap"
        return BridgeMsg.GROK_RUNNING + suffix

    @staticmethod
    def grok_error(exc: str) -> str:
        return f"❌ <b>Grok error</b>\n<pre>{exc}</pre>"

    @staticmethod
    def status_lines(
        *,
        cwd: str,
        git: GitSnapshot,
        model: str,
        sess: UserSession,
        yolo: bool,
        has_rules: bool,
    ) -> list[str]:
        bootstrap = "done" if sess.meta.get("bootstrap_done") else "pending"
        return [
            f"<b>cwd</b>: <code>{cwd}</code>",
            f"<b>git</b>: <code>{git.branch}</code> · dirty: {git.dirty_count}",
            f"<b>model</b>: <code>{model}</code>",
            f"<b>grok session</b>: <code>{sess.grok_session_id or '(new)'}</code>",
            f"<b>messages</b>: {sess.message_count}",
            f"<b>bootstrap</b>: {bootstrap}",
            f"<b>yolo</b>: {yolo}",
            f"<b>metaprompt</b>: {'yes' if has_rules else 'no'}",
        ]
