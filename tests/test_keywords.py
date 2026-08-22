import pytest

from app.utils.keywords import overlap, primary_keyword, tokenize


class TestTokenize:
    def test_lowercases_and_drops_punctuation(self):
        assert tokenize("Echo Dot (4th Gen)!") == ["echo", "dot", "4th"]

    def test_drops_stopwords(self):
        """'gen', 'with' and 'the' appear in nearly every title."""
        assert tokenize("Smart speaker with the Alexa") == ["smart", "speaker", "alexa"]

    def test_drops_duplicates_keeping_order(self):
        assert tokenize("Yoga Mat Yoga Block") == ["yoga", "mat", "block"]

    def test_drops_too_short_words(self):
        assert "a" not in tokenize("A Yoga Mat")

    def test_keeps_short_meaningful_tokens(self):
        assert tokenize("4K TV") == ["4k", "tv"]

    def test_empty_input(self):
        assert tokenize("") == []


class TestPrimaryKeyword:
    """The query must name the product type, which Google Trends knows, not the
    brand and model, which it does not.

    Every title below is a real one taken from the Amazon fixture. Asking about
    "ninja af101 air" came back with an almost empty search history; asking
    about "air fryer" does not.
    """

    @pytest.mark.parametrize(
        ("title", "expected"),
        [
            ("Ninja AF101 Air Fryer, 4 Quart Capacity, Nonstick Basket", "air fryer"),
            ("Anker 45W USB-C Charger, Compact Fast Charger for iPhone", "usb charger"),
            ("Stanley Quencher H2.0 FlowState Stainless Steel Tumbler 40 oz", "steel tumbler"),
            ("Echo Dot (4th Gen) | Smart speaker with Alexa | Charcoal", "echo dot"),
            (
                "Apple AirPods Pro (2nd Generation) Wireless Earbuds with MagSafe Case",
                "wireless earbuds",
            ),
        ],
    )
    def test_names_the_product_not_the_model(self, title, expected):
        assert primary_keyword(title) == expected

    def test_a_specification_tail_is_cut(self):
        """Everything after the first comma describes the product, it is not it."""
        assert primary_keyword("Air Fryer, 4 Quart Capacity, Grey") == "air fryer"

    def test_an_accessory_clause_is_cut(self):
        """'with Alexa Voice Remote' is not what the listing sells."""
        title = "Fire TV Stick 4K streaming device with Alexa Voice Remote"
        assert primary_keyword(title) == "streaming device"

    def test_model_numbers_and_units_are_dropped(self):
        assert primary_keyword("Yoga Mat 6 mm") == "yoga mat"

    def test_respects_max_words(self):
        assert primary_keyword("Stainless Steel Travel Tumbler", max_words=1) == "tumbler"

    def test_falls_back_to_the_whole_title_when_only_a_tail_remains(self):
        """A title that is nothing but specifications still needs a query."""
        assert primary_keyword("40 oz, 12 mm") == "40 oz, 12 mm"

    def test_falls_back_to_raw_title_when_all_words_filtered(self):
        """A title made only of stopwords must not yield an empty query."""
        assert primary_keyword("The Best of A") == "The Best of A"


class TestOverlap:
    def test_finds_common_words(self):
        assert overlap(["yoga", "mat", "home"], ["mat", "fitness"]) == {"mat"}

    def test_no_common_words(self):
        assert overlap(["yoga"], ["laptop"]) == set()
