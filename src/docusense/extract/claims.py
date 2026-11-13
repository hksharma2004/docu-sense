"""Pattern-based claim extraction: requirements, numeric facts and exclusions.

Two styles, chosen per document version (see `detect_style`):
- "bcp14": specs that use RFC 2119 / BCP 14 keywords. Only UPPERCASE MUST/SHALL/… are normative, as the
  convention says; lowercase "must" is ordinary prose.
- "prose": policies, contracts, handbooks. Lowercase modals and common legal/HR phrasings
  ("is required to", "may not", "are prohibited from", "is entitled to") are normative.

Pure functions over sentence text. Database writes live in extract/run.py.
"""

import re
from dataclasses import dataclass, field

from docusense.extract.sentences import flatten

# Longest alternatives first so 'MUST NOT' wins over 'MUST'.
_KEYWORD = re.compile(
    r"(?<![\"'\w])(MUST NOT|SHALL NOT|SHOULD NOT|NOT RECOMMENDED|MUST|SHALL|SHOULD|REQUIRED|"
    r"RECOMMENDED|MAY|OPTIONAL)(?![\"'\w])"
)
_CANONICAL_MODALITY = {
    "SHALL": "MUST", "REQUIRED": "MUST", "SHALL NOT": "MUST NOT",
    "RECOMMENDED": "SHOULD", "NOT RECOMMENDED": "SHOULD NOT", "OPTIONAL": "MAY",
}
# Prose modals, longest/most specific first. Each maps to a canonical BCP 14 modality.
_PROSE_MODALS: list[tuple[str, str]] = [
    (r"(?:is|are) (?:strictly )?(?:prohibited|forbidden|barred) from", "MUST NOT"),
    (r"(?:is|are) not (?:permitted|allowed|authori[sz]ed) to", "MUST NOT"),
    (r"(?:must|shall|may) not|mustn't|shan't|under no circumstances (?:may|shall|will|can)", "MUST NOT"),
    (r"should not|shouldn't|(?:is|are) discouraged from", "SHOULD NOT"),
    (r"(?:is|are) (?:required|obliged|obligated) to|(?:is|are) mandatory|must|shall", "MUST"),
    (r"(?:is|are) (?:expected|encouraged|advised) to|should|(?:is|are) recommended", "SHOULD"),
    (r"(?:is|are) (?:entitled|eligible|permitted|allowed|authori[sz]ed) to|may", "MAY"),
]
_PROSE_KEYWORD = re.compile(
    "|".join(f"(?P<m{i}>(?<![\\w'])(?:{pat})(?![\\w']))" for i, (pat, _) in enumerate(_PROSE_MODALS)), re.I
)
# 'may' that expresses possibility, not permission: "this may cause", "it may be".
_MAY_POSSIBILITY = re.compile(r"^\s*(?:be|cause|result|lead|vary|change|differ|affect|include|occur|take|apply|also be|not be)\b", re.I)

_NUM = r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?"
_UNITS = (
    r"octets?|characters?|bytes?|bits?|kilobytes?|megabytes?|gigabytes?|kb|mb|gb|tb|"
    r"milliseconds?|ms|seconds?|minutes?|hours?|(?:business |working |calendar )?days?|weeks?|months?|years?|"
    r"recipients?|attempts?|times|percent|per cent|%|"
    r"usd|eur|gbp|inr|dollars?|euros?|pounds?|rupees?|kg|kilograms?|km|kilometers?|kilometres?|miles?"
)
_NUMERIC = re.compile(
    rf"(?:(?<![\w$=])(?<!= )(?P<cur>[$€£₹]|\b(?:USD|EUR|GBP|INR|Rs\.?)\s?)(?P<cnum>{_NUM})(?![\w$])(?!\s*=)"
    rf"|(?P<num>{_NUM})(?:\s*(?:-|to)\s*(?P<num2>{_NUM}))?\s*(?P<unit>{_UNITS})(?![\w]))",
    re.I,
)
_CURRENCY = {"$": "usd", "€": "eur", "£": "gbp", "₹": "inr", "rs": "inr", "rs.": "inr", "dollar": "usd",
             "euro": "eur", "pound": "gbp", "rupee": "inr"}
