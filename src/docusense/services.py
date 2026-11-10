"""Query layer shared by the MCP server, the REST API and the benchmark harness.

Every function returns plain JSON-serialisable dicts. Evidence always carries a citation:
    ds://<version_id>#§<section>:b<start>-<end>
plus the span's SHA-256, so any consumer can re-verify it.
"""

import json
import re

import psycopg

from docusense.extract.claims import normalize_terms
from docusense.extract.definitions import normalize_term
from docusense.extract.references import build_tag_map, detect_references
from docusense.extract.run import _corpus_maps, _resolve
from docusense.provenance import Verifier

CANONICAL_MODALITY = {
    "SHALL": "MUST", "REQUIRED": "MUST", "SHALL NOT": "MUST NOT",
    "RECOMMENDED": "SHOULD", "NOT RECOMMENDED": "SHOULD NOT", "OPTIONAL": "MAY",
}
RRF_K = 60

_SPAN_COLS = """p.id, p.version_id, p.kind, p.start_byte, p.end_byte, p.page, p.sha256, p.text,
                s.id AS section_id, s.number, s.title AS section_title, v.document_id, v.seq"""
_SPAN_FROM = """spans p JOIN versions v ON v.id = p.version_id LEFT JOIN sections s ON s.id = p.section_id"""


class NotFound(ValueError):
    pass


def tokens(obj) -> int:
    """Cheap token estimate (chars / 4) used for budget-aware responses."""
    return len(json.dumps(obj, ensure_ascii=False)) // 4


def citation(version_id: str, number: str | None, title: str | None, start: int, end: int) -> str:
    return f"ds://{version_id}#§{number or title or '-'}:b{start}-{end}"


def _clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit].rstrip() + " …"


