"""Defined-term mining (pure functions over paragraph text)."""

import re
from dataclasses import dataclass

from docusense.extract.sentences import flatten

TERMINOLOGY_SECTION = re.compile(
    r"terminology|definitions?\b|conventions|glossary|notation|\bterms\b|\broles\b", re.I
)

_Q = r"[\"“](?P<term>[^\"”]{2,60})[\"”]"
_QUOTED_MEANS = re.compile(_Q + r"\s+(?:means|refers to|is defined as|denotes|is used to (?:mean|refer))\b")
_THE_TERM = re.compile(r"\b[Tt]he (?:term|phrase)\s+" + _Q)
_A_QUOTED_IS = re.compile(r"(?:^|[.;]\s+)(?:An?|The)\s+" + _Q + r"\s+is\s+(?:a|an|the|any)\b")
_COLON_DEF = re.compile(r"^(?P<term>[A-Za-z\"][\w\"\-/ ()']{1,50}?):\s+[A-Za-z(]")
_RFC2119_STYLE = re.compile(r"^\s*\d+\.\s+(?P<term>[A-Z][A-Z ]+?)\s{3,}\S")


@dataclass
class DefinitionMatch:
    term: str
    method: str


def normalize_term(term: str) -> str:
    term = term.strip(" \"'“”:").lower()
    return re.sub(r"\s+", " ", term)


def _ok_term(term: str, max_words: int = 6) -> bool:
    words = term.split()
    return 0 < len(words) <= max_words and not term.endswith(".") and any(c.isalpha() for c in term)


def find_definitions(text: str, in_terminology_section: bool) -> list[DefinitionMatch]:
    """Return defined terms in a paragraph. `text` is the raw span text (indentation preserved)."""
    flat = flatten(text)
    out: list[DefinitionMatch] = []

    def add(term: str, method: str) -> None:
        term = term.strip(" \"'")
        if _ok_term(term) and normalize_term(term) not in {normalize_term(d.term) for d in out}:
            out.append(DefinitionMatch(term, method))

    m = _RFC2119_STYLE.match(text)
    if m:
        add(m.group("term"), "regex:numbered-keyword")

    for pattern, method in ((_QUOTED_MEANS, "regex:quoted-means"), (_THE_TERM, "regex:the-term"),
                            (_A_QUOTED_IS, "regex:a-quoted-is")):
        for m in pattern.finditer(flat):
            add(m.group("term"), method)

    lines = [l for l in text.split("\n") if l.strip()]
    if in_terminology_section:
        m = _COLON_DEF.match(flat)
        if m and _ok_term(m.group("term"), 5):
            add(m.group("term"), "regex:colon")

    # Term on its own line, definition indented more deeply below (RFC 6749 'Roles' style).
    if len(lines) >= 2:
        first, rest = lines[0], lines[1:]
        indent = len(first) - len(first.lstrip())
        deeper = all(len(l) - len(l.lstrip()) > indent for l in rest)
        term = first.strip()
        if (deeper and _ok_term(term, 5) and re.fullmatch(r"[A-Za-z][A-Za-z \-\"']*", term)
                and rest[0].strip()[:1].isupper()):
            add(term, "layout:term-line")
    return out
