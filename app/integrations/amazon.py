"""Скрапер топ-товарів Amazon на Playwright.

Модуль свідомо поділений на дві незалежні частини:

1. `parse_bestsellers()` — чиста функція `HTML -> список товарів`. Без мережі,
   без браузера, без БД. Тестується на збереженому снапшоті за мілісекунди.
2. `AmazonScraper` — Playwright: відкриває реальний Chromium, ходить на Amazon,
   віддає HTML. Розбирати його — не його справа.

Завдяки цьому поділу той самий парсер обслуговує і живий скрапінг, і сід із
локального снапшота. Коли Amazon змінить верстку — правити треба одну функцію.
"""

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from app.core.config import settings
from app.core.exceptions import ScrapingError
from app.core.logging import get_logger

logger = get_logger(__name__)

BASE_URL = "https://www.amazon.com"

# ASIN — внутрішній ідентифікатор товару Amazon: рівно 10 символів [A-Z0-9].
# Використовуємо його як ключ дедуплікації між запусками скрапера.
_ASIN_RE = re.compile(r"/(?:dp|gp/product)/([A-Z0-9]{10})")
_ASIN_EXACT_RE = re.compile(r"^[A-Z0-9]{10}$")

_PRICE_RE = re.compile(r"(\d[\d,\s]*(?:[.,]\d{1,2})?)")
_RATING_RE = re.compile(r"([\d.,]+)\s*out of\s*5")
# Клас виду `a-star-small-4-5` — запасний шлях, коли текстового рейтингу нема
_RATING_CLASS_RE = re.compile(r"a-star(?:-small)?-(\d)(?:-(\d))?")
_DIGITS_RE = re.compile(r"[\d,\s]+")

_CURRENCY_BY_SYMBOL = {"$": "USD", "£": "GBP", "€": "EUR", "¥": "JPY", "₹": "INR"}

# Маркери сторінки-заглушки антибота. Побачили — далі парсити нема сенсу.
_BLOCK_MARKERS = (
    "enter the characters you see below",
    "type the characters you see in this image",
    "robot check",
    "/errors/validatecaptcha",
    "we just need to make sure you're not a robot",
    "request was throttled",
    "sorry, we just need to make sure",
)

# Реальний десктопний UA. Дефолтний UA Playwright містить `HeadlessChrome`
# і його ріжуть на першому ж запиті.
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

# Плитка товару в сітці Best Sellers. Перший селектор, що дав результат, виграє.
_ITEM_SELECTORS = (
    "div#gridItemRoot",
    "div[class*='p13n-sc-uncoverable-faceout']",
    "li[class*='zg-item-immersion']",
    "div[data-asin]",
)


@dataclass(frozen=True, slots=True)
class ScrapedProduct:
    """Один товар так, як його побачив скрапер. Ще не рядок БД.

    `frozen` — щоб ніхто нижче по стеку не «підправив» сирі дані парсингу.
    """

    asin: str
    title: str
    category: str
    price: Decimal | None
    currency: str
    rating: float | None
    reviews_count: int
    product_url: str
    image_url: str | None


# --------------------------------------------------------------------------- #
#  Чистий парсинг: HTML -> ScrapedProduct
# --------------------------------------------------------------------------- #


def detect_block(html: str) -> str | None:
    """Повертає маркер антибота, якщо сторінка — заглушка. Інакше None."""
    lowered = html.lower()
    return next((m for m in _BLOCK_MARKERS if m in lowered), None)


def parse_bestsellers(
    html: str,
    *,
    fallback_category: str = "Best Sellers",
    base_url: str = BASE_URL,
    limit: int | None = None,
) -> list[ScrapedProduct]:
    """Розбирає сторінку Amazon Best Sellers.

    Товари без ASIN, назви або посилання пропускаються — це три поля, без яких
    рядок у БД не має сенсу. Решта полів необовʼязкові: Amazon регулярно ховає
    ціну («See price in cart») або показує товар без жодного відгуку.

    Кидає ScrapingError лише якщо сторінка виявилась заглушкою антибота.
    Порожній результат на валідній сторінці — не виняток, а факт для ScrapeRun.
    """
    if (marker := detect_block(html)) is not None:
        raise ScrapingError(f"Amazon показав сторінку антибота (маркер: {marker!r})")

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

    logger.info("Парсер: категорія %r, зібрано %d товарів", category, len(products))
    return products


