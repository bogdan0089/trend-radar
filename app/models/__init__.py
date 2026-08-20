"""Model registry. Alembic reads it, so every model must be listed here."""

from app.models.past_product import PastProduct
from app.models.product import Product
from app.models.score import Score
from app.models.scrape_run import ScrapeRun
from app.models.trend import TrendSnapshot
from app.models.user import User

__all__ = [
    "PastProduct",
    "Product",
    "Score",
    "ScrapeRun",
    "TrendSnapshot",
    "User",
]
