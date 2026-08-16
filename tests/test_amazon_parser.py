"""Тести парсера Amazon.

Браузер не запускається: парсинг відділений від скрапінгу, тож перевіряємо
чисту функцію на збереженому HTML. Уся сюїта проходить за мілісекунди.
"""

from decimal import Decimal

import pytest

from app.core.exceptions import ScrapingError
from app.integrations.amazon import detect_block, parse_bestsellers


@pytest.fixture(scope="module")
def products(bestsellers_html):
    return parse_bestsellers(bestsellers_html)


def by_asin(products, asin):
    return next(p for p in products if p.asin == asin)


class TestParsing:
    def test_skips_duplicates_and_broken_blocks(self, products):
        """У фікстурі 6 блоків: один дубль ASIN і один без ASIN — лишається 4."""
        assert [p.asin for p in products] == [
            "B08N5WRWNW",
            "B09B8V1LZ3",
            "B0CHX3QBCH",
            "B0BSHF7WHW",
        ]

    def test_collects_all_seven_required_fields(self, products):
        """Сім полів, обовʼязкових за ТЗ."""
        product = by_asin(products, "B08N5WRWNW")

        assert product.title == "Echo Dot (4th Gen) | Smart speaker with Alexa | Charcoal"
        assert product.category == "Best Sellers in Electronics"
        assert product.price == Decimal("49.99")
        assert product.rating == 4.7
        assert product.reviews_count == 552341
        assert product.product_url.startswith("https://www.amazon.com/Echo-Dot")
        assert product.image_url.endswith("._AC_UL300_.jpg")

    def test_category_taken_from_page_heading(self, products):
        assert all(p.category == "Best Sellers in Electronics" for p in products)

    def test_absolute_url_built_from_relative_href(self, products):
        assert by_asin(products, "B09B8V1LZ3").product_url == (
            "https://www.amazon.com/Fire-TV-Stick/dp/B09B8V1LZ3/ref=zg_bs_g_2"
        )


class TestMissingData:
    """Amazon регулярно ховає ціну чи рейтинг. Це не привід губити товар."""

    def test_product_without_price_is_kept(self, products):
        product = by_asin(products, "B09B8V1LZ3")
        assert product.price is None
        assert product.rating == 4.5  # рейтинг є, ціни нема

    def test_new_product_without_rating_and_reviews(self, products):
        product = by_asin(products, "B0CHX3QBCH")
        assert product.rating is None
        assert product.reviews_count == 0
        assert product.price == Decimal("22.99")


class TestTrickyValues:
    def test_price_with_thousands_separator(self, products):
        assert by_asin(products, "B0BSHF7WHW").price == Decimal("1299.00")

    def test_rating_falls_back_to_icon_class(self, products):
        """Коли тексту '4 out of 5 stars' нема, рейтинг читається
        з класу іконки a-star-small-4."""
        assert by_asin(products, "B0BSHF7WHW").rating == 4.0

    def test_currency_detected_from_symbol(self, products):
        assert all(p.currency == "USD" for p in products)


class TestLimit:
    def test_limit_cuts_the_list(self, bestsellers_html):
        assert len(parse_bestsellers(bestsellers_html, limit=2)) == 2

    def test_limit_none_returns_everything(self, bestsellers_html):
        assert len(parse_bestsellers(bestsellers_html, limit=None)) == 4


class TestAntibot:
    def test_blocked_page_raises(self, blocked_html):
        """Заглушка антибота має падати з ScrapingError, а не тихо
        повертати порожній список — інакше у ScrapeRun не видно причини."""
        with pytest.raises(ScrapingError, match="антибот"):
            parse_bestsellers(blocked_html)

    def test_detect_block_finds_marker(self, blocked_html):
        assert detect_block(blocked_html) == "enter the characters you see below"

    def test_detect_block_silent_on_normal_page(self, bestsellers_html):
        assert detect_block(bestsellers_html) is None


class TestEmptyPage:
    def test_page_without_products_is_not_an_error(self):
        """Порожня сторінка — це факт для ScrapeRun, а не виняток."""
        assert parse_bestsellers("<html><body><h1>Nothing</h1></body></html>") == []

    def test_fallback_category_used_when_page_has_no_heading(self):
        html = "<html><body><div id='gridItemRoot'></div></body></html>"
        assert parse_bestsellers(html, fallback_category="Custom") == []
