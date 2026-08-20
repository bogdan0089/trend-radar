"""LLM provider adapters behind one interface, configured from .env."""

import json
import re
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import quote

import httpx

from app.core.config import settings
from app.core.exceptions import ExternalServiceError
from app.core.logging import get_logger

logger = get_logger(__name__)

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
OPENAI_URL = "https://api.openai.com/v1/chat/completions"
GROK_URL = "https://api.x.ai/v1/chat/completions"
GEMINI_URL_TEMPLATE = (
    "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
)

DEFAULT_MODELS = {
    "anthropic": "claude-sonnet-5",
    "openai": "gpt-4o-mini",
    "gemini": "gemini-2.5-flash",
    "grok": "grok-4",
}

MAX_TOKENS = 1024

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)
_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)


@dataclass(frozen=True, slots=True)
class LLMVerdict:
    score: int
    reasoning: str


class LLMClient(Protocol):
    """The contract the scoring service depends on."""

    provider: str

    def complete(self, *, system: str, prompt: str) -> str: ...


class AnthropicClient:
    provider = "anthropic"

    def __init__(self, *, api_key: str, model: str, timeout: int) -> None:
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    def complete(self, *, system: str, prompt: str) -> str:
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
            raise ExternalServiceError(
                f"Anthropic returned an unexpected structure: {exc}"
            ) from exc


class OpenAICompatibleClient:
    """Chat-completions protocol, shared by OpenAI and xAI Grok."""

    def __init__(self, *, api_key: str, model: str, timeout: int, url: str, provider: str) -> None:
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.url = url
        self.provider = provider

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
        data = _post(self.url, payload, headers, self.timeout)

        try:
            return data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as exc:
            raise ExternalServiceError(
                f"{self.provider} returned an unexpected structure: {exc}"
            ) from exc


class GeminiClient:
    """Google Gemini generateContent, which keys by query parameter."""

    provider = "gemini"

    def __init__(self, *, api_key: str, model: str, timeout: int) -> None:
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    def complete(self, *, system: str, prompt: str) -> str:
        payload = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"maxOutputTokens": MAX_TOKENS},
        }
        url = GEMINI_URL_TEMPLATE.format(model=quote(self.model))
        data = _post(
            f"{url}?key={quote(self.api_key)}",
            payload,
            {"Content-Type": "application/json"},
            self.timeout,
        )

        try:
            parts = data["candidates"][0]["content"]["parts"]
            return "".join(part.get("text", "") for part in parts)
        except (KeyError, IndexError, TypeError) as exc:
            raise ExternalServiceError(f"Gemini returned an unexpected structure: {exc}") from exc


def _post(url: str, payload: dict, headers: dict, timeout: int) -> dict:
    """POST shared by every provider; any failure becomes ExternalServiceError."""
    try:
        response = httpx.post(url, json=payload, headers=headers, timeout=timeout)
    except httpx.HTTPError as exc:
        raise ExternalServiceError(f"LLM unreachable: {exc}") from exc

    if response.status_code >= 400:
        raise ExternalServiceError(
            f"LLM responded {response.status_code}: {response.text[:200]}"
        )

    try:
        return response.json()
    except ValueError as exc:
        raise ExternalServiceError(f"LLM returned non-JSON: {exc}") from exc


def parse_verdict(raw: str) -> LLMVerdict:
    """Turn a model reply into score + reasoning, tolerating fences and prose."""
    payload = _extract_json(raw)

    try:
        score = int(round(float(payload["score"])))
        reasoning = str(payload["reasoning"]).strip()
    except (KeyError, TypeError, ValueError) as exc:
        raise ExternalServiceError(f"LLM reply has no score/reasoning: {exc}") from exc

    if not reasoning:
        raise ExternalServiceError("LLM returned an empty reasoning")

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

    raise ExternalServiceError(f"LLM reply is not JSON: {raw[:200]!r}")


def build_client() -> LLMClient | None:
    if not settings.llm_enabled:
        logger.info(
            "LLM disabled (provider=%s, key %s), scoring will use the formula",
            settings.llm_provider,
            "set" if settings.llm_api_key else "missing",
        )
        return None

    provider = settings.llm_provider
    model = settings.llm_model or DEFAULT_MODELS[provider]
    logger.info("LLM enabled: provider=%s, model=%s", provider, model)

    if provider == "anthropic":
        return AnthropicClient(
            api_key=settings.llm_api_key, model=model, timeout=settings.llm_timeout_seconds
        )
    if provider == "gemini":
        return GeminiClient(
            api_key=settings.llm_api_key, model=model, timeout=settings.llm_timeout_seconds
        )

    return OpenAICompatibleClient(
        api_key=settings.llm_api_key,
        model=model,
        timeout=settings.llm_timeout_seconds,
        url=GROK_URL if provider == "grok" else OPENAI_URL,
        provider=provider,
    )
