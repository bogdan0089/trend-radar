"""Demand dynamics from Google Trends, read from the widget JSON via Playwright."""

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

_JSON_PREFIX_RE = re.compile(r"^[^{]*")

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

_RECENT_POINTS = 4

MIN_RELIABLE_INTEREST = 5.0


@dataclass(frozen=True, slots=True)
class TrendResult:
    """Demand dynamics for one keyword, as a 0..100 index and its change."""

    keyword: str
    interest_now: float
    interest_avg: float
    delta_pct: float
    points: list[int]

    @property
    def is_reliable(self) -> bool:
        """False when the yearly average is too low for the percentage to mean anything."""
        return self.interest_avg >= MIN_RELIABLE_INTEREST


def parse_widget_payload(raw: str, *, keyword: str) -> TrendResult:
    """Convert the Google Trends widget JSON into a TrendResult."""
    cleaned = _JSON_PREFIX_RE.sub("", raw, count=1)

    try:
        payload = json.loads(cleaned)
        timeline = payload["default"]["timelineData"]
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise ExternalServiceError(f"Google Trends returned an unexpected format: {exc}") from exc

    points = [
        int(item["value"][0])
        for item in timeline
        if isinstance(item.get("value"), list) and item["value"]
    ]
    if not points:
        raise ExternalServiceError(f"Google Trends has no data for '{keyword}'")

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
    """Percentage by which recent interest exceeds the period average."""
    if avg == 0:
        return 0.0
    return round((now - avg) / avg * 100, 2)


class GoogleTrendsScraper:
    """Opens Trends in Playwright and captures the widget JSON off the network."""

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
        """Collect trends for several keywords; failures come back as values."""
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
                            time.sleep(self.delay_seconds)
                        results[keyword] = self._fetch_one(context, keyword)
                finally:
                    browser.close()

        except PlaywrightError as exc:
            raise ExternalServiceError(f"Could not start the browser for Trends: {exc}") from exc

        return results

    def _fetch_one(self, context, keyword: str) -> TrendResult | ExternalServiceError:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import TimeoutError as PlaywrightTimeout

        url = (
            f"{EXPLORE_URL}?q={quote(keyword)}"
            f"&date={quote(self.period)}&geo={self.geo}&hl=en-US"
        )
        logger.info("Trends: querying keyword %r", keyword)

        payloads: list[str] = []
        page = context.new_page()

        try:
            page.on("response", lambda r: self._capture(r, payloads))
            page.goto(url, wait_until="domcontentloaded", timeout=self.timeout_ms)
            self._wait_for_payload(page, payloads)

            if not payloads:
                return ExternalServiceError(
                    f"Google Trends returned no data for '{keyword}' "
                    "(empty query, rate limit or captcha)"
                )
            return parse_widget_payload(payloads[0], keyword=keyword)

        except PlaywrightTimeout as exc:
            return ExternalServiceError(f"Google Trends timed out on '{keyword}': {exc}")
        except PlaywrightError as exc:
            return ExternalServiceError(f"Browser error on '{keyword}': {exc}")
        except ExternalServiceError as exc:
            return exc
        finally:
            page.close()

    @staticmethod
    def _capture(response, payloads: list[str]) -> None:
        if WIDGET_URL_MARKER not in response.url or not response.ok:
            return
        try:
            payloads.append(response.text())
        except Exception as exc:  # noqa: BLE001 - the body may already be gone
            logger.debug("Trends: could not read the response: %s", exc)

    def _wait_for_payload(self, page, payloads: list[str], *, attempts: int = 30) -> None:
        """Wait for the listener to capture the widget, half a second per try."""
        for _ in range(attempts):
            if payloads:
                return
            page.wait_for_timeout(500)
