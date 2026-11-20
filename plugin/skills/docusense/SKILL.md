---
name: docusense
description: Answer questions about the user's PDFs, Word files and other documents with exact, verified citations by reading them through the DocuSense tools section by section instead of loading whole files. Use when the user asks what a document says, wants a fact or definition with its source, asks what changed between versions of a document, or wants to know whether documents conflict. Also use when the user wants to add files or folders for Claude to read.
---

# Reading documents with DocuSense

DocuSense keeps the user's documents in a local, versioned index. Every passage it returns has a
citation like `ds://<doc>@<version>#§<section>:b<start>-<end>` and a SHA-256 of its exact bytes.
Read only the parts that answer the question; never ask for a whole document when a section will do.

## Adding documents

If the user names files or folders that are not indexed yet, call `add_document` with the local
path. Ingestion runs in the background: poll `ingest_status` until the job is done before searching.

## Answering a question

1. `list_documents` to see what is indexed (skip it if you already know the document id).
2. Find the evidence:
   - `search` (hybrid by default) for most questions;
   - `lookup_definition` when the question is what a term means;
   - `search_claims` for obligations, requirements and other statements of a given kind;
   - `get_section_map` to see a document's table of contents and pick the right section.
3. `read_section` for the surrounding text, and `resolve_reference` to follow cross-references
   such as "see Section 4.2".
4. `get_evidence` (it verifies the hash) or `assemble_context` for the passages you will rely on.

Cite the returned citations verbatim. Never cite a passage whose `verified` is false. If a result
carries `newer_version`, the passage comes from an outdated version: check the newer one first.

## Versions and conflicts

- What changed: `list_versions`, then `diff_versions`. `blame` tells you which version introduced
  a passage. `find_affected_documents` lists documents that refer to one that changed.
- Conflicts: `find_contradictions` returns pairs of conflicting statements. Show both sides with
  their citations and let the user judge; do not pick a winner.
