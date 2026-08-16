"""Тести розбору відповіді Google Trends. Браузер не запускається."""

import json

import pytest

from app.core.exceptions import ExternalServiceError
from app.integrations.google_trends import parse_widget_payload

# Google префіксує JSON цим рядком — захист від JSON hijacking
PREFIX = ")]}',\n"


def payload(values: list[int]) -> str:
    body = {"default": {"timelineData": [{"value": [v]} for v in values]}}
    return PREFIX + json.dumps(body)


class TestParsing:
    def test_computes_average_and_recent_interest(self):
        """Останні 4 точки ≈ останній місяць, решта — база для порівняння."""
        result = parse_widget_payload(payload([20, 20, 20, 20, 40, 40, 40, 40]), keyword="yoga")

        assert result.interest_avg == 30.0
        assert result.interest_now == 40.0
        assert result.keyword == "yoga"

    def test_delta_shows_growth(self):
        result = parse_widget_payload(payload([20, 20, 20, 20, 40, 40, 40, 40]), keyword="yoga")
        assert result.delta_pct == 33.33

    def test_delta_shows_decline(self):
        result = parse_widget_payload(payload([40, 40, 40, 40, 20, 20, 20, 20]), keyword="yoga")
        assert result.delta_pct == -33.33

    def test_keeps_raw_points(self):
        result = parse_widget_payload(payload([1, 2, 3, 4]), keyword="yoga")
        assert result.points == [1, 2, 3, 4]


class TestEdgeCases:
    def test_flat_zero_interest_gives_zero_delta(self):
        """Ділити на нуль не можна, і зростання тут теж немає."""
        result = parse_widget_payload(payload([0, 0, 0, 0]), keyword="dead")
        assert result.delta_pct == 0.0
        assert result.interest_avg == 0.0

    def test_single_point(self):
        result = parse_widget_payload(payload([50]), keyword="new")
        assert result.interest_now == 50.0
        assert result.delta_pct == 0.0

    def test_skips_entries_without_values(self):
        raw = PREFIX + json.dumps(
            {"default": {"timelineData": [{"value": [10]}, {}, {"value": []}, {"value": [30]}]}}
        )
        assert parse_widget_payload(raw, keyword="x").points == [10, 30]


class TestBrokenResponses:
    def test_empty_timeline_raises(self):
        """Порожній ряд — це «даних немає», і краще чесно записати
        'unavailable', ніж вигадати нулі."""
        with pytest.raises(ExternalServiceError, match="не має даних"):
            parse_widget_payload(payload([]), keyword="unknown")

    def test_broken_json_raises(self):
        with pytest.raises(ExternalServiceError, match="неочікуваний формат"):
            parse_widget_payload(PREFIX + "{not json", keyword="x")

    def test_missing_keys_raise(self):
        with pytest.raises(ExternalServiceError, match="неочікуваний формат"):
            parse_widget_payload(PREFIX + json.dumps({"something": "else"}), keyword="x")

    def test_html_instead_of_json_raises(self):
        """Google інколи віддає сторінку капчі замість JSON."""
        with pytest.raises(ExternalServiceError):
            parse_widget_payload("<html><body>captcha</body></html>", keyword="x")
