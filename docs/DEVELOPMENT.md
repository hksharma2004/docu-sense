# DocuSense: configuration, development and internals

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
| `DOCUSENSE_SAVINGS_LOG` | `1` | `0` = do not record the local token ledger |
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

## Feature history


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


## Token savings ledger

Every MCP tool call appends `{ts, session, tool, returned, versions}` to `$DOCUSENSE_HOME/savings.jsonl`
(local only; `DOCUSENSE_SAVINGS_LOG=0` disables it). `docusense savings` compares, per server session, the
tokens returned against pasting each document version the session touched once. Both sides use chars/4.

## Releasing

1. One-time: on pypi.org add a trusted publisher for `docusense-mcp` (workflow `release.yml`, environment `pypi`),
   and create a `pypi` environment in the GitHub repo settings.
2. Bump `version` in `pyproject.toml`, commit, then `git tag v0.x.y && git push --tags`.
3. The workflow tests, builds the wheel and `.mcpb`, publishes to PyPI and creates a GitHub release.
