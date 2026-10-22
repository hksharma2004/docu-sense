"""Dense embeddings (fastembed, local ONNX) stored in pgvector.

Vectors are also cached on disk keyed by sha256(text), so re-ingesting (new span ids, same text)
never recomputes them.
"""

import re
from functools import lru_cache
from pathlib import Path

import numpy as np
import psycopg
from pgvector.psycopg import register_vector

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
        self.path: Path = get_settings().blob_dir.parent / "index" / f"embeddings_{safe}.npz"
        self.vectors: dict[str, np.ndarray] = {}
        if self.path.exists():
            with np.load(self.path) as data:
                self.vectors = {k: data[k] for k in data.files}

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        np.savez(self.path, **self.vectors)


def build(conn: psycopg.Connection, progress=None) -> int:
    """Embed every indexable span lacking an embedding for the current model. Returns spans written."""
    register_vector(conn)
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

    with conn.cursor() as cur:
        cur.executemany(
            """INSERT INTO span_embeddings (span_id, model, embedding) VALUES (%s, %s, %s)
               ON CONFLICT (span_id) DO UPDATE SET model = EXCLUDED.model, embedding = EXCLUDED.embedding""",
            [(r["id"], model, cache.vectors[k]) for r, k in zip(rows, keys)],
        )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS span_embeddings_hnsw ON span_embeddings USING hnsw (embedding vector_cosine_ops)"
    )
    conn.commit()
    return len(rows)


def seed_cache_from_db(conn: psycopg.Connection) -> int:
    """Copy existing pgvector embeddings into the on-disk cache (before a reset)."""
    register_vector(conn)
    model = get_settings().embed_model
    cache = EmbeddingCache(model)
    for r in conn.execute(
        "SELECT p.text, e.embedding FROM span_embeddings e JOIN spans p ON p.id = e.span_id WHERE e.model = %s",
        (model,),
    ):
        cache.vectors[sha256_hex(_clean(r["text"]).encode())] = r["embedding"].to_numpy().astype(np.float32)
    cache.save()
    return len(cache.vectors)


def search(conn: psycopg.Connection, query: str, k: int = 20) -> list[tuple[int, float]]:
    register_vector(conn)
    vector = embed_query(query)
    rows = conn.execute(
        """SELECT span_id, 1 - (embedding <=> %s) AS score FROM span_embeddings
           WHERE model = %s ORDER BY embedding <=> %s LIMIT %s""",
        (vector, get_settings().embed_model, vector, k),
    ).fetchall()
    return [(r["span_id"], float(r["score"])) for r in rows]
