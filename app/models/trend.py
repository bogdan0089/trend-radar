from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin

# Джерело даних. `unavailable` = Google Trends заблокував або не віддав віджет;
# це не помилка, а зафіксований факт, який скоринг враховує окремо.
TREND_SOURCES = ("google_trends", "unavailable")


class TrendSnapshot(TimestampMixin, Base):
    __tablename__ = "trend_snapshots"
    __table_args__ = (Index("ix_trend_snapshots_product_collected", "product_id", "collected_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), index=True, nullable=False
    )

    keyword: Mapped[str] = mapped_column(String(255), nullable=False)
    interest_now: Mapped[float | None] = mapped_column(Float, nullable=True)
    interest_avg: Mapped[float | None] = mapped_column(Float, nullable=True)
    delta_pct: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    raw_points: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    source: Mapped[str] = mapped_column(String(32), default="google_trends", nullable=False)
    error: Mapped[str | None] = mapped_column(String(500), nullable=True)

    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    product = relationship("Product", back_populates="trend_snapshots")

    def __repr__(self) -> str:
        return f"<TrendSnapshot product={self.product_id} delta={self.delta_pct}>"
