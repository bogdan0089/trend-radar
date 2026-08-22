from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.dependencies.auth import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.product import ProductListItem, ProductListResponse
from app.services.product_service import ProductService

router_products = APIRouter(prefix="/api/products", tags=["products"])


@router_products.get("", response_model=ProductListResponse)
def list_products(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> ProductListResponse:
    """Products with their latest score, as the dashboard reads them."""
    rows, total = ProductService(session).list_products(limit=limit, offset=offset)
    return ProductListResponse(
        items=[ProductListItem.from_row(row) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
    )
