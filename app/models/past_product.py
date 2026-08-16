from sqlalchemy import String, Text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin


class PastProduct(TimestampMixin, Base):
    """«Наш успішний минулий товар» — джерело Internal Sales Boost.

    Заповнюється вручну через форму або імпортом CSV.
    """

    __tablename__ = "past_products"

    id: Mapped[int] = mapped_column(primary_key=True)

    title: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    # Нормалізовані ключові слова (нижній регістр) — за ними шукаємо перетин
    keywords: Mapped[list[str]] = mapped_column(ARRAY(String(64)), default=list, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(16), default="manual", nullable=False)  # manual | csv

    def __repr__(self) -> str:
        return f"<PastProduct {self.title[:30]!r} {self.category}>"
