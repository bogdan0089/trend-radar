"""Динаміка попиту з Google Trends через Playwright.

Чому не парсимо графік зі сторінки: він малюється як <svg> з координатами
точок, а не зі значеннями. Натомість слухаємо мережу браузера — сторінка сама
тягне JSON з /api/widgetdata/multiline, з якого той графік і будується.
Браузер справжній, дані чисті.

Як і в amazon.py, розбір відповіді (`parse_widget_payload`) відділений від
мережі й тестується без запуску Chromium.
"""

import json
import re
import time
from dataclasses import dataclass
from statistics import mean
from urllib.parse import quote

from app.core.config import settings
from app.core.exceptions import ExternalServiceError
from app.core.logging import get_logger

logger = get_logger(__name__)

EXPLORE_URL = "https://trends.google.com/trends/explore"
WIDGET_URL_MARKER = "/api/widgetdata/multiline"

# Google префіксує JSON рядком ")]}'," — захист від JSON hijacking.
# json.loads на ньому падає, тож зрізаємо все до першої фігурної дужки.
_JSON_PREFIX_RE = re.compile(r"^[^{]*")

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

# Скільки останніх точок вважаємо «зараз». Крок ряду за 12 місяців — тиждень,
# тож 4 точки ≈ останній місяць. Одна точка була б надто шумною.
_RECENT_POINTS = 4


@dataclass(frozen=True, slots=True)
class TrendResult:
    """Динаміка попиту за одним ключовим словом.

    Значення Google Trends — не абсолютні запити, а індекс 0..100 відносно піку
    за обраний період. Тому цінне саме порівняння «зараз» проти «в середньому».
    """

    keyword: str
    interest_now: float
    interest_avg: float
    delta_pct: float
    points: list[int]


def parse_widget_payload(raw: str, *, keyword: str) -> TrendResult:
    """JSON віджета Google Trends → TrendResult.

    Кидає ExternalServiceError, якщо відповідь не та, на яку ми розраховували:
    краще чесно записати «тренд недоступний», ніж вигадати нулі.
    """
    cleaned = _JSON_PREFIX_RE.sub("", raw, count=1)

    try:
        payload = json.loads(cleaned)
        timeline = payload["default"]["timelineData"]
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise ExternalServiceError(f"Google Trends віддав неочікуваний формат: {exc}") from exc

    points = [
        int(item["value"][0])
        for item in timeline
        if isinstance(item.get("value"), list) and item["value"]
    ]
    if not points:
        raise ExternalServiceError(f"Google Trends не має даних за '{keyword}'")

    interest_avg = mean(points)
    interest_now = mean(points[-_RECENT_POINTS:])

    return TrendResult(
        keyword=keyword,
        interest_now=round(interest_now, 2),
        interest_avg=round(interest_avg, 2),
        delta_pct=_delta_pct(now=interest_now, avg=interest_avg),
        points=points,
    )


def _delta_pct(*, now: float, avg: float) -> float:
    """На скільки відсотків свіжий інтерес вищий за середній.

    avg == 0 означає рівний нуль на всьому періоді — попиту немає взагалі.
    Ділити на нуль не можна, і зростання тут теж немає, тож 0.0.
    """
    if avg == 0:
        return 0.0
    return round((now - avg) / avg * 100, 2)


class GoogleTrendsScraper:
    """Playwright: відкриває Trends і ловить JSON віджета з мережі."""

    def __init__(
        self,
        *,
        headless: bool | None = None,
        proxy: str | None = None,
        timeout_ms: int = 45_000,
        geo: str = "US",
        period: str = "today 12-m",
        delay_seconds: float = 2.0,
    ) -> None:
        self.headless = settings.playwright_headless if headless is None else headless
        self.proxy = proxy if proxy is not None else (settings.scrape_proxy or None)
        self.timeout_ms = timeout_ms
        self.geo = geo
        self.period = period
        self.delay_seconds = delay_seconds

    def fetch_many(self, keywords: list[str]) -> dict[str, TrendResult | ExternalServiceError]:
        """Збирає тренди по списку слів за ОДНУ сесію браузера.

        Запуск Chromium коштує ~10 секунд. На 20 товарах окремі запуски дали б
        3+ хвилини самого лише старту, тож браузер піднімається один раз, а
        сторінка перевідкривається на кожне слово.

        Помилка по одному слову не валить решту: вона лягає в результат як
        значення-виняток, і сервіс запише для цього товару 'unavailable'.
        """
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright

        if not keywords:
            return {}

        results: dict[str, TrendResult | ExternalServiceError] = {}

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
                    )
                    for index, keyword in enumerate(keywords):
                        if index:
                            # Google ріже надто щільні запити (429). Пауза між
                            # словами дешевша, ніж бан на всю сесію.
                            time.sleep(self.delay_seconds)
                        results[keyword] = self._fetch_one(context, keyword)
                finally:
                    browser.close()

        except PlaywrightError as exc:
            raise ExternalServiceError(f"Не вдалося підняти браузер для Trends: {exc}") from exc

        return results

    def fetch(self, keyword: str) -> TrendResult:
        """Одне слово. Зручно для ручної перевірки і тестів."""
        result = self.fetch_many([keyword])[keyword]
        if isinstance(result, ExternalServiceError):
            raise result
        return result

    def _fetch_one(self, context, keyword: str) -> TrendResult | ExternalServiceError:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import TimeoutError as PlaywrightTimeout

        url = (
            f"{EXPLORE_URL}?q={quote(keyword)}"
            f"&date={quote(self.period)}&geo={self.geo}&hl=en-US"
        )
        logger.info("Trends: запит по ключовому слову %r", keyword)

        payloads: list[str] = []
        page = context.new_page()

        try:
            # Слухач вішається ДО переходу: віджет вантажиться одразу після
            # відкриття, і на пізню підписку ми б не встигли.
            page.on("response", lambda r: self._capture(r, payloads))
            page.goto(url, wait_until="domcontentloaded", timeout=self.timeout_ms)
            self._wait_for_payload(page, payloads)

            if not payloads:
                return ExternalServiceError(
                    f"Google Trends не віддав дані по '{keyword}' "
                    "(порожній запит, ліміт частоти або капча)"
                )
            return parse_widget_payload(payloads[0], keyword=keyword)

        except PlaywrightTimeout as exc:
            return ExternalServiceError(f"Таймаут Google Trends на '{keyword}': {exc}")
        except PlaywrightError as exc:
            return ExternalServiceError(f"Помилка браузера на '{keyword}': {exc}")
        except ExternalServiceError as exc:
            return exc
        finally:
            page.close()

    @staticmethod
    def _capture(response, payloads: list[str]) -> None:
        """Callback на кожну мережеву відповідь браузера."""
        if WIDGET_URL_MARKER not in response.url or not response.ok:
            return
        try:
            payloads.append(response.text())
        except Exception as exc:  # noqa: BLE001 — тіло могло вже зникнути
            logger.debug("Trends: не вдалося прочитати відповідь: %s", exc)

    def _wait_for_payload(self, page, payloads: list[str], *, attempts: int = 30) -> None:
        """Чекає, поки слухач упіймає віджет. Пів секунди на спробу."""
        for _ in range(attempts):
            if payloads:
                return
            page.wait_for_timeout(500)
