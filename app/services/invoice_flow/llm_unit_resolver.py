"""LLM fallback resolver for ambiguous invoice unit rows."""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

import httpx

from app.config import settings
from app.services.llm_usage_log import log_openai_response


DecisionType = Literal["convert_to_mass", "convert_to_volume", "keep_pieces", "insufficient"]
ConfidenceType = Literal["low", "medium", "high"]


_DEFAULT_PROMPT = (
    "You resolve unit mapping for invoice rows. Return JSON only with decision, target_unit, "
    "piece_mass_g, piece_volume_ml, confidence, reason."
)


@dataclass(frozen=True, slots=True)
class LlmUnitDecision:
    decision: DecisionType
    target_unit: str | None
    piece_mass_g: Decimal | None
    piece_volume_ml: Decimal | None
    confidence: ConfidenceType
    reason: str


class LlmUnitResolver:
    """Small synchronous OpenAI client for ambiguous row decisions."""

    _cache: dict[str, LlmUnitDecision] = {}

    def __init__(self) -> None:
        self._prompt = self._load_prompt()

    def resolve(
        self,
        *,
        item_name: str,
        unit_measure: str | None,
        unit_amount: Decimal | None,
        supply_quantity: Decimal | None,
        preferred_stock_unit: str | None,
        piece_mass_g: Decimal | None,
        piece_volume_ml: Decimal | None,
    ) -> LlmUnitDecision | None:
        if not settings.openai_api_key:
            return None

        cache_key = self._build_cache_key(
            item_name=item_name,
            unit_measure=unit_measure,
            unit_amount=unit_amount,
            supply_quantity=supply_quantity,
            preferred_stock_unit=preferred_stock_unit,
            piece_mass_g=piece_mass_g,
            piece_volume_ml=piece_volume_ml,
        )
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        payload = {
            "item_name": item_name,
            "unit_measure": unit_measure,
            "unit_amount": str(unit_amount) if unit_amount is not None else None,
            "supply_quantity": str(supply_quantity) if supply_quantity is not None else None,
            "preferred_stock_unit": preferred_stock_unit,
            "piece_mass_g": str(piece_mass_g) if piece_mass_g is not None else None,
            "piece_volume_ml": str(piece_volume_ml) if piece_volume_ml is not None else None,
        }

        input_content = [
            {"role": "system", "content": [{"type": "input_text", "text": self._prompt}]},
            {"role": "user", "content": [{"type": "input_text", "text": json.dumps(payload, ensure_ascii=False)}]},
        ]
        body = {
            "model": settings.invoice_flow_llm_model,
            "input": input_content,
            "temperature": 0,
            "max_output_tokens": 200,
        }
        headers = {
            "authorization": f"Bearer {settings.openai_api_key}",
            "content-type": "application/json",
        }
        timeout = max(5, int(settings.invoice_flow_llm_timeout_sec or 20))

        try:
            with httpx.Client(timeout=timeout) as client:
                response = client.post("https://api.openai.com/v1/responses", headers=headers, json=body)
                response.raise_for_status()
                raw = response.json()
                log_openai_response(
                    raw,
                    model=str(body.get("model") or settings.invoice_flow_llm_model),
                    call_kind="unit_resolver",
                )
        except Exception:
            return None

        parsed = self._extract_json(raw)
        if not isinstance(parsed, dict):
            return None

        decision = self._to_decision(parsed)
        if decision is None:
            return None
        self._cache[cache_key] = decision
        return decision

    def _load_prompt(self) -> str:
        prompt_path = Path(settings.invoice_flow_llm_prompt_fork_path or "").expanduser()
        if prompt_path and not prompt_path.is_absolute():
            prompt_path = Path(__file__).resolve().parents[3] / prompt_path
        if prompt_path and prompt_path.exists():
            try:
                text = prompt_path.read_text(encoding="utf-8").strip()
                if text:
                    return text
            except Exception:
                return _DEFAULT_PROMPT
        return _DEFAULT_PROMPT

    @staticmethod
    def _build_cache_key(
        *,
        item_name: str,
        unit_measure: str | None,
        unit_amount: Decimal | None,
        supply_quantity: Decimal | None,
        preferred_stock_unit: str | None,
        piece_mass_g: Decimal | None,
        piece_volume_ml: Decimal | None,
    ) -> str:
        return json.dumps(
            {
                "name": item_name.strip().lower(),
                "unit_measure": (unit_measure or "").strip().lower(),
                "unit_amount": str(unit_amount) if unit_amount is not None else "",
                "supply_quantity": str(supply_quantity) if supply_quantity is not None else "",
                "preferred_stock_unit": (preferred_stock_unit or "").strip().lower(),
                "piece_mass_g": str(piece_mass_g) if piece_mass_g is not None else "",
                "piece_volume_ml": str(piece_volume_ml) if piece_volume_ml is not None else "",
            },
            ensure_ascii=False,
            sort_keys=True,
        )

    @staticmethod
    def _extract_json(payload: dict[str, Any]) -> dict[str, Any] | None:
        output = payload.get("output") if isinstance(payload, dict) else None
        if not isinstance(output, list):
            return None
        chunks: list[str] = []
        for item in output:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "output_text":
                text = item.get("text")
                if isinstance(text, str):
                    chunks.append(text)
            if item.get("type") == "message":
                for part in item.get("content", []) or []:
                    if not isinstance(part, dict):
                        continue
                    text = part.get("text") or part.get("output_text")
                    if isinstance(text, str):
                        chunks.append(text)
        merged = "\n".join(chunks).strip()
        if not merged:
            return None
        if merged.startswith("```"):
            merged = merged.strip("`").strip()
            if merged.lower().startswith("json"):
                merged = merged[4:].strip()
        try:
            candidate = json.loads(merged)
            return candidate if isinstance(candidate, dict) else None
        except Exception:
            return None

    @staticmethod
    def _to_decimal(value: Any) -> Decimal | None:
        if value is None:
            return None
        try:
            return Decimal(str(value))
        except Exception:
            return None

    def _to_decision(self, payload: dict[str, Any]) -> LlmUnitDecision | None:
        decision_raw = str(payload.get("decision") or "").strip().lower()
        decision_map: dict[str, DecisionType] = {
            "convert_to_mass": "convert_to_mass",
            "convert_to_volume": "convert_to_volume",
            "keep_pieces": "keep_pieces",
            "insufficient": "insufficient",
        }
        decision = decision_map.get(decision_raw)
        if decision is None:
            return None

        confidence_raw = str(payload.get("confidence") or "").strip().lower()
        if confidence_raw not in {"low", "medium", "high"}:
            confidence_raw = "low"
        confidence: ConfidenceType = confidence_raw  # type: ignore[assignment]

        target_unit_raw = str(payload.get("target_unit") or "").strip().lower()
        target_unit = target_unit_raw if target_unit_raw in {"g", "ml"} else None
        piece_mass_g = self._to_decimal(payload.get("piece_mass_g"))
        piece_volume_ml = self._to_decimal(payload.get("piece_volume_ml"))
        reason = str(payload.get("reason") or "").strip()[:300]

        return LlmUnitDecision(
            decision=decision,
            target_unit=target_unit,
            piece_mass_g=piece_mass_g,
            piece_volume_ml=piece_volume_ml,
            confidence=confidence,
            reason=reason,
        )
