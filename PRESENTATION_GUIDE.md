# DocuSense: Supervisor Presentation and Demo Guide

This guide covers how to start the project and how to explain its problem, solution,
architecture, technology choices, limitations, and future work. It describes the local
development setup in this repository.

## 1. The short introduction

> DocuSense is a version-aware evidence layer for technical documents. It turns documents
> such as RFCs and policies into searchable, addressable passages, then exposes those
> passages—with citations and integrity checks—to both people and AI agents.

The key point to emphasize is that DocuSense does not ask an AI model to remember or
summarize a whole document. It helps the model find a relevant passage, identify which
document version it came from, and check that the passage still matches its stored text.

## 2. Start the project

### Prerequisites

- Docker Desktop (or another Docker Compose-compatible runtime) running.
- Python 3.12 and `uv`.
- Node.js compatible with the project's Next.js version, plus `npm`.
- The project corpus files, already included under `corpus/`.

The normal demo does not require an LLM API key. The optional LLM extraction/judging
features are separate from the default deterministic pipeline.

### One-time setup (or after a clean database)

Run these commands from a terminal. Start PostgreSQL first, and wait until it is healthy
before ingesting documents:

```bash
cd /Users/h4rsh/Desktop/docusense
docker compose up -d
docker compose ps
uv sync
uv run docusense ingest
cd viewer
npm ci
```

`docker compose ps` should show the `db` service as running/healthy. PostgreSQL is exposed
on host port `5433`. `uv run docusense ingest` initializes the schema, ingests corpus
versions, extracts references/definitions/claims, detects contradiction candidates, and
builds the lexical and dense search indexes. The first run may take longer while packages
and the local embedding model are downloaded. The corpus is already present, so fetching
it is normally unnecessary; if files are missing, run
`uv run python scripts/fetch_corpus.py` from the repository root before ingesting.

Before the presentation, verify the prepared data:

```bash
cd /Users/h4rsh/Desktop/docusense
uv run docusense stats
uv run docusense verify --deep
uv run python scripts/mcp_smoke.py
```

`verify --deep` checks spans and reparses their source files. The smoke test exercises a
real MCP flow. These checks are best run before the meeting, not during the live demo.

### Live demo: three terminals

First, make sure Docker is still running:

```bash
cd /Users/h4rsh/Desktop/docusense
docker compose up -d
docker compose ps
```

Then open three terminals and leave each process running.

**Terminal 1 — REST API**

```bash
cd /Users/h4rsh/Desktop/docusense
uv run docusense serve-api
```

The API listens at `http://127.0.0.1:8000`. Its interactive API documentation is at
`http://127.0.0.1:8000/docs`.

**Terminal 2 — web viewer**

```bash
cd /Users/h4rsh/Desktop/docusense/viewer
npm run dev
```

Open `http://localhost:3000`. If dependencies have not yet been installed, run `npm ci`
in this terminal's directory first.

**Terminal 3 — MCP Inspector**

```bash
cd /Users/h4rsh/Desktop/docusense
npx -y @modelcontextprotocol/inspector uv run docusense serve-mcp
```

Open the Inspector URL printed in this terminal (commonly `http://localhost:6274`). The
Inspector launches the MCP server as a subprocess; do not separately start
`uv run docusense serve-mcp` in another terminal for this setup. Use the Inspector to
connect and call tools such as `list_documents`, `search`, `get_evidence`, or `verify_span`.

To stop the demo, stop each foreground process with `Ctrl+C`. To stop the database too:

```bash
cd /Users/h4rsh/Desktop/docusense
docker compose down
```

This keeps the Postgres data volume. Do not use `docker compose down -v` unless you
intentionally want to delete that database volume.

## 3. Suggested presentation flow

### A. Explain the problem

Technical requirements are spread across long documents and multiple versions. A person
or an AI assistant can find a plausible passage but still:

