"""Playwright scraper for Amazon best sellers, with parsing kept pure."""

import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from app.core.config import settings
from app.core.exceptions import ScrapingError
from app.core.logging import get_logger

logger = get_logger(__name__)

BASE_URL = "https://www.amazon.com"

_ASIN_RE = re.compile(r"/(?:dp|gp/product)/([A-Z0-9]{10})")
_ASIN_EXACT_RE = re.compile(r"^[A-Z0-9]{10}$")

_PRICE_RE = re.compile(r"(\d[\d,\s]*(?:[.,]\d{1,2})?)")
_RATING_RE = re.compile(r"([\d.,]+)\s*out of\s*5")
_RATING_CLASS_RE = re.compile(r"a-star(?:-small)?-(\d)(?:-(\d))?")
_DIGITS_RE = re.compile(r"[\d,\s]+")

_CURRENCY_BY_SYMBOL = {"$": "USD", "£": "GBP", "€": "EUR", "¥": "JPY", "₹": "INR"}
_CURRENCY_CODE_RE = re.compile(
    r"\b(USD|EUR|GBP|PLN|CAD|AUD|JPY|INR|SEK|CHF|CZK|UAH|NOK|DKK|MXN|BRL)\b"
)

_GENERIC_CATEGORY_TITLES = frozenset(
    {"amazon best sellers", "best sellers", "amazon.com best sellers", "any department"}
)
_CURRENT_SUFFIX_RE = re.compile(r"\(current\)\s*$", re.IGNORECASE)
_CATEGORY_SLUG_RE = re.compile(r"/zgbs/(?:[^/?#]+/)*([^/?#]+)")

_BLOCK_MARKERS = (
    "enter the characters you see below",
    "type the characters you see in this image",
    "robot check",
    "/errors/validatecaptcha",
    "we just need to make sure you're not a robot",
    "request was throttled",
    "sorry, we just need to make sure",
)

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

_US_LOCALE_COOKIES = [
    {"name": "i18n-prefs", "value": "USD", "domain": ".amazon.com", "path": "/"},
    {"name": "lc-main", "value": "en_US", "domain": ".amazon.com", "path": "/"},
]

_ITEM_SELECTORS = (
    "div#gridItemRoot",
    "div[class*='p13n-sc-uncoverable-faceout']",
    "li[class*='zg-item-immersion']",
    "div[data-asin]",
)


@dataclass(frozen=True, slots=True)
class ScrapedProduct:
    """One product as the scraper saw it, not yet a database row."""

    asin: str
    title: str
    category: str
    price: Decimal | None
    currency: str
    rating: float | None
    reviews_count: int
    product_url: str
    image_url: str | None


def detect_block(html: str) -> str | None:
    """Return the anti-bot marker found on the page, or None."""
    lowered = html.lower()
    return next((m for m in _BLOCK_MARKERS if m in lowered), None)


def parse_bestsellers(
    html: str,
    *,
    fallback_category: str = "Best Sellers",
    base_url: str = BASE_URL,
    limit: int | None = None,
) -> list[ScrapedProduct]:
    """Parse one Amazon Best Sellers page. Raises only on an anti-bot page."""
    if (marker := detect_block(html)) is not None:
        raise ScrapingError(f"Amazon served an anti-bot page (marker: {marker!r})")

    soup = BeautifulSoup(html, "lxml")
    category = _extract_category(soup) or fallback_category

    products: list[ScrapedProduct] = []
    seen: set[str] = set()

    for node in _iter_item_nodes(soup):
        product = _parse_item(node, category=category, base_url=base_url)
        if product is None or product.asin in seen:
            continue

        seen.add(product.asin)
        products.append(product)

        if limit is not None and len(products) >= limit:
            break

    logger.info("Parser: category %r, collected %d products", category, len(products))
    return products


def _iter_item_nodes(soup: BeautifulSoup) -> list[Tag]:
    """Product tiles. Amazon changes the wrapper periodically, so try each."""
    for selector in _ITEM_SELECTORS:
        if nodes := soup.select(selector):
            return nodes
    return []


def _parse_item(node: Tag, *, category: str, base_url: str) -> ScrapedProduct | None:
    link = _find_product_link(node)
    if link is None:
        return None

    href = str(link.get("href") or "")
    asin = _extract_asin(node, href)
    if not asin:
        return None

    title = _extract_title(node, link)
    if not title:
        return None

    price, currency = _extract_price(node)

    return ScrapedProduct(
        asin=asin,
        title=title,
        category=category,
        price=price,
        currency=currency,
        rating=_extract_rating(node),
        reviews_count=_extract_reviews_count(node),
        product_url=_absolute(href, base_url),
        image_url=_extract_image(node),
    )


def _find_product_link(node: Tag) -> Tag | None:
    """Find the product link in a tile, preferring the one carrying text."""
    candidates = [
        a
        for a in node.select("a[href]")
        if "/dp/" in str(a.get("href") or "") or "/gp/product/" in str(a.get("href") or "")
    ]
    if not candidates:
        return None
    return next((a for a in candidates if _clean(a.get_text())), candidates[0])


