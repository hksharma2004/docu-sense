"""baseline 2: vector rag mcp, one search(query) tool over ~512-token chunks, same embedding model"""

import json
from pathlib import Path

import numpy as np
from mcp.server import MCPServer

WORK = Path(__file__).resolve().parents[1] / "work"
TEXTS, INDEX = WORK / "texts", WORK / "vector_index.npz"
CHUNK_CHARS, OVERLAP = 2000, 200  # ≈512 tokens

server = MCPServer("vector-rag-baseline", instructions="Semantic search over document chunks.")


def _chunks() -> list[dict]:
    out = []
    for p in sorted(TEXTS.glob("*.txt")):
        text = p.read_text()
        for start in range(0, max(len(text), 1), CHUNK_CHARS - OVERLAP):
            chunk = text[start:start + CHUNK_CHARS]
            if chunk.strip():
                out.append({"file": p.name, "char_offset": start, "text": chunk})
    return out


def _index():
    from docusense.index.embed import embed_texts

    chunks = _chunks()
    if INDEX.exists():
        data = np.load(INDEX, allow_pickle=False)
        if json.loads(str(data["meta"])) == [[c["file"], c["char_offset"]] for c in chunks]:
            return chunks, data["vectors"]
    vectors = np.stack(embed_texts([" ".join(c["text"].split()) for c in chunks]))
    vectors /= np.linalg.norm(vectors, axis=1, keepdims=True)
    np.savez(INDEX, vectors=vectors, meta=json.dumps([[c["file"], c["char_offset"]] for c in chunks]))
    return chunks, vectors


_state: dict = {}


@server.tool()
def search(query: str, k: int = 5) -> list[dict]:
    """Return the k chunks most similar to the query (file name, character offset, text)."""
    from docusense.index.embed import embed_query

    if not _state:
        _state["chunks"], _state["vectors"] = _index()
    q = embed_query(query)
    scores = _state["vectors"] @ (q / np.linalg.norm(q))
    return [dict(_state["chunks"][i], score=round(float(scores[i]), 4)) for i in np.argsort(-scores)[:max(1, min(k, 10))]]


if __name__ == "__main__":
    if not __import__("sys").argv[1:] == ["--build"]:
        server.run()
    else:
        print(len(_index()[0]), "chunks indexed")
