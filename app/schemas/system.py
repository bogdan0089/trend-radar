from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    database: str
    llm_provider: str
    llm_enabled: bool
