# DocuSense

A verifiable and version-native document layer for AI agents, exposed over MCP.
B.Tech IT (VIIth Sem) project, USICT, GGSIPU. See [PLAN.md](PLAN.md) for the full build plan.

## Status

**Week 1 (ingestion + provenance):**

- PDF (fixed-width and xml2rfc-styled layouts) and Markdown parsing into a canonical text
- Section tree (numbered, appendix and unnumbered headings; TOC skipped), paragraph/table spans
- Every span stored with byte offsets + SHA-256 in an append-only Postgres schema
- Content-addressed blob store for source files and canonical texts
- `verify` (re-hash spans) and `verify --deep` (re-parse source, check determinism)

**Week 2 (extraction, search, MCP):**

- Deterministic extraction: cross-references (internal, `Section X of [RFCnnnn]`, citation tags
  mapped through each RFC's reference list, `Obsoletes:`/`Updates:` relations), defined terms,
  and sentence-level claims (BCP 14 requirements, exclusions, numeric facts with units)
- Bounded LLM fallback (Groq, off by default, at most 20 calls per version) for requirement subjects the
  heuristics miss; records model ID, prompt hash and confidence
- BM25 (bm25s) + dense embeddings (fastembed `bge-small-en-v1.5` in pgvector), hybrid via
  reciprocal rank fusion
- MCP server with 9 tools: `list_documents`, `get_section_map`, `read_section`, `search`,
  `search_claims`, `resolve_reference`, `lookup_definition`, `get_evidence`, `verify_span`

## Quick start

```bash
docker compose up -d                       # Postgres 17 + pgvector on :5433
uv sync
uv run python scripts/fetch_corpus.py      # downloads RFCs, writes corpus/manifest.yaml
uv run docusense ingest                    # ingest + extract + index every version
uv run docusense verify --deep             # re-hash every span + re-parse every source
uv run python scripts/mcp_smoke.py         # end-to-end check over the MCP stdio protocol
uv run pytest
```

Other commands:

```bash
uv run docusense stats                     # per-version pages / sections / spans / refs / claims
uv run docusense sections smtp@rfc5321     # section map with pages and byte ranges
uv run docusense search "max line length" --mode hybrid --doc smtp
uv run docusense define "resource owner"
uv run docusense extract [--llm-fallback]  # re-run extraction only
uv run docusense index                     # rebuild BM25, embed new spans (cached by text hash)
uv run docusense verify --span 123         # verification record for one span
uv run docusense db reset --yes            # dev only: wipe all data
```

## Using the MCP server

Claude Code picks up `.mcp.json` in this folder automatically (approve the `docusense` server
when prompted). For Claude Desktop or Cursor, add:

```json
{
  "mcpServers": {
    "docusense": {
      "command": "uv",
      "args": ["run", "--directory", "/absolute/path/to/docusense", "--quiet", "docusense", "serve-mcp"]
    }
  }
}
```

To inspect the tools interactively: `npx @modelcontextprotocol/inspector uv run docusense serve-mcp`.

## Corpus

`corpus/manifest.yaml` maps logical documents to ordered versions (an obsoleting RFC counts as
the next version). RFCs from 8650 onward ship an official PDF, which is used as-is. Older RFCs
are published only as paginated .txt, so `fetch_corpus.py` renders them to a fixed-width PDF
(one RFC page per PDF page, deterministic bytes) and records the .txt URL and SHA-256 under
`origin`. Three short **synthetic** Markdown documents in `corpus/synthetic/` restate RFC rules
with deliberate conflicts; their gold labels are in `corpus/synthetic/planted_conflicts.yaml`.

## Provenance model

- Each version has a canonical text: normalised UTF-8 with page headers/footers removed.
- Canonical text and the original source file are stored by SHA-256 under `store/blobs/`.
- A span is `(version_id, start_byte, end_byte, sha256, parser_version)` over that text.
- `verify` slices the blob and re-hashes. `verify --deep` re-parses the stored source file and
  checks it still produces the same canonical text.
- `versions`, `sections` and `spans` reject UPDATE/DELETE via database triggers.
