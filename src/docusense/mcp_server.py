"""DocuSense MCP server. Fine-grained, citation-first document tools for AI agents.

Run:  docusense serve-mcp                 (stdio: Claude Desktop, Claude Code, Cursor, VS Code)
      docusense serve-mcp --http          (Streamable HTTP on 127.0.0.1:8765/mcp)

DOCUSENSE_TOOLS=core exposes a smaller tool set for agents with tight context budgets.
"""

import functools
import threading
from pathlib import Path
from typing import Any

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp_types import ToolAnnotations

from docusense.config import get_settings
from docusense.db.conn import connect, init_schema
from docusense.services import DocuSense

INSTRUCTIONS = """DocuSense is a verifiable, versioned document store. Every passage (span) it returns carries a
citation like ds://<doc>@<version>#§<section>:b<start>-<end> and a SHA-256 of its exact bytes.

Typical workflow:
  1. list_documents (or the docusense://documents resource) to see what is available,
  2. search (hybrid by default) or search_claims / lookup_definition to find evidence,
  3. read_section for surrounding text; resolve_reference to follow "Section X of …" links,
  4. get_evidence (verifies the hash) or assemble_context before answering.
Rules: cite the returned citations verbatim; never cite a span whose verified=false. If a result has
`newer_version`, that passage is from an obsolete version: check the newer one before answering.
Documents change over time as new versions (v1, v2, …): use diff_versions / blame to explain what changed,
and find_contradictions to surface conflicting statements (both sides are evidence; do not pick a winner).
New files can be added with add_document (local paths); it runs in the background, poll ingest_status."""

server = MCPServer("docusense", instructions=INSTRUCTIONS)

READ_ONLY = ToolAnnotations(read_only_hint=True, idempotent_hint=True, open_world_hint=False)
_local = threading.local()
_schema_ready = False
_schema_lock = threading.Lock()


def _ds() -> DocuSense:
    """One connection per thread: the HTTP transport runs tool calls concurrently."""
    global _schema_ready
    ds = getattr(_local, "ds", None)
    if ds is None:
        conn = connect()
        with _schema_lock:
            if not _schema_ready:
                init_schema(conn)  # idempotent; makes a fresh install usable immediately
                _schema_ready = True
        conn.autocommit = True  # every call sees documents added since the server started
        ds = _local.ds = DocuSense(conn)
    return ds


def tool(core: bool = False, annotations: ToolAnnotations | None = READ_ONLY):
    """Register a tool (skipped when DOCUSENSE_TOOLS=core and the tool isn't core).

    Expected failures (unknown document, bad argument, missing file) become clean tool errors the agent
    can act on, instead of tracebacks.
    """
    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            try:
                return fn(*args, **kwargs)
            except (ValueError, LookupError, OSError) as e:  # NotFound is a ValueError
                raise ToolError(str(e)) from e

        if core or get_settings().tools.strip().lower() != "core":
            server.tool(annotations=annotations)(wrapper)
        return fn

    return decorator


# ── orient ─────────────────────────────────────────────────────────────────────

@tool(core=True)
def list_documents() -> dict[str, Any]:
    """List every document with its versions (oldest→newest) and which version is latest."""
    return _ds().list_documents()


@tool(core=True)
def get_section_map(doc: str, version: str | None = None, max_depth: int = 3, max_tokens: int = 3000) -> dict[str, Any]:
    """Table of contents of a document version: section numbers, titles, levels and page ranges.

    doc: document id ('employee-handbook'), version id ('employee-handbook@v2') or, for RFCs, 'RFC 5321'.
    Defaults to the latest version. max_depth: deepest heading level to include (1 = top-level only).
    """
    return _ds().get_section_map(doc, version, max_depth, max_tokens)


@tool(core=True)
def read_section(doc: str, section: str, version: str | None = None, include_subsections: bool = False,
                 max_tokens: int = 3000) -> dict[str, Any]:
    """Read the paragraphs of one section, each with a citation and SHA-256.

    section: a section number ('4.5.3.1', 'A.1') or part of a title ('Terminology').
    include_subsections: also return text of nested subsections.
    """
    return _ds().read_section(doc, section, version, include_subsections, max_tokens)


# ── find evidence ────────────────────────────────────────────────────────────

@tool(core=True)
def search(query: str, mode: str = "hybrid", doc: str | None = None, k: int = 5, max_tokens: int = 2500) -> dict[str, Any]:
    """Find passages relevant to a query.

    mode: 'lexical' (BM25: exact terms, numbers, identifiers), 'semantic' (embeddings: paraphrased
    questions) or 'hybrid' (both, fused with reciprocal rank fusion).
    doc: optional filter; a document id searches all its versions, a version id only that version.
    """
    return _ds().search(query, mode, doc, k, max_tokens)


