from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, literal_column, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import aliased

from app.models.product import Product
from app.models.score import Score
from app.models.trend import TrendSnapshot
from app.repositories.base import BaseRepository

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
    "source",
)


@dataclass(frozen=True, slots=True)
class UpsertResult:
    product_id: int
    created: bool


@dataclass(frozen=True, slots=True)
class ProductRow:
    """Dashboard row: a product with its latest score and trend reading."""

    product: Product
    score: Score | None
    trend_delta_pct: float | None


class ProductRepository(BaseRepository[Product]):
    model = Product

    def upsert_many(self, rows: list[dict[str, Any]]) -> list[UpsertResult]:
        """Insert or update products in one statement; rows must be unique by asin."""
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
            literal_column("xmax = 0").label("created"),
        )

        return [
            UpsertResult(product_id=row.id, created=row.created)
            for row in self.db.execute(stmt)
        ]

    def delete_by_source(self, source: str) -> int:
        """Delete every product from one source; scores and trends cascade."""
        result = self.db.execute(delete(Product).where(Product.source == source))
        return result.rowcount or 0

    def list_by_ids(self, product_ids: list[int]) -> list[Product]:
        """Fetch products by id in one query rather than a get() per id."""
        if not product_ids:
            return []
        return list(self.db.scalars(select(Product).where(Product.id.in_(product_ids))))

    def list_with_latest_score(self, *, limit: int = 50, offset: int = 0) -> list[ProductRow]:
        """Dashboard listing, highest scored first. Unscored products still appear."""
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
        """Subquery returning the newest row per product_id."""
        return (
            select(model)
            .distinct(model.product_id)
            .order_by(model.product_id, model.created_at.desc(), model.id.desc())
            .subquery()
        )
