# DocuSense — Project Context

Read this first. It explains what DocuSense is, why it exists, how it works and where things live, so a
new contributor (human or AI agent) can be productive without reading the whole codebase.

---

## 1. What it is, in one paragraph

DocuSense is a **local MCP server that gives AI agents structured, verifiable access to documents**
(PDF, Word, HTML, Markdown, text). Instead of pasting a 50,000-token file into context or retrieving
fuzzy top-k chunks, the agent navigates the document like a person: table of contents → section →
paragraph → exact claim. Every passage it returns carries a citation to its exact byte range and a
SHA-256 of those bytes, and documents keep their full version history so agents can ask *what changed*.

Package: `docusense-mcp` (PyPI) · CLI and module: `docusense` · License: MIT · Python ≥ 3.12.

## 2. The main points (the USP)

1. **Far fewer tokens.** Measured on real tasks (`scripts/token_demo.py`): **23x less context than
   pasting documents, 2.3x less than vector RAG** (160,179 vs 15,765 vs 6,869 tokens). Biggest wins
   are precise lookups (19x vs paste, 11x vs RAG) and version diffs (35x vs paste).
2. **Answers questions RAG can't.** "What changed between v1 and v2?" (`diff_versions`), "Who changed
   this rule?" (`blame`), "Does our policy contradict the standard?" (`find_contradictions`). Chunk
   retrieval can only return similar text; it cannot diff or compare.
3. **Verifiable citations.** Citation format `ds://<doc>@<version>#§<section>:b<start>-<end>`.
   `get_evidence` re-hashes the stored bytes, so a hallucinated or altered quote can't pass as evidence.
4. **Versions are first-class and append-only.** Re-adding a changed file creates `v2`; old evidence is
   never overwritten (database triggers reject UPDATE/DELETE on versions, sections and spans).
5. **Deterministic first, LLM optional.** Parsing and extraction are rules and heuristics. An LLM
   fallback exists but is off by default, capped at 20 calls per version, and records model, prompt hash
   and confidence.
6. **Local and free.** Embedded SQLite + local embeddings (`bge-small-en-v1.5`). No API key, no server,
   no data leaves the machine. Postgres + pgvector is optional for teams.
7. **Proves its own value.** `docusense savings` reports tokens agents actually read vs. what pasting the
   same documents would have cost.

**One-line pitch:** *Stop pasting whole documents into your agent.*

**Honest limits:** no gain for a few short files that fit in context anyway. The tool list costs ~3.2k
tokens per session (~2.3k with `DOCUSENSE_TOOLS=core`). The agent benchmark so far only ran DocuSense
itself (100% correct, 93% citation hit-rate on 14 questions); the filesystem and RAG baselines in
`bench/` have not been run, so there is no comparative *accuracy* claim yet, only a token claim.

## 3. Who it's for

- Engineers in Claude Code / Cursor working against long specs, RFCs, API references, design docs.
- Compliance and policy work: checking internal policies against standards, tracking revisions.
- Contracts, handbooks, research papers: exact quotes with page numbers instead of paraphrase.
- Long-running agents whose context fills up from re-reading the same large files.

## 4. How it works

```
file ──► parse (PDF / DOCX / HTML / MD / TXT)
         → canonical text (UTF-8, NFC, page headers/footers removed) + page map
         → section tree → spans (paragraphs, tables, sentences), each = byte range + SHA-256
         → extraction: cross-references, definitions, normative claims (MUST / MUST NOT / numbers)
         → index: BM25 (bm25s) + embeddings (fastembed), fused with reciprocal rank fusion
         ▼
   SQLite (default) or Postgres+pgvector   +   content-addressed blob store (source + canonical text)
         ▼
   services.py  ── one query layer used by everything
         ├── mcp_server.py   MCP tools for agents (stdio or Streamable HTTP)
         ├── cli.py          `docusense` command
         └── api.py          REST API for the Next.js viewer
```

**The core idea: canonical text + byte offsets.** Each version has one canonical text, stored as a blob
under its own SHA-256. Every span is `(version_id, start_byte, end_byte, sha256, parser_version)` over
that text. `verify` slices the blob and re-hashes; `verify --deep` re-parses the original source file and
checks it still produces the identical canonical text (proves parsing is deterministic).

**Token discipline.** Every tool takes `max_tokens` and trims its output to fit. Results go out as
compact JSON text only (no pretty-printing, no duplicate structured copy, no per-hit hashes or scores;
the hash lives in `get_evidence`).

## 5. MCP surface

| Purpose | Tools |
|---|---|
| Orient | `list_documents`, `get_section_map`, `read_section` |
| Find | `search` (hybrid / lexical / semantic), `search_claims`, `lookup_definition`, `resolve_reference` |
| Verify | `get_evidence`, `verify_span`, `assemble_context` (packs evidence into a token budget) |
| Change over time | `list_versions`, `diff_versions`, `blame`, `find_affected_documents`, `find_contradictions` |
| Ingest | `add_document` (background job, limited to `DOCUSENSE_ADD_ROOTS`), `ingest_status` |

