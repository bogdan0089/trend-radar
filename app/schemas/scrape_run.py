from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ScrapeRunRead(BaseModel):
    """State of one pipeline run, polled by the dashboard."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    status: str
    trigger: str

    products_found: int
    products_created: int
    products_updated: int
    trends_collected: int
    scores_created: int

    error: str | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime


class ScrapeRunListResponse(BaseModel):
    items: list[ScrapeRunRead]
