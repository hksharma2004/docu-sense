"""Bounded LLM fallback: only for requirement sentences whose subject the heuristics missed.

Off by default. Every result records the model ID, a SHA-256 of the exact prompt, the method and
a confidence, so LLM-derived claims stay auditable and distinguishable from deterministic ones.
"""

import json
import time
from dataclasses import dataclass

import httpx

from docusense.config import get_settings
from docusense.store.blobs import sha256_hex

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
MAX_CALLS_PER_VERSION = 20

_PROMPT = """You extract the grammatical subject of a normative requirement from a technical standard.

Context paragraph:
<<<{context}>>>

Requirement sentence:
<<<{sentence}>>>

Who or what does the requirement apply to? Resolve pronouns like "it" or "they" using the context.
Answer with JSON only: {{"subject": "<short noun phrase>", "confidence": <0.0-1.0>}}"""


@dataclass
class FallbackResult:
    subject: str | None
    confidence: float
    model_id: str
    prompt_hash: str


class SubjectFallback:
    def __init__(self, max_calls: int = MAX_CALLS_PER_VERSION):
        settings = get_settings()
        self.api_key = settings.groq_api_key
        self.model = settings.extract_model
        self.max_calls = max_calls
        self.calls = 0
        self._client = httpx.Client(timeout=30)

    @property
    def available(self) -> bool:
        return bool(self.api_key) and self.calls < self.max_calls

    def reset_budget(self) -> None:
        self.calls = 0

    def subject_for(self, sentence: str, context: str) -> FallbackResult | None:
        if not self.available:
            return None
        prompt = _PROMPT.format(context=context[:2000], sentence=sentence)
        self.calls += 1
        try:
            for attempt in range(4):
                resp = self._client.post(
                    GROQ_URL,
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json={
                        "model": self.model,
                        "temperature": 0,
                        "response_format": {"type": "json_object"},
                        "messages": [{"role": "user", "content": prompt}],
                    },
                )
                if resp.status_code != 429:
                    break
                time.sleep(float(resp.headers.get("retry-after", 2 ** attempt)))  # free-tier rate limit
            resp.raise_for_status()
            data = json.loads(resp.json()["choices"][0]["message"]["content"])
        except (httpx.HTTPError, KeyError, ValueError):
            return None
        subject = str(data.get("subject") or "").strip() or None
        return FallbackResult(subject, float(data.get("confidence") or 0.0), self.model, sha256_hex(prompt.encode()))
