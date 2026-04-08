"""Парсинг позиций из текстового представления накладной."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from app.schemas import InvoiceItem


class InvoiceParser:
    """Эвристический парсер строк накладной с поддержкой заголовков."""

    _number_pattern = re.compile(r"\d+[\d\s]*[\.,]?\d*")
    _split_pattern = re.compile(r"\t+|\s{2,}")
    _row_start_pattern = re.compile(r"^(?P<no>\d{1,4})\s+(?P<rest>.+)$")
    _row_number_only = re.compile(r"^\d{1,4}$")
    _price_qty_sum_pattern = re.compile(
        r"(?P<price>\d+[\d\s]*[\.,]?\d*)\s+"
        r"(?P<qty>\d+[\d\s]*[\.,]?\d*)\s+"
        r"(?P<unit>[A-Za-zА-Яа-я0-9\.\-]+)\s+"
        r"(?P<sum>\d+[\d\s]*[\.,]?\d*)"
    )
    # Keep unit token Unicode-friendly (Cyrillic + Latin) to avoid mojibake range issues.
    _price_qty_sum_pattern = re.compile(
        r"(?P<price>\d+[\d\s]*[\.,]?\d*)\s+"
        r"(?P<qty>\d+[\d\s]*[\.,]?\d*)\s+"
        r"(?P<unit>[\w\.\-]+)\s+"
        r"(?P<sum>\d+[\d\s]*[\.,]?\d*)"
    )
    _percent_pattern = re.compile(r"(\d{1,2})\s*%")

    _header_synonyms: dict[str, list[str]] = {
        "name": ["наименование", "товар", "услуга", "позиция", "номенк", "наим", "описание"],
        "unit_measure": ["ед", "ед.", "ед изм", "ед.изм", "единица", "uom"],
        "quantity": ["кол-во", "количество", "qty", "кол", "q-ty"],
        "unit_amount": ["кол-во", "количество", "qty", "кол", "q-ty"],
        "unit_price": ["цена", "price", "стоимость ед", "цена ед"],
        "cost_without_tax": ["сумма без", "стоимость без", "без ндс", "без налога"],
        "tax_rate": ["ндс %", "ставка ндс", "налог %", "ндс"],
        "tax_amount": ["сумма ндс", "налог", "сумма налога"],
        "cost_with_tax": ["сумма с", "стоимость с", "с ндс"],
        "total_cost": ["итого", "стоимость товаров всего", "сумма всего", "всего"],
    }

    _table_header_required = ["наименование", "цена", "кол", "ед"]

    @classmethod
    def _to_decimal(cls, raw: str) -> Decimal | None:
        normalized = raw.replace(" ", "").replace(",", ".")
        if not normalized:
            return None
        try:
            return Decimal(normalized)
        except InvalidOperation:
            return None

    @classmethod
    def _normalize_header(cls, header: str) -> str:
        return re.sub(r"[^\w%]+", " ", header.lower(), flags=re.UNICODE).strip()

    @classmethod
    def _match_header(cls, header: str) -> str | None:
        normalized = cls._normalize_header(header)
        for key, variants in cls._header_synonyms.items():
            for variant in variants:
                if variant in normalized:
                    return key
        return None

    @classmethod
    def _is_table_header(cls, line: str) -> bool:
        normalized = cls._normalize_header(line)
        return all(token in normalized for token in cls._table_header_required)

    @classmethod
    def _extract_price_qty_sum(
        cls, text: str
    ) -> tuple[str, Decimal | None, Decimal | None, str | None, Decimal | None] | None:
        match = cls._price_qty_sum_pattern.search(text)
        if not match:
            return None
        name_part = text[: match.start()].strip()
        price = cls._to_decimal(match.group("price"))
        qty = cls._to_decimal(match.group("qty"))
        unit = match.group("unit")
        total = cls._to_decimal(match.group("sum"))
        return name_part, price, qty, unit, total

    @classmethod
    def _finalize_item(
        cls,
        items: list[InvoiceItem],
        name: str,
        price: Decimal | None,
        qty: Decimal | None,
        unit: str | None,
        total: Decimal | None,
        row_no: str | None,
        tax_rate: Decimal | None = None,
        tax_amount: Decimal | None = None,
    ) -> None:
        if not name:
            return
        extras = {"row_no": row_no} if row_no else {}
        items.append(
            InvoiceItem(
                name=name,
                unit_measure=unit,
                unit_amount=qty,
                unit_price=price,
                supply_quantity=qty,
                cost_without_tax=total,
                tax_rate=tax_rate,
                tax_amount=tax_amount,
                cost_with_tax=total,
                total_cost=total,
                extras=extras,
            )
        )

    @classmethod
    def _parse_numbered_table(cls, text: str) -> tuple[list[InvoiceItem], list[str]]:
        lines = [line.rstrip() for line in text.splitlines()]
        header_index = None
        for idx, line in enumerate(lines):
            if cls._is_table_header(line):
                header_index = idx
                break

        if header_index is None:
            return [], []

        return cls._parse_numbered_lines(lines[header_index + 1 :], strict_start=True)

    @classmethod
    def _parse_numbered_anywhere(cls, text: str) -> tuple[list[InvoiceItem], list[str]]:
        lines = [line.rstrip() for line in text.splitlines()]
        return cls._parse_numbered_lines(lines, strict_start=False)

    @classmethod
    def _parse_numbered_lines(
        cls, lines: list[str], strict_start: bool
    ) -> tuple[list[InvoiceItem], list[str]]:
        items: list[InvoiceItem] = []
        warnings: list[str] = []
        current_no: str | None = None
        name_parts: list[str] = []
        started = False
        last_no: int | None = None

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            lowered = stripped.lower()
            if lowered.startswith("итого") or lowered.startswith("в том числе"):
                break

            if cls._row_number_only.fullmatch(stripped):
                candidate = int(stripped)
                if strict_start and not started and candidate != 1:
                    continue
                if not started:
                    started = True
                if last_no is not None and candidate < last_no and candidate != 1:
                    continue
                current_no = stripped
                last_no = candidate
                name_parts = []
                continue

            row_match = cls._row_start_pattern.match(stripped)
            if row_match:
                candidate = int(row_match.group("no"))
                if strict_start and not started and candidate != 1:
                    continue
                if not started:
                    started = True
                if last_no is not None and candidate < last_no and candidate != 1:
                    continue
                current_no = row_match.group("no")
                last_no = candidate
                remainder = row_match.group("rest").strip()
                extracted = cls._extract_price_qty_sum(remainder)
                if extracted:
                    name_part, price, qty, unit, total = extracted
                    name = name_part or " ".join(name_parts)
                    cls._finalize_item(items, name, price, qty, unit, total, current_no)
                    current_no = None
                    name_parts = []
                else:
                    if remainder:
                        name_parts = [remainder]
                continue

            extracted = cls._extract_price_qty_sum(stripped)
            if extracted and current_no is not None:
                name_part, price, qty, unit, total = extracted
                name = " ".join(name_parts + [name_part]).strip()
                cls._finalize_item(items, name, price, qty, unit, total, current_no)
                current_no = None
                name_parts = []
                continue

            if current_no is not None:
                name_parts.append(stripped)

        if not items:
            warnings.append("Не удалось извлечь позиции по нумерованной таблице.")

        return items, warnings

    @classmethod
    def _parse_price_anchor(cls, text: str) -> tuple[list[InvoiceItem], list[str]]:
        lines = [line.rstrip() for line in text.splitlines()]
        anchor_index = None
        for idx, line in enumerate(lines):
            if "цена" in line.lower() and "сум" in line.lower():
                anchor_index = idx
                break

        if anchor_index is None:
            return [], []

        items: list[InvoiceItem] = []
        warnings: list[str] = []
        current_no: str | None = None
        name_parts: list[str] = []

        def parse_row(text: str, row_no: str | None) -> bool:
            matches = list(cls._number_pattern.finditer(text))
            if len(matches) < 4:
                return False
            price = cls._to_decimal(matches[-4].group(0))
            qty = cls._to_decimal(matches[-3].group(0))
            unit = None
            total = cls._to_decimal(matches[-1].group(0))
            name = text[: matches[-4].start()].strip()
            cls._finalize_item(items, name, price, qty, unit, total, row_no)
            return True

        for line in lines[anchor_index + 1 :]:
            stripped = line.strip()
            if not stripped:
                continue
            lowered = stripped.lower()
            if lowered.startswith("итого") or lowered.startswith("в том числе"):
                break

            if cls._row_number_only.fullmatch(stripped):
                current_no = stripped
                name_parts = []
                continue

            row_match = cls._row_start_pattern.match(stripped)
            if row_match:
                current_no = row_match.group("no")
                remainder = row_match.group("rest").strip()
                if parse_row(remainder, current_no):
                    current_no = None
                    name_parts = []
                else:
                    name_parts = [remainder]
                continue

            if current_no is not None:
                candidate = " ".join(name_parts + [stripped]).strip()
                if parse_row(candidate, current_no):
                    current_no = None
                    name_parts = []
                else:
                    name_parts.append(stripped)

        if not items:
            warnings.append("Не удалось извлечь позиции по якорю 'цена'.")

        return items, warnings

    @classmethod
    def _parse_right_aligned_table(cls, text: str) -> tuple[list[InvoiceItem], list[str]]:
        lines = [line.rstrip() for line in text.splitlines()]
        header_index = None
        for idx, line in enumerate(lines):
            normalized = cls._normalize_header(line)
            if "наименование" in normalized and "цена" in normalized and "ндс" in normalized:
                header_index = idx
                break

        if header_index is None:
            return [], []

        items: list[InvoiceItem] = []
        warnings: list[str] = []
        pending_no: str | None = None
        pending_text = ""

        def try_parse_row(text: str, row_no: str | None) -> bool:
            matches = list(cls._number_pattern.finditer(text))
            if len(matches) < 5:
                return False
            last = matches[-1]
            fourth = matches[-4]
            fifth = matches[-5]

            name_part = text[: fifth.start()].strip()
            price = cls._to_decimal(fifth.group(0))
            cost_without_tax = cls._to_decimal(fourth.group(0))
            tax_amount = cls._to_decimal(matches[-2].group(0))
            cost_with_tax = cls._to_decimal(last.group(0))

            percent_match = cls._percent_pattern.search(text)
            tax_rate = cls._to_decimal(percent_match.group(1)) if percent_match else None
            if tax_rate is None:
                rate_candidate = cls._to_decimal(matches[-3].group(0))
                if rate_candidate is not None and rate_candidate <= 100:
                    tax_rate = rate_candidate

            qty = None
            unit = None
            prefix = text[: fifth.start()].strip()
            tokens = prefix.split()
            for idx in range(len(tokens) - 1, -1, -1):
                token = tokens[idx]
                qty_candidate = cls._to_decimal(token)
                if qty_candidate is not None:
                    qty = qty_candidate
                    if idx + 1 < len(tokens):
                        unit = tokens[idx + 1]
                    break

            cls._finalize_item(
                items,
                name_part,
                price,
                qty,
                unit,
                cost_without_tax,
                row_no,
                tax_rate=tax_rate,
                tax_amount=tax_amount,
            )
            return True

        for line in lines[header_index + 1 :]:
            stripped = line.strip()
            if not stripped:
                continue
            lowered = stripped.lower()
            if lowered.startswith("итого") or lowered.startswith("в том числе"):
                break

            row_match = cls._row_start_pattern.match(stripped)
            if row_match:
                if pending_text:
                    try_parse_row(pending_text, pending_no)
                    pending_text = ""
                pending_no = row_match.group("no")
                remainder = row_match.group("rest").strip()
                if try_parse_row(remainder, pending_no):
                    pending_no = None
                else:
                    pending_text = remainder
                continue

            if pending_no is not None:
                pending_text = f"{pending_text} {stripped}".strip()
                if try_parse_row(pending_text, pending_no):
                    pending_no = None
                    pending_text = ""

        if not items:
            warnings.append("Не удалось извлечь позиции по правому блоку таблицы.")

        return items, warnings

    @classmethod
    def _parse_table(cls, text: str) -> tuple[list[InvoiceItem], list[str]]:
        lines = [line.rstrip() for line in text.splitlines()]
        header_index = None
        headers: list[str] = []

        for idx, line in enumerate(lines):
            if len(line.strip()) < 5:
                continue
            parts = [p.strip() for p in cls._split_pattern.split(line) if p.strip()]
            if len(parts) < 2:
                continue

            header_hits = 0
            for part in parts:
                if cls._match_header(part) is not None:
                    header_hits += 1
            if header_hits >= 2:
                header_index = idx
                headers = parts
                break

        if header_index is None or not headers:
            return [], ["Не найден заголовок таблицы, применена эвристика строк."]

        mapped_headers = [cls._match_header(h) for h in headers]
        items: list[InvoiceItem] = []
        warnings: list[str] = []

        for line in lines[header_index + 1 :]:
            if len(line.strip()) == 0:
                if items:
                    break
                continue
            parts = [p.strip() for p in cls._split_pattern.split(line) if p.strip()]
            if len(parts) < 2:
                continue

            if len(parts) < len(headers):
                parts += [""] * (len(headers) - len(parts))
            elif len(parts) > len(headers):
                parts = parts[: len(headers) - 1] + [" ".join(parts[len(headers) - 1 :])]

            data: dict[str, str] = dict(zip(headers, parts, strict=False))
            extras: dict[str, str] = {}

            name = None
            unit_measure = None
            quantity = None
            unit_price = None
            cost_without_tax = None
            tax_rate = None
            tax_amount = None
            cost_with_tax = None
            total_cost = None

            for header, value in data.items():
                key = cls._match_header(header) if header else None
                if key is None:
                    extras[header] = value
                    continue

                if key == "name":
                    name = value
                elif key == "unit_measure":
                    unit_measure = value
                elif key in {"quantity", "unit_amount"}:
                    quantity = cls._to_decimal(value) if value else None
                elif key == "unit_price":
                    unit_price = cls._to_decimal(value) if value else None
                elif key == "cost_without_tax":
                    cost_without_tax = cls._to_decimal(value) if value else None
                elif key == "tax_rate":
                    numeric = value.replace("%", "").strip()
                    tax_rate = cls._to_decimal(numeric) if numeric else None
                elif key == "tax_amount":
                    tax_amount = cls._to_decimal(value) if value else None
                elif key == "cost_with_tax":
                    cost_with_tax = cls._to_decimal(value) if value else None
                elif key == "total_cost":
                    total_cost = cls._to_decimal(value) if value else None
                else:
                    extras[header] = value

            if name is None:
                continue

            items.append(
                InvoiceItem(
                    name=name,
                    unit_measure=unit_measure,
                    unit_amount=quantity,
                    unit_price=unit_price,
                    supply_quantity=quantity,
                    cost_without_tax=cost_without_tax,
                    tax_rate=tax_rate,
                    tax_amount=tax_amount,
                    cost_with_tax=cost_with_tax,
                    total_cost=total_cost,
                    extras=extras,
                )
            )

        if not items:
            warnings.append("Не удалось извлечь позиции по заголовкам таблицы.")

        return items, warnings

    @classmethod
    def _parse_heuristic(cls, text: str) -> tuple[list[InvoiceItem], list[str]]:
        items: list[InvoiceItem] = []
        warnings: list[str] = []

        for line in text.splitlines():
            stripped = line.strip()
            if len(stripped) < 5:
                continue

            matches = list(cls._number_pattern.finditer(stripped))
            if len(matches) < 3:
                continue

            raw_numbers = [m.group(0) for m in matches]
            numbers = [cls._to_decimal(n) for n in raw_numbers]
            numbers = [n for n in numbers if n is not None]
            if len(numbers) < 3:
                continue

            name_end = matches[0].start()
            name = stripped[:name_end].strip(" -;:")
            if not name:
                continue

            unit_amount = numbers[0] if len(numbers) >= 1 else None
            unit_price = numbers[1] if len(numbers) >= 2 else None
            supply_quantity = numbers[2] if len(numbers) >= 3 else None
            cost_without_tax = numbers[3] if len(numbers) >= 4 else None
            cost_with_tax = numbers[4] if len(numbers) >= 5 else None

            if cost_without_tax is None and unit_price is not None and supply_quantity is not None:
                cost_without_tax = unit_price * supply_quantity

            if cost_with_tax is None and cost_without_tax is not None:
                cost_with_tax = cost_without_tax

            items.append(
                InvoiceItem(
                    name=name,
                    unit_amount=unit_amount,
                    unit_price=unit_price,
                    supply_quantity=supply_quantity,
                    cost_without_tax=cost_without_tax,
                    cost_with_tax=cost_with_tax,
                )
            )

        if not items:
            warnings.append("Не удалось выделить позиции по эвристике строк. Проверьте OCR и формат накладной.")

        return items, warnings

    @classmethod
    def parse_items(cls, text: str) -> tuple[list[InvoiceItem], list[str]]:
        items, warnings = cls._parse_numbered_table(text)
        if items:
            return items, warnings

        items, warnings = cls._parse_numbered_anywhere(text)
        if items:
            return items, warnings

        items, warnings = cls._parse_price_anchor(text)
        if items:
            return items, warnings

        items, warnings = cls._parse_right_aligned_table(text)
        if items:
            return items, warnings

        items, warnings = cls._parse_table(text)
        if items:
            return items, warnings

        fallback_items, fallback_warnings = cls._parse_heuristic(text)
        return fallback_items, warnings + fallback_warnings
