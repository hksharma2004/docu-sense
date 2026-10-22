"""DocuSense MCP server (stdio). Fine-grained document tools for AI agents.

Run:  uv run docusense serve-mcp
"""

from functools import lru_cache
from typing import Any

from mcp.server import MCPServer

from docusense.db.conn import connect
from docusense.services import DocuSense

INSTRUCTIONS = """DocuSense exposes a versioned corpus of IETF RFCs (plus a few synthetic policy documents)
as fine-grained tools. Typical workflow:
  1. list_documents / get_section_map to orient yourself,
  2. search (lexical, semantic or hybrid) or search_claims / lookup_definition to find evidence,
  3. read_section to read surrounding text, resolve_reference to follow "Section X of [RFCnnnn]" links,
  4. get_evidence / verify_span before citing.
Every span has a citation like ds://smtp@rfc5321#§4.5.3.1.6:b141982-142194 and a SHA-256.
Always cite these citations in answers. If a result has `newer_version`, the cited version is obsolete:
check the newer version before answering. Documents accept ids ('smtp'), version ids ('smtp@rfc5321')
or RFC names ('RFC 5321')."""

server = MCPServer("docusense", instructions=INSTRUCTIONS)


@lru_cache
def _ds() -> DocuSense:
    conn = connect()
    conn.autocommit = True
    return DocuSense(conn)


@server.tool()
def list_documents() -> dict[str, Any]:
    """List every document in the corpus with its versions (oldest→newest) and which version is latest."""
    return _ds().list_documents()


@server.tool()
def get_section_map(doc: str, version: str | None = None, max_depth: int = 3, max_tokens: int = 3000) -> dict[str, Any]:
    """Table of contents of a document version: section numbers, titles, levels and page ranges.

    doc: document id ('smtp'), version id ('smtp@rfc5321') or RFC name ('RFC 5321'). Defaults to the latest version.
    max_depth: deepest heading level to include (1 = top-level only).
    """
    return _ds().get_section_map(doc, version, max_depth, max_tokens)


@server.tool()
def read_section(doc: str, section: str, version: str | None = None, include_subsections: bool = False,
                 max_tokens: int = 3000) -> dict[str, Any]:
    """Read the paragraphs of one section, each with a citation and SHA-256.

    section: a section number ('4.5.3.1.6', 'A.1') or part of a title ('Terminology').
    include_subsections: also return text of nested subsections.
    """
    return _ds().read_section(doc, section, version, include_subsections, max_tokens)


@server.tool()
def search(query: str, mode: str = "hybrid", doc: str | None = None, k: int = 5, max_tokens: int = 2500) -> dict[str, Any]:
    """Find paragraphs relevant to a query.

    mode: 'lexical' (BM25, best for exact terms, numbers, identifiers), 'semantic' (embeddings, best for
    paraphrased questions) or 'hybrid' (both, fused with reciprocal rank fusion).
    doc: optional filter; a document id searches all its versions, a version id or RFC name only that version.
    """
    return _ds().search(query, mode, doc, k, max_tokens)


@server.tool()
def search_claims(topic: str | None = None, subject: str | None = None, modality: str | None = None,
                  claim_type: str | None = None, doc: str | None = None, k: int = 10,
                  max_tokens: int = 2500) -> dict[str, Any]:
    """Search normative claims extracted from the documents (sentence-level evidence).

    topic: words describing what the claim is about ('implicit grant', 'text line length').
    subject: who the claim applies to ('clients', 'authorization server').
    modality: BCP 14 keyword: MUST, MUST NOT, SHOULD, SHOULD NOT, MAY (synonyms like SHALL/REQUIRED accepted).
    claim_type: requirement | exclusion | numeric.
    Numeric claims include value and unit (e.g. 1000 octet).
    """
    return _ds().search_claims(topic, subject, modality, claim_type, doc, k, max_tokens)


@server.tool()
def resolve_reference(span_id: int | None = None, reference: str | None = None, doc: str | None = None,
                      max_tokens: int = 3000) -> dict[str, Any]:
    """Follow cross-references to their target section, with a preview of the target text.

    Either span_id (resolve every reference inside that span) or reference text such as
    'Section 3.4 of [RFC5322]' together with doc (the document the reference appears in).
    status: resolved (target in corpus), external (outside corpus) or unresolved (target section missing).
    """
    return _ds().resolve_reference(span_id, reference, doc, max_tokens)


@server.tool()
def lookup_definition(term: str, doc: str | None = None, k: int = 5, max_tokens: int = 2000) -> dict[str, Any]:
    """Find where a term is defined ('resource owner', 'MUST', 'mailbox'), with the defining text."""
    return _ds().lookup_definition(term, doc, k, max_tokens)


@server.tool()
def get_evidence(span_id: int, verify: bool = True) -> dict[str, Any]:
    """Full text of one span with its provenance (byte range, SHA-256, parser version), section path,
    whether its version is the latest, and a live hash verification result."""
    return _ds().get_evidence(span_id, verify)


@server.tool()
def verify_span(span_id: int, deep: bool = False) -> dict[str, Any]:
    """Re-hash a span against the stored source text. verified=false means the evidence was altered
    and must not be cited. deep=true also re-parses the original PDF/Markdown file."""
    return _ds().verify_span(span_id, deep)


def main() -> None:
    server.run()


if __name__ == "__main__":
    main()
