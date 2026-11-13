# DocuSense

**Stop pasting whole documents into your agent.** DocuSense is a local MCP server that lets Claude, Cursor
and other agents read your PDFs, Word files and docs *by section and by claim* — so they load the 300
tokens that answer the question, not the 50,000-token file. Every passage comes back with a citation
to its exact bytes and a SHA-256 you can verify.

```
pasting the docs   ████████████████████████████████████████  160,179 tokens
vector RAG (top-5) ████                                         15,765 tokens
DocuSense          ██                                            6,869 tokens   → 23x less than pasting, 2.3x less than RAG
```
<sub>Three real tasks over RFC specs and a policy file; measured by [`scripts/token_demo.py`](scripts/token_demo.py) on the actual tool outputs.</sub>

## Why not just RAG?

Chunk-and-embed retrieval answers "find text like this". Most document questions are not that:

| Question | Paste / file read | Vector RAG | DocuSense |
|---|---|---|---|
| *"What's the max PKCE verifier length? Cite it."* | 9,090 tok | 5,362 tok of nearby chunks | **478 tok**: the one paragraph + verified citation |
| *"What changed between v1 and v2 of the spec?"* | 97,895 tok (both versions) | 5,292 tok, can't actually diff | **2,776 tok**: claim-level diff (`diff_versions`) |
| *"Does our policy conflict with the standard?"* | 53,194 tok | 5,111 tok, hopes the right chunks surface | **3,615 tok**: `find_contradictions`, both sides cited |

What makes the difference:

- **Structure-aware.** Documents are parsed into a section tree, paragraphs, tables, definitions,
  cross-references and normative claims (*MUST / MUST NOT / numeric limits*). Agents navigate like a
  person with a table of contents instead of re-reading everything.
- **Budgeted responses.** Every tool takes `max_tokens`; outputs are compact JSON with no padding.
- **Versions are first-class.** Re-adding a changed file makes `v2`. Ask what changed, who changed it
  (`blame`), or which other documents are affected — without loading either version.
- **Verifiable.** Each passage is `ds://doc@version#§section:b<start>-<end>` + SHA-256. `get_evidence`
  re-hashes against the stored bytes, so a hallucinated quote can't pass as a citation.
- **Local and free.** Embedded SQLite + local embeddings. No API key, no server, nothing leaves your machine.
- **Proves its own value.** `docusense savings` shows how many tokens your agents actually saved.

## Get started (2 minutes)

```bash
uv tool install docusense-mcp           # or: pipx install docusense-mcp
docusense setup                         # registers with Claude Code (also: claude-desktop | cursor | print)
docusense add ~/work/specs handbook.pdf # PDF, .docx, HTML, Markdown, .txt — folders scanned recursively
```

Then ask your agent about your documents. Later, see what it saved (example output):

```console
$ docusense savings
12 agent sessions · 87 tool calls
read via DocuSense:         41,302 tokens
pasting the docs:          912,440 tokens
saved:                     871,138 tokens (22.1x less context)
```

The first indexing run downloads the local embedding model (`bge-small-en-v1.5`, ~130 MB) once.
Claude Desktop users can also install the one-click `docusense.mcpb` bundle from the
[releases page](https://github.com/hksharma2004/docu-sense/releases).

Agents can add files themselves with the `add_document` tool (restricted to `DOCUSENSE_ADD_ROOTS`,
default: your home folder).

## Good fits

- **Engineers** working against long specs, RFCs, API references, design docs and ADRs in Claude Code / Cursor.
- **Compliance and policy work**: checking internal policies against standards, tracking what changed between revisions.
- **Contracts, handbooks, research papers**: precise quotes with page numbers instead of paraphrase.
- **Any long-running agent** whose context fills up from repeatedly reading the same large files.

Less useful for: a handful of short files that fit comfortably in context anyway. The tool list costs
~3.2k tokens per session (~2.3k with `DOCUSENSE_TOOLS=core`), which one avoided document read repays.

## Tools

| Purpose | Tools |
|---|---|
| Orient | `list_documents`, `get_section_map`, `read_section` |
| Find | `search` (hybrid BM25 + embeddings), `search_claims`, `lookup_definition`, `resolve_reference` |
| Verify | `get_evidence`, `verify_span`, `assemble_context` (packs evidence into a token budget) |
| Change over time | `list_versions`, `diff_versions`, `blame`, `find_affected_documents`, `find_contradictions` |
| Ingest | `add_document`, `ingest_status` |

Plus resources (`docusense://documents`, canonical text per version) and prompts (`answer_with_evidence`,
`what_changed`, `audit_contradictions`). `DOCUSENSE_TOOLS=core` exposes 11 tools for tight budgets.

## Accuracy

On a 14-question agent benchmark over the RFC corpus (multi-hop, structural and temporal questions),
an agent using DocuSense answered 100% correctly with 93% citation hit-rate
([`bench/`](bench/), `nvidia/nemotron-3-ultra` via OpenRouter). Retrieval-only eval on non-RFC PDFs
(IRS Pub 463, the Transformer paper): hybrid hit@5 0.85, MRR 0.65 ([`scripts/eval_retrieval.py`](scripts/eval_retrieval.py)).

## More

- Other ways to run it: `docusense serve-mcp --http` (Streamable HTTP, several agents sharing one store;
  non-loopback requires `DOCUSENSE_HTTP_TOKEN`), Postgres + pgvector backend, CLI search.
- Configuration, development, provenance model and releasing: [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md).
- Inspect the tools: `npx @modelcontextprotocol/inspector docusense serve-mcp`.

MIT licensed. Originally built as a B.Tech IT project (USICT, GGSIPU); see [PLAN.md](PLAN.md).
