"""ingest one version: parse -> canonical text blob -> sections + spans, in one transaction"""

from dataclasses import dataclass
from pathlib import Path

from docusense.db.conn import Database

from docusense.config import PARSER_VERSION
from docusense.ingest.md_parser import parse_markdown
from docusense.ingest.model import ParsedDoc
from docusense.ingest.pdf_parser import parse_pdf
from docusense.ingest.sections import build_sections
from docusense.store.blobs import BlobStore, sha256_hex


# file suffix -> stored format. plain text goes through the markdown parser (no headings)
FORMAT_BY_SUFFIX = {"pdf": "pdf", "md": "md", "markdown": "md", "txt": "md",
                    "docx": "docx", "html": "html", "htm": "html"}


def format_for(path: Path) -> str:
    fmt = FORMAT_BY_SUFFIX.get(path.suffix.lstrip(".").lower())
    if fmt is None:
        raise ValueError(f"unsupported file type {path.suffix!r} (supported: {', '.join(sorted(FORMAT_BY_SUFFIX))})")
    return fmt


def parse_source(fmt: str, data: bytes) -> ParsedDoc:
    if fmt == "pdf":
        return parse_pdf(data)
    if fmt == "md":
        return parse_markdown(data)
    if fmt in ("docx", "html"):
        from docusense.ingest.convert import docx_to_markdown, html_to_markdown

        markdown = docx_to_markdown(data) if fmt == "docx" else html_to_markdown(data)
        doc = parse_markdown(markdown.encode("utf-8"))
        doc.layout = fmt
        return doc
    raise ValueError(f"unsupported format: {fmt}")


@dataclass
class IngestResult:
    version_id: str
    status: str  # ingested | skipped
    sections: int = 0
    spans: int = 0
    pages: int = 0
    layout: str = ""


def ingest_version(
    conn: Database,
    *,
    document_id: str,
    title: str,
    family: str,
    label: str,
    seq: int,
    path: Path,
    origin: dict | None = None,
    store: BlobStore | None = None,
) -> IngestResult:
    store = store or BlobStore()
    version_id = f"{document_id}@{label}"
    fmt = format_for(path)
    source = path.read_bytes()
    source_sha = sha256_hex(source)

    existing = conn.execute(
        "SELECT id FROM versions WHERE source_sha256 = %s OR id = %s", (source_sha, version_id)
    ).fetchone()
    conn.rollback()  # close the implicit read txn so the block below is a real transaction
    if existing:
        return IngestResult(existing["id"], "skipped")

    doc = parse_source(fmt, source)
    data = doc.data
    store.put(source)
    text_sha = store.put(data)
    sections = build_sections(doc)

    with conn.transaction():
        conn.execute(
            """INSERT INTO documents (id, title, source_family) VALUES (%s, %s, %s)
               ON CONFLICT (id) DO NOTHING""",
            (document_id, title, family),
        )
        conn.execute(
            """INSERT INTO versions (id, document_id, label, seq, format, source_path, source_sha256,
                                     text_sha256, text_bytes, page_map, parser_version, origin)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (version_id, document_id, label, seq, fmt, str(path), source_sha, text_sha, len(data),
             conn.json(doc.page_starts), PARSER_VERSION, conn.json(origin or {})),
        )

        ids_by_ordinal: dict[int, int] = {}
        for s in sections:
            row = conn.execute(
                """INSERT INTO sections (version_id, parent_id, number, title, level, ordinal,
                                         start_byte, end_byte, page_start, page_end, sha256)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
                (version_id, ids_by_ordinal.get(s["parent_ordinal"]), s["number"], s["title"],
                 s["level"], s["ordinal"], s["start_byte"], s["end_byte"], s["page_start"],
                 s["page_end"], sha256_hex(data[s["start_byte"]:s["end_byte"]])),
            ).fetchone()
            ids_by_ordinal[s["ordinal"]] = row["id"]

        span_rows = []
        for ordinal, b in enumerate(doc.blocks):
            chunk = data[b.start:b.end]
            if not chunk.strip():
                continue
            section = _innermost(sections, b.start)
            span_rows.append((
                version_id, ids_by_ordinal.get(section["ordinal"]) if section else None, b.kind,
                ordinal, b.start, b.end, doc.page_of(b.start), sha256_hex(chunk),
                chunk.decode("utf-8"), PARSER_VERSION, "layout",
            ))
        conn.executemany(
            """INSERT INTO spans (version_id, section_id, kind, ordinal, start_byte, end_byte,
                                  page, sha256, text, parser_version, extraction_method)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            span_rows,
        )

    return IngestResult(version_id, "ingested", len(sections), len(span_rows),
                        len(doc.page_starts), doc.layout)


def _innermost(sections: list[dict], offset: int) -> dict | None:
    best = None
    for s in sections:
        if s["start_byte"] <= offset < max(s["end_byte"], s["start_byte"] + 1):
            if best is None or s["start_byte"] >= best["start_byte"]:
                best = s
    return best
