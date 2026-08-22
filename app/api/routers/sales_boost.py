from fastapi import APIRouter, Depends, File, Query, UploadFile
from sqlalchemy.orm import Session

from app.api.dependencies.auth import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.sales_boost import (
    CsvImportReport,
    PastProductCreate,
    PastProductListResponse,
    PastProductRead,
)
from app.services.past_product_service import PastProductService

router_sales_boost = APIRouter(prefix="/api/sales-boost", tags=["sales-boost"])


@router_sales_boost.get("", response_model=PastProductListResponse)
def list_past_products(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> PastProductListResponse:
    """Our past successful products."""
    items, total = PastProductService(session).list_products(limit=limit, offset=offset)
    return PastProductListResponse(
        items=[PastProductRead.model_validate(item) for item in items],
        total=total,
    )


@router_sales_boost.post("", response_model=PastProductRead, status_code=201)
def create_past_product(
    payload: PastProductCreate,
    session: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> PastProductRead:
    """Manual entry from the Sales Boost form."""
    return PastProductRead.model_validate(PastProductService(session).create(payload))


@router_sales_boost.post("/import-csv", response_model=CsvImportReport)
def import_csv(
    file: UploadFile = File(...),
    session: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> CsvImportReport:
    """CSV import; a partial import is reported, not raised."""
    return PastProductService(session).import_csv(file.file.read())
