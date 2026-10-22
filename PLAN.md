# DocuSense — Build Plan (Mid-Term Edition)

> **DocuSense: A Verifiable and Version-Native Document Layer for AI Agents**
> B.Tech IT, VIIth Sem, USICT (GGSIPU). Harsh Kumar Sharma (00916401523). Guide: Ms. Ritika Khanna

This plan builds the project from scratch, following the approved synopsis. It is sized for a **3–4 week mid-term**:
every synopsis component gets a **thin but working** version. The work that deepens them comes **after mid-term** (§10).

---

## 0. Guiding rules (from the synopsis)

1. **MCP-first.** The main interface is an MCP server with small, composable tools. It is not a single `search → chunks` call.
2. **Deterministic-first.** Parsing, layout heuristics, regex and rules run first. The LLM is a *bounded fallback*, and each use records the model ID, prompt hash, method and confidence.
3. **Every span is verifiable.** Each span stores a `(version_id, start_byte, end_byte, sha256, parser_version)` record. Anyone can re-hash the span to check it.
4. **Append-only versions.** A new version never overwrites old evidence. Diff, blame and contradictions read from this history.
5. **Contradictions are surfaced, never auto-resolved.** Both evidence records are kept.
6. **Fair evaluation.** All configurations use the same agent model and the same budget.

---

## 1. Decisions locked for mid-term

| Area | Choice | Why |
|---|---|---|
| Language / env | Python **3.12** via `uv` (system has 3.14, but some ML wheels lag) | Reproducible, fast installs |
| API | **FastAPI** (REST for the viewer) | Synopsis |
| MCP | **MCP Python SDK** (`mcp`, `FastMCP`), stdio transport | Synopsis |
| PDF parsing | **PyMuPDF** (`pymupdf`): page, block, font and bbox info | Synopsis |
| Markdown parsing | `markdown-it-py` (token line maps → byte offsets) | Deterministic, gives offsets |
| DB | **PostgreSQL + pgvector** in Docker (`pgvector/pgvector:pg17`) on port **5433** | Synopsis. Avoids a clash with Homebrew PG 18 on 5432 |
| Lexical search | **BM25** via `bm25s` (embedded, persisted to disk) | Synopsis says "embedded full-text layer" |
| Embeddings | **Local** `fastembed` + `BAAI/bge-small-en-v1.5` (384-dim) | Groq/OpenRouter have no embedding API. Free, offline, needs no torch |
| LLM fallback extraction | **Groq** (e.g. `llama-3.3-70b-versatile`), behind a flag | Fast, cheap, bounded |
| Evaluation agent | **OpenRouter** (Owl Alpha model ID in `.env`), with a Groq model as backup | Your choice. All configs use the same model |
| Span store | Content-addressed files: `store/blobs/sha256/ab/<hash>` | Synopsis (filesystem for MVP) |
| Viewer | **Next.js + Tailwind**, read-only (span highlight + version diff) | Synopsis. No chat backend |
| Corpus | **IETF RFCs** (PDF) + a tiny synthetic Markdown policy set (§3) | RFCs: versioned via "obsoletes" and full of cross-refs |

> ⚠️ OpenRouter "alpha"/stealth models can be renamed or removed without notice. Pin the exact model ID in `.env` and record it in every benchmark result file. If it disappears, re-run **all** configs on the backup model so the comparison stays fair.

---

## 2. Architecture

```
                ┌─────────────────────────── INGESTION (offline) ───────────────────────────┐
 corpus/raw ──► │ parse (PDF/MD) → canonical text + page map → section tree → spans          │
 manifest.yaml  │ → deterministic extraction (refs, defs, claims, tables) → [LLM fallback]   │
                │ → SHA-256 anchor every span → append-only version record → BM25 + vectors  │
                └───────────────────────────────┬───────────────────────────────────────────┘
                                                ▼
                       PostgreSQL+pgvector   +   store/blobs (content-addressed)
                                                ▼
                         services/ (one query layer, shared by everything)
                 ┌──────────────────────┬──────────────────────┐
                 ▼                      ▼                      ▼
          mcp_server.py (stdio)     api.py (FastAPI)       bench/ (harness)
          ← AI agents               ← viewer (Next.js)     ← baselines + scoring
```

