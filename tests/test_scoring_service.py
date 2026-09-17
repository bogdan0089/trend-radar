"""Tests for scoring orchestration: which branch runs, and what gets stored."""

from decimal import Decimal

import pytest
from sqlalchemy import select

from app.core.exceptions import ExternalServiceError
from app.models.score import Score
from app.repositories.product import ProductRepository
from app.services.scoring_service import ScoringService


class StubLLM:
    """An LLM client that answers from a script and counts its calls."""

    provider = "gemini"

    def __init__(self, reply: str = '{"score": 90, "reasoning": "Strong demand."}') -> None:
        self.reply = reply
        self.calls = 0

    def complete(self, *, system: str, prompt: str) -> str:
        self.calls += 1
        if isinstance(self.reply, Exception):
            raise self.reply
        return self.reply


class FailingLLM(StubLLM):
    def complete(self, *, system: str, prompt: str) -> str:
        self.calls += 1
        raise ExternalServiceError("LLM responded 429: quota exhausted")


@pytest.fixture
def products(db_session):
    """Three stored products, enough to see a budget run out mid-list."""
    rows = [
        {
            "asin": f"B0SCORE{index:03d}",
            "title": f"Wireless charger {index}",
            "category": "Best Sellers in Electronics",
            "price": Decimal("29.99"),
            "currency": "USD",
            "rating": 4.5,
            "reviews_count": 1200,
            "product_url": f"https://www.amazon.com/dp/B0SCORE{index:03d}",
            "image_url": None,
            "source": "amazon",
        }
        for index in range(3)
    ]
    results = ProductRepository(db_session).upsert_many(rows)
    db_session.commit()
    return [result.product_id for result in results]


def stored_scores(db_session) -> list[Score]:
    return list(db_session.scalars(select(Score).order_by(Score.product_id)))


class TestProviderSelection:
    def test_without_a_client_everything_uses_the_formula(self, db_session, products):
        outcome = ScoringService(db_session, use_llm=False).score_products(products)

        assert (outcome.created, outcome.by_fallback, outcome.by_llm) == (3, 3, 0)
        assert {score.provider for score in stored_scores(db_session)} == {"fallback"}

    def test_a_working_client_scores_every_product(self, db_session, products):
        llm = StubLLM()

        outcome = ScoringService(db_session, llm=llm).score_products(products)

        assert llm.calls == 3
        assert (outcome.by_llm, outcome.by_fallback) == (3, 0)
        assert {score.score for score in stored_scores(db_session)} == {90}
        assert {score.provider for score in stored_scores(db_session)} == {"gemini"}

    def test_an_llm_failure_falls_back_per_product(self, db_session, products):
        """A dead provider must not cost a product its score."""
        llm = FailingLLM()

        outcome = ScoringService(db_session, llm=llm).score_products(products)

        assert llm.calls == 3
        assert (outcome.created, outcome.by_fallback) == (3, 3)
        assert {score.provider for score in stored_scores(db_session)} == {"fallback"}

    def test_the_formula_breakdown_is_kept_even_when_the_llm_scored(
        self, db_session, products
    ):
        """The rating can be rechecked by hand against the stored components."""
        ScoringService(db_session, llm=StubLLM()).score_products(products)

        for score in stored_scores(db_session):
            assert set(score.breakdown) == {"rating", "reviews", "trend", "boost"}


class TestGivingUpOnTheProvider:
    """An exhausted quota answers the same way for every remaining product.

    Each of those answers costs a call plus its retries, so after enough
    failures in a row the provider is treated as down for the rest of the run.
    """

    def test_repeated_failures_stop_the_calls(self, db_session, products):
        llm = FailingLLM()

        outcome = ScoringService(
            db_session, llm=llm, failure_threshold=2
        ).score_products(products)

        assert llm.calls == 2
        assert outcome.after_giving_up == 1
        assert (outcome.created, outcome.by_fallback) == (3, 3)

    def test_the_reasoning_says_the_provider_was_skipped(self, db_session, products):
        ScoringService(db_session, llm=FailingLLM(), failure_threshold=1).score_products(
            products
        )

        skipped = [
            score
            for score in stored_scores(db_session)
            if "failed on several products in a row" in score.reasoning
        ]
        assert len(skipped) == 2

    def test_a_success_resets_the_streak(self, db_session, products):
        """One bad answer among good ones must not disable the provider."""

        class FlakyLLM(StubLLM):
            def complete(self, *, system: str, prompt: str) -> str:
                self.calls += 1
                if self.calls == 1:
                    raise ExternalServiceError("LLM responded 503")
                return self.reply

        llm = FlakyLLM()

        outcome = ScoringService(
            db_session, llm=llm, failure_threshold=2
        ).score_products(products)

        assert llm.calls == 3
        assert outcome.after_giving_up == 0
        assert (outcome.by_llm, outcome.by_fallback) == (2, 1)


class TestTimeBudget:
    """40 products scored one after another can outlive the Celery soft limit.

    Once the budget is gone the rest fall to the formula, so the run finishes
    and every product still carries a score.
    """

    def test_an_exhausted_budget_sends_the_rest_to_the_formula(self, db_session, products):
        llm = StubLLM()

        outcome = ScoringService(db_session, llm=llm, budget_seconds=0).score_products(products)

        assert llm.calls == 0
        assert outcome.out_of_budget == 3
        assert (outcome.created, outcome.by_fallback) == (3, 3)

    def test_every_product_still_gets_a_score_and_a_reasoning(self, db_session, products):
        ScoringService(db_session, llm=StubLLM(), budget_seconds=0).score_products(products)

        scores = stored_scores(db_session)
        assert len(scores) == 3
        for score in scores:
            assert 0 <= score.score <= 100
            assert score.reasoning.strip()

    def test_the_reasoning_says_the_budget_ran_out(self, db_session, products):
        ScoringService(db_session, llm=StubLLM(), budget_seconds=0).score_products(products)

        for score in stored_scores(db_session):
            assert "scoring time budget" in score.reasoning

    def test_a_generous_budget_leaves_the_llm_in_charge(self, db_session, products):
        llm = StubLLM()

        outcome = ScoringService(db_session, llm=llm, budget_seconds=600).score_products(products)

        assert llm.calls == 3
        assert outcome.out_of_budget == 0

    def test_the_budget_is_not_counted_when_there_is_no_client(self, db_session, products):
        """Without an LLM the formula is instant, so the budget is meaningless."""
        outcome = ScoringService(db_session, use_llm=False, budget_seconds=0).score_products(
            products
        )

        assert outcome.out_of_budget == 0
        assert outcome.by_fallback == 3
        for score in stored_scores(db_session):
            assert "scoring time budget" not in score.reasoning
