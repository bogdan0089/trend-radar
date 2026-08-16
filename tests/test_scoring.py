"""Тести fallback-формули — гілки, яка працює без API-ключа (вимога ТЗ)."""

import pytest

from app.services.scoring import (
    WEIGHT_BOOST,
    WEIGHT_RATING,
    WEIGHT_REVIEWS,
    WEIGHT_TREND,
    calculate_fallback_score,
)


def score(**overrides):
    defaults = {
        "title": "Test Product",
        "rating": None,
        "reviews_count": 0,
        "trend_delta_pct": None,
        "boost_score": 0,
    }
    return calculate_fallback_score(**{**defaults, **overrides})


class TestBounds:
    def test_weights_sum_to_100(self):
        """Інакше «ідеальний» товар не міг би отримати рівно 100."""
        assert WEIGHT_RATING + WEIGHT_REVIEWS + WEIGHT_TREND + WEIGHT_BOOST == 100

    def test_perfect_product_scores_100(self):
        result = score(rating=5.0, reviews_count=100_000, trend_delta_pct=100.0, boost_score=30)
        assert result.score == 100

    def test_worst_product_scores_0(self):
        result = score(rating=0.0, reviews_count=0, trend_delta_pct=-50.0, boost_score=0)
        assert result.score == 0

    def test_extreme_values_are_clamped(self):
        """Тренд +5000% не має ламати шкалу 0-100."""
        result = score(rating=5.0, reviews_count=10**9, trend_delta_pct=5000.0, boost_score=999)
        assert result.score == 100

    @pytest.mark.parametrize("delta", [-1000.0, -50.0, 0.0, 42.0, 1000.0])
    def test_score_always_in_range(self, delta):
        assert 0 <= score(rating=3.0, reviews_count=500, trend_delta_pct=delta).score <= 100


class TestMissingData:
    """Немає даних — не те саме, що погані дані."""

    def test_missing_rating_is_neutral_not_zero(self):
        """Новий товар без рейтингу не гірший за товар з рейтингом 1.0."""
        unknown = score(rating=None).breakdown["rating"]
        terrible = score(rating=0.0).breakdown["rating"]
        excellent = score(rating=5.0).breakdown["rating"]

        assert terrible < unknown < excellent
        assert unknown == WEIGHT_RATING / 2

    def test_missing_trend_is_neutral(self):
        """Google Trends не дав даних — це не 'попит впав'."""
        unknown = score(trend_delta_pct=None).breakdown["trend"]
        falling = score(trend_delta_pct=-50.0).breakdown["trend"]

        assert falling < unknown
        assert unknown == WEIGHT_TREND / 2

    def test_zero_reviews_gives_zero_points(self):
        """А ось нуль відгуків — це справжній нуль, а не невідомість."""
        assert score(reviews_count=0).breakdown["reviews"] == 0


class TestReviewsScale:
    def test_logarithmic_not_linear(self):
        """Різниця 10 → 1000 має важити більше, ніж 90 000 → 100 000."""
        low_growth = score(reviews_count=1000).breakdown["reviews"] - score(
            reviews_count=10
        ).breakdown["reviews"]
        high_growth = score(reviews_count=100_000).breakdown["reviews"] - score(
            reviews_count=90_000
        ).breakdown["reviews"]

        assert low_growth > high_growth

    def test_more_reviews_never_lowers_score(self):
        values = [score(reviews_count=n).breakdown["reviews"] for n in (0, 10, 1000, 100_000)]
        assert values == sorted(values)


class TestBoostContribution:
    def test_boost_raises_score(self):
        assert score(boost_score=30).score > score(boost_score=0).score

    def test_full_boost_gives_full_weight(self):
        assert score(boost_score=30).breakdown["boost"] == WEIGHT_BOOST


class TestOutput:
    def test_reasoning_is_not_empty(self):
        assert len(score(rating=4.5, reviews_count=100).reasoning) > 50

    def test_reasoning_mentions_actual_numbers(self):
        """reasoning має пояснювати оцінку, а не бути шаблонною фразою."""
        result = score(rating=4.5, reviews_count=1234, trend_delta_pct=25.0)
        assert "4.5" in result.reasoning
        assert "25.0%" in result.reasoning

    def test_reasoning_explains_missing_data(self):
        assert "невідомий" in score(rating=None).reasoning
        assert "даних не дав" in score(trend_delta_pct=None).reasoning

    def test_breakdown_sums_to_score(self):
        """Розклад має збігатись із балом — інакше оцінку не перевірити руками."""
        result = score(rating=4.2, reviews_count=5000, trend_delta_pct=15.0, boost_score=16)
        assert round(sum(result.breakdown.values())) == result.score

    def test_is_deterministic(self):
        """Та сама вхідна дата завжди дає той самий бал — це і є 'детермінована
        математична формула' з ТЗ."""
        args = {"rating": 4.1, "reviews_count": 777, "trend_delta_pct": 33.3, "boost_score": 12}
        assert score(**args).score == score(**args).score
