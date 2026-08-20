from sqlalchemy import func, select

from app.models.past_product import PastProduct
from app.repositories.base import BaseRepository


class PastProductRepository(BaseRepository[PastProduct]):
    model = PastProduct

    def list_all(self) -> list[PastProduct]:
        """Every past product, unpaginated, used to build the boost index."""
        return list(self.db.scalars(select(PastProduct).order_by(PastProduct.id)))

    def list_page(self, *, limit: int = 50, offset: int = 0) -> list[PastProduct]:
        stmt = select(PastProduct).order_by(PastProduct.id.desc()).limit(limit).offset(offset)
        return list(self.db.scalars(stmt))

    def create(
        self,
        *,
        title: str,
        category: str,
        keywords: list[str],
        notes: str | None = None,
        source: str = "manual",
    ) -> PastProduct:
        return self.add(
            PastProduct(
                title=title,
                category=category,
                keywords=keywords,
                notes=notes,
                source=source,
            )
        )

    def exists(self, *, title: str, category: str) -> bool:
        """Case-insensitive duplicate check, so re-importing a CSV is a no-op."""
        stmt = select(func.count()).select_from(PastProduct).where(
            func.lower(PastProduct.title) == title.strip().lower(),
            func.lower(PastProduct.category) == category.strip().lower(),
        )
        return (self.db.scalar(stmt) or 0) > 0
