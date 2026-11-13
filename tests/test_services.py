"""Integration: ingest two linked documents, extract, build BM25, query through the service layer."""

import pytest

from docusense.extract.run import extract_all
from docusense.ingest.pipeline import ingest_version
from docusense.services import DocuSense, NotFound

DOC_A = b"""# Alpha Protocol

## 1. Terminology

"Widget" means a unit of transfer between peers.

## 2. Transfer

Senders MUST NOT transmit a widget larger than 512 octets. Receivers SHOULD reject larger widgets
as described in Section 3 of [RFC9002]. See also Section 2.1.

### 2.1 Retries

A sender MAY retry after 30 seconds.

## 3. References

[RFC9002] Example, "Beta Protocol", RFC 9002, January 2026.
"""

DOC_B_V1 = b"""# Beta Protocol

## 1. Overview

Beta carries widgets.

## 3. Rejection

Receivers reject oversized widgets with error code 7.
"""

DOC_B_V2 = b"""# Beta Protocol

## 1. Overview

Beta carries widgets over secure channels.

## 3. Rejection

Receivers MUST reject oversized widgets with error code 9.
"""


@pytest.fixture
def ds(conn, store, tmp_path, monkeypatch):
    for name, data in {"a.md": DOC_A, "b1.md": DOC_B_V1, "b2.md": DOC_B_V2}.items():
        (tmp_path / name).write_bytes(data)
    ingest_version(conn, document_id="alpha", title="Alpha", family="synthetic", label="rfc9001", seq=1,
                   path=tmp_path / "a.md", store=store)
    ingest_version(conn, document_id="beta", title="Beta", family="synthetic", label="v1", seq=1,
                   path=tmp_path / "b1.md", store=store)
    ingest_version(conn, document_id="beta", title="Beta", family="synthetic", label="rfc9002", seq=2,
                   path=tmp_path / "b2.md", store=store)
    extract_all(conn)

    from docusense.index import bm25
    monkeypatch.setattr(bm25, "index_dir", lambda: tmp_path / "bm25")
    bm25.build(conn)
    service = DocuSense(conn)
    service.verifier.store = store
    return service


def test_version_resolution(ds):
    assert ds.version("beta")["id"] == "beta@rfc9002"
    assert ds.version("beta", "v1")["is_latest"] is False
    assert ds.version("RFC 9001")["id"] == "alpha@rfc9001"
    with pytest.raises(NotFound):
        ds.version("gamma")


def test_section_map_and_read(ds):
    m = ds.get_section_map("alpha")
    assert [s["number"] for s in m["sections"]] == [None, "1", "2", "2.1", "3"]
    sec = ds.read_section("alpha", "2")
    assert sec["subsections"] == ["2.1 Retries"]
    assert sec["spans"][0]["citation"].startswith("ds://alpha@rfc9001#§2:b")


def test_references_resolve_across_documents(ds):
    span = ds.read_section("alpha", "2")["spans"][0]
    refs = {(r["target_version"], r["target_section"], r["status"])
            for r in ds.resolve_reference(span_id=span["span_id"])["references"]}
    assert ("beta@rfc9002", "3", "resolved") in refs
    assert ("alpha@rfc9001", "2.1", "resolved") in refs


def test_reference_to_old_version_flags_newer(ds):
    out = ds.resolve_reference(reference="Section 3 of RFC 9002", doc="alpha")
    assert out["references"][0]["target_is_latest"] is True
    assert out["references"][0]["preview"][0]["text"].startswith("Receivers MUST reject")


def test_definition_and_claims(ds):
    d = ds.lookup_definition("widget")
    assert d["results"][0]["term"] == "Widget" and d["results"][0]["exact"]
    claims = ds.search_claims(topic="widget larger", modality="MUST NOT")["results"]
    assert claims and claims[0]["claim"]["value"] == 512 and claims[0]["claim"]["unit"] == "octet"
    assert claims[0]["kind"] == "sentence"


def test_lexical_search_and_doc_filter(ds):
    hits = ds.search("oversized widgets error code", mode="lexical", k=5)["results"]
    assert {h["version"] for h in hits} >= {"beta@rfc9002", "beta@v1"}
    old = next(h for h in hits if h["version"] == "beta@v1")
    assert old["newer_version"] == "beta@rfc9002"
    only_latest = ds.search("oversized widgets error code", mode="lexical", doc="beta@rfc9002")["results"]
    assert {h["version"] for h in only_latest} == {"beta@rfc9002"}


