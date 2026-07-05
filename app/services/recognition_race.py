"""Parallel vision + SotaOCR hybrid race (MAX channel only)."""
from __future__ import annotations

import asyncio
import contextlib
import logging
from dataclasses import dataclass
from time import perf_counter
from typing import TYPE_CHECKING, Any, Literal

from app.config import settings
from app.errors import UserFacingError
from app.schemas import InvoiceItem

if TYPE_CHECKING:
    from app.services.pipeline import InvoicePipelineService

logger = logging.getLogger(__name__)

WinnerPath = Literal["hybrid", "vision"]


@dataclass(frozen=True, slots=True)
class RecognitionRaceResult:
    llm_data: dict[str, Any]
    items: list[InvoiceItem]
    warnings: list[str]
    winner: WinnerPath
    elapsed_ms: int


def _min_items() -> int:
    return int(getattr(settings, "fast_parser_min_items", 2) or 2)


def _passes_gate(items: list[InvoiceItem], garbage: list[str]) -> bool:
    return bool(items) and not garbage and len(items) >= max(1, _min_items())


def _score(path: WinnerPath, items: list[InvoiceItem], garbage: list[str]) -> tuple[int, int, int]:
    """Higher is better: item count, no garbage, hybrid tie-break."""
    return (len(items), 0 if garbage else 1, 1 if path == "hybrid" else 0)


async def _cancel_task(task: asyncio.Task[Any]) -> None:
    if task.done():
        return
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task


async def race_image_recognition(
    service: InvoicePipelineService,
    *,
    prompt: str,
    prepared_filename: str,
    prepared_content: bytes,
    original_filename: str,
    original_content: bytes,
    text_hint: str,
    user_id: str | None,
    request_id: str,
) -> RecognitionRaceResult:
    """Run hybrid and vision in parallel; first good result wins."""
    started = perf_counter()
    budget = float(max(15, int(getattr(settings, "recognition_race_budget_sec", 90) or 90)))
    vision_budget = float(max(10, int(getattr(settings, "recognition_vision_budget_sec", 45) or 45)))
    hybrid_budget = float(max(10, int(getattr(settings, "recognition_sotaocr_budget_sec", 60) or 60)))
    llm_budget = float(
        max(10, int(getattr(settings, "sotaocr_hybrid_llm_timeout_sec", 45) or 45))
    )

    async def _hybrid_path() -> tuple[dict[str, Any], list[InvoiceItem], list[str]] | None:
        try:
            return await asyncio.wait_for(
                service.recognize_via_sotaocr_hybrid(
                    original_filename,
                    original_content,
                    user_id,
                    request_id,
                    ocr_timeout_sec=hybrid_budget,
                    llm_timeout_sec=llm_budget,
                    skip_openai_probe=True,
                ),
                timeout=hybrid_budget + llm_budget + 2,
            )
        except asyncio.TimeoutError:
            return None
        except Exception as exc:
            logger.warning("Race hybrid path failed: %s", exc, extra={"request_id": request_id})
            return None

    async def _vision_path() -> tuple[dict[str, Any], list[InvoiceItem], list[str]]:
        llm_data, items, garbage = await asyncio.wait_for(
            service.recognize_via_vision(
                prompt,
                prepared_filename,
                prepared_content,
                text_hint,
                user_id,
                request_id,
            ),
            timeout=vision_budget,
        )
        if garbage or not items:
            raw_data, raw_items, raw_garbage = await asyncio.wait_for(
                service.recognize_via_vision(
                    prompt,
                    original_filename,
                    original_content,
                    text_hint,
                    user_id,
                    request_id,
                ),
                timeout=max(5.0, vision_budget * 0.5),
            )
            if raw_items and not raw_garbage:
                return raw_data, raw_items, ["recognition_race_vision_raw"]
            return llm_data, items, []
        return llm_data, items, ["recognition_race_vision"]

    hybrid_task = asyncio.create_task(_hybrid_path(), name=f"race-hybrid-{request_id[:8]}")
    vision_task = asyncio.create_task(_vision_path(), name=f"race-vision-{request_id[:8]}")
    pending: set[asyncio.Task[Any]] = {hybrid_task, vision_task}
    candidates: list[tuple[WinnerPath, dict[str, Any], list[InvoiceItem], list[str], list[str]]] = []

    try:
        while pending and (perf_counter() - started) < budget:
            remaining = budget - (perf_counter() - started)
            if remaining <= 0:
                break
            done, pending = await asyncio.wait(
                pending,
                timeout=min(2.0, remaining),
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in done:
                path: WinnerPath = "hybrid" if task is hybrid_task else "vision"
                try:
                    outcome = task.result()
                except Exception as exc:
                    logger.warning(
                        "Race path %s raised: %s",
                        path,
                        exc,
                        extra={"request_id": request_id},
                    )
                    continue
                if path == "hybrid":
                    if outcome is None:
                        continue
                    llm_data, items, warnings = outcome
                    garbage: list[str] = []
                    if _passes_gate(items, garbage):
                        elapsed_ms = int((perf_counter() - started) * 1000)
                        merged = list(warnings or []) + [
                            "sotaocr_hybrid_used",
                            "recognition_race_winner=hybrid",
                            f"recognition_race_ms={elapsed_ms}",
                        ]
                        await _cancel_task(vision_task)
                        return RecognitionRaceResult(
                            llm_data=llm_data,
                            items=items,
                            warnings=merged,
                            winner="hybrid",
                            elapsed_ms=elapsed_ms,
                        )
                    candidates.append((path, llm_data, items, warnings or [], garbage))
                else:
                    llm_data, items, warnings = outcome
                    garbage = service.detect_garbage_items(items, llm_data)
                    if _passes_gate(items, garbage):
                        elapsed_ms = int((perf_counter() - started) * 1000)
                        merged = list(warnings or []) + [
                            "recognition_race_winner=vision",
                            f"recognition_race_ms={elapsed_ms}",
                        ]
                        await _cancel_task(hybrid_task)
                        return RecognitionRaceResult(
                            llm_data=llm_data,
                            items=items,
                            warnings=merged,
                            winner="vision",
                            elapsed_ms=elapsed_ms,
                        )
                    candidates.append((path, llm_data, items, warnings or [], garbage))

        if candidates:
            best = max(
                candidates,
                key=lambda row: _score(row[0], row[2], row[4]),
            )
            path, llm_data, items, warnings, garbage = best
            if items:
                elapsed_ms = int((perf_counter() - started) * 1000)
                merged = list(warnings)
                if path == "hybrid":
                    merged.append("sotaocr_hybrid_used")
                merged.append(f"recognition_race_winner={path}")
                merged.append(f"recognition_race_ms={elapsed_ms}")
                return RecognitionRaceResult(
                    llm_data=llm_data,
                    items=items,
                    warnings=merged,
                    winner=path,
                    elapsed_ms=elapsed_ms,
                )

        raise UserFacingError(
            "Не удалось распознать документ за отведённое время.",
            hint="Проверьте качество фото или отправьте PDF. Попробуйте снова через минуту.",
            code="llm_timeout",
        )
    finally:
        for task in (hybrid_task, vision_task):
            if not task.done():
                task.cancel()
        await asyncio.gather(hybrid_task, vision_task, return_exceptions=True)
