"""Internal Sales Boost — додатковий бал за схожість із нашими минулими хітами.

Вимога ТЗ: «Якщо вхідний товар збігається за категорією АБО ключовими словами
з нашими минулими товарами — алгоритм додає йому додатковий бал».

Алгоритм детермінований і не залежить ні від БД, ні від мережі: `calculate_boost`
— чиста функція, яку можна повністю покрити тестами. Сервіс лише підвозить їй дані.
"""

from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.repositories.past_product import PastProductRepository
from app.services.keywords import overlap, tokenize

logger = get_logger(__name__)

# Скільки балів за що. Значення підібрані так, щоб збіг категорії важив більше
# за одне випадкове слово, але кілька спільних слів переважували категорію:
# «той самий товар іншими словами» — сильніший сигнал, ніж «та сама полиця».
CATEGORY_MATCH_POINTS = 10
KEYWORD_MATCH_POINTS = 6
MAX_KEYWORD_POINTS = 20
MAX_BOOST = 30


@dataclass(frozen=True, slots=True)
class PastEntry:
    """Минулий успішний товар у вигляді, придатному для порівняння."""

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
        """Людське пояснення — іде в reasoning оцінки."""
        if self.score == 0:
            return "Збігів із нашими минулими товарами не знайдено."

        parts = []
        if self.matched_category:
            parts.append(f"категорія збігається з «{self.matched_category}»")
        if self.matched_keywords:
            words = ", ".join(sorted(self.matched_keywords)[:5])
            parts.append(f"спільні слова: {words}")

        titles = ", ".join(f"«{t}»" for t in self.matched_titles[:3])
        return f"Boost +{self.score}: {'; '.join(parts)}. Схожі минулі товари: {titles}."


def calculate_boost(*, title: str, category: str, past: list[PastEntry]) -> BoostResult:
    """Рахує Boost Score для одного товару.

    Бали нараховуються один раз за факт, а не за кожен минулий товар: якщо
    десять наших хітів лежать в одній категорії, це не робить новий товар
    у десять разів перспективнішим.
    """
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
    """Категорії рідко збігаються символ у символ.

    Amazon віддає «Best Sellers in Electronics», а в нашій історії записано
    просто «Electronics». Тому вважаємо збігом і входження одного в інше.
    """
    a, b = left.strip().lower(), right.strip().lower()
    if not a or not b:
        return False
    return a == b or a in b or b in a


class BoostService:
    """Тонка обгортка: дістає минулі товари з БД і віддає їх алгоритму."""

    def __init__(self, db: Session) -> None:
        self.past_products = PastProductRepository(db)
        self._index: list[PastEntry] | None = None

    def index(self) -> list[PastEntry]:
        """Минулі товари вантажимо ОДИН раз на весь запуск пайплайну.

        Інакше на 20 товарах вийшло б 20 однакових SELECT — класичний N+1.
        """
        if self._index is None:
            self._index = [
                PastEntry(title=p.title, category=p.category, keywords=list(p.keywords or []))
                for p in self.past_products.list_all()
            ]
            logger.info("Boost: завантажено %d минулих товарів", len(self._index))
        return self._index

    def calculate(self, *, title: str, category: str) -> BoostResult:
        return calculate_boost(title=title, category=category, past=self.index())
