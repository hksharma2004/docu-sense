"""DocuSense command line.

Everyday use:  `docusense add <files or folders>`, `docusense list`, `docusense serve-mcp`, `docusense info`.
Corpus / dev:  `docusense ingest <manifest>`, `extract`, `index`, `conflicts`, `verify`, `stats`, `db init|reset`.
"""

import json
from pathlib import Path

import typer
import yaml
from rich.console import Console
from rich.table import Table

from docusense.db.conn import connect, init_schema, reset_schema
from docusense.ingest.pipeline import ingest_version
from docusense.provenance import Verifier

app = typer.Typer(no_args_is_help=True, add_completion=False)
db_app = typer.Typer(no_args_is_help=True)
app.add_typer(db_app, name="db", help="Database schema management.")
console = Console()


@db_app.command("init")
def db_init() -> None:
    """Create tables (idempotent)."""
    with connect() as conn:
        init_schema(conn)
    console.print("[green]schema ready[/]")


@db_app.command("reset")
def db_reset(yes: bool = typer.Option(False, "--yes", help="Skip confirmation.")) -> None:
    """Drop ALL data and recreate the schema (dev only)."""
    if not yes:
        typer.confirm("This deletes every ingested version. Continue?", abort=True)
    with connect() as conn:
        reset_schema(conn)
    console.print("[yellow]schema reset[/]")


@app.command()
def add(
    paths: list[Path] = typer.Argument(..., help="Files (.pdf, .docx, .html, .md, .txt) or folders to add."),
    doc: str | None = typer.Option(None, "--doc", help="Document id (default: derived from the file name). Single file only."),
    title: str | None = typer.Option(None, help="Document title for a new document."),
    label: str | None = typer.Option(None, help="Version label (default v1, v2, ...). Single file only."),
    index: bool = typer.Option(True, help="Update search indexes afterwards (downloads the embedding model on first use)."),
) -> None:
    """Add documents. Re-adding a changed file appends a new version; unchanged files are skipped."""
    from docusense.ingest.add import add_file, collect_files, refresh_derived

    files = collect_files(paths)
    if not files:
        console.print("[yellow]no supported files found[/]")
        raise typer.Exit(1)
    if len(files) > 1 and (doc or label):
        console.print("[red]--doc/--label apply to a single file[/]")
        raise typer.Exit(2)
    table = Table("file", "version", "status", "pages", "sections", "spans", "note")
    added = 0
    with connect() as conn:
        init_schema(conn)
        for f in files:
            try:
                r = add_file(conn, f, doc=doc, title=title, label=label)
            except ValueError as e:
                table.add_row(f.name, "", "[red]error[/]", "", "", "", str(e))
                continue
            added += r.status == "ingested"
            table.add_row(f.name, r.version_id, r.status, str(r.pages or ""), str(r.sections or ""),
                          str(r.spans or ""), r.note)
        console.print(table)
        if added:
            with console.status("extracting claims, references and building indexes…"):
                stats = refresh_derived(conn, index=index)
            console.print(f"[green]{added} new version(s)[/] · {stats}")


@app.command("list")
def list_cmd() -> None:
    """List documents and their versions."""
    from docusense.services import DocuSense

    with connect() as conn:
        init_schema(conn)
        docs = DocuSense(conn).list_documents()["documents"]
    if not docs:
        console.print("no documents yet — add some with [bold]docusense add <file or folder>[/]")
        return
    table = Table("document", "title", "versions (oldest → newest)")
    for d in docs:
        table.add_row(d["document"], d["title"], ", ".join(v["label"] + ("*" if v["is_latest"] else "") for v in d["versions"]))
    console.print(table)


@app.command()
def info() -> None:
    """Show where DocuSense keeps its data and which backend it uses."""
    from docusense.config import get_settings

    s = get_settings()
    url = s.resolved_database_url
    with connect() as conn:
        init_schema(conn)
        n_docs = conn.execute("SELECT count(*) AS n FROM documents").fetchone()["n"]
        n_versions = conn.execute("SELECT count(*) AS n FROM versions").fetchone()["n"]
        backend = conn.dialect
    shown = url if backend == "sqlite" else url.split("@")[-1]  # never print credentials
    console.print(f"home:       {s.home}\nbackend:    {backend} ({shown})\nstore:      {s.resolved_store_dir}\n"
                  f"documents:  {n_docs} ({n_versions} versions)\nembeddings: {s.embed_model}")


