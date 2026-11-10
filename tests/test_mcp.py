"""MCP surface: tool registration, clean errors, add_document jobs, resources and prompts."""

import asyncio
import hashlib
import json
import threading

import numpy as np
import pytest

ALL_TOOLS = {"list_documents", "get_section_map", "read_section", "search", "search_claims",
             "resolve_reference", "lookup_definition", "get_evidence", "verify_span", "assemble_context",
             "list_versions", "diff_versions", "blame", "find_affected_documents", "find_contradictions",
             "add_document", "ingest_status"}

POLICY_V1 = "# Travel Policy\n\n## 1. Hotels\n\nEmployees MUST NOT book hotels above 150 USD per night.\n"
POLICY_V2 = "# Travel Policy\n\n## 1. Hotels\n\nEmployees MUST NOT book hotels above 200 USD per night.\n"


def _fake_vec(text: str) -> np.ndarray:
    vec = np.zeros(64, dtype=np.float32)
    for word in text.lower().split():
        vec[int(hashlib.md5(word.encode()).hexdigest(), 16) % 64] += 1
    return vec


@pytest.fixture
def mcp(tmp_path, monkeypatch):
    """The MCP server pointed at a fresh SQLite home, with an offline fake embedder."""
    from docusense import config, mcp_server
    from docusense.index import embed

    home = tmp_path / "home"
    docs = tmp_path / "docs"
    docs.mkdir()
    monkeypatch.setenv("DOCUSENSE_HOME", str(home))
    monkeypatch.setenv("DOCUSENSE_DATABASE_URL", "")
    monkeypatch.setenv("DOCUSENSE_STORE_DIR", "")
    monkeypatch.setenv("DOCUSENSE_ADD_ROOTS", str(docs))
    config.get_settings.cache_clear()
    monkeypatch.setattr(mcp_server, "_local", threading.local())
    monkeypatch.setattr(mcp_server, "_schema_ready", False)
    monkeypatch.setattr(embed, "embed_texts", lambda texts: [_fake_vec(t) for t in texts])
    monkeypatch.setattr(embed, "embed_query", _fake_vec)
    yield mcp_server.server, docs
    config.get_settings.cache_clear()


def call(server, name, **args):
    result = asyncio.run(server.call_tool(name, args))
    return json.loads(result.content[0].text)


def test_tools_registered():
    from docusense.mcp_server import server

    assert {t.name for t in asyncio.run(server.list_tools())} == ALL_TOOLS


def test_unknown_document_is_a_clean_tool_error(mcp):
    from mcp.server.mcpserver.exceptions import ToolError

    server, _ = mcp
    with pytest.raises(ToolError, match="unknown document"):
        asyncio.run(server.call_tool("get_section_map", {"doc": "nope"}))


def test_add_document_versions_and_search(mcp):
    server, docs = mcp
    f = docs / "travel.md"
    f.write_text(POLICY_V1)
    job = call(server, "add_document", path=str(f), wait_seconds=60)
    assert job["status"] == "done", job
    assert job["results"][0]["version_id"] == "travel@v1"

    f.write_text(POLICY_V2)
    job = call(server, "add_document", path=str(f), wait_seconds=60)
    assert job["results"][0]["version_id"] == "travel@v2"
    assert call(server, "ingest_status", job_id=job["id"])["status"] == "done"

    hits = call(server, "search", query="hotels per night", mode="lexical")["results"]
    assert {h["version"] for h in hits} == {"travel@v1", "travel@v2"}  # index reloaded after each add
    diff = call(server, "diff_versions", doc="travel", level="claim")
    assert diff["summary"]["changed"] == 1, diff


def test_add_document_respects_allowed_roots(mcp, tmp_path):
    from mcp.server.mcpserver.exceptions import ToolError

    server, _ = mcp
    outside = tmp_path / "secret.md"
    outside.write_text("# secret\n")
    with pytest.raises(ToolError, match="outside the allowed folders"):
        asyncio.run(server.call_tool("add_document", {"path": str(outside)}))


def test_resources_and_prompts(mcp):
    server, docs = mcp
    (docs / "travel.md").write_text(POLICY_V1)
    call(server, "add_document", path=str(docs / "travel.md"), wait_seconds=60)

    listing = list(asyncio.run(server.read_resource("docusense://documents")))
    assert json.loads(listing[0].content)["documents"][0]["document"] == "travel"
    text = list(asyncio.run(server.read_resource("docusense://versions/travel@v1")))[0].content
    assert "150 USD" in text

    prompt = asyncio.run(server.get_prompt("answer_with_evidence", {"question": "hotel cap?"}))
    assert "hotel cap?" in prompt.messages[0].content.text
