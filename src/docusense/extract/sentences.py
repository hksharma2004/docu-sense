"""Deterministic sentence splitting with exact byte offsets."""

import re
from dataclasses import dataclass

_BOUNDARY = re.compile(r"(?<=[.!?])[\"')\]]?\s+(?=[\"'(\[]?[A-Z0-9<])")
_ABBREVIATIONS = (
    "e.g.", "i.e.", "etc.", "cf.", "vs.", "Ed.", "al.", "Sec.", "No.", "Fig.", "Vol.", "pp.",
    "Mr.", "Ms.", "Dr.", "Inc.", "Ltd.", "approx.", "Eds.",
)
_INITIAL = re.compile(r"(?:^|\s)[A-Z]\.$")  # 'J. Klensin'


@dataclass
class Sentence:
    start: int  # absolute byte offset
    end: int
    text: str


def _byte_len(s: str) -> int:
    return len(s.encode("utf-8"))


def split_sentences(text: str, base: int = 0) -> list[Sentence]:
    """Split `text` (which starts at byte `base` of the canonical text) into sentences.

    Leading/trailing whitespace is excluded from each sentence's byte range.
    """
    cuts = [0]
    for m in _BOUNDARY.finditer(text):
        before = text[:m.start()].rstrip("\"')]")
        tail = before[-10:]
        if any(tail.endswith(a) for a in _ABBREVIATIONS) or _INITIAL.search(tail):
            continue
        cuts.append(m.end())
    cuts.append(len(text))

    sentences = []
    for a, b in zip(cuts, cuts[1:]):
        chunk = text[a:b]
        lead = len(chunk) - len(chunk.lstrip())
        stripped = chunk.strip()
        if not stripped:
            continue
        start = base + _byte_len(text[:a + lead])
        sentences.append(Sentence(start, start + _byte_len(stripped), stripped))
    return sentences


def flatten(text: str) -> str:
    """Collapse line breaks and indentation, for matching only (never for stored evidence)."""
    return " ".join(text.split())