_EXCLUSION = re.compile(r"\b(is not permitted|are not permitted|is prohibited|are prohibited|"
                        r"must not be used|is forbidden)\b", re.I)
_BOILERPLATE = re.compile(r"key ?words|BCP ?14|RFC ?2119|RFC ?8174", re.I)
_PRONOUNS = {"it", "this", "they", "these", "that", "those", "which", "he", "she", "one", "such"}
_STOPWORDS = {
    "a", "an", "the", "and", "or", "of", "to", "in", "on", "for", "with", "by", "at", "as", "be",
    "is", "are", "was", "were", "been", "being", "that", "this", "these", "those", "it", "its",
    "from", "into", "than", "then", "when", "if", "any", "all", "each", "such", "not", "no", "so",
    "but", "can", "will", "would", "also", "only", "other", "which", "who", "whom", "there",
    "their", "they", "them", "has", "have", "had", "do", "does", "using", "use", "used", "per",
}
_MODAL_WORDS = {"must", "shall", "should", "may", "required", "recommended", "optional"}
_UNIT_SINGULAR = {"times": "time", "ms": "millisecond", "%": "percent", "per cent": "percent",
                  "kb": "kilobyte", "mb": "megabyte", "gb": "gigabyte", "tb": "terabyte", "kg": "kilogram", "km": "kilometer"}
_BCP14_UPPER = re.compile(r"(?<![\w\"'])(?:MUST|SHALL|SHOULD|REQUIRED|RECOMMENDED)(?![\w\"'])")


_RFC_HEADER = re.compile(r"Request for Comments:\s*\d+|Internet Engineering Task Force|Network Working Group", re.I)


def detect_style(texts: list[str]) -> str:
    """'bcp14' when the document uses uppercase RFC 2119 keywords (or cites the convention), else 'prose'."""
    joined = "\n".join(texts)
    if _RFC_HEADER.search(joined[:20000]):
        return "bcp14"  # IETF documents: lowercase modals are not normative by convention
    hits = len(_BCP14_UPPER.findall(joined))
    return "bcp14" if hits >= 3 or (hits and _BOILERPLATE.search(joined)) else "prose"


@dataclass
class ClaimCandidate:
    claim_type: str  # requirement | exclusion | numeric
    modality: str | None
    subject: str | None
    subject_key: str | None
    predicate: str | None
    value_num: float | None = None
    unit: str | None = None
    topic_terms: list[str] = field(default_factory=list)
    needs_fallback: bool = False  # subject could not be determined deterministically


def _stem(word: str) -> str:
    """Light plural folding: policies→policy, minutes→minute, days→day, uris→uri (not 'ss'/'us'/'is')."""
    word = word.lower()
    if len(word) > 4 and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) > 3 and word.endswith("s") and not word.endswith(("ss", "us", "is")):
        return word[:-1]
    return word


def normalize_terms(text: str) -> list[str]:
    words = re.findall(r"[A-Za-z][A-Za-z0-9_\-]*", text)
    out = []
    for w in words:
        lw = w.lower()
        if lw in _STOPWORDS or lw in _MODAL_WORDS or len(lw) < 2:
            continue
        stem = _stem(lw)
        if stem not in out:
            out.append(stem)
    return out


