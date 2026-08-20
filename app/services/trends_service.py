"""Collect Google Trends demand data and store it."""

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.exceptions import ExternalServiceError
from app.core.logging import get_logger
from app.integrations.google_trends import GoogleTrendsScraper, TrendResult
from app.repositories.product import ProductRepository
from app.repositories.trend import TrendRepository
from app.utils.keywords import primary_keyword

logger = get_logger(__name__)


@dataclass
class TrendsOutcome:
    collected: int = 0
    unavailable: int = 0


class TrendsService:
    def __init__(self, db: Session, scraper: GoogleTrendsScraper | None = None) -> None:
        self.db = db
        self.products = ProductRepository(db)
        self.trends = TrendRepository(db)
        self.scraper = scraper or GoogleTrendsScraper()

    def collect_for_products(self, product_ids: list[int]) -> TrendsOutcome:
        """Query Google once per distinct keyword and store a snapshot per product."""
        products = self.products.list_by_ids(product_ids)
        if not products:
            return TrendsOutcome()

        keyword_by_product = {p.id: primary_keyword(p.title) for p in products}
        unique_keywords = sorted(set(keyword_by_product.values()))

        logger.info(
            "Trends: %d products, %d distinct keywords",
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
            "Trends: collected %d, unavailable %d", outcome.collected, outcome.unavailable
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
        """Record the absence of data; `source` marks it as missing, not flat."""
        self.trends.create_snapshot(
            product_id=product_id,
            keyword=keyword,
            delta_pct=0.0,
            source="unavailable",
            error=str(error) if error else "Google Trends returned no result",
        )
