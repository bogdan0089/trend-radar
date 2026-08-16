"""Доступ до історії запусків пайплайну.

ScrapeRun — один запуск. Життєвий цикл:
    pending → running → success | partial | failed

Репозиторій не комітить: транзакцією володіє сервіс. Тут максимум flush().
"""

from datetime import UTC, datetime

from sqlalchemy import select

from app.models.scrape_run import ScrapeRun
from app.repositories.base import BaseRepository


class ScrapeRunRepository(BaseRepository[ScrapeRun]):
    model = ScrapeRun

    def create_pending(self, *, trigger: str, celery_task_id: str | None = None) -> ScrapeRun:
        """Новий запуск у статусі 'pending'. Лічильники беруть дефолти з моделі."""
        return self.add(
            ScrapeRun(status="pending", trigger=trigger, celery_task_id=celery_task_id)
        )

    def mark_running(self, run: ScrapeRun) -> ScrapeRun:
        """Об'єкт уже під наглядом сесії — досить присвоїти поля.
        UPDATE SQLAlchemy згенерує сам при flush."""
        run.status = "running"
        run.started_at = datetime.now(UTC)
        self.db.flush()
        return run

    def mark_finished(
        self,
        run: ScrapeRun,
        *,
        status: str,
        error: str | None = None,
        products_found: int = 0,
        products_created: int = 0,
        products_updated: int = 0,
        trends_collected: int = 0,
        scores_created: int = 0,
    ) -> ScrapeRun:
        """Фінальний статус + лічильники + finished_at."""
        run.status = status
        run.error = error
        run.products_found = products_found
        run.products_created = products_created
        run.products_updated = products_updated
        run.trends_collected = trends_collected
        run.scores_created = scores_created
        run.finished_at = datetime.now(UTC)
        self.db.flush()
        return run

    def get_last(self) -> ScrapeRun | None:
        """Найсвіжіший запуск — для кнопки в панелі."""
        stmt = select(ScrapeRun).order_by(ScrapeRun.id.desc()).limit(1)
        return self.db.scalar(stmt)

    def list_recent(self, *, limit: int = 20) -> list[ScrapeRun]:
        """Історія запусків, від нових до старих.

        id.desc(), а не created_at: два запуски в ту саму секунду дали б
        однаковий created_at і недетермінований порядок.
        """
        stmt = select(ScrapeRun).order_by(ScrapeRun.id.desc()).limit(limit)
        return list(self.db.scalars(stmt))
