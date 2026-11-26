"""cold compaction: old versions lose their source file and embeddings, never their evidence"""

import hashlib
from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from docusense.config import get_settings
from docusense.ingest.add import add_file, refresh_derived
from docusense.provenance import Verifier
from docusense.services import DocuSense
from docusense.versions import compact as c


def html(n: int) -> bytes:
    return (f"<html><body><h1>Leave Policy</h1><h2>1. Annual leave</h2>"
            f"<p>Employees MUST NOT carry over more than {n} days.</p>"
            f"<h2>2. Sick leave</h2><p>Sick leave SHALL be paid in full.</p></body></html>").encode()


@pytest.fixture
def isolated(monkeypatch, tmp_path):
    """keep the embedding cache and retention setting away from the user's real home"""
    monkeypatch.setattr(get_settings(), "store_dir", tmp_path / "store")
    monkeypatch.setattr(get_settings(), "retain", "")


def fake_embed(conn):
    rows = conn.execute("SELECT id FROM spans").fetchall()
    conn.executemany(
        "INSERT INTO span_embeddings (span_id, model, embedding) VALUES (%s, %s, %s)",
        [(r["id"], get_settings().embed_model, np.ones(4, dtype="<f4").tobytes()) for r in rows],
    )
    conn.commit()


@pytest.fixture
def three_versions(conn, store, tmp_path, isolated):
    if conn.dialect != "sqlite":
        pytest.skip("fake embeddings are sqlite blobs")
    f = tmp_path / "leave.html"
    for n in (5, 10, 15):
        f.write_bytes(html(n))
        assert add_file(conn, f, store=store).status == "ingested"
    fake_embed(conn)
    return f


def emb_count(conn, version_id):
    return conn.execute(
        "SELECT count(*) AS n FROM span_embeddings e JOIN spans p ON p.id = e.span_id WHERE p.version_id = %s",
        (version_id,),
    ).fetchone()["n"]


def source_of(conn, version_id):
    return conn.execute("SELECT source_sha256, text_sha256 FROM versions WHERE id = %s", (version_id,)).fetchone()


# ── merkle ──

def test_merkle_root_rfc6962():
    assert c.merkle_root([]) == hashlib.sha256(b"").hexdigest()
    h = hashlib.sha256(b"a").hexdigest()
    assert c.merkle_root([h]) == hashlib.sha256(b"\x00" + bytes.fromhex(h)).hexdigest()
    hs = [hashlib.sha256(bytes([i])).hexdigest() for i in range(5)]
    assert c.merkle_root(hs) != c.merkle_root(hs[::-1])  # order matters
    assert c.merkle_root(hs) != c.merkle_root(hs + hs[-1:])  # no duplicate-last-leaf collision


# ── policy ──

def test_parse_policy():
    p = c.parse_policy("keep-last=3, older-than=12w")
    assert (p.keep_last, p.older_than_days) == (3, 84)
    assert c.parse_policy("older-than=1y").older_than_days == 365
    for bad in ("", "keep-last=0", "older-than=soon", "max=4"):
        with pytest.raises(ValueError):
            c.parse_policy(bad)


def test_select_is_and_and_skips_latest():
    now = datetime(2026, 11, 1, tzinfo=UTC)
    usage = [  # newest first, as versions_usage returns them
        {"version_id": f"d@v{i}", "document_id": "d", "is_latest": i == 4, "compaction": None,
         "ingested_at": now - timedelta(days=age)}
        for i, age in ((4, 1), (3, 200), (2, 10), (1, 300))
    ]
    pick = lambda **kw: [v["version_id"] for v in c.select(usage, c.Policy(**kw), now)]
    assert pick(keep_last=2) == ["d@v2", "d@v1"]
    assert pick(older_than_days=100) == ["d@v3", "d@v1"]
    assert pick(keep_last=2, older_than_days=100) == ["d@v1"]
    assert "d@v4" not in pick(keep_last=1, older_than_days=0)


# ── end to end ──

