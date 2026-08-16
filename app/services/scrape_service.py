"""Логіка збору товарів: парсер → дедуплікація → БД → лічильники.

Сервіс не знає ні про HTTP, ні про Celery. Його однаково викликає і роутер,
і Celery-таска, і сід.
"""

from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import ScrapingError
from app.core.logging import get_logger
from app.integrations.amazon import ScrapedProduct, parse_bestsellers, scrape_bestsellers
from app.repositories.product import ProductRepository

logger = get_logger(__name__)

SNAPSHOT_PATH = Path(__file__).resolve().parent.parent / "seed_data" / "amazon_bestsellers.html"


@dataclass
class ScrapeOutcome:
    """Підсумок збору. Йде прямо в лічильники ScrapeRun."""

    found: int = 0
    created: int = 0
    updated: int = 0
    product_ids: list[int] = field(default_factory=list)
    used_snapshot: bool = False  # True — живий Amazon не дався, взяли демо-снапшот


class ScrapeService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.products = ProductRepository(db)

    def collect(self, *, url: str | None = None, limit: int | None = None) -> ScrapeOutcome:
        """Живий збір з Amazon. Якщо заблокували — падає на демо-снапшот.

        Запуск при цьому НЕ вважається успішним: викликач бачить `used_snapshot`
        і ставить ScrapeRun статус 'partial' з поясненням. Ховати блокування
        під виглядом успіху не можна — інакше ніхто не помітить, що скрапер мертвий.
        """
        try:
            items = scrape_bestsellers(url, limit=limit)
            return self._save(items, source="amazon")

        except ScrapingError as exc:
            if not settings.scrape_snapshot_fallback:
                raise

            logger.warning("Живий скрапінг не вдався (%s) — беру демо-снапшот", exc)
            outcome = self.collect_from_snapshot(limit=limit)
            outcome.used_snapshot = True
            return outcome

    def collect_from_snapshot(self, *, limit: int | None = None) -> ScrapeOutcome:
        """Розбирає збережену сторінку тим самим парсером, що й живий сайт."""
        if not SNAPSHOT_PATH.exists():
            logger.warning("Снапшот %s відсутній — пропускаю", SNAPSHOT_PATH)
            return ScrapeOutcome()

        html = SNAPSHOT_PATH.read_text(encoding="utf-8")
        max_items = limit if limit is not None else settings.scrape_max_products
        items = parse_bestsellers(html, limit=max_items)

        outcome = self._save(items, source="snapshot")
        outcome.used_snapshot = True
        return outcome

    # ------------------------------------------------------------- внутрішнє

    def _save(self, scraped: list[ScrapedProduct], *, source: str) -> ScrapeOutcome:
        unique = self._deduplicate(scraped)
        if not unique:
            logger.warning("Збір: парсер не повернув жодного товару (source=%s)", source)
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
            "Збір (%s): знайдено %d, створено %d, оновлено %d",
            source,
            outcome.found,
            outcome.created,
            outcome.updated,
        )
        return outcome

    @staticmethod
    def _deduplicate(items: list[ScrapedProduct]) -> list[ScrapedProduct]:
        """Один ASIN — один рядок у пачці.

        Amazon показує той самий товар у кількох блоках сторінки, а Postgres на
        два однакові ключі в одному INSERT ... ON CONFLICT відповідає помилкою.
        Лишаємо перше входження: воно вище в рейтингу бестселерів.
        """
        seen: set[str] = set()
        unique: list[ScrapedProduct] = []
        for item in items:
            if item.asin not in seen:
                seen.add(item.asin)
                unique.append(item)
        return unique

    @staticmethod
    def _to_row(item: ScrapedProduct, *, source: str) -> dict:
        """ScrapedProduct → словник під колонки таблиці.

        Обрізаємо рядки під довжину колонок: Amazon інколи віддає категорію
        довшу за 255 символів, і INSERT впав би цілою пачкою.
        """
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
