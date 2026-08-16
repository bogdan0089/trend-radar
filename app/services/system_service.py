from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import get_logger
from app.repositories.health import HealthRepository
from app.schemas.system import HealthResponse

logger = get_logger(__name__)


class SystemService:
    def __init__(self, db: Session) -> None:
        self.health_repo = HealthRepository(db)

    def health(self) -> HealthResponse:
        try:
            self.health_repo.ping()
            db_ok = True
        except Exception:  # noqa: BLE001 — health не має падати сам
            logger.exception("health: база недоступна")
            db_ok = False

        return HealthResponse(
            status="ok" if db_ok else "degraded",
            database="ok" if db_ok else "unreachable",
            llm_provider=settings.llm_provider,
            llm_enabled=settings.llm_enabled,
        )
