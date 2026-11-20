"""pluggable llm provider for the bounded fallbacks (claim subjects, contradiction judging).

never on the critical path, everything works without one. each call returns the model that
answered plus a sha-256 of the exact prompt, so llm-derived data stays auditable.

providers (DOCUSENSE_LLM_PROVIDER, default "auto" = first with a key: groq -> anthropic -> openai):
  groq               openai-compatible, GROQ_API_KEY, model DOCUSENSE_EXTRACT_MODEL (default openai/gpt-oss-120b)
  anthropic          official sdk (`pip install 'docusense-mcp[anthropic]'`), ANTHROPIC_API_KEY,
                     model DOCUSENSE_LLM_MODEL (default claude-opus-5-5)
  openai             OPENAI_API_KEY, model DOCUSENSE_LLM_MODEL (required)
  ollama             local, DOCUSENSE_LLM_BASE_URL (default http://localhost:11434/v1), model required
  openai-compatible  any /chat/completions endpoint: DOCUSENSE_LLM_BASE_URL, DOCUSENSE_LLM_API_KEY, model required
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any

import httpx

from docusense.config import get_settings
from docusense.store.blobs import sha256_hex

OPENAI_COMPATIBLE = {
    "groq": "https://api.groq.com/openai/v1",
    "openai": "https://api.openai.com/v1",
    "ollama": "http://localhost:11434/v1",
}
ANTHROPIC_DEFAULT_MODEL = "claude-opus-5-5"


@dataclass
class LLMResult:
    data: dict
    model_id: str
    prompt_hash: str


class LLM:
    """`complete_json(prompt, schema)` -> parsed json, or None on any failure (never raises)"""

    def __init__(self, provider: str | None = None, model: str | None = None):
        s = get_settings()
        self.provider = (provider or s.llm_provider or "auto").strip().lower()
        if self.provider == "auto":
            self.provider = ("groq" if s.groq_api_key else "anthropic" if s.anthropic_api_key
                             else "openai" if s.openai_api_key else "none")
        self.model = model or s.llm_model or self._default_model()
        self.error: str | None = None
        self._http: httpx.Client | None = None
        self._anthropic = None

        if self.provider == "none":
            self.error = "no LLM configured (set GROQ_API_KEY, ANTHROPIC_API_KEY or OPENAI_API_KEY)"
        elif self.provider == "anthropic":
            try:
                import anthropic
            except ImportError:
                self.error = "the anthropic provider needs: pip install 'docusense-mcp[anthropic]'"
            else:
                self._anthropic = anthropic.Anthropic(api_key=s.anthropic_api_key or None)
        elif self.provider in OPENAI_COMPATIBLE or self.provider == "openai-compatible":
            self.base_url = (s.llm_base_url or OPENAI_COMPATIBLE.get(self.provider, "")).rstrip("/")
            self.api_key = {"groq": s.groq_api_key, "openai": s.openai_api_key}.get(self.provider) or s.llm_api_key
            if not self.base_url:
                self.error = "openai-compatible provider needs DOCUSENSE_LLM_BASE_URL"
            elif not self.model:
                self.error = f"provider {self.provider!r} needs DOCUSENSE_LLM_MODEL"
            elif self.provider in ("groq", "openai") and not self.api_key:
                self.error = f"provider {self.provider!r} needs an API key"
            else:
                self._http = httpx.Client(timeout=60)
        else:
            self.error = f"unknown LLM provider {self.provider!r}"

    def _default_model(self) -> str:
        if self.provider == "groq":
            return get_settings().extract_model
        if self.provider == "anthropic":
            return ANTHROPIC_DEFAULT_MODEL
        return ""

    @property
    def available(self) -> bool:
        return self.error is None

    def complete_json(self, prompt: str, schema: dict[str, Any]) -> LLMResult | None:
        if not self.available:
            return None
        prompt_hash = sha256_hex(prompt.encode())
        try:
            if self._anthropic is not None:
                data, model_id = self._call_anthropic(prompt, schema)
            else:
                data, model_id = self._call_openai_compatible(prompt)
        except Exception as e:  # network, auth, refusal, bad json: the fallback just doesn't apply
            self.last_error = f"{type(e).__name__}: {e}"
            return None
        if not isinstance(data, dict):
            return None
        return LLMResult(data, model_id, prompt_hash)

    def _call_anthropic(self, prompt: str, schema: dict) -> tuple[dict, str]:
        response = self._anthropic.beta.messages.create(
            model=self.model,
            max_tokens=16000,
            # short extraction task: low effort. structured outputs guarantee valid json
            output_config={"effort": "low", "format": {"type": "json_schema", "schema": schema}},
            # on a safety decline, retry on anthropic's fallback model server-side
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            messages=[{"role": "user", "content": prompt}],
        )
        if response.stop_reason == "refusal":
            raise RuntimeError("model declined the request")
        text = next(b.text for b in response.content if b.type == "text")
        return json.loads(text), response.model

    def _call_openai_compatible(self, prompt: str) -> tuple[dict, str]:
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        body = {"model": self.model, "temperature": 0, "response_format": {"type": "json_object"},
                "messages": [{"role": "user", "content": prompt}]}
        for attempt in range(5):
            resp = self._http.post(f"{self.base_url}/chat/completions", headers=headers, json=body)
            if resp.status_code != 429:
                break
            time.sleep(min(float(resp.headers.get("retry-after", 2 ** attempt)), 30))  # free-tier rate limits
        resp.raise_for_status()
        payload = resp.json()
        return json.loads(payload["choices"][0]["message"]["content"]), payload.get("model") or self.model
