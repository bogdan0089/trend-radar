from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PastProductCreate(BaseModel):
    """Ручне додавання через форму на сторінці Sales Boost."""

    title: str = Field(min_length=1, max_length=500)
    category: str = Field(min_length=1, max_length=255)
    keywords: list[str] = Field(default_factory=list)
    notes: str | None = Field(default=None, max_length=2000)

    @field_validator("title", "category")
    @classmethod
    def strip_text(cls, value: str) -> str:
        """' Yoga Mat ' → 'Yoga Mat'. Пробіли по краях ламали б порівняння дублів."""
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Поле не може складатись лише з пробілів")
        return cleaned

    @field_validator("keywords")
    @classmethod
    def normalize_keywords(cls, values: list[str]) -> list[str]:
        """Нижній регістр, без порожніх і дублів, не довші за колонку (64).

        Boost порівнює слова точним збігом, тож 'Yoga' і 'yoga' мають стати
        одним словом ще до збереження.
        """
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
    """Звіт імпорту.

    Битий рядок не валить увесь файл: користувач має отримати те, що вдалося
    прочитати, і список проблем — а не 400 без пояснень.
    """

    imported: int
    skipped: int
    errors: list[str] = Field(default_factory=list)
