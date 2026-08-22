"""Product scoring: an LLM when configured, the deterministic formula otherwise."""

import time
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import ExternalServiceError
from app.core.logging import get_logger
from app.integrations.google_trends import MIN_RELIABLE_INTEREST
from app.integrations.llm import LLMClient, build_client, parse_verdict
from app.models.product import Product
from app.models.trend import TrendSnapshot
from app.repositories.product import ProductRepository
from app.repositories.score import ScoreRepository
from app.repositories.trend import TrendRepository
from app.services.boost_service import BoostResult, BoostService
from app.services.scoring import ScoreResult, calculate_fallback_score

logger = get_logger(__name__)

_SYSTEM_PROMPT = (
    "You are an experienced e-commerce buyer. You rate a product's resale "
    "potential from its Amazon data, its Google Trends dynamics and its "
    "similarity to our past successful products.\n"
    "Reply with EXACTLY one JSON object and no surrounding text:\n"
    '{"score": <integer 0-100>, "reasoning": "<2-4 sentences>"}\n'
    "In the reasoning cite the concrete numbers you relied on."
)

# One run scores up to 40 products one after another, and a slow or retrying
# provider can spend the whole Celery soft limit on them. Once the budget is
# gone the rest fall to the formula, so the run still finishes and every product
# still carries a score.
_BUDGET_NOTE = (
    "The LLM was not asked for this product: the run had spent its scoring time "
    "budget, so the deterministic formula was used instead."
)


@dataclass
class ScoringOutcome:
    created: int = 0
    by_llm: int = 0
    by_fallback: int = 0
    out_of_budget: int = 0


class ScoringService:
    def __init__(
        self,
        db: Session,
        llm: LLMClient | None = None,
        *,
        use_llm: bool = True,
        budget_seconds: float | None = None,
    ) -> None:
        """`use_llm=False` forces the formula even when a key is configured."""
        self.db = db
        self.products = ProductRepository(db)
        self.trends = TrendRepository(db)
        self.scores = ScoreRepository(db)
        self.boost = BoostService(db)
        self.llm = llm if llm is not None else (build_client() if use_llm else None)
        self.budget_seconds = (
            settings.scoring_budget_seconds if budget_seconds is None else budget_seconds
        )

    def score_products(self, product_ids: list[int]) -> ScoringOutcome:
        products = self.products.list_by_ids(product_ids)
        if not products:
            return ScoringOutcome()

        trends = self.trends.latest_by_products([p.id for p in products])
        self.boost.index()

        deadline = time.monotonic() + self.budget_seconds
        outcome = ScoringOutcome()

        for product in products:
            delta, unreliable = self._read_trend(trends.get(product.id))
            boost = self.boost.calculate(title=product.title, category=product.category)

            allow_llm = time.monotonic() < deadline
            if not allow_llm and self.llm is not None:
                outcome.out_of_budget += 1
                if outcome.out_of_budget == 1:
                    logger.warning(
                        "Scoring: the %.0fs budget is spent, the remaining products "
                        "are scored by the formula",
                        self.budget_seconds,
                    )

            result, provider = self._evaluate(
                product, delta, unreliable, boost, allow_llm=allow_llm
            )
            self.scores.create(
                product_id=product.id,
                score=result.score,
                reasoning=result.reasoning,
                provider=provider,
                boost_score=boost.score,
                breakdown=result.breakdown or None,
            )

            outcome.created += 1
            if provider == "fallback":
                outcome.by_fallback += 1
            else:
                outcome.by_llm += 1

        self.db.commit()
        logger.info(
            "Scoring: %d ratings (LLM %d, formula %d, of which %d out of budget)",
            outcome.created,
            outcome.by_llm,
            outcome.by_fallback,
            outcome.out_of_budget,
        )
        return outcome

    @staticmethod
    def _read_trend(snapshot: TrendSnapshot | None) -> tuple[float | None, bool]:
        """Return the demand change and whether it rests on too little data."""
        if snapshot is None or snapshot.source != "google_trends":
            return None, False

        unreliable = (
            snapshot.interest_avg is None or snapshot.interest_avg < MIN_RELIABLE_INTEREST
        )
        return snapshot.delta_pct, unreliable

    def _evaluate(
        self,
        product: Product,
        delta: float | None,
        unreliable: bool,
        boost: BoostResult,
        *,
        allow_llm: bool = True,
    ) -> tuple[ScoreResult, str]:
        fallback = calculate_fallback_score(
            title=product.title,
            rating=product.rating,
            reviews_count=product.reviews_count,
            trend_delta_pct=delta,
            trend_unreliable=unreliable,
            boost_score=boost.score,
            boost_explanation=boost.explain(),
        )

        if self.llm is None:
            return fallback, "fallback"

        if not allow_llm:
            return self._with_note(fallback, _BUDGET_NOTE), "fallback"

        try:
            raw = self.llm.complete(
                system=_SYSTEM_PROMPT,
                prompt=self._build_prompt(product, delta, unreliable, boost),
            )
            verdict = parse_verdict(raw)
        except ExternalServiceError as exc:
            logger.warning(
                "Scoring %s: LLM failed (%s), using the formula",
                product.asin,
                exc,
            )
            return fallback, "fallback"

        return (
            ScoreResult(
                score=verdict.score,
                reasoning=verdict.reasoning,
                breakdown=fallback.breakdown,
            ),
            self.llm.provider,
        )

    @staticmethod
    def _with_note(result: ScoreResult, note: str) -> ScoreResult:
        """The same score, with a line saying why the LLM was not asked."""
        return ScoreResult(
            score=result.score,
            reasoning=f"{result.reasoning} {note}",
            breakdown=result.breakdown,
        )

    @staticmethod
    def _build_prompt(
        product: Product, delta: float | None, unreliable: bool, boost: BoostResult
    ) -> str:
        if delta is None:
            trend_line = "Google Trends: no data"
        elif unreliable:
            trend_line = (
                f"Google Trends: {delta:+.1f}% against the yearly average, but the search "
                "history is nearly empty, so treat this figure as unreliable"
            )
        else:
            trend_line = (
                f"Google Trends: demand {'rising' if delta >= 0 else 'falling'} "
                f"{abs(delta):.1f}% against the yearly average"
            )
        price = f"{product.price} {product.currency}" if product.price else "not shown"
        rating = f"{product.rating}/5" if product.rating else "none"

        return (
            f"Product: {product.title[:200]}\n"
            f"Category: {product.category}\n"
            f"Price: {price}\n"
            f"Rating: {rating}, reviews: {product.reviews_count}\n"
            f"{trend_line}\n"
            f"Internal boost: {boost.explain()}"
        )
