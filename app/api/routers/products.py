from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.product import ProductListResponse
from app.services.product_service import ProductService

router = APIRouter(prefix="/api/products", tags=["products"])


@router.get("", response_model=ProductListResponse)
def list_products(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> ProductListResponse:
    """Список товарів з останньою оцінкою. Дашборд ходить сюди.

    `_: User = Depends(get_current_user)` — залежність виконується заради
    побічного ефекту: без валідного токена вона кине 401 і роутер не запуститься.
    Саме тут реалізується вимога ТЗ «обмеження доступу до панелі».
    """
    return ProductService(db).list_products(limit=limit, offset=offset)