Also: resources `docusense://documents` and `docusense://versions/{id}`; prompts `answer_with_evidence`,
`what_changed`, `audit_contradictions`. `DOCUSENSE_TOOLS=core` exposes 11 tools.

Rules the server gives agents: cite citations verbatim; never cite a span with `verified=false`; if a
result has `newer_version`, check the newer version first; contradictions are surfaced, never resolved
(both sides are evidence).

## 6. User-facing CLI

```bash
uv tool install docusense-mcp
docusense setup [claude-code|claude-desktop|cursor|print]   # register the MCP server
docusense add <files or folders>                            # ingest; changed files become new versions
docusense list | search | define | sections | stats | info
docusense verify [--deep]                                   # re-hash every span
docusense savings [--days N] [--json]                       # token savings ledger
docusense serve-mcp [--http]                                # run the server
```

## 7. Code map

| Path | What |
|---|---|
| `src/docusense/ingest/` | parsers (`pdf_parser`, `md_parser`, `convert` for DOCX/HTML), `normalize`, `sections`, `pipeline` (one version in one transaction), `add` (user files → versions) |
| `src/docusense/extract/` | `references`, `definitions`, `claims`, `llm_fallback`, `run` |
| `src/docusense/index/` | `bm25`, `embed` (fastembed, cached by text hash) |
| `src/docusense/versions/` | `diff`, `blame`, `conflicts` |
| `src/docusense/context/assemble.py` | budgeted evidence packing |
| `src/docusense/services.py` | the query layer (`DocuSense` class) |
| `src/docusense/mcp_server.py` | MCP tools, resources, prompts; compact output + savings hook |
| `src/docusense/savings.py` | token ledger (`$DOCUSENSE_HOME/savings.jsonl`) |
| `src/docusense/provenance.py` | span verification |
| `src/docusense/db/` | connection layer + `schema.sql` (Postgres) / `schema_sqlite.sql` |
| `src/docusense/store/blobs.py` | content-addressed blob store |
| `src/docusense/llm.py` | pluggable LLM provider (Groq / Anthropic / OpenAI / Ollama / OpenAI-compatible) |
| `bench/` | agent benchmark: DocuSense vs filesystem MCP vs vector-RAG MCP, same model and budget |
| `scripts/` | `token_demo`, `eval_retrieval`, `eval_conflicts`, `mcp_smoke`, `fetch_corpus`, `build_mcpb` |
| `corpus/` | RFC manifest + synthetic policy docs with planted conflicts (gold labels) |
| `viewer/` | read-only Next.js viewer (span highlights, version diff, contradictions) |
| `tests/` | pytest; runs on SQLite, plus Postgres when `DOCUSENSE_DATABASE_URL` is set |

Database tables: `documents`, `versions`, `sections`, `spans`, `span_embeddings`, `refs`,
`definitions`, `claims`, `conflicts`.

## 8. Configuration essentials

All settings are `DOCUSENSE_*` env vars (or `.env` in the working directory or `~/.docusense/.env`).
Key ones: `DOCUSENSE_HOME` (default `~/.docusense`), `DOCUSENSE_DATABASE_URL` (empty = SQLite),
`DOCUSENSE_ADD_ROOTS`, `DOCUSENSE_TOOLS`, `DOCUSENSE_HTTP_TOKEN` (required for non-loopback HTTP),
`DOCUSENSE_SAVINGS_LOG=0` to disable the ledger, `DOCUSENSE_LLM_PROVIDER` for the optional fallback.
Full table: [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md).

Note: this repo's local `.env` points at Postgres on port 5433 (Docker / OrbStack). If that isn't running,
unset `DOCUSENSE_DATABASE_URL` to use SQLite.

## 9. Design rules (don't break these)

1. **MCP-first, small composable tools** — not one `search → chunks` call.
2. **Deterministic first**; LLM use is bounded and recorded.
3. **Every span verifiable** by re-hashing; never change how canonical text is produced without bumping
   `PARSER_VERSION`.
4. **Append-only history**; new versions never overwrite evidence.
5. **Contradictions are surfaced, never auto-resolved.**
6. **Every output token must earn its place** — respect `max_tokens`, keep responses compact.
7. **Fair evaluation** — all benchmark configs use the same model and budget.

## 10. Status and next steps

- Done: ingestion (PDF incl. multi-column, DOCX, HTML, MD, TXT), extraction, hybrid search, 17 MCP tools,
  version diff/blame/contradictions, SQLite zero-setup mode, HTTP transport, viewer, savings ledger,
  `setup` command, release workflow (PyPI trusted publishing + `.mcpb` bundle).
- Not yet: published on PyPI (needs the trusted-publisher setup in [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md#releasing));
  benchmark baselines (filesystem, vector RAG) not run, so no comparative accuracy numbers.
- Distribution ideas: official MCP registry, Smithery, awesome-mcp-servers lists, a demo GIF of
  `docusense savings`.

Origin: B.Tech IT (VIIth Sem) project, USICT, GGSIPU. The original build plan is in [PLAN.md](PLAN.md).
