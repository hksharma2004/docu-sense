# DocuSense

Stop pasting whole documents into Claude. DocuSense lets Claude read your PDFs, Word files and docs
by section and by claim, so it loads the few hundred tokens that answer the question instead of the
whole file. Every answer cites the exact passage, and each passage is checked against a SHA-256 of
its bytes.

On our benchmark of real tasks over long technical standards and policies (lookups, version diffs
and conflict checks), DocuSense used 6,869 tokens, against 15,765 for vector RAG and 160,179 for
pasting the documents: about 23 times less context than pasting.

## What you can ask

- "What does the MSA say about termination for convenience?" and get the exact clause, cited.
- "What changed between v1 and v2 of the security policy?" and get only the changed passages.
- "Does the vendor contract conflict with our data retention policy?" and see both sides.
- "Add ~/Documents/contracts" to index a whole folder.

Supported files: PDF, Word (.docx), HTML, Markdown and plain text.

## Requirements

[uv](https://docs.astral.sh/uv/) must be installed. The plugin starts the server with
`uvx docusense-mcp==0.1.2 serve-mcp`, which downloads the pinned
[docusense-mcp](https://pypi.org/project/docusense-mcp/) package from PyPI on first run.

## What the plugin runs, stores and sends

- **Runs** one local MCP server (stdio) on your computer. It exposes tools for searching, reading,
  verifying, diffing and adding documents, plus one skill that teaches Claude to use them.
- **Stores** its index in `~/.docusense` (set `DOCUSENSE_HOME` to move it). Your documents are read
  from the paths you add and never leave your machine.
- **Downloads**, on first run, the package and its dependencies from PyPI and the
  `BAAI/bge-small-en-v1.5` embedding model from Hugging Face. Embeddings are computed locally.
- **Sends nothing else.** DocuSense can optionally use an LLM for contradiction checks, but this
  plugin sets `DOCUSENSE_LLM_PROVIDER=none`, so it makes no LLM calls and ignores any API keys in
  your environment.
- Records token usage per tool call in a local ledger for `docusense savings`; set
  `DOCUSENSE_SAVINGS_LOG=0` to turn it off.

## Links

- Website: https://docusense.xyz
- Source and full documentation: https://github.com/hksharma2004/docu-sense
- License: MIT
