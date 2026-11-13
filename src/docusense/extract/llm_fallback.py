"""Bounded LLM fallback: only for requirement sentences whose subject the heuristics missed.

Off by default; the provider is configurable (docusense/llm.py). Every result records the model ID, a SHA-256 of the exact prompt, the method and
a confidence, so LLM-derived claims stay auditable and distinguishable from deterministic ones.
"""

from dataclasses import dataclass

from docusense.llm import LLM

MAX_CALLS_PER_VERSION = 20

_PROMPT = """You extract the grammatical subject of a normative requirement from a document.

Context paragraph:
<<<{context}>>>

Requirement sentence:
<<<{sentence}>>>

Who or what does the requirement apply to? Resolve pronouns like "it" or "they" using the context.
Answer with JSON only: {{"subject": "<short noun phrase>", "confidence": <0.0-1.0>}}"""

SUBJECT_SCHEMA = {
    "type": "object",
    "properties": {"subject": {"type": "string"}, "confidence": {"type": "number"}},
    "required": ["subject", "confidence"],
    "additionalProperties": False,
}


@dataclass
class FallbackResult:
    subject: str | None
    confidence: float
    model_id: str
    prompt_hash: str


class SubjectFallback:
    """Budgeted LLM access (the same object also serves as the contradiction judge)."""

    def __init__(self, max_calls: int = MAX_CALLS_PER_VERSION, llm: LLM | None = None):
        self.llm = llm or LLM()
        self.model = self.llm.model
        self.max_calls = max_calls
        self.calls = 0

    @property
    def available(self) -> bool:
        return self.llm.available and self.calls < self.max_calls

    def reset_budget(self) -> None:
        self.calls = 0

    def subject_for(self, sentence: str, context: str) -> FallbackResult | None:
        if not self.available:
            return None
        self.calls += 1
        result = self.llm.complete_json(_PROMPT.format(context=context[:2000], sentence=sentence), SUBJECT_SCHEMA)
        if result is None:
            return None
        subject = str(result.data.get("subject") or "").strip() or None
        return FallbackResult(subject, float(result.data.get("confidence") or 0.0), result.model_id, result.prompt_hash)
