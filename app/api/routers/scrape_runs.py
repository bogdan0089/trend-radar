from datetime import timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.dependencies.auth import get_current_user, is_admin
from app.core.config import settings
from app.db.session import get_db
from app.models.user import User
from app.schemas.scrape_run import ScrapeRunListResponse, ScrapeRunRead
from app.services.pipeline_service import PipelineService

router_scrape_runs = APIRouter(prefix="/api/scrape-runs", tags=["scrape-runs"])


@router_scrape_runs.post("", response_model=ScrapeRunRead, status_code=202)
def start_run(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ScrapeRunRead:
    """Queue a pipeline run and return at once, without blocking on scraping.

    Visitors share one server with every other project on it, so a run they start
    waits out a cooldown after the previous one. The admin is not limited.
    """
    cooldown = None if is_admin(user) else timedelta(minutes=settings.visitor_run_cooldown_minutes)
    return ScrapeRunRead.model_validate(PipelineService(db).start_manual_run(cooldown=cooldown))


@router_scrape_runs.get("/latest", response_model=ScrapeRunRead | None)
def latest_run(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> ScrapeRunRead | None:
    """Latest run; the dashboard polls it while the status is running."""
    run = PipelineService(db).latest()
    return ScrapeRunRead.model_validate(run) if run else None


@router_scrape_runs.get("", response_model=ScrapeRunListResponse)
def list_runs(
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> ScrapeRunListResponse:
    """Run history, newest first."""
    runs = PipelineService(db).recent(limit=limit)
    return ScrapeRunListResponse(items=[ScrapeRunRead.model_validate(r) for r in runs])
