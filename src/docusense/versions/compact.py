"""compaction: free disk from old versions without losing evidence.

history is append-only, so every changed file adds a version and disk use only grows.
compaction trades bulk for nothing an agent needs to cite:

level 'cold' (this module): delete the original source file (pdf/docx/...) and the span
embeddings of an old version. the canonical text blob and the span text stay, so every
citation into that version still verifies byte-for-byte; only `verify --deep` (re-parse the
original file) is no longer possible. bm25 search, read_section, diff and blame keep working.

each compaction appends a row to `compactions` with an RFC 6962 merkle root over the
version's span hashes, so the set of spans that existed is pinned in 64 hex chars.

the latest version of a document is never compacted.
"""

import hashlib
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from docusense.db.conn import Database
from docusense.index.bm25 import INDEX_KINDS
from docusense.store.blobs import BlobStore

COLD = "cold"


# ── merkle root (RFC 6962 §2.1) ──────────────────────────────────────────────

def _leaf(h: bytes) -> bytes:
    return hashlib.sha256(b"\x00" + h).digest()


def _node(left: bytes, right: bytes) -> bytes:
    return hashlib.sha256(b"\x01" + left + right).digest()


def _mth(leaves: list[bytes]) -> bytes:
    if len(leaves) == 1:
        return _leaf(leaves[0])
    k = 1 << ((len(leaves) - 1).bit_length() - 1)  # largest power of two < n
    return _node(_mth(leaves[:k]), _mth(leaves[k:]))


def merkle_root(hex_hashes: list[str]) -> str:
    """root over hex sha256 leaves, in the given order. domain-separated leaves/nodes,
    so a leaf can't be passed off as an inner node (no duplicate-last-leaf ambiguity)."""
    if not hex_hashes:
        return hashlib.sha256(b"").hexdigest()
    return _mth([bytes.fromhex(h) for h in hex_hashes]).hex()


def spans_root(conn: Database, version_id: str) -> tuple[str, int]:
    hashes = [r["sha256"] for r in conn.execute(
        "SELECT sha256 FROM spans WHERE version_id = %s ORDER BY id", (version_id,))]
    return merkle_root(hashes), len(hashes)


# ── policy ───────────────────────────────────────────────────────────────────

@dataclass
class Policy:
    keep_last: int | None = None        # keep the newest N versions of each document
    older_than_days: int | None = None  # only versions ingested more than N days ago

    def __post_init__(self) -> None:
        if self.keep_last is None and self.older_than_days is None:
            raise ValueError("a retention policy needs keep-last and/or older-than")
        if self.keep_last is not None and self.keep_last < 1:
            raise ValueError("keep-last must be at least 1 (the latest version is always kept)")
        if self.older_than_days is not None and self.older_than_days < 0:
            raise ValueError("older-than must be >= 0 days")

    def describe(self) -> dict:
        return {k: v for k, v in (("keep_last", self.keep_last), ("older_than_days", self.older_than_days))
                if v is not None}


_DURATION = re.compile(r"^(\d+)\s*([dwmy]?)$")
_UNIT_DAYS = {"": 1, "d": 1, "w": 7, "m": 30, "y": 365}


def parse_days(text: str) -> int:
    m = _DURATION.match(text.strip().lower())
    if not m:
        raise ValueError(f"bad duration {text!r}: use e.g. 90d, 12w, 6m, 1y")
    return int(m.group(1)) * _UNIT_DAYS[m.group(2)]


def parse_policy(text: str) -> Policy:
    """'keep-last=5,older-than=180d' (DOCUSENSE_RETAIN format)"""
    kw: dict = {}
    for part in filter(None, (p.strip() for p in text.split(","))):
        key, _, value = part.partition("=")
        key = key.strip().lower().replace("_", "-")
        if key == "keep-last":
            kw["keep_last"] = int(value)
        elif key == "older-than":
            kw["older_than_days"] = parse_days(value)
        else:
            raise ValueError(f"unknown retention key {key!r}: use keep-last=N and/or older-than=90d")
    return Policy(**kw)


# ── disk usage ───────────────────────────────────────────────────────────────

def _blob_size(store: BlobStore, digest: str) -> int:
    try:
        return store.path_for(digest).stat().st_size
    except FileNotFoundError:
        return 0


