"""`docusense setup` writes client configs without clobbering existing servers."""

import json

from docusense import cli


def test_merge_keeps_other_servers_and_backs_up(tmp_path):
    cfg = tmp_path / "claude_desktop_config.json"
    cfg.write_text(json.dumps({"mcpServers": {"other": {"command": "x"}}, "theme": "dark"}))
    msg = cli._merge_mcp_json(cfg, ["/bin/docusense", "serve-mcp"])
    data = json.loads(cfg.read_text())
    assert data["mcpServers"]["other"] == {"command": "x"} and data["theme"] == "dark"
    assert data["mcpServers"]["docusense"] == {"command": "/bin/docusense", "args": ["serve-mcp"]}
    assert (tmp_path / "claude_desktop_config.json.bak").exists() and "added" in msg
    assert "already" in cli._merge_mcp_json(cfg, ["/bin/docusense", "serve-mcp"])


def test_merge_creates_missing_file(tmp_path):
    cfg = tmp_path / "sub" / "mcp.json"
    cli._merge_mcp_json(cfg, ["docusense", "serve-mcp"])
    assert json.loads(cfg.read_text())["mcpServers"]["docusense"]["command"] == "docusense"


def test_cli_search_and_savings_run(tmp_path, monkeypatch):
    from typer.testing import CliRunner

    from docusense import config
    from docusense.index import embed

    monkeypatch.setenv("DOCUSENSE_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("DOCUSENSE_DATABASE_URL", "")
    monkeypatch.setenv("DOCUSENSE_STORE_DIR", "")
    config.get_settings.cache_clear()
    monkeypatch.setattr(embed, "embed_texts", lambda texts: [[1.0, 0.0]] * len(texts))
    monkeypatch.setattr(embed, "embed_query", lambda text: [1.0, 0.0])
    doc = tmp_path / "travel.md"
    doc.write_text("# Travel\n\n## 1. Hotels\n\nEmployees MUST NOT book hotels above 150 USD per night.\n")
    runner = CliRunner()
    try:
        assert runner.invoke(cli.app, ["add", str(doc)]).exit_code == 0
        out = runner.invoke(cli.app, ["search", "hotels", "--mode", "lexical"])
        assert out.exit_code == 0 and "ds://travel@v1" in out.output
        assert runner.invoke(cli.app, ["savings"]).exit_code == 0
    finally:
        config.get_settings.cache_clear()