@tool(core=True)
def search_claims(topic: str | None = None, subject: str | None = None, modality: str | None = None,
                  claim_type: str | None = None, doc: str | None = None, k: int = 10,
                  max_tokens: int = 2500) -> dict[str, Any]:
    """Search normative statements extracted from the documents (sentence-level evidence).

    topic: words describing what the statement is about ('annual leave carry over', 'text line length').
    subject: who it applies to ('employees', 'clients', 'authorization server').
    modality: MUST, MUST NOT, SHOULD, SHOULD NOT, MAY (synonyms like SHALL / REQUIRED / must not accepted).
    claim_type: requirement | exclusion | numeric. Numeric claims include value and unit (e.g. 1000 octet).
    """
    return _ds().search_claims(topic, subject, modality, claim_type, doc, k, max_tokens)


@tool()
def resolve_reference(span_id: int | None = None, reference: str | None = None, doc: str | None = None,
                      max_tokens: int = 3000) -> dict[str, Any]:
    """Follow cross-references to their target section, with a preview of the target text.

    Either span_id (resolve every reference inside that span) or reference text such as
    'Section 3.4 of [RFC5322]' together with doc (the document the reference appears in).
    status: resolved (target stored), external (outside the store) or unresolved (target section missing).
    """
    return _ds().resolve_reference(span_id, reference, doc, max_tokens)


@tool()
def lookup_definition(term: str, doc: str | None = None, k: int = 5, max_tokens: int = 2000) -> dict[str, Any]:
    """Find where a term is defined ('resource owner', 'eligible employee', 'mailbox'), with the defining text."""
    return _ds().lookup_definition(term, doc, k, max_tokens)


# ── verify ─────────────────────────────────────────────────────────────────────

@tool(core=True)
def get_evidence(span_id: int, verify: bool = True) -> dict[str, Any]:
    """Full text of one span with its provenance (byte range, SHA-256, parser version), section path,
    whether its version is the latest, and a live hash verification result."""
    return _ds().get_evidence(span_id, verify)


@tool()
def verify_span(span_id: int, deep: bool = False) -> dict[str, Any]:
    """Re-hash a span against the stored source text. verified=false means the evidence was altered
    and must not be cited. deep=true also re-parses the original file."""
    return _ds().verify_span(span_id, deep)


@tool(core=True)
def assemble_context(span_ids: list[int], token_budget: int = 4000) -> dict[str, Any]:
    """Build the final evidence pack for an answer. For each span: verify its SHA-256 (rejecting tampered
    spans), attach the latest version's text if the span is obsolete, append conflicting claims, then pack
    everything into token_budget (requested > newer version > conflicts). Cite the returned citations."""
    return _ds().assemble_context(span_ids, token_budget)


# ── versions and change ──────────────────────────────────────────────────────

@tool()
def list_versions(doc: str) -> dict[str, Any]:
    """All versions of a document (oldest→newest, append-only) with hashes, parser version, origin and
    declared relations such as 'obsoletes RFC 2821'."""
    return _ds().list_versions(doc)


@tool(core=True)
def diff_versions(doc: str, from_version: str | None = None, to_version: str | None = None,
                  level: str = "section", max_tokens: int = 4000) -> dict[str, Any]:
    """Compare two versions of a document. Defaults: latest vs the version before it.

    level: 'section' (added/removed/modified/renumbered sections with changed sentences),
    'claim' (requirements whose modality or value changed, added or removed), or
    'reference' (citations added/removed).
    """
    return _ds().diff_versions(doc, from_version, to_version, level, max_tokens)


@tool()
def blame(span_id: int | None = None, text: str | None = None, doc: str | None = None) -> dict[str, Any]:
    """Which version first introduced a passage, and its status (identical/similar/absent) in every version.
    Give span_id, or text + doc to locate the passage in the latest version."""
    return _ds().blame(span_id, text, doc)


@tool()
def find_affected_documents(doc: str, max_tokens: int = 3000) -> dict[str, Any]:
    """Documents that reference this document (cite, update or obsolete it). Use it to see what may need
    review when the document changes; flags sources that still cite an obsolete version."""
    return _ds().find_affected_documents(doc, max_tokens)


@tool(core=True)
def find_contradictions(doc: str | None = None, include_history: bool = False, include_rejected: bool = False,
                        k: int = 20, max_tokens: int = 4000) -> dict[str, Any]:
    """Statements from different documents that conflict (different values for the same limit, or opposing
    MUST/MUST NOT/MAY requirements). Both sides are returned as evidence; nothing is auto-resolved.

    status: confirmed (rule + LLM judge agree), candidate (rule only) or rejected (judge disagreed, hidden by default).
    include_history: also include pairs involving obsolete versions.
    """
    return _ds().find_contradictions(doc, include_history, include_rejected, k, max_tokens)


# ── add documents ────────────────────────────────────────────────────────────

@tool(core=True, annotations=ToolAnnotations(read_only_hint=False, destructive_hint=False,
                                             idempotent_hint=True, open_world_hint=False))
