"""Dense embeddings (fastembed, local ONNX).

Postgres stores them in pgvector (HNSW index). SQLite stores float32 bytes and searches with an
exact numpy cosine scan, which is fast enough for local corpora (~100k spans).

Vectors are also cached on disk keyed by sha256(text), so re-ingesting (new span ids, same text)
never recomputes them.
"""

import re
from functools import lru_cache
from pathlib import Path

import numpy as np
from docusense.db.conn import Database

from docusense.config import get_settings
from docusense.index.bm25 import INDEX_KINDS
from docusense.store.blobs import sha256_hex

QUERY_PREFIX = "Represent this sentence for searching relevant passages: "  # bge retrieval instruction
BATCH = 64


@lru_cache
def _model():
    from fastembed import TextEmbedding

    return TextEmbedding(get_settings().embed_model)


def _clean(text: str) -> str:
    return " ".join(text.split())


def embed_texts(texts: list[str]) -> list[np.ndarray]:
    return list(_model().embed(texts, batch_size=BATCH))


def embed_query(query: str) -> np.ndarray:
    return next(iter(_model().embed([QUERY_PREFIX + query])))


class EmbeddingCache:
    def __init__(self, model: str):
        safe = re.sub(r"[^\w.-]", "_", model)
        self.path: Path = get_settings().index_dir / f"embeddings_{safe}.npz"
        self.vectors: dict[str, np.ndarray] = {}
        if self.path.exists():
            with np.load(self.path) as data:
                self.vectors = {k: data[k] for k in data.files}

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        np.savez(self.path, **self.vectors)


def _register(conn: Database) -> None:
    if conn.dialect == "postgres":
        from pgvector.psycopg import register_vector

        register_vector(conn.raw)


def _to_db(conn: Database, vec: np.ndarray):
    return vec if conn.dialect == "postgres" else np.asarray(vec, dtype="<f4").tobytes()


def _from_db(value) -> np.ndarray:
    if isinstance(value, (bytes, memoryview)):
        return np.frombuffer(value, dtype="<f4")
    return value.to_numpy().astype(np.float32)


def build(conn: Database, progress=None) -> int:
    """Embed every indexable span lacking an embedding for the current model. Returns spans written."""
    _register(conn)
    model = get_settings().embed_model
    cache = EmbeddingCache(model)
    rows = conn.execute(
        """SELECT p.id, p.text FROM spans p
           LEFT JOIN span_embeddings e ON e.span_id = p.id AND e.model = %s
           WHERE p.kind = ANY(%s) AND e.span_id IS NULL ORDER BY p.id""",
        (model, list(INDEX_KINDS)),
    ).fetchall()
    keys = [sha256_hex(_clean(r["text"]).encode()) for r in rows]
    missing = sorted({k: r for k, r in zip(keys, rows) if k not in cache.vectors}.items())
    for i in range(0, len(missing), 256):
        batch = missing[i:i + 256]
        for (key, _), vec in zip(batch, embed_texts([_clean(r["text"]) for _, r in batch])):
            cache.vectors[key] = vec
        cache.save()
        if progress:
            progress(min(i + 256, len(missing)), len(missing))

    conn.executemany(
        """INSERT INTO span_embeddings (span_id, model, embedding) VALUES (%s, %s, %s)
           ON CONFLICT (span_id) DO UPDATE SET model = excluded.model, embedding = excluded.embedding""",
        [(r["id"], model, _to_db(conn, cache.vectors[k])) for r, k in zip(rows, keys)],
    )
    if conn.dialect == "postgres":
        conn.execute(
            "CREATE INDEX IF NOT EXISTS span_embeddings_hnsw ON span_embeddings USING hnsw (embedding vector_cosine_ops)"
        )
    conn.commit()
    _MATRIX.clear()
    return len(rows)


def seed_cache_from_db(conn: Database) -> int:
    """Copy existing pgvector embeddings into the on-disk cache (before a reset)."""
    _register(conn)
    model = get_settings().embed_model
    cache = EmbeddingCache(model)
    for r in conn.execute(
        "SELECT p.text, e.embedding FROM span_embeddings e JOIN spans p ON p.id = e.span_id WHERE e.model = %s",
        (model,),
    ):
        cache.vectors[sha256_hex(_clean(r["text"]).encode())] = _from_db(r["embedding"])
    cache.save()
    return len(cache.vectors)


# SQLite: (model, row count, max span id) -> (span ids, L2-normalised matrix)
_MATRIX: dict[tuple, tuple[np.ndarray, np.ndarray]] = {}


def _sqlite_matrix(conn: Database, model: str) -> tuple[np.ndarray, np.ndarray]:
    stamp = conn.execute(
        "SELECT count(*) AS n, max(span_id) AS m FROM span_embeddings WHERE model = %s", (model,)
    ).fetchone()
    key = (model, stamp["n"], stamp["m"])
    if key not in _MATRIX:
        rows = conn.execute(
            "SELECT span_id, embedding FROM span_embeddings WHERE model = %s ORDER BY span_id", (model,)
        ).fetchall()
        ids = np.array([r["span_id"] for r in rows], dtype=np.int64)
        mat = np.stack([_from_db(r["embedding"]) for r in rows]) if rows else np.zeros((0, 1), np.float32)
        norms = np.linalg.norm(mat, axis=1, keepdims=True)
        _MATRIX.clear()
        _MATRIX[key] = (ids, mat / np.where(norms == 0, 1, norms))
    return _MATRIX[key]


def search(conn: Database, query: str, k: int = 20) -> list[tuple[int, float]]:
    vector = embed_query(query)
    if conn.dialect == "sqlite":
        ids, mat = _sqlite_matrix(conn, get_settings().embed_model)
        if not len(ids):
            return []
        q = np.asarray(vector, dtype=np.float32)
        scores = mat @ (q / (np.linalg.norm(q) or 1))
        top = np.argsort(-scores)[:k]
        return [(int(ids[i]), float(scores[i])) for i in top]
    _register(conn)
    rows = conn.execute(
        """SELECT span_id, 1 - (embedding <=> %s) AS score FROM span_embeddings
           WHERE model = %s ORDER BY embedding <=> %s LIMIT %s""",
        (vector, get_settings().embed_model, vector, k),
    ).fetchall()
    return [(r["span_id"], float(r["score"])) for r in rows]
