"""Heading detection and section-tree construction."""

import re
from dataclasses import dataclass

from docusense.ingest.model import Heading, ParsedDoc

UNNUMBERED_HEADINGS = {
    "abstract", "status of this memo", "copyright notice", "table of contents", "contents",
    "acknowledgments", "acknowledgements", "acknowledgment", "acknowledgement",
    "author's address", "authors' addresses", "authors addresses", "editor's address",
    "editors' addresses", "full copyright statement", "intellectual property", "index",
    "contributors", "references", "normative references", "informative references",
}

_TITLE = r"(?P<title>[A-Za-z0-9\"'(\[#<].*[A-Za-z].*)"
_NUMBERED = re.compile(r"^(?P<num>\d{1,2}(?:\.\d{1,3})*)\.?\s+" + _TITLE + "$")
_APPENDIX = re.compile(r"^Appendix\s+(?P<num>[A-Z](?:\.\d{1,3})*)[.:]?\s*(?P<title>.*)$", re.I)
_LETTERED = re.compile(r"^(?P<num>[A-Z](?:\.\d{1,3})+)\.?\s+" + _TITLE + "$")
_LETTER_TOP = re.compile(r"^(?P<num>[A-Z])\.\s+(?P<title>[A-Z].*)$")  # 'A. TCP Transport Service'
_DOT_LEADER = re.compile(r"(\.\s?){3,}\s*\d+\s*$")
_INLINE_BODY = re.compile(r"^(.*?\S)\s{3,}\S")  # 'MUST   This word, or the terms ...'


@dataclass
class HeadingMatch:
    number: str | None
    title: str
    level: int
    inline_body: bool = False  # body text continues on the heading line (RFC 2119 style)


def match_heading_text(text: str) -> HeadingMatch | None:
    """Pure text rule: does this line read like an RFC-style heading?"""
    t = text.strip()
    if not t or len(t) > 100 or _DOT_LEADER.search(t):
        return None
    if t.lower().rstrip(":") in UNNUMBERED_HEADINGS:
        return HeadingMatch(None, t.rstrip(":"), 1)
    for pattern in (_APPENDIX, _NUMBERED, _LETTERED, _LETTER_TOP):
        m = pattern.match(t)
        if m:
            num = m.group("num").upper() if pattern is _APPENDIX else m.group("num")
            title = m.group("title").strip() or t
            inline = _INLINE_BODY.match(title)
            if inline:
                return HeadingMatch(num, inline.group(1), num.count(".") + 1, inline_body=True)
            if title.endswith(".") and len(title.split()) > 8:
                return None  # a numbered sentence, not a heading
            return HeadingMatch(num, title, num.count(".") + 1)
    return None


def build_sections(doc: ParsedDoc) -> list[dict]:
    """Turn headings into a section tree. Returns dicts in document order.

    Each section covers [heading start, start of next heading at the same or higher level),
    trimmed of trailing whitespace. Content before the first heading is a level-0 front matter.
    """
    data = doc.data
    headings: list[Heading] = list(doc.headings)
    sections: list[dict] = []

    first = headings[0].start if headings else len(data)
    if data[:first].strip():
        sections.append(_section(None, "Front Matter", 0, 0, first, data, doc))

    for i, h in enumerate(headings):
        end = len(data)
        for nxt in headings[i + 1:]:
            if nxt.level <= h.level:
                end = nxt.start
                break
        sections.append(_section(h.number, h.title, h.level, h.start, end, data, doc))

    stack: list[dict] = []
    for ordinal, s in enumerate(sections):
        s["ordinal"] = ordinal
        while stack and stack[-1]["level"] >= s["level"]:
            stack.pop()
        s["parent_ordinal"] = stack[-1]["ordinal"] if stack else None
        if s["level"] > 0:  # front matter (level 0) is never a parent
            stack.append(s)
    return sections


def _section(number, title, level, start, end, data: bytes, doc: ParsedDoc) -> dict:
    while end > start and data[end - 1:end] in (b" ", b"\n"):
        end -= 1
    return {
        "number": number,
        "title": title,
        "level": level,
        "start_byte": start,
        "end_byte": end,
        "page_start": doc.page_of(start),
        "page_end": doc.page_of(max(start, end - 1)),
    }
