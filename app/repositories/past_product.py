from sqlalchemy import func, select

from app.models.past_product import PastProduct
from app.repositories.base import BaseRepository


class PastProductRepository(BaseRepository[PastProduct]):
    model = PastProduct

    def list_all(self) -> list[PastProduct]:
        """Усі минулі товари — для побудови індексу Boost.

        Без пагінації свідомо: це наша власна історія успішних товарів,
        її десятки-сотні рядків, і алгоритму потрібні всі одразу.
        """
        return list(self.db.scalars(select(PastProduct).order_by(PastProduct.id)))

    def list_page(self, *, limit: int = 50, offset: int = 0) -> list[PastProduct]:
        """Сторінка для UI, від нових до старих."""
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
        """Перевірка дубля перед вставкою.

        Порівнюємо без урахування регістру: користувач імпортує CSV повторно,
        і «Yoga Mat» не має додатися другим рядком поруч із «yoga mat».
        """
        stmt = select(func.count()).select_from(PastProduct).where(
            func.lower(PastProduct.title) == title.strip().lower(),
            func.lower(PastProduct.category) == category.strip().lower(),
        )
        return (self.db.scalar(stmt) or 0) > 0
