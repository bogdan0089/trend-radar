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
    def test_takes_first_meaningful_words(self):
        """Amazon titles lead with brand and model, then marketing copy."""
        title = "Anker 45W USB-C Charger, Compact Fast Charging for iPhone"
        assert primary_keyword(title) == "anker 45w usb"

    def test_respects_max_words(self):
        assert primary_keyword("Ninja Air Fryer Nonstick Basket", max_words=2) == "ninja air"

    def test_falls_back_to_raw_title_when_all_words_filtered(self):
        """A title made only of stopwords must not yield an empty query."""
        assert primary_keyword("The Best of A") == "The Best of A"


class TestOverlap:
    def test_finds_common_words(self):
        assert overlap(["yoga", "mat", "home"], ["mat", "fitness"]) == {"mat"}

    def test_no_common_words(self):
        assert overlap(["yoga"], ["laptop"]) == set()