@app.command()
def ingest(
    manifest: Path = typer.Argument(Path("corpus/manifest.yaml")),
    extract: bool = typer.Option(True, help="Run reference/definition/claim extraction afterwards."),
    index: bool = typer.Option(True, help="Build BM25 + embedding indexes afterwards."),
    llm_fallback: bool = typer.Option(False, help="Use the bounded LLM fallback during extraction (see DOCUSENSE_LLM_PROVIDER)."),
) -> None:
    """Ingest every version in a manifest (already-ingested versions are skipped), then extract + index."""
    spec = yaml.safe_load(manifest.read_text())
    base = manifest.parent
    table = Table("version", "status", "layout", "pages", "sections", "spans")
    with connect() as conn:
        init_schema(conn)
        for doc in spec["documents"]:
            for seq, v in enumerate(doc["versions"], start=1):
                r = ingest_version(
                    conn,
                    document_id=doc["id"], title=doc["title"], family=doc["family"],
                    label=v["label"], seq=seq, path=base / v["file"], origin=v.get("origin"),
                )
                table.add_row(r.version_id, r.status, r.layout, str(r.pages or ""),
                              str(r.sections or ""), str(r.spans or ""))
    console.print(table)
    if extract:
        extract_cmd(version=None, llm_fallback=llm_fallback)
        conflicts_cmd(llm_judge=llm_fallback, max_judge_calls=300)
    if index:
        index_cmd()


@app.command("extract")
def extract_cmd(
    version: str | None = typer.Option(None, help="Limit to one version id."),
    llm_fallback: bool = typer.Option(False, help="Use the bounded LLM fallback for unresolved subjects."),
) -> None:
    """Deterministic extraction: cross-references, definitions, claims (re-runnable)."""
    from docusense.extract.run import extract_all

    table = Table("version", "refs resolved", "external", "unresolved", "definitions", "claims", "llm calls")
    with connect() as conn:
        for s in extract_all(conn, llm_fallback=llm_fallback, version_id=version):
            table.add_row(s.version_id, str(s.refs["resolved"]), str(s.refs["external"]),
                          str(s.refs["unresolved"]), str(s.definitions), str(sum(s.claims.values())),
                          str(s.llm_calls))
    console.print(table)


@app.command("index")
def index_cmd() -> None:
    """Build the BM25 index and embed any spans that have no embedding yet."""
    from docusense.index import bm25, embed

    with connect() as conn:
        console.print(f"bm25: indexed {bm25.build(conn)} spans")
        n = embed.build(conn, progress=lambda done, total: console.print(f"  embedded {done}/{total}"))
        console.print(f"embeddings: {n} new")


@app.command("search")
def search_cmd(
    query: str,
    mode: str = typer.Option("hybrid", help="lexical | semantic | hybrid"),
    doc: str | None = typer.Option(None),
    k: int = typer.Option(5),
) -> None:
    """Search spans from the command line."""
    from docusense.services import DocuSense

    with connect() as conn:
        for rank, r in enumerate(DocuSense(conn).search(query, mode, doc, k)["results"], 1):
            console.print(f"[dim]{rank}.[/] [bold]{r['citation']}[/] [dim]p.{r['page']}[/]")
            console.print("  " + " ".join(r["text"].split())[:220])


@app.command("define")
def define_cmd(term: str, doc: str | None = typer.Option(None)) -> None:
    """Look up where a term is defined."""
    from docusense.services import DocuSense

    with connect() as conn:
        for r in DocuSense(conn).lookup_definition(term, doc)["results"]:
            console.print(f"[bold]{r['term']}[/] {r['citation']} [dim]{r['method']}[/]")
            console.print("  " + " ".join(r["text"].split())[:220])


@app.command("conflicts")
def conflicts_cmd(
    llm_judge: bool = typer.Option(False, help="Confirm candidates with the bounded LLM judge."),
    max_judge_calls: int = typer.Option(300),
) -> None:
    """Recompute cross-document contradiction candidates."""
    from docusense.versions.conflicts import detect

    with connect() as conn:
        console.print(detect(conn, llm_judge=llm_judge, max_judge_calls=max_judge_calls))


@app.command("serve-api")
def serve_api(port: int = typer.Option(8000), reload: bool = typer.Option(False)) -> None:
    """Run the REST API for the viewer."""
    import uvicorn

    uvicorn.run("docusense.api:app", host="127.0.0.1", port=port, reload=reload)


