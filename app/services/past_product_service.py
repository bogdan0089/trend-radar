"""Our past successful products: manual entry and CSV import."""

import csv
import io
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.exceptions import ValidationError
from app.core.logging import get_logger
from app.models.past_product import PastProduct
from app.repositories.past_product import PastProductRepository
from app.schemas.sales_boost import CsvImportReport, PastProductCreate
from app.utils.keywords import tokenize

logger = get_logger(__name__)

_TITLE_COLUMNS = ("title", "name", "product", "product_name")
_CATEGORY_COLUMNS = ("category", "cat", "niche")
_KEYWORDS_COLUMNS = ("keywords", "tags", "key_words")
_NOTES_COLUMNS = ("notes", "note", "comment", "description")

_MAX_REPORTED_ERRORS = 20
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

    def list_products(
        self, *, limit: int = 50, offset: int = 0
    ) -> tuple[list[PastProduct], int]:
        items = self.past_products.list_page(limit=limit, offset=offset)
        return items, self.past_products.count()

    def create(self, payload: PastProductCreate) -> PastProduct:
        keywords = payload.keywords or self._derive_keywords(payload.title)

        product = self.past_products.create(
            title=payload.title,
            category=payload.category,
            keywords=keywords,
            notes=payload.notes,
            source="manual",
        )
        self.db.commit()
        logger.info("Sales Boost: added product %r manually", payload.title)
        return product

    def import_csv(self, raw: bytes) -> CsvImportReport:
        """Import a CSV. Only title and category are required."""
        if not raw:
            raise ValidationError("The file is empty")
        if len(raw) > _MAX_CSV_BYTES:
            raise ValidationError("The file is larger than 5 MB")

        reader = csv.DictReader(io.StringIO(self._decode(raw)))
        if not reader.fieldnames:
            raise ValidationError("The file has no header row")

        columns = self._map_columns(reader.fieldnames)
        if "title" not in columns or "category" not in columns:
            raise ValidationError(
                "The CSV must contain 'title' and 'category' columns. "
                f"Found: {', '.join(reader.fieldnames)}"
            )

        imported = skipped = 0
        errors: list[str] = []

        for line_number, raw_row in enumerate(reader, start=2):
            try:
                row = self._parse_row(raw_row, columns)
            except ValueError as exc:
                skipped += 1
                self._collect_error(errors, f"row {line_number}: {exc}")
                continue

            if self.past_products.exists(title=row.title, category=row.category):
                skipped += 1
                self._collect_error(errors, f"row {line_number}: duplicate '{row.title}'")
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
        logger.info("Sales Boost: CSV import, added %d, skipped %d", imported, skipped)
        return CsvImportReport(imported=imported, skipped=skipped, errors=errors)

    @staticmethod
    def _decode(raw: bytes) -> str:
        """Decode the upload, tolerating the BOM Excel prepends."""
        try:
            return raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            return raw.decode("cp1251", errors="replace")

    @staticmethod
    def _map_columns(fieldnames: list[str]) -> dict[str, str]:
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
            raise ValueError("empty title")
        if not category:
            raise ValueError("empty category")

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
        """Split 'yoga; mat, fitness' into distinct lowercase words."""
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
        """Derive keywords from the title when the row supplied none."""
        return tokenize(title)[:_DERIVED_KEYWORDS_LIMIT]

    @staticmethod
    def _collect_error(errors: list[str], message: str) -> None:
        if len(errors) < _MAX_REPORTED_ERRORS:
            errors.append(message)
        elif len(errors) == _MAX_REPORTED_ERRORS:
            errors.append("... remaining errors not shown")