def add_document(path: str, doc: str | None = None, title: str | None = None, label: str | None = None,
                 wait_seconds: float = 20) -> dict[str, Any]:
    """Add a local file or folder (.pdf, .md, .markdown, .txt) to DocuSense.

    Re-adding a file whose content changed appends a new version (v1, v2, …); unchanged files are skipped,
    so it is safe to call repeatedly. doc / label set the document id / version label (single file only).
    Ingestion runs in the background: if it is not finished within wait_seconds the result has
    status 'running' and a job_id; call ingest_status(job_id) until it is 'done'.
    """
    from docusense.ingest.add import collect_files
    from docusense.jobs import check_allowed, jobs

    root = check_allowed(Path(path))
    files = collect_files([root])
    if not files:
        raise ValueError(f"no supported files (.pdf, .md, .markdown, .txt) at {root}")
    if len(files) > 1 and (doc or label):
        raise ValueError("doc/label can only be set when adding a single file")
    job = jobs.wait(jobs.submit(files, doc=doc, title=title, label=label), min(max(wait_seconds, 0), 120))
    return job.view()


@tool(core=True)
def ingest_status(job_id: str | None = None) -> dict[str, Any]:
    """Status of a background add_document job (or the 10 most recent jobs when job_id is omitted)."""
    from docusense.jobs import jobs

    if job_id is None:
        return {"jobs": [j.view() for j in jobs.recent()]}
    job = jobs.get(job_id)
    if job is None:
        raise ValueError(f"unknown job {job_id!r} (jobs are kept in memory until the server restarts)")
    return job.view()


# ── resources and prompts ─────────────────────────────────────────────────────

@server.resource("docusense://documents", name="documents", mime_type="application/json",
                 description="Every document and its versions (oldest→newest).")
def documents_resource() -> dict[str, Any]:
    return _ds().list_documents()


@server.resource("docusense://versions/{version_id}", name="version-text", mime_type="text/plain",
                 description="Canonical text of one document version (the bytes every citation offset points into).")
def version_text_resource(version_id: str) -> str:
    from docusense.store.blobs import BlobStore

    v = _ds().version(version_id)
    return BlobStore().get(v["text_sha256"]).decode("utf-8")


@server.prompt(title="Answer with verified citations")
def answer_with_evidence(question: str) -> str:
    """Answer a question using only verified DocuSense evidence."""
    return (f"Answer this question using DocuSense: {question}\n\n"
            "1. Find evidence with search (and search_claims for rules, limits or requirements).\n"
            "2. Read surrounding text with read_section where the passage alone is ambiguous.\n"
            "3. Call assemble_context with the span_ids you will rely on.\n"
            "4. Answer concisely. After each claim, cite the ds:// citation it rests on. If a span is from an "
            "obsolete version or has a conflicting statement, say so. If the evidence does not answer the "
            "question, say that instead of guessing.")


@server.prompt(title="What changed between versions")
def what_changed(doc: str) -> str:
    """Summarise what changed in the latest version of a document."""
    return (f"Explain what changed in the latest version of '{doc}' using DocuSense.\n"
            "1. list_versions to see the history.\n"
            "2. diff_versions at level 'claim' (changed requirements and values) and level 'section'.\n"
            "3. For the most important changes, show old vs new text with both citations.\n"
            "4. find_affected_documents to list documents that may need review.")


@server.prompt(title="Audit for contradictions")
def audit_contradictions(doc: str | None = None) -> str:
    """Review conflicting statements across documents."""
    scope = f"involving '{doc}'" if doc else "across all documents"
    return (f"Audit DocuSense for contradictions {scope}.\n"
            "1. find_contradictions" + (f"(doc='{doc}')" if doc else "") + ".\n"
            "2. For each pair, decide whether it is a real conflict, a scoped exception, or a false positive, "
            "quoting both sides with their citations.\n"
            "3. Do not resolve conflicts yourself: list who should decide and which document is newer.")


# ── entry points ─────────────────────────────────────────────────────────────

def main() -> None:
    import sys

    import pymupdf

    # stdout carries JSON-RPC: route MuPDF warnings (stdout by default) to stderr.
    pymupdf.set_messages(stream=sys.stderr)
    server.run()


def http_app(host: str = "127.0.0.1", path: str = "/mcp"):
    """Streamable HTTP ASGI app, with bearer-token auth when DOCUSENSE_HTTP_TOKEN is set."""
    app = server.streamable_http_app(streamable_http_path=path, host=host)
    token = get_settings().http_token
    if not token:
        return app

    import hmac

    from starlette.responses import JSONResponse

    async def guarded(scope, receive, send):
        if scope["type"] == "http":
            headers = dict(scope.get("headers") or [])
            if not hmac.compare_digest(headers.get(b"authorization", b""), f"Bearer {token}".encode()):
                await JSONResponse({"error": "unauthorized"}, status_code=401,
                                   headers={"WWW-Authenticate": "Bearer"})(scope, receive, send)
                return
        await app(scope, receive, send)

    return guarded


if __name__ == "__main__":
    main()
