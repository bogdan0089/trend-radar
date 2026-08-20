from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import api_router
from app.core.config import settings
from app.core.exceptions import (
    AlreadyExistsError,
    DomainError,
    InvalidCredentialsError,
    NotFoundError,
    ValidationError,
)
from app.core.logging import configure_logging, get_logger

configure_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    logger.info("Trend Radar API started")
    yield
    logger.info("Trend Radar API stopped")


app = FastAPI(
    title="Trend Radar API",
    description="Scraping, AI scoring and analytics for trending products",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_STATUS_BY_ERROR: list[tuple[type[DomainError], int]] = [
    (NotFoundError, 404),
    (AlreadyExistsError, 409),
    (InvalidCredentialsError, 401),
    (ValidationError, 422),
]


@app.exception_handler(DomainError)
def domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
    status = next((s for err, s in _STATUS_BY_ERROR if isinstance(exc, err)), 400)
    if status >= 500:
        logger.exception("Unhandled domain error at %s", request.url.path)
    return JSONResponse(status_code=status, content={"detail": str(exc)})


app.include_router(api_router)
