from sqlalchemy import select

from app.models.trend import TrendSnapshot
from app.repositories.base import BaseRepository


class TrendRepository(BaseRepository[TrendSnapshot]):
    model = TrendSnapshot

    def latest_by_products(self, product_ids: list[int]) -> dict[int, TrendSnapshot]:
        """Найсвіжіший знімок на кожен товар — одним запитом.

        DISTINCT ON лишає перший рядок у групі за ORDER BY, тож сортування
        від нових до старих дає рівно по одному актуальному знімку.
        """
        if not product_ids:
            return {}

        stmt = (
            select(TrendSnapshot)
            .where(TrendSnapshot.product_id.in_(product_ids))
            .distinct(TrendSnapshot.product_id)
            .order_by(
                TrendSnapshot.product_id,
                TrendSnapshot.created_at.desc(),
                TrendSnapshot.id.desc(),
            )
        )
        return {snapshot.product_id: snapshot for snapshot in self.db.scalars(stmt)}

    def create_snapshot(
        self,
        *,
        product_id: int,
        keyword: str,
        interest_now: float | None = None,
        interest_avg: float | None = None,
        delta_pct: float = 0.0,
        raw_points: list[int] | None = None,
        source: str = "google_trends",
        error: str | None = None,
    ) -> TrendSnapshot:
        """Знімок тренду. Історію не перезаписуємо: кожен збір — новий рядок,
        щоб було видно, як попит змінювався від запуску до запуску."""
        return self.add(
            TrendSnapshot(
                product_id=product_id,
                keyword=keyword[:255],
                interest_now=interest_now,
                interest_avg=interest_avg,
                delta_pct=delta_pct,
                raw_points=raw_points,
                source=source,
                error=error[:500] if error else None,
            )
        )
