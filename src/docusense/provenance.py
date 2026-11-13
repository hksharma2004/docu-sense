"""Provenance verification: a span is trusted only if its bytes still hash to the stored SHA-256.

verify_span(deep=False): canonical-text blob → slice [start, end) → sha256 == stored hash,
                         and the stored text equals the slice.
verify_span(deep=True):  additionally re-parses the original source file and checks that the
                         parser still produces the same canonical text (determinism check).
"""

from collections import defaultdict

from docusense.db.conn import Database

from docusense.config import PARSER_VERSION
from docusense.store.blobs import BlobStore, sha256_hex

_SPAN_SQL = """
SELECT s.id, s.version_id, s.start_byte, s.end_byte, s.sha256, s.text, s.parser_version,
       v.text_sha256, v.source_sha256, v.format
FROM spans s JOIN versions v ON v.id = s.version_id
"""


class Verifier:
    def __init__(self, conn: Database, store: BlobStore | None = None):
        self.conn = conn
        self.store = store or BlobStore()
        self._text_cache: dict[str, bytes | None] = {}
        self._deep_cache: dict[str, dict] = {}

    def _text(self, digest: str) -> bytes | None:
        if digest not in self._text_cache:
            try:
                self._text_cache[digest] = self.store.get(digest)
            except FileNotFoundError:
                self._text_cache[digest] = None
        return self._text_cache[digest]

    def deep_check(self, version_id: str) -> dict:
        """Re-run the parser on the stored source file and compare canonical-text hashes."""
        if version_id in self._deep_cache:
            return self._deep_cache[version_id]
        from docusense.ingest.pipeline import parse_source

        v = self.conn.execute(
            "SELECT source_sha256, text_sha256, format, parser_version FROM versions WHERE id = %s",
            (version_id,),
        ).fetchone()
        result = {"source_intact": False, "reparse_match": False,
                  "parser_version": PARSER_VERSION, "stored_parser_version": v["parser_version"]}
        try:
            source = self.store.get(v["source_sha256"])
        except FileNotFoundError:
            result["error"] = "source blob missing"
        else:
            result["source_intact"] = sha256_hex(source) == v["source_sha256"]
            if result["source_intact"]:
                reparsed = sha256_hex(parse_source(v["format"], source).data)
                result["reparse_match"] = reparsed == v["text_sha256"]
        self._deep_cache[version_id] = result
        return result

    def verify_row(self, row: dict, deep: bool = False) -> dict:
        blob = self._text(row["text_sha256"])
        result = {
            "span_id": row["id"],
            "version_id": row["version_id"],
            "start_byte": row["start_byte"],
            "end_byte": row["end_byte"],
            "stored_sha256": row["sha256"],
            "parser_version": row["parser_version"],
        }
        if blob is None:
            return result | {"verified": False, "error": "canonical text blob missing"}

        chunk = blob[row["start_byte"]:row["end_byte"]]
        recomputed = sha256_hex(chunk)
        result |= {
            "recomputed_sha256": recomputed,
            "hash_match": recomputed == row["sha256"],
            "text_match": chunk.decode("utf-8", errors="replace") == row["text"],
            "blob_intact": sha256_hex(blob) == row["text_sha256"],
        }
        result["verified"] = result["hash_match"] and result["text_match"]
        if deep:
            check = self.deep_check(row["version_id"])
            result["deep"] = check
            result["verified"] = result["verified"] and check["reparse_match"]
        return result

    def verify_span(self, span_id: int, deep: bool = False) -> dict:
        row = self.conn.execute(_SPAN_SQL + " WHERE s.id = %s", (span_id,)).fetchone()
        if row is None:
            return {"span_id": span_id, "verified": False, "error": "span not found"}
        return self.verify_row(row, deep)

    def verify_all(self, deep: bool = False, version_id: str | None = None) -> dict:
        sql, params = _SPAN_SQL, ()
        if version_id:
            sql, params = sql + " WHERE s.version_id = %s", (version_id,)
        per_version: dict[str, dict] = defaultdict(lambda: {"total": 0, "verified": 0, "failed": []})
        for row in self.conn.execute(sql + " ORDER BY s.id", params):
            r = self.verify_row(row, deep)
            stats = per_version[row["version_id"]]
            stats["total"] += 1
            if r["verified"]:
                stats["verified"] += 1
            else:
                stats["failed"].append(row["id"])
        total = sum(s["total"] for s in per_version.values())
        verified = sum(s["verified"] for s in per_version.values())
        return {"total": total, "verified": verified, "versions": dict(per_version)}