### 2.1 Canonical text and byte offsets (the core idea)

- On ingest, every version produces one **canonical text**: UTF-8, NFC-normalised, `\n` line endings, with page headers and footers removed.
- The canonical text is stored as a blob under its own SHA-256 (`text_sha256`). The original file's hash (`source_sha256`) is stored too.
- A **page map** records the byte offset where each page starts, so any span can be mapped back to a page.
- **Every span is a byte range `[start, end)` into the canonical text**, plus `sha256(text[start:end])`.
- **`verify_span`**: load the blob by `text_sha256`, slice the bytes, re-hash, and compare with the stored hash.
- **`verify_span(deep=True)`**: re-run the parser (same `parser_version`) on the original file and check that the result still hashes to `text_sha256`. This proves extraction is deterministic.
- **Citation format:** `ds://smtp@rfc5321#§4.5.3.1:b10234-10391:sha256=ab12…`

---

## 3. Corpus (mid-term size: 14 RFCs + 3 Markdown docs = 17 versions)

`corpus/manifest.yaml` maps each **logical document** to its ordered **versions**. In RFC terms, an obsoleting RFC counts as the next version.

| Logical doc | Versions (old → new) | Gives us |
|---|---|---|
| `smtp` | RFC 2821 → RFC 5321 | Section/claim diff, blame, numeric facts ("1000 octets") |
| `imf` | RFC 2822 → RFC 5322 | Diff, definitions (ABNF terms) |
| `uri` | RFC 2396 → RFC 3986 | Diff, heavily cited by others |
| `tls` | RFC 5246 → RFC 8446 | Large rewrite, a hard diff case |
| `bcp14` | RFC 2119 | Defines MUST/SHOULD. Definition lookup |
| `bcp14-case` | RFC 8174 (updates 2119, not a version of it) | Reference target |
| `oauth2` | RFC 6749 | Hub doc for affected-documents |
| `oauth2-bearer` | RFC 6750 | Refs → 6749, 3986 |
| `pkce` | RFC 7636 | Refs → 6749 |
| `oauth-security-bcp` | RFC 9700 (**official v3 PDF**) | Updates 6749/6750. Styled-PDF layout, affected-docs |
| `mail-policy` *(synthetic, Markdown)* | v1 → v2 | Markdown ingestion, planted contradictions with RFC 5321 |
| `oauth-profile` *(synthetic, Markdown)* | v1 | Planted conflict with RFC 6749/7636 |