def _extract_asin(node: Tag, href: str) -> str | None:
    """Read the ASIN from the tile attributes, a nested node, or the URL."""
    for attr in ("data-asin", "id"):
        value = str(node.get(attr) or "").strip()
        if _ASIN_EXACT_RE.match(value):
            return value

    if (inner := node.select_one("[data-asin]")) is not None:
        value = str(inner.get("data-asin") or "").strip()
        if _ASIN_EXACT_RE.match(value):
            return value

    match = _ASIN_RE.search(href)
    return match.group(1) if match else None


def _extract_title(node: Tag, link: Tag) -> str | None:
    """Extract the product title from the tile, the image alt, or the link."""
    for selector in ("[class*='p13n-sc-truncate']", "[class*='line-clamp']"):
        found = node.select_one(selector)
        if found is not None and (text := _clean(found.get_text())):
            return text

    img = node.select_one("img[alt]")
    if img is not None and (alt := _clean(str(img.get("alt") or ""))):
        return alt

    return _clean(link.get_text()) or None


def _extract_image(node: Tag) -> str | None:
    img = node.select_one("img[src]")
    if img is None:
        return None

    src = _clean(str(img.get("src") or ""))
    if src.startswith("data:") and (srcset := str(img.get("srcset") or "")):
        src = _clean(srcset.split(",")[0].split(" ")[0])

    return src or None


def _extract_price(node: Tag) -> tuple[Decimal | None, str]:
    """Price and currency, matched on a class substring."""
    for selector in (
        "[class*='p13n-sc-price']",
        "span.a-price span.a-offscreen",
        "[class*='price']",
    ):
        for found in node.select(selector):
            text = _clean(found.get_text())
            if (parsed := _parse_price(text)) is not None:
                return parsed, _detect_currency(text)

    return None, "USD"


def _parse_price(text: str) -> Decimal | None:
    match = _PRICE_RE.search(text)
    if match is None:
        return None

    raw = match.group(1).replace(" ", "").replace(",", "")
    try:
        price = Decimal(raw)
    except InvalidOperation:
        return None

    return price if 0 < price < Decimal("100000000") else None


def _detect_currency(text: str) -> str:
    """Detect the currency of a price string, code first, then symbol."""
    if (found := _CURRENCY_CODE_RE.search(text.upper())) is not None:
        return found.group(1)
    return next((code for sym, code in _CURRENCY_BY_SYMBOL.items() if sym in text), "USD")


def _extract_rating(node: Tag) -> float | None:
    """Read '4.6 out of 5 stars' from text, title or aria-label."""
    candidates: list[str] = []

    if (alt := node.select_one("span.a-icon-alt")) is not None:
        candidates.append(alt.get_text())

    for element in node.select("[title], [aria-label]"):
        candidates.append(str(element.get("title") or ""))
        candidates.append(str(element.get("aria-label") or ""))

    for text in candidates:
        if (match := _RATING_RE.search(text)) is not None:
            value = _to_float(match.group(1).replace(",", "."))
            if value is not None and 0 <= value <= 5:
                return value

    return _rating_from_class(node)


def _rating_from_class(node: Tag) -> float | None:
    """Fallback: the class `a-star-small-4-5` means 4.5."""
    for icon in node.select("i[class]"):
        classes = " ".join(icon.get("class") or [])
        if (match := _RATING_CLASS_RE.search(classes)) is not None:
            whole, half = match.group(1), match.group(2) or "0"
            value = float(f"{whole}.{half}")
            if 0 <= value <= 5:
                return value
    return None


def _extract_reviews_count(node: Tag) -> int:
    """Review count, arriving as '12,345' or '(12,345)'."""
    for selector in (
        "a[href*='#customerReviews'] span",
        "div.a-icon-row span.a-size-small",
        "span.a-size-small",
        "[class*='review']",
    ):
        for found in node.select(selector):
            text = _clean(found.get_text()).strip("()")
            if (match := _DIGITS_RE.fullmatch(text)) is not None:
                digits = match.group(0).replace(",", "").replace(" ", "")
                if digits.isdigit():
                    return int(digits)

    return 0


def _extract_category(soup: BeautifulSoup) -> str | None:
    """Find the specific category name, skipping the generic site-wide banner."""
    for selector in (
        "h1",
        "[class*='zg-selected']",
        "[class*='zg_selected']",
        "div.a-breadcrumb li:last-of-type span.a-list-item",
        "#zg_banner_text",
    ):
        for found in soup.select(selector):
            text = _clean(_CURRENT_SUFFIX_RE.sub("", _clean(found.get_text())))
            if text and text.lower() not in _GENERIC_CATEGORY_TITLES:
                return text[:255]

    if (title := soup.find("title")) is not None:
        text = _clean(title.get_text())
        if ":" in text:
            text = text.split(":", 1)[1]
        cleaned = _clean(text.replace("Amazon.com", ""))
        if cleaned and cleaned.lower() not in _GENERIC_CATEGORY_TITLES:
            return cleaned[:255]

    return None


