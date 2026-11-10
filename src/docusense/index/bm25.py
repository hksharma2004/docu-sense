"""Embedded BM25 index over paragraph/table spans (bm25s, persisted under store/index/bm25)."""

import json
from pathlib import Path

import bm25s
from docusense.db.conn import Database
import Stemmer

from docusense.config import get_settings

INDEX_KINDS = ("paragraph", "table", "code")
_stemmer = Stemmer.Stemmer("english")


def index_dir() -> Path:
    return get_settings().index_dir / "bm25"


def _tokenize(texts: list[str]):
    return bm25s.tokenize(texts, stopwords="en", stemmer=_stemmer, show_progress=False)


def build(conn: Database) -> int:
    rows = conn.execute(
        "SELECT id, text FROM spans WHERE kind = ANY(%s) ORDER BY id", (list(INDEX_KINDS),)
    ).fetchall()
    retriever = bm25s.BM25()
    retriever.index(_tokenize([r["text"] for r in rows]), show_progress=False)
    out = index_dir()
    out.mkdir(parents=True, exist_ok=True)
    retriever.save(str(out))
    (out / "span_ids.json").write_text(json.dumps([r["id"] for r in rows]))
    return len(rows)


class BM25Index:
    def __init__(self, path: Path | None = None):
        path = path or index_dir()
        self.retriever = bm25s.BM25.load(str(path))
        self.span_ids: list[int] = json.loads((path / "span_ids.json").read_text())

    def search(self, query: str, k: int = 20) -> list[tuple[int, float]]:
        tokens = _tokenize([query])
        if not tokens.vocab:
            return []
        k = min(k, len(self.span_ids))
        docs, scores = self.retriever.retrieve(tokens, k=k, show_progress=False)
        return [(self.span_ids[int(d)], float(s)) for d, s in zip(docs[0], scores[0]) if s > 0]
