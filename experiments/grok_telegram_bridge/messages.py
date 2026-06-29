"""Single place for Grok bridge user-facing texts (Telegram + MAX)."""
from __future__ import annotations

from experiments.grok_telegram_bridge.git_snapshot import GitSnapshot
from experiments.grok_telegram_bridge.session_store import UserSession


class BridgeMsg:
    ACCESS_DENIED = "Access denied."
    CALLBACK_OK = "OK"
    UNKNOWN_BUTTON = "Неизвестная кнопка"
    NEW_SESSION = "🆕 Новая сессия. Очищен контекст bridge. Следующий запрос — с bootstrap."
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

    COMMANDS: tuple[tuple[str, str], ...] = (
        ("/help", "меню и справка"),
        ("/start", "то же, что /help (MAX)"),
        ("/new", "новая сессия Grok"),
        ("/status", "cwd, git, модель, bootstrap"),
        ("/yolo on|off", "авто-approve инструментов"),
        ("/check", "режим верификации (--check)"),
        ("/verify", "алиас /check"),
    )

    @staticmethod
    def commands_text(*, channel: str = "max") -> str:
        lines = ["<b>Команды:</b>"]
        for cmd, desc in BridgeMsg.COMMANDS:
            if channel != "max" and cmd == "/start":
                continue
            lines.append(f"• <code>{cmd}</code> — {desc}")
        if channel == "max":
            lines.append(
                "\n<i>В клиенте MAX подсказка при вводе <code>/</code> может быть пустой — "
                "это ограничение платформы. Отправь <code>/help</code> или кнопку «Справка».</i>"
            )
        return "\n".join(lines)

    @staticmethod
    def unknown_command(cmd: str) -> str:
        return (
            f"Неизвестная команда <code>/{cmd}</code>.\n\n"
            f"{BridgeMsg.commands_text()}"
        )

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
            f"Результаты пишутся в <code>{handoff}</code> для Cursor дома.\n\n"
            f"{BridgeMsg.commands_text(channel=channel)}"
        )

    @staticmethod
    def yolo_hint(current: bool) -> str:
        return f"YOLO: <b>{current}</b>. Кнопки или /yolo on|off"

    @staticmethod
    def yolo_set(value: bool) -> str:
        return f"YOLO: <b>{value}</b>"

    @staticmethod
    def context_block(preview: str) -> str:
        return preview

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
            f"🖥️ <b>Дашборд</b> ({status})\n\n"
            f"Открывай файл:\n<code>{path}</code>\n\n"
            f"<i>Обновлено только что.</i>"
        )

    @staticmethod
    def dashboard_link(*, ok: bool, note: str, url: str) -> str:
        status = "обновлён" if ok else f"ошибка: {note}"
        return (
            f"🖥️ <b>Дашборд</b> ({status})\n\n"
            f"Открой в браузере:\n<a href=\"{url}\">{url}</a>\n\n"
            f"<i>С телефона: Tailscale включён или та же Wi‑Fi. Сервер: "
            f"<code>scripts/serve_project_dashboard.py</code></i>"
        )

    @staticmethod
    def dash_refresh_block(*, ok: bool, note: str, path: str) -> str:
        text = BridgeMsg.DASHBOARD_OK if ok else BridgeMsg.DASHBOARD_FAIL.format(note=note)
        return f"🔄 Дашборд: {text}\n<code>{path}</code>"

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
    def handoff_compact(path: str) -> str:
        """Compact handoff info instead of dumping the whole file."""
        return (
            "🏠 <b>Handoff для Cursor</b>\n\n"
            f"Файл: <code>{path}</code>\n\n"
            "1. Открой его дома\n"
            "2. `git status` + смотри последние runs/\n"
            "3. Продолжай работу"
        )

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
