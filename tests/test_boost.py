"""Tests for the Boost Score, the core of the Internal Sales Boost requirement."""

import pytest

from app.services.boost_service import (
    CATEGORY_MATCH_POINTS,
    KEYWORD_MATCH_POINTS,
    MAX_BOOST,
    MAX_KEYWORD_POINTS,
    PastEntry,
    calculate_boost,
)


@pytest.fixture
def yoga_mat():
    return PastEntry(title="Yoga Mat Pro", category="Sports", keywords=["yoga", "mat"])


class TestNoMatch:
    def test_empty_history_gives_zero(self):
        result = calculate_boost(title="Echo Dot", category="Electronics", past=[])
        assert result.score == 0
        assert result.matched_titles == []

    def test_unrelated_product_gives_zero(self, yoga_mat):
        result = calculate_boost(
            title="Apple MacBook Air Laptop", category="Computers", past=[yoga_mat]
        )
        assert result.score == 0
        assert result.matched_category is None


class TestCategoryMatch:
    def test_exact_category_match(self, yoga_mat):
        result = calculate_boost(title="Dumbbell Rack", category="Sports", past=[yoga_mat])
        assert result.score == CATEGORY_MATCH_POINTS
        assert result.matched_category == "Sports"

    def test_partial_category_match(self, yoga_mat):
        """Amazon says 'Best Sellers in Sports' where our history says 'Sports'."""
        result = calculate_boost(
            title="Dumbbell Rack", category="Best Sellers in Sports", past=[yoga_mat]
        )
        assert result.score == CATEGORY_MATCH_POINTS

    def test_category_match_is_case_insensitive(self, yoga_mat):
        result = calculate_boost(title="Dumbbell Rack", category="SPORTS", past=[yoga_mat])
        assert result.score == CATEGORY_MATCH_POINTS

    @pytest.mark.parametrize(
        ("past_category", "product_category"),
        [
            ("Art", "Smart Home"),
            ("Pet", "Carpet Care"),
            ("Tea", "Steam Cleaning"),
            ("Toy", "Toyota Accessories"),
        ],
    )
    def test_a_category_hidden_inside_a_word_does_not_match(
        self, past_category, product_category
    ):
        """Raw substring matching handed out the points for nothing: "art" sits
        inside "smart home" and "pet" inside "carpet care"."""
        entry = PastEntry(title="Something", category=past_category, keywords=[])

        result = calculate_boost(title="Thing", category=product_category, past=[entry])

        assert result.matched_category is None
        assert result.score == 0

    @pytest.mark.parametrize(
        ("past_category", "product_category"),
        [
            ("Electronics", "Best Sellers in Electronics"),
            ("Home & Kitchen", "Best Sellers in Home & Kitchen"),
            ("Toys", "Toys and Games"),
        ],
    )
    def test_a_category_that_is_really_contained_still_matches(
        self, past_category, product_category
    ):
        """The reason containment exists: Amazon prefixes its page titles."""
        entry = PastEntry(title="Something", category=past_category, keywords=[])

        result = calculate_boost(title="Thing", category=product_category, past=[entry])

        assert result.score == CATEGORY_MATCH_POINTS


class TestKeywordMatch:
    def test_single_keyword(self, yoga_mat):
        result = calculate_boost(
            title="Foldable Yoga Block", category="Fitness", past=[yoga_mat]
        )
        assert result.score == KEYWORD_MATCH_POINTS
        assert result.matched_keywords == ["yoga"]

    def test_two_keywords(self, yoga_mat):
        result = calculate_boost(
            title="Non-slip Yoga Mat for Home", category="Fitness", past=[yoga_mat]
        )
        assert result.score == 2 * KEYWORD_MATCH_POINTS
        assert result.matched_keywords == ["mat", "yoga"]

    def test_keyword_points_are_capped(self):
        """Many shared words must not add up to an unbounded score."""
        entry = PastEntry(
            title="x",
            category="Other",
            keywords=["yoga", "mat", "block", "strap", "wheel", "towel"],
        )
        result = calculate_boost(
            title="Yoga Mat Block Strap Wheel Towel", category="Fitness", past=[entry]
        )
        assert result.score == MAX_KEYWORD_POINTS

    def test_keywords_derived_from_title_when_empty(self):
        """A past product without keywords matches on words from its title."""
        entry = PastEntry(title="Air Fryer Basket", category="Other", keywords=[])
        result = calculate_boost(title="Ninja Air Fryer", category="Kitchen", past=[entry])
        assert result.score > 0
        assert "fryer" in result.matched_keywords


class TestCombined:
    def test_category_and_keywords_add_up(self, yoga_mat):
        result = calculate_boost(
            title="Non-slip Yoga Mat", category="Sports", past=[yoga_mat]
        )
        assert result.score == CATEGORY_MATCH_POINTS + 2 * KEYWORD_MATCH_POINTS

    def test_total_is_capped(self):
        entry = PastEntry(
            title="x",
            category="Sports",
            keywords=["yoga", "mat", "block", "strap", "wheel"],
        )
        result = calculate_boost(
            title="Yoga Mat Block Strap Wheel", category="Sports", past=[entry]
        )
        assert result.score == MAX_BOOST

    def test_points_counted_once_across_many_past_products(self):
        """Category points are awarded once, however many past products match."""
        history = [
            PastEntry(title=f"Item {i}", category="Sports", keywords=[]) for i in range(10)
        ]
        result = calculate_boost(title="Dumbbell Rack", category="Sports", past=history)
        assert result.score == CATEGORY_MATCH_POINTS
        assert len(result.matched_titles) == 10


class TestExplain:
    def test_explains_no_match(self):
        assert "No matches" in calculate_boost(title="X", category="Y", past=[]).explain()

    def test_explains_match(self, yoga_mat):
        text = calculate_boost(
            title="Non-slip Yoga Mat", category="Sports", past=[yoga_mat]
        ).explain()
        assert "Boost +22" in text
        assert "Yoga Mat Pro" in text
