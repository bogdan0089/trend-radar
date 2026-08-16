"""Збір динаміки попиту з Google Trends і збереження в БД.

Ключове рішення: недоступний тренд — це НЕ помилка пайплайну. Google блокує
частину запитів, і якщо через це падав би весь збір, система була б непридатна.
Замість винятку пишемо знімок із source='unavailable' і причиною — скоринг
далі бачить «даних немає» і враховує це окремо від «попит падає».
"""

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.exceptions import ExternalServiceError
from app.core.logging import get_logger
from app.integrations.google_trends import GoogleTrendsScraper, TrendResult
from app.repositories.product import ProductRepository
from app.repositories.trend import TrendRepository
from app.services.keywords import primary_keyword

logger = get_logger(__name__)


@dataclass
class TrendsOutcome:
    collected: int = 0  # успішно зібрані
    unavailable: int = 0  # Google не дав даних


class TrendsService:
    def __init__(self, db: Session, scraper: GoogleTrendsScraper | None = None) -> None:
        self.db = db
        self.products = ProductRepository(db)
        self.trends = TrendRepository(db)
        # Скрапер підмінюється в тестах, щоб не піднімати Chromium
        self.scraper = scraper or GoogleTrendsScraper()

    def collect_for_products(self, product_ids: list[int]) -> TrendsOutcome:
        products = self.products.list_by_ids(product_ids)
        if not products:
            return TrendsOutcome()

        # Кілька товарів можуть дати однакове ключове слово («Anker USB C»).
        # Питаємо Google один раз на слово, а знімок пишемо кожному товару.
        keyword_by_product = {p.id: primary_keyword(p.title) for p in products}
        unique_keywords = sorted(set(keyword_by_product.values()))

        logger.info(
            "Тренди: %d товарів, %d унікальних ключових слів",
            len(products),
            len(unique_keywords),
        )
        results = self.scraper.fetch_many(unique_keywords)

        outcome = TrendsOutcome()
        for product_id, keyword in keyword_by_product.items():
            result = results.get(keyword)
            if isinstance(result, TrendResult):
                self._save_success(product_id, result)
                outcome.collected += 1
            else:
                self._save_unavailable(product_id, keyword, result)
                outcome.unavailable += 1

        self.db.commit()
        logger.info(
            "Тренди: зібрано %d, недоступно %d", outcome.collected, outcome.unavailable
        )
        return outcome

    def _save_success(self, product_id: int, result: TrendResult) -> None:
        self.trends.create_snapshot(
            product_id=product_id,
            keyword=result.keyword,
            interest_now=result.interest_now,
            interest_avg=result.interest_avg,
            delta_pct=result.delta_pct,
            raw_points=result.points,
            source="google_trends",
        )

    def _save_unavailable(
        self, product_id: int, keyword: str, error: ExternalServiceError | None
    ) -> None:
        """Фіксуємо сам факт відсутності даних.

        delta_pct=0.0, а не None: колонка NOT NULL, і нуль тут читається
        правильно — «зростання не зафіксовано», а source каже, що причина
        в недоступності, а не в реальному застої попиту.
        """
        self.trends.create_snapshot(
            product_id=product_id,
            keyword=keyword,
            delta_pct=0.0,
            source="unavailable",
            error=str(error) if error else "Google Trends не повернув результат",
        )
