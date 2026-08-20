"""Deterministic scoring formula, used whenever no LLM key is configured."""

import math
from dataclasses import dataclass, field

WEIGHT_RATING = 25
WEIGHT_REVIEWS = 20
WEIGHT_TREND = 25
WEIGHT_BOOST = 30

REVIEWS_CEILING = 100_000
TREND_SCALE_PCT = 200.0
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
    trend_unreliable: bool = False,
) -> ScoreResult:
    """Return a 0-100 score and its explanation; an unknown trend scores neutral."""
    rating_factor = NEUTRAL_FACTOR if rating is None else _clamp(rating / 5)
    reviews_factor = _reviews_factor(reviews_count)
    trend_known = trend_delta_pct is not None and not trend_unreliable
    trend_factor = _trend_factor(trend_delta_pct) if trend_known else NEUTRAL_FACTOR
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
            trend_unreliable=trend_unreliable,
            boost_score=boost_score,
            boost_explanation=boost_explanation,
            breakdown=breakdown,
        ),
        breakdown=breakdown,
    )


def _reviews_factor(count: int) -> float:
    """Map a review count onto 0..1 on a logarithmic scale."""
    if count <= 0:
        return 0.0
    return _clamp(math.log10(1 + count) / math.log10(1 + REVIEWS_CEILING))


def _trend_factor(delta_pct: float) -> float:
    """Map demand change onto 0..1, where 0.5 means "at the yearly average"."""
    magnitude = _clamp(
        math.log10(1 + abs(delta_pct) / 10) / math.log10(1 + TREND_SCALE_PCT / 10)
    )
    return _clamp(0.5 + 0.5 * math.copysign(magnitude, delta_pct))


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def _build_reasoning(
    *,
    title: str,
    rating: float | None,
    reviews_count: int,
    trend_delta_pct: float | None,
    trend_unreliable: bool,
    boost_score: int,
    boost_explanation: str,
    breakdown: dict[str, float],
) -> str:
    """Build an explanation in which every term of the breakdown is visible."""
    lines = [f"Score computed by the formula (no LLM) for '{title[:80]}'."]

    if rating is None:
        lines.append(f"Rating unknown, neutral {breakdown['rating']} of {WEIGHT_RATING}.")
    else:
        lines.append(f"Rating {rating}/5 gives {breakdown['rating']} of {WEIGHT_RATING}.")

    lines.append(
        f"Reviews {reviews_count:,} (logarithmic scale) give "
        f"{breakdown['reviews']} of {WEIGHT_REVIEWS}.".replace(",", " ")
    )

    if trend_delta_pct is None:
        lines.append(
            f"Google Trends returned no data, neutral {breakdown['trend']} of {WEIGHT_TREND}."
        )
    elif trend_unreliable:
        lines.append(
            f"Google Trends shows {trend_delta_pct:+.1f}%, but on a nearly empty search "
            f"history, so it is not counted: neutral {breakdown['trend']} of {WEIGHT_TREND}."
        )
    else:
        direction = "rising" if trend_delta_pct >= 0 else "falling"
        lines.append(
            f"Demand {direction} {abs(trend_delta_pct):.1f}% against the yearly average gives "
            f"{breakdown['trend']} of {WEIGHT_TREND}."
        )

    if boost_score > 0:
        lines.append(f"{boost_explanation} That gives {breakdown['boost']} of {WEIGHT_BOOST}.")
    else:
        lines.append(f"No matches with our past products, 0 of {WEIGHT_BOOST}.")

    return " ".join(lines)
