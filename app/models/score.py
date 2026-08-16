from sqlalchemy import CheckConstraint, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin

# Хто порахував оцінку. fallback = детермінована формула без LLM.
SCORE_PROVIDERS = ("anthropic", "openai", "fallback")


class Score(TimestampMixin, Base):
    __tablename__ = "scores"
    __table_args__ = (
        CheckConstraint("score >= 0 AND score <= 100", name="ck_scores_range"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), index=True, nullable=False
    )

    # Обовʼязкові за ТЗ
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    reasoning: Mapped[str] = mapped_column(Text, nullable=False)

    provider: Mapped[str] = mapped_column(String(32), default="fallback", nullable=False)
    # Розклад балу по складниках — і для UI, і щоб оцінку можна було перевірити
    breakdown: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    boost_score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    product = relationship("Product", back_populates="scores")

    def __repr__(self) -> str:
        return f"<Score product={self.product_id} {self.score} by {self.provider}>"
