from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class ScoreRead(BaseModel):
    """Оцінка товару. `score` і `reasoning` — обовʼязкові за ТЗ."""

    model_config = ConfigDict(from_attributes=True)

    score: int = Field(ge=0, le=100)
    reasoning: str
    provider: str
    boost_score: int
    breakdown: dict | None = None
    created_at: datetime


class ProductRead(BaseModel):
    """Сім полів з ТЗ + службові. Назовні віддаємо тільки цю схему,
    ORM-модель за межі сервісного шару не виходить."""

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
    """Рядок дашборду: товар + його остання оцінка + динаміка тренду.

    `score` може бути None — товар щойно спарсили, а скоринг ще не відпрацював.
    Фронт має вміти це показати, а не впасти.
    """

    score: ScoreRead | None = None
    trend_delta_pct: float | None = None


class ProductListResponse(BaseModel):
    items: list[ProductListItem]
    total: int
    limit: int
    offset: int