- cite the wrong version or miss that a document has been superseded;
- lose the section/page context around a passage;
- return a quote that no longer matches its source;
- miss relevant material because exact-keyword and semantic searches behave differently;
- overlook a conflict between a local policy and a referenced standard.

These are especially important when the answer needs to be auditable rather than merely
plausible.

### B. Explain the solution

DocuSense parses PDFs and Markdown into canonical text, sections, and passages called
spans. It records each span's version, byte offsets, page, and SHA-256 hash. It indexes
the corpus for lexical and semantic retrieval, extracts useful structure such as
definitions and references, and offers version comparisons and contradiction candidates.

People use the web viewer. AI clients use the same query layer through MCP tools. Both
paths can lead back to the same versioned evidence.

### C. Demo the user journey

1. **Documents:** show the corpus and the version labels. Explain that old versions are
   retained instead of overwritten.
2. **Search:** search for `maximum text line length`. Open a result and point out its
   citation, section, and page.
3. **Evidence:** inspect the selected span and show its hash/provenance and verification
   result.
4. **Diff:** compare `mail-policy` v1 with v2. Point out the line-length change from
   2000 octets to 1000 octets.
5. **Contradictions:** show the policy/RFC evidence sides. Explain that the system
   surfaces candidates; it does not silently choose which source should win.
6. **MCP Inspector:** call `list_documents`, then `search`, and inspect a result with
   `get_evidence` or `verify_span`. This demonstrates that an AI-facing tool interface
   is available in addition to the human-facing viewer.

The fictional policy documents intentionally contain disagreements with RFCs so this
behavior can be demonstrated consistently. Clearly label them as synthetic test data,
not real organizational policy.

### D. Explain what happens behind the scenes

1. A manifest identifies logical documents, their ordered versions, and source files.
2. The ingestion pipeline parses a PDF or Markdown source and produces canonical UTF-8
   text, section boundaries, and spans.
3. The source and canonical text are stored by content hash; metadata and extracted data
   are recorded in PostgreSQL.
4. Deterministic extractors identify references, definitions, and sentence-level claims.
   Optional LLM fallback/judging is off by default.
5. BM25 and local dense embeddings support lexical, semantic, and hybrid search. Hybrid
   results use reciprocal-rank fusion.
6. The shared `DocuSense` service supplies both the REST API and MCP tools.
7. The viewer presents documents, search results, evidence, contradictions, and diffs.

## 4. Unique selling points

- **Evidence is addressable:** results point to a particular version and byte range, not
  just a document title or an ungrounded answer.
- **Integrity can be checked:** spans carry hashes and can be verified; deep verification
  also reparses the original source to check parser determinism.
- **Versions are first-class:** older versions remain available, with comparisons and
  stale-version awareness.
- **Retrieval combines approaches:** BM25 is useful for exact wording and identifiers;
  dense embeddings help with paraphrased queries; hybrid retrieval combines rankings.
- **Agent-ready interface:** MCP gives compatible AI clients a structured way to search,
  read sections, follow references, assemble context, and verify evidence.
- **Conflicts remain transparent:** both sides of a detected conflict are retained with
  provenance rather than hidden behind an automatic winner.
- **Local-first demo path:** the default corpus, embedding model, database, API, and
  viewer can run locally without calling a hosted LLM.

## 5. Technology stack

