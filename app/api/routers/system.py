from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.system import HealthResponse
from app.services.system_service import SystemService

router_system = APIRouter(prefix="/api", tags=["system"])


@router_system.get("/health", response_model=HealthResponse)
def health(session: Session = Depends(get_db)) -> HealthResponse:
    """Liveness of the API and its database, plus the active scoring mode."""
    status = SystemService(session).health()
    return HealthResponse(
        status="ok" if status.database_ok else "degraded",
        database="ok" if status.database_ok else "unreachable",
        llm_provider=status.llm_provider,
        llm_enabled=status.llm_enabled,
    )
