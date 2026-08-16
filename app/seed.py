"""Автоматичний сід при старті API.

Викликається з entrypoint.sh після міграцій. Ідемпотентний: повторний запуск
нічого не дублює. Мета — щоб `docker compose up` не вимагав жодного ручного кроку.
"""

from app.core.config import settings
from app.core.logging import get_logger
from app.db.session import session_scope
from app.repositories.product import ProductRepository
from app.services.auth_service import AuthService
from app.services.scrape_service import ScrapeService

logger = get_logger(__name__)


def seed() -> None:
    logger.info("Сід: старт")

    with session_scope() as db:
        created = AuthService(db).ensure_admin(settings.admin_username, settings.admin_password)
        if created:
            logger.info("Сід: адміна '%s' створено", settings.admin_username)

    with session_scope() as db:
        _seed_demo_products(db)

    logger.info("Сід: готово")


def _seed_demo_products(db) -> None:
    """Наповнює базу з демо-снапшота, якщо товарів ще немає.

    Мета — щоб дашборд не був порожнім одразу після `docker compose up`, ще до
    першого запуску скрапера. Повторний старт нічого не робить: як тільки в базі
    зʼявився хоч один товар, сід мовчки виходить.
    """
    if ProductRepository(db).count() > 0:
        logger.info("Сід: товари вже є — пропускаю")
        return

    outcome = ScrapeService(db).collect_from_snapshot()
    logger.info("Сід: додано %d демо-товарів зі снапшота", outcome.created)


if __name__ == "__main__":
    seed()
