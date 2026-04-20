from __future__ import annotations

import unittest

from app.services.category_onboarding import (
    build_business_profile,
    build_llm_refinement_prompt,
    get_onboarding_questions,
    suggest_categories,
)


class CategoryOnboardingTests(unittest.TestCase):
    def test_questionnaire_is_compact_and_stable(self) -> None:
        questions = get_onboarding_questions()
        self.assertGreaterEqual(len(questions), 3)
        self.assertLessEqual(len(questions), 10)
        self.assertEqual(questions[0].question_id, "business_model")

    def test_profile_and_suggestions_for_food_alcohol_business(self) -> None:
        answers = {
            "business_model": ["horeca", "retail"],
            "sells_food": "yes",
            "sells_alcohol": "yes",
            "sells_bakery": "yes",
            "has_production": "yes",
            "needs_cold_chain": "yes",
            "sells_nonfood": "no",
            "uses_disposables": "yes",
        }

        plan = suggest_categories(answers)

        self.assertIn("horeca", plan.profile.segments)
        self.assertIn("alcohol", plan.profile.tags)
        self.assertIn("Алкоголь", plan.suggested_categories)
        self.assertIn("Выпечка", plan.suggested_categories)
        self.assertIn("Замороженные товары", plan.suggested_categories)
        self.assertGreater(len(plan.categories_to_create), 0)

    def test_existing_categories_match_by_alias_and_similarity(self) -> None:
        answers = {
            "business_model": ["horeca"],
            "sells_food": "yes",
            "sells_alcohol": "no",
            "sells_bakery": "no",
            "has_production": "no",
            "needs_cold_chain": "no",
            "sells_nonfood": "no",
            "uses_disposables": "yes",
        }
        existing = [
            "молочка",
            "хозка",
            "расходники",
            "Упаковка и тара",
        ]

        plan = suggest_categories(answers, existing_categories=existing)

        self.assertEqual(plan.matched_existing.get("Молочная продукция"), "молочка")
        self.assertEqual(plan.matched_existing.get("Хозтовары и уборка"), "хозка")
        self.assertEqual(plan.matched_existing.get("Расходные материалы"), "расходники")
        self.assertNotIn("Упаковка и тара", plan.categories_to_create)

    def test_profile_flags_when_segment_missing(self) -> None:
        profile = build_business_profile(
            {
                "sells_food": "yes",
                "sells_alcohol": "yes",
                "has_production": "yes",
            }
        )
        self.assertIn("segment_not_selected", profile.risk_flags)

    def test_llm_prompt_builder_returns_json_contract(self) -> None:
        plan = suggest_categories(
            {
                "business_model": ["services"],
                "sells_food": "no",
                "sells_alcohol": "no",
                "sells_bakery": "no",
                "has_production": "no",
                "needs_cold_chain": "no",
                "sells_nonfood": "yes",
                "uses_disposables": "yes",
            },
            existing_categories=["Прочее"],
        )
        prompt = build_llm_refinement_prompt(plan)
        self.assertIn("final_categories[]", prompt)
        self.assertIn("merge_map{}", prompt)
        self.assertIn("warnings[]", prompt)


if __name__ == "__main__":
    unittest.main()

