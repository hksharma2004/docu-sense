"""How much text does the model have to read to answer? DocuSense vs the usual alternatives.

    uv run python -m bench.export            # once: canonical texts for the baselines
    uv run python scripts/token_demo.py

Scenario: a compliance check — "Does Example Org's mail policy conflict with the SMTP standard?"
and two lookups. For each, it measures the context an agent must load:
  paste docs   – the whole relevant documents in the prompt (what people do in a chat window)
  vector RAG   – top-5 ~512-token chunks per query, 2 queries (a typical RAG tool)
  DocuSense    – the actual tool calls an agent makes (outputs measured, not guessed)
Tokens are estimated as characters / 4 for every column, so the comparison is like-for-like.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from docusense.db.conn import connect  # noqa: E402
from docusense.services import DocuSense  # noqa: E402

TEXTS = ROOT / "bench" / "work" / "texts"


def tok(obj) -> int:
    text = obj if isinstance(obj, str) else json.dumps(obj, ensure_ascii=False, separators=(",", ":"))  # what MCP sends
    return len(text) // 4


def vector_rag(queries: list[str]) -> int:
    from bench.baselines.vector_rag_mcp import search

    return sum(tok(search(q, k=5)) for q in queries)


SCENARIOS = [
    {
        "task": "Audit: does mail-policy v2 conflict with RFC 5321?",
        "docs": ["mail-policy@v2", "smtp@rfc5321"],
        "rag_queries": ["mail policy limits that conflict with SMTP", "SMTP retry interval give-up time line length recipients"],
        "docusense": lambda ds: [ds.find_contradictions(doc="mail-policy"),
                                 ds.get_evidence(ds.search("retry interval at least 30 minutes", doc="smtp", k=1)["results"][0]["span_id"])],
    },
    {
        "task": "What changed in SMTP between RFC 2821 and RFC 5321 (requirements)?",
        "docs": ["smtp@rfc2821", "smtp@rfc5321"],
        "rag_queries": ["changes from RFC 2821 to RFC 5321", "SMTP requirement MUST changes"],
        "docusense": lambda ds: [ds.diff_versions("smtp", level="claim", max_tokens=3000)],
    },
    {
        "task": "Max PKCE code_verifier length, with a verified citation",
        "docs": ["pkce@rfc7636"],
        "rag_queries": ["code_verifier minimum maximum length", "PKCE code verifier characters"],
        "docusense": lambda ds: [ds.search("code_verifier minimum and maximum length", doc="pkce", k=3),
                                 ds.get_evidence(ds.search("code_verifier minimum length 43", doc="pkce", k=1)["results"][0]["span_id"])],
    },
]


def main() -> None:
    rows = []
    with connect() as conn:
        ds = DocuSense(conn)
        for s in SCENARIOS:
            paste = sum(tok((TEXTS / f"{d}.txt").read_text()) for d in s["docs"])
            rag = vector_rag(s["rag_queries"])
            dsense = sum(tok(out) for out in s["docusense"](ds))
            rows.append((s["task"], paste, rag, dsense))

    print("| task | paste docs | vector RAG | DocuSense | saving vs paste | vs RAG |")
    print("|---|---|---|---|---|---|")
    for task, paste, rag, dsense in rows:
        print(f"| {task} | {paste:,} | {rag:,} | {dsense:,} | {paste / dsense:.0f}x | {rag / dsense:.1f}x |")
    total = [sum(r[i] for r in rows) for i in (1, 2, 3)]
    print(f"| **total** | {total[0]:,} | {total[1]:,} | {total[2]:,} | {total[0] / total[2]:.0f}x | {total[1] / total[2]:.1f}x |")


if __name__ == "__main__":
    main()