def _iter_item_nodes(soup: BeautifulSoup) -> list[Tag]:
    """Плитки товарів. Amazon час від часу міняє обгортку — пробуємо по черзі."""
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
    """Посилання на картку товару. Ігноруємо лінк на відгуки — він теж <a>."""
    for candidate in node.select("a[href]"):
        href = str(candidate.get("href") or "")
        if "/dp/" in href or "/gp/product/" in href:
            return candidate
    return None


def _extract_asin(node: Tag, href: str) -> str | None:
    # 1. Атрибут data-asin — найнадійніше, коли він є
    for attr in ("data-asin", "id"):
        value = str(node.get(attr) or "").strip()
        if _ASIN_EXACT_RE.match(value):
            return value

    # 2. Вкладений елемент з data-asin
    if (inner := node.select_one("[data-asin]")) is not None:
        value = str(inner.get("data-asin") or "").strip()
        if _ASIN_EXACT_RE.match(value):
            return value

    # 3. З URL: /Product-Name/dp/B0XXXXXXXX/...
    match = _ASIN_RE.search(href)
    return match.group(1) if match else None


def _extract_title(node: Tag, link: Tag) -> str | None:
    """Назва товару.

    Порядок не випадковий: `alt` картинки Amazon заповнює повною назвою і майже
    ніколи не міняє, тоді як класи текстових блоків у них хешовані й «пливуть».
    """
    if (img := node.select_one("img[alt]")) is not None:
        if alt := _clean(str(img.get("alt") or "")):
            return alt

    for selector in ("[class*='line-clamp']", "[class*='p13n-sc-truncate']", "span", "div"):
        if (found := link.select_one(selector)) is not None:
            if text := _clean(found.get_text()):
                return text

    return _clean(link.get_text()) or None


def _extract_image(node: Tag) -> str | None:
    img = node.select_one("img[src]")
    if img is None:
        return None

    src = _clean(str(img.get("src") or ""))
    # Amazon віддає плейсхолдер у src і справжню картинку в srcset — беремо її
    if src.startswith("data:") and (srcset := str(img.get("srcset") or "")):
        src = _clean(srcset.split(",")[0].split(" ")[0])

    return src or None


def _extract_price(node: Tag) -> tuple[Decimal | None, str]:
    """Ціна і валюта. Клас у них хешований (`_cDEzb_p13n-sc-price_3mJ9Z`),
    тому шукаємо за підрядком у class, а не за точним іменем."""
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

    # Numeric(10, 2) у моделі: більше не влізе, а такі значення — сміття парсингу
    return price if 0 < price < Decimal("100000000") else None


def _detect_currency(text: str) -> str:
    return next((code for sym, code in _CURRENCY_BY_SYMBOL.items() if sym in text), "USD")


def _extract_rating(node: Tag) -> float | None:
    """Рейтинг: 'Amazon 4.6 out of 5 stars' у тексті, title або aria-label."""
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
    """Запасний шлях: клас `a-star-small-4-5` означає 4.5."""
    for icon in node.select("i[class]"):
        classes = " ".join(icon.get("class") or [])
        if (match := _RATING_CLASS_RE.search(classes)) is not None:
            whole, half = match.group(1), match.group(2) or "0"
            value = float(f"{whole}.{half}")
            if 0 <= value <= 5:
                return value
    return None


def _extract_reviews_count(node: Tag) -> int:
    """Кількість відгуків. Приходить як '12,345' або '(12,345)'.

    Свідомо НЕ беремо будь-яке число зі сторінки: поряд лежать ціна й позиція
    в рейтингу, і жадібний регекс легко підхопить їх замість відгуків.
    """
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
    """Назва категорії: хлібні крихти → банер → <title> сторінки."""
    for selector in (
        "[class*='zg_selected']",
        "#zg_banner_text",
        "div.a-breadcrumb li:last-of-type span.a-list-item",
        "h1",
    ):
        if (found := soup.select_one(selector)) is not None:
            if text := _clean(found.get_text()):
                return text[:255]

    if (title := soup.find("title")) is not None:
        # 'Amazon Best Sellers: Best Kitchen & Dining' -> 'Best Kitchen & Dining'
        text = _clean(title.get_text())
        if ":" in text:
            text = text.split(":", 1)[1]
        if cleaned := _clean(text.replace("Amazon.com", "")):
            return cleaned[:255]

    return None