def category_from_url(url: str) -> str:
    """Derive a readable category from the URL slug: 'home-garden' -> 'Home Garden'."""
    match = _CATEGORY_SLUG_RE.search(url)
    if match is None:
        return "Best Sellers"
    slug = match.group(1).replace("-", " ").replace("_", " ")
    return _clean(slug).title()[:255] or "Best Sellers"


def _absolute(href: str, base_url: str) -> str:
    return href if href.startswith("http") else urljoin(base_url, href)


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _to_float(value: str) -> float | None:
    try:
        return float(value)
    except ValueError:
        return None


class AmazonScraper:
    """Thin Playwright wrapper whose only job is to return page HTML."""

    def __init__(
        self,
        *,
        headless: bool | None = None,
        proxy: str | None = None,
        timeout_ms: int = 60_000,
    ) -> None:
        self.headless = settings.playwright_headless if headless is None else headless
        self.proxy = proxy if proxy is not None else (settings.scrape_proxy or None)
        self.timeout_ms = timeout_ms

    def fetch_many(self, urls: list[str]) -> dict[str, str | ScrapingError]:
        """Fetch HTML for several pages in one session; failures come back as values."""
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright

        if not urls:
            return {}

        results: dict[str, str | ScrapingError] = {}

        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(
                    headless=self.headless,
                    proxy={"server": self.proxy} if self.proxy else None,
                    args=[
                        "--disable-blink-features=AutomationControlled",
                        "--no-sandbox",
                        "--disable-dev-shm-usage",
                    ],
                )
                try:
                    context = browser.new_context(
                        user_agent=_USER_AGENT,
                        viewport={"width": 1440, "height": 900},
                        locale="en-US",
                        timezone_id="America/New_York",
                        extra_http_headers={"Accept-Language": "en-US,en;q=0.9"},
                    )
                    context.add_cookies(_US_LOCALE_COOKIES)
                    for url in urls:
                        results[url] = self._fetch_one(context, url)
                finally:
                    browser.close()

        except PlaywrightError as exc:
            raise ScrapingError(f"Could not start the browser: {exc}") from exc

        return results

    def _fetch_one(self, context, url: str) -> str | ScrapingError:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import TimeoutError as PlaywrightTimeout

        logger.info("Scrape: opening %s (headless=%s)", url, self.headless)
        page = context.new_page()

        try:
            page.set_default_timeout(self.timeout_ms)
            page.goto(url, wait_until="domcontentloaded", timeout=self.timeout_ms)
            self._wait_for_grid(page)
            self._scroll_to_bottom(page)
            html = page.content()
        except PlaywrightTimeout as exc:
            return ScrapingError(f"Timed out loading {url}: {exc}")
        except PlaywrightError as exc:
            return ScrapingError(f"Browser error on {url}: {exc}")
        finally:
            page.close()

        if (marker := detect_block(html)) is not None:
            logger.warning("Scrape: anti-bot triggered on %s (marker %r)", url, marker)
            return ScrapingError(f"Amazon blocked the request (marker: {marker!r})")

        logger.info("Scrape: received %d bytes of HTML from %s", len(html), url)
        return html

    def _wait_for_grid(self, page) -> None:
        """Wait for the product grid; a missing grid is not fatal."""
        from playwright.sync_api import TimeoutError as PlaywrightTimeout

        try:
            page.wait_for_selector(", ".join(_ITEM_SELECTORS), timeout=20_000)
        except PlaywrightTimeout:
            logger.warning("Scrape: product grid did not appear in 20s, parsing as is")

    def _scroll_to_bottom(self, page, *, steps: int = 6) -> None:
        """Scroll down so Amazon lazy-loads the lower tiles and their images."""
        for _ in range(steps):
            page.mouse.wheel(0, 2000)
            page.wait_for_timeout(400)
        page.wait_for_timeout(1000)


@dataclass
class CategoryScrapeOutcome:
    """Products gathered across categories, plus why any of them failed."""

    products: list[ScrapedProduct] = field(default_factory=list)
    failures: dict[str, str] = field(default_factory=dict)


def scrape_categories(
    urls: list[str] | None = None,
    *,
    limit_per_category: int | None = None,
    scraper: AmazonScraper | None = None,
) -> CategoryScrapeOutcome:
    """Full cycle across several categories: browser -> HTML -> products."""
    target_urls = urls if urls is not None else settings.category_urls
    max_items = (
        limit_per_category
        if limit_per_category is not None
        else settings.scrape_max_products
    )

    outcome = CategoryScrapeOutcome()
    for url, result in (scraper or AmazonScraper()).fetch_many(target_urls).items():
        if isinstance(result, ScrapingError):
            logger.warning("Scrape: category %s failed, %s", url, result)
            outcome.failures[url] = str(result)
            continue

        try:
            outcome.products.extend(
                parse_bestsellers(
                    result,
                    base_url=BASE_URL,
                    limit=max_items,
                    fallback_category=category_from_url(url),
                )
            )
        except ScrapingError as exc:
            logger.warning("Scrape: category %s blocked, %s", url, exc)
            outcome.failures[url] = str(exc)

    logger.info(
        "Scrape: %d categories, %d products, %d failed categories",
        len(target_urls),
        len(outcome.products),
        len(outcome.failures),
    )
    return outcome
