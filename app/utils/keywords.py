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

# Amazon titles separate with an en dash, an em dash or a bullet as readily as
# with ASCII. They are folded to plain characters by code point, so the pattern
# below carries no look-alike glyphs that a reader could mistake for a hyphen.
_PUNCTUATION_FOLDING = {0x2013: "-", 0x2014: "-", 0x2022: "|"}

# Everything after the first separator is specification or an accessory, not the
# product itself: "Ninja AF101 Air Fryer, 4 Quart Capacity" and "Fire TV Stick
# streaming device with Alexa Voice Remote" - the remote is not what is sold.
_SEGMENT_SPLIT_RE = re.compile(
    r"[|,;:]|\s-\s|\b(?:with|for|including|includes|featuring|plus)\b",
    re.IGNORECASE,
)

# "(4th Gen)", "[2-Pack]": model and packaging notes, never the product type.
_BRACKETS_RE = re.compile(r"\([^)]*\)|\[[^\]]*\]")

_HAS_DIGIT_RE = re.compile(r"\d")

# Units that trail a size and would otherwise become the query: "40 oz".
_UNITS = frozenset(
    {
        "oz", "ml", "lb", "lbs", "kg", "mg", "mm", "cm", "inch", "inches",
        "ft", "qt", "quart", "gal", "hz", "ghz", "mhz", "gb", "tb", "mb",
        "mah", "wh", "watt", "watts", "volt", "volts",
    }
)


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


def primary_keyword(title: str, *, max_words: int = 2) -> str:
    """Build the Google Trends query from the product type in a title.

    English product names are head-final: the type is the last noun, while the
    brand and model that open the title are exactly what Google Trends has no
    data for. "Ninja AF101 Air Fryer, 4 Quart Capacity" is an air fryer, and
    asking about "ninja af101 air" came back with an almost empty history.

    So the title is cut down to its core - no specification tail, no bracketed
    model note, no sizes - and the trailing words of what is left are used.
    """
    core = _BRACKETS_RE.sub(" ", title.translate(_PUNCTUATION_FOLDING))
    head = _SEGMENT_SPLIT_RE.split(core)[0]

    tokens = _describing_tokens(head) or _describing_tokens(core)
    if not tokens:
        return title.strip()[:64]

    return " ".join(tokens[-max_words:])


def _describing_tokens(text: str) -> list[str]:
    """Tokens that can describe a product type: no model numbers, no units."""
    return [
        token
        for token in tokenize(text)
        if not _HAS_DIGIT_RE.search(token) and token not in _UNITS
    ]


def overlap(left: list[str], right: list[str]) -> set[str]:
    return set(left) & set(right)