def _absolute(href: str, base_url: str) -> str:
    return href if href.startswith("http") else urljoin(base_url, href)


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _to_float(value: str) -> float | None:
    try:
        return float(value)
    except ValueError:
        return None


# --------------------------------------------------------------------------- #
#  Playwright: реальний браузер -> HTML
# --------------------------------------------------------------------------- #


class AmazonScraper:
    """Тонка обгортка над Playwright. Уміє рівно одне: віддати HTML сторінки.

    Синхронний API (`sync_playwright`) — навмисно: цей код виконується всередині
    Celery-таски, яка теж синхронна. Асинхронний варіант вимагав би окремого
    event loop у воркері й давав би більше проблем, ніж користі.
    """

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

    def fetch_html(self, url: str) -> str:
        """Відкриває сторінку і повертає її HTML після довантаження сітки.

        Кидає ScrapingError на таймаут, падіння браузера або сторінку антибота.
        """
        # Імпорт локальний: у контейнері api Playwright не встановлений браузером,
        # і модуль не має падати на імпорті лише тому, що хтось його зачепив.
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import TimeoutError as PlaywrightTimeout
        from playwright.sync_api import sync_playwright

        logger.info("Скрапінг: відкриваю %s (headless=%s)", url, self.headless)

        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(
                    headless=self.headless,
                    proxy={"server": self.proxy} if self.proxy else None,
                    args=[
                        # Прибирає navigator.webdriver — найпростіший маркер бота
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
                    page = context.new_page()
                    page.set_default_timeout(self.timeout_ms)
                    page.goto(url, wait_until="domcontentloaded", timeout=self.timeout_ms)
                    self._wait_for_grid(page)
                    self._scroll_to_bottom(page)
                    html = page.content()
                finally:
                    browser.close()

        except PlaywrightTimeout as exc:
            raise ScrapingError(f"Таймаут при завантаженні {url}: {exc}") from exc
        except PlaywrightError as exc:
            raise ScrapingError(f"Помилка браузера на {url}: {exc}") from exc

        if (marker := detect_block(html)) is not None:
            logger.warning("Скрапінг: спрацював антибот на %s (маркер %r)", url, marker)
            raise ScrapingError(f"Amazon заблокував запит (маркер: {marker!r})")

        logger.info("Скрапінг: отримано %d байт HTML з %s", len(html), url)
        return html

    def _wait_for_grid(self, page) -> None:
        """Чекає сітку товарів. Її відсутність — не привід падати одразу:
        нехай парсер сам скаже, що знайшов нуль, і це запишеться у ScrapeRun."""
        from playwright.sync_api import TimeoutError as PlaywrightTimeout

        try:
            page.wait_for_selector(", ".join(_ITEM_SELECTORS), timeout=20_000)
        except PlaywrightTimeout:
            logger.warning("Скрапінг: сітка товарів не зʼявилась за 20 с — парсимо як є")

    def _scroll_to_bottom(self, page, *, steps: int = 6) -> None:
        """Amazon вантажить нижні плитки й картинки лениво — без прокрутки
        половина товарів приходить із порожнім image_url."""
        for _ in range(steps):
            page.mouse.wheel(0, 2000)
            page.wait_for_timeout(400)
        page.wait_for_timeout(1000)


def scrape_bestsellers(
    url: str | None = None,
    *,
    limit: int | None = None,
    scraper: AmazonScraper | None = None,
) -> list[ScrapedProduct]:
    """Повний цикл: браузер → HTML → список товарів.

    `scraper` можна підмінити у тестах, не піднімаючи Chromium.
    """
    target_url = url or settings.amazon_category_url
    max_items = limit if limit is not None else settings.scrape_max_products

    html = (scraper or AmazonScraper()).fetch_html(target_url)
    return parse_bestsellers(html, base_url=BASE_URL, limit=max_items)