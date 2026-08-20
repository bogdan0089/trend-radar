"""Automatic seeding at API startup. Idempotent."""

from app.core.config import settings
from app.core.logging import get_logger
from app.db.session import session_scope
from app.repositories.past_product import PastProductRepository
from app.repositories.product import ProductRepository
from app.services.auth_service import AuthService
from app.services.scoring_service import ScoringService
from app.services.scrape_service import ScrapeService

logger = get_logger(__name__)

_DEMO_PAST_PRODUCTS = (
    {
        "title": "Anker PowerCore 20000 Portable Power Bank",
        "category": "Electronics",
        "keywords": ["anker", "charger", "usb", "portable"],
        "notes": "Sold through two seasons, best margin in accessories.",
    },
    {
        "title": "Ninja Foodi 6-in-1 Air Fryer",
        "category": "Home & Kitchen",
        "keywords": ["ninja", "air", "fryer", "kitchen"],
        "notes": "Peaked before the winter holidays.",
    },
    {
        "title": "Stanley Insulated Travel Tumbler 30 oz",
        "category": "Sports & Outdoors",
        "keywords": ["stanley", "tumbler", "stainless", "steel"],
        "notes": "Carried by the TikTok wave, still steady.",
    },
    {
        "title": "Wireless Earbuds with Charging Case",
        "category": "Electronics",
        "keywords": ["wireless", "earbuds", "bluetooth", "case"],
        "notes": "High return rate, but the volume covered it.",
    },
    {
        "title": "Non-Slip Yoga Mat 6 mm",
        "category": "Sports & Outdoors",
        "keywords": ["yoga", "mat", "fitness"],
        "notes": "Deliberately matches nothing in the demo snapshot.",
    },
)


def seed() -> None:
    logger.info("Seed: start")

    with session_scope() as db:
        created = AuthService(db).ensure_admin(settings.admin_username, settings.admin_password)
        if created:
            logger.info("Seed: admin '%s' created", settings.admin_username)

    with session_scope() as db:
        _seed_past_products(db)

    with session_scope() as db:
        _seed_demo_products(db)

    logger.info("Seed: done")


def _seed_past_products(db) -> None:
    """Populate the Sales Boost history when it is still empty."""
    repository = PastProductRepository(db)
    if repository.count() > 0:
        logger.info("Seed: past products already present, skipping")
        return

    for entry in _DEMO_PAST_PRODUCTS:
        repository.create(**entry, source="seed")

    db.commit()
    logger.info("Seed: added %d demo past products", len(_DEMO_PAST_PRODUCTS))


def _seed_demo_products(db) -> None:
    """Fill the database from the demo snapshot when no products exist yet."""
    if ProductRepository(db).count() > 0:
        logger.info("Seed: products already present, skipping")
        return

    outcome = ScrapeService(db).collect_from_snapshot()
    logger.info("Seed: added %d demo products from the snapshot", outcome.created)

    if not outcome.product_ids:
        return

    scoring = ScoringService(db, use_llm=False).score_products(outcome.product_ids)
    logger.info("Seed: scored %d demo products with the formula", scoring.created)


if __name__ == "__main__":
    seed()
