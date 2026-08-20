"""Service health reporting."""

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import get_logger
from app.repositories.health import HealthRepository

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class HealthStatus:
    """Outcome of the health check."""

    database_ok: bool
    llm_provider: str
    llm_enabled: bool


class SystemService:
    def __init__(self, db: Session) -> None:
        self.health_repo = HealthRepository(db)

    def health(self) -> HealthStatus:
        """Report service state; never raises, a failed ping degrades the status."""
        try:
            self.health_repo.ping()
            database_ok = True
        except Exception:
            logger.exception("health: database unreachable")
            database_ok = False

        return HealthStatus(
            database_ok=database_ok,
            llm_provider=settings.llm_provider,
            llm_enabled=settings.llm_enabled,
        )
