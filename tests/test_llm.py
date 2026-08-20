"""Tests for LLM response handling and provider selection."""

import json

import pytest

from app.core.exceptions import ExternalServiceError
from app.integrations import llm as llm_module
from app.integrations.llm import (
    DEFAULT_MODELS,
    GROK_URL,
    OPENAI_URL,
    AnthropicClient,
    GeminiClient,
    OpenAICompatibleClient,
    build_client,
    parse_verdict,
)


class TestValidResponses:
    def test_plain_json(self):
        verdict = parse_verdict('{"score": 78, "reasoning": "Demand is rising"}')
        assert verdict.score == 78
        assert verdict.reasoning == "Demand is rising"

    def test_json_in_markdown_fence(self):
        raw = '```json\n{"score": 55, "reasoning": "Average potential"}\n```'
        assert parse_verdict(raw).score == 55

    def test_json_surrounded_by_text(self):
        raw = 'Here is my rating:\n{"score": 90, "reasoning": "Strong trend"}\nHope it helps.'
        assert parse_verdict(raw).score == 90

    def test_float_score_is_rounded(self):
        assert parse_verdict('{"score": 72.6, "reasoning": "ok"}').score == 73

    def test_score_as_string(self):
        assert parse_verdict('{"score": "64", "reasoning": "ok"}').score == 64

    def test_object_wrapped_in_array(self):
        """Recovering the first object is cheaper than falling back needlessly."""
        assert parse_verdict('[{"score": 50, "reasoning": "ok"}]').score == 50


class TestClamping:
    """An out-of-range score is clamped: only the format was wrong."""

    def test_above_100(self):
        assert parse_verdict('{"score": 150, "reasoning": "ok"}').score == 100

    def test_below_zero(self):
        assert parse_verdict('{"score": -20, "reasoning": "ok"}').score == 0


class TestBrokenResponses:
    """Anything unparseable raises, and scoring falls back to the formula."""

    def test_not_json_at_all(self):
        with pytest.raises(ExternalServiceError, match="not JSON"):
            parse_verdict("Sorry, I cannot rate this product.")

    def test_missing_score(self):
        with pytest.raises(ExternalServiceError, match="no score"):
            parse_verdict('{"reasoning": "something"}')

    def test_missing_reasoning(self):
        with pytest.raises(ExternalServiceError, match="no score"):
            parse_verdict('{"score": 50}')

    def test_empty_reasoning(self):
        with pytest.raises(ExternalServiceError, match="empty reasoning"):
            parse_verdict('{"score": 50, "reasoning": "   "}')

    def test_score_is_not_a_number(self):
        with pytest.raises(ExternalServiceError, match="no score"):
            parse_verdict('{"score": "high", "reasoning": "ok"}')

    def test_empty_response(self):
        with pytest.raises(ExternalServiceError):
            parse_verdict("")


@pytest.fixture
def captured_post(monkeypatch):
    """Replace the shared _post with a recorder returning a canned payload."""
    calls: dict = {}

    def fake_post(url, payload, headers, timeout):
        calls.update(url=url, payload=payload, headers=headers, timeout=timeout)
        return calls["response"]

    monkeypatch.setattr(llm_module, "_post", fake_post)
    return calls


class TestProviderResponseShapes:
    """Each vendor nests the answer differently; that is what these lock down."""

    def test_anthropic_joins_text_blocks(self, captured_post):
        captured_post["response"] = {
            "content": [
                {"type": "text", "text": '{"score": 70,'},
                {"type": "thinking", "text": "ignored"},
                {"type": "text", "text": ' "reasoning": "ok"}'},
            ]
        }
        client = AnthropicClient(api_key="k", model="m", timeout=5)

        assert parse_verdict(client.complete(system="s", prompt="p")).score == 70

    def test_openai_reads_first_choice(self, captured_post):
        captured_post["response"] = {
            "choices": [{"message": {"content": '{"score": 42, "reasoning": "ok"}'}}]
        }
        client = OpenAICompatibleClient(
            api_key="k", model="m", timeout=5, url=OPENAI_URL, provider="openai"
        )

        assert parse_verdict(client.complete(system="s", prompt="p")).score == 42

    def test_gemini_joins_parts_and_passes_key_in_query(self, captured_post):
        captured_post["response"] = {
            "candidates": [{"content": {"parts": [{"text": '{"score": 61, "reasoning": "ok"}'}]}}]
        }
        client = GeminiClient(api_key="secret-key", model="gemini-3.6-flash", timeout=5)

        assert parse_verdict(client.complete(system="s", prompt="p")).score == 61
        assert "key=secret-key" in captured_post["url"]
        assert captured_post["payload"]["systemInstruction"]["parts"][0]["text"] == "s"

    def test_unexpected_structure_raises(self, captured_post):
        captured_post["response"] = {"unexpected": True}
        client = GeminiClient(api_key="k", model="m", timeout=5)

        with pytest.raises(ExternalServiceError, match="Gemini"):
            client.complete(system="s", prompt="p")


