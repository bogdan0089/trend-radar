"""Keyword extraction from product titles. Pure string handling."""

import re

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

_MIN_WORD_LENGTH = 2

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> list[str]:
    """Split a title into meaningful lowercase words, in order and without duplicates."""
    seen: set[str] = set()
    tokens: list[str] = []

    for word in _TOKEN_RE.findall(text.lower()):
        if len(word) < _MIN_WORD_LENGTH or word in _STOPWORDS or word in seen:
            continue
        seen.add(word)
        tokens.append(word)

    return tokens


def primary_keyword(title: str, *, max_words: int = 3) -> str:
    """Build the Google Trends query from the leading words of a title."""
    tokens = tokenize(title)
    if not tokens:
        return title.strip()[:64]
    return " ".join(tokens[:max_words])


def overlap(left: list[str], right: list[str]) -> set[str]:
    return set(left) & set(right)