| Layer | Technology | Role |
|---|---|---|
| Language/runtime | Python 3.12 | Ingestion, extraction, search services, CLI, API, and MCP server |
| Relational storage | PostgreSQL 17 + pgvector | Documents, versions, sections, spans, extracted data, and dense vectors |
| Source integrity | SHA-256 content-addressed blob store | Stores source/canonical text blobs and supports span verification |
| PDF/Markdown parsing | PyMuPDF and markdown-it-py | Parses the project's PDF and Markdown inputs |
| Extraction/API | Python regex/rules, FastAPI, Uvicorn | Deterministic extraction and HTTP endpoints for the viewer |
| Lexical search | bm25s and PyStemmer | BM25 retrieval for terms and exact wording |
| Dense search | fastembed, BAAI/bge-small-en-v1.5, NumPy, pgvector | Local embedding generation, caching, and vector retrieval |
| AI tool protocol | MCP Python SDK | Exposes document capabilities as structured tools |
| Frontend | Next.js, React, TypeScript, Tailwind CSS | Browser-based document and evidence viewer |
| Development/test | uv, npm, Docker Compose, pytest | Dependency management, local services, and tests |

## 6. Architecture

```text
PDF / Markdown sources + corpus manifest
                  |
                  v
       Parser and canonical text
                  |
          +-------+--------+
          |                |
          v                v
  Content-addressed     PostgreSQL
  source/text blobs     documents, versions,
                        sections, spans, claims,
                        references, definitions
                              |
                 +------------+-----------+
                 |                        |
                 v                        v
        BM25 + dense indexes        Shared DocuSense
                                    query/services layer
                                      |            |
                                      v            v
                                FastAPI REST      MCP stdio
                                      |            |
                                      v            v
                                Next.js viewer   MCP client /
                                                 Inspector
```

The database schema rejects updates and deletes to the core version, section, and span
records. Derived extraction/index data can be regenerated; the evidence records themselves
are intended to remain append-only.

## 7. How other AI/LLM providers can use it

DocuSense is **not an inference provider** and does not require a particular LLM to answer
questions. MCP is its model/client integration point:

1. A compatible AI host launches `uv run docusense serve-mcp` as a local stdio MCP server.
2. The model asks the host to call a DocuSense tool, for example `search` or
   `get_section_map`.
3. DocuSense returns structured results with citations and provenance.
4. The model uses `get_evidence`, `verify_span`, or `assemble_context` to check and
   package evidence before citing it in its answer.

The repo documents configuration for clients such as Claude Desktop and Cursor; the MCP
Inspector is useful for testing calls manually. A different LLM can use the tools if its
host supports MCP or has an MCP adapter. The current server uses **stdio**, so a remote
provider cannot simply connect to it over the internet as-is; remote use would need a
compatible host/bridge or an MCP HTTP transport plus appropriate authentication and
deployment. The REST API is also available for custom applications that prefer HTTP.

The optional Groq fallback/judge is separate: it can assist selected extraction or
contradiction workflows, but it is not required for normal search, verification, or MCP
operation.

## 8. Alternatives and tradeoffs

| Choice in this project | Alternative | Why this choice / tradeoff |
|---|---|---|
| PostgreSQL + pgvector | SQLite for a tiny single-user demo; a hosted vector database for a larger service | One database stores structured metadata and vectors, and is suitable for a local multi-component demo. It adds Docker/database setup and is not yet a production deployment architecture. |
| BM25 + dense retrieval + rank fusion | BM25-only, vector-only, or a more complex reranker | Hybrid retrieval can cover exact terms and paraphrases. It costs more disk/CPU and still needs measured relevance evaluation and tuning. |
| Local fastembed model | Hosted embedding API | Local inference avoids per-query embedding API calls and keeps the default path local, but requires model download and machine resources; hosted models may be stronger or easier to scale but introduce network, cost, and data-handling considerations. |
| Deterministic parsers and rule-based extraction | OCR/document AI or LLM-first parsing/extraction | Rules are repeatable and easy to inspect. They can miss unusual layouts, implicit claims, or ambiguous language. OCR/LLM methods may cover more cases but add errors, cost, latency, or non-determinism. |
| MCP stdio for local AI-host integration | HTTP/remote MCP service | Stdio is simple for local clients and avoids exposing a service port. It is not by itself a remote, authenticated, multi-user deployment. |
| SHA-256 span checks and append-only core records | Signed source attestations or an external immutable ledger | Hashes detect a mismatch against stored text; they do not prove who published a source or prevent a privileged actor from replacing both data and hashes. Strong authenticity would need trusted signatures/source verification and key management. |
| Next.js viewer plus FastAPI | A single full-stack framework or a command-line-only interface | Separate API and UI make the shared services accessible to a browser and other HTTP clients, but require running and configuring more than one process. |

