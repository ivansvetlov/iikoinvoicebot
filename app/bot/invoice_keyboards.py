"""Shared inline keyboards for post-recognition invoice actions."""

from __future__ import annotations

from typing import Any

from app.bot.messages import Msg

TRANSIENT_RETRY_ERROR_CODES = frozenset(
    {
        "llm_unavailable",
        "llm_timeout",
        "llm_bad_response",
        "worker_unhandled_exception",
        "backend_unavailable",
    }
)


def _button(text: str, callback_data: str, *, style: str | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"text": text, "callback_data": callback_data}
    if style:
        payload["style"] = style
    return payload


def build_invoice_actions(
    request_id: str | None,
    *,
    allow_send: bool = True,
    allow_sync: bool = True,
    allow_service: bool = True,
) -> dict[str, Any] | None:
    if not request_id:
        return None

    first_row = [_button(Msg.BTN_INV_EDIT, f"inv:edit:{request_id}", style="primary")]
    if allow_send:
        first_row.append(_button(Msg.BTN_INV_SEND, f"inv:send:{request_id}", style="success"))

    rows: list[list[dict[str, Any]]] = [first_row]
    if allow_sync:
        rows.append([_button(Msg.BTN_INV_SYNC, f"inv:syncnom:{request_id}", style="primary")])

    bottom_row: list[dict[str, Any]] = []
    if allow_service:
        bottom_row.append(_button(Msg.BTN_INV_SERVICE, f"inv:service:{request_id}", style="default"))
    bottom_row.append(_button(Msg.BTN_BACK, f"inv:cancel:{request_id}", style="danger"))
    rows.append(bottom_row)
    return {"inline_keyboard": rows}


def build_retry_actions(request_id: str | None, error_code: str | None) -> dict[str, Any] | None:
    if not request_id:
        return None
    if str(error_code or "").strip().lower() not in TRANSIENT_RETRY_ERROR_CODES:
        return None
    return {
        "inline_keyboard": [
            [_button(Msg.BTN_RETRY, f"inv:retry:{request_id}", style="primary")],
        ]
    }


def build_sync_confirm_actions(request_id: str) -> dict[str, Any]:
    return {
        "inline_keyboard": [
            [
                _button(Msg.BTN_SYNC_RUN, f"inv:syncnomconfirm:{request_id}", style="success"),
                _button(Msg.BTN_BACK, f"inv:back:{request_id}", style="default"),
            ],
        ]
    }


def build_posting_review_actions(
    request_id: str,
    *,
    can_confirm: bool,
) -> dict[str, Any]:
    rows: list[list[dict[str, Any]]] = [
        [_button(Msg.BTN_REFRESH_UNITS, f"inv:refreshunits:{request_id}", style="primary")],
    ]
    if can_confirm:
        rows.append([_button(Msg.BTN_POST_CONFIRM, f"inv:postconfirm:{request_id}", style="success")])
    rows.append([_button(Msg.BTN_BACK, f"inv:back:{request_id}", style="default")])
    return {"inline_keyboard": rows}


def build_back_confirm_actions(request_id: str) -> dict[str, Any]:
    return {
        "inline_keyboard": [
            [
                _button(Msg.BTN_YES_BACK, f"inv:backconfirm:{request_id}", style="success"),
                _button(Msg.BTN_STAY, f"inv:back:{request_id}:stay", style="default"),
            ],
        ]
    }


def build_service_menu_actions(request_id: str, *, allow_rollback: bool) -> dict[str, Any]:
    rows: list[list[dict[str, Any]]] = [
        [_button(Msg.BTN_SERVICE_CLEAR_STOCK, f"inv:service:clear:{request_id}", style="danger")],
    ]
    if allow_rollback:
        rows.append([_button(Msg.BTN_SERVICE_ROLLBACK, f"inv:service:rollback:{request_id}", style="primary")])
    rows.append([_button(Msg.BTN_BACK, f"inv:back:{request_id}", style="default")])
    return {"inline_keyboard": rows}
