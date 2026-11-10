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

## Quick start (no database server needed)

DocuSense stores everything in `~/.docusense` (embedded SQLite + content-addressed blobs).

```bash
uv tool install docusense-mcp     # or: pipx install docusense-mcp
docusense add ./policies/ handbook.pdf      # PDF, Word (.docx), HTML, Markdown, .txt; folders scanned recursively
docusense list                              # documents and versions
docusense search "carry over leave" --mode hybrid
docusense verify                            # re-hash every stored span
```

Re-adding a file whose content changed appends a **new version** (`v1`, `v2`, …) instead of
overwriting, so `diff_versions`, `blame` and contradiction checks work on ordinary files. The first
indexing run downloads the local embedding model (`bge-small-en-v1.5`, ~130 MB).

## Using the MCP server

Claude Code:

```bash
claude mcp add docusense -- docusense serve-mcp
```

Claude Desktop / Cursor / VS Code (`mcpServers` in their config):

```json
{
  "mcpServers": {
    "docusense": { "command": "docusense", "args": ["serve-mcp"] }
  }
}
```

Streamable HTTP (remote-capable clients, several agents sharing one store):

```bash
docusense serve-mcp --http                         # http://127.0.0.1:8765/mcp
DOCUSENSE_HTTP_TOKEN=… docusense serve-mcp --http --host 0.0.0.0   # non-loopback requires a bearer token
```

What the server exposes:

- **17 tools**: orient (`list_documents`, `get_section_map`, `read_section`), find (`search`,
  `search_claims`, `lookup_definition`, `resolve_reference`), verify (`get_evidence`, `verify_span`,
  `assemble_context`), change over time (`list_versions`, `diff_versions`, `blame`,
  `find_affected_documents`, `find_contradictions`) and ingestion (`add_document`, `ingest_status`).
  `DOCUSENSE_TOOLS=core` trims this to 11 for agents with small context budgets.
- **Resources**: `docusense://documents` and `docusense://versions/{version_id}` (canonical text).
- **Prompts**: `answer_with_evidence`, `what_changed`, `audit_contradictions`.

`add_document` lets the agent ingest local files itself. It only reads paths under
`DOCUSENSE_ADD_ROOTS` (comma-separated; default: your home folder) and only `.pdf/.docx/.html/.md/.txt`
files. Large files are processed in the background; the agent polls `ingest_status`.

To inspect the tools interactively: `npx @modelcontextprotocol/inspector docusense serve-mcp`.

## Configuration

Settings are `DOCUSENSE_*` environment variables (or a `.env` in the working directory or in
`~/.docusense/.env`); see [.env.example](.env.example). They are namespaced on purpose: a project's own
`DATABASE_URL` is never picked up.

| Variable | Default | |
|---|---|---|
| `DOCUSENSE_HOME` | `~/.docusense` | database, blobs, indexes |
| `DOCUSENSE_DATABASE_URL` | SQLite in `DOCUSENSE_HOME` | `postgresql://…` for Postgres + pgvector |
| `DOCUSENSE_STORE_DIR` | `$DOCUSENSE_HOME/store` | blob store + search indexes |
| `DOCUSENSE_ADD_ROOTS` | home folder | folders `add_document` may read |
| `DOCUSENSE_TOOLS` | `all` | `core` = smaller MCP tool list |
| `DOCUSENSE_HTTP_TOKEN` | – | bearer token for `serve-mcp --http` |
| `DOCUSENSE_LLM_PROVIDER` | `auto` | `groq` / `anthropic` / `openai` / `ollama` / `openai-compatible` for the optional LLM fallback |
| `GROQ_API_KEY` / `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` | – | `auto` picks the first one set (Anthropic needs `docusense-mcp[anthropic]`) |
| `DOCUSENSE_LLM_MODEL` | per provider | e.g. `claude-opus-5-5` (Anthropic default); required for openai/ollama |

## Development (RFC corpus, Postgres)

```bash
uv sync
docker compose up -d                       # optional: Postgres 17 + pgvector on :5433
cp .env.example .env                       # uncomment DOCUSENSE_DATABASE_URL to use Postgres
uv run python scripts/fetch_corpus.py      # downloads RFCs, writes corpus/manifest.yaml
uv run docusense ingest                    # ingest + extract + index every version in the manifest
uv run docusense verify --deep             # re-hash every span + re-parse every source
uv run python scripts/mcp_smoke.py         # end-to-end check over the MCP stdio protocol
uv run pytest                              # runs on SQLite, and on Postgres too when configured
```

Other commands:

```bash
uv run docusense info                      # data location, backend, counts
uv run docusense stats                     # per-version pages / sections / spans / refs / claims
uv run docusense sections smtp@rfc5321     # section map with pages and byte ranges
uv run docusense define "resource owner"
uv run docusense extract [--llm-fallback]  # re-run extraction only
uv run docusense index                     # rebuild BM25, embed new spans (cached by text hash)
uv run docusense verify --span 123         # verification record for one span
uv run docusense db reset --yes            # dev only: wipe all data
```

## Retrieval eval (non-RFC documents)

`uv run python scripts/eval_retrieval.py` ingests two real public documents (IRS Publication 463, a
3-column government PDF; the Transformer paper) and asks 20 paraphrased questions. No LLM is involved.

| mode | hit@1 | hit@5 | MRR |
|---|---|---|---|
| lexical | 0.40 | 0.80 | 0.52 |
| semantic | 0.50 | 0.85 | 0.62 |
| hybrid | 0.50 | 0.85 | 0.65 |

Use it to check that retrieval changes actually help (index-time de-hyphenation, for example, lowered
hybrid MRR to 0.57 and was not adopted).

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
- `versions`, `sections` and `spans` reject UPDATE/DELETE via database triggers (both backends).
