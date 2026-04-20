"""Business onboarding questionnaire and category planning helpers.

This module is intentionally standalone: no bot wiring here.
It can be plugged into onboarding flow later without changing core logic.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


AnswerValue = str | bool | list[str]


@dataclass(frozen=True, slots=True)
class QuestionOption:
    key: str
    label: str


@dataclass(frozen=True, slots=True)
class OnboardingQuestion:
    question_id: str
    title: str
    question: str
    options: tuple[QuestionOption, ...]
    allow_multiple: bool = False
    required: bool = True


@dataclass(slots=True)
class BusinessProfile:
    segments: set[str] = field(default_factory=set)
    tags: set[str] = field(default_factory=set)
    risk_flags: set[str] = field(default_factory=set)
    answers: dict[str, AnswerValue] = field(default_factory=dict)


@dataclass(slots=True)
class CategoryPlan:
    profile: BusinessProfile
    suggested_categories: list[str]
    matched_existing: dict[str, str]
    categories_to_create: list[str]
    notes: list[str]


_QUESTIONNAIRE: tuple[OnboardingQuestion, ...] = (
    OnboardingQuestion(
        question_id="business_model",
        title="Формат бизнеса",
        question="Какие форматы у бизнеса?",
        options=(
            QuestionOption("horeca", "HoReCa / общепит"),
            QuestionOption("retail", "Розница"),
            QuestionOption("beauty", "Бьюти / здоровье"),
            QuestionOption("pharmacy", "Фарма / медтовары"),
            QuestionOption("manufacturing", "Производство"),
            QuestionOption("services", "Сервисные услуги"),
        ),
        allow_multiple=True,
    ),
    OnboardingQuestion(
        question_id="sales_channels",
        title="Каналы продаж",
        question="Где продаете основной объем?",
        options=(
            QuestionOption("offline", "Только офлайн"),
            QuestionOption("online", "Только онлайн"),
            QuestionOption("mixed", "Офлайн + онлайн"),
            QuestionOption("b2b", "Преимущественно B2B"),
        ),
    ),
    OnboardingQuestion(
        question_id="sells_food",
        title="Пищевой контур",
        question="Есть ли продовольственные позиции?",
        options=(
            QuestionOption("yes", "Да"),
            QuestionOption("no", "Нет"),
        ),
    ),
    OnboardingQuestion(
        question_id="sells_bakery",
        title="Выпечка",
        question="Есть ли выпечка/кондитерка в ассортименте?",
        options=(
            QuestionOption("yes", "Да"),
            QuestionOption("no", "Нет"),
        ),
    ),
    OnboardingQuestion(
        question_id="sells_alcohol",
        title="Алкоголь",
        question="Есть ли алкоголь в продаже или закупке?",
        options=(
            QuestionOption("yes", "Да"),
            QuestionOption("no", "Нет"),
        ),
    ),
    OnboardingQuestion(
        question_id="has_production",
        title="Производство",
        question="Есть ли приготовление/сборка своих позиций?",
        options=(
            QuestionOption("yes", "Да"),
            QuestionOption("no", "Нет"),
        ),
    ),
    OnboardingQuestion(
        question_id="needs_cold_chain",
        title="Холодовая цепь",
        question="Есть ли охлажденные или замороженные товары?",
        options=(
            QuestionOption("yes", "Да"),
            QuestionOption("no", "Нет"),
        ),
    ),
    OnboardingQuestion(
        question_id="sells_nonfood",
        title="Непродтовары",
        question="Есть ли непродовольственные товары?",
        options=(
            QuestionOption("yes", "Да"),
            QuestionOption("no", "Нет"),
        ),
    ),
    OnboardingQuestion(
        question_id="uses_disposables",
        title="Расходники",
        question="Используете одноразовые материалы/упаковку?",
        options=(
            QuestionOption("yes", "Да"),
            QuestionOption("no", "Нет"),
        ),
    ),
)


_BASE_CATEGORIES: tuple[str, ...] = (
    "Основной ассортимент",
    "Расходные материалы",
    "Хозтовары и уборка",
    "Упаковка и тара",
    "Услуги",
    "Прочее",
)


_SEGMENT_CATEGORIES: dict[str, tuple[str, ...]] = {
    "horeca": (
        "Сырье и ингредиенты",
        "Напитки",
        "Снеки и десерты",
        "Заготовки и полуфабрикаты",
    ),
    "retail": (
        "Товары для перепродажи",
        "Сезонный ассортимент",
        "Акционные позиции",
    ),
    "beauty": (
        "Косметика и уход",
        "Инструменты и расходники",
        "Дезинфекция и стерилизация",
    ),
    "pharmacy": (
        "Медицинские товары",
        "БАД и витамины",
        "Сопутствующие товары",
    ),
    "manufacturing": (
        "Сырье и материалы",
        "Комплектующие",
        "Упаковка готовой продукции",
    ),
    "services": (
        "Материалы для оказания услуг",
        "Хозяйственные расходы",
    ),
}


_TAG_CATEGORIES: dict[str, tuple[str, ...]] = {
    "food": (
        "Молочная продукция",
        "Базовые продукты",
    ),
    "bakery": (
        "Выпечка",
        "Ингредиенты для выпечки",
    ),
    "alcohol": (
        "Алкоголь",
        "Безалкогольные напитки",
    ),
    "production": (
        "Технологические потери",
        "Заготовки и полуфабрикаты",
    ),
    "cold_chain": (
        "Охлажденные товары",
        "Замороженные товары",
    ),
    "nonfood": (
        "Непродовольственные товары",
    ),
    "disposables": (
        "Одноразовые материалы",
        "Упаковка и тара",
    ),
}


_CATEGORY_ALIASES: dict[str, str] = {
    "молочка": "молочная продукция",
    "хозка": "хозтовары и уборка",
    "расходники": "расходные материалы",
    "одноразка": "одноразовые материалы",
    "тара": "упаковка и тара",
}


def get_onboarding_questions() -> list[OnboardingQuestion]:
    """Return deterministic onboarding questionnaire (3-10 compact questions)."""
    return list(_QUESTIONNAIRE)


def build_business_profile(answers: dict[str, AnswerValue]) -> BusinessProfile:
    """Build compact profile used for deterministic category planning."""
    profile = BusinessProfile(answers=dict(answers))
    profile.segments.update(_normalize_multi(answers.get("business_model")))

    if _is_yes(answers.get("sells_food")):
        profile.tags.add("food")
    if _is_yes(answers.get("sells_bakery")):
        profile.tags.add("bakery")
    if _is_yes(answers.get("sells_alcohol")):
        profile.tags.add("alcohol")
    if _is_yes(answers.get("has_production")):
        profile.tags.add("production")
    if _is_yes(answers.get("needs_cold_chain")):
        profile.tags.add("cold_chain")
    if _is_yes(answers.get("sells_nonfood")):
        profile.tags.add("nonfood")
    if _is_yes(answers.get("uses_disposables")):
        profile.tags.add("disposables")

    if "alcohol" in profile.tags and not ({"retail", "horeca"} & profile.segments):
        profile.risk_flags.add("alcohol_without_primary_segment")
    if "production" in profile.tags and "services" in profile.segments and "food" not in profile.tags:
        profile.risk_flags.add("production_in_service_segment")
    if not profile.segments:
        profile.risk_flags.add("segment_not_selected")

    return profile


def suggest_categories(
    answers: dict[str, AnswerValue],
    existing_categories: list[str] | None = None,
) -> CategoryPlan:
    """Plan category set and map it to existing categories if provided."""
    profile = build_business_profile(answers)
    existing = existing_categories or []
    suggested = _dedupe_keep_order(
        [
            *_BASE_CATEGORIES,
            *[cat for segment in sorted(profile.segments) for cat in _SEGMENT_CATEGORIES.get(segment, ())],
            *[cat for tag in sorted(profile.tags) for cat in _TAG_CATEGORIES.get(tag, ())],
        ]
    )
    matched = _match_existing_categories(suggested, existing)
    to_create = [name for name in suggested if name not in matched]

    notes = [
        "Категории сформированы по матрице правил, а не по confidence LLM.",
        "Новые категории рекомендуется подтверждать владельцем или администратором.",
    ]
    if profile.risk_flags:
        notes.append(f"Проверьте флаги профиля: {', '.join(sorted(profile.risk_flags))}.")

    return CategoryPlan(
        profile=profile,
        suggested_categories=suggested,
        matched_existing=matched,
        categories_to_create=to_create,
        notes=notes,
    )


def build_llm_refinement_prompt(plan: CategoryPlan, max_categories: int = 40) -> str:
    """Build optional prompt for LLM post-processing (not used by default)."""
    suggested = plan.suggested_categories[:max_categories]
    existing_map = ", ".join(f"{k}->{v}" for k, v in sorted(plan.matched_existing.items()))
    segments = ", ".join(sorted(plan.profile.segments)) or "n/a"
    tags = ", ".join(sorted(plan.profile.tags)) or "n/a"
    return (
        "You are helping to finalize product category taxonomy.\n"
        "Keep business semantics, avoid duplicates, and keep names short.\n"
        f"Segments: {segments}\n"
        f"Tags: {tags}\n"
        f"Suggested categories: {suggested}\n"
        f"Already matched categories: {existing_map or 'n/a'}\n"
        "Return JSON with keys: final_categories[], merge_map{}, warnings[]."
    )


def _is_yes(value: AnswerValue | None) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, list):
        normalized = {str(item).strip().lower() for item in value}
        return "yes" in normalized or "да" in normalized
    if value is None:
        return False
    normalized_value = str(value).strip().lower()
    return normalized_value in {"yes", "да", "true", "1"}


def _normalize_multi(value: AnswerValue | None) -> set[str]:
    if value is None:
        return set()
    if isinstance(value, list):
        return {str(item).strip().lower() for item in value if str(item).strip()}
    if isinstance(value, bool):
        return {"yes"} if value else {"no"}
    normalized = str(value).strip().lower()
    return {normalized} if normalized else set()


def _dedupe_keep_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if not value:
            continue
        key = _normalize_text(value)
        if key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result


def _normalize_text(value: str) -> str:
    normalized = str(value).strip().lower()
    normalized = re.sub(r"[^\w\s]+", " ", normalized, flags=re.UNICODE)
    normalized = re.sub(r"\s+", " ", normalized, flags=re.UNICODE).strip()
    return _CATEGORY_ALIASES.get(normalized, normalized)


def _token_set(value: str) -> set[str]:
    normalized = _normalize_text(value)
    return {token for token in normalized.split(" ") if token}


def _similarity(a: str, b: str) -> float:
    left = _token_set(a)
    right = _token_set(b)
    if not left or not right:
        return 0.0
    inter = len(left & right)
    union = len(left | right)
    if union == 0:
        return 0.0
    return inter / union


def _match_existing_categories(suggested: list[str], existing: list[str]) -> dict[str, str]:
    if not existing:
        return {}

    exact_index: dict[str, str] = {}
    for name in existing:
        key = _normalize_text(name)
        if key and key not in exact_index:
            exact_index[key] = name

    matched: dict[str, str] = {}
    for target in suggested:
        normalized_target = _normalize_text(target)
        if normalized_target in exact_index:
            matched[target] = exact_index[normalized_target]
            continue

        best_name = ""
        best_score = 0.0
        duplicate_best = False
        for current in existing:
            score = _similarity(target, current)
            if score > best_score:
                best_score = score
                best_name = current
                duplicate_best = False
            elif score == best_score and score > 0:
                duplicate_best = True
        if best_score >= 0.66 and not duplicate_best:
            matched[target] = best_name
    return matched

