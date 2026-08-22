from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import api_router
from app.core.config import settings
from app.core.exceptions import DomainError
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


@app.exception_handler(DomainError)
def domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
    if exc.http_status_code >= 500:
        logger.exception("Unhandled domain error at %s", request.url.path)

    # RFC 9110 requires a 401 to name the scheme the client should use.
    headers = {"WWW-Authenticate": "Bearer"} if exc.http_status_code == 401 else None

    return JSONResponse(
        status_code=exc.http_status_code,
        content={"detail": str(exc)},
        headers=headers,
    )


app.include_router(api_router)
