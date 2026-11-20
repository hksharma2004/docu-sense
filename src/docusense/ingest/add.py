"""add user documents without a manifest.

each file becomes a document (id from the file name unless given). changed bytes append a
new version (v1, v2, ...), so diff / blame / contradictions work on plain files that change
over time. identical bytes are a no-op.
"""

import re
from dataclasses import dataclass
from pathlib import Path

from docusense.db.conn import Database
from docusense.ingest.pipeline import FORMAT_BY_SUFFIX, IngestResult, ingest_version
from docusense.store.blobs import BlobStore, sha256_hex

USER_FAMILY = "user"


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "document"


def collect_files(paths: list[Path], recursive: bool = True) -> list[Path]:
    """expand folders into supported files (sorted, hidden files skipped)"""
    out: list[Path] = []
    for p in paths:
        if p.is_dir():
            pattern = "**/*" if recursive else "*"
            out += sorted(
                f for f in p.glob(pattern)
                if f.is_file() and f.suffix.lstrip(".").lower() in FORMAT_BY_SUFFIX
                and not any(part.startswith(".") for part in f.relative_to(p).parts)
            )
        elif p.is_file():
            out.append(p)
        else:
            raise FileNotFoundError(f"no such file or folder: {p}")
    return out


@dataclass
class AddResult(IngestResult):
    document_id: str = ""
    note: str = ""


def add_file(conn: Database, path: Path, doc: str | None = None, title: str | None = None,
             label: str | None = None, store: BlobStore | None = None) -> AddResult:
    path = path.expanduser().resolve()
    document_id = slugify(doc or path.stem)
    source_sha = sha256_hex(path.read_bytes())

    same = conn.execute("SELECT id, document_id FROM versions WHERE source_sha256 = %s", (source_sha,)).fetchone()
    if same:
        conn.rollback()
        note = "" if same["document_id"] == document_id else f"identical bytes already stored as {same['id']}"
        return AddResult(same["id"], "skipped", document_id=same["document_id"], note=note)

    existing = conn.execute("SELECT title FROM documents WHERE id = %s", (document_id,)).fetchone()
    seq = conn.execute(
        "SELECT coalesce(max(seq), 0) + 1 AS n FROM versions WHERE document_id = %s", (document_id,)
    ).fetchone()["n"]
    label = slugify(label) if label else f"v{seq}"
    if conn.execute("SELECT 1 FROM versions WHERE id = %s", (f"{document_id}@{label}",)).fetchone():
        conn.rollback()
        raise ValueError(f"{document_id}@{label} already exists with different content; choose another label")
    conn.rollback()

    result = ingest_version(
        conn,
        document_id=document_id,
        title=(existing["title"] if existing else None) or title or path.stem,
        family=USER_FAMILY,
        label=label,
        seq=seq,
        path=path,
        origin={"path": str(path), "added_by": "docusense add"},
        store=store,
    )
    return AddResult(**vars(result), document_id=document_id,
                     note="new version of existing document" if existing and result.status == "ingested" else "")


def refresh_derived(conn: Database, index: bool = True, progress=None) -> dict:
    """re-run extraction, contradiction detection and indexing after an add.

    extraction runs over every version so references *into* the new doc resolve too.
    """
    from docusense.extract.run import extract_all
    from docusense.versions.conflicts import detect

    stats = {"extracted_versions": len(extract_all(conn))}
    stats["conflicts"] = detect(conn)["candidates"]
    if index:
        from docusense.index import bm25, embed

        stats["bm25_spans"] = bm25.build(conn)
        stats["embedded"] = embed.build(conn, progress=progress)
    return stats
