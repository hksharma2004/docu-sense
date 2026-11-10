import pytest

from docusense.ingest.pipeline import ingest_version
from docusense.provenance import Verifier

DOC = b"""# Test Policy

## 1. Scope

Servers MUST accept at least 100 recipients.

## 2. Limits

Lines MUST NOT exceed 1000 octets.
"""


@pytest.fixture
def ingested(conn, store, tmp_path):
    path = tmp_path / "policy.md"
    path.write_bytes(DOC)
    result = ingest_version(conn, document_id="policy", title="Test Policy", family="synthetic",
                            label="v1", seq=1, path=path, store=store)
    assert result.status == "ingested"
    return result, path


def test_all_spans_verify(conn, store, ingested):
    report = Verifier(conn, store).verify_all(deep=True)
    assert report["total"] > 0 and report["verified"] == report["total"]


def test_reingest_is_skipped(conn, store, ingested):
    _, path = ingested
    again = ingest_version(conn, document_id="policy", title="Test Policy", family="synthetic",
                           label="v1", seq=1, path=path, store=store)
    assert again.status == "skipped"


def test_tampered_blob_fails_verification(conn, store, ingested):
    version = conn.execute("SELECT text_sha256 FROM versions WHERE id = 'policy@v1'").fetchone()
    span = conn.execute(
        "SELECT id, start_byte FROM spans WHERE text LIKE '%%1000 octets%%'"
    ).fetchone()

    blob_path = store.path_for(version["text_sha256"])
    data = bytearray(blob_path.read_bytes())
    pos = data.index(b"1000", span["start_byte"])
    data[pos:pos + 4] = b"9000"  # poison the evidence
    blob_path.write_bytes(bytes(data))

    result = Verifier(conn, store).verify_span(span["id"])
    assert result["verified"] is False
    assert result["hash_match"] is False
    assert result["blob_intact"] is False

    other = conn.execute("SELECT id FROM spans WHERE text LIKE '%%100 recipients%%'").fetchone()
    other_result = Verifier(conn, store).verify_span(other["id"])
    assert other_result["verified"] is True  # untouched span still verifies
    assert other_result["blob_intact"] is False  # but the blob as a whole is flagged


def test_spans_are_append_only(conn, ingested):
    with pytest.raises(Exception, match="append-only"):
        conn.execute("UPDATE spans SET text = 'forged' WHERE id = (SELECT min(id) FROM spans)")
    conn.rollback()
    with pytest.raises(Exception, match="append-only"):
        conn.execute("DELETE FROM versions")
    conn.rollback()