- **PDF sources (decided in week 1):** the RFC Editor publishes official PDFs only for v3-format RFCs (RFC 8650 onward), and datatracker's PDF endpoint blocks scripts (403). So `scripts/fetch_corpus.py` uses the official PDF when one exists (RFC 9700). Otherwise it downloads the official paginated `.txt` and renders it to a fixed-width PDF (one RFC page per PDF page, byte-for-byte deterministic, the same layout datatracker serves). The `.txt` URL and SHA-256 are recorded under `origin` in the manifest. The parser therefore handles two real PDF layouts: **mono** (rendered) and **styled** (xml2rfc/WeasyPrint).
- **Why the synthetic Markdown set:** the synopsis requires *Markdown ingestion* and *contradiction metrics*. Real RFCs rarely contradict each other in a way we can label, so 2–3 short hand-written "organisation policy" docs restate RFC rules with deliberate conflicts (for example "lines MAY exceed 2000 octets" against RFC 5321's 1000). The synopsis explicitly allows "a controlled synthetic corpus". Keep each doc short (1–2 pages).

---

## 4. Repository layout

```
docusense/
├── PLAN.md
├── README.md
├── pyproject.toml              # uv project, Python 3.12
├── docker-compose.yml          # pgvector/pgvector:pg17 on :5433
├── .env.example
├── corpus/
│   ├── manifest.yaml
│   ├── raw/                    # *.pdf, *.md  (git-ignored except synthetic md)
│   └── synthetic/              # mail-policy-v1.md, mail-policy-v2.md, oauth-profile-v1.md
├── store/blobs/                # content-addressed canonical texts (git-ignored)
├── src/docusense/
│   ├── config.py               # pydantic-settings, reads .env
│   ├── db/
│   │   ├── schema.sql
│   │   └── conn.py             # psycopg pool
│   ├── store/blobs.py          # put(bytes)->sha, get(sha)->bytes
│   ├── ingest/
│   │   ├── pdf_parser.py       # PyMuPDF → lines + page map, header/footer strip
│   │   ├── md_parser.py        # markdown-it → headings/paragraphs with byte offsets
│   │   ├── normalize.py        # NFC, newlines, deterministic
│   │   ├── sections.py         # heading detection → section tree, skip TOC
│   │   ├── spans.py            # paragraph/table spans + hashing
│   │   └── pipeline.py         # orchestrates one version ingest (idempotent)
│   ├── extract/
│   │   ├── references.py       # regex + reference-list parsing + resolution
│   │   ├── definitions.py      # terminology-section + pattern mining
│   │   ├── claims.py           # BCP14 requirements, numeric facts, exclusions
│   │   ├── tables.py           # ASCII-table detection (span kind = table)
│   │   └── llm_fallback.py     # bounded Groq call, logs model_id/prompt_hash/confidence
│   ├── index/
│   │   ├── bm25.py
│   │   └── embed.py
│   ├── versions/
│   │   ├── diff.py             # section / claim / reference diff
│   │   ├── blame.py
│   │   └── conflicts.py        # contradiction candidates → conflicts table
│   ├── context/assemble.py     # verify → version check → contradiction scan → pack
│   ├── services.py             # all query functions (used by MCP + API + bench)
│   ├── mcp_server.py
│   ├── api.py
│   └── cli.py                  # `docusense ingest|reindex|verify|serve-mcp|serve-api`
├── viewer/                     # Next.js + Tailwind
├── bench/
│   ├── questions.jsonl
│   ├── baselines/
│   │   ├── fs_mcp.py           # raw filesystem: list_files, grep, read_file
│   │   ├── vector_rag_mcp.py   # single search(query)->chunks
│   │   └── graphrag_mcp.py     # post-midterm
│   ├── agent_runner.py         # MCP client + OpenAI-compatible tool loop
│   ├── score.py
│   └── results/
└── tests/
```

---

## 5. Data model (`schema.sql`)

```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE documents (
  id            TEXT PRIMARY KEY,          -- 'smtp'
  title         TEXT NOT NULL,
  source_family TEXT NOT NULL              -- 'rfc' | 'synthetic'
);

CREATE TABLE versions (                    -- APPEND-ONLY
  id             TEXT PRIMARY KEY,         -- 'smtp@rfc5321'
  document_id    TEXT REFERENCES documents(id),
  label          TEXT NOT NULL,            -- 'rfc5321'
  seq            INT  NOT NULL,            -- 1,2,3… order within document
  format         TEXT NOT NULL,            -- 'pdf' | 'md'
  source_sha256  TEXT NOT NULL UNIQUE,     -- hash of original file
  text_sha256    TEXT NOT NULL,            -- hash of canonical text blob
  page_map       JSONB,                    -- [byte offset of each page start]
  parser_version TEXT NOT NULL,            -- 'docusense-parser/0.1.0'
  ingested_at    TIMESTAMPTZ DEFAULT now(),
  UNIQUE (document_id, seq)
);

CREATE TABLE sections (
  id          BIGSERIAL PRIMARY KEY,
  version_id  TEXT REFERENCES versions(id),
  parent_id   BIGINT REFERENCES sections(id),
  number      TEXT,                        -- '4.5.3.1' / 'A'
  title       TEXT,
  level       INT,
  ordinal     INT,
  start_byte  INT, end_byte INT,
  page_start  INT, page_end INT,
  sha256      TEXT NOT NULL
);

CREATE TABLE spans (
  id                BIGSERIAL PRIMARY KEY,
  version_id        TEXT REFERENCES versions(id),
  section_id        BIGINT REFERENCES sections(id),
  kind              TEXT NOT NULL,         -- paragraph | table | sentence
  start_byte        INT NOT NULL, end_byte INT NOT NULL,
  page              INT,
  sha256            TEXT NOT NULL,
  text              TEXT NOT NULL,
  parser_version    TEXT NOT NULL,
  extraction_method TEXT NOT NULL,         -- 'layout' | 'regex' | 'llm'
  model_id          TEXT, prompt_hash TEXT, confidence REAL
);

CREATE TABLE span_embeddings (             -- separate so spans stay strictly append-only
  span_id   BIGINT PRIMARY KEY REFERENCES spans(id),
  model     TEXT NOT NULL,
  embedding vector(384) NOT NULL
);

CREATE TABLE refs (
  id              BIGSERIAL PRIMARY KEY,
  span_id         BIGINT REFERENCES spans(id),
  raw             TEXT,                    -- 'Section 3.4 of [RFC5322]'
  target_doc      TEXT,                    -- 'imf' (NULL = internal)
  target_section  TEXT,                    -- '3.4'
  resolved_section_id BIGINT REFERENCES sections(id),
  status          TEXT                     -- resolved | unresolved | external
);

CREATE TABLE definitions (
  id BIGSERIAL PRIMARY KEY, term TEXT, term_norm TEXT,
  span_id BIGINT REFERENCES spans(id), version_id TEXT REFERENCES versions(id),
  method TEXT
);

CREATE TABLE claims (
  id BIGSERIAL PRIMARY KEY,
  span_id     BIGINT REFERENCES spans(id),   -- sentence-level span
  version_id  TEXT REFERENCES versions(id),
  claim_type  TEXT,        -- requirement | numeric | exclusion | procedure
  subject     TEXT, subject_key TEXT,        -- normalised for matching
  modality    TEXT,        -- MUST | MUST NOT | SHOULD | SHOULD NOT | MAY | NULL
  value_num   DOUBLE PRECISION, unit TEXT,
  method      TEXT, model_id TEXT, prompt_hash TEXT, confidence REAL
);

CREATE TABLE conflicts (                    -- both sides kept, never resolved
  id BIGSERIAL PRIMARY KEY,
  claim_a BIGINT REFERENCES claims(id), claim_b BIGINT REFERENCES claims(id),
  reason TEXT,             -- 'modality_mismatch' | 'value_mismatch'
  detected_at TIMESTAMPTZ DEFAULT now()
);

-- append-only enforcement
CREATE FUNCTION forbid_mutation() RETURNS trigger AS $$
BEGIN RAISE EXCEPTION 'append-only table: % not allowed', TG_OP; END $$ LANGUAGE plpgsql;
CREATE TRIGGER versions_append_only BEFORE UPDATE OR DELETE ON versions
  FOR EACH ROW EXECUTE FUNCTION forbid_mutation();
CREATE TRIGGER spans_append_only BEFORE UPDATE OR DELETE ON spans
  FOR EACH ROW EXECUTE FUNCTION forbid_mutation();
```

The real schema lives in `src/docusense/db/schema.sql`. Sections are append-only too.

---

## 6. Component specs

### 6.1 Structural parsing (deterministic)
- **PDF:** use PyMuPDF `page.get_text("dict")` to get lines with bbox and font. Lines that repeat at the top or bottom of most pages are **headers/footers** (in RFCs, `RFC 5321  SMTP  October 2008` and `Klensin  Standards Track  [Page 7]`). Strip them and record the page boundaries.
- **Headings:** a numbered line at the left margin, matching `^(\d+(\.\d+)*|[A-Z](\.\d+)*)\.?\s{1,3}\S` and followed by text. Skip the **Table of Contents** block (lines ending in dot leaders or page numbers).
- **Section tree:** heading level = number depth. Each section's byte range runs to the next heading at the same or a higher level.
- **Paragraph spans:** blank-line separated blocks inside a section.
- **Tables:** blocks where most lines contain `|`, `+--` or several column-aligned runs of 2+ spaces become `kind=table`. Mid-term detects them only; no cell parsing.
- **Markdown:** `#` levels give sections. Paragraphs, tables and code blocks come from token `map` line ranges, converted to byte offsets.
- **Idempotent:** re-ingesting a file with an existing `source_sha256` does nothing.

### 6.2 Deterministic extraction
- **References (regex):** `Section 4.1.2`, `Section 3 of [RFC5322]`, `[RFC5322], Section 3.4`, `RFC 2119`, `[RFC2119]`, `Appendix A`, plus bracket tags like `[SMTP-EXT]`. These are resolved through the document's own **References section**, which maps each tag to an RFC number.
- **Resolution:** an internal ref resolves to a section in the same version. An external ref resolves to the corpus doc containing that RFC; versioned docs resolve to the version named, or else the latest. If the target is outside the corpus, `status=external`. Otherwise it is `unresolved` and recorded.
- **Definitions:** the paragraphs inside sections titled *Terminology / Definitions / Conventions*, plus patterns: `"X": …`, `The term "X" …`, `X is defined as`, `X means`, and the BCP 14 keyword list from RFC 2119.
- **Claims:**
  - *Requirement:* a sentence containing an uppercase BCP 14 keyword. `modality` is that keyword and `subject` is the noun phrase before it (heuristic: text from the sentence start or the last clause boundary up to the keyword).
  - *Numeric:* a number followed by a unit (`octets|characters|bytes|seconds|minutes|hours|days`), for example "maximum total length of a text line … is 1000 octets".
  - *Exclusion:* `MUST NOT`, `SHALL NOT`, `is not permitted`, `except`.
  - `subject_key` = lowercased, stop-words removed, lemma-light, used for cross-doc matching.
- **LLM fallback (bounded):** used only for requirement sentences where the subject heuristic fails. The cap is **N=20 calls per version**, the setting is `--llm-fallback` (off by default) and the model is Groq. Each claim stores `model_id`, `sha256(prompt)`, `method='llm'` and `confidence`.

### 6.3 Indexing
- **BM25** over paragraph spans, using `bm25s` persisted to `store/index/bm25/`.
- **Dense** vectors are written to `spans.embedding` with an HNSW index (`vector_cosine_ops`).
- **Claim index** = the `claims` table, with btree indexes on `subject_key`, `modality` and `claim_type`.

### 6.4 Version intelligence
- **Section diff:** align the sections of v_old and v_new by number first, then by title similarity (`difflib` ratio ≥ 0.8). Status = `added | removed | modified | unchanged` (unchanged means the normalised-text hashes are equal). Modified sections get a sentence-level diff.
- **Claim diff:** match claims by `subject_key`, then report `added | removed | modality_changed | value_changed`.
- **Reference diff:** set difference of the resolved targets.
- **Blame:** given a span or sentence in version N, walk back through the versions to the **earliest** one that contains it. Match by exact normalised hash, or fuzzy ratio ≥ 0.9. Return the introducing version.
- **Affected documents:** `refs` where `target_doc = X`. These are the docs that may need review when X changes.
- **Contradictions:** pair claims with the same `subject_key` across **different documents** (or the latest versions). A different `modality` (MUST vs MUST NOT or MAY) or a different `value_num` with the same unit gives a `conflicts` row. Both rows are kept. Optionally, a Groq judge confirms the top candidates, capped and logged.

### 6.5 Context assembly (implements Figure 2 of the synopsis)
`assemble_context(span_ids, token_budget)` runs these steps:
1. **Provenance verify** each span. On a SHA-256 mismatch, reject the span, add it to `rejected[]` and suggest a re-fetch.
2. **Version check.** If the span's version is not the latest, attach the matching section from the newest version plus a short section/claim diff.
3. **Contradiction scan.** Append any spans that conflict with the span.
4. **Budget-aware packing.** Order by score (requested span > newer version > conflict), estimate tokens at chars/4, and pack greedily. Over-budget spans are truncated to their first sentences and marked `truncated=true`.
5. Return the evidence blocks, each with its **citation string**.

---

## 7. MCP tool surface (`mcp_server.py`)

Every tool takes an optional `max_tokens` (the response budget) and returns JSON with citations. That covers "dispatch by task type + budget".

| # | Tool | Synopsis capability |
|---|---|---|
| 1 | `list_documents()` | navigation |
| 2 | `get_section_map(doc, version?)` | navigation / section map |
| 3 | `read_section(doc, section, version?)` | navigation / evidence |
| 4 | `search(query, mode=lexical\|semantic\|hybrid, doc?, k=5)` | lexical + semantic search |
| 5 | `search_claims(subject?, modality?, claim_type?, doc?)` | claim search |
| 6 | `resolve_reference(span_id)` | reference resolution |
| 7 | `lookup_definition(term, doc?)` | definition lookup |
| 8 | `get_evidence(span_id)` | evidence retrieval (+ `verified`, `is_latest` flags) |
| 9 | `verify_span(span_id, deep=false)` | provenance verification |
| 10 | `list_versions(doc)` | versioning |
| 11 | `diff_versions(doc, from, to, level=section\|claim\|reference)` | version comparison |
| 12 | `blame(doc, span_id\|text)` | span blame |
| 13 | `find_affected_documents(doc)` | affected-document discovery |
| 14 | `find_contradictions(doc?, subject?)` | contradiction surfacing |
| 15 | `assemble_context(span_ids, token_budget)` | context assembly |

Test the server with **MCP Inspector** (`npx @modelcontextprotocol/inspector`) and connect it to Claude Desktop or Cursor for the live demo.

---

## 8. Evaluation harness (`bench/`)

### 8.1 Questions (mid-term: **30**; final: 100+)
`questions.jsonl` has 6 of each type: **structural, multi-hop, temporal/version, contradiction, reference-following**.
```json
{"id":"T03","type":"temporal","question":"What did RFC 5321 change about … compared to RFC 2821?",
 "gold_answer":"…","gold_citations":[{"version":"smtp@rfc5321","section":"4.5.3.1"}],
 "answer_keywords":["1000","octets"]}
```

### 8.2 Configurations (same agent model, same budget: max **15 tool calls**, max **60k tokens**)
| Config | Tools exposed | Mid-term? |
|---|---|---|
| Raw filesystem MCP | `list_files`, `grep`, `read_file(path, offset, limit)` over canonical `.txt` | ✅ |
| Vector RAG-MCP | `search(query) → top-k 512-token chunks` (same embedding model) | ✅ |
| GraphRAG-MCP | Microsoft GraphRAG index + `local_search`/`global_search` | ⏭ post-midterm |
| **DocuSense** | the 15 tools above | ✅ |

`agent_runner.py`: connects through the MCP Python SDK client (stdio), converts MCP tools to OpenAI-format function schemas, and runs the tool loop against OpenRouter or Groq (both are OpenAI-compatible). It logs every call, prompt/completion tokens from `usage`, wall-clock latency and the final answer. The system prompt requires citations as quoted text plus a source.

### 8.3 Metrics (`score.py`)
| Metric | How |
|---|---|
| Answer correctness | keyword match + LLM-judge (Groq, fixed prompt, temp 0) |
| Citation exact match | cited section == gold section (baseline quotes are mapped to sections by string-matching into the canonical text) |
| Span verification rate | % of citations whose quoted text re-hashes / exactly matches the source |
| Tool calls, tokens, latency | from the runner logs |
| Multi-hop success | correctness on the multi-hop + reference-following subset |
| Contradiction detection | recall/precision on the planted conflicts |
| Version-diff accuracy | correctness on the temporal subset + `diff_versions` vs a hand-labelled section diff for smtp and uri |

Output: `bench/results/<date>_<model>.json` + a markdown table + 2 bar charts (tokens, tool calls).
Results are cached per (config, question, model) so Groq/OpenRouter rate limits don't force full re-runs.

---

## 9. Mid-term timeline (4 weeks; week 4 can compress into week 3 if you only have 3)

### Week 1 — Foundations: ingest + provenance ✅ DONE
- [x] `uv init`, `pyproject.toml`, `docker-compose.yml`, `.env.example`, `schema.sql` applied
- [x] `scripts/fetch_corpus.py` downloads the RFCs (official PDF or rendered from .txt) and writes `manifest.yaml`. 3 synthetic Markdown docs + `planted_conflicts.yaml` gold labels
- [x] `blobs.py`, `normalize.py`, `pdf_parser.py` (baseline line rebuild, header/footer strip, page map, mono + styled layouts)
- [x] `sections.py` (numbered/appendix/unnumbered headings, inline-body headings, TOC skip, section tree) and `md_parser.py`
- [x] `pipeline.py`: ingest one version end-to-end in one transaction, idempotent (span building is in `pipeline.py`, so there is no separate `spans.py`)
- [x] `provenance.py` `verify_span` (+ deep verify), CLI `docusense ingest | verify | sections | stats | db init/reset`
- [x] Tests (24): heading rules, parsers, render determinism, tampered blob fails, append-only triggers, idempotent re-ingest
- **Exit check met:** 17 versions ingested (14 RFC PDFs + 3 Markdown) into 5956 spans. `docusense verify --deep` gives **5956/5956 (100%)**. Every TOC entry in every RFC was detected as a section.

### Week 2 — Extraction, search, MCP
- [ ] `references.py` (regex + reference-list mapping + resolution), `definitions.py`, `claims.py`, `tables.py`
- [ ] `llm_fallback.py` (Groq, capped, logged), off by default
- [ ] `bm25.py`, `embed.py`, hybrid search (reciprocal rank fusion)
- [ ] `services.py` + `mcp_server.py` tools 1–9
- [ ] Try it in MCP Inspector and in Claude Desktop/Cursor
- **Exit check:** an agent answers "What does RFC 6750 say about the URI syntax it references?" by following `resolve_reference` to RFC 3986, with a verified citation.

### Week 3 — Versions, contradictions, context, viewer
- [ ] `diff.py` (section/claim/reference), `blame.py`, affected docs, `conflicts.py`
- [ ] `assemble.py` (Figure 2 flow), MCP tools 10–15
- [ ] `api.py` (FastAPI): `/documents`, `/versions/{id}/sections`, `/spans/{id}`, `/diff`, `/verify/{span}`
- [ ] `viewer/`: (1) document page with section tree and text, `?span=` highlights the span and shows a ✅/❌ verify badge; (2) diff page, side-by-side sections coloured added/removed/modified
- **Exit check:** `diff_versions('smtp','rfc2821','rfc5321')` gives a sensible section diff, and the planted contradictions show up in `find_contradictions`.

### Week 4 — Benchmark, report, demo
- [ ] Write 30 questions with gold citations (spread across the corpus)
- [ ] `fs_mcp.py`, `vector_rag_mcp.py`, `agent_runner.py`, `score.py`
- [ ] Run 3 configs × 30 questions and generate the results table and charts
- [ ] README (setup in ≤ 5 commands), mid-term slides, rehearse the demo
- **Exit check:** a results table with real numbers, and a demo that runs from a clean `docker compose up`.

### Mid-term demo script (~7 min)
1. `docker compose up`, then `docusense ingest`, showing the section map of RFC 5321.
2. In an agent (Claude Desktop/Cursor + DocuSense MCP), ask a reference-following question. Show the tool calls and the cited answer.
3. Click the citation in the viewer: highlighted span, ✅ verified.
4. **Poisoning demo:** flip one byte in a blob → ❌ verify fails → `assemble_context` rejects the span.
5. `diff_versions` smtp 2821→5321 on the viewer's diff page, plus `blame` on one sentence.
6. `find_contradictions`: the synthetic policy conflicts with RFC 5321, with both spans shown.
7. Benchmark table: DocuSense vs raw FS vs vector RAG (tokens, tool calls, citation match).

---

## 10. After mid-term (final submission)

- GraphRAG-MCP baseline (Microsoft `graphrag`, indexed with the same LLM provider)
- Benchmark grows to 100+ questions, plus several runs per config to report variance
- Better table extraction, better claim subject extraction, LLM-fallback coverage study (deterministic vs LLM share)
- More version chains (HTTP 7230-series → 9110/9112), internet-draft revisions (-00…-NN) as true versions
- Final report, ablations (e.g. DocuSense without `assemble_context`, without reference resolution)

**Explicitly out of scope** (synopsis "Future Scope"): DOCX/PPTX/HTML ingestion, OCR, domain ontology linking, multi-user permissions, graph-backed multi-hop traversal.

---

## 11. Synopsis traceability (for evaluators)

| Synopsis objective | Where in this plan | Mid-term status target |
|---|---|---|
| Fine-grained MCP document layer | §7, `mcp_server.py` | ✅ 15 tools |
| Ingest PDF + Markdown; pages, sections, tables, refs, terms | §6.1–6.2 | ✅ (tables: detection only) |
| Lexical, semantic, claim-level retrieval | §6.3, tools 4–5 | ✅ |
| Cross-ref resolution, definition lookup, navigation | §6.2, tools 1–3, 6–7 | ✅ |
| Byte offsets + SHA-256 + version + parser provenance | §2.1, §5 | ✅ |
| Append-only versioning, section/claim diff, blame, affected docs, contradictions | §6.4, tools 10–14 | ✅ thin |
| Evaluation vs raw FS, vector RAG-MCP, GraphRAG-MCP | §8 | ✅ 2 of 3 baselines, GraphRAG in final |
| Figure 1 (ingestion pipeline) | §2, §6.1–6.3 | ✅ |
| Figure 2 (query-time workflow) | §6.5 `assemble_context` | ✅ |

---

## 12. Risks and mitigations

| Risk | Mitigation |
|---|---|
| RFC PDF headers/footers break heading detection | Strip repeated lines per page. Unit-test on 5321 and 8446 |
| Free-tier Groq/OpenRouter rate limits during the benchmark | Cache responses, run sequentially, keep 30 questions for mid-term |
| Stealth model disappears | Pin the ID, keep a Groq backup, and re-run all configs on the same model |
| Too much scope for 3–4 weeks | Week exit checks. Cut order if late: viewer diff page → blame → LLM fallback |
| Claim subject heuristic is noisy | It only has to work for planted contradictions and diff demos at mid-term. Measure and improve later |

---

## 13. Quick start (target README)

```bash
cp .env.example .env              # add GROQ_API_KEY, OPENROUTER_API_KEY, AGENT_MODEL
docker compose up -d              # postgres+pgvector on :5433
uv sync
uv run python scripts/fetch_corpus.py
uv run docusense ingest corpus/manifest.yaml
uv run docusense serve-mcp        # stdio MCP server
uv run docusense serve-api        # FastAPI on :8000 ; cd viewer && npm run dev
```

`.env.example`
```
DATABASE_URL=postgresql://docusense:docusense@localhost:5433/docusense
EMBED_MODEL=BAAI/bge-small-en-v1.5
GROQ_API_KEY=
EXTRACT_MODEL=llama-3.3-70b-versatile
OPENROUTER_API_KEY=
AGENT_PROVIDER=openrouter
AGENT_MODEL=<exact Owl Alpha model id from openrouter.ai>
AGENT_MAX_TOOL_CALLS=15
AGENT_MAX_TOKENS=60000
```
