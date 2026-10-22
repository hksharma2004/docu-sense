# DocuSense

A verifiable and version-native document layer for AI agents, exposed over MCP.
B.Tech IT (VIIth Sem) project, USICT, GGSIPU. See [PLAN.md](PLAN.md) for the full build plan.

## Status

Week 1 (ingestion + provenance) is done:

- PDF (fixed-width and xml2rfc-styled layouts) and Markdown parsing into a canonical text
- Section tree (numbered, appendix and unnumbered headings; TOC skipped), paragraph/table spans
- Every span stored with byte offsets + SHA-256 in an append-only Postgres schema
- Content-addressed blob store for source files and canonical texts
- `verify` (re-hash spans) and `verify --deep` (re-parse source, check determinism)

## Quick start

```bash
docker compose up -d                       # Postgres 17 + pgvector on :5433
uv sync
uv run python scripts/fetch_corpus.py      # downloads RFCs, writes corpus/manifest.yaml
uv run docusense ingest                    # ingest every version in the manifest
uv run docusense verify --deep             # re-hash every span + re-parse every source
uv run pytest
```

Other commands:

```bash
uv run docusense stats                     # per-version pages / sections / spans
uv run docusense sections smtp@rfc5321     # section map with pages and byte ranges
uv run docusense verify --span 123         # verification record for one span
uv run docusense db reset --yes            # dev only: wipe all data
```

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
