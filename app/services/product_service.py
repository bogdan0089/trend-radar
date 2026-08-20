"""Read side of the dashboard product listing."""

from sqlalchemy.orm import Session

from app.repositories.product import ProductRepository, ProductRow


class ProductService:
    def __init__(self, db: Session) -> None:
        self.products = ProductRepository(db)

    def list_products(
        self, *, limit: int = 50, offset: int = 0
    ) -> tuple[list[ProductRow], int]:
        """Return one page of products with their latest score, plus the total."""
        rows = self.products.list_with_latest_score(limit=limit, offset=offset)
        return rows, self.products.count()
