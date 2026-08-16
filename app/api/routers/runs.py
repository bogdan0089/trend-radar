from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.run import ScrapeRunListResponse, ScrapeRunRead
from app.services.pipeline_service import PipelineService

router = APIRouter(prefix="/api/runs", tags=["runs"])


@router.post("", response_model=ScrapeRunRead, status_code=202)
def start_run(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> ScrapeRunRead:
    """Кнопка «Запустити збір трендів».

    202 Accepted, а не 200: робота лише поставлена в чергу і виконається у
    Celery. Відповідь віддається одразу — API на скрапінгу не блокується.
    """
    return ScrapeRunRead.model_validate(PipelineService(db).start_manual_run())


@router.get("/latest", response_model=ScrapeRunRead | None)
def latest_run(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> ScrapeRunRead | None:
    """Останній запуск — панель опитує його, поки статус running."""
    run = PipelineService(db).latest()
    return ScrapeRunRead.model_validate(run) if run else None


@router.get("", response_model=ScrapeRunListResponse)
def list_runs(
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> ScrapeRunListResponse:
    """Історія запусків, від нових до старих."""
    runs = PipelineService(db).recent(limit=limit)
    return ScrapeRunListResponse(items=[ScrapeRunRead.model_validate(r) for r in runs])
