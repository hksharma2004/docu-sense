"""LLM provider selection and request shapes, with fake transports (no network, no spend)."""

import json
from types import SimpleNamespace

import httpx
import pytest

from docusense import config
from docusense.extract.llm_fallback import SubjectFallback
from docusense.llm import LLM

SCHEMA = {"type": "object", "properties": {"subject": {"type": "string"}}, "required": ["subject"],
          "additionalProperties": False}


@pytest.fixture
def env(monkeypatch):
    # Blank the plain names (overrides any .env), remove the prefixed aliases (they would shadow them).
    for key in ("GROQ_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "DOCUSENSE_LLM_PROVIDER",
                "DOCUSENSE_LLM_MODEL", "DOCUSENSE_LLM_BASE_URL"):
        monkeypatch.setenv(key, "")
    for key in ("DOCUSENSE_GROQ_API_KEY", "DOCUSENSE_ANTHROPIC_API_KEY", "DOCUSENSE_OPENAI_API_KEY"):
        monkeypatch.delenv(key, raising=False)

    def set_env(**values):
        for k, v in values.items():
            monkeypatch.setenv(k, v)
        config.get_settings.cache_clear()

    set_env()
    yield set_env
    config.get_settings.cache_clear()


def test_auto_selection(env):
    assert LLM().provider == "none" and not LLM().available
    env(ANTHROPIC_API_KEY="sk-test")
    llm = LLM()
    assert (llm.provider, llm.model, llm.available) == ("anthropic", "claude-opus-5-5", True)
    env(GROQ_API_KEY="gsk-test")
    assert LLM().provider == "groq"  # groq first: the historical default


def test_openai_compatible_request(env):
    env(DOCUSENSE_LLM_PROVIDER="ollama", DOCUSENSE_LLM_MODEL="llama3.1")
    llm = LLM()
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"], seen["body"] = str(request.url), json.loads(request.content)
        return httpx.Response(200, json={"model": "llama3.1", "choices": [{"message": {"content": '{"subject": "clients"}'}}]})

    llm._http = httpx.Client(transport=httpx.MockTransport(handler))
    result = llm.complete_json("who?", SCHEMA)
    assert seen["url"] == "http://localhost:11434/v1/chat/completions"
    assert seen["body"]["response_format"] == {"type": "json_object"} and seen["body"]["model"] == "llama3.1"
    assert result.data == {"subject": "clients"} and result.model_id == "llama3.1" and len(result.prompt_hash) == 64


def test_openai_requires_model(env):
    env(OPENAI_API_KEY="sk-test")
    llm = LLM()
    assert llm.provider == "openai" and not llm.available and "DOCUSENSE_LLM_MODEL" in llm.error


class _FakeAnthropic:
    def __init__(self, response):
        self.kwargs = None
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))
        self._response = response

    def _create(self, **kwargs):
        self.kwargs = kwargs
        return self._response


def test_anthropic_request_shape_and_refusal(env):
    env(ANTHROPIC_API_KEY="sk-test")
    llm = LLM()
    ok = SimpleNamespace(stop_reason="end_turn", model="claude-opus-5-5",
                         content=[SimpleNamespace(type="thinking"), SimpleNamespace(type="text", text='{"subject": "servers"}')])
    fake = llm._anthropic = _FakeAnthropic(ok)
    result = llm.complete_json("who?", SCHEMA)
    assert result.data == {"subject": "servers"} and result.model_id == "claude-opus-5-5"
    assert fake.kwargs["output_config"] == {"effort": "low", "format": {"type": "json_schema", "schema": SCHEMA}}
    assert fake.kwargs["fallbacks"] == "default" and fake.kwargs["betas"] == ["server-side-fallback-2026-07-01"]

    llm._anthropic = _FakeAnthropic(SimpleNamespace(stop_reason="refusal", model="claude-opus-5-5", content=[]))
    assert llm.complete_json("who?", SCHEMA) is None


def test_subject_fallback_budget(env):
    env(ANTHROPIC_API_KEY="sk-test")
    fb = SubjectFallback(max_calls=1)
    fb.llm._anthropic = _FakeAnthropic(SimpleNamespace(
        stop_reason="end_turn", model="claude-opus-5-5",
        content=[SimpleNamespace(type="text", text='{"subject": "the client", "confidence": 0.9}')]))
    r = fb.subject_for("It MUST retry.", "The client sends a request. It MUST retry.")
    assert (r.subject, r.confidence, r.model_id) == ("the client", 0.9, "claude-opus-5-5")
    assert not fb.available and fb.subject_for("x", "y") is None