@app.command("serve-mcp")
def serve_mcp(
    http: bool = typer.Option(False, "--http", help="Serve Streamable HTTP instead of stdio."),
    host: str = typer.Option("127.0.0.1", help="HTTP bind address."),
    port: int = typer.Option(8765, help="HTTP port."),
    path: str = typer.Option("/mcp", help="HTTP endpoint path."),
) -> None:
    """Run the MCP server: stdio by default (Claude Desktop/Code, Cursor, VS Code), or --http."""
    if not http:
        from docusense.mcp_server import main

        main()
        return

    import uvicorn

    from docusense.config import get_settings
    from docusense.mcp_server import http_app

    loopback = host in ("127.0.0.1", "localhost", "::1")
    if not loopback and not get_settings().http_token:
        console.print("[red]refusing to listen on a non-loopback address without DOCUSENSE_HTTP_TOKEN set[/]")
        raise typer.Exit(2)
    err = Console(stderr=True)
    err.print(f"DocuSense MCP (Streamable HTTP) on http://{host}:{port}{path}"
              + (" · bearer token required" if get_settings().http_token else ""))
    uvicorn.run(http_app(host=host, path=path), host=host, port=port, log_level="warning")


@app.command()
def verify(
    span: int | None = typer.Option(None, help="Verify one span id."),
    version: str | None = typer.Option(None, help="Limit to one version id, e.g. smtp@rfc5321."),
    deep: bool = typer.Option(False, help="Also re-parse the source file (determinism check)."),
) -> None:
    """Re-hash spans against the content-addressed canonical text."""
    with connect() as conn:
        verifier = Verifier(conn)
        if span is not None:
            console.print_json(json.dumps(verifier.verify_span(span, deep=deep)))
            return
        report = verifier.verify_all(deep=deep, version_id=version)

    table = Table("version", "spans", "verified", "failed span ids")
    for vid, s in sorted(report["versions"].items()):
        ok = s["verified"] == s["total"]
        table.add_row(vid, str(s["total"]), f"[{'green' if ok else 'red'}]{s['verified']}[/]",
                      ", ".join(map(str, s["failed"][:8])) + (" …" if len(s["failed"]) > 8 else ""))
    console.print(table)
    pct = 100 * report["verified"] / report["total"] if report["total"] else 0
    console.print(f"[bold]{report['verified']}/{report['total']} spans verified ({pct:.1f}%)[/]")
    if report["verified"] != report["total"]:
        raise typer.Exit(1)


@app.command()
def sections(version: str = typer.Argument(..., help="Version id, e.g. smtp@rfc5321.")) -> None:
    """Print the section map of a version."""
    with connect() as conn:
        rows = conn.execute(
            """SELECT number, title, level, page_start, page_end, start_byte, end_byte
               FROM sections WHERE version_id = %s ORDER BY ordinal""", (version,)
        ).fetchall()
    if not rows:
        console.print(f"[red]no sections for {version}[/]")
        raise typer.Exit(1)
    for r in rows:
        indent = "  " * max(r["level"] - 1, 0)
        console.print(f"{indent}{r['number'] or '·'} {r['title']}  "
                      f"[dim]p{r['page_start']}-{r['page_end']} b{r['start_byte']}-{r['end_byte']}[/]")


@app.command()
def stats() -> None:
    """Corpus overview."""
    with connect() as conn:
        rows = conn.execute(
            """SELECT v.id, v.format, v.seq, jsonb_array_length(v.page_map) AS pages,
                      (SELECT count(*) FROM sections s WHERE s.version_id = v.id) AS sections,
                      (SELECT count(*) FROM spans p WHERE p.version_id = v.id AND p.kind <> 'sentence') AS spans,
                      (SELECT count(*) FROM refs r WHERE r.version_id = v.id) AS refs,
                      (SELECT count(*) FROM definitions d WHERE d.version_id = v.id) AS defs,
                      (SELECT count(*) FROM claims c WHERE c.version_id = v.id) AS claims
               FROM versions v ORDER BY v.document_id, v.seq"""
        ).fetchall()
    table = Table("version", "format", "seq", "pages", "sections", "spans", "refs", "defs", "claims")
    for r in rows:
        table.add_row(r["id"], r["format"], str(r["seq"]), str(r["pages"]), str(r["sections"]),
                      str(r["spans"]), str(r["refs"]), str(r["defs"]), str(r["claims"]))
    console.print(table)


