"""Tests for the Amazon parser and the multi-category scrape orchestration."""

from decimal import Decimal

import pytest

from app.core.exceptions import ScrapingError
from app.integrations.amazon import (
    category_from_url,
    detect_block,
    parse_bestsellers,
    scrape_categories,
)


@pytest.fixture(scope="module")
def products(bestsellers_html):
    return parse_bestsellers(bestsellers_html)


def by_asin(products, asin):
    return next(p for p in products if p.asin == asin)


class TestParsing:
    def test_skips_duplicates_and_broken_blocks(self, products):
        """The fixture holds 6 blocks: one duplicate ASIN and one without."""
        assert [p.asin for p in products] == [
            "B08N5WRWNW",
            "B09B8V1LZ3",
            "B0CHX3QBCH",
            "B0BSHF7WHW",
        ]

    def test_collects_all_seven_required_fields(self, products):
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
    """Amazon regularly hides a price or a rating; that must not lose the product."""

    def test_product_without_price_is_kept(self, products):
        product = by_asin(products, "B09B8V1LZ3")
        assert product.price is None
        assert product.rating == 4.5

    def test_new_product_without_rating_and_reviews(self, products):
        product = by_asin(products, "B0CHX3QBCH")
        assert product.rating is None
        assert product.reviews_count == 0
        assert product.price == Decimal("22.99")


class TestTrickyValues:
    def test_price_with_thousands_separator(self, products):
        assert by_asin(products, "B0BSHF7WHW").price == Decimal("1299.00")

    def test_rating_falls_back_to_icon_class(self, products):
        assert by_asin(products, "B0BSHF7WHW").rating == 4.0

    def test_currency_detected_from_symbol(self, products):
        assert all(p.currency == "USD" for p in products)

    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("$49.99", "USD"),
            ("PLN 161.89", "PLN"),
            ("161,89 zł PLN", "PLN"),
            ("£19.50", "GBP"),
        ],
    )
    def test_currency_code_wins_over_symbol(self, text, expected):
        """A European host is quoted "PLN 161.89" on amazon.com, not "$161.89"."""
        from app.integrations.amazon import _detect_currency

        assert _detect_currency(text) == expected


class TestAntibot:
    def test_blocked_page_raises(self, blocked_html):
        """A block must raise rather than return an empty list."""
        with pytest.raises(ScrapingError, match="anti-bot"):
            parse_bestsellers(blocked_html)

    def test_detect_block_finds_marker(self, blocked_html):
        assert detect_block(blocked_html) == "enter the characters you see below"

    def test_detect_block_silent_on_normal_page(self, bestsellers_html):
        assert detect_block(bestsellers_html) is None


