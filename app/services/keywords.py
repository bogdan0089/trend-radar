"""Витяг ключових слів із назви товару.

Чиста математика над рядками: без БД, без мережі. Використовується двічі —
для запиту в Google Trends і для зіставлення з нашими минулими товарами.
"""

import re

# Слова, які є майже в кожній назві на Amazon і нічого не розрізняють.
# Без цього списку «Wireless Bluetooth Pack of 2» збігалося б із будь-чим.
_STOPWORDS = frozenset(
    {
        "a", "an", "and", "the", "for", "with", "of", "in", "on", "to", "by",
        "or", "from", "at", "up", "new", "set", "pack", "pcs", "pieces", "piece",
        "inch", "inches", "size", "color", "colour", "black", "white", "grey",
        "gray", "blue", "red", "green", "pink", "gold", "silver",
        "free", "best", "premium", "professional", "quality", "upgraded",
        "portable", "adjustable", "universal", "multi", "super", "ultra",
        "gen", "generation", "version", "model", "edition", "series",
        "compatible", "including", "included", "includes", "plus", "pro",
        "large", "small", "medium", "mini", "big", "light", "heavy", "duty",
    }
)

# Мінімальна довжина слова. «4k», «tv» лишаємо, а «a», «xl» — шум.
_MIN_WORD_LENGTH = 2

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> list[str]:
    """Назва товару → список значущих слів у нижньому регістрі.

    'Echo Dot (4th Gen) | Smart speaker with Alexa' → ['echo', 'dot', '4th',
    'smart', 'speaker', 'alexa']

    Порядок зберігається (він важливий для primary_keyword), дублі прибираються.
    """
    seen: set[str] = set()
    tokens: list[str] = []

    for word in _TOKEN_RE.findall(text.lower()):
        if len(word) < _MIN_WORD_LENGTH or word in _STOPWORDS or word in seen:
            continue
        seen.add(word)
        tokens.append(word)

    return tokens


def primary_keyword(title: str, *, max_words: int = 3) -> str:
    """Пошуковий запит для Google Trends.

    Беремо перші кілька слів назви: на Amazon спочатку йде бренд і модель,
    а маркетинговий хвіст («Fast Charging, 2-Pack, Ideal Gift») тільки зашумив
    би запит. Якщо значущих слів не лишилось — віддаємо обрізану назву як є.
    """
    tokens = tokenize(title)
    if not tokens:
        return title.strip()[:64]
    return " ".join(tokens[:max_words])


def overlap(left: list[str], right: list[str]) -> set[str]:
    """Спільні слова двох наборів."""
    return set(left) & set(right)
