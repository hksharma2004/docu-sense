"""Run deterministic extraction for a version and persist refs, definitions and claims.

Extraction output is derived data: re-running it replaces the version's refs/definitions/claims.
Sentence spans it creates are evidence and append-only (deduplicated by byte range).
"""

import re
from collections import Counter
from dataclasses import dataclass, field

import psycopg

from docusense.config import PARSER_VERSION
from docusense.extract.claims import extract_claim, normalize_terms
from docusense.extract.definitions import TERMINOLOGY_SECTION, find_definitions, normalize_term
from docusense.extract.llm_fallback import SubjectFallback
from docusense.extract.references import (
    RefMatch, build_tag_map, detect_references, detect_relations,
)
from docusense.extract.sentences import flatten, split_sentences
from docusense.store.blobs import sha256_hex

EXTRACTOR = "regex/0.1"

SKIP_SECTIONS = re.compile(
    r"^(table of contents|contents|status of this memo|copyright notice|full copyright statement|"
    r"intellectual property|authors?'?s?'? addresses|author'?s address|editors?'? address(es)?|"
    r"acknowledge?ments?|index|contributors)$",
    re.I,
)
REFERENCE_SECTION = re.compile(r"^((normative|informative) )?references$", re.I)


@dataclass
class ExtractStats:
    version_id: str
    refs: Counter = field(default_factory=Counter)
    definitions: int = 0
    claims: Counter = field(default_factory=Counter)
    sentences: int = 0
    llm_calls: int = 0


def _corpus_maps(conn: psycopg.Connection) -> tuple[dict[str, dict], dict[tuple[str, str], int]]:
    rfc_versions = {}
    for v in conn.execute("SELECT id, document_id, label FROM versions"):
        m = re.fullmatch(r"rfc0*(\d+)", v["label"])
        if m:
            rfc_versions[m.group(1)] = v
    sections = {
        (s["version_id"], s["number"]): s["id"]
        for s in conn.execute("SELECT id, version_id, number FROM sections WHERE number IS NOT NULL ORDER BY ordinal DESC")
    }
    return rfc_versions, sections


def _resolve(ref: RefMatch, version_id: str, rfc_versions: dict, sections: dict) -> dict:
    row = {"raw": ref.raw, "relation": ref.relation, "target_doc": None, "target_rfc": ref.rfc,
           "target_version": None, "target_section": ref.section, "resolved_section_id": None}
    if ref.internal:
        row["target_version"] = version_id
        row["resolved_section_id"] = sections.get((version_id, ref.section))
        row["status"] = "resolved" if row["resolved_section_id"] else "unresolved"
        return row
    target = rfc_versions.get(ref.rfc) if ref.rfc else None
    if target is None:
        row["status"] = "external"  # outside the corpus (or a non-RFC citation)
        return row
    row["target_doc"] = target["document_id"]
    row["target_version"] = target["id"]
    if ref.section:
        row["resolved_section_id"] = sections.get((target["id"], ref.section))
        row["status"] = "resolved" if row["resolved_section_id"] else "unresolved"
    else:
        row["status"] = "resolved"
    return row


def extract_version(
    conn: psycopg.Connection,
    version_id: str,
    fallback: SubjectFallback | None = None,
    maps: tuple[dict, dict] | None = None,
) -> ExtractStats:
    stats = ExtractStats(version_id)
    rfc_versions, sections = maps or _corpus_maps(conn)
    spans = conn.execute(
        """SELECT p.id, p.kind, p.ordinal, p.page, p.start_byte, p.text, p.section_id, s.number, s.title, s.level,
                  s.ordinal AS section_ordinal, par.title AS parent_title
           FROM spans p
           LEFT JOIN sections s ON s.id = p.section_id
           LEFT JOIN sections par ON par.id = s.parent_id
           WHERE p.version_id = %s AND p.kind <> 'sentence'
           ORDER BY p.ordinal""",
        (version_id,),
    ).fetchall()

    def in_reference_list(sp: dict) -> bool:
        return bool(REFERENCE_SECTION.match(sp["title"] or "")) or bool(
            REFERENCE_SECTION.match(sp["parent_title"] or "") and sp["level"] and sp["level"] > 1)

    tag_map = build_tag_map([sp["text"] for sp in spans if in_reference_list(sp)])
    if fallback:
        fallback.reset_budget()

    with conn.transaction():
        conn.execute("DELETE FROM conflicts WHERE claim_a IN (SELECT id FROM claims WHERE version_id = %s) "
                     "OR claim_b IN (SELECT id FROM claims WHERE version_id = %s)", (version_id, version_id))
        for table in ("refs", "definitions", "claims"):
            conn.execute(f"DELETE FROM {table} WHERE version_id = %s", (version_id,))

        first_span_of_section: dict[int, int] = {}
        for sp in spans:
            title = sp["title"] or ""
            if sp["section_id"] is not None:
                first_span_of_section.setdefault(sp["section_id"], sp["id"])

            if title == "Front Matter":
                for ref in detect_relations(sp["text"]):
                    _insert_ref(conn, sp["id"], version_id, _resolve(ref, version_id, rfc_versions, sections), stats)
                continue
            if SKIP_SECTIONS.match(title) or in_reference_list(sp):
                continue

            for ref in detect_references(sp["text"], tag_map):
                _insert_ref(conn, sp["id"], version_id, _resolve(ref, version_id, rfc_versions, sections), stats)

            terminology = bool(TERMINOLOGY_SECTION.search(title) or TERMINOLOGY_SECTION.search(sp["parent_title"] or ""))
            for d in find_definitions(sp["text"], terminology):
                _insert_definition(conn, d.term, d.method, sp["id"], sp["section_id"], version_id)
                stats.definitions += 1

            if sp["kind"] == "paragraph":
                _extract_claims(conn, sp, version_id, stats, fallback)

        # Subsections of a terminology section define their own title (RFC 5321 §2.3.x style).
        for s in conn.execute(
            """SELECT c.id, c.title, p.title AS parent_title FROM sections c
               JOIN sections p ON p.id = c.parent_id WHERE c.version_id = %s""", (version_id,)
        ).fetchall():
            if (TERMINOLOGY_SECTION.search(s["parent_title"]) and s["id"] in first_span_of_section
                    and len(s["title"].split()) <= 6):
                _insert_definition(conn, s["title"], "layout:terminology-subsection",
                                   first_span_of_section[s["id"]], s["id"], version_id)
                stats.definitions += 1
    conn.commit()
    if fallback:
        stats.llm_calls = fallback.calls
    return stats


