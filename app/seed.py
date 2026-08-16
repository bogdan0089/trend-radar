"""Автоматичний сід при старті API.

Викликається з entrypoint.sh після міграцій. Ідемпотентний: повторний запуск
нічого не дублює. Мета — щоб `docker compose up` не вимагав жодного ручного кроку.
"""

from app.core.config import settings
from app.core.logging import get_logger
from app.db.session import session_scope
from app.services.auth_service import AuthService

logger = get_logger(__name__)


def seed() -> None:
    logger.info("Сід: старт")

    with session_scope() as db:
        created = AuthService(db).ensure_admin(settings.admin_username, settings.admin_password)
        if created:
            logger.info("Сід: адміна '%s' створено", settings.admin_username)

    logger.info("Сід: готово")


if __name__ == "__main__":
    seed()