@app.command()
def savings(
    days: int = typer.Option(0, help="Only count the last N days (0 = all time)."),
    as_json: bool = typer.Option(False, "--json", help="Machine-readable output."),
) -> None:
    """Tokens your agents read through DocuSense vs. pasting the same documents into context."""
    import time

    from docusense import savings as ledger

    with connect() as conn:
        init_schema(conn)
        version_tokens = {r["id"]: r["text_bytes"] // 4
                          for r in conn.execute("SELECT id, text_bytes FROM versions").fetchall()}
    s = ledger.summarize(version_tokens, since=time.time() - days * 86400 if days else None)
    if as_json:
        console.print_json(json.dumps(s))
        return
    if not s["calls"]:
        console.print(f"No agent activity yet. Connect an agent ([bold]docusense setup[/]) and ask it about your documents.\n"
                      f"Ledger: {ledger.ledger_path()}")
        return
    console.print(f"[bold]{s['sessions']}[/] agent sessions · [bold]{s['calls']}[/] tool calls\n"
                  f"read via DocuSense:   [bold]{s['returned']:>12,}[/] tokens\n"
                  f"pasting the docs:     [bold]{s['paste']:>12,}[/] tokens")
    if s["returned"] < s["paste"]:
        console.print(f"[green]saved:                {s['saved']:>12,} tokens ({s['ratio']}x less context)[/]")
    else:
        console.print("[yellow]no saving: these documents are small enough to paste directly. "
                      "DocuSense pays off on long or many documents.[/]")
    top = ", ".join(f"{t} ×{n}" for t, n in list(s["tools"].items())[:6])
    console.print(f"[dim]most used: {top}\nbaseline = each document version an agent touched, pasted once per session "
                  f"(chars/4). Ledger: {ledger.ledger_path()} · disable with DOCUSENSE_SAVINGS_LOG=0[/]")


def _server_command() -> list[str]:
    """Absolute command for the MCP server: GUI clients (Claude Desktop, Cursor) don't inherit your shell PATH."""
    import shutil
    import sys

    exe = shutil.which("docusense")
    if exe:
        return [str(Path(exe).resolve()), "serve-mcp"]
    uvx = shutil.which("uvx")
    if uvx:
        return [uvx, "--from", "docusense-mcp", "docusense", "serve-mcp"]
    return [sys.executable, "-m", "docusense.cli", "serve-mcp"]


def _desktop_config() -> Path:
    import os
    import sys

    if sys.platform == "darwin":
        return Path.home() / "Library/Application Support/Claude/claude_desktop_config.json"
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA", Path.home())) / "Claude/claude_desktop_config.json"
    return Path.home() / ".config/Claude/claude_desktop_config.json"


def _merge_mcp_json(path: Path, cmd: list[str]) -> str:
    data = {}
    if path.exists():
        text = path.read_text(encoding="utf-8").strip()
        data = json.loads(text) if text else {}
        path.with_suffix(path.suffix + ".bak").write_text(text, encoding="utf-8")
    entry = {"command": cmd[0], "args": cmd[1:]}
    if data.get("mcpServers", {}).get("docusense") == entry:
        return f"already configured in {path}"
    data.setdefault("mcpServers", {})["docusense"] = entry
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return f"added to {path} (backup: {path.name}.bak) — restart the app"


@app.command()
def setup(
    client: str = typer.Argument("claude-code", help="claude-code | claude-desktop | cursor | print"),
) -> None:
    """Register the DocuSense MCP server with an agent client."""
    import shutil
    import subprocess

    cmd = _server_command()
    client = client.lower()
    if client == "claude-code":
        claude = shutil.which("claude")
        if not claude:
            raise RuntimeError("`claude` CLI not found. Install Claude Code, or use: docusense setup print")
        done = subprocess.run([claude, "mcp", "add", "--scope", "user", "docusense", "--", *cmd],
                              capture_output=True, text=True)
        out = (done.stdout + done.stderr).strip()
        if done.returncode and "already exists" not in out:
            raise RuntimeError(out or "claude mcp add failed")
        console.print(out or "added", "\n[green]Claude Code[/]: run /mcp in a session to confirm.")
    elif client == "claude-desktop":
        console.print(_merge_mcp_json(_desktop_config(), cmd))
    elif client == "cursor":
        console.print(_merge_mcp_json(Path.home() / ".cursor/mcp.json", cmd))
    elif client == "print":
        console.print_json(json.dumps({"mcpServers": {"docusense": {"command": cmd[0], "args": cmd[1:]}}}))
    else:
        raise ValueError(f"unknown client {client!r}: use claude-code, claude-desktop, cursor or print")
    console.print("[dim]Next: `docusense add <folder>` your docs, ask your agent about them, then `docusense savings`.[/]")


if __name__ == "__main__":
    app()


def main() -> None:
    """Console entry point: expected errors print one line instead of a traceback."""
    import sys

    try:
        app()
    except (ValueError, LookupError, OSError, RuntimeError) as e:
        Console(stderr=True).print(f"[red]error:[/] {e}")
        sys.exit(1)
