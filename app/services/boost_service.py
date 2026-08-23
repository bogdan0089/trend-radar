"""Internal Sales Boost: extra points for resembling our past winners."""

from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.repositories.past_product import PastProductRepository
from app.utils.keywords import overlap, tokenize

logger = get_logger(__name__)

CATEGORY_MATCH_POINTS = 10
KEYWORD_MATCH_POINTS = 6
MAX_KEYWORD_POINTS = 20
MAX_BOOST = 30


@dataclass(frozen=True, slots=True)
class PastEntry:
    """A past successful product reduced to what the comparison needs."""

    title: str
    category: str
    keywords: list[str]


@dataclass
class BoostResult:
    score: int = 0
    matched_category: str | None = None
    matched_keywords: list[str] = field(default_factory=list)
    matched_titles: list[str] = field(default_factory=list)

    def explain(self) -> str:
        if self.score == 0:
            return "No matches with our past products."

        parts = []
        if self.matched_category:
            parts.append(f"category matches '{self.matched_category}'")
        if self.matched_keywords:
            words = ", ".join(sorted(self.matched_keywords)[:5])
            parts.append(f"shared words: {words}")

        titles = ", ".join(f"'{t}'" for t in self.matched_titles[:3])
        return f"Boost +{self.score}: {'; '.join(parts)}. Similar past products: {titles}."


def calculate_boost(*, title: str, category: str, past: list[PastEntry]) -> BoostResult:
    """Compute the boost for one product. Points are awarded once per fact."""
    if not past:
        return BoostResult()

    product_tokens = tokenize(f"{title} {category}")

    matched_category: str | None = None
    matched_keywords: set[str] = set()
    matched_titles: list[str] = []

    for entry in past:
        category_hit = _category_matches(category, entry.category)
        keyword_hits = overlap(product_tokens, entry.keywords or tokenize(entry.title))

        if not category_hit and not keyword_hits:
            continue

        if category_hit and matched_category is None:
            matched_category = entry.category
        matched_keywords |= keyword_hits
        matched_titles.append(entry.title)

    keyword_points = min(len(matched_keywords) * KEYWORD_MATCH_POINTS, MAX_KEYWORD_POINTS)
    category_points = CATEGORY_MATCH_POINTS if matched_category else 0

    return BoostResult(
        score=min(category_points + keyword_points, MAX_BOOST),
        matched_category=matched_category,
        matched_keywords=sorted(matched_keywords),
        matched_titles=matched_titles,
    )


def _category_matches(left: str, right: str) -> bool:
    """Match categories by whole words, not by raw substring.

    One category legitimately contains the other: Amazon labels a page "Best
    Sellers in Electronics" while our history stores "Electronics". Comparing
    the raw strings did that, but it also matched "Art" inside "Smart Home",
    "Pet" inside "Carpet Care" and "Tea" inside "Steam Cleaning", handing out
    the category points for nothing.
    """
    a, b = set(tokenize(left)), set(tokenize(right))
    if not a or not b:
        return False
    return a <= b or b <= a


class BoostService:
    def __init__(self, db: Session) -> None:
        self.past_products = PastProductRepository(db)
        self._index: list[PastEntry] | None = None

    def index(self) -> list[PastEntry]:
        """Load past products once per run and cache them."""
        if self._index is None:
            self._index = [
                PastEntry(title=p.title, category=p.category, keywords=list(p.keywords or []))
                for p in self.past_products.list_all()
            ]
            logger.info("Boost: loaded %d past products", len(self._index))
        return self._index

    def calculate(self, *, title: str, category: str) -> BoostResult:
        return calculate_boost(title=title, category=category, past=self.index())
