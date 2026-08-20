"""Tests for product collection: live data, snapshot fallback and demo cleanup."""

from decimal import Decimal

import pytest
from sqlalchemy import select

from app.core.exceptions import ScrapingError
from app.integrations.amazon import CategoryScrapeOutcome, ScrapedProduct
from app.models.product import Product
from app.repositories.product import ProductRepository
from app.services.scrape_service import ScrapeService

DEMO_ASIN = "B08KWJ4B3T"


def scraped(asin: str, title: str = "Live product") -> ScrapedProduct:
    return ScrapedProduct(
        asin=asin,
        title=title,
        category="Best Sellers in Electronics",
        price=Decimal("19.99"),
        currency="USD",
        rating=4.5,
        reviews_count=100,
        product_url=f"https://www.amazon.com/dp/{asin}",
        image_url="https://example.com/image.jpg",
    )


def stored(db_session) -> dict[str, str]:
    """Every stored product as asin -> source."""
    rows = db_session.scalars(select(Product)).all()
    return {row.asin: row.source for row in rows}


@pytest.fixture
def with_demo_products(db_session):
    """Two demo rows, exactly as the seed leaves them before the first scrape."""
    ProductRepository(db_session).upsert_many(
        [
            {
                "asin": DEMO_ASIN,
                "title": "Demo tumbler",
                "category": "Best Sellers in Electronics",
                "price": Decimal("45.00"),
                "currency": "USD",
                "rating": 4.6,
                "reviews_count": 67015,
                "product_url": f"https://www.amazon.com/dp/{DEMO_ASIN}",
                "image_url": "https://example.com/demo.jpg",
                "source": "snapshot",
            },
            {
                "asin": "B0DEMO0002",
                "title": "Demo fryer",
                "category": "Best Sellers in Electronics",
                "price": Decimal("89.99"),
                "currency": "USD",
                "rating": 4.8,
                "reviews_count": 98743,
                "product_url": "https://www.amazon.com/dp/B0DEMO0002",
                "image_url": "https://example.com/demo2.jpg",
                "source": "snapshot",
            },
        ]
    )
    db_session.commit()
    return db_session


def patch_scrape(monkeypatch, outcome: CategoryScrapeOutcome):
    monkeypatch.setattr(
        "app.services.scrape_service.scrape_categories",
        lambda *args, **kwargs: outcome,
    )


class TestDemoCleanup:
    def test_live_scrape_removes_the_demo_products(self, with_demo_products, monkeypatch):
        db = with_demo_products
        patch_scrape(monkeypatch, CategoryScrapeOutcome(products=[scraped("B0LIVE0001")]))

        outcome = ScrapeService(db).collect()

        assert outcome.demo_removed == 2
        assert stored(db) == {"B0LIVE0001": "amazon"}

    def test_a_product_seen_live_survives_even_if_it_was_a_demo_row(
        self, with_demo_products, monkeypatch
    ):
        """The demo ASIN comes back from Amazon, so it is real data now, not a leftover."""
        db = with_demo_products
        live = CategoryScrapeOutcome(products=[scraped(DEMO_ASIN, "Real title")])
        patch_scrape(monkeypatch, live)

        ScrapeService(db).collect()

        assert stored(db) == {DEMO_ASIN: "amazon"}
        product = db.scalar(select(Product).where(Product.asin == DEMO_ASIN))
        assert product.title == "Real title"

    def test_snapshot_fallback_keeps_the_demo_products(self, with_demo_products, monkeypatch):
        """Nothing came back from Amazon, so the demo rows are all the dashboard has."""
        db = with_demo_products
        patch_scrape(monkeypatch, CategoryScrapeOutcome(failures={"a": "blocked"}))

        outcome = ScrapeService(db).collect()

        assert outcome.used_snapshot is True
        assert outcome.demo_removed == 0
        assert set(stored(db).values()) == {"snapshot"}

    def test_a_failed_browser_start_also_falls_back(self, with_demo_products, monkeypatch):
        db = with_demo_products

        def boom(*args, **kwargs):
            raise ScrapingError("Could not start the browser")

        monkeypatch.setattr("app.services.scrape_service.scrape_categories", boom)

        outcome = ScrapeService(db).collect()

        assert outcome.used_snapshot is True
        assert outcome.demo_removed == 0


class TestCounters:
    def test_counts_created_and_updated_separately(self, db_session, monkeypatch):
        patch_scrape(monkeypatch, CategoryScrapeOutcome(products=[scraped("B0COUNT001")]))
        first = ScrapeService(db_session).collect()

        patch_scrape(monkeypatch, CategoryScrapeOutcome(products=[scraped("B0COUNT001")]))
        second = ScrapeService(db_session).collect()

        assert (first.created, first.updated) == (1, 0)
        assert (second.created, second.updated) == (0, 1)

    def test_duplicate_asins_in_one_batch_are_collapsed(self, db_session, monkeypatch):
        """Amazon repeats a product across blocks; Postgres rejects it twice in one upsert."""
        patch_scrape(
            monkeypatch,
            CategoryScrapeOutcome(products=[scraped("B0DUP00001"), scraped("B0DUP00001")]),
        )

        outcome = ScrapeService(db_session).collect()

        assert outcome.found == 1
        assert list(stored(db_session)) == ["B0DUP00001"]
