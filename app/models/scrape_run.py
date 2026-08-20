from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin

RUN_STATUSES = ("pending", "running", "success", "partial", "failed")
RUN_TRIGGERS = ("manual", "schedule")


class ScrapeRun(TimestampMixin, Base):
    """Pipeline run history, so the dashboard button can show real progress."""

    __tablename__ = "scrape_runs"

    id: Mapped[int] = mapped_column(primary_key=True)

    status: Mapped[str] = mapped_column(String(16), default="pending", index=True, nullable=False)
    trigger: Mapped[str] = mapped_column(String(16), default="manual", nullable=False)

    products_found: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    products_created: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    products_updated: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    trends_collected: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    scores_created: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    celery_task_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return f"<ScrapeRun {self.id} {self.status}>"
