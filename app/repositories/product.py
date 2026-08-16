from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import literal_column, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import aliased

from app.models.product import Product
from app.models.score import Score
from app.models.trend import TrendSnapshot
from app.repositories.base import BaseRepository

# Що перезаписуємо, коли товар уже в базі.
# first_seen_at не чіпаємо — це дата, коли ми побачили товар уперше.
_UPDATABLE_FIELDS = (
    "title",
    "category",
    "price",
    "currency",
    "rating",
    "reviews_count",
    "product_url",
    "image_url",
    "last_seen_at",
)


@dataclass(frozen=True, slots=True)
class UpsertResult:
    product_id: int
    created: bool  # True — товар зʼявився вперше, False — оновили наявний


@dataclass(frozen=True, slots=True)
class ProductRow:
    """Рядок дашборду: товар + остання оцінка + свіжий тренд."""

    product: Product
    score: Score | None
    trend_delta_pct: float | None


class ProductRepository(BaseRepository[Product]):
    model = Product

    def upsert_many(self, rows: list[dict[str, Any]]) -> list[UpsertResult]:
        """Вставляє або оновлює пачку товарів ОДНИМ запитом.

        Ключ конфлікту — унікальний asin: той самий товар у наступному запуску
        не створить дубль, а оновить ціну, рейтинг і last_seen_at.

        У rows не повинно бути двох рядків з однаковим asin — Postgres на це
        відповідає «ON CONFLICT DO UPDATE cannot affect row a second time».
        Дедуплікація — робота сервісу.
        """
        if not rows:
            return []

        now = datetime.now(UTC)
        values = [{**row, "first_seen_at": now, "last_seen_at": now} for row in rows]

        insert_stmt = pg_insert(Product).values(values)
        stmt = insert_stmt.on_conflict_do_update(
            index_elements=[Product.asin],
            set_={field: insert_stmt.excluded[field] for field in _UPDATABLE_FIELDS},
        ).returning(
            Product.id,
            # xmax — id транзакції, яка сховала стару версію рядка. При INSERT
            # ховати нічого, тож xmax = 0. Єдиний спосіб відрізнити вставку
            # від оновлення всередині одного запиту.
            literal_column("xmax = 0").label("created"),
        )

        return [
            UpsertResult(product_id=row.id, created=row.created)
            for row in self.db.execute(stmt)
        ]

    def list_by_ids(self, product_ids: list[int]) -> list[Product]:
        """Товари за списком id — одним запитом, без циклу з get() на кожен."""
        if not product_ids:
            return []
        return list(self.db.scalars(select(Product).where(Product.id.in_(product_ids))))

    def list_with_latest_score(self, *, limit: int = 50, offset: int = 0) -> list[ProductRow]:
        """Список для дашборду, найперспективніші зверху.

        LEFT JOIN, а не INNER: товар щойно спарсили, скоринг ще не відпрацював —
        він має показатись без оцінки, а не зникнути зі списку.
        """
        score = aliased(Score, self._latest_per_product(Score))
        trend = aliased(TrendSnapshot, self._latest_per_product(TrendSnapshot))

        stmt = (
            select(Product, score, trend.delta_pct)
            .outerjoin(score, score.product_id == Product.id)
            .outerjoin(trend, trend.product_id == Product.id)
            .order_by(score.score.desc().nullslast(), Product.last_seen_at.desc())
            .limit(limit)
            .offset(offset)
        )

        return [
            ProductRow(product=row[0], score=row[1], trend_delta_pct=row[2])
            for row in self.db.execute(stmt)
        ]

    @staticmethod
    def _latest_per_product(model: type) -> Any:
        """Підзапит «останній рядок на кожен product_id».

        DISTINCT ON — розширення Postgres: у кожній групі лишає перший рядок
        за порядком з ORDER BY. Без нього довелось би тягнути оцінку окремим
        запитом на кожен товар (N+1).
        """
        return (
            select(model)
            .distinct(model.product_id)
            .order_by(model.product_id, model.created_at.desc(), model.id.desc())
            .subquery()
        )
