"""cross-reference detection (pure). resolution against the corpus lives in extract/run.py"""

import re
from dataclasses import dataclass

from docusense.extract.sentences import flatten

_SEC = r"(?:\d+(?:\.\d+)*|[A-Z](?:\.\d+)*)(?![\w])"
_SEC_WORD = r"(?:[Ss]ection|[Ss]ec\.|Appendix)"

# order matters: specific patterns claim their text first
_SECTION_OF_DOC = re.compile(
    rf"\b{_SEC_WORD}\s+(?P<sec>{_SEC})\s+of\s+(?:\[(?P<tag>[^\]\s]+)\]|RFC\s?(?P<rfc>\d+))"
)
_DOC_COMMA_SECTION = re.compile(
    rf"(?:\[(?P<tag>[^\]\s]+)\]|\bRFC\s?(?P<rfc>\d+)),?\s+{_SEC_WORD}\s+(?P<sec>{_SEC})"
)
_INTERNAL = re.compile(
    rf"\b(?P<kw>[Ss]ections?|Appendix|Appendices)\s+(?P<list>{_SEC}"
    rf"(?:(?:\s*,\s*(?:and\s+|or\s+)?|\s+and\s+|\s+or\s+|\s+through\s+){_SEC})*)"
)
_BRACKET = re.compile(r"\[(?P<tag>[A-Za-z][\w.\-+:/]*|\d{1,3})\]")
_PLAIN_RFC = re.compile(r"\bRFCs?\s?(?P<rfc>\d{2,4})\b")
_RELATION = re.compile(r"\b(?P<rel>Obsoletes|Updates):\s*(?P<nums>\d+(?:\s*,\s*\d+)*)", re.I)
_ENTRY_TAG = re.compile(r"^\s*\[(?P<tag>[^\]\s]+)\]")
_ENTRY_RFC = re.compile(r"\bRFC\s?0*(?P<rfc>\d{1,4})\b")


@dataclass
class RefMatch:
    raw: str
    relation: str  # section | cites | obsoletes | updates
    tag: str | None = None
    rfc: str | None = None
    section: str | None = None  # target section number (none = whole doc)

    @property
    def internal(self) -> bool:
        return self.tag is None and self.rfc is None


def parse_reference_entry(text: str) -> tuple[str | None, str | None]:
    """'[RFC5322] Resnick, P., "Internet Message Format", RFC 5322, ...' -> ('RFC5322', '5322')."""
    flat = flatten(text)
    tag_match = _ENTRY_TAG.match(flat)
    tag = tag_match.group("tag") if tag_match else None
    rfc_match = _ENTRY_RFC.search(flat[tag_match.end():] if tag_match else flat)
    rfc = rfc_match.group("rfc") if rfc_match else None
    if rfc is None and tag and re.fullmatch(r"RFC0*\d+", tag, re.I):
        rfc = tag[3:].lstrip("0")
    return tag, rfc


def build_tag_map(entries: list[str]) -> dict[str, str | None]:
    """map citation tags to rfc numbers. untagged entries extend the previous tag (bcp groups)"""
    tags: dict[str, str | None] = {}
    current = None
    for text in entries:
        tag, rfc = parse_reference_entry(text)
        if tag:
            current = tag
            tags[tag] = rfc
        elif current and rfc and tags.get(current) is None:
            tags[current] = rfc
    return tags


def detect_relations(text: str) -> list[RefMatch]:
    out = []
    for m in _RELATION.finditer(flatten(text)):
        for num in re.findall(r"\d+", m.group("nums")):
            out.append(RefMatch(m.group(0), m.group("rel").lower(), rfc=num.lstrip("0")))
    return out


def detect_references(text: str, tag_map: dict[str, str | None]) -> list[RefMatch]:
    flat = flatten(text)
    taken: list[tuple[int, int]] = []
    found: list[tuple[int, RefMatch]] = []

    def free(m: re.Match) -> bool:
        return all(m.end() <= a or m.start() >= b for a, b in taken)

    def claim(m: re.Match, ref: RefMatch) -> None:
        taken.append((m.start(), m.end()))
        found.append((m.start(), ref))

    def rfc_for(tag: str | None, rfc: str | None) -> str | None:
        if rfc:
            return rfc.lstrip("0")
        if tag and tag_map.get(tag):
            return tag_map[tag]
        m = re.fullmatch(r"RFC0*(\d+)", tag or "", re.I)
        return m.group(1) if m else None

    for pattern in (_SECTION_OF_DOC, _DOC_COMMA_SECTION):
        for m in pattern.finditer(flat):
            if free(m):
                tag = m.group("tag")
                claim(m, RefMatch(m.group(0), "section", tag, rfc_for(tag, m.group("rfc")), m.group("sec")))

    for m in _INTERNAL.finditer(flat):
        if not free(m):
            continue
        numbers = re.findall(_SEC, m.group("list"))
        taken.append((m.start(), m.end()))
        for num in numbers:
            found.append((m.start(), RefMatch(m.group(0), "section", section=num)))

    for m in _BRACKET.finditer(flat):
        tag = m.group("tag")
        if free(m) and (tag in tag_map or re.fullmatch(r"RFC\d+", tag)):
            claim(m, RefMatch(m.group(0), "cites", tag, rfc_for(tag, None)))

    for m in _PLAIN_RFC.finditer(flat):
        if free(m):
            claim(m, RefMatch(m.group(0), "cites", rfc=m.group("rfc").lstrip("0")))

    found.sort(key=lambda pair: pair[0])
    seen, out = set(), []
    for _, ref in found:
        key = (ref.relation, ref.tag, ref.rfc, ref.section)
        if key not in seen:
            seen.add(key)
            out.append(ref)
    return out
