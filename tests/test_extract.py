import pytest

from docusense.extract.claims import extract_claim
from docusense.extract.definitions import find_definitions
from docusense.extract.references import build_tag_map, detect_references, detect_relations
from docusense.extract.sentences import split_sentences

# ── sentences ────────────────────────────────────────────────────────────────


def test_sentence_offsets_are_exact():
    text = "   First sentence here.  Second one, e.g. with an abbreviation.\n   Third (see\n   Section 4.1)."
    base = 1000
    data = text.encode()
    sentences = split_sentences(text, base)
    assert [s.text.split()[0] for s in sentences] == ["First", "Second", "Third"]
    for s in sentences:
        assert data[s.start - base:s.end - base].decode() == s.text


def test_sentence_split_keeps_initials_together():
    assert len(split_sentences("Written by J. Klensin in 2008. Another sentence.")) == 2


# ── claims ───────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("sentence, ctype, modality, subject, value, unit", [
    ("The maximum total length of a text line including the <CRLF> is 1000 octets.",
     "numeric", None, "maximum total length of a text line including the <CRLF>", 1000, "octet"),
    ("When comparing redirect URIs, authorization servers MUST utilize exact string matching.",
     "requirement", "MUST", "authorization servers", None, None),
    ("Clients SHOULD NOT use the implicit grant.", "exclusion", "SHOULD NOT", "Clients", None, None),
    ("PKCE is OPTIONAL for confidential clients.", "requirement", "MAY", "PKCE", None, None),
    ("• Public clients MUST use PKCE [RFC7636] to this end.", "requirement", "MUST", "Public clients", None, None),
    ("An authorization server that redirects a request MUST use 303.", "requirement", "MUST",
     "authorization server", None, None),
    ("The give-up time SHALL be at least 4-5 days.", "requirement", "MUST", "give-up time", 4, "day"),
])
def test_claim_extraction(sentence, ctype, modality, subject, value, unit):
    c = extract_claim(sentence)
    assert (c.claim_type, c.modality, c.subject, c.value_num, c.unit) == (ctype, modality, subject, value, unit)


def test_pronoun_subject_needs_fallback():
    c = extract_claim("It MUST be rejected by the server.")
    assert c.subject is None and c.needs_fallback


def test_bcp14_boilerplate_is_not_a_claim():
    assert extract_claim('The key words "MUST", "MUST NOT" and "MAY" in this document are to be '
                         'interpreted as described in BCP 14 [RFC2119].') is None


def test_lowercase_must_is_not_a_requirement():
    assert extract_claim("Implementations must handle this case gracefully.") is None


# ── references ───────────────────────────────────────────────────────────────

TAGS = build_tag_map([
    '[RFC5322]  Resnick, P., Ed., "Internet Message Format", RFC 5322, October 2008.',
    '[2]  Braden, R., "Requirements for Internet hosts", STD 3, RFC 1123, October 1989.',
    '[BCP195]  Best Current Practice 195.',
    'Moriarty, K., "Deprecating TLS 1.0 and TLS 1.1", BCP 195, RFC 8996, March 2021.',
    '[W3C.CORS]  van Kesteren, A., "Cross-Origin Resource Sharing", 2014.',
])


def test_tag_map():
    assert TAGS == {"RFC5322": "5322", "2": "1123", "BCP195": "8996", "W3C.CORS": None}


def test_detect_references():
    text = ("See Section 3.4 of [RFC5322] and [RFC5322], Appendix A.1. Also Sections 4.1.1 and 4.1.2,\n"
            "   section 2.4 and Appendix B, as discussed in [2] and [W3C.CORS]. RFC 6749 applies.")
    refs = [(r.relation, r.rfc, r.section) for r in detect_references(text, TAGS)]
    assert refs == [
        ("section", "5322", "3.4"),
        ("section", "5322", "A.1"),
        ("section", None, "4.1.1"),
        ("section", None, "4.1.2"),
        ("section", None, "2.4"),
        ("section", None, "B"),
        ("cites", "1123", None),
        ("cites", None, None),
        ("cites", "6749", None),
    ]


def test_section_list_does_not_swallow_next_word():
    refs = detect_references("see Section 4.10.1, Section 4.11 for details", {})
    assert [r.section for r in refs] == ["4.10.1", "4.11"]


def test_untagged_rfc_bracket_resolves_by_name():
    refs = detect_references("as in Section 3.4 of [RFC5322]", {})
    assert refs[0].rfc == "5322"


def test_relations():
    rels = [(r.relation, r.rfc) for r in detect_relations("Obsoletes: 2821\nUpdates: 1123, 6750")]
    assert rels == [("obsoletes", "2821"), ("updates", "1123"), ("updates", "6750")]


# ── definitions ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize("text, terminology, expected", [
    ('"Relay server" means any server that accepts mail.', False, ["Relay server"]),
    ('An "open redirector" is an endpoint on a web server.', False, ["open redirector"]),
    ('The term "access token" refers to a credential.', False, ["access token"]),
    ("   resource owner\n      An entity capable of granting access.", False, ["resource owner"]),
    ("Greeting: the first line sent by a client.", True, ["Greeting"]),
    ("Greeting: the first line sent by a client.", False, []),
    ('1. MUST   This word, or the terms "REQUIRED" or "SHALL", mean that', False, ["MUST"]),
    ("The client sends a request.", False, []),
])
def test_definitions(text, terminology, expected):
    assert [d.term for d in find_definitions(text, terminology)] == expected
