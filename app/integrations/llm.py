"""Адаптери LLM-провайдерів під спільним інтерфейсом.

ТЗ вимагає, щоб провайдер і ключ задавались через .env, тож обидва провайдери
викликаються по HTTP (httpx), а не через два різні SDK. Сервіс скорингу знає
тільки про `LLMClient` і не здогадується, хто саме за ним стоїть.

Без ключа `build_client()` повертає None — і скоринг іде на детерміновану
формулу. Проєкт має підніматись без API-ключа.
"""

import json
import re
from dataclasses import dataclass
from typing import Protocol

import httpx

from app.core.config import settings
from app.core.exceptions import ExternalServiceError
from app.core.logging import get_logger

logger = get_logger(__name__)

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
OPENAI_URL = "https://api.openai.com/v1/chat/completions"

DEFAULT_MODELS = {"anthropic": "claude-opus-5", "openai": "gpt-4o-mini"}

MAX_TOKENS = 1024

# Модель інколи загортає JSON у ```json ... ``` — витягуємо вміст блоку
_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)
# Останній рубіж: перший об'єкт у тексті
_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)


@dataclass(frozen=True, slots=True)
class LLMVerdict:
    score: int
    reasoning: str


class LLMClient(Protocol):
    """Контракт, від якого залежить сервіс скорингу."""

    provider: str

    def complete(self, *, system: str, prompt: str) -> str: ...


class AnthropicClient:
    provider = "anthropic"

    def __init__(self, *, api_key: str, model: str, timeout: int) -> None:
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    def complete(self, *, system: str, prompt: str) -> str:
        # temperature на актуальних моделях Claude прибрано — надішлеш, буде 400
        payload = {
            "model": self.model,
            "max_tokens": MAX_TOKENS,
            "system": system,
            "messages": [{"role": "user", "content": prompt}],
        }
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": ANTHROPIC_VERSION,
            "content-type": "application/json",
        }
        data = _post(ANTHROPIC_URL, payload, headers, self.timeout)

        try:
            blocks = data["content"]
            return "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
        except (KeyError, TypeError) as exc:
            raise ExternalServiceError(f"Anthropic віддав неочікувану структуру: {exc}") from exc


class OpenAIClient:
    provider = "openai"

    def __init__(self, *, api_key: str, model: str, timeout: int) -> None:
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    def complete(self, *, system: str, prompt: str) -> str:
        payload = {
            "model": self.model,
            "max_tokens": MAX_TOKENS,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        data = _post(OPENAI_URL, payload, headers, self.timeout)

        try:
            return data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as exc:
            raise ExternalServiceError(f"OpenAI віддав неочікувану структуру: {exc}") from exc


def _post(url: str, payload: dict, headers: dict, timeout: int) -> dict:
    """Один POST на обидва провайдери. Будь-яка мережева біда → ExternalServiceError,
    щоб сервіс скорингу мав рівно один тип винятку для фолбеку."""
    try:
        response = httpx.post(url, json=payload, headers=headers, timeout=timeout)
    except httpx.HTTPError as exc:
        raise ExternalServiceError(f"LLM недоступний: {exc}") from exc

    if response.status_code >= 400:
        # Тіло може містити підказку (ліміт, невірна модель), але не ключ
        raise ExternalServiceError(
            f"LLM відповів {response.status_code}: {response.text[:200]}"
        )

    try:
        return response.json()
    except ValueError as exc:
        raise ExternalServiceError(f"LLM віддав не-JSON: {exc}") from exc


def parse_verdict(raw: str) -> LLMVerdict:
    """Текст відповіді → score + reasoning.

    Модель майже завжди повертає валідний JSON, але «майже» тут недостатньо:
    навколо нього бувають ```-огорожа і пояснювальний текст. Не розібрали —
    кидаємо виняток, і скоринг чесно падає на формулу.
    """
    payload = _extract_json(raw)

    try:
        score = int(round(float(payload["score"])))
        reasoning = str(payload["reasoning"]).strip()
    except (KeyError, TypeError, ValueError) as exc:
        raise ExternalServiceError(f"У відповіді LLM немає score/reasoning: {exc}") from exc

    if not reasoning:
        raise ExternalServiceError("LLM повернув порожній reasoning")

    # Модель інколи пише 105 або -3. Обрізаємо, а не падаємо: сама оцінка змістовна.
    return LLMVerdict(score=max(0, min(100, score)), reasoning=reasoning)


def _extract_json(raw: str) -> dict:
    text = raw.strip()
    if (fenced := _FENCE_RE.search(text)) is not None:
        text = fenced.group(1).strip()

    candidates = [text]
    if (found := _OBJECT_RE.search(text)) is not None:
        candidates.append(found.group(0))

    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except ValueError:
            continue
        if isinstance(parsed, dict):
            return parsed

    raise ExternalServiceError(f"Відповідь LLM не є JSON: {raw[:200]!r}")


def build_client() -> LLMClient | None:
    """Клієнт за налаштуваннями .env, або None — якщо ключа немає.

    Це єдине місце, де вирішується «LLM чи fallback». Сервіс скорингу лише
    перевіряє результат на None.
    """
    if not settings.llm_enabled:
        logger.info(
            "LLM вимкнено (provider=%s, ключ %s) — скоринг піде на формулу",
            settings.llm_provider,
            "заданий" if settings.llm_api_key else "відсутній",
        )
        return None

    model = settings.llm_model or DEFAULT_MODELS[settings.llm_provider]
    kwargs = {
        "api_key": settings.llm_api_key,
        "model": model,
        "timeout": settings.llm_timeout_seconds,
    }

    logger.info("LLM увімкнено: provider=%s, model=%s", settings.llm_provider, model)
    if settings.llm_provider == "anthropic":
        return AnthropicClient(**kwargs)
    return OpenAIClient(**kwargs)
