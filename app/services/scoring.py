"""Детермінована формула оцінки товару — fallback без LLM.

Вимога ТЗ: «Якщо ключ відсутній у .env, скоринг працює за детермінованою
математичною формулою. Проєкт має успішно підніматися без API-ключа».

Модуль чистий: без БД, без мережі, без конфігу. Ті самі входи завжди дають
той самий бал, тож формула повністю покривається тестами і її можна перевірити
руками, дивлячись на breakdown.
"""

import math
from dataclasses import dataclass, field

# Ваги складників. Сума = 100, тож кожен бал видно у відсотках впливу.
WEIGHT_RATING = 25
WEIGHT_REVIEWS = 20
WEIGHT_TREND = 25
WEIGHT_BOOST = 30

# Скільки відгуків вважаємо «стелею». Далі приріст майже не відчувається:
# різниця між 100 000 і 500 000 відгуків для рішення баєра неістотна.
REVIEWS_CEILING = 100_000

# Межі динаміки тренду. -50% і нижче — падіння, +100% і вище — вибух попиту.
TREND_FLOOR_PCT = -50.0
TREND_CAP_PCT = 100.0

# Коли даних немає, ставимо нейтраль, а не нуль: новий товар без відгуків
# не гірший за товар із рейтингом 1.0, про нього просто нічого не відомо.
NEUTRAL_FACTOR = 0.5

MAX_BOOST_POINTS = 30


@dataclass
class ScoreResult:
    score: int
    reasoning: str
    breakdown: dict[str, float] = field(default_factory=dict)


def calculate_fallback_score(
    *,
    title: str,
    rating: float | None,
    reviews_count: int,
    trend_delta_pct: float | None,
    boost_score: int,
    boost_explanation: str = "",
) -> ScoreResult:
    """Бал 0–100 і текстове пояснення.

    `trend_delta_pct=None` означає «Google Trends не дав даних» — це не те саме,
    що нульова динаміка, тому такий випадок отримує нейтраль і окремий рядок
    у поясненні.
    """
    rating_factor = NEUTRAL_FACTOR if rating is None else _clamp(rating / 5)
    reviews_factor = _reviews_factor(reviews_count)
    trend_factor = NEUTRAL_FACTOR if trend_delta_pct is None else _trend_factor(trend_delta_pct)
    boost_factor = _clamp(boost_score / MAX_BOOST_POINTS)

    breakdown = {
        "rating": round(rating_factor * WEIGHT_RATING, 1),
        "reviews": round(reviews_factor * WEIGHT_REVIEWS, 1),
        "trend": round(trend_factor * WEIGHT_TREND, 1),
        "boost": round(boost_factor * WEIGHT_BOOST, 1),
    }
    score = int(round(sum(breakdown.values())))

    return ScoreResult(
        score=max(0, min(100, score)),
        reasoning=_build_reasoning(
            title=title,
            rating=rating,
            reviews_count=reviews_count,
            trend_delta_pct=trend_delta_pct,
            boost_score=boost_score,
            boost_explanation=boost_explanation,
            breakdown=breakdown,
        ),
        breakdown=breakdown,
    )


def _reviews_factor(count: int) -> float:
    """Логарифмічна шкала.

    Лінійна була б непридатною: різниця між 10 і 1 000 відгуками величезна,
    а між 90 000 і 100 000 — ніяка. Логарифм саме це й відображає.
    """
    if count <= 0:
        return 0.0
    return _clamp(math.log10(1 + count) / math.log10(1 + REVIEWS_CEILING))


def _trend_factor(delta_pct: float) -> float:
    """Динаміку -50%..+100% розтягуємо в 0..1, за межами — плато."""
    bounded = max(TREND_FLOOR_PCT, min(TREND_CAP_PCT, delta_pct))
    return (bounded - TREND_FLOOR_PCT) / (TREND_CAP_PCT - TREND_FLOOR_PCT)


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def _build_reasoning(
    *,
    title: str,
    rating: float | None,
    reviews_count: int,
    trend_delta_pct: float | None,
    boost_score: int,
    boost_explanation: str,
    breakdown: dict[str, float],
) -> str:
    """Пояснення, з якого видно кожен доданок.

    Це вимога ТЗ (`reasoning`) і водночас спосіб перевірити оцінку руками:
    цифри в тексті мають збігатися з breakdown.
    """
    lines = [f"Оцінка розрахована формулою (без LLM) для «{title[:80]}»."]

    if rating is None:
        lines.append(f"Рейтинг невідомий — нейтральні {breakdown['rating']} з {WEIGHT_RATING}.")
    else:
        lines.append(f"Рейтинг {rating}/5 → {breakdown['rating']} з {WEIGHT_RATING}.")

    lines.append(
        f"Відгуків {reviews_count:,} (логарифмічна шкала) → "
        f"{breakdown['reviews']} з {WEIGHT_REVIEWS}.".replace(",", " ")
    )

    if trend_delta_pct is None:
        lines.append(
            f"Google Trends даних не дав — нейтральні {breakdown['trend']} з {WEIGHT_TREND}."
        )
    else:
        direction = "зростає" if trend_delta_pct >= 0 else "спадає"
        lines.append(
            f"Попит {direction} на {abs(trend_delta_pct):.1f}% від середнього за рік → "
            f"{breakdown['trend']} з {WEIGHT_TREND}."
        )

    if boost_score > 0:
        lines.append(f"{boost_explanation} → {breakdown['boost']} з {WEIGHT_BOOST}.")
    else:
        lines.append(f"Збігів із нашими минулими товарами немає → 0 з {WEIGHT_BOOST}.")

    return " ".join(lines)
