"""Celery-таска повного циклу.

Викликається двома шляхами:
  * кнопкою «Запустити збір трендів» у панелі (trigger='manual');
  * Celery Beat кожні 6 годин (trigger='schedule', ТЗ п.1).

Таска свідомо тонка. Уся логіка — у PipelineService, той самий код виконується
і під HTTP, і під Celery.
"""

import time

from app.celery_app import celery
from app.core.logging import get_logger
from app.db.session import session_scope
from app.services.pipeline_service import PipelineService

logger = get_logger(__name__)


@celery.task(name="app.tasks.pipeline.run_pipeline", bind=True)
def run_pipeline(self, run_id: int | None = None, trigger: str = "manual") -> dict:
    """Скрапінг → тренди → скоринг.

    `run_id` передає роутер, який уже створив запис запуску. Beat запускає таску
    без нього — тоді запис створюється тут.
    """
    started = time.monotonic()
    logger.info("Таска run_pipeline: старт (run_id=%s, trigger=%s)", run_id, trigger)

    with session_scope() as db:
        service = PipelineService(db)

        if run_id is None:
            run = service.create_run(trigger=trigger)
            run_id = run.id
            service.attach_task_id(run, self.request.id or "")

        run = service.execute(run_id)
        result = {
            "run_id": run.id,
            "status": run.status,
            "products_found": run.products_found,
            "scores_created": run.scores_created,
        }

    logger.info(
        "Таска run_pipeline: фініш за %.1f с — %s",
        time.monotonic() - started,
        result,
    )
    return result
