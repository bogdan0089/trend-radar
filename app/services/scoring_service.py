"""Скоринг товарів: LLM або детермінована формула.

Вимога ТЗ: ШІ генерує підсумковий рейтинг на основі даних товару, трендів і
внутрішнього бусту; без ключа працює математична формула. Обидві гілки віддають
однаковий контракт — score 0-100 і текстовий reasoning.

Правило фолбеку: будь-яка проблема з LLM (немає ключа, таймаут, 429, невалідний
JSON) переводить конкретний товар на формулу і пише в лог ПРИЧИНУ. Тихо
підставити нуль — найгірше, що тут можна зробити.
"""

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.exceptions import ExternalServiceError
from app.core.logging import get_logger
from app.integrations.llm import LLMClient, build_client, parse_verdict
from app.models.product import Product
from app.repositories.product import ProductRepository
from app.repositories.score import ScoreRepository
from app.repositories.trend import TrendRepository
from app.services.boost_service import BoostResult, BoostService
from app.services.scoring import ScoreResult, calculate_fallback_score

logger = get_logger(__name__)

_SYSTEM_PROMPT = (
    "Ти досвідчений баєр e-commerce. Оцінюєш потенціал товару для перепродажу "
    "за даними з Amazon, динамікою Google Trends і схожістю з нашими минулими "
    "успішними товарами.\n"
    "Відповідай ВИКЛЮЧНО одним JSON-об'єктом без пояснень навколо:\n"
    '{"score": <ціле 0-100>, "reasoning": "<2-4 речення українською>"}\n'
    "У reasoning назви конкретні цифри, на які спираєшся."
)


@dataclass
class ScoringOutcome:
    created: int = 0
    by_llm: int = 0
    by_fallback: int = 0


class ScoringService:
    def __init__(self, db: Session, llm: LLMClient | None = None) -> None:
        self.db = db
        self.products = ProductRepository(db)
        self.trends = TrendRepository(db)
        self.scores = ScoreRepository(db)
        self.boost = BoostService(db)
        # None = ключа немає, працюємо на формулі. У тестах підміняється моком.
        self.llm = llm if llm is not None else build_client()

    def score_products(self, product_ids: list[int]) -> ScoringOutcome:
        products = self.products.list_by_ids(product_ids)
        if not products:
            return ScoringOutcome()

        # Обидва запити — по одному на всю пачку, не на кожен товар
        trends = self.trends.latest_by_products([p.id for p in products])
        self.boost.index()

        outcome = ScoringOutcome()
        for product in products:
            snapshot = trends.get(product.id)
            # source='unavailable' означає «Google не дав даних», а не «попит нульовий»
            delta = (
                snapshot.delta_pct
                if snapshot is not None and snapshot.source == "google_trends"
                else None
            )
            boost = self.boost.calculate(title=product.title, category=product.category)

            result, provider = self._evaluate(product, delta, boost)
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
            "Скоринг: оцінок %d (LLM %d, формула %d)",
            outcome.created,
            outcome.by_llm,
            outcome.by_fallback,
        )
        return outcome

    # --------------------------------------------------------------- внутрішнє

    def _evaluate(
        self, product: Product, delta: float | None, boost: BoostResult
    ) -> tuple[ScoreResult, str]:
        fallback = calculate_fallback_score(
            title=product.title,
            rating=product.rating,
            reviews_count=product.reviews_count,
            trend_delta_pct=delta,
            boost_score=boost.score,
            boost_explanation=boost.explain(),
        )

        if self.llm is None:
            return fallback, "fallback"

        try:
            raw = self.llm.complete(
                system=_SYSTEM_PROMPT,
                prompt=self._build_prompt(product, delta, boost),
            )
            verdict = parse_verdict(raw)
        except ExternalServiceError as exc:
            # Причина обов'язково в лозі: інакше мовчазний фолбек не помітять
            logger.warning(
                "Скоринг товару %s: LLM не спрацював (%s) — беру формулу",
                product.asin,
                exc,
            )
            return fallback, "fallback"

        # Розклад формули лишаємо навіть для LLM: за ним оцінку можна перевірити
        return (
            ScoreResult(
                score=verdict.score,
                reasoning=verdict.reasoning,
                breakdown=fallback.breakdown,
            ),
            self.llm.provider,
        )

    @staticmethod
    def _build_prompt(product: Product, delta: float | None, boost: BoostResult) -> str:
        trend_line = (
            "Google Trends: даних немає"
            if delta is None
            else f"Google Trends: попит {'зростає' if delta >= 0 else 'спадає'} "
            f"на {abs(delta):.1f}% від середнього за рік"
        )
        price = f"{product.price} {product.currency}" if product.price else "не вказана"
        rating = f"{product.rating}/5" if product.rating else "немає"

        return (
            f"Товар: {product.title[:200]}\n"
            f"Категорія: {product.category}\n"
            f"Ціна: {price}\n"
            f"Рейтинг: {rating}, відгуків: {product.reviews_count}\n"
            f"{trend_line}\n"
            f"Внутрішній буст: {boost.explain()}"
        )