def _insert_ref(conn, span_id: int, version_id: str, row: dict, stats: ExtractStats) -> None:
    conn.execute(
        """INSERT INTO refs (span_id, version_id, raw, relation, target_doc, target_rfc, target_version,
                             target_section, resolved_section_id, status)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
        (span_id, version_id, row["raw"], row["relation"], row["target_doc"], row["target_rfc"],
         row["target_version"], row["target_section"], row["resolved_section_id"], row["status"]),
    )
    stats.refs[row["status"]] += 1


def _insert_definition(conn, term: str, method: str, span_id: int, section_id: int | None, version_id: str) -> None:
    conn.execute(
        """INSERT INTO definitions (term, term_norm, span_id, section_id, version_id, method)
           VALUES (%s, %s, %s, %s, %s, %s)""",
        (term, normalize_term(term), span_id, section_id, version_id, method),
    )


def _sentence_span_id(conn, version_id: str, section_id: int | None, ordinal: int, start: int,
                      end: int, text: str, page: int) -> int:
    row = conn.execute(
        """INSERT INTO spans (version_id, section_id, kind, ordinal, start_byte, end_byte, page, sha256,
                              text, parser_version, extraction_method)
           VALUES (%s, %s, 'sentence', %s, %s, %s, %s, %s, %s, %s, 'regex')
           ON CONFLICT (version_id, kind, start_byte, end_byte) DO NOTHING RETURNING id""",
        (version_id, section_id, ordinal, start, end, page, sha256_hex(text.encode()), text, PARSER_VERSION),
    ).fetchone()
    if row:
        return row["id"]
    return conn.execute(
        "SELECT id FROM spans WHERE version_id = %s AND kind = 'sentence' AND start_byte = %s AND end_byte = %s",
        (version_id, start, end),
    ).fetchone()["id"]


def _extract_claims(conn, sp: dict, version_id: str, stats: ExtractStats, fallback: SubjectFallback | None) -> None:
    for i, sent in enumerate(split_sentences(sp["text"], base=sp["start_byte"])):
        claim = extract_claim(sent.text)
        if claim is None:
            continue
        method, model_id, prompt_hash, confidence = EXTRACTOR, None, None, 1.0
        if claim.needs_fallback and fallback and fallback.available:
            result = fallback.subject_for(flatten(sent.text), flatten(sp["text"]))
            if result and result.subject:
                claim.subject = result.subject
                claim.subject_key = " ".join(normalize_terms(result.subject))
                method, model_id, prompt_hash, confidence = "llm", result.model_id, result.prompt_hash, result.confidence
        span_id = _sentence_span_id(conn, version_id, sp["section_id"], sp["ordinal"] * 1000 + i,
                                    sent.start, sent.end, sent.text, sp["page"])
        stats.sentences += 1
        conn.execute(
            """INSERT INTO claims (span_id, version_id, claim_type, subject, subject_key, modality, predicate,
                                   value_num, unit, topic_terms, method, model_id, prompt_hash, confidence)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (span_id, version_id, claim.claim_type, claim.subject, claim.subject_key, claim.modality,
             claim.predicate, claim.value_num, claim.unit, claim.topic_terms, method, model_id,
             prompt_hash, confidence if method == "llm" else (0.5 if claim.needs_fallback else 1.0)),
        )
        stats.claims[claim.claim_type] += 1


def extract_all(conn: psycopg.Connection, llm_fallback: bool = False, version_id: str | None = None) -> list[ExtractStats]:
    maps = _corpus_maps(conn)
    fallback = SubjectFallback() if llm_fallback else None
    ids = [version_id] if version_id else [r["id"] for r in conn.execute("SELECT id FROM versions ORDER BY document_id, seq")]
    conn.rollback()
    return [extract_version(conn, vid, fallback, maps) for vid in ids]
