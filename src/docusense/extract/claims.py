"""Pattern-based claim extraction: BCP 14 requirements, numeric facts and exclusions.

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
_NUMERIC = re.compile(
    r"(?P<num>\d+(?:\.\d+)?)(?:\s*(?:-|to)\s*(?P<num2>\d+(?:\.\d+)?))?\s*"
    r"(?P<unit>octets?|characters?|bytes?|bits?|seconds?|minutes?|hours?|days?|recipients?|"
    r"attempts?|times)\b",
    re.I,
)
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
_UNIT_SINGULAR = {"times": "time"}


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
    raw = raw.lower()
    return _UNIT_SINGULAR.get(raw, raw[:-1] if raw.endswith("s") else raw)


def extract_claim(sentence: str) -> ClaimCandidate | None:
    flat = flatten(sentence)
    if len(flat) < 12:
        return None
    kw = _KEYWORD.search(flat)
    if kw and _BOILERPLATE.search(flat):
        return None  # 'The key words "MUST", ... are to be interpreted as described in BCP 14'
    num = _NUMERIC.search(flat)

    if kw:
        modality = _CANONICAL_MODALITY.get(kw.group(1), kw.group(1))
        subject = _subject(flat[:kw.start()])
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
        value_num=float(num.group("num")) if num else None,
        unit=_unit(num.group("unit")) if num else None,
        topic_terms=normalize_terms(flat),
        needs_fallback=bool(kw) and subject is None,
    )
