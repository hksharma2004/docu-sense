"""DocuSense command line: `docusense db init|reset`, `ingest`, `verify`, `sections`, `stats`."""

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
def ingest(manifest: Path = typer.Argument(Path("corpus/manifest.yaml"))) -> None:
    """Ingest every document version listed in a manifest (already-ingested versions are skipped)."""
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
            """SELECT v.id, v.format, v.seq, v.text_bytes, jsonb_array_length(v.page_map) AS pages,
                      (SELECT count(*) FROM sections s WHERE s.version_id = v.id) AS sections,
                      (SELECT count(*) FROM spans p WHERE p.version_id = v.id) AS spans
               FROM versions v ORDER BY v.document_id, v.seq"""
        ).fetchall()
    table = Table("version", "format", "seq", "pages", "bytes", "sections", "spans")
    for r in rows:
        table.add_row(r["id"], r["format"], str(r["seq"]), str(r["pages"]), str(r["text_bytes"]),
                      str(r["sections"]), str(r["spans"]))
    console.print(table)


if __name__ == "__main__":
    app()
