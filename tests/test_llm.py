"""Тести розбору відповіді LLM.

Мережа не піднімається: перевіряємо тільки чисту функцію parse_verdict, яка
вирішує, чи можна довіряти тому, що повернула модель.
"""

import pytest

from app.core.exceptions import ExternalServiceError
from app.integrations.llm import parse_verdict


class TestValidResponses:
    def test_plain_json(self):
        verdict = parse_verdict('{"score": 78, "reasoning": "Попит зростає"}')
        assert verdict.score == 78
        assert verdict.reasoning == "Попит зростає"

    def test_json_in_markdown_fence(self):
        """Моделі часто загортають JSON у ```json ... ```."""
        raw = '```json\n{"score": 55, "reasoning": "Середній потенціал"}\n```'
        assert parse_verdict(raw).score == 55

    def test_json_surrounded_by_text(self):
        raw = 'Ось моя оцінка:\n{"score": 90, "reasoning": "Сильний тренд"}\nСподіваюсь, корисно.'
        assert parse_verdict(raw).score == 90

    def test_float_score_is_rounded(self):
        assert parse_verdict('{"score": 72.6, "reasoning": "ок"}').score == 73

    def test_score_as_string(self):
        assert parse_verdict('{"score": "64", "reasoning": "ок"}').score == 64

    def test_object_wrapped_in_array(self):
        """Модель повернула список з одного вердикту — беремо перший об'єкт.
        Розбирати такий випадок дешевше, ніж без потреби падати на формулу."""
        assert parse_verdict('[{"score": 50, "reasoning": "ок"}]').score == 50


class TestClamping:
    """Модель інколи вигадує бал поза шкалою — обрізаємо, а не падаємо:
    сама оцінка змістовна, вийшов за межі лише формат."""

    def test_above_100(self):
        assert parse_verdict('{"score": 150, "reasoning": "ок"}').score == 100

    def test_below_zero(self):
        assert parse_verdict('{"score": -20, "reasoning": "ок"}').score == 0


class TestBrokenResponses:
    """Не розібрали — кидаємо виняток, і скоринг чесно падає на формулу."""

    def test_not_json_at_all(self):
        with pytest.raises(ExternalServiceError, match="не є JSON"):
            parse_verdict("Вибачте, я не можу оцінити цей товар.")

    def test_missing_score(self):
        with pytest.raises(ExternalServiceError, match="немає score"):
            parse_verdict('{"reasoning": "щось"}')

    def test_missing_reasoning(self):
        with pytest.raises(ExternalServiceError, match="немає score"):
            parse_verdict('{"score": 50}')

    def test_empty_reasoning(self):
        """Порожній reasoning не проходить: ТЗ вимагає пояснення оцінки."""
        with pytest.raises(ExternalServiceError, match="порожній reasoning"):
            parse_verdict('{"score": 50, "reasoning": "   "}')

    def test_score_is_not_a_number(self):
        with pytest.raises(ExternalServiceError, match="немає score"):
            parse_verdict('{"score": "високий", "reasoning": "ок"}')

    def test_empty_response(self):
        with pytest.raises(ExternalServiceError):
            parse_verdict("")
