from fastapi import APIRouter, Depends, File, Query, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.past_product import (
    CsvImportReport,
    PastProductCreate,
    PastProductListResponse,
    PastProductRead,
)
from app.services.past_product_service import PastProductService

router = APIRouter(prefix="/api/past-products", tags=["sales-boost"])


@router.get("", response_model=PastProductListResponse)
def list_past_products(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> PastProductListResponse:
    """Список наших успішних минулих товарів."""
    return PastProductService(db).list_products(limit=limit, offset=offset)


@router.post("", response_model=PastProductRead, status_code=201)
def create_past_product(
    payload: PastProductCreate,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> PastProductRead:
    """Ручне додавання через форму (ТЗ, п.3)."""
    return PastProductService(db).create(payload)


@router.post("/import-csv", response_model=CsvImportReport)
def import_csv(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> CsvImportReport:
    """Імпорт CSV (ТЗ, п.3).

    Повертає 200 навіть із помилками всередині звіту: частковий успіх — це
    нормальний результат імпорту, а не збій запиту.
    """
    return PastProductService(db).import_csv(file.file.read())
