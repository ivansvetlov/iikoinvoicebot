"""Owner-provided conversion rules for invoice flow."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path


def _to_decimal(value: str | int | float | None) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except Exception:  # noqa: BLE001
        return None


@dataclass(frozen=True, slots=True)
class OwnerConversionRule:
    pattern: str
    target_unit: str | None = None
    piece_mass_g: Decimal | None = None
    piece_volume_ml: Decimal | None = None
    density_g_per_ml: Decimal | None = None


@dataclass(frozen=True, slots=True)
class _CompiledRule:
    regex: re.Pattern[str]
    payload: OwnerConversionRule


class OwnerRuleBook:
    """Lightweight cached rulebook loaded from a local JSON file."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._mtime: float | None = None
        self._rules: tuple[_CompiledRule, ...] = ()

    def match(self, item_name: str) -> OwnerConversionRule | None:
        self._reload_if_needed()
        text = (item_name or "").strip()
        if not text:
            return None
        for compiled in self._rules:
            if compiled.regex.search(text):
                return compiled.payload
        return None

    def _reload_if_needed(self) -> None:
        if not self.path.exists():
            self._mtime = None
            self._rules = ()
            return

        current_mtime = self.path.stat().st_mtime
        if self._mtime is not None and current_mtime == self._mtime:
            return

        data = json.loads(self.path.read_text(encoding="utf-8"))
        raw_rules = data.get("rules") if isinstance(data, dict) else None
        compiled: list[_CompiledRule] = []
        if isinstance(raw_rules, list):
            for raw in raw_rules:
                if not isinstance(raw, dict):
                    continue
                pattern = str(raw.get("pattern") or "").strip()
                if not pattern:
                    continue
                try:
                    regex = re.compile(pattern, re.IGNORECASE)
                except re.error:
                    continue
                payload = OwnerConversionRule(
                    pattern=pattern,
                    target_unit=(str(raw.get("target_unit") or "").strip() or None),
                    piece_mass_g=_to_decimal(raw.get("piece_mass_g")),
                    piece_volume_ml=_to_decimal(raw.get("piece_volume_ml")),
                    density_g_per_ml=_to_decimal(raw.get("density_g_per_ml")),
                )
                compiled.append(_CompiledRule(regex=regex, payload=payload))

        self._rules = tuple(compiled)
        self._mtime = current_mtime
