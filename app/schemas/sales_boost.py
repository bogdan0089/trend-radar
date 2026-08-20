from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PastProductCreate(BaseModel):
    """Payload of the manual form on the Sales Boost page."""

    title: str = Field(min_length=1, max_length=500)
    category: str = Field(min_length=1, max_length=255)
    keywords: list[str] = Field(default_factory=list)
    notes: str | None = Field(default=None, max_length=2000)

    @field_validator("title", "category")
    @classmethod
    def strip_text(cls, value: str) -> str:
        """Trim surrounding whitespace and reject a blank value."""
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("The field cannot consist only of whitespace")
        return cleaned

    @field_validator("keywords")
    @classmethod
    def normalize_keywords(cls, values: list[str]) -> list[str]:
        """Lowercase, drop blanks and duplicates, trim to the column width."""
        seen: set[str] = set()
        result: list[str] = []
        for raw in values:
            word = raw.strip().lower()[:64]
            if word and word not in seen:
                seen.add(word)
                result.append(word)
        return result


class PastProductRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    category: str
    keywords: list[str]
    notes: str | None
    source: str
    created_at: datetime


class PastProductListResponse(BaseModel):
    items: list[PastProductRead]
    total: int


class CsvImportReport(BaseModel):
    """Import summary: what was stored, what was skipped and why."""

    imported: int
    skipped: int
    errors: list[str] = Field(default_factory=list)