class TestCategoryExtraction:
    """Extracting the real category name, not the generic banner."""

    def test_generic_banner_heading_is_skipped(self):
        html = """
        <html><head><title>Amazon Best Sellers: Best Electronics</title></head>
        <body>
          <h1>Amazon Best Sellers</h1>
          <h1>Best Sellers in Electronics</h1>
          <div id="gridItemRoot">
            <a href="/x/dp/B08N5WRWNW"><span class="p13n-sc-truncate">Item</span></a>
          </div>
        </body></html>
        """
        assert parse_bestsellers(html)[0].category == "Best Sellers in Electronics"

    def test_nav_tree_current_suffix_is_stripped(self):
        html = """
        <html><body>
          <h1>Amazon Best Sellers</h1>
          <div class="zg-selected">Electronics(Current)</div>
          <div id="gridItemRoot">
            <a href="/x/dp/B08N5WRWNW"><span class="p13n-sc-truncate">Item</span></a>
          </div>
        </body></html>
        """
        assert parse_bestsellers(html)[0].category == "Electronics"

    def test_falls_back_to_slug_when_only_generic_headings(self):
        """The slug comes from our own config, so it cannot drift with markup."""
        html = """
        <html><head><title>Amazon Best Sellers</title></head>
        <body>
          <h1>Amazon Best Sellers</h1>
          <div id="gridItemRoot">
            <a href="/x/dp/B08N5WRWNW"><span class="p13n-sc-truncate">Item</span></a>
          </div>
        </body></html>
        """
        products = parse_bestsellers(html, fallback_category="Home Garden")
        assert products[0].category == "Home Garden"

    @pytest.mark.parametrize(
        ("url", "expected"),
        [
            ("https://www.amazon.com/Best-Sellers-Electronics/zgbs/electronics", "Electronics"),
            ("https://www.amazon.com/x/zgbs/home-garden", "Home Garden"),
            ("https://www.amazon.com/x/zgbs/sporting-goods/", "Sporting Goods"),
            ("https://www.amazon.com/x/zgbs/electronics/172282", "172282"),
            ("https://www.amazon.com/Best-Sellers/zgbs", "Best Sellers"),
        ],
    )
    def test_category_from_url(self, url, expected):
        assert category_from_url(url) == expected

    def test_scrape_categories_labels_each_category_from_its_url(self):
        """The whole point of the fix: two categories must not share one label."""
        page = """
        <html><body>
          <h1>Amazon Best Sellers</h1>
          <div id="gridItemRoot">
            <a href="/x/dp/{asin}"><span class="p13n-sc-truncate">Item</span></a>
          </div>
        </body></html>
        """
        scraper = StubScraper(
            {
                "https://www.amazon.com/x/zgbs/electronics": page.format(asin="B08N5WRWNW"),
                "https://www.amazon.com/x/zgbs/home-garden": page.format(asin="B09B8V1LZ3"),
            }
        )

        result = scrape_categories(list(scraper.pages), scraper=scraper)

        assert {p.category for p in result.products} == {"Electronics", "Home Garden"}


class TestEmptyPage:
    def test_page_without_products_is_not_an_error(self):
        """An empty page is a fact for the ScrapeRun, not an exception."""
        assert parse_bestsellers("<html><body><h1>Nothing</h1></body></html>") == []

    def test_fallback_category_used_when_page_has_no_heading(self):
        html = "<html><body><div id='gridItemRoot'></div></body></html>"
        assert parse_bestsellers(html, fallback_category="Custom") == []


class StubScraper:
    """Stands in for AmazonScraper, returning canned HTML or errors per URL."""

    def __init__(self, pages: dict[str, str | ScrapingError]) -> None:
        self.pages = pages
        self.requested: list[str] = []

    def fetch_many(self, urls: list[str]) -> dict[str, str | ScrapingError]:
        self.requested = list(urls)
        return {url: self.pages[url] for url in urls}


class TestScrapeCategories:
    """Several categories are walked in one pass; one failure must not sink the rest."""

    def test_collects_products_from_every_category(self, bestsellers_html):
        scraper = StubScraper({"a": bestsellers_html, "b": bestsellers_html})

        result = scrape_categories(["a", "b"], limit_per_category=2, scraper=scraper)

        assert len(result.products) == 4
        assert result.failures == {}
        assert scraper.requested == ["a", "b"]

    def test_limit_applies_per_category(self, bestsellers_html):
        scraper = StubScraper({"a": bestsellers_html, "b": bestsellers_html})

        result = scrape_categories(["a", "b"], limit_per_category=1, scraper=scraper)

        assert len(result.products) == 2

    def test_failed_category_is_recorded_and_others_continue(self, bestsellers_html):
        scraper = StubScraper({"a": ScrapingError("timeout"), "b": bestsellers_html})

        result = scrape_categories(["a", "b"], limit_per_category=2, scraper=scraper)

        assert len(result.products) == 2
        assert "timeout" in result.failures["a"]

    def test_blocked_page_becomes_a_failure_not_an_exception(
        self, bestsellers_html, blocked_html
    ):
        """A captcha on one category must not abort the whole run."""
        scraper = StubScraper({"a": blocked_html, "b": bestsellers_html})

        result = scrape_categories(["a", "b"], limit_per_category=2, scraper=scraper)

        assert len(result.products) == 2
        assert "anti-bot" in result.failures["a"]

    def test_all_categories_failing_yields_no_products(self):
        scraper = StubScraper({"a": ScrapingError("blocked"), "b": ScrapingError("blocked")})

        result = scrape_categories(["a", "b"], scraper=scraper)

        assert result.products == []
        assert set(result.failures) == {"a", "b"}