class DocuSense:
    def __init__(self, conn: psycopg.Connection):
        self.conn = conn
        self.verifier = Verifier(conn)
        self._bm25 = None

    # ── helpers ──────────────────────────────────────────────────────────────

    def _latest(self) -> dict[str, dict]:
        rows = self.conn.execute(
            "SELECT DISTINCT ON (document_id) document_id, id, seq FROM versions ORDER BY document_id, seq DESC"
        ).fetchall()
        return {r["document_id"]: r for r in rows}

    def version(self, doc: str, version: str | None = None) -> dict:
        """Resolve 'smtp', 'smtp@rfc5321', 'rfc5321', 'RFC 5321' (+ optional version label)."""
        key = re.sub(r"\s+", "", doc.strip().lower())
        if version:
            vkey = re.sub(r"\s+", "", version.strip().lower())
            row = self.conn.execute(
                "SELECT * FROM versions WHERE id = %s OR (document_id = %s AND label = %s)",
                (vkey if "@" in vkey else f"{key}@{vkey}", key, vkey),
            ).fetchone()
        elif "@" in key:
            row = self.conn.execute("SELECT * FROM versions WHERE id = %s", (key,)).fetchone()
        else:
            row = self.conn.execute(
                """SELECT * FROM versions WHERE label = %s OR label = %s
                   UNION ALL
                   (SELECT * FROM versions WHERE document_id = %s ORDER BY seq DESC LIMIT 1)
                   LIMIT 1""",
                (key, "rfc" + key.removeprefix("rfc").lstrip("0"), key),
            ).fetchone()
        if row is None:
            docs = ", ".join(r["id"] for r in self.conn.execute("SELECT id FROM documents ORDER BY id"))
            raise NotFound(f"unknown document/version {doc!r}{' / ' + version if version else ''}. Known documents: {docs}")
        latest = self._latest()[row["document_id"]]
        row["is_latest"] = latest["id"] == row["id"]
        row["latest_version"] = latest["id"]
        return row

    def _span_view(self, r: dict, text_limit: int = 1200) -> dict:
        latest = self._latest().get(r["document_id"])
        view = {
            "span_id": r["id"],
            "citation": citation(r["version_id"], r["number"], r["section_title"], r["start_byte"], r["end_byte"]),
            "version": r["version_id"],
            "section": " ".join(x for x in (r["number"], r["section_title"]) if x),
            "page": r["page"],
            "kind": r["kind"],
            "text": _clip(r["text"].strip(), text_limit),
            "sha256": r["sha256"],
        }
        if latest and latest["id"] != r["version_id"]:
            view["newer_version"] = latest["id"]
        return view

    def _spans(self, where: str, params: tuple, order: str = "p.ordinal") -> list[dict]:
        return self.conn.execute(f"SELECT {_SPAN_COLS} FROM {_SPAN_FROM} WHERE {where} ORDER BY {order}", params).fetchall()

    def _fit(self, items: list, max_tokens: int) -> tuple[list, bool]:
        out, used = [], 0
        for item in items:
            cost = tokens(item)
            if out and used + cost > max_tokens:
                return out, True
            out.append(item)
            used += cost
        return out, False

    def _doc_filter(self, doc: str, version_col: str = "p.version_id") -> tuple[str, str]:
        """A specific version ('smtp@rfc5321', 'rfc5321') filters by version; a document id by document."""
        v = self.version(doc)
        key = doc.lower().replace(" ", "")
        if "@" in key or re.fullmatch(r"rfc\d+", key):
            return f"{version_col} = %s", v["id"]
        return "v.document_id = %s", v["document_id"]

    def _section(self, version_id: str, section: str) -> dict:
        s = section.strip().removeprefix("§").removeprefix("Section ").removeprefix("Appendix ").strip().rstrip(".")
        row = self.conn.execute(
            "SELECT * FROM sections WHERE version_id = %s AND number = %s", (version_id, s)
        ).fetchone() or self.conn.execute(
            "SELECT * FROM sections WHERE version_id = %s AND title ILIKE %s ORDER BY length(title), ordinal LIMIT 1",
            (version_id, f"%{s}%"),
        ).fetchone()
        if row is None:
            raise NotFound(f"no section {section!r} in {version_id}; call get_section_map to see valid sections")
        return row

    def _section_path(self, section_id: int | None) -> list[str]:
        path = []
        while section_id:
            s = self.conn.execute("SELECT parent_id, number, title FROM sections WHERE id = %s", (section_id,)).fetchone()
            path.append(" ".join(x for x in (s["number"], s["title"]) if x))
            section_id = s["parent_id"]
        return path[::-1]

    def _paragraph_for(self, span_id: int) -> dict:
        """Map a sentence span to the paragraph span containing it (refs live on paragraphs)."""
        r = self.conn.execute("SELECT id, version_id, kind, start_byte, end_byte FROM spans WHERE id = %s", (span_id,)).fetchone()
        if r is None:
            raise NotFound(f"no span {span_id}")
        if r["kind"] != "sentence":
            return r
        return self.conn.execute(
            """SELECT id, version_id, kind, start_byte, end_byte FROM spans WHERE version_id = %s
               AND kind <> 'sentence' AND start_byte <= %s AND end_byte >= %s LIMIT 1""",
            (r["version_id"], r["start_byte"], r["end_byte"]),
        ).fetchone() or r

    # ── 1. navigation ────────────────────────────────────────────────────────

    def list_documents(self) -> dict:
        rows = self.conn.execute(
            """SELECT d.id, d.title, d.source_family, v.id AS version_id, v.label, v.seq, v.format,
                      jsonb_array_length(v.page_map) AS pages
               FROM documents d JOIN versions v ON v.document_id = d.id ORDER BY d.id, v.seq"""
        ).fetchall()
        latest = self._latest()
        docs: dict[str, dict] = {}
        for r in rows:
            d = docs.setdefault(r["id"], {"document": r["id"], "title": r["title"], "family": r["source_family"], "versions": []})
            d["versions"].append({"version_id": r["version_id"], "label": r["label"], "seq": r["seq"],
                                  "pages": r["pages"], "is_latest": latest[r["id"]]["id"] == r["version_id"]})
        return {"documents": list(docs.values()),
                "note": "Versions are ordered oldest→newest; a newer RFC that obsoletes an older one is its next version."}

    def get_section_map(self, doc: str, version: str | None = None, max_depth: int = 3, max_tokens: int = 3000) -> dict:
        v = self.version(doc, version)
        rows = self.conn.execute(
            """SELECT id, number, title, level, page_start, page_end FROM sections
               WHERE version_id = %s AND level <= %s ORDER BY ordinal""", (v["id"], max_depth)
        ).fetchall()
        items = [{"number": r["number"], "title": r["title"], "level": r["level"], "pages": f"{r['page_start']}-{r['page_end']}"}
                 for r in rows]
        items, truncated = self._fit(items, max_tokens)
        return {"version": v["id"], "is_latest": v["is_latest"], "latest_version": v["latest_version"],
                "sections": items, "truncated": truncated}

    def read_section(self, doc: str, section: str, version: str | None = None,
                     include_subsections: bool = False, max_tokens: int = 3000) -> dict:
        v = self.version(doc, version)
        s = self._section(v["id"], section)
        if include_subsections:
            spans = self._spans("p.version_id = %s AND p.kind <> 'sentence' AND p.start_byte >= %s AND p.start_byte < %s",
                                (v["id"], s["start_byte"], max(s["end_byte"], s["start_byte"] + 1)))
        else:
            spans = self._spans("p.section_id = %s AND p.kind <> 'sentence'", (s["id"],))
        items, truncated = self._fit([self._span_view(r, 4000) for r in spans], max_tokens)
        children = self.conn.execute(
            "SELECT number, title FROM sections WHERE parent_id = %s ORDER BY ordinal", (s["id"],)
        ).fetchall()
        return {
            "version": v["id"], "is_latest": v["is_latest"], "latest_version": v["latest_version"],
            "section": " ".join(x for x in (s["number"], s["title"]) if x),
            "path": self._section_path(s["id"]),
            "pages": f"{s['page_start']}-{s['page_end']}",
            "spans": items, "truncated": truncated,
            "subsections": [" ".join(x for x in (c["number"], c["title"]) if x) for c in children],
        }

    # ── 2. search ────────────────────────────────────────────────────────────

    def search(self, query: str, mode: str = "hybrid", doc: str | None = None, k: int = 5,
               max_tokens: int = 2500) -> dict:
        if mode not in ("lexical", "semantic", "hybrid"):
            raise ValueError("mode must be lexical, semantic or hybrid")
        pool = 200 if doc else 50
        rankings: list[list[int]] = []
        if mode in ("lexical", "hybrid"):
            if self._bm25 is None:
                from docusense.index.bm25 import BM25Index
                self._bm25 = BM25Index()
            rankings.append([sid for sid, _ in self._bm25.search(query, pool)])
        if mode in ("semantic", "hybrid"):
            from docusense.index import embed
            rankings.append([sid for sid, _ in embed.search(self.conn, query, pool)])

        scores: dict[int, float] = {}
        for ranking in rankings:
            for rank, sid in enumerate(ranking):
                scores[sid] = scores.get(sid, 0.0) + 1.0 / (RRF_K + rank + 1)
        ordered = sorted(scores, key=scores.get, reverse=True)
        if not ordered:
            return {"query": query, "mode": mode, "results": [], "truncated": False}

        where, params = "p.id = ANY(%s)", [ordered]
        if doc:
            clause, value = self._doc_filter(doc)
            where += " AND " + clause
            params.append(value)
        rows = {r["id"]: r for r in self._spans(where, tuple(params), "p.id")}
        results = []
        for sid in ordered:
            if sid in rows:
                view = self._span_view(rows[sid], 700)
                view["score"] = round(scores[sid], 5)
                results.append(view)
            if len(results) >= k:
                break
        results, truncated = self._fit(results, max_tokens)
        return {"query": query, "mode": mode, "results": results, "truncated": truncated}

    def search_claims(self, topic: str | None = None, subject: str | None = None, modality: str | None = None,
                      claim_type: str | None = None, doc: str | None = None, k: int = 10,
                      max_tokens: int = 2500) -> dict:
        where, params, rank = ["TRUE"], [], "0"
        if topic:
            terms = normalize_terms(topic)
            where.append("c.topic_terms && %s")
            params.append(terms)
            rank = "cardinality(ARRAY(SELECT unnest(c.topic_terms) INTERSECT SELECT unnest(%s::text[])))"
        if subject:
            where.append("c.subject_key LIKE %s")
            params.append("%" + " ".join(normalize_terms(subject)) + "%")
        if modality:
            m = modality.strip().upper()
            where.append("c.modality = %s")
            params.append(CANONICAL_MODALITY.get(m, m))
        if claim_type:
            where.append("c.claim_type = %s")
            params.append(claim_type)
        if doc:
            clause, value = self._doc_filter(doc, "c.version_id")
            where.append(clause)
            params.append(value)

        order_params = [terms] if topic else []
        rows = self.conn.execute(
            f"""SELECT c.claim_type, c.modality, c.subject, c.value_num, c.unit, c.method, c.confidence,
                       {_SPAN_COLS}, {rank} AS overlap
                FROM claims c JOIN {_SPAN_FROM} ON p.id = c.span_id
                WHERE {' AND '.join(where)}
                ORDER BY overlap DESC, v.seq DESC, c.id LIMIT %s""",
            tuple(order_params + params + [k]),
        ).fetchall()
        results = []
        for r in rows:
            view = self._span_view(r, 500)
            view["claim"] = {"type": r["claim_type"], "modality": r["modality"], "subject": r["subject"],
                             "value": r["value_num"], "unit": r["unit"], "method": r["method"],
                             "confidence": r["confidence"]}
            results.append(view)
        results, truncated = self._fit(results, max_tokens)
        return {"results": results, "truncated": truncated}

    # ── 3. references and definitions ────────────────────────────────────────

    def _ref_target(self, row: dict) -> dict:
        out = {"raw": row["raw"], "relation": row["relation"], "status": row["status"],
               "target_version": row["target_version"], "target_section": row["target_section"]}
        if row.get("target_rfc"):
            out["target_rfc"] = f"RFC {row['target_rfc']}"
        if row["target_version"]:
            tv = self.version(row["target_version"])
            out["target_is_latest"] = tv["is_latest"]
            if not tv["is_latest"]:
                out["newer_version"] = tv["latest_version"]
        if row.get("resolved_section_id"):
            s = self.conn.execute("SELECT * FROM sections WHERE id = %s", (row["resolved_section_id"],)).fetchone()
            out["target_section_title"] = s["title"]
            first = self._spans("p.section_id = %s AND p.kind <> 'sentence'", (s["id"],))[:2]
            out["preview"] = [self._span_view(r, 600) for r in first]
        elif row["status"] == "external":
            out["note"] = "target is outside the corpus"
        elif row["status"] == "unresolved":
            out["note"] = "target section not found in the target document"
        return out

    def resolve_reference(self, span_id: int | None = None, reference: str | None = None,
                          doc: str | None = None, max_tokens: int = 3000) -> dict:
        if span_id is None and not reference:
            raise ValueError("give span_id (resolve every reference inside a span) or reference text + doc")
        if span_id is not None:
            para = self._paragraph_for(span_id)
            rows = self.conn.execute("SELECT * FROM refs WHERE span_id = %s ORDER BY id", (para["id"],)).fetchall()
            source = para["version_id"]
        else:
            if not doc:
                raise ValueError("doc is required when resolving free-text references")
            v = self.version(doc)
            source = v["id"]
            entries = [r["text"] for r in self._spans(
                "p.version_id = %s AND p.kind <> 'sentence' AND s.title ~* 'references$'", (v["id"],))]
            rfc_versions, sections = _corpus_maps(self.conn)
            rows = [_resolve(ref, v["id"], rfc_versions, sections)
                    for ref in detect_references(reference, build_tag_map(entries))]
            if not rows:
                raise NotFound(f"no reference recognised in {reference!r} (try 'Section 3.4 of [RFC5322]' or 'RFC 6749')")
        items, truncated = self._fit([self._ref_target(r) for r in rows], max_tokens)
        return {"source_version": source, "references": items, "truncated": truncated}

    def lookup_definition(self, term: str, doc: str | None = None, k: int = 5, max_tokens: int = 2000) -> dict:
        norm = normalize_term(term)
        variants = list({norm, norm.rstrip("s"), norm + "s"})
        where, params = "(d.term_norm = ANY(%s) OR d.term_norm LIKE %s)", [variants, f"%{norm}%"]
        if doc:
            v = self.version(doc)
            where += " AND v.document_id = %s"
            params.append(v["document_id"])
        rows = self.conn.execute(
            f"""SELECT d.term, d.method, {_SPAN_COLS}, d.term_norm = ANY(%s) AS exact, doc.source_family
                FROM definitions d JOIN {_SPAN_FROM} ON p.id = d.span_id JOIN documents doc ON doc.id = v.document_id
                WHERE {where}
                ORDER BY exact DESC, (doc.source_family = 'rfc') DESC, v.seq DESC, length(d.term) LIMIT %s""",
            tuple([variants] + params + [k]),
        ).fetchall()
        results = []
        for r in rows:
            view = self._span_view(r, 900)
            view["term"], view["method"], view["exact"] = r["term"], r["method"], r["exact"]
            results.append(view)
        results, truncated = self._fit(results, max_tokens)
        hint = None if results else "no definition found; try search(query=...) for usage of the term"
        return {"term": term, "results": results, "truncated": truncated, **({"hint": hint} if hint else {})}

    # ── 4. evidence and provenance ───────────────────────────────────────────

    def get_evidence(self, span_id: int, verify: bool = True) -> dict:
        rows = self._spans("p.id = %s", (span_id,))
        if not rows:
            raise NotFound(f"no span {span_id}")
        r = rows[0]
        view = self._span_view(r, 20000)
        v = self.version(r["version_id"])
        meta = self.conn.execute(
            "SELECT parser_version, extraction_method, model_id, confidence FROM spans WHERE id = %s", (span_id,)
        ).fetchone()
        view.update({
            "section_path": self._section_path(r["section_id"]),
            "is_latest": v["is_latest"],
            "latest_version": v["latest_version"],
            "provenance": {"version_id": r["version_id"], "start_byte": r["start_byte"], "end_byte": r["end_byte"],
                           "sha256": r["sha256"], "text_sha256": v["text_sha256"], "source_sha256": v["source_sha256"],
                           **{k: meta[k] for k in meta if meta[k] is not None}},
        })
        if verify:
            check = self.verifier.verify_span(span_id)
            view["verified"] = check["verified"]
        return view

    def verify_span(self, span_id: int, deep: bool = False) -> dict:
        return self.verifier.verify_span(span_id, deep=deep)

    # ── 5. versions, contradictions, context (week 3) ────────────────────────

    def list_versions(self, doc: str) -> dict:
        v = self.version(doc)
        rows = self.conn.execute(
            """SELECT v.id, v.label, v.seq, v.format, v.source_sha256, v.text_sha256, v.parser_version,
                      v.ingested_at, v.origin, jsonb_array_length(v.page_map) AS pages,
                      (SELECT count(*) FROM sections s WHERE s.version_id = v.id) AS sections
               FROM versions v WHERE v.document_id = %s ORDER BY v.seq""",
            (v["document_id"],),
        ).fetchall()
        relations = self.conn.execute(
            """SELECT DISTINCT version_id, relation, target_rfc, target_version FROM refs
               WHERE relation IN ('obsoletes', 'updates') AND version_id = ANY(%s)""",
            ([r["id"] for r in rows],),
        ).fetchall()
        out = []
        for r in rows:
            out.append({
                "version_id": r["id"], "label": r["label"], "seq": r["seq"], "format": r["format"],
                "pages": r["pages"], "sections": r["sections"], "is_latest": r["id"] == v["latest_version"],
                "source_sha256": r["source_sha256"], "text_sha256": r["text_sha256"],
                "parser_version": r["parser_version"], "ingested_at": r["ingested_at"].isoformat(),
                "origin": r["origin"],
                "declares": [f"{x['relation']} RFC {x['target_rfc']}" for x in relations if x["version_id"] == r["id"]],
            })
        return {"document": v["document_id"], "append_only": True, "versions": out}

    def _version_pair(self, doc: str, from_version: str | None, to_version: str | None) -> tuple[dict, dict]:
        versions = self.list_versions(doc)["versions"]
        if len(versions) < 2 and not (from_version and to_version):
            raise NotFound(f"{doc} has only one version; nothing to diff")
        new = self.version(doc, to_version) if to_version else self.version(versions[-1]["version_id"])
        if from_version:
            old = self.version(doc, from_version)
        else:
            older = [x for x in versions if x["seq"] < new["seq"]]
            if not older:
                raise NotFound(f"{new['id']} is the first version; pass from_version explicitly")
            old = self.version(older[-1]["version_id"])
        return old, new

    def diff_versions(self, doc: str, from_version: str | None = None, to_version: str | None = None,
                      level: str = "section", max_tokens: int = 4000) -> dict:
        from docusense.versions import diff

        old, new = self._version_pair(doc, from_version, to_version)
        if level == "section":
            out = diff.diff_sections(self.conn, old["id"], new["id"])
            items, truncated = self._fit([s for s in out["sections"] if s["status"] != "unchanged"], max_tokens)
            out["sections"], out["truncated"] = items, truncated
            out["note"] = "unchanged sections omitted; see summary for counts"
        elif level == "claim":
            out = diff.diff_claims(self.conn, old["id"], new["id"])
            budget = max_tokens // 3
            for key in ("changed", "added", "removed"):
                out[key], cut = self._fit(out[key], budget)
                out["truncated"] = out.get("truncated", False) or cut
        elif level == "reference":
            out = diff.diff_references(self.conn, old["id"], new["id"])
        else:
            raise ValueError("level must be section, claim or reference")
        return out

    def blame(self, span_id: int | None = None, text: str | None = None, doc: str | None = None) -> dict:
        from docusense.versions.blame import blame

        if span_id is None:
            if not (text and doc):
                raise ValueError("give span_id, or text + doc")
            v = self.version(doc)
            row = self.conn.execute(
                """SELECT id FROM spans WHERE version_id = %s AND kind <> 'sentence'
                   AND regexp_replace(text, '\\s+', ' ', 'g') ILIKE %s ORDER BY length(text) LIMIT 1""",
                (v["id"], f"%{' '.join(text.split())}%"),
            ).fetchone()
            if row is None:
                raise NotFound(f"text not found in {v['id']}; use search to locate it first")
            span_id = row["id"]
        return blame(self.conn, span_id)

    def find_affected_documents(self, doc: str, max_tokens: int = 3000) -> dict:
        v = self.version(doc)
        rows = self.conn.execute(
            """SELECT r.version_id AS source_version, src.document_id AS source_doc, r.relation,
                      r.target_version, count(*) AS mentions,
                      array_agg(DISTINCT r.raw) AS raws, min(r.span_id) AS example_span
               FROM refs r JOIN versions src ON src.id = r.version_id
               WHERE r.target_doc = %s AND src.document_id <> %s
               GROUP BY 1, 2, 3, 4 ORDER BY 2, 1""",
            (v["document_id"], v["document_id"]),
        ).fetchall()
        latest = self._latest()
        items = []
        for r in rows:
            items.append({
                "source_version": r["source_version"],
                "source_is_latest": latest[r["source_doc"]]["id"] == r["source_version"],
                "relation": r["relation"], "cites_version": r["target_version"],
                "cites_obsolete_version": r["target_version"] != v["latest_version"],
                "mentions": r["mentions"], "examples": r["raws"][:4], "example_span_id": r["example_span"],
            })
        items.sort(key=lambda x: (not x["source_is_latest"], x["source_version"]))
        items, truncated = self._fit(items, max_tokens)
        return {"document": v["document_id"], "latest_version": v["latest_version"],
                "affected": items, "truncated": truncated,
                "note": "documents whose text references this document; review them when it changes"}

    def find_contradictions(self, doc: str | None = None, include_history: bool = False,
                            include_rejected: bool = False, k: int = 20, max_tokens: int = 4000) -> dict:
        where = ["TRUE"]
        params: list = []
        if not include_rejected:
            where.append("coalesce(f.details->>'status', '') <> 'rejected'")
        if not include_history:
            where.append("""ca.version_id IN (SELECT DISTINCT ON (document_id) id FROM versions ORDER BY document_id, seq DESC)
                            AND cb.version_id IN (SELECT DISTINCT ON (document_id) id FROM versions ORDER BY document_id, seq DESC)""")
        if doc:
            v = self.version(doc)
            where.append("(xa.document_id = %s OR xb.document_id = %s)")
            params += [v["document_id"], v["document_id"]]
        rows = self.conn.execute(
            f"""SELECT f.id, f.reason, f.confidence, f.method, f.details, ca.span_id AS span_a, cb.span_id AS span_b
                FROM conflicts f
                JOIN claims ca ON ca.id = f.claim_a JOIN claims cb ON cb.id = f.claim_b
                JOIN versions xa ON xa.id = ca.version_id JOIN versions xb ON xb.id = cb.version_id
                WHERE {' AND '.join(where)}
                ORDER BY (f.details->>'status' = 'confirmed') DESC, f.confidence DESC LIMIT %s""",
            tuple(params + [k]),
        ).fetchall()
        items = []
        for r in rows:
            a = self._span_view(self._spans("p.id = %s", (r["span_a"],))[0], 500)
            b = self._span_view(self._spans("p.id = %s", (r["span_b"],))[0], 500)
            details = r["details"] or {}
            items.append({"conflict_id": r["id"], "reason": r["reason"], "status": details.get("status", "candidate"),
                          "score": r["confidence"], "method": r["method"],
                          "judge": details.get("judge"), "a": a, "b": b})
        items, truncated = self._fit(items, max_tokens)
        return {"contradictions": items, "truncated": truncated,
                "note": "both sides are kept as evidence; DocuSense never picks a winner"}

    def assemble_context(self, span_ids: list[int], token_budget: int = 4000) -> dict:
        from docusense.context.assemble import assemble_context

        return assemble_context(self, span_ids, token_budget)

    # ── 6. viewer helpers (REST API only) ────────────────────────────────────

    def version_document(self, version_id: str) -> dict:
        v = self.version(version_id)
        sections = self.conn.execute(
            """SELECT id, parent_id, number, title, level, page_start, page_end FROM sections
               WHERE version_id = %s ORDER BY ordinal""", (v["id"],)
        ).fetchall()
        spans = self.conn.execute(
            """SELECT id, section_id, kind, page, start_byte, end_byte, sha256, text FROM spans
               WHERE version_id = %s AND kind <> 'sentence' ORDER BY ordinal""", (v["id"],)
        ).fetchall()
        doc = self.conn.execute("SELECT title, source_family FROM documents WHERE id = %s", (v["document_id"],)).fetchone()
        versions = self.conn.execute(
            "SELECT id, label, seq FROM versions WHERE document_id = %s ORDER BY seq", (v["document_id"],)
        ).fetchall()
        return {"version_id": v["id"], "document": v["document_id"], "title": doc["title"],
                "family": doc["source_family"], "label": v["label"], "format": v["format"],
                "is_latest": v["is_latest"], "latest_version": v["latest_version"],
                "pages": len(v["page_map"]), "text_sha256": v["text_sha256"], "source_sha256": v["source_sha256"],
                "parser_version": v["parser_version"], "versions": versions,
                "sections": sections, "spans": spans}
