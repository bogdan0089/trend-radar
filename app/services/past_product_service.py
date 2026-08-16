"""Наші минулі успішні товари: ручне додавання і імпорт CSV.

Головне рішення щодо CSV: імпорт толерантний. Один битий рядок не валить файл —
користувач отримує те, що вдалося прочитати, плюс список проблем. Кинути 400 на
весь файл через одну порожню назву — найгірший з можливих варіантів.
"""

import csv
import io
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.exceptions import ValidationError
from app.core.logging import get_logger
from app.repositories.past_product import PastProductRepository
from app.schemas.past_product import (
    CsvImportReport,
    PastProductCreate,
    PastProductListResponse,
    PastProductRead,
)
from app.services.keywords import tokenize

logger = get_logger(__name__)

# Люди називають колонки по-різному, а падати через 'name' замість 'title' безглуздо.
_TITLE_COLUMNS = ("title", "name", "product", "product_name")
_CATEGORY_COLUMNS = ("category", "cat", "niche")
_KEYWORDS_COLUMNS = ("keywords", "tags", "key_words")
_NOTES_COLUMNS = ("notes", "note", "comment", "description")

# Скільки помилок показуємо. На файлі в 10 000 битих рядків повний список
# роздув би відповідь до мегабайтів і нічим би не допоміг.
_MAX_REPORTED_ERRORS = 20

# Скільки слів беремо з назви, коли колонки keywords немає
_DERIVED_KEYWORDS_LIMIT = 8

_MAX_CSV_BYTES = 5 * 1024 * 1024


@dataclass
class _Row:
    title: str
    category: str
    keywords: list[str]
    notes: str | None


class PastProductService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.past_products = PastProductRepository(db)

    # ------------------------------------------------------------------ читання

    def list_products(self, *, limit: int = 50, offset: int = 0) -> PastProductListResponse:
        items = self.past_products.list_page(limit=limit, offset=offset)
        return PastProductListResponse(
            items=[PastProductRead.model_validate(item) for item in items],
            total=self.past_products.count(),
        )

    # ------------------------------------------------------------------- запис

    def create(self, payload: PastProductCreate) -> PastProductRead:
        """Ручне додавання через форму."""
        keywords = payload.keywords or self._derive_keywords(payload.title)

        product = self.past_products.create(
            title=payload.title,
            category=payload.category,
            keywords=keywords,
            notes=payload.notes,
            source="manual",
        )
        self.db.commit()
        logger.info("Sales Boost: додано товар %r вручну", payload.title)
        return PastProductRead.model_validate(product)

    def import_csv(self, raw: bytes) -> CsvImportReport:
        """Імпорт CSV. Обовʼязкові колонки — title і category, решта опційні."""
        if not raw:
            raise ValidationError("Файл порожній")
        if len(raw) > _MAX_CSV_BYTES:
            raise ValidationError("Файл більший за 5 МБ")

        reader = csv.DictReader(io.StringIO(self._decode(raw)))
        if not reader.fieldnames:
            raise ValidationError("У файлі немає рядка заголовків")

        columns = self._map_columns(reader.fieldnames)
        if "title" not in columns or "category" not in columns:
            raise ValidationError(
                "У CSV мають бути колонки 'title' і 'category'. "
                f"Знайдено: {', '.join(reader.fieldnames)}"
            )

        imported = skipped = 0
        errors: list[str] = []

        # enumerate з 2: рядок 1 — заголовки, тож нумерація збігається з тим,
        # що користувач бачить у своєму редакторі таблиць.
        for line_number, raw_row in enumerate(reader, start=2):
            try:
                row = self._parse_row(raw_row, columns)
            except ValueError as exc:
                skipped += 1
                self._collect_error(errors, f"рядок {line_number}: {exc}")
                continue

            if self.past_products.exists(title=row.title, category=row.category):
                skipped += 1
                self._collect_error(errors, f"рядок {line_number}: дубль «{row.title}»")
                continue

            self.past_products.create(
                title=row.title,
                category=row.category,
                keywords=row.keywords,
                notes=row.notes,
                source="csv",
            )
            imported += 1

        self.db.commit()
        logger.info("Sales Boost: імпорт CSV — додано %d, пропущено %d", imported, skipped)
        return CsvImportReport(imported=imported, skipped=skipped, errors=errors)

    # --------------------------------------------------------------- внутрішнє

    @staticmethod
    def _decode(raw: bytes) -> str:
        """utf-8-sig прибирає BOM, який Excel дописує на початок файлу —
        інакше перша колонка називалась би '﻿title' і не знайшлась би."""
        try:
            return raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            # Excel під Windows часто зберігає в cp1251
            return raw.decode("cp1251", errors="replace")

    @staticmethod
    def _map_columns(fieldnames: list[str]) -> dict[str, str]:
        """Реальні заголовки файлу → наші назви полів."""
        mapping: dict[str, str] = {}
        for name in fieldnames:
            key = (name or "").strip().lower()
            if key in _TITLE_COLUMNS:
                mapping.setdefault("title", name)
            elif key in _CATEGORY_COLUMNS:
                mapping.setdefault("category", name)
            elif key in _KEYWORDS_COLUMNS:
                mapping.setdefault("keywords", name)
            elif key in _NOTES_COLUMNS:
                mapping.setdefault("notes", name)
        return mapping

    def _parse_row(self, raw_row: dict, columns: dict[str, str]) -> _Row:
        title = (raw_row.get(columns["title"]) or "").strip()
        category = (raw_row.get(columns["category"]) or "").strip()

        if not title:
            raise ValueError("порожня назва")
        if not category:
            raise ValueError("порожня категорія")

        keywords = self._split_keywords(raw_row.get(columns.get("keywords", ""), ""))
        notes = (raw_row.get(columns.get("notes", ""), "") or "").strip() or None

        return _Row(
            title=title[:500],
            category=category[:255],
            keywords=keywords or self._derive_keywords(title),
            notes=notes,
        )

    @staticmethod
    def _split_keywords(value: str | None) -> list[str]:
        """'yoga; mat, fitness' → ['yoga', 'mat', 'fitness'].

        Приймаємо і крапку з комою, і кому: у CSV кома вже роздільник колонок,
        тож люди частіше пишуть крапку з комою, але не завжди.
        """
        if not value:
            return []

        seen: set[str] = set()
        result: list[str] = []
        for chunk in value.replace(";", ",").split(","):
            word = chunk.strip().lower()[:64]
            if word and word not in seen:
                seen.add(word)
                result.append(word)
        return result

    @staticmethod
    def _derive_keywords(title: str) -> list[str]:
        """Коли слів не вказали — беремо їх із назви.

        Без цього товар без keywords не дав би жодного збігу і Boost для нього
        завжди був би нулем, хоча користувач його додав саме заради збігів.
        """
        return tokenize(title)[:_DERIVED_KEYWORDS_LIMIT]

    @staticmethod
    def _collect_error(errors: list[str], message: str) -> None:
        if len(errors) < _MAX_REPORTED_ERRORS:
            errors.append(message)
        elif len(errors) == _MAX_REPORTED_ERRORS:
            errors.append("... решта помилок не показана")