def test_compact_frees_space_and_keeps_evidence(conn, store, three_versions):
    plan = c.compact(conn, c.Policy(keep_last=1), store, dry_run=True)
    assert [v["version_id"] for v in plan.versions] == ["leave@v2", "leave@v1"]
    assert emb_count(conn, "leave@v1") > 0  # dry run changed nothing

    done = c.compact(conn, c.Policy(keep_last=1), store)
    assert done.bytes_freed > 0
    for vid in ("leave@v1", "leave@v2"):
        assert emb_count(conn, vid) == 0
        v = source_of(conn, vid)
        assert not store.exists(v["source_sha256"])
        assert store.exists(v["text_sha256"])
    assert emb_count(conn, "leave@v3") > 0
    assert store.exists(source_of(conn, "leave@v3")["source_sha256"])

    # every citation still verifies; deep check is skipped, not failed, on compacted versions
    verifier = Verifier(conn, store)
    report = verifier.verify_all()
    assert report["total"] > 0 and report["verified"] == report["total"]
    old_span = conn.execute("SELECT id FROM spans WHERE version_id = 'leave@v1' LIMIT 1").fetchone()["id"]
    deep = verifier.verify_span(old_span, deep=True)
    assert deep["verified"] and "skipped" in deep["deep"]

    # the record pins the span set
    row = conn.execute("SELECT * FROM compactions WHERE version_id = 'leave@v1'").fetchone()
    assert (row["spans_root"], row["span_count"]) == c.spans_root(conn, "leave@v1")

    ds = DocuSense(conn)
    ds.verifier.store = store
    ev = ds.get_evidence(old_span)
    assert ev["verified"] and ev["compaction"]["level"] == "cold"
    assert {v["version_id"]: "compaction" in v for v in ds.list_versions("leave")["versions"]} == {
        "leave@v1": True, "leave@v2": True, "leave@v3": False}
    assert ds.diff_versions("leave", "v1", "v3")  # diff still reads compacted versions


def test_compaction_is_idempotent_and_append_only(conn, store, three_versions):
    c.compact(conn, c.Policy(keep_last=1), store)
    assert c.compact(conn, c.Policy(keep_last=1), store).versions == []
    assert c.compact_version(conn, "leave@v1", store)["status"] == "already compacted"
    with pytest.raises(ValueError, match="latest"):
        c.compact_version(conn, "leave@v3", store)
    with pytest.raises(Exception, match="append-only"):
        conn.execute("DELETE FROM compactions WHERE version_id = 'leave@v1'")
    conn.rollback()


def test_embedding_backfill_skips_compacted(conn, store, three_versions, monkeypatch):
    from docusense.index import embed

    c.compact(conn, c.Policy(keep_last=1), store)
    monkeypatch.setattr(embed, "embed_texts", lambda texts: [np.ones(4, dtype=np.float32) for _ in texts])
    embed.build(conn)
    assert emb_count(conn, "leave@v1") == 0


def test_markdown_source_shared_with_text_is_kept(conn, store, tmp_path, isolated):
    f = tmp_path / "notes.md"
    for body in (b"# Notes\n\nFirst draft.\n", b"# Notes\n\nSecond draft.\n"):
        f.write_bytes(body)
        add_file(conn, f, store=store)
    v1 = source_of(conn, "notes@v1")
    c.compact(conn, c.Policy(keep_last=1), store)
    assert store.exists(v1["text_sha256"])
    assert Verifier(conn, store).verify_all()["verified"] == Verifier(conn, store).verify_all()["total"]


def test_retain_setting_compacts_after_add(conn, tmp_path, isolated, monkeypatch):
    from docusense.store.blobs import BlobStore

    monkeypatch.setattr(get_settings(), "retain", "keep-last=1")
    f = tmp_path / "leave.html"
    for n in (5, 10):
        f.write_bytes(html(n))
        add_file(conn, f)  # default store, under the isolated store_dir
    stats = refresh_derived(conn, index=False)
    assert not BlobStore().exists(source_of(conn, "leave@v1")["source_sha256"])
    assert stats["compacted"] == 1
    assert conn.execute("SELECT version_id FROM compactions").fetchall() == [{"version_id": "leave@v1"}]