def _embedding_bytes(conn: Database) -> dict[str, tuple[int, int]]:
    """version_id -> (embedding rows, bytes)"""
    size = "length(e.embedding)" if conn.dialect == "sqlite" else "vector_dims(e.embedding) * 4"
    rows = conn.execute(
        f"""SELECT p.version_id, count(*) AS n, coalesce(sum({size}), 0) AS b
            FROM span_embeddings e JOIN spans p ON p.id = e.span_id GROUP BY p.version_id"""
    ).fetchall()
    return {r["version_id"]: (int(r["n"]), int(r["b"])) for r in rows}


def _source_shares_text(conn: Database, source_sha: str) -> bool:
    """markdown / txt sources can be byte-identical to some version's canonical text"""
    return conn.execute("SELECT 1 FROM versions WHERE text_sha256 = %s LIMIT 1", (source_sha,)).fetchone() is not None


def versions_usage(conn: Database, store: BlobStore | None = None, doc: str | None = None) -> list[dict]:
    """one row per version: what it holds on disk and whether it's compacted"""
    store = store or BlobStore()
    emb = _embedding_bytes(conn)
    compacted = {r.pop("version_id"): r for r in conn.execute(
        "SELECT version_id, level, compacted_at, bytes_freed FROM compactions")}
    sql = "SELECT id, document_id, label, seq, source_sha256, text_sha256, text_bytes, ingested_at FROM versions"
    params: tuple = ()
    if doc:
        sql, params = sql + " WHERE document_id = %s", (doc,)
    rows = conn.execute(sql + " ORDER BY document_id, seq DESC", params).fetchall()
    latest: dict[str, str] = {}
    out = []
    for r in rows:
        latest.setdefault(r["document_id"], r["id"])
        source_shared = r["source_sha256"] == r["text_sha256"]
        n_emb, b_emb = emb.get(r["id"], (0, 0))
        out.append({
            "version_id": r["id"], "document_id": r["document_id"], "label": r["label"], "seq": r["seq"],
            "is_latest": latest[r["document_id"]] == r["id"],
            "ingested_at": r["ingested_at"],
            "source_bytes": 0 if source_shared else _blob_size(store, r["source_sha256"]),
            "text_bytes": _blob_size(store, r["text_sha256"]),
            "embeddings": n_emb, "embedding_bytes": b_emb,
            "compaction": compacted.get(r["id"]),
        })
    return out


# ── selection and compaction ─────────────────────────────────────────────────

def _aware(ts) -> datetime:
    if isinstance(ts, str):
        ts = datetime.fromisoformat(ts)
    return ts if ts.tzinfo else ts.replace(tzinfo=UTC)


def select(usage: list[dict], policy: Policy, now: datetime | None = None) -> list[dict]:
    """versions the policy allows compacting. both rules must hold (AND), never the latest."""
    now = now or datetime.now(UTC)
    cutoff = now - timedelta(days=policy.older_than_days) if policy.older_than_days is not None else None
    rank: dict[str, int] = {}
    picked = []
    for v in usage:  # newest first within each document
        rank[v["document_id"]] = rank.get(v["document_id"], 0) + 1
        if v["is_latest"] or v["compaction"]:
            continue
        if policy.keep_last is not None and rank[v["document_id"]] <= policy.keep_last:
            continue
        if cutoff is not None and _aware(v["ingested_at"]) > cutoff:
            continue
        picked.append(v)
    return picked


@dataclass
class CompactResult:
    versions: list[dict] = field(default_factory=list)
    bytes_freed: int = 0
    dry_run: bool = False


