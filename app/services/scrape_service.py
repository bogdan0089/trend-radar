"""Product collection: parser -> deduplication -> database -> counters."""

from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import ScrapingError
from app.core.logging import get_logger
from app.integrations.amazon import ScrapedProduct, parse_bestsellers, scrape_categories
from app.repositories.product import ProductRepository

logger = get_logger(__name__)

SNAPSHOT_PATH = Path(__file__).resolve().parent.parent / "seed_data" / "amazon_bestsellers.html"


@dataclass
class ScrapeOutcome:
    """Collection summary; feeds the ScrapeRun counters directly."""

    found: int = 0
    created: int = 0
    updated: int = 0
    product_ids: list[int] = field(default_factory=list)
    used_snapshot: bool = False
    demo_removed: int = 0
    failed_categories: dict[str, str] = field(default_factory=dict)


class ScrapeService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.products = ProductRepository(db)

    def collect(self, *, urls: list[str] | None = None, limit: int | None = None) -> ScrapeOutcome:
        """Scrape every configured category, falling back to the demo snapshot."""
        try:
            result = scrape_categories(urls, limit_per_category=limit)
        except ScrapingError as exc:
            logger.warning("Scrape did not start (%s)", exc)
            return self._fallback_to_snapshot(limit=limit, reason=str(exc))

        if not result.products:
            reason = "; ".join(result.failures.values()) or "no products were parsed"
            return self._fallback_to_snapshot(limit=limit, reason=reason)

        outcome = self._save(result.products, source="amazon")
        outcome.failed_categories = result.failures
        outcome.demo_removed = self._drop_demo_products()
        return outcome

    def collect_from_snapshot(self, *, limit: int | None = None) -> ScrapeOutcome:
        """Parse the bundled demo page with the parser used on live HTML."""
        if not SNAPSHOT_PATH.exists():
            logger.warning("Snapshot %s is missing, skipping", SNAPSHOT_PATH)
            return ScrapeOutcome()

        html = SNAPSHOT_PATH.read_text(encoding="utf-8")
        max_items = limit if limit is not None else settings.scrape_max_products
        items = parse_bestsellers(html, limit=max_items)

        outcome = self._save(items, source="snapshot")
        outcome.used_snapshot = True
        return outcome

    def _drop_demo_products(self) -> int:
        """Discard the bundled demo rows once live data has replaced them."""
        removed = self.products.delete_by_source("snapshot")
        if removed:
            self.db.commit()
            logger.info("Collect: removed %d demo products, live data is in place", removed)
        return removed

    def _fallback_to_snapshot(self, *, limit: int | None, reason: str) -> ScrapeOutcome:
        if not settings.scrape_snapshot_fallback:
            raise ScrapingError(reason)

        logger.warning("Live scrape failed (%s), falling back to the demo snapshot", reason)
        outcome = self.collect_from_snapshot(limit=limit)
        outcome.used_snapshot = True
        return outcome

    def _save(self, scraped: list[ScrapedProduct], *, source: str) -> ScrapeOutcome:
        unique = self._deduplicate(scraped)
        if not unique:
            logger.warning("Collect: parser returned no products (source=%s)", source)
            return ScrapeOutcome()

        results = self.products.upsert_many(
            [self._to_row(item, source=source) for item in unique]
        )
        self.db.commit()

        outcome = ScrapeOutcome(
            found=len(unique),
            created=sum(1 for r in results if r.created),
            updated=sum(1 for r in results if not r.created),
            product_ids=[r.product_id for r in results],
        )
        logger.info(
            "Collect (%s): found %d, created %d, updated %d",
            source,
            outcome.found,
            outcome.created,
            outcome.updated,
        )
        return outcome

    @staticmethod
    def _deduplicate(items: list[ScrapedProduct]) -> list[ScrapedProduct]:
        """Keep one row per ASIN, the first occurrence winning."""
        seen: set[str] = set()
        unique: list[ScrapedProduct] = []
        for item in items:
            if item.asin not in seen:
                seen.add(item.asin)
                unique.append(item)
        return unique

    @staticmethod
    def _to_row(item: ScrapedProduct, *, source: str) -> dict:
        return {
            "asin": item.asin,
            "title": item.title,
            "category": item.category[:255],
            "price": item.price,
            "currency": item.currency[:8],
            "rating": item.rating,
            "reviews_count": item.reviews_count,
            "product_url": item.product_url,
            "image_url": item.image_url,
            "source": source,
        }
