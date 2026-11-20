"""`docusense add`: manifest-free ingest with automatic versioning"""

import pytest

from docusense.ingest.add import add_file, collect_files, refresh_derived, slugify
from docusense.services import DocuSense

V1 = b"# Leave Policy\n\n## 1. Annual leave\n\nEmployees MUST NOT carry over more than 5 days.\n"
V2 = b"# Leave Policy\n\n## 1. Annual leave\n\nEmployees MUST NOT carry over more than 10 days.\n"


def test_slugify():
    assert slugify("Employee Handbook (2026).pdf") == "employee-handbook-2026-pdf"
    assert slugify("***") == "document"


def test_add_versions_skip_and_diff(conn, store, tmp_path, monkeypatch):
    f = tmp_path / "Leave Policy.md"
    f.write_bytes(V1)
    r1 = add_file(conn, f, store=store)
    assert (r1.version_id, r1.status) == ("leave-policy@v1", "ingested")

    assert add_file(conn, f, store=store).status == "skipped"  # same bytes → no-op

    f.write_bytes(V2)
    r2 = add_file(conn, f, store=store)
    assert (r2.version_id, r2.status) == ("leave-policy@v2", "ingested")
    assert r2.note == "new version of existing document"

    from docusense.index import bm25
    monkeypatch.setattr(bm25, "index_dir", lambda: tmp_path / "bm25")
    refresh_derived(conn, index=False)
    bm25.build(conn)

    ds = DocuSense(conn)
    ds.verifier.store = store
    assert ds.version("leave-policy")["id"] == "leave-policy@v2"
    diff = ds.diff_versions("leave-policy", level="claim")
    assert diff["changed"] or (diff["added"] and diff["removed"])
    assert ds.verifier.verify_all()["verified"] > 0


def test_add_label_conflict_and_unsupported(conn, store, tmp_path):
    a = tmp_path / "a.md"
    a.write_bytes(V1)
    add_file(conn, a, label="2026", store=store)
    a.write_bytes(V2)
    with pytest.raises(ValueError, match="already exists"):
        add_file(conn, a, label="2026", store=store)
    bad = tmp_path / "x.pages"
    bad.write_bytes(b"PK")
    with pytest.raises(ValueError, match="unsupported"):
        add_file(conn, bad, store=store)


def test_collect_files(tmp_path):
    (tmp_path / "sub").mkdir()
    (tmp_path / ".hidden").mkdir()
    for name in ("a.md", "sub/b.pdf", "sub/c.txt", "d.pages", ".hidden/e.md"):
        (tmp_path / name).write_bytes(b"x")
    assert [p.relative_to(tmp_path).as_posix() for p in collect_files([tmp_path])] == ["a.md", "sub/b.pdf", "sub/c.txt"]