def compact_version(conn: Database, version_id: str, store: BlobStore | None = None,
                    policy: dict | None = None) -> dict:
    """cold-compact one version. db first, then the file, so a crash can only orphan a blob."""
    store = store or BlobStore()
    v = conn.execute(
        "SELECT id, document_id, seq, source_sha256 FROM versions WHERE id = %s", (version_id,)
    ).fetchone()
    if v is None:
        raise ValueError(f"no version {version_id}")
    newest = conn.execute("SELECT max(seq) AS m FROM versions WHERE document_id = %s", (v["document_id"],)).fetchone()
    if v["seq"] == newest["m"]:
        raise ValueError(f"{version_id} is the latest version of {v['document_id']}; it is never compacted")
    if conn.execute("SELECT 1 FROM compactions WHERE version_id = %s AND level = %s",
                    (version_id, COLD)).fetchone():
        conn.rollback()
        return {"version_id": version_id, "status": "already compacted", "bytes_freed": 0}

    delete_source = not _source_shares_text(conn, v["source_sha256"])
    source_bytes = _blob_size(store, v["source_sha256"]) if delete_source else 0
    emb_n, emb_b = _embedding_bytes(conn).get(version_id, (0, 0))
    root, n_spans = spans_root(conn, version_id)
    with conn.transaction():
        conn.execute(
            """INSERT INTO compactions (version_id, level, span_count, spans_root, bytes_freed, policy)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            (version_id, COLD, n_spans, root, source_bytes + emb_b, conn.json(policy or {})),
        )
        conn.execute(
            "DELETE FROM span_embeddings WHERE span_id IN (SELECT id FROM spans WHERE version_id = %s)",
            (version_id,),
        )
    conn.commit()  # postgres: transaction() inside an open implicit tx is only a savepoint
    if delete_source:
        try:
            store.path_for(v["source_sha256"]).unlink()
        except FileNotFoundError:
            pass
    return {"version_id": version_id, "status": "compacted", "spans_root": root, "span_count": n_spans,
            "source_bytes": source_bytes, "embeddings": emb_n, "embedding_bytes": emb_b,
            "bytes_freed": source_bytes + emb_b}


def prune_embedding_cache(conn: Database) -> int:
    """drop cached vectors no live (non-compacted) span needs. returns entries removed"""
    from docusense.config import get_settings
    from docusense.index import embed
    from docusense.store.blobs import sha256_hex

    cache = embed.EmbeddingCache(get_settings().embed_model)
    if not cache.vectors:
        return 0
    live = {sha256_hex(embed._clean(r["text"]).encode()) for r in conn.execute(
        """SELECT p.text FROM spans p WHERE p.kind = ANY(%s)
           AND NOT EXISTS (SELECT 1 FROM compactions c WHERE c.version_id = p.version_id)""",
        (list(INDEX_KINDS),))}
    stale = [k for k in cache.vectors if k not in live]
    for k in stale:
        del cache.vectors[k]
    if stale:
        cache.save()
    embed._MATRIX.clear()
    return len(stale)


def compact(conn: Database, policy: Policy, store: BlobStore | None = None, doc: str | None = None,
            dry_run: bool = False) -> CompactResult:
    store = store or BlobStore()
    picked = select(versions_usage(conn, store, doc), policy)
    conn.rollback()
    result = CompactResult(dry_run=dry_run)
    if dry_run:
        result.versions = [{"version_id": v["version_id"], "status": "would compact",
                            "bytes_freed": v["source_bytes"] + v["embedding_bytes"]} for v in picked]
    else:
        result.versions = [compact_version(conn, v["version_id"], store, policy.describe()) for v in picked]
        if picked:
            prune_embedding_cache(conn)
            conn.rollback()
    result.bytes_freed = sum(v["bytes_freed"] for v in result.versions)
    return result


def auto_compact(conn: Database, store: BlobStore | None = None) -> CompactResult | None:
    """run DOCUSENSE_RETAIN after an add. cold only; no-op when unset"""
    from docusense.config import get_settings

    spec = get_settings().retain.strip()
    if not spec:
        return None
    try:
        policy = parse_policy(spec)
    except ValueError as e:  # a bad setting must not fail an add that already succeeded
        import sys

        print(f"docusense: ignoring DOCUSENSE_RETAIN={spec!r}: {e}", file=sys.stderr)
        return None
    return compact(conn, policy, store)


def compaction_of(conn: Database, version_id: str) -> dict | None:
    row = conn.execute(
        """SELECT level, compacted_at, span_count, spans_root FROM compactions
           WHERE version_id = %s ORDER BY compacted_at DESC LIMIT 1""", (version_id,)
    ).fetchone()
    if row is None:
        return None
    ts = row["compacted_at"]
    return {**row, "compacted_at": ts.isoformat() if hasattr(ts, "isoformat") else ts}
