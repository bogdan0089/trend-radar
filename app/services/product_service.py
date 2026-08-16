"""Читання товарів для дашборду."""

from sqlalchemy.orm import Session

from app.repositories.product import ProductRepository, ProductRow
from app.schemas.product import ProductListItem, ProductListResponse, ScoreRead


class ProductService:
    def __init__(self, db: Session) -> None:
        self.products = ProductRepository(db)

    def list_products(self, *, limit: int = 50, offset: int = 0) -> ProductListResponse:
        rows = self.products.list_with_latest_score(limit=limit, offset=offset)

        return ProductListResponse(
            items=[self._to_item(row) for row in rows],
            total=self.products.count(),
            limit=limit,
            offset=offset,
        )

    @staticmethod
    def _to_item(row: ProductRow) -> ProductListItem:
        """ORM-обʼєкти → плоский DTO. Назовні модель не виходить."""
        item = ProductListItem.model_validate(row.product)
        item.score = ScoreRead.model_validate(row.score) if row.score else None
        item.trend_delta_pct = row.trend_delta_pct
        return item
