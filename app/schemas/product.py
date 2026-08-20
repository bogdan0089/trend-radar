from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from app.repositories.product import ProductRow


class ScoreRead(BaseModel):
    """A product rating with its explanation."""

    model_config = ConfigDict(from_attributes=True)

    score: int = Field(ge=0, le=100)
    reasoning: str
    provider: str
    boost_score: int
    breakdown: dict | None = None
    created_at: datetime


class ProductRead(BaseModel):
    """A product as the API returns it."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    asin: str

    title: str
    category: str
    price: Decimal | None
    rating: float | None
    reviews_count: int
    product_url: str
    image_url: str | None

    currency: str
    first_seen_at: datetime
    last_seen_at: datetime


class ProductListItem(ProductRead):
    """Dashboard row: a product with its latest score and trend movement."""

    score: ScoreRead | None = None
    trend_delta_pct: float | None = None

    @classmethod
    def from_row(cls, row: "ProductRow") -> "ProductListItem":
        """Flatten a repository row into the response schema."""
        item = cls.model_validate(row.product)
        item.score = ScoreRead.model_validate(row.score) if row.score else None
        item.trend_delta_pct = row.trend_delta_pct
        return item


class ProductListResponse(BaseModel):
    items: list[ProductListItem]
    total: int
    limit: int
    offset: int