## 9. Limitations to acknowledge honestly

- The included corpus is a focused demo set (RFCs and synthetic examples), not a
  comprehensive index of standards or a production corpus.
- PDF parsing works on the project's text-based sources; scanned documents would need
  OCR, and unusual layouts can still confuse extraction.
- Claim and contradiction extraction is heuristic. It can miss conflicts or produce
  candidates that need human review. A candidate is not a legal or policy conclusion.
- A correct hash shows that text matches the stored canonical blob; it does not by itself
  certify the authority or authenticity of the original source.
- The local stdio MCP server is designed for local integrations. Authentication,
  authorization, tenant isolation, and remote deployment need additional engineering.
- The embedding model and database consume local storage/resources; first-time setup
  needs downloads and indexing time.
- Search quality and contradiction quality should be reported with evaluation results
  before making claims about broad accuracy. The repository has planted conflict labels
  and an evaluation script to support such measurement.

## 10. What to improve next

Prioritize improvements by evidence and user need:

1. **Measure retrieval and extraction quality:** create a held-out query set; report
   recall@k/MRR for search and precision/recall for contradictions, including false
   positives and missed cases.
2. **Improve provenance at the source boundary:** record retrieval timestamps and
   publisher metadata, verify upstream checksums/signatures where available, and make
   clear what the hash does and does not attest.
3. **Broaden parser coverage:** add OCR or a document-AI path for scanned PDFs and test
   against varied real-world layouts.
4. **Make extraction uncertainty explicit:** retain confidence/method metadata, support
   review/feedback, and use the optional LLM path only with clear budgets and evaluation.
5. **Support remote use safely:** add a supported HTTP MCP transport, authentication,
   authorization, rate limiting, and deployment documentation before exposing it beyond
   a trusted local machine.
6. **Improve operations:** add structured logs, resource limits, backup/restore guidance,
   database migrations, and a one-command development launch option.
7. **Scale deliberately:** benchmark ingestion and query latency as the corpus grows;
   consider incremental indexing, background jobs, and a dedicated vector service only
   if measurements justify the added operational complexity.
8. **Improve user-facing trust cues:** show whether evidence is current, verified, or
   only a contradiction candidate, and help users inspect why a candidate was generated.

## 11. Likely supervisor questions

**“Does this replace the LLM?”**  
No. It supplies document retrieval and evidence tools to an LLM or user. The model still
does the conversational reasoning; DocuSense helps ground that reasoning in specific,
checkable passages.

**“Can the system guarantee that an answer is correct?”**  
No. It can make evidence traceable and detect changes to stored text, but retrieval,
extraction, interpretation, source authority, and the final answer can still be wrong.

**“Why use MCP?”**  
MCP provides a standard tool interface that compatible AI hosts can call, instead of
requiring a separate custom integration for every tool. A REST API is also provided for
non-MCP clients.

**“Why not put the entire document in the prompt?”**  
Long documents and version histories consume context and make it harder to target the
right version and cite precise evidence. Search plus focused context assembly keeps the
retrieved material bounded and traceable.

**“What is the main contribution?”**  
The combination of version-aware retrieval, byte-range citations, reproducible integrity
checks, version comparison, and an agent-facing MCP interface in one document evidence
layer.

## 12. Closing statement

> DocuSense turns long, changing technical documents into version-specific evidence that
> people can inspect and compatible AI clients can retrieve and verify. The current
> implementation demonstrates that workflow locally; accuracy measurement, broader
> document coverage, and secure remote deployment are the next steps.