def test_evidence_is_verified(ds):
    span = ds.read_section("alpha", "2.1")["spans"][0]
    ev = ds.get_evidence(span["span_id"])
    assert ev["verified"] is True
    assert ev["section_path"] == ["2 Transfer", "2.1 Retries"]
    assert len(ev["provenance"]["sha256"]) == 64 and "sha256" not in span  # hash lives in evidence, not every hit


def test_sentence_spans_verify_and_reextract_is_idempotent(conn, ds):
    before = conn.execute("SELECT count(*) AS n FROM spans WHERE kind = 'sentence'").fetchone()["n"]
    extract_all(conn)
    after = conn.execute("SELECT count(*) AS n FROM spans WHERE kind = 'sentence'").fetchone()["n"]
    assert before == after > 0
    report = ds.verifier.verify_all()
    assert report["verified"] == report["total"]


def test_budget_truncation(ds):
    out = ds.get_section_map("alpha", max_tokens=20)
    assert out["truncated"] is True and len(out["sections"]) >= 1


# ── week 3 tools (exercised on every backend) ──────────────────────────────────

def test_list_versions_and_diff(ds):
    versions = ds.list_versions("beta")["versions"]
    assert [v["version_id"] for v in versions] == ["beta@v1", "beta@rfc9002"]
    assert versions[-1]["is_latest"] and isinstance(versions[0]["ingested_at"], str)
    assert versions[0]["pages"] >= 1

    sections = ds.diff_versions("beta", level="section")
    assert sections["from"] == "beta@v1" and sections["to"] == "beta@rfc9002"
    assert any(s["status"] != "unchanged" for s in sections["sections"])

    claims = ds.diff_versions("beta", level="claim")
    assert claims["added"] or claims["changed"]
    ds.diff_versions("beta", level="reference")


def test_blame_finds_origin(ds):
    span = ds.read_section("beta", "1")["spans"][0]
    out = ds.blame(span_id=span["span_id"])
    assert out
    by_text = ds.blame(text="Beta carries widgets over secure", doc="beta")
    assert by_text


def test_affected_documents_and_contradictions(ds, conn):
    affected = ds.find_affected_documents("beta")["affected"]
    assert any(a["source_version"] == "alpha@rfc9001" and a["examples"] for a in affected)

    from docusense.versions.conflicts import detect
    detect(conn)
    out = ds.find_contradictions(include_history=True)
    assert "contradictions" in out
    for item in out["contradictions"]:
        assert item["a"]["citation"].startswith("ds://") and item["status"] == "candidate"


def test_assemble_context_and_viewer_document(ds):
    span = ds.read_section("alpha", "2")["spans"][0]
    ctx = ds.assemble_context([span["span_id"]], token_budget=2000)
    assert ctx
    doc = ds.version_document("alpha@rfc9001")
    assert doc["pages"] >= 1 and doc["spans"] and doc["sections"]


def test_semantic_search(ds, conn, tmp_path, monkeypatch):
    """Semantic + hybrid search with a deterministic fake embedder (no model download)."""
    import hashlib

    import numpy as np

    from docusense.index import embed

    def fake(text: str) -> np.ndarray:
        vec = np.zeros(64, dtype=np.float32)
        for word in text.lower().split():
            vec[int(hashlib.md5(word.strip(".,:\"'").encode()).hexdigest(), 16) % 64] += 1
        return vec

    monkeypatch.setattr(embed, "embed_texts", lambda texts: [fake(t) for t in texts])
    monkeypatch.setattr(embed, "embed_query", fake)
    monkeypatch.setattr(embed.EmbeddingCache, "save", lambda self: None)
    if conn.dialect == "postgres":
        pytest.skip("pgvector column is fixed at 384 dims; fake embedder is 64")
    assert embed.build(conn) > 0
    hits = ds.search("secure channels widgets", mode="semantic", k=3)["results"]
    assert hits and hits[0]["version"] == "beta@rfc9002"
    assert ds.search("secure channels widgets", mode="hybrid", k=3)["results"]
