"""Оркестрація повного циклу: скрапінг → тренди → скоринг.

Той самий сервіс обслуговує і ручний запуск із панелі, і розклад Celery Beat.
Кожен етап пише свій результат у ScrapeRun, тож кнопка в інтерфейсі показує
реальний стан, а не спінер у нікуди.
"""

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.exceptions import DomainError, ExternalServiceError, NotFoundError
from app.core.logging import get_logger
from app.models.scrape_run import ScrapeRun
from app.repositories.scrape_run import ScrapeRunRepository
from app.services.scoring_service import ScoringService
from app.services.scrape_service import ScrapeService
from app.services.trends_service import TrendsService

logger = get_logger(__name__)


@dataclass
class _Counters:
    products_found: int = 0
    products_created: int = 0
    products_updated: int = 0
    trends_collected: int = 0
    scores_created: int = 0


class PipelineService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.runs = ScrapeRunRepository(db)

    # ------------------------------------------------------------ запуск

    def create_run(self, *, trigger: str) -> ScrapeRun:
        """Створює запис запуску ДО постановки в чергу.

        Так у відповіді роутера вже є run_id, і панель одразу може показати
        «збір поставлено в чергу», навіть якщо воркер зайнятий.
        """
        run = self.runs.create_pending(trigger=trigger)
        self.db.commit()
        logger.info("Пайплайн: створено запуск %d (trigger=%s)", run.id, trigger)
        return run

    def attach_task_id(self, run: ScrapeRun, task_id: str) -> None:
        run.celery_task_id = task_id
        self.db.commit()

    def start_manual_run(self) -> ScrapeRun:
        """Кнопка «Запустити збір трендів» у панелі.

        Ставить задачу в чергу і одразу повертає керування — API не блокується
        на скрапінгу (вимога ТЗ до архітектури).
        """
        if (active := self.active_run()) is not None:
            # Другий скрапінг паралельно з першим дав би подвійне навантаження
            # на Amazon і гонку за той самий ASIN. Повертаємо поточний запуск.
            logger.info("Пайплайн: запуск %d ще працює — новий не створюю", active.id)
            return active

        run = self.create_run(trigger="manual")

        # Імпорт локальний: app.tasks.pipeline імпортує цей сервіс, і на рівні
        # модуля вийшов би цикл імпортів.
        from app.tasks.pipeline import run_pipeline

        try:
            async_result = run_pipeline.delay(run_id=run.id, trigger="manual")
        except Exception as exc:  # noqa: BLE001 — брокер недоступний
            logger.exception("Пайплайн: не вдалося поставити запуск %d у чергу", run.id)
            self.runs.mark_finished(
                run, status="failed", error=f"Черга недоступна: {exc}"[:2000]
            )
            self.db.commit()
            raise ExternalServiceError("Черга задач недоступна, спробуйте пізніше") from exc

        self.attach_task_id(run, async_result.id)
        return run

    def active_run(self) -> ScrapeRun | None:
        """Запуск, який ще не завершився."""
        last = self.runs.get_last()
        return last if last is not None and last.status in ("pending", "running") else None

    def latest(self) -> ScrapeRun | None:
        return self.runs.get_last()

    def recent(self, *, limit: int = 20) -> list[ScrapeRun]:
        return self.runs.list_recent(limit=limit)

    # ------------------------------------------------------------ виконання

    def execute(self, run_id: int) -> ScrapeRun:
        """Виконує пайплайн. Викликається з Celery-таски.

        Виняток усередині не «губиться»: він записується у ScrapeRun зі статусом
        failed і тільки потім піднімається далі — щоб Celery теж його побачив.
        """
        run = self.runs.get(run_id)
        if run is None:
            raise NotFoundError(f"Запуск {run_id} не знайдено")

        self.runs.mark_running(run)
        self.db.commit()

        counters = _Counters()
        try:
            counters, used_snapshot = self._run_stages(counters)
        except DomainError as exc:
            logger.exception("Пайплайн %d впав", run_id)
            self.runs.mark_finished(run, status="failed", error=str(exc)[:2000])
            self.db.commit()
            raise

        status, note = self._resolve_status(counters, used_snapshot=used_snapshot)
        self.runs.mark_finished(
            run,
            status=status,
            error=note,
            products_found=counters.products_found,
            products_created=counters.products_created,
            products_updated=counters.products_updated,
            trends_collected=counters.trends_collected,
            scores_created=counters.scores_created,
        )
        self.db.commit()

        logger.info("Пайплайн %d завершено зі статусом %s", run_id, status)
        return run

    def _run_stages(self, counters: _Counters) -> tuple[_Counters, bool]:
        scrape = ScrapeService(self.db).collect()
        counters.products_found = scrape.found
        counters.products_created = scrape.created
        counters.products_updated = scrape.updated

        if not scrape.product_ids:
            return counters, scrape.used_snapshot

        trends = TrendsService(self.db).collect_for_products(scrape.product_ids)
        counters.trends_collected = trends.collected

        scoring = ScoringService(self.db).score_products(scrape.product_ids)
        counters.scores_created = scoring.created

        return counters, scrape.used_snapshot

    @staticmethod
    def _resolve_status(counters: _Counters, *, used_snapshot: bool) -> tuple[str, str | None]:
        """Успіх — тільки коли реально зібрали живі дані.

        Робота зі снапшота показує товари в панелі, але це НЕ успішний збір:
        якщо позначити його 'success', ніхто не помітить, що скрапер заблокований.
        """
        if used_snapshot:
            return "partial", "Amazon заблокував запит — дані взято з демо-снапшота"
        if counters.products_found == 0:
            return "partial", "Сторінка відкрилась, але жодного товару не розібрано"
        return "success", None