def _subject(prefix: str) -> str | None:
    """Noun phrase right before the keyword: drop leading clauses, keep the last few words."""
    prefix = re.sub(r"\[[^\]]*\]|\([^)]*\)", " ", prefix)       # citations, parentheticals
    prefix = re.sub(r"[•*•◦]", " ", prefix)           # bullets
    prefix = re.sub(r"\s+(?:is|are|be|is not|are not)\s*$", "", prefix.strip())  # 'PKCE is OPTIONAL'
    clause = re.split(r"[,;:]\s+|\bthen\b|\botherwise\b|\(|\)", prefix)[-1].strip()
    clause = re.sub(r"^(?:and|or|but|so|thus|hence|therefore|also)\s+", "", clause, flags=re.I)
    clause = re.split(r"\s+(?:that|which|who|whose)\s+", clause)[0]  # head noun before relative clause
    words = clause.split()
    if not words:
        return None
    words = words[-12:]
    while words and words[0].lower() in {"the", "a", "an", "all", "any", "each", "every"}:
        words = words[1:]
    subject = " ".join(words).strip(" \"'")
    if not subject or subject.lower() in _PRONOUNS:
        return None
    return subject


def _unit(raw: str) -> str:
    raw = " ".join(raw.lower().split())
    if raw in _UNIT_SINGULAR:
        return _UNIT_SINGULAR[raw]
    single = raw[:-1] if raw.endswith("s") and raw not in ("ms",) else raw
    return _CURRENCY.get(single, single)


def _value(num: re.Match) -> tuple[float, str]:
    if num.group("cnum") is not None:
        cur = num.group("cur").strip().lower()
        return float(num.group("cnum").replace(",", "")), _CURRENCY.get(cur, cur)
    return float(num.group("num").replace(",", "")), _unit(num.group("unit"))


class _Keyword:
    """Uniform view over a BCP 14 or prose modal match."""

    def __init__(self, start: int, end: int, modality: str):
        self._start, self._end, self.modality = start, end, modality

    def start(self) -> int:
        return self._start

    def end(self) -> int:
        return self._end


def _find_keyword(flat: str, style: str) -> _Keyword | None:
    kw = _KEYWORD.search(flat)
    if kw:
        return _Keyword(kw.start(), kw.end(), _CANONICAL_MODALITY.get(kw.group(1), kw.group(1)))
    if style != "prose":
        return None
    for m in _PROSE_KEYWORD.finditer(flat):
        idx = next(i for i in range(len(_PROSE_MODALS)) if m.group(f"m{i}"))
        modality = _PROSE_MODALS[idx][1]
        if modality == "MAY" and m.group(0).lower() == "may" and _MAY_POSSIBILITY.match(flat[m.end():]):
            continue  # "this may cause delays": possibility, not permission
        return _Keyword(m.start(), m.end(), modality)
    return None


def extract_claim(sentence: str, style: str = "bcp14") -> ClaimCandidate | None:
    flat = flatten(sentence)
    if len(flat) < 12:
        return None
    kw = _find_keyword(flat, style)
    if kw and _BOILERPLATE.search(flat):
        return None  # 'The key words "MUST", ... are to be interpreted as described in BCP 14'
    num = _NUMERIC.search(flat)

    if kw:
        modality = kw.modality
        subject = _subject(flat[:kw.start()])
        if style == "prose" and modality == "MAY" and subject is None:
            kw = None  # bare 'may' without a clear actor is too often possibility
    if kw:
        predicate = flat[kw.end():].strip(" .")
        claim_type = "exclusion" if modality in ("MUST NOT", "SHOULD NOT") else "requirement"
    elif num:
        modality, claim_type = None, "numeric"
        subject = _subject(flat[:num.start()]) or None
        predicate = flat
    elif _EXCLUSION.search(flat):
        m = _EXCLUSION.search(flat)
        modality, claim_type = "MUST NOT", "exclusion"
        subject = _subject(flat[:m.start()])
        predicate = flat[m.end():].strip(" .")
    else:
        return None

    return ClaimCandidate(
        claim_type=claim_type,
        modality=modality,
        subject=subject,
        subject_key=" ".join(normalize_terms(subject)) if subject else None,
        predicate=predicate or None,
        value_num=_value(num)[0] if num else None,
        unit=_value(num)[1] if num else None,
        topic_terms=normalize_terms(flat),
        needs_fallback=bool(kw) and subject is None,
    )