class TestBuildClient:
    """Provider selection, including the no-key path required by the spec."""

    @staticmethod
    def _configure(monkeypatch, **values):
        for name, value in values.items():
            monkeypatch.setattr(llm_module.settings, name, value)

    def test_none_provider_disables_llm(self, monkeypatch):
        self._configure(monkeypatch, llm_provider="none", llm_api_key="")
        assert build_client() is None

    def test_missing_key_disables_llm(self, monkeypatch):
        """The spec requires the project to start with a provider set but no key."""
        self._configure(monkeypatch, llm_provider="gemini", llm_api_key="   ")
        assert build_client() is None

    @pytest.mark.parametrize(
        ("provider", "expected_type"),
        [
            ("anthropic", AnthropicClient),
            ("gemini", GeminiClient),
            ("openai", OpenAICompatibleClient),
            ("grok", OpenAICompatibleClient),
        ],
    )
    def test_provider_selects_client(self, monkeypatch, provider, expected_type):
        self._configure(monkeypatch, llm_provider=provider, llm_api_key="k", llm_model="")
        client = build_client()

        assert isinstance(client, expected_type)
        assert client.provider == provider
        assert client.model == DEFAULT_MODELS[provider]

    def test_grok_and_openai_use_different_endpoints(self, monkeypatch):
        self._configure(monkeypatch, llm_provider="grok", llm_api_key="k", llm_model="")
        assert build_client().url == GROK_URL

        self._configure(monkeypatch, llm_provider="openai", llm_api_key="k", llm_model="")
        assert build_client().url == OPENAI_URL

    def test_explicit_model_overrides_the_default(self, monkeypatch):
        self._configure(
            monkeypatch, llm_provider="grok", llm_api_key="k", llm_model="grok-4-fast"
        )
        assert build_client().model == "grok-4-fast"


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict | None = None, headers: dict | None = None):
        self.status_code = status_code
        self.headers = headers or {}
        self._payload = payload if payload is not None else {"error": "boom"}
        self.text = json.dumps(self._payload)

    def json(self) -> dict:
        return self._payload


@pytest.fixture
def http_calls(monkeypatch):
    """Drive _post directly: queue responses, record posts, never really sleep."""
    state: dict = {"queue": [], "posts": 0, "slept": []}

    def fake_post(url, **kwargs):
        state["posts"] += 1
        return state["queue"].pop(0)

    monkeypatch.setattr(llm_module.httpx, "post", fake_post)
    monkeypatch.setattr(llm_module.time, "sleep", lambda s: state["slept"].append(s))
    return state


class TestRetryOnRateLimit:
    """Free provider tiers 429 on long batches; one retry keeps the run on the LLM."""

    def test_429_then_success(self, http_calls):
        http_calls["queue"] = [
            _FakeResponse(429),
            _FakeResponse(200, {"ok": True}),
        ]

        assert llm_module._post("u", {}, {}, 5) == {"ok": True}
        assert http_calls["posts"] == 2
        assert http_calls["slept"] == [llm_module.BACKOFF_SECONDS[0]]

    def test_gives_up_after_max_attempts(self, http_calls):
        http_calls["queue"] = [_FakeResponse(429) for _ in range(llm_module.MAX_ATTEMPTS)]

        with pytest.raises(ExternalServiceError, match="429"):
            llm_module._post("u", {}, {}, 5)

        assert http_calls["posts"] == llm_module.MAX_ATTEMPTS

    def test_a_bad_key_is_not_retried(self, http_calls):
        """401 will never pass, so retrying only delays the fallback."""
        http_calls["queue"] = [_FakeResponse(401)]

        with pytest.raises(ExternalServiceError, match="401"):
            llm_module._post("u", {}, {}, 5)

        assert http_calls["posts"] == 1
        assert http_calls["slept"] == []

    def test_unknown_model_is_not_retried(self, http_calls):
        http_calls["queue"] = [_FakeResponse(404)]

        with pytest.raises(ExternalServiceError, match="404"):
            llm_module._post("u", {}, {}, 5)

        assert http_calls["posts"] == 1

    def test_retry_after_header_wins_over_the_backoff(self, http_calls):
        http_calls["queue"] = [
            _FakeResponse(429, headers={"Retry-After": "4"}),
            _FakeResponse(200, {"ok": True}),
        ]

        llm_module._post("u", {}, {}, 5)
        assert http_calls["slept"] == [4.0]

    def test_retry_after_is_capped(self, http_calls):
        """A provider asking for ten minutes must not stall the whole pipeline."""
        http_calls["queue"] = [
            _FakeResponse(429, headers={"Retry-After": "600"}),
            _FakeResponse(200, {"ok": True}),
        ]

        llm_module._post("u", {}, {}, 5)
        assert http_calls["slept"] == [llm_module.MAX_RETRY_DELAY]

    def test_server_errors_are_retried_too(self, http_calls):
        http_calls["queue"] = [_FakeResponse(503), _FakeResponse(200, {"ok": True})]

        assert llm_module._post("u", {}, {}, 5) == {"ok": True}
        assert http_calls["posts"] == 2
